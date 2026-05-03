"""Model routing for Phase 1 cleanup (Phase 1.6).

The cleanup pipeline routes each pair to one of three tiers based on
input token estimate:

    Tier 1 — Haiku 4.5 (commercial API)   |  ≤ 2K tokens
    Tier 2 — Qwen3.5-27B local             |  2K–8K tokens     (slot 'step1_cleanup')
    Tier 3 — Hermes-4-70B local            |  > 8K tokens      (slot 'breadth')

Retry escalation: a transient failure on a lower tier can be retried
on the next-higher tier. The router records this as `retry_from_tier`
so it knows not to route back to the same level.

This module exposes:

  * `ModelRoute` — the decision record (model_id, tier, dispatch path,
    slot name, rationale)
  * `route_cleanup(estimated_tokens, retry_from_tier=None) → ModelRoute`
    — pure decision, no I/O
  * `dispatch_route(route, ...) → DispatchResult` — actually executes
    the call against either AnthropicClient or `boot.call_local_endpoint`

Token thresholds + tier names are constants near the top so the
cleanup orchestrator can use them in cost estimation without
re-encoding the routing logic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

TIER_HAIKU     = "haiku"        # Anthropic Haiku 4.5 — fast/cheap, ≤30K tokens
TIER_SONNET    = "sonnet"       # Anthropic Sonnet 4.5 — capable, larger pairs
TIER_QWEN_27   = "qwen-27"      # local fallback, slot 'step1_cleanup'
TIER_HERMES_70 = "hermes-70"    # local fallback, slot 'breadth'

# Token thresholds (input tokens, estimated).
# Cleanup routing biases toward cloud models because the user wants the
# advanced-model path for stream-of-consciousness pairs:
#   ≤30K tokens          → Haiku 4.5 (default, fast)
#   30K–180K tokens       → Sonnet 4.5 (more capable, same 200K context)
#   >180K tokens          → Sonnet 4.5 with note (best effort within context)
# Local models stay available as fallback paths only — see dispatch_route.
THRESHOLD_HAIKU_MAX  = 30_000
THRESHOLD_SONNET_MAX = 180_000

# Slot names matching the existing Ora slot system.
SLOT_QWEN_27   = "step1_cleanup"
SLOT_HERMES_70 = "breadth"

# Default model IDs for each tier (used as the route's model_id label).
MODEL_HAIKU       = "claude-haiku-4-5"
MODEL_SONNET      = "claude-sonnet-4-5"
MODEL_QWEN_27     = "qwen-27b-local"
MODEL_HERMES_70   = "hermes-70b-local"

# Order from cheapest/fastest to most-capable. Used for retry escalation.
TIER_ORDER = (TIER_HAIKU, TIER_SONNET, TIER_QWEN_27, TIER_HERMES_70)


# ---------------------------------------------------------------------------
# Route + dispatch records
# ---------------------------------------------------------------------------


@dataclass
class ModelRoute:
    """The chosen tier + dispatch info for one cleanup call."""
    tier:       str    # 'haiku' | 'qwen-27' | 'hermes-70'
    model_id:   str    # human-readable id used by stats + logs
    dispatch:   str    # 'anthropic-api' | 'local-endpoint'
    slot_name:  str    # for local-endpoint: 'step1_cleanup' | 'breadth'
    rationale:  str    # plain-English why this tier


@dataclass
class DispatchResult:
    """Outcome of dispatching a route. `text` is empty on failure."""
    text:           str = ""
    tier:           str = ""
    model_id:       str = ""
    dispatch:       str = ""
    input_tokens:   int = 0
    output_tokens:  int = 0
    cost_usd:       float = 0.0
    duration_secs:  float = 0.0
    error:          str = ""


# ---------------------------------------------------------------------------
# Pure routing decision
# ---------------------------------------------------------------------------


def route_cleanup(estimated_tokens: int,
                    retry_from_tier: Optional[str] = None) -> ModelRoute:
    """Pick the cleanup tier for an input of `estimated_tokens` size.

    Args:
      estimated_tokens: rough token count of the combined system + user
        message we're about to send.
      retry_from_tier: if set, the previous tier that failed (so we
        don't route back to it). Bumps to the next tier in TIER_ORDER.

    Returns a ModelRoute. Never raises.
    """
    target_tier = _natural_tier(estimated_tokens)

    if retry_from_tier:
        # Bump to the next tier in TIER_ORDER beyond the one that failed.
        try:
            failed_idx = TIER_ORDER.index(retry_from_tier)
        except ValueError:
            failed_idx = -1
        bumped_idx = max(failed_idx + 1, TIER_ORDER.index(target_tier))
        bumped_idx = min(bumped_idx, len(TIER_ORDER) - 1)
        target_tier = TIER_ORDER[bumped_idx]
        rationale = (f"retry escalation from {retry_from_tier}: "
                     f"{estimated_tokens} tokens → tier {target_tier}")
    else:
        rationale = _rationale_for(estimated_tokens, target_tier)

    return _route_for_tier(target_tier, rationale)


def _natural_tier(estimated_tokens: int) -> str:
    if estimated_tokens <= THRESHOLD_HAIKU_MAX:
        return TIER_HAIKU
    # Everything above Haiku threshold goes to Sonnet — both fit Sonnet's
    # 200K context comfortably, and Sonnet's added capacity matters most
    # for the long stream-of-consciousness pairs the user flagged.
    return TIER_SONNET


def _rationale_for(estimated_tokens: int, tier: str) -> str:
    if tier == TIER_HAIKU:
        return f"≤{THRESHOLD_HAIKU_MAX} tokens — Haiku 4.5 (default, fast)"
    if tier == TIER_SONNET:
        return f">{THRESHOLD_HAIKU_MAX} tokens — Sonnet 4.5 (advanced)"
    if tier == TIER_QWEN_27:
        return f"local fallback — Qwen 27B"
    return f"local fallback — Hermes 70B"


def _route_for_tier(tier: str, rationale: str) -> ModelRoute:
    if tier == TIER_HAIKU:
        return ModelRoute(
            tier=TIER_HAIKU, model_id=MODEL_HAIKU,
            dispatch="anthropic-api", slot_name="",
            rationale=rationale,
        )
    if tier == TIER_SONNET:
        return ModelRoute(
            tier=TIER_SONNET, model_id=MODEL_SONNET,
            dispatch="anthropic-api", slot_name="",
            rationale=rationale,
        )
    if tier == TIER_QWEN_27:
        return ModelRoute(
            tier=TIER_QWEN_27, model_id=MODEL_QWEN_27,
            dispatch="local-endpoint", slot_name=SLOT_QWEN_27,
            rationale=rationale,
        )
    return ModelRoute(
        tier=TIER_HERMES_70, model_id=MODEL_HERMES_70,
        dispatch="local-endpoint", slot_name=SLOT_HERMES_70,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_route(route:           ModelRoute,
                    *,
                    system:          str,
                    user:            str,
                    anthropic_client: Any = None,
                    config:           Optional[dict] = None,
                    max_tokens:       int = 8192,
                    temperature:      float = 0.0) -> DispatchResult:
    """Execute the chosen route. Returns a DispatchResult.

    For `dispatch == 'anthropic-api'` the caller must provide
    `anthropic_client` (an `AnthropicClient` instance). For
    `dispatch == 'local-endpoint'` the caller must provide `config`
    (the live Ora config dict) so the slot can be resolved via
    `boot.get_slot_endpoint`.
    """
    out = DispatchResult(
        tier=route.tier, model_id=route.model_id, dispatch=route.dispatch,
    )
    start = time.monotonic()

    if route.dispatch == "anthropic-api":
        if anthropic_client is None:
            out.error = "anthropic_client not provided"
            out.duration_secs = time.monotonic() - start
            return out
        try:
            result = anthropic_client.call(
                system=system, user=user, model=route.model_id,
                max_tokens=max_tokens, temperature=temperature,
            )
        except Exception as e:
            out.error = f"anthropic dispatch raised: {e}"
            out.duration_secs = time.monotonic() - start
            return out
        out.text          = result.text
        out.input_tokens  = result.input_tokens
        out.output_tokens = result.output_tokens
        out.cost_usd      = result.cost_usd
        out.error         = result.error
        out.duration_secs = time.monotonic() - start
        return out

    if route.dispatch == "local-endpoint":
        # Detect whether local dispatch is even possible. If not (no config
        # passed, can't import boot, no endpoint registered for the slot),
        # fall back to Haiku via the anthropic client when one is provided.
        local_unavailable_reason = ""
        if config is None:
            local_unavailable_reason = "config not provided for local-endpoint dispatch"
        else:
            try:
                from orchestrator.boot import (
                    call_local_endpoint, get_slot_endpoint,
                )
            except Exception as e:
                local_unavailable_reason = f"local dispatch import failed: {e}"
            else:
                endpoint = get_slot_endpoint(config, route.slot_name)
                if endpoint is None:
                    local_unavailable_reason = f"no endpoint for slot '{route.slot_name}'"

        if local_unavailable_reason:
            # Fallback path: use Haiku via the anthropic client if available.
            if anthropic_client is None:
                out.error = local_unavailable_reason
                out.duration_secs = time.monotonic() - start
                return out
            try:
                fb = anthropic_client.call(
                    system=system, user=user, model=MODEL_HAIKU,
                    max_tokens=max_tokens, temperature=temperature,
                )
            except Exception as e:
                out.error = (f"local unavailable ({local_unavailable_reason}); "
                              f"haiku fallback raised: {e}")
                out.duration_secs = time.monotonic() - start
                return out
            out.tier          = TIER_HAIKU            # record actual model used
            out.model_id      = MODEL_HAIKU
            out.dispatch      = "anthropic-api-fallback"
            out.text          = fb.text
            out.input_tokens  = fb.input_tokens
            out.output_tokens = fb.output_tokens
            out.cost_usd      = fb.cost_usd
            out.error         = fb.error
            out.duration_secs = time.monotonic() - start
            return out
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        try:
            text = call_local_endpoint(messages, endpoint)
        except Exception as e:
            out.error = f"local endpoint raised: {e}"
            out.duration_secs = time.monotonic() - start
            return out
        out.text = text or ""
        # Local dispatch doesn't expose token counts cheaply; estimate.
        from orchestrator.historical.api_client import estimate_tokens
        out.input_tokens  = estimate_tokens(system) + estimate_tokens(user)
        out.output_tokens = estimate_tokens(out.text)
        out.duration_secs = time.monotonic() - start
        return out

    out.error = f"unknown dispatch type: {route.dispatch}"
    out.duration_secs = time.monotonic() - start
    return out


__all__ = [
    "TIER_HAIKU", "TIER_QWEN_27", "TIER_HERMES_70", "TIER_ORDER",
    "THRESHOLD_HAIKU_MAX", "THRESHOLD_QWEN_MAX",
    "SLOT_QWEN_27", "SLOT_HERMES_70",
    "MODEL_HAIKU", "MODEL_QWEN_27", "MODEL_HERMES_70",
    "ModelRoute", "DispatchResult",
    "route_cleanup", "dispatch_route",
]
