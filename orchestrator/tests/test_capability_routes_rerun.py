#!/usr/bin/env python3
"""Smoke tests for the three re-run capability routes.

WP-7.3.3f / 7.3.3g / 7.3.3i — three sibling sub-WPs hit the org limit
before their server routes landed; the JS modules were complete but the
endpoints they call were missing. These tests exercise the routes via
Flask's test_client to verify happy-path + bad-input handling without
requiring a Replicate token.

Routes covered:
* ``POST /api/capability/image_varies``      — Contracts §3.6 (sync, list)
* ``POST /api/capability/image_to_prompt``   — Contracts §3.7 (sync, text)
* ``POST /api/capability/video_generates``   — Contracts §3.9 (async, job)
* ``POST /api/capability/image_edits``       — Contracts §3.2 (sync, bytes);
  required-input handling only, added when the route stopped backfilling a
  prompt the caller never wrote.

Run::

    /opt/homebrew/bin/python3 -m pytest \
        orchestrator/tests/test_capability_routes_rerun.py -q

Provider calls are patched with deterministic test fixtures; production
routes are never asked to fulfill a request through a mock switch.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))


def _tiny_png_data_url() -> str:
    """Return a minimal 4×4 PNG as a data URL.

    Used by patched provider fixtures to verify image bytes flow through.
    We build it via PIL so the route can decode it without erroring.
    """
    from PIL import Image
    img = Image.new("RGBA", (4, 4), (128, 128, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _tiny_png_bytes() -> bytes:
    return base64.b64decode(_tiny_png_data_url().split(",", 1)[1])


def _fake_registry(slot: str, provider_id: str, output):
    """Return a deterministic registry double and its captured calls."""
    from capability_registry import InvocationResult

    calls = []
    registry = mock.Mock()

    def invoke(invoked_slot, inputs, provider_id=None, **kwargs):
        calls.append({
            "slot": invoked_slot,
            "inputs": dict(inputs),
            "provider_id": provider_id,
            "kwargs": kwargs,
        })
        result_output = output(dict(inputs)) if callable(output) else output
        return InvocationResult(
            slot=invoked_slot,
            provider_id=provider_id or provider_id_for_result,
            output=result_output,
            execution_pattern="async" if slot == "video_generates" else "sync",
            inputs_used=dict(inputs),
            attempts=[{
                "provider_id": provider_id or provider_id_for_result,
                "succeeded": True,
                "error_code": None,
                "error_message": None,
            }],
        )

    provider_id_for_result = provider_id
    registry.invoke.side_effect = invoke
    return registry, calls


class CapabilityMockBoundaryTests(unittest.TestCase):
    """Production routes reject the old deterministic fixture switch."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_mock_flag_is_rejected_by_every_affected_route(self) -> None:
        cases = [
            (
                "/api/capability/image_edits",
                {
                    "prompt": "make it blue",
                    "image_data_url": _tiny_png_data_url(),
                    "mask_data_url": _tiny_png_data_url(),
                    "mock": True,
                },
            ),
            (
                "/api/capability/image_outpaints",
                {
                    "prompt": "extend to the right",
                    "image_data_url": _tiny_png_data_url(),
                    "directions": ["right"],
                    "mock": True,
                },
            ),
            (
                "/api/capability/image_upscales",
                {
                    "image_data_url": _tiny_png_data_url(),
                    "scale_factor": 2,
                    "mock": True,
                },
            ),
            (
                "/api/capability/image_styles",
                {
                    "source_image_data_url": _tiny_png_data_url(),
                    "style_reference_data_url": _tiny_png_data_url(),
                    "mock": True,
                },
            ),
            (
                "/api/capability/image_critique",
                {
                    "image_data_url": _tiny_png_data_url(),
                    "rubric": "composition",
                    "mock": True,
                },
            ),
            (
                "/api/capability/image_varies",
                {
                    "slot": "image_varies",
                    "inputs": {"source_image": "obj_42", "mock": True},
                },
            ),
            (
                "/api/capability/image_to_prompt",
                {
                    "slot": "image_to_prompt",
                    "inputs": {"image": "obj_99", "mock": True},
                },
            ),
        ]

        for route, body in cases:
            with self.subTest(route=route):
                with mock.patch.object(
                    self.server,
                    "_load_image_capability_registry",
                    side_effect=AssertionError("mock request reached provider setup"),
                ) as load_registry:
                    resp = self.client.post(
                        route,
                        data=json.dumps(body),
                        content_type="application/json",
                    )
                self.assertFalse(200 <= resp.status_code < 300)
                payload = json.loads(resp.data)
                self.assertEqual(payload["error"]["code"], "mock_not_allowed")
                self.assertIsInstance(payload["error"]["attempts"], list)
                load_registry.assert_not_called()


class CapabilityImageStylesRouteTests(unittest.TestCase):
    """Regression coverage for /api/capability/image_styles."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_decoded_source_and_style_bytes_reach_provider(self) -> None:
        registry, calls = _fake_registry(
            "image_styles",
            "local-diffusers",
            _tiny_png_bytes(),
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_styles",
                data=json.dumps({
                    "source_image_data_url": _tiny_png_data_url(),
                    "style_reference_data_url": _tiny_png_data_url(),
                    "strength": 0.6,
                }),
                content_type="application/json",
            )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls[0]["inputs"]["source_image"], _tiny_png_bytes())
        self.assertEqual(calls[0]["inputs"]["style_reference"], _tiny_png_bytes())
        self.assertEqual(calls[0]["inputs"]["strength"], 0.6)


class CapabilityImageVariesRouteTests(unittest.TestCase):
    """Smoke tests for /api/capability/image_varies (Contracts §3.6)."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_source_bytes_flow_and_unresolved_id_returns_400(self) -> None:
        """Provider receives bytes; a canvas id alone is rejected truthfully."""
        body = {
            "slot": "image_varies",
            "inputs": {
                "source_image": "obj_42",
                "count": 4,
                "variation_strength": 0.5,
                "source_image_data_url": _tiny_png_data_url(),
            },
        }
        registry, calls = _fake_registry(
            "image_varies",
            "local-diffusers",
            lambda inputs: [
                {"image_data_uri": _tiny_png_data_url()}
                for _ in range(inputs["count"])
            ],
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_varies",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertNotIn("mocked", payload)
        self.assertEqual(payload.get("provider"), "local-diffusers")
        self.assertEqual(calls[0]["inputs"]["source_image"], _tiny_png_bytes())
        self.assertIsInstance(payload.get("images"), list)
        self.assertEqual(len(payload["images"]), 4)
        for entry in payload["images"]:
            self.assertIsInstance(entry, dict)
            self.assertIn("data", entry)
            self.assertIsInstance(entry["data"], str)
            self.assertTrue(len(entry["data"]) > 50, "expected non-empty base64")
            # Ensure it's actually decodable.
            base64.b64decode(entry["data"])

        unresolved = self.client.post(
            "/api/capability/image_varies",
            data=json.dumps({
                "slot": "image_varies",
                "inputs": {"source_image": "obj_42", "count": 2},
            }),
            content_type="application/json",
        )
        self.assertEqual(unresolved.status_code, 400)
        error = json.loads(unresolved.data)["error"]
        self.assertEqual(error["code"], "source_ambiguous")
        self.assertIn("source_image_data_url", error["message"])
        self.assertEqual(len(calls), 1)

    def test_count_clamps_to_bounds(self) -> None:
        """Count outside [1,8] is silently clamped."""
        body = {
            "slot": "image_varies",
            "inputs": {
                "source_image": "obj_42",
                "count": 99,
                "source_image_data_url": _tiny_png_data_url(),
            },
        }
        registry, calls = _fake_registry(
            "image_varies",
            "alternate-image-provider",
            lambda inputs: [
                {"image_data_uri": _tiny_png_data_url()}
                for _ in range(inputs["count"])
            ],
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_varies",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertLessEqual(len(payload["images"]), 8)
        self.assertEqual(calls[0]["inputs"]["count"], 8)

    def test_missing_source_image_returns_400(self) -> None:
        """Bad input: empty source_image surfaces source_ambiguous."""
        body = {"slot": "image_varies", "inputs": {}}
        resp = self.client.post(
            "/api/capability/image_varies",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "source_ambiguous")

    def test_no_provider_error_includes_attempts(self) -> None:
        """Fallback exhaustion stays visible in the typed error response."""
        from capability_registry import CapabilityError

        attempts = [
            {
                "provider_id": "preferred-image-provider",
                "succeeded": False,
                "error_code": "model_unavailable",
                "error_message": "preferred unavailable",
            },
            {
                "provider_id": "alternate-image-provider",
                "succeeded": False,
                "error_code": "model_unavailable",
                "error_message": "alternate unavailable",
            },
        ]
        registry = mock.Mock()
        registry.invoke.side_effect = CapabilityError(
            "model_unavailable",
            "No provider returned usable variations.",
            attempts=attempts,
        )
        body = {
            "slot": "image_varies",
            "inputs": {
                "source_image": "obj_42",
                "source_image_data_url": _tiny_png_data_url(),
            },
        }
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_varies",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 502)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "model_unavailable")
        self.assertEqual(payload["error"]["attempts"], attempts)

    def test_registry_error_status_mapping(self) -> None:
        """Contract/input errors are 400; provider errors remain 502."""
        from capability_registry import CapabilityError

        input_codes = {
            "prompt_rejected", "no_mask_drawn", "no_image_selected",
            "mask_invalid", "no_specific_guidance", "missing_required_input",
            "references_incompatible", "direction_invalid", "image_too_small",
            "image_too_large", "source_ambiguous", "image_unreadable",
        }
        provider_codes = {"model_unavailable", "quota_exceeded", "provider_failed"}
        registry = mock.Mock()

        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            for code in input_codes | provider_codes:
                with self.subTest(code=code):
                    registry.invoke.side_effect = CapabilityError(code, code)
                    resp = self.client.post(
                        "/api/capability/image_varies",
                        data=json.dumps({
                            "slot": "image_varies",
                            "inputs": {
                                "source_image": "obj_42",
                                "source_image_data_url": _tiny_png_data_url(),
                            },
                        }),
                        content_type="application/json",
                    )
                    expected = 400 if code in input_codes else 502
                    self.assertEqual(resp.status_code, expected)
                    payload = json.loads(resp.data)
                    self.assertEqual(payload["error"]["code"], code)


class CapabilityImageToPromptRouteTests(unittest.TestCase):
    """Smoke tests for /api/capability/image_to_prompt (Contracts §3.7)."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_patched_provider_returns_plain_caption(self) -> None:
        """Default target_style 'dalle' returns a provider-shaped caption."""
        body = {
            "slot": "image_to_prompt",
            "inputs": {"image": "obj_99"},
        }
        registry, _calls = _fake_registry(
            "image_to_prompt",
            "alternate-caption-provider",
            "a photograph of a landscape with rolling hills under a clear sky",
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_to_prompt",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertNotIn("mocked", payload)
        self.assertEqual(payload.get("provider"), "alternate-caption-provider")
        self.assertEqual(payload.get("target_style"), "dalle")
        self.assertIsInstance(payload.get("prompt"), str)
        self.assertGreater(len(payload["prompt"]), 10)
        # DALL-E flavor is intentionally plain — no Midjourney flags.
        self.assertNotIn("--ar", payload["prompt"])

    def test_target_style_mj_appends_flags(self) -> None:
        """Midjourney target appends --ar / --v / --style flags."""
        body = {
            "slot": "image_to_prompt",
            "inputs": {"image": "obj_99", "target_style": "mj"},
        }
        registry, _calls = _fake_registry(
            "image_to_prompt",
            "alternate-caption-provider",
            lambda inputs: "a portrait --ar 16:9 --v 6 --style raw",
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_to_prompt",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertEqual(payload["target_style"], "mj")
        self.assertIn("--ar", payload["prompt"])
        self.assertIn("--v", payload["prompt"])

    def test_target_style_sd_appends_detail_stack(self) -> None:
        """Stable Diffusion target appends a comma-separated detail stack."""
        body = {
            "slot": "image_to_prompt",
            "inputs": {"image": "obj_99", "target_style": "sd"},
        }
        registry, _calls = _fake_registry(
            "image_to_prompt",
            "alternate-caption-provider",
            lambda inputs: "masterpiece, highly detailed, 8k, hyperrealistic",
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_to_prompt",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertIn("masterpiece", payload["prompt"])
        self.assertIn("8k", payload["prompt"])

    def test_invalid_target_style_falls_back_to_dalle(self) -> None:
        """Unknown target_style is silently coerced to 'dalle'."""
        body = {
            "slot": "image_to_prompt",
            "inputs": {"image": "obj_99", "target_style": "klingon"},
        }
        registry, calls = _fake_registry(
            "image_to_prompt",
            "alternate-caption-provider",
            "a still life arrangement of objects on a wooden surface",
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_to_prompt",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertEqual(payload["target_style"], "dalle")
        self.assertEqual(calls[0]["inputs"]["target_style"], "dalle")

    def test_no_provider_error_includes_attempts(self) -> None:
        """Caption-provider exhaustion is returned with its attempt history."""
        from capability_registry import CapabilityError

        attempts = [{
            "provider_id": "replicate",
            "succeeded": False,
            "error_code": "model_unavailable",
            "error_message": "no token",
        }]
        registry = mock.Mock()
        registry.invoke.side_effect = CapabilityError(
            "model_unavailable",
            "No caption provider is available.",
            attempts=attempts,
        )
        body = {
            "slot": "image_to_prompt",
            "inputs": {"image": "obj_99"},
        }
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ):
            resp = self.client.post(
                "/api/capability/image_to_prompt",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 502)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "model_unavailable")
        self.assertEqual(payload["error"]["attempts"], attempts)

    def test_missing_image_returns_400(self) -> None:
        """Bad input: empty image surfaces image_unreadable."""
        body = {"slot": "image_to_prompt", "inputs": {}}
        resp = self.client.post(
            "/api/capability/image_to_prompt",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "image_unreadable")


class CapabilityVideoGeneratesRouteTests(unittest.TestCase):
    """Smoke tests for /api/capability/video_generates (Contracts §3.9, async).

    Provider transport is patched below the real registry and OpenRouter
    handler, so no credential or network is needed. Bad inputs must refuse
    before the capability is invoked.
    """

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    @contextmanager
    def _conversation_scope(self, sessions_root, conversation_id):
        if (Path(sessions_root) / conversation_id).is_dir():
            yield conversation_id, None
            return
        yield conversation_id, self.server._json_response(
            {"error": "conversation not found"}, status=404,
        )

    def _route_context(self, registry, sessions_root):
        context = mock.Mock()
        context.valid_live_conversation_id.side_effect = lambda value: (
            isinstance(value, str)
            and bool(value)
            and value == value.strip()
            and all(
                char.isascii()
                and (char.islower() or char.isdigit() or char in "_-")
                for char in value
            )
        )
        context.conversation_read_scope.side_effect = lambda value: (
            self._conversation_scope(sessions_root, value)
        )
        context.load_async_capability_registry.return_value = registry
        return context

    def test_happy_path_preserves_declared_parameters_and_job_shape(self) -> None:
        """The live handler queues every declared resolution without a 502."""
        from capability_registry import CapabilityRegistry
        from orchestrator.integrations import openrouter_images
        from orchestrator.job_queue import JobQueue

        provider_id = "openrouter:test/video-model"
        registry = CapabilityRegistry(routing_config={
            "slots": {
                "video_generates": {
                    "preferred": provider_id,
                    "fallback": [],
                },
            },
        })
        registry.register_provider(
            "video_generates",
            provider_id,
            openrouter_images._video_handler_factory("test/video-model"),
        )

        delivered: list[dict] = []

        def fake_call(model_id, prompt, **parameters):
            cancel_requested = parameters.pop("cancel_requested")
            self.assertFalse(cancel_requested())
            delivered.append({
                "model_id": model_id,
                "prompt": prompt,
                **parameters,
            })
            return b"video"

        contract = CapabilityRegistry().get_contract("video_generates")
        resolution_spec = next(
            spec for spec in contract["optional_inputs"]
            if spec["name"] == "resolution"
        )
        declared_resolutions = tuple(resolution_spec["enum_values"])
        view = self.server.app.view_functions[
            "plugin_video_capability_video_generates"
        ]
        route_module = sys.modules[view.__module__]
        with tempfile.TemporaryDirectory() as sessions_root:
            (Path(sessions_root) / "conv_smoke").mkdir()
            queue = JobQueue(sessions_root)
            context = self._route_context(registry, sessions_root)

            def run_inline(*args):
                openrouter_images._run_video_job(*args)

            with mock.patch.dict(
                     sys.modules, {"openrouter_images": openrouter_images},
                 ), mock.patch.object(route_module, "_context", context), \
                 mock.patch.object(
                     openrouter_images, "_resolve_key", return_value="test-key",
                 ), mock.patch.object(
                     openrouter_images, "_video_job_queue", return_value=queue,
                 ), mock.patch.object(
                     openrouter_images, "_start_video_worker", side_effect=run_inline,
                 ), mock.patch.object(
                     openrouter_images, "_call_video_model", side_effect=fake_call,
                 ) as transport:
                for resolution in declared_resolutions:
                    with self.subTest(resolution=resolution):
                        body = {
                            "slot": "video_generates",
                            "inputs": {
                                "prompt": "  A cat surfing on a wave at sunset  ",
                                "duration": 6.25,
                                "resolution": resolution,
                                "style": "  cinematic  ",
                            },
                            "placeholder_anchor": {
                                "x": 100, "y": 100, "width": 640, "height": 360,
                            },
                            "conversation_id": "conv_smoke",
                        }
                        resp = self.client.post(
                            "/api/capability/video_generates",
                            data=json.dumps(body),
                            content_type="application/json",
                        )
                        self.assertEqual(resp.status_code, 200, resp.data)
                        self.assertEqual(delivered[-1], {
                            "model_id": "test/video-model",
                            "prompt": "  A cat surfing on a wave at sunset  ",
                            "slot": "video_generates",
                            "duration": 6.25,
                            "resolution": resolution,
                            "style": "  cinematic  ",
                        })
                        payload = json.loads(resp.data)
                        self.assertEqual(payload["job"]["status"], "queued")
                        self.assertEqual(payload["conversation_id"], "conv_smoke")
                        self.assertEqual(
                            payload["job"]["placeholder_anchor"],
                            {"x": 100, "y": 100, "width": 640, "height": 360},
                        )
                        completed = queue.get_job(
                            "conv_smoke", payload["job"]["id"],
                        )
                        self.assertEqual(completed["status"], "complete")
                        result_url = completed["result_ref"]["video_url"]
                        self.assertIn(payload["job"]["id"], result_url)
                        artifact = (
                            Path(sessions_root)
                            / "conv_smoke"
                            / "uploads"
                            / result_url.rsplit("/", 1)[-1]
                        )
                        self.assertEqual(artifact.read_bytes(), b"video")

                transport.side_effect = RuntimeError("upstream generation failed")
                failed_resp = self.client.post(
                    "/api/capability/video_generates",
                    data=json.dumps({
                        "slot": "video_generates",
                        "inputs": {"prompt": "A generation that fails upstream"},
                        "conversation_id": "conv_smoke",
                    }),
                    content_type="application/json",
                )
                self.assertEqual(failed_resp.status_code, 200, failed_resp.data)
                failed_payload = json.loads(failed_resp.data)
                self.assertEqual(failed_payload["job"]["status"], "queued")
                failed = queue.get_job(
                    "conv_smoke", failed_payload["job"]["id"],
                )
                self.assertEqual(failed["status"], "failed")
                self.assertIn("upstream generation failed", failed["error"])

    def test_provider_fallback_keeps_the_requested_dialogue_binding(self) -> None:
        """Replicate refusal cannot send OpenRouter output to a default bucket."""
        from capability_registry import CapabilityError, CapabilityRegistry
        from orchestrator.integrations import openrouter_images
        from orchestrator.job_queue import JobQueue

        registry = CapabilityRegistry(routing_config={
            "slots": {
                "video_generates": {
                    "preferred": "replicate",
                    "fallback": ["openrouter:test/video-model"],
                    "fallback_on": ["model_unavailable"],
                },
            },
        })

        def replicate_refusal(_inputs):
            raise CapabilityError(
                "model_unavailable", "Replicate unavailable",
                slot="video_generates",
            )

        registry.register_provider(
            "video_generates", "replicate", replicate_refusal,
        )
        registry.register_provider(
            "video_generates",
            "openrouter:test/video-model",
            openrouter_images._video_handler_factory("test/video-model"),
        )

        view = self.server.app.view_functions[
            "plugin_video_capability_video_generates"
        ]
        route_module = sys.modules[view.__module__]
        with tempfile.TemporaryDirectory() as sessions_root:
            (Path(sessions_root) / "fallback_dialogue").mkdir()
            queue = JobQueue(sessions_root)
            context = self._route_context(registry, sessions_root)

            def run_inline(*args):
                openrouter_images._run_video_job(*args)

            with mock.patch.dict(
                     sys.modules, {"openrouter_images": openrouter_images},
                 ), mock.patch.object(route_module, "_context", context), \
                 mock.patch.object(
                     openrouter_images, "_resolve_key", return_value="test-key",
                 ), mock.patch.object(
                     openrouter_images, "_video_job_queue", return_value=queue,
                 ), mock.patch.object(
                     openrouter_images, "_start_video_worker", side_effect=run_inline,
                 ), mock.patch.object(
                     openrouter_images, "_call_video_model", return_value=b"video",
                 ):
                response = self.client.post(
                    "/api/capability/video_generates",
                    data=json.dumps({
                        "slot": "video_generates",
                        "inputs": {"prompt": "fallback test"},
                        "conversation_id": "fallback_dialogue",
                    }),
                    content_type="application/json",
                )

            self.assertEqual(response.status_code, 200, response.data)
            body = json.loads(response.data)
            completed = queue.get_job(
                "fallback_dialogue", body["job"]["id"],
            )
            self.assertEqual(completed["status"], "complete")
            self.assertEqual(
                completed["metadata"]["provider"],
                "openrouter:test/video-model",
            )
            self.assertIn(
                "/api/jobs/fallback_dialogue/",
                completed["result_ref"]["video_url"],
            )

    def test_openrouter_submit_body_includes_validated_parameters(self) -> None:
        """The real provider adapter carries all submitted fields to transport."""
        from orchestrator.integrations import openrouter_images

        calls = []
        responses = [
            json.dumps({
                "id": "job-1",
                "polling_url": "/api/v1/videos/job-1",
            }).encode(),
            json.dumps({
                "status": "completed",
                "unsigned_urls": [
                    "https://openrouter.ai.attacker.example/video.mp4"
                ],
            }).encode(),
            b"video",
        ]

        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0), mock.sentinel.destination

        with mock.patch.object(
            openrouter_images, "_resolve_key", return_value="test-key",
        ), mock.patch.object(
            openrouter_images.time, "sleep", return_value=None,
        ), mock.patch.object(
            openrouter_images.network_policy,
            "urllib_request_bytes",
            side_effect=fetch,
        ):
            result = openrouter_images._call_video_model(
                "vendor/model",
                "A cat surfing",
                poll_interval_s=0,
                max_wait_s=10,
                duration=6.25,
                resolution="4k",
                style="cinematic",
            )

        self.assertEqual(result, b"video")
        submitted = json.loads(calls[0][1]["data"].decode("utf-8"))
        self.assertEqual(submitted, {
            "model": "vendor/model",
            "prompt": "A cat surfing",
            "duration": 6.25,
            "style": "cinematic",
            "resolution": "4k",
        })
        self.assertEqual(
            calls[1][0],
            "https://openrouter.ai/api/v1/videos/job-1",
        )
        self.assertEqual(
            calls[1][1]["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(
            calls[1][1]["required_origin"],
            "https://openrouter.ai",
        )
        self.assertEqual(
            calls[2][0],
            "https://openrouter.ai.attacker.example/video.mp4",
        )
        self.assertNotIn("headers", calls[2][1])
        self.assertNotIn("required_origin", calls[2][1])

    def test_openrouter_hosted_result_uses_origin_locked_auth(self) -> None:
        """Only the exact OpenRouter origin receives result credentials."""
        from orchestrator.integrations import openrouter_images

        calls = []
        responses = [
            json.dumps({
                "id": "job-1",
                "polling_url": "/api/v1/videos/job-1",
            }).encode(),
            json.dumps({
                "status": "completed",
                "video_url": (
                    "https://openrouter.ai/api/v1/videos/job-1/content"
                ),
            }).encode(),
            b"video",
        ]

        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0), mock.sentinel.destination

        with mock.patch.object(
            openrouter_images, "_resolve_key", return_value="test-key",
        ), mock.patch.object(
            openrouter_images.time, "sleep", return_value=None,
        ), mock.patch.object(
            openrouter_images.network_policy,
            "urllib_request_bytes",
            side_effect=fetch,
        ):
            result = openrouter_images._call_video_model(
                "vendor/model",
                "A cat surfing",
                poll_interval_s=0,
                max_wait_s=10,
            )

        self.assertEqual(result, b"video")
        self.assertEqual(
            calls[2][0],
            "https://openrouter.ai/api/v1/videos/job-1/content",
        )
        self.assertEqual(
            calls[2][1]["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(
            calls[2][1]["required_origin"],
            "https://openrouter.ai",
        )
        self.assertEqual(calls[2][1]["max_redirects"], 0)

    def test_openrouter_provider_terminal_states_remain_truthful(self) -> None:
        """Cancelled stays cancelled; expired becomes an explicit failed job."""
        from orchestrator.integrations import openrouter_images
        from orchestrator.job_queue import JobQueue

        for terminal_status in ("cancelled", "expired"):
            with self.subTest(status=terminal_status):
                calls = []
                responses = [
                    json.dumps({
                        "id": "job-1",
                        "polling_url": "/api/v1/videos/job-1",
                    }).encode(),
                    json.dumps({"status": terminal_status}).encode(),
                ]

                def fetch(url, **kwargs):
                    calls.append((url, kwargs))
                    return responses.pop(0), mock.sentinel.destination

                with mock.patch.object(
                    openrouter_images, "_resolve_key", return_value="test-key",
                ), mock.patch.object(
                    openrouter_images.time, "sleep", return_value=None,
                ), mock.patch.object(
                    openrouter_images.network_policy,
                    "urllib_request_bytes",
                    side_effect=fetch,
                ):
                    with tempfile.TemporaryDirectory() as sessions_root:
                        (Path(sessions_root) / "video_dialogue").mkdir()
                        queue = JobQueue(sessions_root)
                        job = queue.dispatch(
                            "video_dialogue",
                            "video_generates",
                            {"prompt": "A cat surfing"},
                        )
                        openrouter_images._run_video_job(
                            queue,
                            "video_dialogue",
                            job["id"],
                            "vendor/model",
                            "A cat surfing",
                            None,
                            None,
                            None,
                        )
                        terminal = queue.get_job("video_dialogue", job["id"])

                expected_status = (
                    "cancelled" if terminal_status == "cancelled" else "failed"
                )
                self.assertEqual(terminal["status"], expected_status)
                if terminal_status == "expired":
                    self.assertIn("expired", terminal["error"])
                    self.assertNotIn("timed out", terminal["error"])
                self.assertEqual(len(calls), 2)
                self.assertEqual(responses, [])

    def test_openrouter_worker_observes_ora_cancellation_while_polling(self) -> None:
        """An in-progress cancel stops the bounded worker before another poll."""
        from orchestrator.integrations import openrouter_images
        from orchestrator.job_queue import JobQueue

        calls = []
        with tempfile.TemporaryDirectory() as sessions_root:
            (Path(sessions_root) / "video_dialogue").mkdir()
            queue = JobQueue(sessions_root)
            job = queue.dispatch(
                "video_dialogue",
                "video_generates",
                {"prompt": "A cat surfing"},
            )

            def fetch(url, **kwargs):
                calls.append((url, kwargs))
                if len(calls) == 1:
                    return json.dumps({
                        "id": "job-1",
                        "polling_url": "/api/v1/videos/job-1",
                    }).encode(), mock.sentinel.destination
                queue.request_cancel("video_dialogue", job["id"])
                return json.dumps({
                    "status": "running",
                }).encode(), mock.sentinel.destination

            with mock.patch.object(
                openrouter_images, "_resolve_key", return_value="test-key",
            ), mock.patch.object(
                openrouter_images.time, "sleep", return_value=None,
            ), mock.patch.object(
                openrouter_images.network_policy,
                "urllib_request_bytes",
                side_effect=fetch,
            ):
                openrouter_images._run_video_job(
                    queue,
                    "video_dialogue",
                    job["id"],
                    "vendor/model",
                    "A cat surfing",
                    None,
                    None,
                    None,
                )

            terminal = queue.get_job("video_dialogue", job["id"])
            self.assertEqual(terminal["status"], "cancelled")
            self.assertEqual(len(calls), 2)

    def test_untrusted_absolute_polling_origin_refuses_before_transport(self) -> None:
        """A provider response cannot redirect the bearer to another origin."""
        from orchestrator.integrations import openrouter_images

        calls = []

        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return json.dumps({
                "id": "job-1",
                "polling_url": (
                    "https://openrouter.ai.attacker.example/videos/job-1"
                ),
            }).encode(), mock.sentinel.destination

        with mock.patch.object(
            openrouter_images, "_resolve_key", return_value="test-key",
        ), mock.patch.object(
            openrouter_images.network_policy,
            "urllib_request_bytes",
            side_effect=fetch,
        ):
            with self.assertRaises(Exception) as raised:
                openrouter_images._call_video_model(
                    "vendor/model",
                    "A cat surfing",
                    poll_interval_s=0,
                    max_wait_s=10,
                )

        self.assertEqual(
            getattr(raised.exception, "code", None),
            "model_unavailable",
        )
        self.assertEqual(len(calls), 1)

    def test_missing_prompt_returns_400(self) -> None:
        """Bad input: empty prompt surfaces prompt_rejected."""
        from capability_registry import CapabilityRegistry

        view = self.server.app.view_functions[
            "plugin_video_capability_video_generates"
        ]
        route_module = sys.modules[view.__module__]
        with tempfile.TemporaryDirectory() as sessions_root:
            (Path(sessions_root) / "video_dialogue").mkdir()
            context = self._route_context(
                CapabilityRegistry(), sessions_root,
            )
            with mock.patch.object(route_module, "_context", context):
                resp = self.client.post(
                    "/api/capability/video_generates",
                    data=json.dumps({
                        "slot": "video_generates",
                        "inputs": {},
                        "conversation_id": "video_dialogue",
                    }),
                    content_type="application/json",
                )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "prompt_rejected")

    def test_missing_or_unknown_dialogue_refuses_before_provider_loading(self) -> None:
        """Async output cannot be filed under a synthetic or absent Dialogue."""
        from capability_registry import CapabilityRegistry

        view = self.server.app.view_functions[
            "plugin_video_capability_video_generates"
        ]
        route_module = sys.modules[view.__module__]
        with tempfile.TemporaryDirectory() as sessions_root:
            context = self._route_context(
                CapabilityRegistry(), sessions_root,
            )
            with mock.patch.object(route_module, "_context", context):
                missing = self.client.post(
                    "/api/capability/video_generates",
                    data=json.dumps({
                        "slot": "video_generates",
                        "inputs": {"prompt": "test prompt"},
                    }),
                    content_type="application/json",
                )
                unknown = self.client.post(
                    "/api/capability/video_generates",
                    data=json.dumps({
                        "slot": "video_generates",
                        "inputs": {"prompt": "test prompt"},
                        "conversation_id": "missing_dialogue",
                    }),
                    content_type="application/json",
                )

            self.assertEqual(missing.status_code, 400, missing.data)
            self.assertEqual(unknown.status_code, 404, unknown.data)
            context.load_async_capability_registry.assert_not_called()

    def test_invalid_parameters_are_rejected_before_invoke(self) -> None:
        """Invalid or undeclared inputs visibly refuse instead of disappearing."""
        from capability_registry import CapabilityRegistry

        cases = (
            ("undeclared resolution", {"resolution": "square"}, "resolution"),
            ("unknown resolution", {"resolution": "8k"}, "resolution"),
            ("coercible duration", {"duration": "6.25"}, "duration"),
            ("boolean duration", {"duration": True}, "duration"),
            ("invalid style", {"style": ["cinematic"]}, "style"),
            ("unknown fps", {"fps": 24}, "fps"),
            (
                "input-level provider override",
                {"provider_override": "openrouter:test/video-model"},
                "provider_override",
            ),
        )
        view = self.server.app.view_functions[
            "plugin_video_capability_video_generates"
        ]
        route_module = sys.modules[view.__module__]
        with tempfile.TemporaryDirectory() as sessions_root:
            (Path(sessions_root) / "video_dialogue").mkdir()
            context = self._route_context(
                CapabilityRegistry(), sessions_root,
            )
            with mock.patch.object(route_module, "_context", context), \
                 mock.patch(
                     "capability_registry.CapabilityRegistry.invoke",
                 ) as invoke:
                for label, invalid, field in cases:
                    with self.subTest(label=label):
                        invoke.reset_mock()
                        resp = self.client.post(
                            "/api/capability/video_generates",
                            data=json.dumps({
                                "slot": "video_generates",
                                "inputs": {
                                    "prompt": "test prompt", **invalid,
                                },
                                "conversation_id": "video_dialogue",
                            }),
                            content_type="application/json",
                        )
                        self.assertEqual(resp.status_code, 400, resp.data)
                        payload = json.loads(resp.data)
                        self.assertEqual(
                            payload["error"]["code"], "prompt_rejected",
                        )
                        self.assertIn(field, payload["error"]["message"])
                        invoke.assert_not_called()


class CapabilityImageEditsRouteTests(unittest.TestCase):
    """Required-input handling for /api/capability/image_edits (§3.2).

    ``prompt`` is one of three required inputs alongside ``image`` and
    ``mask``. The route used to invent a prompt when the caller left it
    blank; these tests pin the rejection. Every blank-prompt case below
    supplies valid image and mask data URLs, so a 400 can only be coming
    from the prompt and not from data-URL decoding.
    """

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def _post(self, body: dict):
        return self.client.post(
            "/api/capability/image_edits",
            data=json.dumps(body),
            content_type="application/json",
        )

    def test_absent_prompt_returns_400(self) -> None:
        """No `prompt` key at all → missing_required_input, no invention."""
        resp = self._post({
            "slot": "image_edits",
            "image_data_url": _tiny_png_data_url(),
            "mask_data_url": _tiny_png_data_url(),
        })
        self.assertEqual(resp.status_code, 400, resp.data)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "missing_required_input")
        self.assertIn("prompt", payload["error"]["message"])

    def test_blank_prompt_returns_400(self) -> None:
        """Whitespace-only `prompt` is blank, not a prompt."""
        resp = self._post({
            "slot": "image_edits",
            "prompt": "   \n\t ",
            "image_data_url": _tiny_png_data_url(),
            "mask_data_url": _tiny_png_data_url(),
        })
        self.assertEqual(resp.status_code, 400, resp.data)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "missing_required_input")

    def test_wellformed_request_unaffected(self) -> None:
        """A provider image URL becomes the existing image_b64 response."""
        provider_url = "https://replicate.delivery/example.png"
        provider_bytes = _tiny_png_bytes()
        registry, _calls = _fake_registry(
            "image_edits",
            "replicate",
            {"image_url": provider_url},
        )
        with mock.patch.object(
            self.server, "_load_image_capability_registry", return_value=registry
        ), mock.patch.object(
            self.server, "_fetch_provider_asset", return_value=provider_bytes
        ) as fetch_asset:
            resp = self._post({
                "slot": "image_edits",
                "prompt": "make it blue",
                "image_data_url": _tiny_png_data_url(),
                "mask_data_url": _tiny_png_data_url(),
            })
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertNotIn("mocked", payload)
        self.assertEqual(payload.get("mode"), "inpaint")
        self.assertIsInstance(payload.get("image_b64"), str)
        self.assertEqual(
            payload["image_b64"], base64.b64encode(provider_bytes).decode("ascii")
        )
        self.assertEqual(payload["attempts"][0]["provider_id"], "replicate")
        fetch_asset.assert_called_once_with(provider_url, timeout=30)

    def test_prompt_reaches_the_provider_verbatim(self) -> None:
        """The real path hands the caller's own words to the registry."""
        captured: dict = {}

        from capability_registry import InvocationResult

        def fake_invoke(self, slot, inputs, provider_id=None, **kw):
            captured["inputs"] = dict(inputs)
            return InvocationResult(
                slot=slot,
                provider_id="local-diffusers",
                output=b"\x89PNG\r\n\x1a\nfake",
                execution_pattern="sync",
            )

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), \
                mock.patch("capability_registry.CapabilityRegistry.invoke",
                           new=fake_invoke):
            resp = self._post({
                "slot": "image_edits",
                "prompt": "make it blue",
                "image_data_url": _tiny_png_data_url(),
                "mask_data_url": _tiny_png_data_url(),
            })
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(captured.get("inputs", {}).get("prompt"), "make it blue")


if __name__ == "__main__":
    unittest.main()
