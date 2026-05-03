#!/usr/bin/env python3
"""WP-7.3.2b — Stability AI integration tests.

Test criterion (per §13.3): "Live call to each integrated endpoint with
a benign payload; verify successful output and correct slot dispatch."
This file runs in two modes:

  * **Mocked mode (default).** No keychain entry → all three endpoints
    are exercised against a stubbed ``urllib.request.urlopen`` that
    returns a small fake PNG payload. Verifies request shape, slot
    dispatch through the registry, and error-translation paths.

  * **Live mode.** When the env var ``ORA_STABILITY_LIVE`` is set
    *and* a key is present at keyring service ``ora-stability``
    account ``api-key``, the live integration is exercised against
    the real Stability v2beta API with the smallest-payload calls
    possible (1:1 aspect, single direction outpaint, default upscale).
    Skips otherwise.

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_stability_integration -v
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from capability_registry import (  # noqa: E402
    CapabilityError,
    CapabilityRegistry,
    load_registry,
)
from integrations import stability  # noqa: E402


# ---------------------------------------------------------------------------
# A 1×1 transparent PNG, the smallest valid PNG payload. Used as both
# the fake server response and as test image input for outpaint/upscale.
# ---------------------------------------------------------------------------
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xfc\xff\xff?\x00\x05\xfe\x02\xfe\xa3"
    b"\xb1\x83\xa3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _fake_urlopen_factory(
    captured: dict[str, object],
    response_bytes: bytes = TINY_PNG,
    status_code: int = 200,
    error_body: bytes | None = None,
):
    """Build a urlopen replacement that captures the outgoing request
    and returns ``response_bytes`` (or raises HTTPError when
    ``status_code`` >= 400)."""

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
        if status_code >= 400:
            import urllib.error
            err = urllib.error.HTTPError(
                request.full_url,
                status_code,
                "Bad Request",
                hdrs=request.headers,
                fp=io.BytesIO(error_body or b""),
            )
            raise err
        return _FakeResponse(response_bytes)

    return _fake_urlopen


# ---------------------------------------------------------------------------
# Mocked-mode tests — always run.
# ---------------------------------------------------------------------------

class StabilityDispatcherMockedTests(unittest.TestCase):
    """Direct dispatcher exercises with mocked HTTP."""

    API_KEY = "sk-test-stability-1234"

    def test_image_generates_basic_call_shape(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            out = stability.dispatch_image_generates(
                prompt="a small red cube on a white background",
                aspect_ratio="1:1",
                api_key=self.API_KEY,
            )
        self.assertEqual(out, TINY_PNG)
        self.assertIn("/v2beta/stable-image/generate/sd3", captured["url"])
        self.assertEqual(
            captured["headers"]["Authorization"],
            f"Bearer {self.API_KEY}",
        )
        self.assertIn(b'name="prompt"', captured["body"])
        self.assertIn(b"a small red cube", captured["body"])
        self.assertIn(b'name="aspect_ratio"', captured["body"])
        self.assertIn(b"1:1", captured["body"])
        self.assertIn(b'name="model"', captured["body"])
        self.assertIn(b"sd3-large", captured["body"])

    def test_image_generates_appends_style(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            stability.dispatch_image_generates(
                prompt="cat",
                style="oil painting",
                api_key=self.API_KEY,
            )
        # Composite prompt joined with comma.
        self.assertIn(b"cat, oil painting", captured["body"])

    def test_image_generates_empty_prompt_raises(self):
        with self.assertRaises(CapabilityError) as cm:
            stability.dispatch_image_generates(prompt="   ", api_key="x")
        self.assertEqual(cm.exception.code, "prompt_rejected")

    def test_image_outpaints_direction_validation(self):
        with self.assertRaises(CapabilityError) as cm:
            stability.dispatch_image_outpaints(
                image=TINY_PNG,
                directions=[],
                prompt="extend please",
                api_key="x",
            )
        self.assertEqual(cm.exception.code, "direction_invalid")

        with self.assertRaises(CapabilityError) as cm:
            stability.dispatch_image_outpaints(
                image=TINY_PNG,
                directions=["upward"],
                prompt="extend please",
                api_key="x",
            )
        self.assertEqual(cm.exception.code, "direction_invalid")

    def test_image_outpaints_request_shape(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            out = stability.dispatch_image_outpaints(
                image=TINY_PNG,
                directions=["right", "bottom"],
                prompt="more landscape",
                pixels_per_direction=256,
                api_key=self.API_KEY,
            )
        self.assertEqual(out, TINY_PNG)
        self.assertIn(
            "/v2beta/stable-image/edit/outpaint", captured["url"]
        )
        self.assertIn(b'name="image"', captured["body"])
        self.assertIn(b'name="right"', captured["body"])
        self.assertIn(b"256", captured["body"])
        self.assertIn(b'name="bottom"', captured["body"])

    def test_image_upscales_request_shape(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            out = stability.dispatch_image_upscales(
                image=TINY_PNG,
                scale_factor=2.0,
                api_key=self.API_KEY,
            )
        self.assertEqual(out, TINY_PNG)
        self.assertIn(
            "/v2beta/stable-image/upscale/conservative", captured["url"]
        )
        # Default neutral prompt is sent.
        self.assertIn(b"high detail", captured["body"])

    def test_image_upscales_rejects_scale_lte_one(self):
        with self.assertRaises(CapabilityError) as cm:
            stability.dispatch_image_upscales(
                image=TINY_PNG, scale_factor=1.0, api_key="x"
            )
        self.assertEqual(cm.exception.code, "handler_failed")

    def test_image_input_path_is_read(self):
        # Exercise _coerce_image_bytes path branch.
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory({}),
        ):
            tmp = HERE / "_stability_tmp_input.png"
            tmp.write_bytes(TINY_PNG)
            try:
                stability.dispatch_image_upscales(
                    image=str(tmp), scale_factor=2.0, api_key="key"
                )
            finally:
                tmp.unlink(missing_ok=True)

    def test_image_input_unsupported_type_raises(self):
        with self.assertRaises(CapabilityError) as cm:
            stability.dispatch_image_upscales(
                image=12345, scale_factor=2.0, api_key="key"
            )
        self.assertEqual(cm.exception.code, "handler_failed")


class StabilityErrorTranslationTests(unittest.TestCase):
    """HTTP error → slot common_errors mapping."""

    def test_401_translates_to_model_unavailable(self):
        captured: dict[str, object] = {}
        body = json.dumps(
            {"name": "unauthorized", "errors": ["bad key"]}
        ).encode()
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(
                captured, status_code=401, error_body=body
            ),
        ):
            with self.assertRaises(CapabilityError) as cm:
                stability.dispatch_image_generates(
                    prompt="x", api_key="key"
                )
        self.assertEqual(cm.exception.code, "model_unavailable")

    def test_429_on_generates_translates_to_quota_exceeded(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(
                captured,
                status_code=429,
                error_body=b'{"name":"too_many_requests","errors":["slow"]}',
            ),
        ):
            with self.assertRaises(CapabilityError) as cm:
                stability.dispatch_image_generates(
                    prompt="x", api_key="key"
                )
        self.assertEqual(cm.exception.code, "quota_exceeded")

    def test_400_content_moderation_translates_to_prompt_rejected(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(
                captured,
                status_code=400,
                error_body=b'{"name":"content_moderation","errors":["blocked"]}',
            ),
        ):
            with self.assertRaises(CapabilityError) as cm:
                stability.dispatch_image_generates(
                    prompt="bad prompt", api_key="key"
                )
        self.assertEqual(cm.exception.code, "prompt_rejected")

    def test_413_on_upscale_translates_to_image_too_large(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(
                captured,
                status_code=413,
                error_body=b'{"name":"payload_too_large","errors":["big"]}',
            ),
        ):
            with self.assertRaises(CapabilityError) as cm:
                stability.dispatch_image_upscales(
                    image=TINY_PNG, scale_factor=2.0, api_key="key"
                )
        self.assertEqual(cm.exception.code, "image_too_large")

    def test_400_image_too_small_translates(self):
        captured: dict[str, object] = {}
        with mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(
                captured,
                status_code=400,
                error_body=b'{"name":"image_too_small","errors":["min 64"]}',
            ),
        ):
            with self.assertRaises(CapabilityError) as cm:
                stability.dispatch_image_upscales(
                    image=TINY_PNG, scale_factor=2.0, api_key="key"
                )
        self.assertEqual(cm.exception.code, "image_too_small")


class StabilityRegistryDispatchTests(unittest.TestCase):
    """End-to-end: registry receives an invoke call and routes it
    through the registered Stability handler."""

    def setUp(self):
        # Build a registry from the actual capabilities.json + a
        # routing-config that names stability as preferred for all
        # three slots (mirrors what register() lands in production
        # routing-config.json after WP-7.3.2b's edits).
        self.registry = CapabilityRegistry(
            config_path=WORKSPACE / "config" / "capabilities.json",
            routing_config={
                "slots": {
                    "image_generates": {
                        "preferred": "stability",
                        "fallback": [],
                    },
                    "image_outpaints": {
                        "preferred": "stability",
                        "fallback": [],
                    },
                    "image_upscales": {
                        "preferred": "stability",
                        "fallback": [],
                    },
                }
            },
        )
        registered = stability.register(self.registry)
        self.assertEqual(
            sorted(registered),
            ["image_generates", "image_outpaints", "image_upscales"],
        )

    def _run_through_registry(self, slot, inputs):
        captured: dict[str, object] = {}
        # Patch _get_api_key so the test doesn't need a Keychain entry.
        with mock.patch.object(
            stability,
            "_get_api_key",
            return_value="sk-fake",
        ), mock.patch.object(
            stability.urllib.request,
            "urlopen",
            _fake_urlopen_factory(captured),
        ):
            result = self.registry.invoke(slot, inputs)
        return result, captured

    def test_image_generates_via_registry(self):
        result, captured = self._run_through_registry(
            "image_generates",
            {"prompt": "a small green tree", "aspect_ratio": "1:1"},
        )
        self.assertEqual(result.provider_id, "stability")
        self.assertEqual(result.output, TINY_PNG)
        self.assertIn("/v2beta/stable-image/generate/sd3", captured["url"])

    def test_image_outpaints_via_registry(self):
        result, captured = self._run_through_registry(
            "image_outpaints",
            {
                "image": TINY_PNG,
                "directions": ["top"],
                "prompt": "more sky",
            },
        )
        self.assertEqual(result.provider_id, "stability")
        self.assertEqual(result.output, TINY_PNG)
        self.assertIn(
            "/v2beta/stable-image/edit/outpaint", captured["url"]
        )

    def test_image_upscales_via_registry(self):
        result, captured = self._run_through_registry(
            "image_upscales",
            {"image": TINY_PNG, "scale_factor": 2.0},
        )
        self.assertEqual(result.provider_id, "stability")
        self.assertEqual(result.output, TINY_PNG)
        self.assertIn(
            "/v2beta/stable-image/upscale/conservative", captured["url"]
        )


class StabilityKeyringTests(unittest.TestCase):
    """Verify the missing-key path surfaces ``model_unavailable``."""

    def test_missing_key_raises_model_unavailable(self):
        with mock.patch("keyring.get_password", return_value=None):
            with self.assertRaises(CapabilityError) as cm:
                stability._get_api_key()
        self.assertEqual(cm.exception.code, "model_unavailable")
        self.assertIn(
            "API Key Acquisition", str(cm.exception)
        )


# ---------------------------------------------------------------------------
# Live-mode tests — opt-in via env var + key presence.
# ---------------------------------------------------------------------------

def _live_enabled() -> bool:
    if not os.environ.get("ORA_STABILITY_LIVE"):
        return False
    try:
        import keyring  # noqa: WPS433
    except ImportError:
        return False
    return bool(
        keyring.get_password(
            stability.KEYRING_SERVICE, stability.KEYRING_ACCOUNT
        )
    )


@unittest.skipUnless(
    _live_enabled(),
    "Live Stability calls disabled (set ORA_STABILITY_LIVE=1 and "
    "store key at keyring service 'ora-stability' account 'api-key' "
    "to enable).",
)
class StabilityLiveTests(unittest.TestCase):
    """Smallest-payload live calls. Single test per endpoint."""

    def test_image_generates_live(self):
        out = stability.dispatch_image_generates(
            prompt="a single red dot on white background",
            aspect_ratio="1:1",
        )
        self.assertIsInstance(out, bytes)
        self.assertGreater(len(out), 100, "Live API returned empty")
        self.assertEqual(out[:8], b"\x89PNG\r\n\x1a\n")

    def test_image_outpaints_live(self):
        # Use a generated image to keep it benign.
        seed = stability.dispatch_image_generates(
            prompt="solid blue square", aspect_ratio="1:1"
        )
        out = stability.dispatch_image_outpaints(
            image=seed,
            directions=["right"],
            prompt="extend the blue",
            pixels_per_direction=256,
        )
        self.assertIsInstance(out, bytes)
        self.assertGreater(len(out), 100)

    def test_image_upscales_live(self):
        seed = stability.dispatch_image_generates(
            prompt="solid green square", aspect_ratio="1:1"
        )
        out = stability.dispatch_image_upscales(
            image=seed, scale_factor=2.0
        )
        self.assertIsInstance(out, bytes)
        self.assertGreater(len(out), 100)


if __name__ == "__main__":
    unittest.main()
