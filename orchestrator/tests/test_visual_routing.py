#!/usr/bin/env python3
"""
WP-4.2 — capability-conditional vision routing gate tests.

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* ``route_for_image_input`` selects an extractor from the preferred bucket when
  the downstream model is text-only and an image_path is present.
* Falls back to the fallback bucket when the preferred bucket has no
  vision-capable endpoint.
* Sets ``no_vision_available=True`` when neither bucket has a vision-capable
  endpoint (WP-4.4 UX fallback).
* Direct pass-through when the downstream model is ``vision_capable: true``
  — no extractor is selected.
* Missing ``vision_capable`` field on an endpoint defaults to ``False``
  (defensive reader contract).
* No-op when ``image_path`` is absent from ``context_pkg``.

Tests use ``threading.Thread`` stub mirroring ``test_visual_e2e.py`` /
``test_visual_merged_input.py`` for server integration — but most of this
file directly exercises ``boot.route_for_image_input`` without touching the
server at all (the routing function is pure w.r.t. the supplied routing
config, no I/O, no model calls).
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))


class _NoopThread:
    """Stub thread that fires no side-effects — mirrors test_visual_e2e."""

    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def join(self, *a, **k):
        pass

    daemon = True


def _mock_routing_config(
    include_local: bool = True,
    include_api_vision: bool = True,
    include_api_text: bool = True,
    preferred_bucket: str = "premium",
    fallback_bucket: str = "fast",
) -> dict:
    """Assemble a minimal routing-config dict with 3 models in 3 buckets.

    * ``local-mlx-test`` (local-premium) — vision_capable: False
    * ``api-vision`` (premium)           — vision_capable: True
    * ``api-text`` (fast)                — vision_capable: False
    """
    endpoints = []
    buckets: dict[str, list[str]] = {
        "local-premium": [],
        preferred_bucket: [],
        fallback_bucket: [],
    }
    if include_local:
        endpoints.append({
            "id": "local-mlx-test",
            "type": "local",
            "display_name": "Local MLX Test",
            "tier": "local-premium",
            "status": "active",
            "enabled": True,
            "vision_capable": False,
        })
        buckets["local-premium"].append("local-mlx-test")
    if include_api_vision:
        endpoints.append({
            "id": "api-vision",
            "type": "api",
            "display_name": "API Vision Model",
            "tier": preferred_bucket,
            "status": "active",
            "enabled": True,
            "vision_capable": True,
        })
        buckets[preferred_bucket].append("api-vision")
    if include_api_text:
        endpoints.append({
            "id": "api-text",
            "type": "api",
            "display_name": "API Text-Only Model",
            "tier": fallback_bucket,
            "status": "active",
            "enabled": True,
            "vision_capable": False,
        })
        buckets[fallback_bucket].append("api-text")
    return {
        "_schema_version": 2,
        "vision_extraction": {
            "enabled": True,
            "preferred_extractor_bucket": preferred_bucket,
            "fallback_extractor_bucket": fallback_bucket,
            "description": "test fixture",
        },
        "endpoints": endpoints,
        "buckets": buckets,
    }


class RouteForImageInputSelectionTests(unittest.TestCase):
    """Direct unit tests for ``boot.route_for_image_input``.

    After WP-4.3, selecting an extractor also TRIGGERS an extraction call.
    We patch ``visual_extraction.extract_spatial_from_image`` at the class
    level so no real model invocation happens in these routing tests —
    extraction-specific coverage lives in ``test_visual_extraction.py``.
    The selection behaviour (which endpoint is chosen, when fallback fires,
    when no_vision_available is set) is unchanged.
    """

    def setUp(self) -> None:
        # Import lazily so other modules don't load if one breaks.
        from boot import route_for_image_input  # noqa: WPS433
        self.gate = route_for_image_input

        # Patch the extractor call so tests stay model-free and fast. Any
        # test that wants to exercise the extraction path uses
        # ``self.fake_extract.return_value`` to customize.
        import visual_extraction  # noqa: WPS433
        self._extract_patcher = mock.patch.object(
            visual_extraction,
            "extract_spatial_from_image",
            return_value=visual_extraction.ExtractionResult(
                spatial_representation=None,
                confidence=0.0,
                raw_response="",
                parse_errors=[],
                extractor_model="mock-extractor",
            ),
        )
        self.fake_extract = self._extract_patcher.start()
        self.addCleanup(self._extract_patcher.stop)

    # ------------------------------------------------------------------
    # Case A: downstream = vision-capable, image present → direct pass.
    # ------------------------------------------------------------------
    def test_case_a_vision_capable_downstream_direct_pass(self) -> None:
        """When the requested model is vision_capable, no extractor is picked."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "api-vision", "vision_capable": True}
        rc = _mock_routing_config()
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # The same model flows through unchanged.
        self.assertIs(eff, downstream)
        # Same dict — mutation in place.
        self.assertIs(out_ctx, ctx)
        # Direct-pass flag is set; no extractor chosen.
        self.assertTrue(out_ctx.get("vision_direct_pass"))
        self.assertIsNone(out_ctx.get("vision_extractor_selected"))
        # No fallback signaling should fire.
        self.assertFalse(out_ctx.get("no_vision_available", False))

    # ------------------------------------------------------------------
    # Case B: downstream = text-only, image present → API vision selected.
    # ------------------------------------------------------------------
    def test_case_b_text_only_downstream_selects_preferred_extractor(self) -> None:
        """Text-only downstream + image → extractor from preferred bucket."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config()
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # Downstream is not swapped — extractor runs FIRST, then downstream.
        self.assertIs(eff, downstream)
        # Extractor was picked from the preferred bucket.
        sel = out_ctx.get("vision_extractor_selected")
        self.assertIsNotNone(sel, "extractor should have been selected")
        self.assertEqual(sel["id"], "api-vision")
        self.assertEqual(sel["bucket"], "premium")
        self.assertFalse(out_ctx.get("vision_direct_pass"))
        # WP-4.3 — extraction was attempted; our mock returns None.
        # The key is present so downstream code can tell extraction ran.
        self.assertIn("vision_extraction_result", out_ctx)
        self.assertIsNone(out_ctx["vision_extraction_result"])
        self.assertTrue(self.fake_extract.called,
                        "extractor call should have fired")
        self.assertFalse(out_ctx.get("no_vision_available", False))

    def test_case_b_fallback_bucket_when_preferred_is_empty(self) -> None:
        """Preferred has no vision model → fallback bucket is tried."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        # Zero the preferred bucket by omitting the vision API model from it.
        rc = _mock_routing_config()
        rc["buckets"]["premium"] = []  # wipe preferred
        # Put the vision model into the fallback bucket instead.
        rc["buckets"]["fast"].append("api-vision")
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        sel = out_ctx.get("vision_extractor_selected")
        self.assertIsNotNone(sel)
        self.assertEqual(sel["id"], "api-vision")
        self.assertEqual(sel["bucket"], "fast")

    # ------------------------------------------------------------------
    # Case C: no vision-capable model in any bucket → no_vision_available.
    # ------------------------------------------------------------------
    def test_case_c_no_vision_model_anywhere_sets_fallback_flag(self) -> None:
        """When neither bucket has a vision-capable endpoint, flag it."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        # Strip the vision-capable model entirely.
        rc = _mock_routing_config(include_api_vision=False)
        with self.assertLogs(level="INFO") if False else mock.patch("builtins.print") as mocked_print:
            eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # Downstream is unchanged — pipeline continues in text-only mode.
        self.assertIs(eff, downstream)
        self.assertTrue(out_ctx.get("no_vision_available"))
        self.assertIsNone(out_ctx.get("vision_extractor_selected"))
        self.assertFalse(out_ctx.get("vision_direct_pass"))
        # Warning was logged (via print, since boot.py uses print for ops logs).
        calls = [" ".join(str(a) for a in c.args) for c in mocked_print.call_args_list]
        joined = "\n".join(calls)
        self.assertIn("WARNING", joined)
        self.assertIn("no vision-capable", joined)

    # ------------------------------------------------------------------
    # Case D: no image present → strict no-op.
    # ------------------------------------------------------------------
    def test_case_d_no_image_is_strict_noop(self) -> None:
        """No image_path → nothing is added to context_pkg; model unchanged."""
        ctx = {"mode_name": "systems_dynamics", "gear": 3}
        before = dict(ctx)
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config()
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        self.assertIs(eff, downstream)
        # context_pkg left totally untouched — text-only path is unaffected.
        self.assertEqual(ctx, before)
        self.assertNotIn("vision_extractor_selected", ctx)
        self.assertNotIn("vision_direct_pass", ctx)
        self.assertNotIn("no_vision_available", ctx)

    # ------------------------------------------------------------------
    # Case E: missing vision_capable field defaults to False (defensive).
    # ------------------------------------------------------------------
    def test_case_e_missing_vision_capable_defaults_to_false(self) -> None:
        """A downstream model missing the field is treated as text-only."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        # Note: vision_capable absent (not even present as False).
        downstream = {"id": "mystery-model"}
        rc = _mock_routing_config()
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # Because default is False, extractor should be selected.
        sel = out_ctx.get("vision_extractor_selected")
        self.assertIsNotNone(sel, "missing vision_capable must default to False")
        self.assertEqual(sel["id"], "api-vision")
        self.assertFalse(out_ctx.get("vision_direct_pass"))

    def test_case_e_extractor_with_missing_field_is_not_picked(self) -> None:
        """An endpoint in the preferred bucket without vision_capable is skipped."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config(include_api_vision=False)
        # Add a new endpoint in premium with no vision_capable field at all.
        rc["endpoints"].append({
            "id": "mystery-premium",
            "type": "api",
            "status": "active",
            "enabled": True,
            # No vision_capable key present.
        })
        rc["buckets"]["premium"].append("mystery-premium")
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # Mystery model must NOT be picked — it has no vision_capable field.
        self.assertIsNone(out_ctx.get("vision_extractor_selected"))
        self.assertTrue(out_ctx.get("no_vision_available"))

    # ------------------------------------------------------------------
    # Extra coverage to bring assertion count comfortably past 15.
    # ------------------------------------------------------------------
    def test_disabled_bucket_filter_skips_disabled_endpoints(self) -> None:
        """``enabled: False`` endpoints must be skipped even if vision_capable."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config()
        # Disable the only vision-capable API model.
        for ep in rc["endpoints"]:
            if ep["id"] == "api-vision":
                ep["enabled"] = False
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # No picker should have selected the disabled endpoint.
        self.assertIsNone(out_ctx.get("vision_extractor_selected"))
        self.assertTrue(out_ctx.get("no_vision_available"))

    def test_inactive_status_endpoints_are_skipped(self) -> None:
        """``status != 'active'`` must be skipped."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config()
        for ep in rc["endpoints"]:
            if ep["id"] == "api-vision":
                ep["status"] = "inactive"
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        self.assertIsNone(out_ctx.get("vision_extractor_selected"))
        self.assertTrue(out_ctx.get("no_vision_available"))

    def test_vision_extraction_disabled_skips_gate(self) -> None:
        """``vision_extraction.enabled: false`` disables the gate entirely."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config()
        rc["vision_extraction"]["enabled"] = False
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # Gate was skipped: no extractor fields added.
        self.assertNotIn("vision_extractor_selected", out_ctx)
        self.assertNotIn("vision_direct_pass", out_ctx)
        self.assertNotIn("no_vision_available", out_ctx)

    def test_none_context_pkg_is_graceful(self) -> None:
        """Calling with ``context_pkg=None`` returns unchanged; no crash."""
        eff, out_ctx = self.gate(None, {"id": "x"}, routing_config=_mock_routing_config())
        self.assertIsNone(out_ctx)
        self.assertEqual(eff, {"id": "x"})

    def test_unresolved_downstream_still_selects_extractor(self) -> None:
        """When ``requested_model`` is None, text-only is assumed — extractor picked."""
        ctx = {"image_path": "/abs/img.png"}
        rc = _mock_routing_config()
        eff, out_ctx = self.gate(ctx, requested_model=None, routing_config=rc)
        # With no model to check, the gate treats it as text-only (safe default).
        sel = out_ctx.get("vision_extractor_selected")
        self.assertIsNotNone(sel)
        self.assertEqual(sel["id"], "api-vision")
        self.assertIsNone(eff)


class RouteForImageInputConfigLoadTests(unittest.TestCase):
    """When ``routing_config=None``, the gate loads from disk; assert it works."""

    def setUp(self) -> None:
        # Patch the extractor call so disk-config tests don't hit a real model.
        import visual_extraction  # noqa: WPS433
        self._extract_patcher = mock.patch.object(
            visual_extraction,
            "extract_spatial_from_image",
            return_value=visual_extraction.ExtractionResult(
                spatial_representation=None,
                confidence=0.0,
                raw_response="",
                parse_errors=[],
                extractor_model="mock-extractor",
            ),
        )
        self._extract_patcher.start()
        self.addCleanup(self._extract_patcher.stop)

    def test_loads_routing_config_from_disk(self) -> None:
        """Default behaviour: no routing_config arg → load from file."""
        from boot import route_for_image_input
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "local-mlx-kimi-dev-72b", "vision_capable": False}
        # The real routing-config.json sits at ~/ora/config/routing-config.json
        # and after our WP-4.2 edits it includes vision_extraction + per-endpoint
        # vision_capable flags. We expect an extractor to be selected.
        eff, out_ctx = route_for_image_input(ctx, downstream)
        self.assertIs(eff, downstream)
        sel = out_ctx.get("vision_extractor_selected")
        self.assertIsNotNone(sel, "real routing-config should yield an extractor")
        # The selected extractor must be a vision-capable endpoint.
        self.assertIn("id", sel)
        self.assertIn("bucket", sel)

    def test_load_failure_is_failopen(self) -> None:
        """If routing-config can't be loaded, the gate is a safe no-op."""
        from boot import route_for_image_input
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "x", "vision_capable": False}
        # Patch the open used by the gate to raise.
        with mock.patch("builtins.open", side_effect=OSError("nope")):
            eff, out_ctx = route_for_image_input(ctx, downstream)
        # Fail-open: no extractor fields added, pipeline continues.
        self.assertIs(eff, downstream)
        self.assertNotIn("vision_extractor_selected", out_ctx)
        self.assertNotIn("no_vision_available", out_ctx)


class RoutingConfigSchemaTests(unittest.TestCase):
    """The real routing-config.json carries the WP-4.2 vision_extraction block."""

    def test_vision_extraction_block_present(self) -> None:
        cfg_path = WORKSPACE / "config" / "routing-config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        self.assertIn("vision_extraction", cfg)
        ve = cfg["vision_extraction"]
        self.assertIn("enabled", ve)
        self.assertIn("preferred_extractor_bucket", ve)
        self.assertIn("fallback_extractor_bucket", ve)

    def test_all_endpoints_have_vision_capable_field(self) -> None:
        cfg_path = WORKSPACE / "config" / "routing-config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        missing = [ep.get("id", "?") for ep in cfg.get("endpoints", [])
                   if "vision_capable" not in ep]
        self.assertEqual(
            missing, [],
            f"endpoints missing vision_capable: {missing}",
        )

    def test_all_local_mlx_are_text_only(self) -> None:
        """Per WP-4.2 plan: local MLX models are never vision-capable."""
        cfg_path = WORKSPACE / "config" / "routing-config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        for ep in cfg.get("endpoints", []):
            if ep.get("type") == "local":
                self.assertFalse(
                    ep.get("vision_capable", False),
                    f"local endpoint {ep.get('id')} should be text-only",
                )


class ModelsJsonSchemaTests(unittest.TestCase):
    """Every model in models.json carries a ``vision_capable`` field."""

    def test_models_json_has_vision_capable_on_every_entry(self) -> None:
        models_path = WORKSPACE / "config" / "models.json"
        with open(models_path) as f:
            cfg = json.load(f)
        all_models = cfg.get("local_models", []) + cfg.get("commercial_models", [])
        self.assertTrue(len(all_models) > 0)
        missing = [m.get("id", "?") for m in all_models if "vision_capable" not in m]
        self.assertEqual(missing, [], f"models missing vision_capable: {missing}")

    def test_all_local_models_are_text_only(self) -> None:
        models_path = WORKSPACE / "config" / "models.json"
        with open(models_path) as f:
            cfg = json.load(f)
        for m in cfg.get("local_models", []):
            self.assertFalse(
                m.get("vision_capable", True),
                f"local model {m.get('id')} should be vision_capable: false",
            )

    def test_all_commercial_models_are_vision_capable_by_default(self) -> None:
        """Per spec: modern API/browser models default to True; explicit exceptions documented.

        Documented exception (WP-7.3.2): image-generation-only models
        (DALL-E 3, DALL-E 2, Stability SD3, Replicate image models) are
        ``image_capable: true`` but ``vision_capable: false`` — they
        emit images, they don't consume them. The vision-extraction
        routing path (`vision_capable`) is for models that can read an
        image and produce text, which is a different capability."""
        models_path = WORKSPACE / "config" / "models.json"
        with open(models_path) as f:
            cfg = json.load(f)
        for m in cfg.get("commercial_models", []):
            if m.get("image_capable") is True:
                # Image-generation models are documented exceptions per
                # WP-7.3.2's capability-slot taxonomy.
                continue
            self.assertTrue(
                m.get("vision_capable", False),
                f"commercial model {m.get('id')} should be vision_capable: true "
                "(documented default for modern API/browser transports)",
            )


class PipelineIntegrationTests(unittest.TestCase):
    """Ensure the routing gate doesn't break the server's multipart endpoint.

    Uses the same ``threading.Thread`` stub pattern as
    ``test_visual_merged_input.py`` — pipeline is mocked so no real model
    call happens; we only check that image_path flows through unchanged.
    """

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_multipart_with_image_still_reaches_pipeline(self) -> None:
        """After WP-4.2, /chat/multipart with an image should still stream normally."""
        captured = {}

        def fake_stream(clean_input, history, use_pipeline=True,
                        panel_id="main", images=None, extra_context=None, **kwargs):
            captured["extra_context"] = extra_context
            yield self.server._sse("pipeline_stage", stage="complete", gear=3)
            yield self.server._sse("response", text="ok")

        image_bytes = b"\x89PNG\r\n\x1a\nFAKE"
        data = {
            "message": "Describe the image.",
            "conversation_id": "wp42-integration",
            "image": (io.BytesIO(image_bytes), "photo.png"),
        }

        with mock.patch.object(self.server, "agentic_loop_stream",
                               side_effect=fake_stream), \
             mock.patch.object(self.server.threading, "Thread", _NoopThread):
            resp = self.client.post("/chat/multipart", data=data,
                                    content_type="multipart/form-data")
            b"".join(resp.response)

        self.assertEqual(resp.status_code, 200)
        # image_path is still on the extra_context that reaches the streamer.
        self.assertIn("image_path", captured["extra_context"])


if __name__ == "__main__":
    unittest.main()
