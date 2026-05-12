"""Tests for civitai_images — fallback dispatcher for image_generates_cartoon.

Covers:
  - prompt validation (missing / empty)
  - activation token auto-prepend (hectorcartoon)
  - style hint appended
  - aspect_ratio → (width, height) mapping
  - missing API key → CapabilityError(model_unavailable)
  - successful POST + image fetch → bytes
  - HTTP 401/403 → model_unavailable
  - HTTP 402 / 429 → quota_exceeded
  - HTTP 400 with policy language → prompt_rejected
  - non-policy HTTP 400 → model_unavailable
  - job status terminal failure → model_unavailable
  - job status failure with policy reason → prompt_rejected
  - non-terminal status triggers polling until terminal
  - polling timeout returns model_unavailable
  - register() binds the provider id correctly
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
INTEGRATIONS = os.path.join(ORCH, "integrations")
for p in (ORCH, INTEGRATIONS):
    if p not in sys.path:
        sys.path.insert(0, p)

import civitai_images  # noqa: E402
from capability_registry import (  # noqa: E402
    CapabilityError,
    CapabilityRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(payload_dict, status=200):
    """Build a context-manager-shaped response that urlopen returns."""
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    resp = mock.MagicMock()
    resp.read.return_value = payload_bytes
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.status = status
    return resp


def _fake_binary_response(content_bytes):
    """Same shape but with raw bytes (for the image fetch step)."""
    resp = mock.MagicMock()
    resp.read.return_value = content_bytes
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.status = 200
    return resp


def _http_error(status, body_text=""):
    """Build a urllib HTTPError that exposes status + read()."""
    err = urllib.error.HTTPError(
        url="https://orchestration.civitai.com/v2/consumer/workflows?wait=120",
        code=status,
        msg=f"HTTP {status}",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(body_text.encode("utf-8")),
    )
    return err


SAMPLE_SUCCESS_PAYLOAD = {
    "id": "wf_test_123",
    "status": "succeeded",
    "steps": [{
        "output": {
            "images": [{
                "id": "img_1",
                "url": "https://orchestration-new.civitai.com/blobs/img_1.jpg?sig=fake",
                "available": True,
            }],
        },
    }],
}

SAMPLE_IMAGE_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00fakepayload"


# ---------------------------------------------------------------------------
# Prompt validation
# ---------------------------------------------------------------------------

class TestPromptValidation(unittest.TestCase):

    def test_missing_prompt_raises(self):
        with self.assertRaises(CapabilityError) as cm:
            civitai_images.dispatch_hector_lora({})
        self.assertEqual(cm.exception.code, "missing_required_input")

    def test_empty_prompt_raises(self):
        with self.assertRaises(CapabilityError) as cm:
            civitai_images.dispatch_hector_lora({"prompt": "   "})
        self.assertEqual(cm.exception.code, "missing_required_input")

    def test_non_string_prompt_raises(self):
        with self.assertRaises(CapabilityError) as cm:
            civitai_images.dispatch_hector_lora({"prompt": 12345})
        self.assertEqual(cm.exception.code, "missing_required_input")


# ---------------------------------------------------------------------------
# Activation-token auto-prepend
# ---------------------------------------------------------------------------

class TestActivationToken(unittest.TestCase):

    def _capture_body(self, inputs):
        """Run the dispatcher with mocked urlopen + keychain and return
        the parsed JSON body of the workflow POST."""
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                captured["body"] = json.loads(req.data.decode("utf-8"))
                return _fake_response(SAMPLE_SUCCESS_PAYLOAD)
            # Image fetch path
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                civitai_images.dispatch_hector_lora(inputs)
        return captured["body"]

    def test_auto_prepends_activation_token_when_missing(self):
        """The LoRA dispatcher auto-prepends `hectorcartoon` to prompts
        that don't already include it. Under the 2026-05-12 slot-separation
        architecture, this dispatcher is only registered against
        `image_generates_cartoon`, so any prompt that reaches it is by
        definition a cartoon prompt — auto-prepend is correct."""
        body = self._capture_body({"prompt": "a man at a podium"})
        prompt = body["steps"][0]["input"]["prompt"]
        # The activation token must lead the prompt.
        self.assertTrue(prompt.lower().startswith("hectorcartoon"))
        self.assertIn("a man at a podium", prompt)
        # And only once — no double-prepend.
        self.assertEqual(prompt.lower().count("hectorcartoon"), 1)

    def test_accepts_prompt_with_activation_token(self):
        body = self._capture_body(
            {"prompt": "hectorcartoon, a man at a podium"})
        prompt = body["steps"][0]["input"]["prompt"]
        # The token should appear exactly once in the submitted body.
        self.assertEqual(prompt.lower().count("hectorcartoon"), 1)
        self.assertIn("a man at a podium", prompt)

    def test_style_hint_appended_when_token_present(self):
        body = self._capture_body({
            "prompt": "hectorcartoon, a man at a podium",
            "style": "watercolor wash",
        })
        prompt = body["steps"][0]["input"]["prompt"]
        self.assertIn("in the style of watercolor wash", prompt)


# ---------------------------------------------------------------------------
# Aspect ratio mapping
# ---------------------------------------------------------------------------

class TestAspectRatio(unittest.TestCase):

    def _capture_body(self, inputs):
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                captured["body"] = json.loads(req.data.decode("utf-8"))
                return _fake_response(SAMPLE_SUCCESS_PAYLOAD)
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                civitai_images.dispatch_hector_lora(inputs)
        return captured["body"]

    def test_1_1_default(self):
        body = self._capture_body({"prompt": "hectorcartoon, x"})
        inp = body["steps"][0]["input"]
        self.assertEqual((inp["width"], inp["height"]), (1024, 1024))

    def test_16_9(self):
        body = self._capture_body({"prompt": "hectorcartoon, x", "aspect_ratio": "16:9"})
        inp = body["steps"][0]["input"]
        self.assertEqual((inp["width"], inp["height"]), (1344, 768))

    def test_9_16(self):
        body = self._capture_body({"prompt": "hectorcartoon, x", "aspect_ratio": "9:16"})
        inp = body["steps"][0]["input"]
        self.assertEqual((inp["width"], inp["height"]), (768, 1344))

    def test_unknown_aspect_falls_back_to_square(self):
        body = self._capture_body({"prompt": "hectorcartoon, x", "aspect_ratio": "weird"})
        inp = body["steps"][0]["input"]
        self.assertEqual((inp["width"], inp["height"]), (1024, 1024))


# ---------------------------------------------------------------------------
# Body shape correctness
# ---------------------------------------------------------------------------

class TestBodyShape(unittest.TestCase):

    def test_body_includes_lora_air_and_flux2_klein_engine(self):
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                captured["body"] = json.loads(req.data.decode("utf-8"))
                return _fake_response(SAMPLE_SUCCESS_PAYLOAD)
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})

        body = captured["body"]
        inp = body["steps"][0]["input"]
        self.assertEqual(body["steps"][0]["$type"], "imageGen")
        self.assertEqual(inp["engine"], "flux2")
        self.assertEqual(inp["model"], "klein")
        self.assertEqual(inp["modelVersion"], "9b-base")
        self.assertEqual(inp["operation"], "createImage")
        # LoRA dict keyed by AIR
        loras = inp["loras"]
        self.assertIn(civitai_images.HECTOR_LORA_AIR, loras)
        self.assertEqual(loras[civitai_images.HECTOR_LORA_AIR],
                         civitai_images.HECTOR_LORA_STRENGTH)


# ---------------------------------------------------------------------------
# Auth / key handling
# ---------------------------------------------------------------------------

class TestAuth(unittest.TestCase):

    def test_missing_api_key_raises_model_unavailable(self):
        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value=None):
            with self.assertRaises(CapabilityError) as cm:
                civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
        self.assertEqual(cm.exception.code, "model_unavailable")

    def test_bearer_header_attached(self):
        captured: dict = {}

        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                captured["headers"] = dict(req.headers)
                return _fake_response(SAMPLE_SUCCESS_PAYLOAD)
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="test-token-123"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})

        # urllib.request.Request normalizes header names to titlecase
        self.assertEqual(captured["headers"].get("Authorization"),
                         "Bearer test-token-123")
        self.assertIn("Mozilla", captured["headers"].get("User-agent", ""))


# ---------------------------------------------------------------------------
# HTTP error translation
# ---------------------------------------------------------------------------

class TestHttpErrors(unittest.TestCase):

    def _run_with_http_error(self, status, body=""):
        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                raise _http_error(status, body)
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                try:
                    civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
                except CapabilityError as exc:
                    return exc
        return None

    def test_401_unauthorized(self):
        exc = self._run_with_http_error(401, '{"detail":"bad token"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "model_unavailable")

    def test_403_forbidden(self):
        exc = self._run_with_http_error(403, '{"detail":"access denied"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "model_unavailable")

    def test_402_insufficient_funds(self):
        exc = self._run_with_http_error(402, '{"detail":"not enough buzz"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "quota_exceeded")

    def test_429_rate_limit(self):
        exc = self._run_with_http_error(429, '{"detail":"slow down"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "quota_exceeded")

    def test_400_with_policy_language_is_prompt_rejected(self):
        exc = self._run_with_http_error(
            400, '{"detail":"prompt blocked by content policy"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "prompt_rejected")

    def test_400_with_moderation_language_is_prompt_rejected(self):
        exc = self._run_with_http_error(
            400, '{"error":"moderation rejection: prohibited content"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "prompt_rejected")

    def test_generic_400_is_model_unavailable(self):
        exc = self._run_with_http_error(
            400, '{"errors":{"input":["malformed shape"]}}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "model_unavailable")

    def test_500_is_model_unavailable(self):
        exc = self._run_with_http_error(500, '{"detail":"server error"}')
        self.assertIsNotNone(exc)
        self.assertEqual(exc.code, "model_unavailable")


# ---------------------------------------------------------------------------
# Job status translation
# ---------------------------------------------------------------------------

class TestJobStatus(unittest.TestCase):

    def _run_with_payload(self, payload):
        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                return _fake_response(payload)
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                try:
                    return civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
                except CapabilityError as exc:
                    return exc

    def test_failed_status_is_model_unavailable(self):
        exc = self._run_with_payload({
            "status": "failed",
            "id": "wf",
            "reason": "GPU node crashed",
        })
        self.assertIsInstance(exc, CapabilityError)
        self.assertEqual(exc.code, "model_unavailable")

    def test_failed_with_policy_reason_is_prompt_rejected(self):
        exc = self._run_with_payload({
            "status": "failed",
            "id": "wf",
            "reason": "Content policy violation in prompt",
        })
        self.assertIsInstance(exc, CapabilityError)
        self.assertEqual(exc.code, "prompt_rejected")

    def test_canceled_is_model_unavailable(self):
        exc = self._run_with_payload({"status": "canceled", "id": "wf"})
        self.assertIsInstance(exc, CapabilityError)
        self.assertEqual(exc.code, "model_unavailable")

    def test_succeeded_with_missing_steps_is_model_unavailable(self):
        exc = self._run_with_payload({
            "status": "succeeded", "id": "wf", "steps": []})
        self.assertIsInstance(exc, CapabilityError)
        self.assertEqual(exc.code, "model_unavailable")

    def test_succeeded_with_missing_images_is_model_unavailable(self):
        exc = self._run_with_payload({
            "status": "succeeded", "id": "wf",
            "steps": [{"output": {"images": []}}],
        })
        self.assertIsInstance(exc, CapabilityError)
        self.assertEqual(exc.code, "model_unavailable")


# ---------------------------------------------------------------------------
# Polling — non-terminal status → poll loop → terminal
# ---------------------------------------------------------------------------

class TestPolling(unittest.TestCase):

    def setUp(self):
        # Speed up polling for tests — patch the constants down to a
        # near-zero interval and short cap. The tested function imports
        # time at use; patching time.sleep is the cleaner intervention.
        self._sleep_patcher = mock.patch("time.sleep", return_value=None)
        self._sleep_patcher.start()
        self.addCleanup(self._sleep_patcher.stop)

    def test_scheduled_then_succeeded(self):
        """POST returns 'scheduled' with id; the next poll returns
        'succeeded' with image URL — dispatcher fetches and returns bytes.
        """
        poll_responses = iter([
            _fake_response({"status": "scheduled", "id": "wf"}),
            _fake_response({
                **SAMPLE_SUCCESS_PAYLOAD,
                "id": "wf",
            }),
            _fake_binary_response(SAMPLE_IMAGE_BYTES),
        ])

        def fake_urlopen(req, **kwargs):
            return next(poll_responses)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                result = civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
        self.assertEqual(result, SAMPLE_IMAGE_BYTES)

    def test_polling_timeout_returns_model_unavailable(self):
        """If polling exhausts the cap without hitting a terminal status,
        dispatcher raises model_unavailable."""
        # First call: POST returns scheduled. Every subsequent call returns
        # scheduled too. We patch _POLL_MAX_SECONDS down to a small cap.
        all_scheduled = _fake_response({"status": "scheduled", "id": "wf"})

        def fake_urlopen(req, **kwargs):
            # Return a fresh mock each time (so the context manager works)
            return _fake_response({"status": "scheduled", "id": "wf"})

        with mock.patch.object(civitai_images, "_POLL_MAX_SECONDS", 8):
            with mock.patch.object(civitai_images, "_POLL_INTERVAL_SEC", 2):
                with mock.patch.object(civitai_images, "_get_api_key",
                                       return_value="fake-key"):
                    with mock.patch("urllib.request.urlopen",
                                    side_effect=fake_urlopen):
                        with self.assertRaises(CapabilityError) as cm:
                            civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
        self.assertEqual(cm.exception.code, "model_unavailable")

    def test_polling_failed_status_is_translated(self):
        responses = iter([
            _fake_response({"status": "scheduled", "id": "wf"}),
            _fake_response({"status": "failed", "id": "wf",
                            "reason": "Content policy violation"}),
        ])

        def fake_urlopen(req, **kwargs):
            return next(responses)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                with self.assertRaises(CapabilityError) as cm:
                    civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
        self.assertEqual(cm.exception.code, "prompt_rejected")


# ---------------------------------------------------------------------------
# Network error handling
# ---------------------------------------------------------------------------

class TestNetworkErrors(unittest.TestCase):

    def test_url_error_is_model_unavailable(self):
        def fake_urlopen(req, **kwargs):
            raise urllib.error.URLError("Connection refused")

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                with self.assertRaises(CapabilityError) as cm:
                    civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
        self.assertEqual(cm.exception.code, "model_unavailable")

    def test_image_fetch_url_error_is_model_unavailable(self):
        # POST succeeds with image URL, but the image fetch fails.
        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                return _fake_response(SAMPLE_SUCCESS_PAYLOAD)
            raise urllib.error.URLError("Connection refused on image CDN")

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                with self.assertRaises(CapabilityError) as cm:
                    civitai_images.dispatch_hector_lora({"prompt": "hectorcartoon, x"})
        self.assertEqual(cm.exception.code, "model_unavailable")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration(unittest.TestCase):

    def test_register_binds_provider_against_image_generates_cartoon(self):
        """Per the 2026-05-12 slot-separation architecture, the LoRA is
        registered only against `image_generates_cartoon` — not the
        general `image_generates` slot used for news / illustration."""
        registry = CapabilityRegistry()
        civitai_images.register(registry)
        self.assertIn(
            "civitai-hector-lora-v1",
            registry.providers_for("image_generates_cartoon"),
        )

    def test_register_does_not_bind_to_image_generates(self):
        """Defensive: confirm the LoRA cannot be reached through the
        general image_generates slot. News / illustration prompts must
        never route to this dispatcher."""
        registry = CapabilityRegistry()
        civitai_images.register(registry)
        self.assertNotIn(
            "civitai-hector-lora-v1",
            registry.providers_for("image_generates"),
        )

    def test_register_handler_is_callable(self):
        registry = CapabilityRegistry()
        civitai_images.register(registry)
        self.assertTrue(registry.has_provider(
            "image_generates_cartoon", "civitai-hector-lora-v1"))


# ---------------------------------------------------------------------------
# Success-path end-to-end (mocked)
# ---------------------------------------------------------------------------

class TestEndToEnd(unittest.TestCase):

    def test_happy_path_returns_image_bytes(self):
        def fake_urlopen(req, **kwargs):
            if "workflows" in req.full_url and req.get_method() == "POST":
                return _fake_response(SAMPLE_SUCCESS_PAYLOAD)
            # Image fetch from the signed URL
            self.assertIn("orchestration-new.civitai.com",
                          req.full_url)
            return _fake_binary_response(SAMPLE_IMAGE_BYTES)

        with mock.patch.object(civitai_images, "_get_api_key",
                               return_value="fake-key"):
            with mock.patch("urllib.request.urlopen",
                            side_effect=fake_urlopen):
                result = civitai_images.dispatch_hector_lora(
                    {"prompt": "hectorcartoon, test", "aspect_ratio": "1:1"})
        self.assertEqual(result, SAMPLE_IMAGE_BYTES)
        # JPEG magic bytes
        self.assertEqual(result[:2], b"\xff\xd8")


if __name__ == "__main__":
    unittest.main()
