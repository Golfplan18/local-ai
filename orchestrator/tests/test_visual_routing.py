#!/usr/bin/env python3
"""
WP-4.2 — capability-conditional vision routing gate tests.

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m pytest ~/ora/orchestrator/tests -q

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


import runtime_paths  # noqa: E402
from oversight_sandbox import redirect_sessions_root  # noqa: E402


def setUpModule():
    # Keep this module's Dialogue writes out of the live sessions store, and
    # out of the previous run's. An envelope on disk is authoritative, so a
    # leftover one from an earlier run makes the endpoint ignore the history
    # this suite supplies — the module passes on a clean tree and fails on the
    # second run.
    redirect_sessions_root()

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

    Vision extraction is wired via the slot path (the legacy bucket-fallback
    fields were retired in install Chunk 12, 2026-05-19).
    ``slots.image_extracts.{interactive, agent}`` both point at ``api-vision``
    so route_for_image_input picks it regardless of execution_context. When
    ``include_api_vision`` is False the slot still references the id, but
    ``_endpoint_from_slot_entry`` returns None and route_for_image_input
    falls through to ``no_vision_available = True`` — preserving the prior
    no-vision-anywhere coverage.
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
            "slot": "image_extracts",
            "description": "test fixture",
        },
        "slots": {
            "image_extracts": {
                "interactive": "api-vision",
                "agent":       "api-vision",
            },
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
        """Text-only downstream + image → extractor from image_extracts slot."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config()
        eff, out_ctx = self.gate(ctx, downstream, routing_config=rc)
        # Downstream is not swapped — extractor runs FIRST, then downstream.
        self.assertIs(eff, downstream)
        # Extractor was picked from the configured slot. ``source`` carries
        # the origin tag ``slot:image_extracts:<execution_context>``.
        sel = out_ctx.get("vision_extractor_selected")
        self.assertIsNotNone(sel, "extractor should have been selected")
        self.assertEqual(sel["id"], "api-vision")
        self.assertEqual(sel["source"], "slot:image_extracts:interactive")
        self.assertFalse(out_ctx.get("vision_direct_pass"))
        # WP-4.3 — extraction was attempted; our mock returns None.
        # The key is present so downstream code can tell extraction ran.
        self.assertIn("vision_extraction_result", out_ctx)
        self.assertIsNone(out_ctx["vision_extraction_result"])
        self.assertTrue(self.fake_extract.called,
                        "extractor call should have fired")
        self.assertFalse(out_ctx.get("no_vision_available", False))

    # ------------------------------------------------------------------
    # Case C: no vision-capable model in the slot → no_vision_available.
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
        """A slot entry without vision_capable is skipped."""
        ctx = {"image_path": "/abs/path/to/image.png"}
        downstream = {"id": "local-mlx-test", "vision_capable": False}
        rc = _mock_routing_config(include_api_vision=False)
        # Add a new endpoint with no vision_capable field at all, and wire
        # the slot to it. ``_endpoint_from_slot_entry`` should refuse to
        # treat a missing field as truthy.
        rc["endpoints"].append({
            "id": "mystery-premium",
            "type": "api",
            "status": "active",
            "enabled": True,
            # No vision_capable key present.
        })
        rc["buckets"]["premium"].append("mystery-premium")
        rc["slots"]["image_extracts"] = {
            "interactive": "mystery-premium",
            "agent":       "mystery-premium",
        }
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
        # ``source`` carries the origin — slot-resolved when the live
        # routing-config.json has vision_extraction.slot set (preferred),
        # bucket-resolved otherwise.
        self.assertIn("id", sel)
        self.assertIn("source", sel)
        self.assertTrue(sel["source"].startswith("slot:"))

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
        # Slot path is canonical after install Chunk 12 (2026-05-19).
        self.assertIn("slot", ve)
        # Legacy bucket-fallback fields are retired.
        self.assertNotIn("preferred_extractor_bucket", ve)
        self.assertNotIn("fallback_extractor_bucket", ve)

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

    def test_local_endpoints_declare_vision_capable_explicitly(self) -> None:
        """Local endpoints state their vision support as a real boolean.

        WP-4.2 assumed local MLX models were never vision-capable and this test
        asserted it. The 2026-05-26 model swap replaced the local lineup with a
        vision-capable one across three training families (see CLAUDE.md), so
        every local endpoint in routing-config.json now declares
        ``vision_capable: true`` and the old assertion was asserting a policy
        the system had deliberately dropped.

        What still matters is that the flag is declared and typed: routing
        treats a missing field as False (test_case_e_*), so a local model that
        CAN see images but forgets the field is silently demoted to extraction.
        """
        cfg_path = WORKSPACE / "config" / "routing-config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        local = [ep for ep in cfg.get("endpoints", [])
                 if ep.get("type") == "local"]
        self.assertTrue(local, "routing-config declares no local endpoints")
        for ep in local:
            self.assertIsInstance(
                ep.get("vision_capable"), bool,
                f"local endpoint {ep.get('id')} must declare vision_capable "
                "as a boolean",
            )


class ModelsJsonSchemaTests(unittest.TestCase):
    """Every model in models.json carries a ``vision_capable`` field."""

    def test_models_json_has_vision_capable_on_every_entry(self) -> None:
        models_path = runtime_paths.models_json_path()
        with open(models_path) as f:
            cfg = json.load(f)
        all_models = cfg.get("local_models", []) + cfg.get("commercial_models", [])
        self.assertTrue(len(all_models) > 0)
        missing = [m.get("id", "?") for m in all_models if "vision_capable" not in m]
        self.assertEqual(missing, [], f"models missing vision_capable: {missing}")

    def test_local_models_declare_valid_vision_capable(self) -> None:
        """Local models must declare ``vision_capable`` as a boolean.

        Historical note: an earlier revision of this test asserted every
        local model was ``vision_capable: false`` (the lineup was text-only
        at the time). The 2026-05-26 model swap moved the local lineup to a
        vision-capable family (Qwen / GLM / Mistral vision variants — see
        CLAUDE.md), so ``vision_capable: true`` is now correct and expected.
        ``config/models.json`` is gitignored and machine-specific (each Mac /
        server / fork curates its own), so this checks the schema invariant
        — a valid boolean flag the routing gate can read — rather than a
        fixed value that would be brittle across machines.
        """
        models_path = runtime_paths.models_json_path()
        if not models_path.exists():
            self.skipTest("models.json not present")
        with open(models_path) as f:
            cfg = json.load(f)
        for m in cfg.get("local_models", []):
            self.assertIsInstance(
                m.get("vision_capable"),
                bool,
                f"local model {m.get('id')} must declare vision_capable "
                "as a boolean",
            )

    def test_all_commercial_models_are_vision_capable_by_default(self) -> None:
        """Per spec: modern API/browser models default to True; explicit exceptions documented.

        Documented exception (WP-7.3.2): image-generation-only models
        (DALL-E 3, DALL-E 2, Stability SD3, Replicate image models) are
        ``image_capable: true`` but ``vision_capable: false`` — they
        emit images, they don't consume them. The vision-extraction
        routing path (`vision_capable`) is for models that can read an
        image and produce text, which is a different capability."""
        models_path = runtime_paths.models_json_path()
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
        from server import app as server  # noqa: WPS433
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


# ---------------------------------------------------------------------------
# Slot-based vision-extraction selection (WP-7.x / web-RAG follow-up).
# Image-generation models accept image input by construction, so we can
# reuse the chain in slots.image_generates as the extractor source rather
# than carving out a dedicated bucket that has to be kept in sync.
# ---------------------------------------------------------------------------


class EndpointFromSlotEntry(unittest.TestCase):
    """Unit tests for the slot-entry → endpoint-dict resolver."""

    def setUp(self):
        from boot import _endpoint_from_slot_entry
        self.resolve = _endpoint_from_slot_entry
        self.rc = {
            "endpoints": [
                {"id": "api-vision", "type": "api", "service": "openai",
                 "vision_capable": True, "enabled": True, "status": "active"},
                {"id": "local-text-only", "type": "local",
                 "vision_capable": False, "enabled": True, "status": "active"},
                {"id": "api-disabled", "type": "api", "service": "openai",
                 "vision_capable": True, "enabled": False, "status": "active"},
            ],
        }

    def test_openrouter_prefix_synthesizes_endpoint(self):
        ep = self.resolve("openrouter:openai/gpt-5.4-image-2", self.rc)
        self.assertIsNotNone(ep)
        self.assertEqual(ep["service"], "openrouter")
        self.assertEqual(ep["model"], "openai/gpt-5.4-image-2")
        self.assertTrue(ep["vision_capable"])

    def test_openrouter_prefix_empty_model_returns_none(self):
        ep = self.resolve("openrouter:", self.rc)
        self.assertIsNone(ep)

    def test_plain_endpoint_id_resolved_when_vision_capable(self):
        ep = self.resolve("api-vision", self.rc)
        self.assertIsNotNone(ep)
        self.assertEqual(ep["id"], "api-vision")

    def test_plain_endpoint_id_skipped_when_text_only(self):
        ep = self.resolve("local-text-only", self.rc)
        self.assertIsNone(ep)

    def test_plain_endpoint_id_skipped_when_disabled(self):
        ep = self.resolve("api-disabled", self.rc)
        self.assertIsNone(ep)

    def test_text_to_image_generators_skipped(self):
        # Pure text-to-image services aren't vision-input-capable, so they
        # must never resolve as a vision extractor — even though they
        # legitimately appear in image_generates fallback chains.
        for entry in ("local-diffusers", "stability", "replicate"):
            self.assertIsNone(self.resolve(entry, self.rc),
                              f"{entry} should NOT resolve as extractor")

    def test_unknown_entry_returns_none(self):
        ep = self.resolve("unknown:something", self.rc)
        self.assertIsNone(ep)


class PickVisionExtractorFromSlot(unittest.TestCase):
    """Walks the preferred + fallback chain for a slot and returns the
    first vision-input-capable entry."""

    def setUp(self):
        from boot import _pick_vision_extractor_from_slot
        self.pick = _pick_vision_extractor_from_slot
        self.rc = {
            "slots": {
                "image_generates": {
                    "preferred": "openrouter:openai/gpt-5.4-image-2",
                    "fallback": [
                        "openrouter:google/gemini-3-pro-image-preview",
                        "local-diffusers",
                    ],
                },
                "image_edits": {
                    "preferred": "local-diffusers",
                    "fallback": ["replicate"],
                },
                "image_to_prompt": {
                    "preferred": "replicate",
                    "fallback": [],
                },
            },
            "endpoints": [],
        }

    def test_preferred_openrouter_entry_wins(self):
        ep, walked = self.pick(self.rc, "image_generates")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "openai/gpt-5.4-image-2")
        # Only the preferred was inspected.
        self.assertEqual(walked, ["openrouter:openai/gpt-5.4-image-2"])

    def test_falls_through_local_diffusers_to_next_openrouter(self):
        # Make preferred unresolvable to force fallback walk.
        self.rc["slots"]["image_generates"]["preferred"] = "local-diffusers"
        ep, walked = self.pick(self.rc, "image_generates")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "google/gemini-3-pro-image-preview")
        self.assertEqual(
            walked,
            ["local-diffusers", "openrouter:google/gemini-3-pro-image-preview"],
        )

    def test_slot_with_only_text_to_image_generators_returns_none(self):
        # image_edits has only local-diffusers + replicate → no extractor.
        ep, walked = self.pick(self.rc, "image_edits")
        self.assertIsNone(ep)
        self.assertEqual(walked, ["local-diffusers", "replicate"])

    def test_unknown_slot_returns_none(self):
        ep, walked = self.pick(self.rc, "ghost_slot")
        self.assertIsNone(ep)
        self.assertEqual(walked, [])


class SlotBasedVisionExtractionEndToEnd(unittest.TestCase):
    """End-to-end: route_for_image_input prefers slot resolution when the
    routing-config carries vision_extraction.slot."""

    def setUp(self):
        from boot import route_for_image_input
        self.gate = route_for_image_input
        # Mock the extractor so the integration doesn't actually fire a
        # network call.
        self._extract_patcher = mock.patch(
            "boot.extract_spatial_from_image",
            create=True,
            return_value=mock.Mock(
                spatial_representation=None,
                extractor_model="mock",
                confidence=0.0,
                parse_errors=[],
            ),
        )
        # The import-from-inside-route_for_image_input pattern means we
        # have to patch the module the gate imports from.
        self._extract_patcher = mock.patch(
            "visual_extraction.extract_spatial_from_image",
            return_value=mock.Mock(
                spatial_representation=None,
                extractor_model="mock",
                confidence=0.0,
                parse_errors=[],
            ),
        )
        self._extract_patcher.start()
        self.addCleanup(self._extract_patcher.stop)

    def _rc(self, *, slot_set: bool, image_gen_preferred: str | None) -> dict:
        slots = {}
        if image_gen_preferred:
            slots["image_generates"] = {
                "preferred": image_gen_preferred,
                "fallback": ["local-diffusers"],
            }
        return {
            "vision_extraction": {
                "enabled": True,
                **({"slot": "image_generates"} if slot_set else {}),
            },
            "buckets": {
                "premium": ["bucket-fallback-ep"],
                "fast":    [],
            },
            "slots": slots,
            "endpoints": [
                {"id": "bucket-fallback-ep", "type": "api", "service": "openai",
                 "vision_capable": True, "enabled": True, "status": "active",
                 "display_name": "Bucket Fallback"},
            ],
        }

    def test_slot_resolution_wins_when_configured(self):
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "text-only", "vision_capable": False}
        rc = self._rc(slot_set=True,
                       image_gen_preferred="openrouter:openai/gpt-5.4-image-2")
        eff, out = self.gate(ctx, downstream, routing_config=rc)
        sel = out["vision_extractor_selected"]
        self.assertEqual(sel["source"], "slot:image_generates")
        self.assertEqual(sel["id"], "openrouter:openai/gpt-5.4-image-2")

    def test_slot_unresolvable_sets_no_vision_available(self):
        # image_generates chain is entirely text-to-image generators →
        # slot path can't produce an extractor. The legacy bucket-fallback
        # was retired in install Chunk 12 (2026-05-19); the gate now sets
        # no_vision_available=True instead.
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "text-only", "vision_capable": False}
        rc = self._rc(slot_set=True, image_gen_preferred="local-diffusers")
        eff, out = self.gate(ctx, downstream, routing_config=rc)
        self.assertIsNone(out.get("vision_extractor_selected"))
        self.assertTrue(out.get("no_vision_available"))

    def test_no_slot_configured_sets_no_vision_available(self):
        # When vision_extraction.slot is absent there is nothing to walk.
        # Post-Chunk-12 the gate sets no_vision_available=True rather than
        # falling back to a bucket walk (which no longer exists).
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "text-only", "vision_capable": False}
        rc = self._rc(slot_set=False, image_gen_preferred=None)
        eff, out = self.gate(ctx, downstream, routing_config=rc)
        self.assertIsNone(out.get("vision_extractor_selected"))
        self.assertTrue(out.get("no_vision_available"))


class PickVisionExtractorFromImageExtractsSlot(unittest.TestCase):
    """Per-pipeline schema: slots.image_extracts.{interactive, agent}.

    Each pipeline picks one model; the OPPOSITE pipeline's pick is the
    cross-pipeline backup. Two-deep, no fallback list.
    """

    def setUp(self):
        from boot import _pick_vision_extractor_from_image_extracts
        self.pick = _pick_vision_extractor_from_image_extracts
        self.rc = {
            "slots": {
                "image_extracts": {
                    "interactive": "openrouter:openai/gpt-5",
                    "agent":       "openrouter:anthropic/claude-opus-4-7",
                },
            },
            "endpoints": [],
        }

    def test_interactive_pipeline_picks_interactive_entry(self):
        ep, walked = self.pick(self.rc, "interactive")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "openai/gpt-5")
        # Only the primary was inspected — the backup wasn't needed.
        self.assertEqual(walked, ["openrouter:openai/gpt-5"])

    def test_agent_pipeline_picks_agent_entry(self):
        ep, walked = self.pick(self.rc, "agent")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "anthropic/claude-opus-4-7")
        self.assertEqual(walked, ["openrouter:anthropic/claude-opus-4-7"])

    def test_interactive_falls_back_to_agent_when_primary_missing(self):
        self.rc["slots"]["image_extracts"]["interactive"] = ""
        ep, walked = self.pick(self.rc, "interactive")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "anthropic/claude-opus-4-7")
        # Only the backup was inspected (primary was empty so it wasn't added).
        self.assertEqual(walked, ["openrouter:anthropic/claude-opus-4-7"])

    def test_agent_falls_back_to_interactive_when_primary_unresolvable(self):
        # Agent's primary is a text-to-image generator (not vision-input
        # capable). Cross-pipeline backup fires to interactive's entry.
        self.rc["slots"]["image_extracts"]["agent"] = "local-diffusers"
        ep, walked = self.pick(self.rc, "agent")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "openai/gpt-5")
        self.assertEqual(walked, ["local-diffusers", "openrouter:openai/gpt-5"])

    def test_both_unresolvable_returns_none(self):
        self.rc["slots"]["image_extracts"] = {
            "interactive": "local-diffusers",
            "agent":       "replicate",
        }
        ep, walked = self.pick(self.rc, "interactive")
        self.assertIsNone(ep)
        self.assertEqual(walked, ["local-diffusers", "replicate"])

    def test_unknown_execution_context_normalizes_to_agent(self):
        # "autonomous" / any non-"interactive" string lands on agent — matches
        # the convention in resolve_gear4_endpoints.
        ep, walked = self.pick(self.rc, "autonomous")
        self.assertIsNotNone(ep)
        self.assertEqual(ep["model"], "anthropic/claude-opus-4-7")

    def test_identical_primary_and_backup_dedup(self):
        # When both pipelines point at the same model, the chain is one-deep
        # (no duplicate inspection).
        self.rc["slots"]["image_extracts"]["agent"] = (
            self.rc["slots"]["image_extracts"]["interactive"]
        )
        ep, walked = self.pick(self.rc, "interactive")
        self.assertIsNotNone(ep)
        self.assertEqual(walked, ["openrouter:openai/gpt-5"])


class RouteForImageInputThreadsExecutionContext(unittest.TestCase):
    """End-to-end: route_for_image_input dispatches the image_extracts slot
    through the per-pipeline path and threads execution_context correctly."""

    def setUp(self):
        from boot import route_for_image_input
        self.gate = route_for_image_input
        self._extract_patcher = mock.patch(
            "visual_extraction.extract_spatial_from_image",
            return_value=mock.Mock(
                spatial_representation=None,
                extractor_model="mock",
                confidence=0.0,
                parse_errors=[],
            ),
        )
        self._extract_patcher.start()
        self.addCleanup(self._extract_patcher.stop)

    def _rc(self):
        return {
            "vision_extraction": {
                "enabled": True,
                "slot": "image_extracts",
            },
            "slots": {
                "image_extracts": {
                    "interactive": "openrouter:openai/gpt-5",
                    "agent":       "openrouter:anthropic/claude-opus-4-7",
                },
            },
            "buckets": {"premium": [], "fast": []},
            "endpoints": [],
        }

    def test_interactive_context_picks_interactive_slot(self):
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "text-only", "vision_capable": False}
        eff, out = self.gate(ctx, downstream, routing_config=self._rc(),
                              execution_context="interactive")
        sel = out["vision_extractor_selected"]
        self.assertEqual(sel["source"], "slot:image_extracts:interactive")
        self.assertEqual(sel["id"], "openrouter:openai/gpt-5")

    def test_agent_context_picks_agent_slot(self):
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "text-only", "vision_capable": False}
        eff, out = self.gate(ctx, downstream, routing_config=self._rc(),
                              execution_context="agent")
        sel = out["vision_extractor_selected"]
        self.assertEqual(sel["source"], "slot:image_extracts:agent")
        self.assertEqual(sel["id"], "openrouter:anthropic/claude-opus-4-7")

    def test_agent_primary_unresolvable_uses_cross_pipeline_backup(self):
        rc = self._rc()
        rc["slots"]["image_extracts"]["agent"] = "local-diffusers"
        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "text-only", "vision_capable": False}
        eff, out = self.gate(ctx, downstream, routing_config=rc,
                              execution_context="agent")
        sel = out["vision_extractor_selected"]
        # Crossed over to interactive's pick.
        self.assertEqual(sel["source"], "slot:image_extracts:agent")
        self.assertEqual(sel["id"], "openrouter:openai/gpt-5")


class ModeToVisualIntegrityTests(unittest.TestCase):
    """Regression: nothing validated mode-to-visual.json against reality.

    Two silent-drift classes had accumulated. A key naming a mode file that no
    longer exists routes nothing — `red-team` sat where neither
    red-team-assessment nor red-team-advocate would ever look, leaving both
    unconfigured, and `systems-dynamics` outlived its split into the causal and
    structural modes that already have their own entries. A `visual_types`
    string outside the recognized set is dropped without an error, a warning or
    a log line — `custom_annotated_svg` had been inert on spatial-reasoning.

    Both classes fail silently at runtime, so they only surface as "why does
    this mode never draw anything". These assertions make them loud.
    """

    CONFIG = WORKSPACE / "config" / "mode-to-visual.json"
    MODES_DIR = WORKSPACE / "modes"

    def _modes(self) -> dict:
        with open(self.CONFIG, encoding="utf-8") as fh:
            return json.load(fh)["modes"]

    def test_every_configured_key_names_a_real_mode_file(self):
        available = {p.stem for p in self.MODES_DIR.glob("*.md")}
        orphans = sorted(set(self._modes()) - available)
        self.assertEqual(
            [], orphans,
            f"mode-to-visual.json configures modes with no mode file: {orphans}. "
            "Such an entry routes nothing and hides that its real successors "
            "are unconfigured.")

    def test_every_declared_visual_type_is_recognized(self):
        import boot
        offenders = {
            mode: [t for t in cfg.get("visual_types", [])
                   if t not in boot._KNOWN_VISUAL_TYPES]
            for mode, cfg in self._modes().items()
        }
        offenders = {m: t for m, t in offenders.items() if t}
        self.assertEqual(
            {}, offenders,
            f"unrecognized visual_types are dropped silently: {offenders}")

    def test_both_red_team_successors_are_configured(self):
        modes = self._modes()
        for name in ("red-team-assessment", "red-team-advocate"):
            with self.subTest(mode=name):
                self.assertIn(name, modes)

    def test_retired_split_parents_are_gone(self):
        modes = self._modes()
        for retired in ("red-team", "systems-dynamics"):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, modes)


class VisualTypePreflightAcceptSetTests(unittest.TestCase):
    """Regression: a mode's declared visual types are an ACCEPT-SET.

    ``_append_visual_type_preflight`` used to compare the emitted type against
    ``visual_types[0]`` alone and append a note ordering the next revision to
    replace it. Thirteen of the twenty-seven configured modes declare more than
    one type, so a correctly-chosen sibling — a sequence diagram in
    process-mapping, a time-series in information-density — was reported as a
    defect and revised away in favour of the first-listed type. The note is
    injected into gear 4's cross-evaluation output, which the revisers read.
    """

    import boot  # noqa: E402  (module-scoped import keeps the class self-contained)

    def _draft(self, vtype: str) -> str:
        return (
            "Prose.\n\n```ora-visual\n"
            + json.dumps({"id": "fig-1", "type": vtype})
            + "\n```\n"
        )

    def _preflight(self, vtype: str, mode: str, ctx=None) -> str:
        return self.boot._append_visual_type_preflight(
            self._draft(vtype), ctx or {}, mode, "step4-eval")

    def test_sibling_type_is_accepted_not_corrected(self):
        """process-mapping declares flowchart / sequence / state."""
        for vtype in ("flowchart", "sequence", "state"):
            with self.subTest(vtype=vtype):
                out = self._preflight(vtype, "process-mapping")
                self.assertNotIn("visual preflight", out)

    def test_every_declared_type_of_a_multi_type_mode_is_accepted(self):
        out = self._preflight("heatmap", "information-density")
        self.assertNotIn("visual preflight", out)

    def test_type_outside_the_accept_set_is_still_flagged(self):
        out = self._preflight("bow_tie", "process-mapping")
        self.assertIn("visual preflight", out)
        self.assertIn("bow_tie", out)
        # The note names what the mode does produce, rather than only its first.
        self.assertIn("flowchart", out)
        self.assertIn("sequence", out)

    def test_explicitly_requested_kind_still_forces_that_kind(self):
        """A named request is the one case where a sibling IS wrong."""
        out = self._preflight("sequence", "process-mapping",
                              ctx={"visual_kind": "flowchart"})
        self.assertIn("visual preflight", out)
        self.assertIn("requested visual type", out)

    def test_explicitly_requested_kind_matching_emission_is_silent(self):
        out = self._preflight("flowchart", "process-mapping",
                              ctx={"visual_kind": "flowchart"})
        self.assertNotIn("visual preflight", out)

    def test_underscore_and_hyphen_spellings_are_the_same_type(self):
        out = self._preflight("causal-loop-diagram", "root-cause-analysis")
        self.assertNotIn("visual preflight", out)

    def test_unconfigured_mode_flags_nothing(self):
        """No declared types means no expectation to violate."""
        out = self._preflight("fishbone", "stakeholder-mapping")
        self.assertNotIn("visual preflight", out)

    def test_draft_without_an_envelope_is_untouched(self):
        text = "Just prose, no envelope."
        self.assertEqual(
            text,
            self.boot._append_visual_type_preflight(text, {}, "process-mapping",
                                                    "step4-eval"))

    def test_accept_set_helper_reports_explicitness(self):
        accepted, explicit = self.boot._visual_accepted_kinds({}, "process-mapping")
        self.assertFalse(explicit)
        self.assertIn("sequence", accepted)
        accepted, explicit = self.boot._visual_accepted_kinds(
            {"visual_kind": "tornado"}, "process-mapping")
        self.assertTrue(explicit)
        self.assertEqual(["tornado"], accepted)


if __name__ == "__main__":
    unittest.main()
