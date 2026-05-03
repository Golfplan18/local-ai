#!/usr/bin/env python3
"""WP-7.3.2a — OpenAI image API integration tests.

Covers the §13.3 test criterion: "Live call to each integrated endpoint
with a benign payload; verify successful output and correct slot
dispatch." Live calls are gated behind ``ORA_LIVE_OPENAI_IMAGES=1`` so
the default test run uses mocked OpenAI responses (the live call costs
money and requires a configured key).

Three test classes:

* ``OpenAIImageRegistrationTests``  — module-load registration plumbing.
* ``OpenAIImageDispatchMockedTests`` — mocked SDK responses, validates
  output shape + error mapping for each slot's documented common errors.
* ``OpenAIImageDispatchLiveTests``  — live OpenAI call, single benign
  payload, opt-in via env var.

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

This file uses stdlib ``unittest`` to match the rest of the suite.
"""
from __future__ import annotations

import base64
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from capability_registry import CapabilityError, CapabilityRegistry  # noqa: E402

from integrations import openai_images  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _stub_capabilities_dict() -> dict:
    """Minimal capabilities dict declaring only the two slots openai_images
    fulfills. Keeps the unit tests independent of the full slot catalog."""
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
            "image_edits": {
                "name": "image_edits",
                "summary": "Edit.",
                "required_inputs": [
                    {"name": "image", "type": "image-ref", "description": "x"},
                    {"name": "mask", "type": "mask", "description": "x"},
                    {"name": "prompt", "type": "text", "description": "x"},
                ],
                "optional_inputs": [
                    {"name": "strength", "type": "float", "default": 0.75},
                ],
                "output": {"type": "image-bytes"},
                "execution_pattern": "sync",
                "common_errors": [
                    {"code": "no_mask_drawn"},
                    {"code": "no_image_selected"},
                    {"code": "mask_invalid"},
                ],
            },
        },
    }


def _fake_openai_image_response(b64_payload: bytes) -> MagicMock:
    """Build a MagicMock matching the openai SDK's images response shape.

    The real ``client.images.generate`` returns an object with a ``data``
    list of items each having a ``b64_json`` attribute; we replicate
    just enough surface for the dispatcher to read."""
    response = MagicMock()
    item = MagicMock()
    item.b64_json = base64.b64encode(b64_payload).decode("ascii")
    response.data = [item]
    return response


# ---------------------------------------------------------------------------
# Registration plumbing
# ---------------------------------------------------------------------------

class OpenAIImageRegistrationTests(unittest.TestCase):
    """Module-load registration binds both slots correctly."""

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())

    def test_register_binds_both_slots(self) -> None:
        openai_images.register(self.registry)
        self.assertIn(
            openai_images.PROVIDER_IMAGE_GENERATES,
            self.registry.providers_for("image_generates"),
        )
        self.assertIn(
            openai_images.PROVIDER_IMAGE_EDITS,
            self.registry.providers_for("image_edits"),
        )

    def test_register_provider_constants_match_routing_config_preference(self) -> None:
        """The provider IDs match what routing-config.json now references
        as `preferred`. If this test fails, either openai_images.py or
        routing-config.json drifted."""
        # Hard-coded by the integration; routing-config.json must agree.
        self.assertEqual(openai_images.PROVIDER_IMAGE_GENERATES, "openai-dalle3")
        self.assertEqual(openai_images.PROVIDER_IMAGE_EDITS, "openai-dalle2")


# ---------------------------------------------------------------------------
# Mocked dispatch — no network
# ---------------------------------------------------------------------------

class OpenAIImageDispatchMockedTests(unittest.TestCase):
    """Validates wire format + error mapping with a stubbed openai client."""

    PNG_PAYLOAD = b"\x89PNG\r\n\x1a\nFAKE_BYTES_FOR_TEST"

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())
        openai_images.register(self.registry)

    # -- Success paths ---------------------------------------------------

    def test_image_generates_returns_decoded_bytes(self) -> None:
        fake_response = _fake_openai_image_response(self.PNG_PAYLOAD)
        fake_client = MagicMock()
        fake_client.images.generate.return_value = fake_response

        with patch.object(openai_images, "_get_client", return_value=fake_client):
            result = self.registry.invoke(
                "image_generates",
                {"prompt": "a calm lake"},
            )

        self.assertEqual(result.output, self.PNG_PAYLOAD)
        self.assertEqual(result.provider_id, "openai-dalle3")

        # The dispatcher should have called images.generate with our prompt
        # and the size derived from the default 1:1 aspect ratio.
        kwargs = fake_client.images.generate.call_args.kwargs
        self.assertEqual(kwargs["model"], openai_images.MODEL_IMAGE_GENERATES)
        self.assertEqual(kwargs["prompt"], "a calm lake")
        self.assertEqual(kwargs["size"], "1024x1024")
        self.assertEqual(kwargs["n"], 1)

    def test_image_generates_aspect_ratio_translates_to_size(self) -> None:
        fake_client = MagicMock()
        fake_client.images.generate.return_value = _fake_openai_image_response(self.PNG_PAYLOAD)
        with patch.object(openai_images, "_get_client", return_value=fake_client):
            self.registry.invoke(
                "image_generates",
                {"prompt": "a wide vista", "aspect_ratio": "16:9"},
            )
        self.assertEqual(
            fake_client.images.generate.call_args.kwargs["size"],
            "1792x1024",
        )

    def test_image_generates_style_appends_to_prompt(self) -> None:
        fake_client = MagicMock()
        fake_client.images.generate.return_value = _fake_openai_image_response(self.PNG_PAYLOAD)
        with patch.object(openai_images, "_get_client", return_value=fake_client):
            self.registry.invoke(
                "image_generates",
                {"prompt": "a cat", "style": "watercolor"},
            )
        self.assertEqual(
            fake_client.images.generate.call_args.kwargs["prompt"],
            "a cat, in the style of watercolor",
        )

    def test_image_edits_returns_decoded_bytes(self) -> None:
        fake_client = MagicMock()
        fake_client.images.edit.return_value = _fake_openai_image_response(self.PNG_PAYLOAD)

        with patch.object(openai_images, "_get_client", return_value=fake_client):
            result = self.registry.invoke(
                "image_edits",
                {
                    "image": b"FAKE_IMAGE_BYTES",
                    "mask": b"FAKE_MASK_BYTES",
                    "prompt": "add a hat",
                },
            )

        self.assertEqual(result.output, self.PNG_PAYLOAD)
        self.assertEqual(result.provider_id, "openai-dalle2")
        kwargs = fake_client.images.edit.call_args.kwargs
        self.assertEqual(kwargs["model"], openai_images.MODEL_IMAGE_EDITS)
        self.assertEqual(kwargs["prompt"], "add a hat")

    # -- Required-input validation --------------------------------------

    def test_image_edits_missing_image_raises_no_image_selected(self) -> None:
        # Bypass the registry's own pre-validation by calling the
        # dispatcher directly so the slot-specific code path runs.
        with self.assertRaises(CapabilityError) as ctx:
            openai_images.dispatch_image_edits(
                {"image": None, "mask": b"x", "prompt": "x"}
            )
        self.assertEqual(ctx.exception.code, "no_image_selected")

    def test_image_edits_missing_mask_raises_no_mask_drawn(self) -> None:
        with self.assertRaises(CapabilityError) as ctx:
            openai_images.dispatch_image_edits(
                {"image": b"x", "mask": None, "prompt": "x"}
            )
        self.assertEqual(ctx.exception.code, "no_mask_drawn")

    # -- Error translation ----------------------------------------------

    def test_content_policy_violation_maps_to_prompt_rejected(self) -> None:
        # Simulate the BadRequestError shape from the OpenAI SDK.
        class FakeBadRequest(Exception):
            pass

        FakeBadRequest.__name__ = "BadRequestError"
        exc = FakeBadRequest("Your request was rejected as a result of our safety system.")
        exc.body = {"error": {"code": "content_policy_violation"}}

        translated = openai_images._translate_openai_error(exc, slot="image_generates")
        self.assertEqual(translated.code, "prompt_rejected")
        self.assertEqual(translated.slot, "image_generates")

    def test_content_policy_via_message_only(self) -> None:
        """Even without ``error.code``, a content-policy phrase in the
        message routes to prompt_rejected — defensive fallback."""
        exc = Exception("blocked by our content policy")
        translated = openai_images._translate_openai_error(exc, slot="image_generates")
        self.assertEqual(translated.code, "prompt_rejected")

    def test_rate_limit_maps_to_quota_exceeded(self) -> None:
        class FakeRateLimitError(Exception):
            pass

        FakeRateLimitError.__name__ = "RateLimitError"
        exc = FakeRateLimitError("You exceeded your current quota")
        translated = openai_images._translate_openai_error(exc, slot="image_generates")
        self.assertEqual(translated.code, "quota_exceeded")

    def test_authentication_error_maps_to_model_unavailable(self) -> None:
        class FakeAuthError(Exception):
            pass

        FakeAuthError.__name__ = "AuthenticationError"
        exc = FakeAuthError("Invalid API key")
        translated = openai_images._translate_openai_error(exc, slot="image_generates")
        self.assertEqual(translated.code, "model_unavailable")

    def test_missing_api_key_raises_model_unavailable(self) -> None:
        # Force both env and keychain lookups to return nothing.
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False), \
             patch.object(openai_images, "_get_api_key", return_value=None):
            with self.assertRaises(CapabilityError) as ctx:
                openai_images._get_client()
            self.assertEqual(ctx.exception.code, "model_unavailable")

    # -- Slot dispatch surfaces translated errors -----------------------

    def test_dispatch_translates_sdk_exception_at_registry_layer(self) -> None:
        """The dispatcher should translate exceptions before they reach
        the registry, so callers see the slot-level code, not
        handler_failed."""
        class FakeRateLimitError(Exception):
            pass

        FakeRateLimitError.__name__ = "RateLimitError"
        fake_client = MagicMock()
        fake_client.images.generate.side_effect = FakeRateLimitError("rate limit")

        with patch.object(openai_images, "_get_client", return_value=fake_client):
            with self.assertRaises(CapabilityError) as ctx:
                self.registry.invoke("image_generates", {"prompt": "anything"})

        self.assertEqual(ctx.exception.code, "quota_exceeded")
        self.assertEqual(ctx.exception.slot, "image_generates")


# ---------------------------------------------------------------------------
# Live call (opt-in)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.environ.get("ORA_LIVE_OPENAI_IMAGES") == "1",
    "Live OpenAI call disabled (set ORA_LIVE_OPENAI_IMAGES=1 to enable).",
)
class OpenAIImageDispatchLiveTests(unittest.TestCase):
    """Single live call to verify wire format end to end. Off by default
    so the test run never costs money or hangs on a missing key."""

    def test_live_image_generates_returns_image_bytes(self) -> None:
        registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())
        openai_images.register(registry)
        result = registry.invoke(
            "image_generates",
            {"prompt": "a small red square on white background", "aspect_ratio": "1:1"},
        )
        self.assertIsInstance(result.output, (bytes, bytearray))
        self.assertGreater(len(result.output), 1024)
        # PNG magic.
        self.assertTrue(result.output.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
