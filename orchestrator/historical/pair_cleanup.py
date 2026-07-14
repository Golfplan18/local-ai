"""Per-pair cleanup orchestration (Phase 1.8).

Composes the upstream pieces into a single end-to-end cleanup
operation for one `RawPair`:

  parse (1.2)
    → segment user input + classify pasted segments (1.3)
    → estimate tokens, route to model tier (1.5/1.6)
    → cleanup user input (1.7) — model call with paste-marker preservation
    → cleanup AI response (1.7) — model call with junk pruning
    → engagement-wrapper strip (1.4) — deterministic Python
    → CleanedPair record

Returns a `CleanedPair` with cleaned text plus full diagnostics:
which model handled each call, token counts, costs, drift warnings,
engagement-strip records.

The output of this module feeds Phase 1.9 (context-header generation)
and Phase 1.10 (cleaned-pair file writer).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from orchestrator import runtime_paths as _rp
from orchestrator.historical import RawPair
from orchestrator.historical.api_client import (
    AnthropicClient,
    estimate_tokens,
)
from orchestrator.historical.engagement import (
    StripRecord,
    strip_engagement,
)
from orchestrator.historical.model_router import (
    DispatchResult,
    ModelRoute,
    TIER_HAIKU,
    TIER_QWEN_27,
    dispatch_route,
    route_cleanup,
)
from orchestrator.historical.paste_detection import (
    Segment,
    process_user_input,
)
from orchestrator.historical.prompts import (
    AICleanupCall,
    PersonalSegmentCleanupCall,
    UserCleanupCall,
    UserCleanupResult,
    build_ai_cleanup_call,
    build_personal_segment_cleanup_call,
    build_user_cleanup_call_interleaved,
    extract_user_cleanup_result,
    looks_like_cleanup_refusal,
    strip_cleanup_preamble,
)


# Refusal-guard audit log (JSONL, one record per guarded fallback).
# Resolved at call time so tests and sandboxed runs can redirect it.
GUARD_LOG_ENV     = "ORA_CLEANUP_GUARD_LOG"
_INITIAL_GUARD_LOG_DEFAULT = "~/ora/data/cleanup-guard.log"
GUARD_LOG_DEFAULT = _INITIAL_GUARD_LOG_DEFAULT


def _guard_log_path() -> Path:
    configured = os.environ.get(GUARD_LOG_ENV)
    if configured:
        return Path(configured).expanduser()
    if GUARD_LOG_DEFAULT != _INITIAL_GUARD_LOG_DEFAULT:
        return Path(GUARD_LOG_DEFAULT).expanduser()
    roots = _rp.resolve_runtime_roots()
    return roots.ora_home / "data" / "cleanup-guard.log"


def _log_guard_event(source_path: str, pair_num: int, side: str,
                     signature: str, rejected_output: str) -> None:
    """Append one JSONL record for a refusal-guard fallback. Best-effort —
    a logging failure never blocks the cleanup itself."""
    try:
        log_path = _guard_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts":           datetime.now().isoformat(timespec="seconds"),
            "source_path":  source_path,
            "pair_num":     pair_num,
            "side":         side,                     # "user" | "ai"
            "signature":    signature,
            "action":       "raw_preserved",
            "output_prefix": rejected_output[:200],
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# Practical upper bound: Haiku/Sonnet 4.5 share a 200K token context
# (~800K chars). A pair larger than that genuinely cannot fit any single
# Anthropic call. We skip LLM cleanup only at this absolute ceiling and
# raw-preserve. Everything below routes through the model_router which
# picks Haiku for typical pairs and Sonnet for long ones.
MAX_CLEANUP_INPUT_CHARS = 700_000

# Per-segment chunking: a single personal segment above the threshold gets
# split on paragraph boundaries into chunks targeting ~10K output tokens
# each. The 64K-token output budget per Anthropic call is the bottleneck
# — a 100K-word inline-pasted book that registers as one personal segment
# can exceed it. Chunking keeps every cleanup call comfortably within
# budget, and each cleaned chunk is concatenated back with `\n\n`.
PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS = 120_000   # ~30K tokens
PERSONAL_SEGMENT_CHUNK_TARGET_CHARS    = 40_000    # ~10K tokens

_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")


def chunk_personal_segment(text: str) -> list[str]:
    """Split an oversized personal segment at paragraph boundaries.

    Returns ``[text]`` unchanged if it's already at or under the chunk
    threshold. Otherwise splits on `\\n\\s*\\n`, then greedily groups
    paragraphs into chunks targeting ``PERSONAL_SEGMENT_CHUNK_TARGET_CHARS``
    each. A single paragraph that exceeds the target stays as its own
    chunk; the per-chunk MAX_CLEANUP_INPUT_CHARS check downstream catches
    any single paragraph too large for one Anthropic call.
    """
    if len(text) <= PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS:
        return [text]
    paragraphs = [p for p in _PARAGRAPH_BREAK_RE.split(text) if p.strip()]
    if not paragraphs:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for p in paragraphs:
        p_len = len(p)
        # Start a new chunk if adding this paragraph would push us past
        # the target — but only if `current` already has at least one
        # paragraph (so a single huge paragraph still gets emitted as
        # its own chunk rather than producing an empty chunk).
        if current and current_len + p_len > PERSONAL_SEGMENT_CHUNK_TARGET_CHARS:
            chunks.append("\n\n".join(current))
            current = [p]
            current_len = p_len
        else:
            current.append(p)
            current_len += p_len + 2  # +2 for the "\n\n" separator
    if current:
        chunks.append("\n\n".join(current))
    return chunks


# ---------------------------------------------------------------------------
# Output record
# ---------------------------------------------------------------------------


@dataclass
class CleanupSideRecord:
    """Per-side (user or AI) cleanup diagnostics."""
    route:           Optional[ModelRoute] = None
    input_tokens:    int = 0
    output_tokens:   int = 0
    cost_usd:        float = 0.0
    duration_secs:   float = 0.0
    error:           str = ""
    retried_tier:    str = ""           # if retry escalation fired


@dataclass
class CleanedPair:
    """End-to-end cleanup output for one RawPair."""

    # Source identity
    pair_num:                int
    when:                    Optional[datetime]
    source_path:             str = ""

    # User side
    user_segments:           list[Segment] = field(default_factory=list)
    cleaned_user_input:      str = ""           # cleaned + paste-restored
    user_cleanup_warnings:   list[str] = field(default_factory=list)
    user_paste_drift:        bool = False
    user_record:             CleanupSideRecord = field(default_factory=CleanupSideRecord)

    # AI side
    cleaned_ai_response:     str = ""           # after model cleanup + strip
    cleaned_ai_pre_strip:    str = ""           # model output before strip
    engagement_strips:       list[StripRecord] = field(default_factory=list)
    ai_record:               CleanupSideRecord = field(default_factory=CleanupSideRecord)

    # Aggregate
    errors:                  list[str] = field(default_factory=list)
    skipped:                 bool = False
    skip_reason:             str = ""

    @property
    def total_cost_usd(self) -> float:
        return self.user_record.cost_usd + self.ai_record.cost_usd

    @property
    def total_input_tokens(self) -> int:
        return self.user_record.input_tokens + self.ai_record.input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self.user_record.output_tokens + self.ai_record.output_tokens


# ---------------------------------------------------------------------------
# One side's cleanup (with retry escalation on transient failure)
# ---------------------------------------------------------------------------


def _do_dispatch_with_retry(
    *,
    system:           str,
    user:             str,
    estimated_tokens: int,
    anthropic_client: AnthropicClient,
    config:           Optional[dict],
    max_tokens:       int,
) -> tuple[DispatchResult, ModelRoute, str]:
    """Run cleanup against the natural tier, escalate on transient failure.

    Returns (final dispatch result, final route used, retried_from_tier).
    `retried_from_tier` is "" if no escalation happened.
    """
    route = route_cleanup(estimated_tokens)
    result = dispatch_route(
        route, system=system, user=user,
        anthropic_client=anthropic_client, config=config,
        max_tokens=max_tokens,
    )
    if not result.error:
        return result, route, ""

    # Escalate one tier on error.
    retried_from = route.tier
    bumped_route = route_cleanup(estimated_tokens, retry_from_tier=route.tier)
    if bumped_route.tier == route.tier:
        # Already at top tier; can't bump.
        return result, route, ""

    bumped_result = dispatch_route(
        bumped_route, system=system, user=user,
        anthropic_client=anthropic_client, config=config,
        max_tokens=max_tokens,
    )
    if not bumped_result.error:
        return bumped_result, bumped_route, retried_from
    # Both attempts failed — return the last error with the bumped route.
    return bumped_result, bumped_route, retried_from


def _record_from_dispatch(
    dispatch_result: DispatchResult,
    route:           ModelRoute,
    retried_from:    str,
) -> CleanupSideRecord:
    return CleanupSideRecord(
        route=route,
        input_tokens=dispatch_result.input_tokens,
        output_tokens=dispatch_result.output_tokens,
        cost_usd=dispatch_result.cost_usd,
        duration_secs=dispatch_result.duration_secs,
        error=dispatch_result.error,
        retried_tier=retried_from,
    )


# ---------------------------------------------------------------------------
# User-input cleanup
# ---------------------------------------------------------------------------


def _clean_user_input(
    pair:              RawPair,
    vault_index:       Optional[dict],
    anthropic_client:  AnthropicClient,
    config:            Optional[dict],
    max_tokens:        int,
    source_platform:   str = "unknown",
    source_path:       str = "",
) -> tuple[list[Segment], str, list[str], bool, CleanupSideRecord]:
    """Run Phase 1.3 → 1.7 on the user's side.

    `source_platform` is plumbed through to `process_user_input` for the
    platform-aware paste classifier (Gemini → low news threshold,
    Claude → high; per the user's observation that Gemini inlined
    pastes while Claude segregated them via attachments).

    Returns (segments, cleaned_text_marker_free, warnings, paste_drift,
    record).
    """
    raw_user = pair.user_content
    if not raw_user:
        # Legitimate degenerate pair — e.g. a Claude Code session where
        # the user pressed Enter to advance a prompt, leaving the user
        # message blank and the assistant message carrying all signal.
        # Not an error; emit an empty user side and let the AI side
        # carry the file.
        return [], "", [], False, CleanupSideRecord(route=None)

    segments = process_user_input(
        raw_user, vault_index=vault_index, source_platform=source_platform,
    )

    # Segment-based cleanup: only personal segments go through the model.
    # Pasted segments pass through verbatim — the model never has to
    # reproduce them, which eliminates the 50K-token reproduction stalls
    # that hit Sonnet on huge pasted content.
    cleaned_parts:        list[str] = []
    warnings:             list[str] = []
    total_input_tokens    = 0
    total_output_tokens   = 0
    total_cost            = 0.0
    last_route            = None
    any_dispatch_error    = ""
    retried_tier_seen     = ""

    for seg in segments:
        if seg.kind == "pasted":
            # Preserve verbatim — no model call.
            if seg.content:
                cleaned_parts.append(seg.content)
            continue

        # Personal segment → clean via model. Chunk first so each call
        # fits within the 64K-token output budget; below the threshold
        # `chunk_personal_segment` returns `[text]` unchanged.
        text = seg.content
        if not text or not text.strip():
            continue

        chunks = chunk_personal_segment(text)
        seg_cleaned_parts: list[str] = []

        for chunk in chunks:
            if len(chunk) > MAX_CLEANUP_INPUT_CHARS:
                # Single paragraph above the absolute per-call ceiling
                # — chunking can't help. Preserve raw and warn.
                warnings.append(
                    f"personal segment chunk too large for LLM cleanup "
                    f"({len(chunk)} chars > {MAX_CLEANUP_INPUT_CHARS}); "
                    f"raw preserved"
                )
                seg_cleaned_parts.append(chunk)
                continue

            call: PersonalSegmentCleanupCall = build_personal_segment_cleanup_call(chunk)
            estimated = estimate_tokens(call.system) + estimate_tokens(call.user)
            dispatch_result, route, retried_from = _do_dispatch_with_retry(
                system=call.system, user=call.user,
                estimated_tokens=estimated,
                anthropic_client=anthropic_client, config=config,
                max_tokens=max_tokens,
            )
            last_route = route
            if retried_from:
                retried_tier_seen = retried_from
            total_input_tokens  += dispatch_result.input_tokens
            total_output_tokens += dispatch_result.output_tokens
            total_cost          += dispatch_result.cost_usd

            if dispatch_result.error:
                warnings.append(
                    f"segment cleanup error (raw preserved): "
                    f"{dispatch_result.error[:200]}"
                )
                seg_cleaned_parts.append(chunk)  # fall back to raw for this chunk
                any_dispatch_error = dispatch_result.error
                continue

            # Normalize model output: framing preamble + leaked wrapper
            # tags may appear in either order, so strip preamble on both
            # sides of the tag strip. Preamble strip carries the same
            # immunity rule as the refusal guard (a framing line present
            # in the input is content, not framing).
            cleaned = strip_cleanup_preamble(dispatch_result.text.strip(),
                                             chunk)
            if cleaned.startswith("<input_to_clean>"):
                cleaned = cleaned.removeprefix("<input_to_clean>").strip()
            if cleaned.endswith("</input_to_clean>"):
                cleaned = cleaned.removesuffix("</input_to_clean>").strip()
            cleaned = strip_cleanup_preamble(cleaned, chunk).strip()

            # Empty-output guard: a successful call that returns nothing
            # (or nothing but framing) must not erase the chunk.
            if chunk.strip() and not cleaned:
                warnings.append("cleanup returned empty output; raw preserved")
                _log_guard_event(source_path, pair.pair_num, "user",
                                 "empty-output", dispatch_result.text[:200])
                seg_cleaned_parts.append(chunk)
                continue

            # Refusal guard: if the model commented on the input instead
            # of returning it, keep the original text. Worst case is
            # uncleaned-but-intact — never the model's commentary.
            refusal_sig = looks_like_cleanup_refusal(cleaned, chunk)
            if refusal_sig:
                warnings.append(
                    f"cleanup output looked like model commentary "
                    f"(signature: {refusal_sig!r}); raw preserved"
                )
                _log_guard_event(source_path, pair.pair_num, "user",
                                 refusal_sig, cleaned)
                seg_cleaned_parts.append(chunk)
                continue
            seg_cleaned_parts.append(cleaned)

        # Reassemble the segment from its cleaned chunks (one chunk in
        # the typical case, multiple for huge personal segments).
        cleaned_parts.append("\n\n".join(seg_cleaned_parts))

    cleaned_text = "\n\n".join(cleaned_parts).strip()

    record = CleanupSideRecord(
        route=last_route,
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_usd=total_cost,
        error=any_dispatch_error,
        retried_tier=retried_tier_seen,
    )
    return segments, cleaned_text, warnings, False, record


# ---------------------------------------------------------------------------
# AI-response cleanup + engagement strip
# ---------------------------------------------------------------------------


def _clean_ai_response(
    pair:              RawPair,
    anthropic_client:  AnthropicClient,
    config:            Optional[dict],
    max_tokens:        int,
    source_path:       str = "",
) -> tuple[str, str, list[StripRecord], CleanupSideRecord]:
    """Run Phase 1.7 + 1.4 on the AI side.

    Returns (cleaned_ai_pre_strip, cleaned_ai_final, strips, record).
    """
    raw_ai = pair.assistant_content
    if not raw_ai:
        # Mirror of the empty-user case — a pair with content only on
        # the user side. Not an error; emit empty AI side and let the
        # user side carry the file.
        return "", "", [], CleanupSideRecord(route=None)

    if len(raw_ai) > MAX_CLEANUP_INPUT_CHARS:
        # Too large for LLM cleanup — preserve raw, but still run the
        # deterministic engagement strip on it. SUCCESS path, not an error.
        cleaned, strips = strip_engagement(raw_ai)
        return raw_ai, cleaned, strips, CleanupSideRecord(
            route=None, error="",  # not an error
            retried_tier="size-skipped",
        )

    call: AICleanupCall = build_ai_cleanup_call(raw_ai)
    estimated = estimate_tokens(call.system) + estimate_tokens(call.user)

    dispatch_result, route, retried_from = _do_dispatch_with_retry(
        system=call.system, user=call.user,
        estimated_tokens=estimated,
        anthropic_client=anthropic_client, config=config,
        max_tokens=max_tokens,
    )
    record = _record_from_dispatch(dispatch_result, route, retried_from)

    if dispatch_result.error:
        # Fall back to raw AI content (post-strip). Preserve any strips
        # we can detect from raw.
        cleaned, strips = strip_engagement(raw_ai)
        return raw_ai, cleaned, strips, record

    # Normalize model output (same order as the user side: preamble /
    # tags / preamble, immunity against lines present in the input).
    pre_strip = strip_cleanup_preamble(dispatch_result.text.strip(), raw_ai)
    if pre_strip.startswith("<input_to_clean>"):
        pre_strip = pre_strip.removeprefix("<input_to_clean>").strip()
    if pre_strip.endswith("</input_to_clean>"):
        pre_strip = pre_strip.removesuffix("</input_to_clean>").strip()
    pre_strip = strip_cleanup_preamble(pre_strip, raw_ai)

    # Empty-output guard: a successful call that returns nothing must
    # not erase the response.
    if raw_ai.strip() and not pre_strip.strip():
        _log_guard_event(source_path, pair.pair_num, "ai",
                         "empty-output", dispatch_result.text[:200])
        record.retried_tier = record.retried_tier or "guard-raw-preserved"
        cleaned, strips = strip_engagement(raw_ai)
        return raw_ai, cleaned, strips, record

    # Refusal guard: a cleanup model commenting on the response instead
    # of returning it falls back to the raw response (post-strip).
    refusal_sig = looks_like_cleanup_refusal(pre_strip, raw_ai)
    if refusal_sig:
        _log_guard_event(source_path, pair.pair_num, "ai",
                         refusal_sig, pre_strip)
        record.retried_tier = record.retried_tier or "guard-raw-preserved"
        cleaned, strips = strip_engagement(raw_ai)
        return raw_ai, cleaned, strips, record

    cleaned, strips = strip_engagement(pre_strip)
    return pre_strip, cleaned, strips, record


# ---------------------------------------------------------------------------
# End-to-end pair cleanup
# ---------------------------------------------------------------------------


def clean_pair(
    pair:              RawPair,
    *,
    vault_index:       Optional[dict] = None,
    anthropic_client:  AnthropicClient,
    config:            Optional[dict] = None,
    source_path:       str = "",
    source_platform:   str = "unknown",
    max_tokens:        int = 64000,
) -> CleanedPair:
    """Run the full Phase 1 pipeline on a single RawPair.

    Returns a CleanedPair record with cleaned text + diagnostics. Never
    raises for cleanup-side errors; all such errors are captured on
    the returned record's `errors` list. Only programmer errors raise.

    `source_platform` (claude/chatgpt/gemini/local-ora/unknown) is
    threaded through to the paste classifier — Gemini segments get a
    much lower threshold for news/opinion classification per the user's
    observation that Gemini inlined pastes while Claude segregated them.
    """
    out = CleanedPair(
        pair_num=pair.pair_num,
        when=pair.when,
        source_path=source_path,
    )

    if not pair.user_content and not pair.assistant_content:
        out.skipped = True
        out.skip_reason = "empty pair"
        return out

    # User side
    (segments, cleaned_user, warnings, drift, user_rec) = _clean_user_input(
        pair, vault_index=vault_index,
        anthropic_client=anthropic_client, config=config,
        max_tokens=max_tokens,
        source_platform=source_platform,
        source_path=source_path,
    )
    out.user_segments         = segments
    out.cleaned_user_input    = cleaned_user
    out.user_cleanup_warnings = warnings
    out.user_paste_drift      = drift
    out.user_record           = user_rec
    if user_rec.error:
        out.errors.append(f"user cleanup: {user_rec.error}")

    # AI side
    (pre_strip, final_ai, strips, ai_rec) = _clean_ai_response(
        pair, anthropic_client=anthropic_client, config=config,
        max_tokens=max_tokens,
        source_path=source_path,
    )
    out.cleaned_ai_pre_strip = pre_strip
    out.cleaned_ai_response  = final_ai
    out.engagement_strips    = strips
    out.ai_record            = ai_rec
    if ai_rec.error:
        out.errors.append(f"ai cleanup: {ai_rec.error}")

    return out


__all__ = [
    "CleanedPair",
    "CleanupSideRecord",
    "MAX_CLEANUP_INPUT_CHARS",
    "PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS",
    "PERSONAL_SEGMENT_CHUNK_TARGET_CHARS",
    "chunk_personal_segment",
    "clean_pair",
]
