#!/usr/bin/env python3
"""OpenAI image API integration tests.

Covers the §13.3 test criterion: "Live call to each integrated endpoint
with a benign payload; verify successful output and correct slot
dispatch." Live calls are gated behind ``ORA_LIVE_OPENAI_IMAGES=1`` so
the default test run uses mocked OpenAI responses (the live call costs
money and requires a configured key).

DALL-E 2 and DALL-E 3 bindings were removed 2026-05-12 following
OpenAI's same-day deprecation announcement; the surviving binding is
gpt-image-1 against ``image_generates``.

Three test classes:

* ``OpenAIImageRegistrationTests``  — module-load registration plumbing.
* ``OpenAIImageDispatchMockedTests`` — mocked SDK responses, validates
  output shape + error mapping for each slot's documented common errors.
* ``OpenAIImageDispatchLiveTests``  — live OpenAI call, single benign
  payload, opt-in via env var.

Run::

    /opt/homebrew/bin/python3 -m pytest ~/ora/orchestrator/tests -q

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
    """Minimal capabilities dict declaring the slots openai_images fulfills.

    Under the 2026-05-12 slot-separation architecture, gpt-image-1 binds
    against both `image_generates` (news / illustration) and
    `image_generates_cartoon` (Hector cartoons). Both slots have identical
    input contracts so the stub mirrors the same shape for both."""
    slot_def = {
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
    }
    return {
        "_schema_version": 1,
        "slots": {
            "image_generates": {"name": "image_generates", **slot_def},
            "image_generates_cartoon": {"name": "image_generates_cartoon", **slot_def},
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
    """Module-load registration binds the image_generates slot correctly."""

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())

    def test_register_binds_image_generates_slot(self) -> None:
        openai_images.register(self.registry)
        self.assertIn(
            "openai:gpt-image-1",
            self.registry.providers_for("image_generates"),
        )

    def test_register_binds_image_generates_cartoon_slot(self) -> None:
        """Per the 2026-05-12 slot-separation architecture, gpt-image-1 is
        the publisher-chosen Slot 1 for the cartoon path too (image quality
        over the LoRA's spec-compliance, with the LoRA as the fallback)."""
        openai_images.register(self.registry)
        self.assertIn(
            "openai:gpt-image-1",
            self.registry.providers_for("image_generates_cartoon"),
        )

    def test_every_model_registers_under_the_slot_config_id_format(self) -> None:
        """Provider ids are ``openai:<model_id>``, one per model.

        Until 2026-05-22 this module registered a single provider whose id was
        the bare ``openai-gpt-image-1``, and this test pinned that string as
        "what routing-config.json references as preferred". Commit 8990cb5d
        stopped the dispatcher assuming any one model: register() now binds
        every model in OPENAI_IMAGE_MODELS under ``openai:<model_id>`` so slot
        config can route to a specific one. That id format IS the coupling to
        routing-config now, so it is what this test holds.
        """
        openai_images.register(self.registry)
        registered = set(self.registry.providers_for("image_generates"))
        for model_id in openai_images.OPENAI_IMAGE_MODELS:
            self.assertIn(f"openai:{model_id}", registered)

    def test_register_twice_on_one_registry_neither_duplicates_nor_raises(self) -> None:
        """``register()`` must be idempotent per registry object.

        ``register_with_default_registry()`` relies on this: it registers
        against every freshly loaded registry, so a re-register on the
        same object must be harmless. ``register_provider`` replaces the
        handler for an existing provider id and guards the slot's
        provider list against duplicate appends.
        """
        openai_images.register(self.registry)
        first = list(self.registry.providers_for("image_generates"))

        # Must not raise, and must not grow the provider list.
        openai_images.register(self.registry)
        openai_images.register(self.registry)
        after = list(self.registry.providers_for("image_generates"))

        self.assertEqual(first, after)
        self.assertEqual(len(after), len(set(after)), f"duplicate providers: {after}")

    def test_every_default_registry_call_binds_providers(self) -> None:
        """Successive calls must EACH return a registry with providers bound.

        ``capability_registry.load_registry()`` constructs a new registry
        on every call — it does not memoise. A module-level
        "already registered" latch therefore left the second and every
        later caller holding a registry with none of this module's
        providers bound, silently dropping the OpenAI chain for both
        image-generation slots. Regression guard for that latch.
        """
        built: list[CapabilityRegistry] = []

        def _fresh_registry() -> CapabilityRegistry:
            reg = CapabilityRegistry(config_dict=_stub_capabilities_dict())
            built.append(reg)
            return reg

        with patch.object(openai_images, "load_registry", _fresh_registry):
            first = openai_images.register_with_default_registry()
            second = openai_images.register_with_default_registry()

        # Guard the premise: the loader really did hand back two distinct
        # registries, so the assertions below are not vacuous.
        self.assertEqual(len(built), 2)
        self.assertIsNot(first, second)

        for call_no, registry in ((1, first), (2, second)):
            for slot in ("image_generates", "image_generates_cartoon"):
                with self.subTest(call=call_no, slot=slot):
                    self.assertIn(
                        "openai:gpt-image-1",
                        registry.providers_for(slot),
                        f"call {call_no} returned a registry with no OpenAI "
                        f"provider bound to {slot}",
                    )
                    self.assertIsNotNone(
                        registry.resolve_provider(slot),
                        f"call {call_no} returned a registry that cannot "
                        f"resolve a provider for {slot}",
                    )


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
        self.assertEqual(result.provider_id, "openai:gpt-image-1")

        # The dispatcher should have called images.generate with our prompt
        # and the size derived from the default 1:1 aspect ratio. gpt-image-1
        # rejects ``response_format`` — verify we don't pass it.
        kwargs = fake_client.images.generate.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-image-1")
        self.assertEqual(kwargs["prompt"], "a calm lake")
        self.assertEqual(kwargs["size"], "1024x1024")
        self.assertEqual(kwargs["n"], 1)
        self.assertNotIn("response_format", kwargs)

    def test_image_generates_aspect_ratio_translates_to_gpt_size(self) -> None:
        """gpt-image-1 accepts 1024×1024 / 1024×1536 / 1536×1024 / auto.
        16:9 must map to gpt-image-1's 1536×1024 landscape."""
        fake_client = MagicMock()
        fake_client.images.generate.return_value = _fake_openai_image_response(self.PNG_PAYLOAD)
        with patch.object(openai_images, "_get_client", return_value=fake_client):
            self.registry.invoke(
                "image_generates",
                {"prompt": "a wide vista", "aspect_ratio": "16:9"},
            )
        kwargs = fake_client.images.generate.call_args.kwargs
        self.assertEqual(kwargs["size"], "1536x1024")
        self.assertEqual(kwargs["model"], "gpt-image-1")

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
