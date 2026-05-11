#!/usr/bin/env python3
"""Capability registry fallback-chain tests.

Covers the runtime fallback machinery added to
``capability_registry.CapabilityRegistry.invoke()``:

  * When the preferred provider raises a fallback-triggering
    ``CapabilityError``, ``invoke()`` advances to the next provider in
    the routing-config chain.
  * The ``InvocationResult.attempts`` field records every provider
    tried (succeeded or failed) so callers can render telemetry.
  * On total chain exhaustion, the last ``CapabilityError`` is raised
    with ``.attempts`` populated.
  * Non-triggering error codes (input-validation, ``handler_failed``)
    do not advance the chain.
  * The per-slot ``fallback_on`` override in routing-config controls
    which error codes trigger fallback. ``[]`` disables fallback.
  * Explicit ``provider_id`` argument to ``invoke()`` disables fallback
    (the caller made a deliberate choice).
  * Missing routing-config → registration-order chain.

Built around mock handlers — no integration code, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from capability_registry import (  # noqa: E402
    CapabilityError,
    CapabilityRegistry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _capabilities_dict() -> dict:
    """Minimal capabilities dict declaring one slot with the standard
    common_errors taxonomy."""
    return {
        "_schema_version": 1,
        "slots": {
            "image_generates": {
                "name": "image_generates",
                "summary": "Generate.",
                "required_inputs": [
                    {"name": "prompt", "type": "text", "description": "x"}
                ],
                "optional_inputs": [],
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


def _routing_config(
    preferred: str | None = None,
    fallback: list[str] | None = None,
    fallback_on: list[str] | None | object = ...,
) -> dict:
    """Build a routing-config dict for the one slot.

    ``fallback_on=...`` (Ellipsis sentinel) means "omit the key";
    ``fallback_on=None`` means "explicit null" (treated same as omitted);
    ``fallback_on=[]`` means "fail-fast — never fall back."
    """
    slot_cfg: dict = {}
    if preferred is not None:
        slot_cfg["preferred"] = preferred
    if fallback is not None:
        slot_cfg["fallback"] = fallback
    if fallback_on is not ...:
        slot_cfg["fallback_on"] = fallback_on
    return {"slots": {"image_generates": slot_cfg}}


def _success_handler(image_bytes: bytes = b"\x89PNG-fake"):
    """Build a handler that returns the given bytes."""
    def handler(inputs):
        return image_bytes
    return handler


def _raising_handler(code: str, message: str = "test-failure"):
    """Build a handler that raises CapabilityError(code, message)."""
    def handler(inputs):
        raise CapabilityError(code, message, slot="image_generates")
    return handler


# ---------------------------------------------------------------------------
# Successful happy paths
# ---------------------------------------------------------------------------

class FallbackHappyPathTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2", "slot3"],
            ),
        )
        self.registry.register_provider("image_generates", "slot1", _success_handler(b"a"))
        self.registry.register_provider("image_generates", "slot2", _success_handler(b"b"))
        self.registry.register_provider("image_generates", "slot3", _success_handler(b"c"))

    def test_preferred_succeeds_returns_first_provider(self) -> None:
        result = self.registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(result.provider_id, "slot1")
        self.assertEqual(result.output, b"a")

    def test_preferred_succeeds_attempts_has_one_entry(self) -> None:
        result = self.registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0]["provider_id"], "slot1")
        self.assertTrue(result.attempts[0]["succeeded"])
        self.assertIsNone(result.attempts[0]["error_code"])

    def test_attempts_field_is_independent_per_call(self) -> None:
        r1 = self.registry.invoke("image_generates", {"prompt": "x"})
        r2 = self.registry.invoke("image_generates", {"prompt": "x"})
        # Different list instances — no shared mutable state across calls.
        self.assertIsNot(r1.attempts, r2.attempts)


# ---------------------------------------------------------------------------
# Fallback walks the chain on triggering codes
# ---------------------------------------------------------------------------

class FallbackChainWalkTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2", "slot3"],
            ),
        )

    def test_prompt_rejected_advances_to_next_provider(self) -> None:
        """§5.8.1 Slot 1 → Slot 2 moderation lottery."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        self.registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))
        self.registry.register_provider(
            "image_generates", "slot3", _success_handler(b"slot3-image"))

        result = self.registry.invoke("image_generates", {"prompt": "x"})

        self.assertEqual(result.provider_id, "slot2")
        self.assertEqual(result.output, b"slot2-image")
        # Two attempts: slot1 failed (prompt_rejected), slot2 succeeded.
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual(result.attempts[0]["provider_id"], "slot1")
        self.assertFalse(result.attempts[0]["succeeded"])
        self.assertEqual(result.attempts[0]["error_code"], "prompt_rejected")
        self.assertEqual(result.attempts[1]["provider_id"], "slot2")
        self.assertTrue(result.attempts[1]["succeeded"])

    def test_model_unavailable_advances_to_next_provider(self) -> None:
        """Missing API key on Slot 1 → try Slot 2."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("model_unavailable"))
        self.registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))
        self.registry.register_provider(
            "image_generates", "slot3", _success_handler())

        result = self.registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(result.provider_id, "slot2")
        self.assertEqual(len(result.attempts), 2)

    def test_quota_exceeded_advances_to_next_provider(self) -> None:
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("quota_exceeded"))
        self.registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        result = self.registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(result.provider_id, "slot2")

    def test_chain_walks_multiple_failures_until_success(self) -> None:
        """slot1 + slot2 both refuse, slot3 succeeds."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        self.registry.register_provider(
            "image_generates", "slot2", _raising_handler("model_unavailable"))
        self.registry.register_provider(
            "image_generates", "slot3", _success_handler(b"slot3-image"))

        result = self.registry.invoke("image_generates", {"prompt": "x"})

        self.assertEqual(result.provider_id, "slot3")
        self.assertEqual(result.output, b"slot3-image")
        self.assertEqual(len(result.attempts), 3)
        self.assertEqual(
            [a["provider_id"] for a in result.attempts],
            ["slot1", "slot2", "slot3"],
        )
        self.assertEqual(
            [a["succeeded"] for a in result.attempts],
            [False, False, True],
        )

    def test_attempts_order_matches_routing_config_chain(self) -> None:
        """Even when providers register in a different order, the chain
        walked respects routing-config's preferred + fallback order."""
        # Register in reverse so insertion-order is slot3, slot2, slot1.
        self.registry.register_provider(
            "image_generates", "slot3", _success_handler())
        self.registry.register_provider(
            "image_generates", "slot2", _raising_handler("prompt_rejected"))
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))

        result = self.registry.invoke("image_generates", {"prompt": "x"})
        # Routing-config says preferred=slot1, fallback=[slot2, slot3].
        self.assertEqual(
            [a["provider_id"] for a in result.attempts],
            ["slot1", "slot2", "slot3"],
        )


# ---------------------------------------------------------------------------
# Total chain exhaustion — last error wins, carries chain
# ---------------------------------------------------------------------------

class ChainExhaustionTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2"],
            ),
        )

    def test_all_providers_fail_raises_last_error(self) -> None:
        """When everything refuses, raise the last provider's error —
        that's the canonical 'no one could fulfill this' signal."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected", "slot1 refused"))
        self.registry.register_provider(
            "image_generates", "slot2", _raising_handler("model_unavailable", "slot2 down"))

        with self.assertRaises(CapabilityError) as ctx:
            self.registry.invoke("image_generates", {"prompt": "x"})

        # The LAST error's code wins.
        self.assertEqual(ctx.exception.code, "model_unavailable")
        self.assertIn("slot2 down", str(ctx.exception))

    def test_exhausted_chain_error_carries_attempts(self) -> None:
        """The raised error must carry the full attempts chain so the
        caller can log/render the telemetry."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        self.registry.register_provider(
            "image_generates", "slot2", _raising_handler("model_unavailable"))

        with self.assertRaises(CapabilityError) as ctx:
            self.registry.invoke("image_generates", {"prompt": "x"})

        self.assertEqual(len(ctx.exception.attempts), 2)
        self.assertEqual(
            [a["error_code"] for a in ctx.exception.attempts],
            ["prompt_rejected", "model_unavailable"],
        )
        # Neither attempt succeeded.
        self.assertFalse(any(a["succeeded"] for a in ctx.exception.attempts))


# ---------------------------------------------------------------------------
# Non-triggering codes do not advance the chain
# ---------------------------------------------------------------------------

class NonTriggeringCodeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2"],
            ),
        )

    def test_handler_failed_does_not_advance(self) -> None:
        """handler_failed = generic catch-all; auto-retry would mask the
        underlying issue. Surface immediately."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("handler_failed"))
        # slot2 would succeed if reached — but it shouldn't be reached.
        slot2_calls = {"count": 0}

        def slot2_handler(inputs):
            slot2_calls["count"] += 1
            return b"slot2-image"

        self.registry.register_provider("image_generates", "slot2", slot2_handler)

        with self.assertRaises(CapabilityError) as ctx:
            self.registry.invoke("image_generates", {"prompt": "x"})

        self.assertEqual(ctx.exception.code, "handler_failed")
        self.assertEqual(slot2_calls["count"], 0)
        # Attempts chain shows only slot1.
        self.assertEqual(len(ctx.exception.attempts), 1)

    def test_input_validation_error_does_not_invoke_any_provider(self) -> None:
        """Missing required input fails before any handler runs."""
        self.registry.register_provider("image_generates", "slot1", _success_handler())
        self.registry.register_provider("image_generates", "slot2", _success_handler())

        with self.assertRaises(CapabilityError) as ctx:
            self.registry.invoke("image_generates", {})  # no prompt

        self.assertEqual(ctx.exception.code, "missing_required_input")
        # Input-validation errors don't populate attempts — nothing was tried.
        self.assertEqual(ctx.exception.attempts, [])


# ---------------------------------------------------------------------------
# Per-slot fallback_on override
# ---------------------------------------------------------------------------

class PerSlotFallbackOverrideTests(unittest.TestCase):

    def _build_registry(self, fallback_on) -> CapabilityRegistry:
        rc = _routing_config(
            preferred="slot1",
            fallback=["slot2"],
            fallback_on=fallback_on,
        )
        return CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=rc,
        )

    def test_empty_fallback_on_disables_fallback_entirely(self) -> None:
        """``fallback_on: []`` means fail-fast — even prompt_rejected
        surfaces immediately. Required for video_generates / style_trains
        where silent retry could double-charge."""
        registry = self._build_registry(fallback_on=[])
        registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        with self.assertRaises(CapabilityError) as ctx:
            registry.invoke("image_generates", {"prompt": "x"})

        self.assertEqual(ctx.exception.code, "prompt_rejected")
        # Only slot1 was tried.
        self.assertEqual(len(ctx.exception.attempts), 1)

    def test_custom_fallback_on_narrows_trigger_set(self) -> None:
        """A slot can opt INTO advancing only on model_unavailable — so
        prompt_rejected surfaces (the prompt is the prompt, retrying
        won't help) but a missing key tries the next provider."""
        registry = self._build_registry(fallback_on=["model_unavailable"])
        registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        with self.assertRaises(CapabilityError) as ctx:
            registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(ctx.exception.code, "prompt_rejected")

        # But model_unavailable still advances.
        registry2 = self._build_registry(fallback_on=["model_unavailable"])
        registry2.register_provider(
            "image_generates", "slot1", _raising_handler("model_unavailable"))
        registry2.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))
        result = registry2.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(result.provider_id, "slot2")

    def test_omitted_fallback_on_uses_default_set(self) -> None:
        """Missing fallback_on key → default {prompt_rejected,
        model_unavailable, quota_exceeded}."""
        registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2"],
                # fallback_on omitted via the Ellipsis sentinel default.
            ),
        )
        registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        result = registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(result.provider_id, "slot2")

    def test_fallback_triggering_codes_helper_returns_correct_set(self) -> None:
        """The public helper that exposes the resolved set, used by
        outside code (e.g., debugging tools)."""
        default = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(preferred="slot1"),
        )
        self.assertEqual(
            default.fallback_triggering_codes("image_generates"),
            frozenset({"prompt_rejected", "model_unavailable", "quota_exceeded"}),
        )

        empty = self._build_registry(fallback_on=[])
        self.assertEqual(empty.fallback_triggering_codes("image_generates"), frozenset())

        custom = self._build_registry(fallback_on=["prompt_rejected"])
        self.assertEqual(
            custom.fallback_triggering_codes("image_generates"),
            frozenset({"prompt_rejected"}),
        )


# ---------------------------------------------------------------------------
# Explicit provider_id disables fallback
# ---------------------------------------------------------------------------

class ExplicitProviderIdTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2"],
            ),
        )

    def test_explicit_provider_id_disables_fallback_on_failure(self) -> None:
        """When the caller names a provider, fallback is off — the
        caller is making a deliberate choice (testing or debugging)."""
        self.registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        self.registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        with self.assertRaises(CapabilityError) as ctx:
            self.registry.invoke(
                "image_generates",
                {"prompt": "x"},
                provider_id="slot1",
            )
        self.assertEqual(ctx.exception.code, "prompt_rejected")
        self.assertEqual(len(ctx.exception.attempts), 1)
        self.assertEqual(ctx.exception.attempts[0]["provider_id"], "slot1")

    def test_explicit_provider_id_success_records_single_attempt(self) -> None:
        self.registry.register_provider(
            "image_generates", "slot1", _success_handler(b"slot1-image"))
        self.registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        result = self.registry.invoke(
            "image_generates",
            {"prompt": "x"},
            provider_id="slot2",
        )
        self.assertEqual(result.provider_id, "slot2")
        self.assertEqual(result.output, b"slot2-image")
        self.assertEqual(len(result.attempts), 1)

    def test_explicit_provider_id_must_be_registered(self) -> None:
        self.registry.register_provider(
            "image_generates", "slot1", _success_handler())
        with self.assertRaises(CapabilityError) as ctx:
            self.registry.invoke(
                "image_generates",
                {"prompt": "x"},
                provider_id="not-registered",
            )
        self.assertEqual(ctx.exception.code, "provider_not_found")


# ---------------------------------------------------------------------------
# Missing routing-config → registration-order chain
# ---------------------------------------------------------------------------

class NoRoutingConfigTests(unittest.TestCase):

    def test_no_routing_config_uses_registration_order(self) -> None:
        """With no routing-config, the chain is the registration order
        — first-registered tried first, with fallback enabled."""
        registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=None,
        )
        registry.register_provider(
            "image_generates", "slot1", _raising_handler("prompt_rejected"))
        registry.register_provider(
            "image_generates", "slot2", _success_handler(b"slot2-image"))

        result = registry.invoke("image_generates", {"prompt": "x"})
        # Defaults still trigger fallback even without routing-config.
        self.assertEqual(result.provider_id, "slot2")

    def test_no_routing_config_single_provider_no_fallback(self) -> None:
        registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=None,
        )
        registry.register_provider(
            "image_generates", "slot1", _success_handler())
        result = registry.invoke("image_generates", {"prompt": "x"})
        self.assertEqual(result.provider_id, "slot1")
        self.assertEqual(len(result.attempts), 1)


# ---------------------------------------------------------------------------
# resolve_provider_chain — direct exercise
# ---------------------------------------------------------------------------

class ResolveProviderChainTests(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(
            config_dict=_capabilities_dict(),
            routing_config=_routing_config(
                preferred="slot1",
                fallback=["slot2", "slot3", "slot1"],  # deliberate dup of preferred
            ),
        )

    def test_chain_deduplicates_preferred_appearing_in_fallback(self) -> None:
        for name in ("slot1", "slot2", "slot3"):
            self.registry.register_provider("image_generates", name, _success_handler())
        chain = self.registry.resolve_provider_chain("image_generates")
        self.assertEqual(chain, ["slot1", "slot2", "slot3"])

    def test_chain_skips_unregistered_providers(self) -> None:
        """If routing-config names a provider that hasn't registered,
        it's silently skipped — the slot stays usable with whatever
        providers ARE registered."""
        self.registry.register_provider("image_generates", "slot1", _success_handler())
        # slot2 + slot3 deliberately unregistered.
        chain = self.registry.resolve_provider_chain("image_generates")
        self.assertEqual(chain, ["slot1"])

    def test_chain_empty_when_nothing_registered(self) -> None:
        chain = self.registry.resolve_provider_chain("image_generates")
        self.assertEqual(chain, [])

    def test_resolve_provider_returns_chain_first(self) -> None:
        """``resolve_provider`` is now a thin wrapper over the chain."""
        self.registry.register_provider("image_generates", "slot1", _success_handler())
        self.registry.register_provider("image_generates", "slot2", _success_handler())
        self.assertEqual(self.registry.resolve_provider("image_generates"), "slot1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
