#!/usr/bin/env python3
"""Gemini 2.5 Flash Image integration tests (MSI §5.8.1 Slot 2).

Covers the §13.3 test criterion: "Live call to each integrated endpoint
with a benign payload; verify successful output and correct slot
dispatch." Live calls are gated behind ``ORA_LIVE_GEMINI_IMAGES=1`` so
the default test run uses mocked HTTP (mirrors the openai_images +
stability_integration pattern).

Three test classes:

* ``GeminiImageRegistrationTests``   — registration plumbing.
* ``GeminiImageDispatchMockedTests`` — mocked urlopen, validates
  request shape + response parsing + the full error taxonomy
  (HTTP 4xx/5xx + 200-with-block-reason + 200-with-empty-candidates +
  finish-reason safety variants).
* ``GeminiImageDispatchLiveTests``   — live Google call, single benign
  payload, opt-in via env var.

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_gemini_integration -v
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from capability_registry import CapabilityError, CapabilityRegistry  # noqa: E402

from integrations import gemini_images  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimum-viable PNG (1×1 transparent). Used as the "image bytes" the
# fake Gemini server returns base64-encoded inside inlineData.data.
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xfc\xff\xff?\x00\x05\xfe\x02\xfe\xa3"
    b"\xb1\x83\xa3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _stub_capabilities_dict() -> dict:
    """Minimal capabilities dict declaring only the slot gemini_images
    fulfills. Mirrors test_openai_images for consistency."""
    return {
        "_schema_version": 1,
        "slots": {
            "image_generates": {
                "name": "image_generates",
                "summary": "Generate.",
                "required_inputs": [
                    {"name": "prompt", "type": "text", "description": "x"}
                ],
                "optional_inputs": [
                    {"name": "style", "type": "text", "default": None},
                    {"name": "aspect_ratio", "type": "enum", "default": "1:1"},
                ],
                "output": {"type": "image-bytes"},
                "execution_pattern": "sync",
                "common_errors": [
                    {"code": "model_unavailable"},
                    {"code": "prompt_rejected"},
                    {"code": "quota_exceeded"},
                ],
            },
        },
    }


def _gemini_success_payload(image_bytes: bytes = TINY_PNG) -> bytes:
    """Return a JSON-encoded Gemini ``generateContent`` response that
    carries ``image_bytes`` (base64-encoded) inside the first
    candidate's first inlineData part."""
    return json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": base64.b64encode(image_bytes).decode("ascii"),
                                }
                            }
                        ],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ]
        }
    ).encode("utf-8")


def _fake_urlopen_factory(
    captured: dict,
    response_bytes: bytes | None = None,
    status_code: int = 200,
    error_body: bytes | None = None,
    network_error: bool = False,
):
    """Build a urlopen replacement that captures the outgoing request
    and returns ``response_bytes`` (or raises HTTPError / URLError)."""

    class _FakeResponse:
        def __init__(self, payload: bytes):
            self._buf = io.BytesIO(payload)

        def read(self):
            return self._buf.read()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = request.data
        captured["timeout"] = timeout
        if network_error:
            raise urllib.error.URLError("simulated network failure")
        if status_code >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                status_code,
                "Error",
                hdrs=request.headers,
                fp=io.BytesIO(error_body or b""),
            )
        return _FakeResponse(response_bytes if response_bytes is not None else _gemini_success_payload())

    return _fake_urlopen


# ---------------------------------------------------------------------------
# Registration plumbing
# ---------------------------------------------------------------------------

class GeminiImageRegistrationTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())

    def test_register_binds_image_generates(self) -> None:
        gemini_images.register(self.registry)
        self.assertIn(
            gemini_images.PROVIDER_ID,
            self.registry.providers_for("image_generates"),
        )

    def test_provider_id_matches_models_json_id(self) -> None:
        """The PROVIDER_ID must match ``models.json``'s ``id`` field so
        ``routing-config.json`` (updated by Item 3) can reference this
        provider by the same string the V3 Settings panel exposes."""
        self.assertEqual(gemini_images.PROVIDER_ID, "gemini-2.5-flash-image")

    def test_register_skips_when_slot_absent(self) -> None:
        """``register()`` returns an empty list and does not raise when
        the slot isn't declared in capabilities — matches stability.py."""
        empty_registry = CapabilityRegistry(config_dict={"_schema_version": 1, "slots": {}})
        registered = gemini_images.register(empty_registry)
        self.assertEqual(registered, [])


# ---------------------------------------------------------------------------
# Mocked dispatch — no network
# ---------------------------------------------------------------------------

class GeminiImageDispatchMockedTests(unittest.TestCase):

    API_KEY = "AIza-test-gemini-1234567890"

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())
        gemini_images.register(self.registry)
        # Force the auth helper to return our test key without
        # touching the real env or keychain.
        self._patcher = mock.patch.object(
            gemini_images, "_get_api_key", return_value=self.API_KEY,
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    # -- Happy path -----------------------------------------------------

    def test_dispatch_returns_decoded_image_bytes(self) -> None:
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            result = self.registry.invoke(
                "image_generates",
                {"prompt": "a tabby kitten on a windowsill"},
            )
        self.assertEqual(result.output, TINY_PNG)
        self.assertEqual(result.provider_id, "gemini-2.5-flash-image")

    def test_request_body_shape_matches_gemini_contract(self) -> None:
        """Body must be ``{"contents": [{"parts": [{"text": "..."}]}]}``."""
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            gemini_images.dispatch_image_generates({"prompt": "hello"})
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual(
            body,
            {"contents": [{"parts": [{"text": "hello"}]}]},
        )

    def test_api_key_passed_as_query_parameter(self) -> None:
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            gemini_images.dispatch_image_generates({"prompt": "hi"})
        # The Generative Language API takes ?key=<api-key>, not a
        # Bearer header. The Authorization header MUST NOT be set
        # (defensive — leaking the key on a header would be a regression).
        self.assertIn(f"key={self.API_KEY}", captured["url"])
        self.assertNotIn("Authorization", captured["headers"])

    def test_user_agent_header_set(self) -> None:
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            gemini_images.dispatch_image_generates({"prompt": "hi"})
        # urllib Request capitalizes header names; check case-insensitively.
        headers_lc = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(headers_lc.get("user-agent"), gemini_images._USER_AGENT)

    def test_aspect_ratio_appends_prompt_hint(self) -> None:
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            gemini_images.dispatch_image_generates(
                {"prompt": "a vista", "aspect_ratio": "16:9"},
            )
        body = json.loads(captured["body"].decode("utf-8"))
        text = body["contents"][0]["parts"][0]["text"]
        self.assertIn("16:9", text)
        self.assertIn("a vista", text)

    def test_style_appends_to_prompt(self) -> None:
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            gemini_images.dispatch_image_generates(
                {"prompt": "a cat", "style": "watercolor"},
            )
        body = json.loads(captured["body"].decode("utf-8"))
        text = body["contents"][0]["parts"][0]["text"]
        self.assertIn("watercolor", text)

    # -- Required-input validation --------------------------------------

    def test_missing_prompt_raises_missing_required_input(self) -> None:
        with self.assertRaises(CapabilityError) as ctx:
            gemini_images.dispatch_image_generates({})
        self.assertEqual(ctx.exception.code, "missing_required_input")

    def test_empty_prompt_raises_missing_required_input(self) -> None:
        with self.assertRaises(CapabilityError) as ctx:
            gemini_images.dispatch_image_generates({"prompt": "   "})
        self.assertEqual(ctx.exception.code, "missing_required_input")

    # -- Response-body taxonomy (HTTP 200 with safety blocks) -----------

    def test_prompt_feedback_block_reason_maps_to_prompt_rejected(self) -> None:
        captured: dict = {}
        block_body = json.dumps(
            {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, response_bytes=block_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "prompt_rejected")

    def test_empty_candidates_maps_to_prompt_rejected(self) -> None:
        """Silent rejection — Gemini returns 200 with no candidates and
        no blockReason. Must classify as ``prompt_rejected`` so the
        §5.8.1 Slot-2 fallback chain advances."""
        captured: dict = {}
        empty_body = json.dumps({"candidates": []}).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, response_bytes=empty_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "prompt_rejected")

    def test_finish_reason_safety_without_image_maps_to_prompt_rejected(self) -> None:
        captured: dict = {}
        safety_body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "I can't generate that."}], "role": "model"},
                        "finishReason": "SAFETY",
                        "index": 0,
                    }
                ]
            }
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, response_bytes=safety_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "prompt_rejected")

    def test_response_with_only_text_part_no_image_maps_to_handler_failed(self) -> None:
        """Normal STOP finish but no inlineData = handler_failed.
        Distinct from a safety block — the model just gave text back."""
        captured: dict = {}
        text_only_body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Here is your image: ..."}], "role": "model"},
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ]
            }
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, response_bytes=text_only_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "handler_failed")

    def test_non_json_response_maps_to_handler_failed(self) -> None:
        captured: dict = {}
        garbage = b"<html>not json</html>"
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, response_bytes=garbage),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "handler_failed")

    # -- HTTP-error taxonomy --------------------------------------------

    def test_http_400_safety_body_maps_to_prompt_rejected(self) -> None:
        captured: dict = {}
        err_body = json.dumps(
            {"error": {"code": 400, "message": "The prompt was blocked due to safety violations.", "status": "INVALID_ARGUMENT"}}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, status_code=400, error_body=err_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "prompt_rejected")

    def test_http_400_generic_maps_to_handler_failed(self) -> None:
        captured: dict = {}
        err_body = json.dumps(
            {"error": {"code": 400, "message": "Malformed contents array.", "status": "INVALID_ARGUMENT"}}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, status_code=400, error_body=err_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "handler_failed")

    def test_http_401_maps_to_model_unavailable(self) -> None:
        captured: dict = {}
        err_body = json.dumps(
            {"error": {"code": 401, "message": "API key not valid", "status": "UNAUTHENTICATED"}}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, status_code=401, error_body=err_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "model_unavailable")

    def test_http_403_maps_to_model_unavailable(self) -> None:
        captured: dict = {}
        err_body = json.dumps(
            {"error": {"code": 403, "message": "Permission denied", "status": "PERMISSION_DENIED"}}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, status_code=403, error_body=err_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "model_unavailable")

    def test_http_429_maps_to_quota_exceeded(self) -> None:
        captured: dict = {}
        err_body = json.dumps(
            {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, status_code=429, error_body=err_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "quota_exceeded")

    def test_http_500_maps_to_model_unavailable(self) -> None:
        captured: dict = {}
        err_body = json.dumps(
            {"error": {"code": 500, "message": "Internal", "status": "INTERNAL"}}
        ).encode("utf-8")
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, status_code=500, error_body=err_body),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "model_unavailable")

    def test_network_urlerror_maps_to_model_unavailable(self) -> None:
        captured: dict = {}
        with mock.patch.object(
            gemini_images.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured, network_error=True),
        ):
            with self.assertRaises(CapabilityError) as ctx:
                gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "model_unavailable")

    # -- Auth failure ---------------------------------------------------

    def test_missing_api_key_raises_model_unavailable(self) -> None:
        """Stop the per-test patcher so the real _get_api_key runs, then
        force both env and keyring to return empty."""
        self._patcher.stop()
        # Re-stop on cleanup is a no-op; the addCleanup we registered is
        # already harmless.

        def _no_key(*args, **kwargs):
            return ""

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with mock.patch("keyring.get_password", side_effect=_no_key):
                with self.assertRaises(CapabilityError) as ctx:
                    gemini_images.dispatch_image_generates({"prompt": "x"})
        self.assertEqual(ctx.exception.code, "model_unavailable")
        # Restart the patcher so addCleanup's stop() is idempotent.
        self._patcher = mock.patch.object(
            gemini_images, "_get_api_key", return_value=self.API_KEY,
        )
        self._patcher.start()


# ---------------------------------------------------------------------------
# Live call (opt-in)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.environ.get("ORA_LIVE_GEMINI_IMAGES") == "1",
    "Live Gemini call disabled (set ORA_LIVE_GEMINI_IMAGES=1 to enable).",
)
class GeminiImageDispatchLiveTests(unittest.TestCase):
    """Single live call to verify wire format end to end. Off by default
    so the test run never costs money or hangs on a missing key."""

    def test_live_image_generates_returns_image_bytes(self) -> None:
        registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())
        gemini_images.register(registry)
        result = registry.invoke(
            "image_generates",
            {"prompt": "a small blue circle on a white background, minimalist", "aspect_ratio": "1:1"},
        )
        self.assertIsInstance(result.output, (bytes, bytearray))
        self.assertGreater(len(result.output), 1024)
        # PNG magic.
        self.assertTrue(result.output.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
