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

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_capability_routes_rerun -v

Mock paths are explicit (``mock=true``) so the tests run cleanly even
when a Replicate token is configured locally.
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

    Used by the mock paths to verify image_bytes flow through. We build
    via PIL so the mock paths can decode and tint it without erroring.
    """
    from PIL import Image
    img = Image.new("RGBA", (4, 4), (128, 128, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


class CapabilityImageVariesRouteTests(unittest.TestCase):
    """Smoke tests for /api/capability/image_varies (Contracts §3.6)."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_happy_mock_returns_image_list(self) -> None:
        """Mock path returns a list of base64 images keyed under `images`."""
        body = {
            "slot": "image_varies",
            "inputs": {
                "source_image": "obj_42",
                "count": 4,
                "variation_strength": 0.5,
                "source_image_data_url": _tiny_png_data_url(),
            },
            "mock": True,
        }
        resp = self.client.post(
            "/api/capability/image_varies",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertTrue(payload.get("mocked"))
        self.assertEqual(payload.get("provider"), "mock-image-varies")
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
            "mock": True,
        }
        resp = self.client.post(
            "/api/capability/image_varies",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertLessEqual(len(payload["images"]), 8)

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
        """When no source_image_data_url is supplied, mock still emits images."""
        body = {
            "slot": "image_varies",
            "inputs": {"source_image": "obj_42", "count": 2},
            "mock": True,
        }
        resp = self.client.post(
            "/api/capability/image_varies",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertEqual(len(payload["images"]), 2)


class CapabilityImageToPromptRouteTests(unittest.TestCase):
    """Smoke tests for /api/capability/image_to_prompt (Contracts §3.7)."""

    def setUp(self) -> None:
        import server  # noqa: WPS433
        self.server = server
        self.client = server.app.test_client()

    def test_happy_mock_dalle_returns_plain_caption(self) -> None:
        """Default target_style 'dalle' emits a plain caption with no suffix flags."""
        body = {
            "slot": "image_to_prompt",
            "inputs": {"image": "obj_99"},
            "mock": True,
        }
        resp = self.client.post(
            "/api/capability/image_to_prompt",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertTrue(payload.get("mocked"))
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
            "mock": True,
        }
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
            "mock": True,
        }
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
            "mock": True,
        }
        resp = self.client.post(
            "/api/capability/image_to_prompt",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertEqual(payload["target_style"], "dalle")

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
        import server  # noqa: WPS433
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


if __name__ == "__main__":
    unittest.main()
