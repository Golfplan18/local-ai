"""Resolution chain — multi-turn discussion that resolves a Paused queue entry.

Mirrors framework_elicitation.py in spirit: the conversation IS the state,
no separate persistence layer. Each AI turn in a resolution chain carries
a hidden marker tagging the queue entry the discussion is about, plus the
machine-readable form of the proposed alternative (option 3 content).

Marker format (HTML comment, invisible in markdown render):

    <!-- ora-resolution: {"queue_id": "<id>", "alternative": "<text>"} -->

Visible to the user, every AI response in a resolution chain ends with:

    Resolution options:
    1. Approve as proposed
    2. Deny
    [3. Apply this alternative:
        <full alternative text — possibly multi-paragraph>]

    Type 1, 2, or 3 to act, or ask anything to continue.

Option 3 only appears once the AI has formulated a substantive alternative
that diverges from the system's original proposal. Until then, only 1 and 2
are shown.

User input:
    "1"  → commit Approve as proposed
    "2"  → commit Deny (one-line reason taken from the user's most recent
           free-form turn before "2", or empty)
    "3"  → commit Apply this alternative (with content from the marker)
    anything else → continued discussion

After a successful commit, the conversation gets a "(resolved)" suffix on
its display_name and the queue entry is removed.

Entry points:
    is_resolution_continuation(history)   -> Optional[ContinuationContext]
    start_resolution(queue_id, sessions_root, config) -> dict
    continue_resolution(ctx, history, latest_user_text, conversation_id, config)
        -> str

Closes deferred handoff item #8 backend (resolution chain). The V3 sidebar
panel surfaces these chains via the discuss endpoint.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional


RESOLUTION_SLOT = "sidebar"  # small model — same slot as elicitation summarizer

MARKER_PATTERN = re.compile(
    r"<!--\s*ora-resolution:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)
RESOLVED_SUFFIX = " (resolved)"


@dataclass
class ContinuationContext:
    queue_id: str
    last_alternative: str  # most recent option-3 content from the marker (may be empty)


# ---------- Marker helpers ----------

def is_resolution_continuation(history: list) -> Optional[ContinuationContext]:
    """Return a ContinuationContext if the most recent assistant message in
    history carries a resolution-chain marker. None otherwise.
    """
    if not history:
        return None
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "") or ""
        m = MARKER_PATTERN.search(content)
        if not m:
            return None
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return ContinuationContext(
            queue_id=str(payload.get("queue_id", "")),
            last_alternative=str(payload.get("alternative", "")),
        )
    return None


def _marker_for(queue_id: str, alternative: str = "") -> str:
    """Build the HTML-comment marker. JSON-encoded payload, invisible in render."""
    payload = {"queue_id": queue_id, "alternative": alternative or ""}
    return f"<!-- ora-resolution: {json.dumps(payload, ensure_ascii=False)} -->"


# ---------- start_resolution ----------

def start_resolution(
    queue_id: str,
    sessions_root: Optional[str] = None,
    config: Optional[dict] = None,
) -> dict:
    """Begin a discussion thread for a Paused queue entry.

    Creates a new conversation in ~/ora/sessions/<id>/conversation.json
    seeded with one assistant message containing the entry's context, the
    initial options block (1 and 2; option 3 emerges once a substantive
    alternative is formulated), and the marker.

    Returns ``{"conversation_id": "...", "queue_entry_id": "...",
    "first_message": "...", "display_name": "..."}``.

    Raises ``ValueError`` when the queue id can't be found.
    """
    from oversight_queue import find_paused_by_id, link_discussion

    entry = find_paused_by_id(queue_id)
    if entry is None:
        raise ValueError(f"No Paused entry with id {queue_id!r}")

    if entry.discussion_conversation_id:
        # Already has a discussion — return the existing one
        return {
            "conversation_id": entry.discussion_conversation_id,
            "queue_entry_id": entry.id,
            "first_message": "",
            "display_name": _discussion_display_name(entry.name),
            "reused": True,
        }

    conversation_id = _new_conversation_id(entry)
    first_message = _build_seed_message(entry)
    display_name = _discussion_display_name(entry.name)

    _create_conversation_envelope(
        conversation_id=conversation_id,
        display_name=display_name,
        first_assistant_message=first_message,
        sessions_root=sessions_root,
    )

    link_discussion(entry.id, conversation_id)

    return {
        "conversation_id": conversation_id,
        "queue_entry_id": entry.id,
        "first_message": first_message,
        "display_name": display_name,
        "reused": False,
    }


def _build_seed_message(entry) -> str:
    """First AI message in a resolution thread — context + options + marker."""
    event = entry.event or {}
    verdict = entry.verdict or {}
    project = event.get("project_nexus", "(no project)")
    event_type = event.get("event_type", "Escalation")
    reasoning = (verdict.get("reasoning") or "").strip()
    if not reasoning:
        reasoning = (verdict.get("raw_output") or "").strip()
    if len(reasoning) > 4000:
        reasoning = reasoning[:4000] + "…"

    body_parts = [
        f"**Resolving:** {entry.name}",
        "",
        f"- **Project:** `{project}`",
        f"- **Event type:** `{event_type}`",
    ]
    if entry.redefinition:
        body_parts.append("- **Type:** redefinition proposal")
    if entry.forced_reason:
        body_parts.append(f"- **Forced reason:** {entry.forced_reason}")
    body_parts.append("")
    body_parts.append("**System reasoning:**")
    body_parts.append("")
    body_parts.append(reasoning or "_(no reasoning recorded)_")
    body_parts.append("")
    body_parts.append("---")
    body_parts.append("")
    body_parts.append("Ask whatever you need to decide. When ready, type a number to commit.")
    body_parts.append("")
    body_parts.append(_render_options_block(alternative=""))

    body = "\n".join(body_parts)
    return f"{body}\n\n{_marker_for(entry.id, alternative='')}"


def _render_options_block(alternative: str) -> str:
    """Render the user-facing numbered options. Option 3 only appears when
    ``alternative`` is non-empty and substantive."""
    lines = ["**Resolution options:**"]
    lines.append("1. Approve as proposed")
    lines.append("2. Deny")
    if alternative.strip():
        lines.append("3. Apply this alternative:")
        lines.append("")
        for para in alternative.strip().split("\n"):
            lines.append(f"    {para}" if para.strip() else "")
        lines.append("")
    lines.append("")
    lines.append("Type **1**, **2**, or **3** to commit. Anything else continues the discussion.")
    return "\n".join(lines)


def _discussion_display_name(entry_name: str) -> str:
    """Title for the discussion conversation."""
    return f"Resolve: {entry_name}"


def _new_conversation_id(entry) -> str:
    """Stable, content-derived conversation id for a discussion thread."""
    import hashlib
    seed = f"resolution|{entry.id}|{entry.queued_at}"
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"resolve-{h}"


def _create_conversation_envelope(
    conversation_id: str,
    display_name: str,
    first_assistant_message: str,
    sessions_root: Optional[str] = None,
):
    """Write a fresh conversation.json with one seed assistant message.

    If an envelope already exists at the target path, do not overwrite — the
    discussion has already been opened (start_resolution handles this case
    upstream by returning the existing conversation_id).
    """
    from datetime import datetime as _dt
    root = os.path.expanduser(sessions_root or "~/ora/sessions/")
    conv_dir = os.path.join(root, conversation_id)
    env_path = os.path.join(conv_dir, "conversation.json")
    if os.path.isfile(env_path):
        return
    os.makedirs(conv_dir, exist_ok=True)
    now_iso = _dt.now().isoformat(timespec="seconds")
    envelope = {
        "conversation_id": conversation_id,
        "display_name": display_name,
        "tag": "",
        "created": now_iso,
        "parent_conversation_id": None,
        "fork_point_chunk_id": None,
        "is_welcome": False,
        "messages": [
            {
                "role": "assistant",
                "content": first_assistant_message,
                "timestamp": now_iso,
            }
        ],
    }
    with open(env_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)


# ---------- continue_resolution ----------

def continue_resolution(
    ctx: ContinuationContext,
    history: list,
    latest_user_text: str,
    conversation_id: str = "",
    config: Optional[dict] = None,
) -> str:
    """Advance an in-progress resolution by one turn.

    Branches on the user's input:
      "1" / "2" / "3" → commit the corresponding action, return final message
      anything else  → continued discussion: small-model call updates the
                       AI's response + possibly produces a new alternative
                       proposal; returns the response with marker re-attached.
    """
    config = config or {}
    user_text = (latest_user_text or "").strip()

    if user_text == "1":
        return _commit_approve_as_proposed(ctx, conversation_id)
    if user_text == "2":
        return _commit_deny(ctx, history, conversation_id)
    if user_text == "3":
        return _commit_apply_alternative(ctx, conversation_id)

    # Continued discussion
    return _generate_discussion_turn(ctx, history, user_text, config)


def _commit_approve_as_proposed(ctx: ContinuationContext, conversation_id: str) -> str:
    """User typed 1 — apply redefinition as the system originally proposed."""
    from oversight_queue import find_raw_index_by_id
    from redefinition_handler import approve_redefinition

    raw_index = find_raw_index_by_id(ctx.queue_id)
    if raw_index is None:
        return "[Queue entry no longer present — perhaps already resolved.]"

    result = approve_redefinition(raw_index, proposed_definition=None)
    if not result.success:
        return f"[Approval failed: {result.error}]"

    _mark_conversation_resolved(conversation_id)
    return (
        "**Approved as proposed.**\n\n"
        f"- **Archived PED:** `{result.archived_path}`\n"
        f"- **New PED:** `{result.new_ped_path}`\n"
        f"- **Re-evaluation queued:** `{result.reeval_task_id}`"
    )


def _commit_apply_alternative(ctx: ContinuationContext, conversation_id: str) -> str:
    """User typed 3 — apply the alternative content from the marker."""
    if not (ctx.last_alternative or "").strip():
        return (
            "[Option 3 has no alternative content yet — keep discussing until "
            "the AI proposes a substantive alternative, then type 3 again.]"
        )

    from oversight_queue import find_raw_index_by_id
    from redefinition_handler import approve_redefinition

    raw_index = find_raw_index_by_id(ctx.queue_id)
    if raw_index is None:
        return "[Queue entry no longer present — perhaps already resolved.]"

    result = approve_redefinition(
        raw_index, proposed_definition=ctx.last_alternative
    )
    if not result.success:
        return f"[Apply-alternative failed: {result.error}]"

    _mark_conversation_resolved(conversation_id)
    return (
        "**Applied alternative.**\n\n"
        f"- **Archived PED:** `{result.archived_path}`\n"
        f"- **New PED:** `{result.new_ped_path}`\n"
        f"- **Re-evaluation queued:** `{result.reeval_task_id}`\n\n"
        "**Alternative applied:**\n\n"
        f"{ctx.last_alternative.strip()}"
    )


def _commit_deny(
    ctx: ContinuationContext, history: list, conversation_id: str,
) -> str:
    """User typed 2 — deny the redefinition with a reason from recent context."""
    from oversight_queue import find_raw_index_by_id
    from redefinition_handler import deny_redefinition

    raw_index = find_raw_index_by_id(ctx.queue_id)
    if raw_index is None:
        return "[Queue entry no longer present — perhaps already resolved.]"

    reason = _extract_deny_reason(history)

    result = deny_redefinition(raw_index, reason=reason)
    if not result.success:
        return f"[Denial failed: {result.error}]"

    _mark_conversation_resolved(conversation_id)
    suffix = f"\n\n**Reason recorded:** {reason}" if reason else ""
    return f"**Denied.** Queue entry removed.{suffix}"


def _extract_deny_reason(history: list) -> str:
    """Pull a denial reason from the most recent user turns. Stitches up to
    the last 3 user turns if they're substantive (>5 chars and not a single
    digit). Caps at 500 chars."""
    parts: list[str] = []
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        content = (msg.get("content", "") or "").strip()
        if not content or len(content) <= 5:
            continue
        if content in ("1", "2", "3"):
            continue
        parts.append(content)
        if len(parts) >= 3:
            break
    if not parts:
        return ""
    parts.reverse()
    joined = " | ".join(parts)
    return joined[:500]


# ---------- discussion turn (continued conversation) ----------

def _generate_discussion_turn(
    ctx: ContinuationContext, history: list, user_text: str, config: dict,
) -> str:
    """Make a small-model call: read the conversation, respond to the user,
    and emit a possibly-updated alternative proposal in the structured tail.

    The model is instructed to:
      1. Answer the user's question or engage with their reasoning.
      2. If a substantive alternative has emerged, formulate it concretely.
      3. Always end with the options block.
    """
    try:
        from boot import call_model, get_slot_endpoint, get_active_endpoint
    except Exception:
        return _fallback_response(ctx, "Unable to load model — keep discussing.")

    endpoint = (
        get_slot_endpoint(config, RESOLUTION_SLOT) or get_active_endpoint(config)
    )
    if endpoint is None:
        return _fallback_response(ctx, "No model endpoint available.")

    conv_text = _format_conversation_for_prompt(history, user_text)

    prompt = (
        "You are mediating a discussion between the user and an oversight system "
        "to resolve a paused decision. Engage substantively with what the user "
        "asks; explain context as needed; help them reach a defined endpoint.\n\n"
        "Output format — strict. Your response has TWO parts:\n"
        "  PART 1: a free-form discussion response (markdown, multi-paragraph "
        "ok). Address the user's most recent message.\n"
        "  PART 2: a structured tail in this exact format:\n\n"
        "ALTERNATIVE:\n"
        "<the proposed alternative resolution as a complete, concrete text "
        "the user could approve verbatim. Multi-paragraph ok. Write \"(none)\" "
        "if no substantive alternative has emerged from the discussion yet.>\n\n"
        "Do NOT include the numbered options list — that is rendered "
        "separately. Do NOT add prose after the ALTERNATIVE block.\n\n"
        "===\n"
        "CONVERSATION SO FAR:\n"
        f"{conv_text}\n\n"
        f"USER'S LATEST MESSAGE:\n{user_text}\n"
    )
    messages = [
        {"role": "system", "content": "You are a careful discussion mediator."},
        {"role": "user", "content": prompt},
    ]

    try:
        response = call_model(messages, endpoint)
    except Exception as exc:
        return _fallback_response(ctx, f"Model call failed: {exc}")

    discussion, alternative = _split_response(response or "")
    if not discussion:
        discussion = "_(model returned no discussion content)_"

    return _wrap_with_options(
        discussion=discussion,
        queue_id=ctx.queue_id,
        alternative=alternative,
    )


def _split_response(response: str) -> tuple:
    """Pull discussion text + ALTERNATIVE block out of a model response.

    Returns (discussion_text, alternative_text). If the model didn't follow
    the format, falls back to (full_response, "").
    """
    m = re.search(r"ALTERNATIVE:\s*\n(.+?)\Z", response, re.DOTALL | re.IGNORECASE)
    if not m:
        return (response.strip(), "")
    alt = m.group(1).strip()
    discussion = response[:m.start()].rstrip()
    if alt.lower() in {"(none)", "none", "n/a", "none yet"}:
        alt = ""
    return (discussion, alt)


def _wrap_with_options(discussion: str, queue_id: str, alternative: str) -> str:
    """Compose discussion body + options block + marker."""
    options = _render_options_block(alternative)
    marker = _marker_for(queue_id, alternative)
    return f"{discussion.rstrip()}\n\n{options}\n\n{marker}"


def _fallback_response(ctx: ContinuationContext, note: str) -> str:
    """Graceful response when the model is unavailable. Keeps the marker so
    the next turn can re-try."""
    discussion = (
        f"_{note}_\n\n"
        "I can't help refine the proposal right now without a model. You can "
        "still type **1** to approve as proposed or **2** to deny."
    )
    return _wrap_with_options(
        discussion=discussion,
        queue_id=ctx.queue_id,
        alternative=ctx.last_alternative,
    )


def _format_conversation_for_prompt(history: list, latest_user_text: str) -> str:
    """Render history for the discussion-mediator prompt. Strips markers
    from prior assistant turns so the model doesn't see its own scaffolding."""
    lines = []
    for msg in history:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "") or ""
        content = MARKER_PATTERN.sub("", content)
        # Also strip any prior options blocks
        content = re.sub(
            r"\*\*Resolution options:\*\*.*?(?:\n\n|\Z)",
            "",
            content,
            flags=re.DOTALL,
        )
        content = content.strip()
        if not content:
            continue
        if len(content) > 1500:
            content = content[:1500] + "…"
        lines.append(f"{role.upper()}: {content}")
    return "\n\n".join(lines)


# ---------- post-resolution ----------

def _mark_conversation_resolved(conversation_id: str):
    """Append "(resolved)" to the discussion conversation's display_name.

    Best-effort — failure here doesn't block resolution. Idempotent: if the
    suffix is already present, leaves the name alone.
    """
    if not conversation_id:
        return
    sessions_root = os.path.expanduser("~/ora/sessions/")
    env_path = os.path.join(sessions_root, conversation_id, "conversation.json")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path) as f:
            env = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    name = env.get("display_name", "") or ""
    if name.endswith(RESOLVED_SUFFIX):
        return
    env["display_name"] = (name + RESOLVED_SUFFIX).strip()
    try:
        with open(env_path, "w") as f:
            json.dump(env, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
