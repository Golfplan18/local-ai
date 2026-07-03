"""Context compaction — compress conversation history when approaching
the model's context window limit."""

from __future__ import annotations

import os

WORKSPACE = os.path.expanduser("~/ora/")


def estimate_tokens(text: str) -> int:
    """Approximate token count (4 chars per token)."""
    return len(text) // 4


def total_message_tokens(messages: list) -> int:
    """Estimate total tokens across all messages."""
    return sum(estimate_tokens(m.get("content", "")) for m in messages)


COMPACTION_PROMPT = """You are compressing a conversation for context continuity.
Summarize the conversation below into a structured summary containing:
1. Key decisions made
2. Open questions or unresolved issues
3. Established facts and context
4. Current working problem
5. Any named variables, entities, files, or code references that must persist

Be concise but preserve all actionable information. Do not lose specific details
like file paths, function names, or error messages.

CONVERSATION TO COMPRESS:
"""


import sys
from datetime import datetime

# Slots the compactor tries in order. 'small' was the original choice but it
# isn't a standard slot — get_slot_endpoint always returned None, falling
# through to the active endpoint. That meant compaction silently used the
# analytical slot regardless of intent.
_COMPACTION_SLOT_ORDER = ("sidebar", "classification", "step1_cleanup")


def _log_compaction(event: str, **fields) -> None:
    """Emit a single-line stderr log AND append to the compaction event log.

    Without this surface, compaction firing / skipping / failing was
    invisible — long conversations silently lost history with no signal
    that compaction had run, succeeded, or quietly dropped.
    """
    msg = f"[compact_context] {event}"
    if fields:
        msg += " " + " ".join(f"{k}={v}" for k, v in fields.items())
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass
    try:
        import json as _json
        try:
            import runtime_paths as _rp_c
        except ImportError:  # pragma: no cover
            from orchestrator import runtime_paths as _rp_c
        # Same root the retention sweeper rotates (ORA_HOME-relocatable).
        log_path = os.path.join(_rp_c.DATA_DIR_STR, "compaction-events.jsonl")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            payload = {"timestamp_utc": datetime.utcnow().isoformat() + "Z",
                       "event": event, **fields}
            f.write(_json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


def compact_context(messages: list, call_model_fn, context_limit: int = 1_000_000) -> list:
    """Compact conversation history when approaching the context window limit.

    Args:
        messages: Current message array.
        call_model_fn: Function to call the model: fn(messages, endpoint) -> str.
                       Pass None to skip compaction (graceful degradation).
        context_limit: Model's context window size in tokens.

    Returns:
        The (possibly compacted) messages array. When compaction succeeds,
        the middle of the conversation is replaced by a SYSTEM-attributed
        summary marker. When compaction fails, the original messages are
        returned — but the failure is logged to
        ``~/ora/data/compaction-events.jsonl`` and stderr so the silent
        drop class is visible to a developer reviewing logs.

    Attribution change (2026-05-15 sweep 4): the compacted summary is
    injected as a SYSTEM message with an explicit "the model did not
    say this" marker. The prior shape presented it as an assistant
    turn, causing downstream turns to confabulate from the summary's
    gaps as if they were the model's own prior reasoning.
    """
    if call_model_fn is None:
        _log_compaction("skipped", reason="no_call_model_fn",
                        current_tokens=total_message_tokens(messages),
                        context_limit=context_limit)
        return messages

    current_tokens = total_message_tokens(messages)
    threshold = int(context_limit * 0.8)
    if current_tokens < threshold:
        return messages  # Below threshold, not logged (too noisy).

    # Fire pre_compact hook
    try:
        from hooks import fire_hooks
        fire_hooks("pre_compact")
    except ImportError:
        pass

    system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
    keep_tail = messages[-6:] if len(messages) > 6 else messages[1 if system_msg else 0:]
    middle = messages[1:-len(keep_tail)] if system_msg else messages[:-len(keep_tail)]

    if not middle:
        _log_compaction("skipped", reason="no_middle_to_compact",
                        current_tokens=current_tokens, context_limit=context_limit)
        return messages

    middle_chars = sum(len(m.get("content", "") or "") for m in middle)
    middle_truncated_msgs = sum(
        1 for m in middle if len(m.get("content", "") or "") > 2000
    )

    conv_text = ""
    for msg in middle:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:2000]
        conv_text += f"\n[{role}]: {content}\n"

    compaction_messages = [
        {"role": "system", "content": COMPACTION_PROMPT},
        {"role": "user", "content": conv_text},
    ]

    try:
        from boot import load_routing_config, get_slot_endpoint, get_active_endpoint
        config = load_routing_config()
        endpoint = None
        endpoint_source = "unresolved"
        for slot in _COMPACTION_SLOT_ORDER:
            ep = get_slot_endpoint(config, slot)
            if ep is not None:
                endpoint = ep
                endpoint_source = f"slot:{slot}"
                break
        if endpoint is None:
            endpoint = get_active_endpoint(config)
            endpoint_source = "active_endpoint_fallback"
        if endpoint is None:
            _log_compaction("failed", reason="no_endpoint",
                            current_tokens=current_tokens,
                            middle_chars_lost_if_we_proceeded=middle_chars)
            return messages

        summary = call_model_fn(compaction_messages, endpoint)
        if not summary or len(summary) < 50:
            _log_compaction(
                "failed", reason="summary_too_short_or_empty",
                endpoint_source=endpoint_source,
                summary_chars=(len(summary) if summary else 0),
                current_tokens=current_tokens,
                middle_chars_lost_if_we_proceeded=middle_chars,
            )
            return messages

    except Exception as e:
        _log_compaction("failed", reason="exception",
                        error=str(e)[:300],
                        current_tokens=current_tokens,
                        middle_chars_lost_if_we_proceeded=middle_chars)
        return messages

    compacted = []
    if system_msg:
        compacted.append(system_msg)
    compacted.append({
        "role": "system",
        "content": (
            "[COMPACTED CONTEXT — system-generated summary; the model "
            "did not say this. The middle of the conversation was "
            f"compressed by a separate summarizer call (dropped "
            f"~{middle_chars} chars across {len(middle)} messages, "
            f"{middle_truncated_msgs} of which were >2000 chars and got "
            f"pre-truncated). Treat the summary as a partial record of "
            "what happened, not as your prior assertions.]\n\n"
            f"{summary}"
        ),
    })
    compacted.extend(keep_tail)

    _log_compaction(
        "compacted",
        endpoint_source=endpoint_source,
        before_tokens=current_tokens,
        after_tokens=total_message_tokens(compacted),
        middle_msgs_dropped=len(middle),
        middle_chars_dropped=middle_chars,
        middle_pre_truncated_msgs=middle_truncated_msgs,
        summary_chars=len(summary),
        kept_system=(system_msg is not None),
        kept_tail_msgs=len(keep_tail),
    )

    return compacted
