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


def compact_context(messages: list, call_model_fn, context_limit: int = 8192) -> list:
    """Compact conversation history when approaching the context window limit.

    Args:
        messages: Current message array.
        call_model_fn: Function to call the model: fn(messages, endpoint) -> str.
                       Pass None to skip compaction (graceful degradation).
        context_limit: Model's context window size in tokens.

    Returns:
        The (possibly compacted) messages array.
    """
    if call_model_fn is None:
        return messages

    current_tokens = total_message_tokens(messages)

    # Only compact if above 80% of context limit
    threshold = int(context_limit * 0.8)
    if current_tokens < threshold:
        return messages

    # Fire pre_compact hook
    try:
        from hooks import fire_hooks
        fire_hooks("pre_compact")
    except ImportError:
        pass

    # Preserve system prompt (first message) and last 3 turns
    system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
    keep_tail = messages[-6:] if len(messages) > 6 else messages[1 if system_msg else 0:]  # ~3 user+assistant pairs, or all non-system if short
    middle = messages[1:-len(keep_tail)] if system_msg else messages[:-len(keep_tail)]

    if not middle:
        return messages  # Nothing to compact

    # Build the conversation text to compress
    conv_text = ""
    for msg in middle:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:2000]  # Cap per-message to avoid huge compaction input
        conv_text += f"\n[{role}]: {content}\n"

    # Call model for compaction
    compaction_messages = [
        {"role": "system", "content": COMPACTION_PROMPT},
        {"role": "user", "content": conv_text},
    ]

    try:
        # Use the same endpoint loading as boot.py
        from boot import load_endpoints, get_slot_endpoint, get_active_endpoint
        config = load_endpoints()
        endpoint = get_slot_endpoint(config, "small") or get_active_endpoint(config)
        if endpoint is None:
            return messages

        summary = call_model_fn(compaction_messages, endpoint)
        if not summary or len(summary) < 50:
            return messages  # Compaction failed, keep original

    except Exception:
        return messages

    # Rebuild messages array
    compacted = []
    if system_msg:
        compacted.append(system_msg)
    compacted.append({
        "role": "assistant",
        "content": f"[COMPACTED CONTEXT]\n\n{summary}",
    })
    compacted.extend(keep_tail)

    return compacted
