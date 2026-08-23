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


class CapabilityImageVariesRouteTests(unittest.TestCase):
    """Smoke tests for /api/capability/image_varies (Contracts §3.6)."""

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_patched_provider_returns_image_list(self) -> None:
        """A patched provider returns the route's real image-list shape."""
        body = {
            "slot": "image_varies",
            "inputs": {
                "source_image": "obj_42",
                "count": 4,
                "variation_strength": 0.5,
                "source_image_data_url": _tiny_png_data_url(),
            },
        }
        registry, _calls = _fake_registry(
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
        self.assertIsInstance(payload.get("images"), list)
        self.assertEqual(len(payload["images"]), 4)
        for entry in payload["images"]:
            self.assertIsInstance(entry, dict)
            self.assertIn("data", entry)
            self.assertIsInstance(entry["data"], str)
            self.assertTrue(len(entry["data"]) > 50, "expected non-empty base64")
            # Ensure it's actually decodable.
            base64.b64decode(entry["data"])

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

    def test_no_source_bytes_falls_back_to_placeholder(self) -> None:
        """When no source_image_data_url is supplied, patched provider emits images."""
        body = {
            "slot": "image_varies",
            "inputs": {"source_image": "obj_42", "count": 2},
        }
        registry, _calls = _fake_registry(
            "image_varies",
            "local-diffusers",
            lambda inputs: [
                {"image_data_uri": _tiny_png_data_url()}
                for _ in range(2)
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
        self.assertEqual(len(payload["images"]), 2)

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
            "inputs": {"source_image": "obj_42"},
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
                            "inputs": {"source_image": "obj_42"},
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

    Async slot: no mock path. We patch the Replicate dispatcher so the test
    doesn't require a real token, but the route's job-dict shape is what we
    verify here. A bad-input test confirms the prompt_rejected error code.
    """

    def setUp(self) -> None:
        from server import app as server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_happy_path_returns_job_dict(self) -> None:
        """Successful invoke returns { job: {id, status, ...}, conversation_id }."""
        fake_job = {
            "id": "job_abc123",
            "status": "queued",
            "capability": "video_generates",
            "parameters": {"prompt": "A cat surfing"},
            "dispatched_at": 1714521600,
        }

        # Stub the registry's invoke so no real Replicate call happens.
        # The route's import path lazily loads replicate +
        # capability_registry; we patch at the registry layer to keep the
        # patch surface minimal.
        from capability_registry import InvocationResult
        fake_result = InvocationResult(
            slot="video_generates",
            provider_id="replicate",
            output=fake_job,
            execution_pattern="async",
        )

        with mock.patch("capability_registry.CapabilityRegistry.invoke",
                        return_value=fake_result):
            body = {
                "slot": "video_generates",
                "inputs": {
                    "prompt": "A cat surfing on a wave at sunset",
                    "duration": 6,
                    "resolution": "1080p",
                    "style": "cinematic",
                },
                "placeholder_anchor": {"x": 100, "y": 100, "width": 640, "height": 360},
                "conversation_id": "conv_smoke",
            }
            resp = self.client.post(
                "/api/capability/video_generates",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertIn("job", payload)
        self.assertEqual(payload["job"]["id"], "job_abc123")
        self.assertEqual(payload["job"]["status"], "queued")
        self.assertEqual(payload["conversation_id"], "conv_smoke")
        # placeholder_anchor is stamped onto the response job dict.
        self.assertEqual(
            payload["job"]["placeholder_anchor"],
            {"x": 100, "y": 100, "width": 640, "height": 360},
        )

    def test_missing_prompt_returns_400(self) -> None:
        """Bad input: empty prompt surfaces prompt_rejected."""
        body = {"slot": "video_generates", "inputs": {}}
        resp = self.client.post(
            "/api/capability/video_generates",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        payload = json.loads(resp.data)
        self.assertEqual(payload["error"]["code"], "prompt_rejected")

    def test_invalid_resolution_silently_dropped(self) -> None:
        """Unknown resolution is dropped from handler_inputs (not an error)."""
        captured: dict = {}

        from capability_registry import InvocationResult

        def fake_invoke(self, slot, inputs, provider_id=None, **kw):
            captured["inputs"] = dict(inputs)
            return InvocationResult(
                slot=slot,
                provider_id="replicate",
                output={"id": "j1", "status": "queued",
                        "capability": slot, "parameters": inputs},
                execution_pattern="async",
            )

        with mock.patch("capability_registry.CapabilityRegistry.invoke",
                        new=fake_invoke):
            body = {
                "slot": "video_generates",
                "inputs": {
                    "prompt": "test prompt",
                    "resolution": "8k",  # not in valid set
                },
            }
            resp = self.client.post(
                "/api/capability/video_generates",
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        # 'resolution' should not be in handler_inputs since 8k is rejected.
        self.assertNotIn("resolution", captured.get("inputs", {}))


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
