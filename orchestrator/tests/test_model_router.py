"""Tests for cleanup model routing (Phase 1.6).

Verifies:
  - Token thresholds map to the correct tier
  - Retry escalation bumps the tier
  - Dispatch-API path uses the AnthropicClient (mocked)
  - Dispatch-local path resolves slots and calls call_local_endpoint
    via injected boot module shim
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.api_client import CallResult  # noqa: E402
from orchestrator.historical.model_router import (  # noqa: E402
    DispatchResult,
    MODEL_HAIKU,
    MODEL_HERMES_70,
    MODEL_QWEN_27,
    MODEL_SONNET,
    ModelRoute,
    SLOT_HERMES_70,
    SLOT_QWEN_27,
    THRESHOLD_HAIKU_MAX,
    THRESHOLD_SONNET_MAX,
    TIER_HAIKU,
    TIER_HERMES_70,
    TIER_QWEN_27,
    TIER_SONNET,
    dispatch_route,
    route_cleanup,
)


# ---------------------------------------------------------------------------
# Pure routing decisions
# ---------------------------------------------------------------------------


class TestRouteDecision(unittest.TestCase):

    def test_small_input_routes_to_haiku(self):
        r = route_cleanup(500)
        self.assertEqual(r.tier, TIER_HAIKU)
        self.assertEqual(r.dispatch, "anthropic-api")
        self.assertEqual(r.model_id, MODEL_HAIKU)
        self.assertEqual(r.slot_name, "")

    def test_at_haiku_threshold_still_haiku(self):
        r = route_cleanup(THRESHOLD_HAIKU_MAX)
        self.assertEqual(r.tier, TIER_HAIKU)

    def test_just_over_haiku_routes_to_sonnet(self):
        r = route_cleanup(THRESHOLD_HAIKU_MAX + 1)
        self.assertEqual(r.tier, TIER_SONNET)
        self.assertEqual(r.dispatch, "anthropic-api")
        self.assertEqual(r.model_id, MODEL_SONNET)

    def test_huge_input_still_routes_to_sonnet(self):
        # Above the documented Sonnet ceiling we still pick Sonnet
        # (best-effort) — no further escalation tiers exist for routing
        # decisions.
        r = route_cleanup(THRESHOLD_SONNET_MAX + 50_000)
        self.assertEqual(r.tier, TIER_SONNET)


# ---------------------------------------------------------------------------
# Retry escalation
# ---------------------------------------------------------------------------


class TestRetryEscalation(unittest.TestCase):

    def test_retry_from_haiku_bumps_to_sonnet(self):
        r = route_cleanup(500, retry_from_tier=TIER_HAIKU)
        self.assertEqual(r.tier, TIER_SONNET)

    def test_retry_from_sonnet_bumps_to_qwen(self):
        r = route_cleanup(500, retry_from_tier=TIER_SONNET)
        self.assertEqual(r.tier, TIER_QWEN_27)

    def test_retry_from_qwen_bumps_to_hermes(self):
        r = route_cleanup(500, retry_from_tier=TIER_QWEN_27)
        self.assertEqual(r.tier, TIER_HERMES_70)

    def test_retry_from_hermes_stays_hermes(self):
        # Already at the top — can't bump further.
        r = route_cleanup(500, retry_from_tier=TIER_HERMES_70)
        self.assertEqual(r.tier, TIER_HERMES_70)

    def test_retry_when_natural_already_higher(self):
        # Natural is sonnet (over Haiku threshold). Retry from Haiku
        # picks max(failed_idx+1, natural_idx) = Sonnet; the natural pick
        # was already past the failed tier, so no further bump.
        r = route_cleanup(200_000, retry_from_tier=TIER_HAIKU)
        self.assertEqual(r.tier, TIER_SONNET)


# ---------------------------------------------------------------------------
# Dispatch — anthropic-api path
# ---------------------------------------------------------------------------


class TestDispatchAnthropic(unittest.TestCase):

    def test_dispatch_haiku_calls_client(self):
        client = MagicMock()
        client.call = MagicMock(return_value=CallResult(
            text="cleaned", model=MODEL_HAIKU,
            input_tokens=100, output_tokens=50, cost_usd=0.001,
        ))
        route = ModelRoute(
            tier=TIER_HAIKU, model_id=MODEL_HAIKU,
            dispatch="anthropic-api", slot_name="", rationale="test",
        )
        result = dispatch_route(
            route, system="be terse", user="ping",
            anthropic_client=client, max_tokens=512,
        )
        self.assertEqual(result.text, "cleaned")
        self.assertEqual(result.tier, TIER_HAIKU)
        self.assertEqual(result.input_tokens, 100)
        self.assertEqual(result.cost_usd, 0.001)
        self.assertEqual(result.error, "")
        # Verify the client was called with system + user.
        kwargs = client.call.call_args.kwargs
        self.assertEqual(kwargs["system"], "be terse")
        self.assertEqual(kwargs["user"], "ping")
        self.assertEqual(kwargs["model"], MODEL_HAIKU)

    def test_dispatch_anthropic_propagates_error(self):
        client = MagicMock()
        client.call = MagicMock(return_value=CallResult(
            text="", model=MODEL_HAIKU, error="rate limited",
        ))
        route = ModelRoute(
            tier=TIER_HAIKU, model_id=MODEL_HAIKU,
            dispatch="anthropic-api", slot_name="", rationale="test",
        )
        result = dispatch_route(route, system="", user="hi",
                                  anthropic_client=client)
        self.assertEqual(result.text, "")
        self.assertIn("rate limited", result.error)

    def test_dispatch_anthropic_missing_client(self):
        route = ModelRoute(
            tier=TIER_HAIKU, model_id=MODEL_HAIKU,
            dispatch="anthropic-api", slot_name="", rationale="test",
        )
        result = dispatch_route(route, system="", user="hi",
                                  anthropic_client=None)
        self.assertNotEqual(result.error, "")


# ---------------------------------------------------------------------------
# Dispatch — local-endpoint path
# ---------------------------------------------------------------------------


class TestDispatchLocal(unittest.TestCase):

    def test_dispatch_local_resolves_slot_and_calls_endpoint(self):
        route = ModelRoute(
            tier=TIER_QWEN_27, model_id=MODEL_QWEN_27,
            dispatch="local-endpoint", slot_name=SLOT_QWEN_27,
            rationale="test",
        )
        with patch("orchestrator.boot.get_slot_endpoint",
                   return_value={"url": "http://localhost:1234"}) as mock_get, \
             patch("orchestrator.boot.call_local_endpoint",
                   return_value="local cleaned text") as mock_call:
            result = dispatch_route(
                route, system="instructions", user="long text here",
                config={"slots": {SLOT_QWEN_27: "qwen-27"}},
            )
            mock_get.assert_called_once()
            mock_call.assert_called_once()
            # Verify messages assembled correctly
            messages = mock_call.call_args[0][0]
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(messages[0]["content"], "instructions")
            self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(result.text, "local cleaned text")
        self.assertEqual(result.error, "")
        # Token estimates populated for local dispatch.
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)

    def test_dispatch_local_no_endpoint_falls_back_to_haiku(self):
        # When the slot has no registered endpoint AND an anthropic client
        # is available, dispatch falls back to Haiku via the API.
        client = MagicMock()
        client.call = MagicMock(return_value=CallResult(
            text="haiku fallback ok", model=MODEL_HAIKU,
            input_tokens=100, output_tokens=50, cost_usd=0.001,
        ))
        route = ModelRoute(
            tier=TIER_QWEN_27, model_id=MODEL_QWEN_27,
            dispatch="local-endpoint", slot_name=SLOT_QWEN_27,
            rationale="test",
        )
        with patch("orchestrator.boot.get_slot_endpoint", return_value=None):
            result = dispatch_route(
                route, system="x", user="y", config={},
                anthropic_client=client,
            )
        self.assertEqual(result.text, "haiku fallback ok")
        self.assertEqual(result.tier, TIER_HAIKU)
        self.assertEqual(result.dispatch, "anthropic-api-fallback")

    def test_dispatch_local_endpoint_raises_recorded(self):
        route = ModelRoute(
            tier=TIER_HERMES_70, model_id=MODEL_HERMES_70,
            dispatch="local-endpoint", slot_name=SLOT_HERMES_70,
            rationale="test",
        )
        with patch("orchestrator.boot.get_slot_endpoint",
                   return_value={"url": "http://localhost:9999"}), \
             patch("orchestrator.boot.call_local_endpoint",
                   side_effect=ConnectionRefusedError("server down")):
            result = dispatch_route(
                route, system="x", user="y", config={},
            )
        self.assertEqual(result.text, "")
        self.assertIn("server down", result.error)

    def test_dispatch_local_no_config_falls_back_to_haiku(self):
        # When config is None (CLI didn't provide one) AND anthropic
        # client is available, dispatch falls back to Haiku via the API.
        client = MagicMock()
        client.call = MagicMock(return_value=CallResult(
            text="fallback ok", model=MODEL_HAIKU,
            input_tokens=100, output_tokens=50, cost_usd=0.001,
        ))
        route = ModelRoute(
            tier=TIER_QWEN_27, model_id=MODEL_QWEN_27,
            dispatch="local-endpoint", slot_name=SLOT_QWEN_27,
            rationale="test",
        )
        result = dispatch_route(route, system="x", user="y", config=None,
                                  anthropic_client=client)
        self.assertEqual(result.text, "fallback ok")
        self.assertEqual(result.dispatch, "anthropic-api-fallback")

    def test_dispatch_local_no_config_no_client_records_error(self):
        # Without anthropic_client AND without config, both paths blocked.
        route = ModelRoute(
            tier=TIER_QWEN_27, model_id=MODEL_QWEN_27,
            dispatch="local-endpoint", slot_name=SLOT_QWEN_27,
            rationale="test",
        )
        result = dispatch_route(route, system="x", user="y", config=None,
                                  anthropic_client=None)
        self.assertEqual(result.text, "")
        self.assertIn("config not provided", result.error)


if __name__ == "__main__":
    unittest.main()
