#!/usr/bin/env python3
"""
WP-5.3 — Spatial continuity across turns. Plus envelope-level ``tag`` for
stealth/private mode dispatch (V3 Phase 1.1, 2026-04-28).

This module owns the turn-to-turn persistence contract for visual state. Each
turn of a conversation may carry a ``spatial_representation``, an
``annotations`` payload, and/or a ``vision_extraction_result``. When the next
turn fires, the analytical pipeline receives the prior turn's spatial state
alongside the new input so the model sees the evolution of the user's
arrangement — not just the latest snapshot.

Conversation-level mode is carried on the envelope as ``tag`` (one of
``CONVERSATION_TAGS``). Set at conversation creation, immutable for the
life of the conversation. Used by close-out dispatch (purge / retain /
flag) and by RAG queries to filter private content.

Persistence surface
-------------------

``~/ora/sessions/<conversation_id>/conversation.json`` is the native
structured log for a conversation. Envelope shape:

    {
      "conversation_id": "<id>",
      "tag": "" | "stealth" | "private",
      "messages": [ ... ]
    }

Each message in ``messages[]`` is a ``{role, content, timestamp, ...}``
dict; WP-5.3 adds three optional fields per turn:

    {
      "role": "user",
      "content": "<text>",
      "timestamp": "...",
      "spatial_representation": { ... } | null,
      "annotations": [ ... ] | null,
      "vision_extraction_result": { ... } | null
    }

All three turn-level fields are optional. Missing fields are stored as
``null`` (not absent) so forward/backward compatibility is trivial: older
records without these keys are still loadable, and reading code always sees
``None`` for a missing slot.

Schema-version strategy
-----------------------

No ``schema_version`` field on the conversation.json envelope — the additive-
fields approach + null-default rule means existing files keep working without
migration. If we ever need to bump the shape (e.g. renaming a key), we'll
introduce ``schema_version: "1"`` at that point. Until then, absence of the
field means "v0 / unversioned".

Backwards compat
----------------

* A conversation.json written before WP-5.3 has no spatial_representation
  keys on its turns. :func:`get_prior_spatial_state` returns ``None`` for
  those and the caller skips the PRIOR-STATE fence.
* A conversation written before V3 Phase 1.1 has no ``tag`` field on the
  envelope. :func:`get_conversation_tag` returns ``""`` (standard mode) for
  those, and writes pass through ``save_turn_spatial_state`` preserve the
  absence — the field is added on the next save when a non-empty tag is
  supplied, otherwise the envelope keeps its original shape.
* A conversation passed as an in-memory ``history`` list (chat endpoint
  history arg) may or may not contain the spatial keys. Both shapes are
  accepted by :func:`get_prior_spatial_state`.

The helpers are deliberately pure-Python and free of Flask so they can be
imported from ``boot.py`` (server-agnostic) or from tests without a server.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default sessions root. Tests override via ``sessions_root=`` kwarg on
# :func:`save_turn_spatial_state` / :func:`load_conversation_json`.
_DEFAULT_SESSIONS_ROOT = Path.home() / "ora" / "sessions"

# The three optional turn fields WP-5.3 persists. Kept as a module-level
# tuple so :func:`save_turn_spatial_state` and tests can enumerate them.
TURN_SPATIAL_FIELDS: tuple[str, ...] = (
    "spatial_representation",
    "annotations",
    "vision_extraction_result",
)

# Valid conversation-level tag values (V3 Phase 1.1). Empty string is the
# default (standard mode); ``stealth`` and ``private`` carry the V3 mode
# semantics. Set at conversation creation, immutable thereafter.
CONVERSATION_TAGS: tuple[str, ...] = ("", "stealth", "private")


# ---------------------------------------------------------------------------
# Conversation JSON I/O
# ---------------------------------------------------------------------------


def _conversation_path(conversation_id: str, sessions_root: Path) -> Path:
    """Return the absolute path to the conversation.json for a given id."""
    return Path(sessions_root) / conversation_id / "conversation.json"


def load_conversation_json(
    conversation_id: str,
    sessions_root: Path | None = None,
) -> dict[str, Any] | None:
    """Read the conversation.json for a conversation_id, or None if missing.

    Returns the raw dict including the ``messages`` list. Never raises on
    parse error — corrupted files return ``None``, so callers can fall back
    to the in-memory ``history`` arg without blowing up the pipeline.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("messages"), list):
        return None
    return data


def save_turn_spatial_state(
    conversation_id: str,
    user_input: str,
    ai_response: str,
    *,
    spatial_representation: dict | None = None,
    annotations: dict | list | None = None,
    vision_extraction_result: dict | None = None,
    timestamp: str | None = None,
    tag: str = "",
    sessions_root: Path | None = None,
) -> Path | None:
    """Append a user+assistant pair to conversation.json with optional
    spatial fields on the user turn.

    Creates the session directory + file on first write. On subsequent
    writes, appends to ``messages[]`` preserving prior turns.

    The user turn carries the three optional spatial fields. The assistant
    turn is written with the same three fields set to ``None`` (reserved —
    future assistants may emit spatial state too). Keys are always present
    (never absent) so downstream code can rely on the shape.

    The ``tag`` argument carries the conversation-level mode (V3 Phase 1.1)
    and is honored on FIRST save only — when this call creates a new
    envelope, ``tag`` lands on the envelope. On subsequent calls the
    existing envelope's tag is preserved verbatim regardless of what
    ``tag`` is passed in (immutability for the life of the conversation).
    Invalid tags (not in ``CONVERSATION_TAGS``) silently coerce to ``""``.

    Returns the path written, or ``None`` on I/O failure (non-blocking; the
    persistence step must never break the conversation flow).
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    existing: dict[str, Any] | None = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = None
            elif not isinstance(existing.get("messages"), list):
                existing = None
        except (OSError, json.JSONDecodeError):
            existing = None

    # Resolve the tag to write. On a new envelope, validate the incoming
    # ``tag`` against CONVERSATION_TAGS (silently coerce invalid → ""). On
    # an existing envelope, preserve the prior tag verbatim — V3 Phase 1.1
    # immutability rule.
    if existing is None:
        from datetime import datetime as _dt
        envelope_tag = tag if tag in CONVERSATION_TAGS else ""
        # V3 Backlog 2C — auto-generate display_name from the first user
        # prompt (trimmed to 60 chars). The user can override via
        # POST /api/conversation/<id>/rename.
        first_prompt = (user_input or "").strip().replace("\n", " ")
        derived_name = first_prompt[:60] if first_prompt else ""
        existing = {
            "conversation_id":         conversation_id,
            "display_name":            derived_name,
            "tag":                     envelope_tag,
            "created":                 timestamp or _dt.now().isoformat(timespec="seconds"),
            "parent_conversation_id":  None,
            "fork_point_chunk_id":     None,
            "messages":                [],
        }
    else:
        # Backfill V3 Backlog 2C envelope fields on legacy envelopes that
        # pre-date this section. Default to "" / None. Never overwrite
        # values that are already set.
        if "tag" not in existing:
            existing["tag"] = ""
        if "created" not in existing:
            from datetime import datetime as _dt
            existing["created"] = timestamp or _dt.now().isoformat(timespec="seconds")
        if "parent_conversation_id" not in existing:
            existing["parent_conversation_id"] = None
        if "fork_point_chunk_id" not in existing:
            existing["fork_point_chunk_id"] = None

    # Normalize annotations payload: accept either wrapper dict or bare list.
    annotations_normalized: Any
    if annotations is None:
        annotations_normalized = None
    elif isinstance(annotations, dict) and "annotations" in annotations:
        annotations_normalized = annotations.get("annotations")
    elif isinstance(annotations, list):
        annotations_normalized = annotations
    else:
        # Unknown shape — store verbatim rather than dropping it.
        annotations_normalized = annotations

    user_turn = {
        "role": "user",
        "content": user_input,
        "timestamp": timestamp,
        "spatial_representation": spatial_representation,
        "annotations": annotations_normalized,
        "vision_extraction_result": vision_extraction_result,
    }
    assistant_turn = {
        "role": "assistant",
        "content": ai_response,
        "timestamp": timestamp,
        "spatial_representation": None,
        "annotations": None,
        "vision_extraction_result": None,
    }

    existing["messages"].append(user_turn)
    existing["messages"].append(assistant_turn)

    try:
        path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


# ---------------------------------------------------------------------------
# Prior-state retrieval
# ---------------------------------------------------------------------------


def get_prior_spatial_state(
    conversation_id: str,
    history: list | None,
    *,
    sessions_root: Path | None = None,
) -> dict | None:
    """Return the most recent user-turn spatial_representation, or None.

    Search order:
      1. Walk ``history`` backwards (cheapest — already in memory).
      2. If nothing found, load conversation.json from disk and walk its
         ``messages[]`` backwards.

    Only user turns are considered (assistant/system turns don't carry
    user-drawn spatial state). A snapshot is returned (``copy.deepcopy``) so
    the caller can mutate it without corrupting the history.
    """
    # Walk in-memory history first.
    if history and isinstance(history, list):
        for turn in reversed(history):
            if not isinstance(turn, dict):
                continue
            if turn.get("role") != "user":
                continue
            rep = turn.get("spatial_representation")
            if rep:
                return copy.deepcopy(rep)

    # Fall through to disk.
    data = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if data is None:
        return None
    for turn in reversed(data.get("messages") or []):
        if not isinstance(turn, dict):
            continue
        if turn.get("role") != "user":
            continue
        rep = turn.get("spatial_representation")
        if rep:
            return copy.deepcopy(rep)
    return None


def get_prior_annotations(
    conversation_id: str,
    history: list | None,
    *,
    sessions_root: Path | None = None,
) -> list | None:
    """Return the most recent user-turn annotations list, or None.

    Same search rule as :func:`get_prior_spatial_state`. Persistent edit
    intent tends to span turns, so we expose this for the rare mode where
    the model needs to see what the user previously wanted annotated.
    """
    if history and isinstance(history, list):
        for turn in reversed(history):
            if not isinstance(turn, dict):
                continue
            if turn.get("role") != "user":
                continue
            annots = turn.get("annotations")
            if annots:
                return copy.deepcopy(annots)

    data = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if data is None:
        return None
    for turn in reversed(data.get("messages") or []):
        if not isinstance(turn, dict):
            continue
        if turn.get("role") != "user":
            continue
        annots = turn.get("annotations")
        if annots:
            return copy.deepcopy(annots)
    return None


# ---------------------------------------------------------------------------
# Conversation-level tag (V3 Phase 1.1)
# ---------------------------------------------------------------------------


def get_conversation_tag(
    conversation_id: str,
    sessions_root: Path | None = None,
) -> str:
    """Return the conversation-level ``tag`` for a conversation.

    Reads conversation.json from disk and returns the envelope's ``tag``
    field. Returns ``""`` (standard mode) if the file is missing,
    unreadable, the field is absent (legacy envelopes), or the value is
    not in ``CONVERSATION_TAGS``.

    Used by close-out dispatch (purge / retain / flag) and by RAG queries
    that need to filter on conversation-level mode without loading the
    full message history.
    """
    data = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if data is None:
        return ""
    tag = data.get("tag", "")
    if not isinstance(tag, str) or tag not in CONVERSATION_TAGS:
        return ""
    return tag


# ---------------------------------------------------------------------------
# Conversation enumeration + read tracking (V3 Phase 2)
# ---------------------------------------------------------------------------


def _derive_title(messages: list, max_len: int = 60) -> str:
    """Derive a short title from the first user message in the conversation.

    Returns an empty string if no user message is present yet (e.g.,
    envelope created but pipeline not finished). Truncates to ``max_len``
    characters with an ellipsis when longer; collapses whitespace.
    """
    if not isinstance(messages, list):
        return ""
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        # Collapse internal whitespace; trim
        single_line = " ".join(content.split())
        if len(single_line) <= max_len:
            return single_line
        return single_line[: max_len - 1].rstrip() + "…"
    return ""


def _last_activity_at(messages: list) -> str | None:
    """Return the timestamp of the most recent message, or None."""
    if not isinstance(messages, list):
        return None
    for m in reversed(messages):
        if not isinstance(m, dict):
            continue
        ts = m.get("timestamp")
        if isinstance(ts, str) and ts:
            return ts
    return None


def iter_conversations(
    sessions_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Enumerate conversations under ``sessions_root`` and return summary
    dicts.

    Each summary is shaped::

        {
          "conversation_id": "<id>",
          "tag": "" | "stealth" | "private",
          "title": "<derived from first user message>",
          "message_count": <int>,
          "last_activity_at": "<iso timestamp>" | None,
          "last_read_at": "<iso timestamp>" | None,
        }

    Conversations whose conversation.json is missing or unreadable are
    skipped silently (this is a list-for-display helper, not a strict
    audit). Returned in arbitrary order; callers sort/group as needed.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    if not root.exists() or not root.is_dir():
        return []

    summaries: list[dict[str, Any]] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        conv_path = entry / "conversation.json"
        if not conv_path.exists():
            continue
        try:
            data = json.loads(conv_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        messages = data.get("messages") or []
        tag = data.get("tag", "")
        if not isinstance(tag, str) or tag not in CONVERSATION_TAGS:
            tag = ""
        last_read = data.get("last_read_at")
        if not isinstance(last_read, str):
            last_read = None
        is_welcome = bool(data.get("is_welcome"))
        # V3 Backlog 2C — user-supplied display_name overrides the derived
        # title when set; otherwise iter_conversations derives the title
        # from the first user message.
        display_name = data.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            title = display_name.strip()
        else:
            title = "Welcome to Ora" if is_welcome else _derive_title(messages)
        last_status = data.get("last_status") if isinstance(data.get("last_status"), str) else None
        last_error_summary = data.get("last_error_summary") if isinstance(data.get("last_error_summary"), str) else None
        # V3 Backlog 3F — user-pinned conversations surface in the Pinned
        # group at the top of the sidebar (independent of the WELCOME
        # auto-pin via is_welcome).
        user_pinned = bool(data.get("pinned"))
        summaries.append({
            "conversation_id": entry.name,
            "tag": tag,
            "title": title,
            "message_count": len(messages) if isinstance(messages, list) else 0,
            "last_activity_at": _last_activity_at(messages),
            "last_read_at": last_read,
            "is_welcome": is_welcome,
            "pinned": user_pinned,
            "last_status": last_status,
            "last_error_summary": last_error_summary,
        })
    return summaries


# V3 spec §6.2 — WELCOME thread reserved id and envelope marker. The
# thread is created on first launch when the sessions directory has no
# existing conversations, pinned to the top of the sidebar regardless of
# recency, and exempt from automatic cleanup. The user can manually
# delete it.
WELCOME_CONVERSATION_ID = "welcome"

WELCOME_PLACEHOLDER_BODY = """**Welcome to Ora**

This is your orientation thread. The full help system is under construction.

Once it's ready, this thread will offer:
- A guided introduction to Ora's interface and the eight-step pipeline
- Searchable answers about how modes, gears, and frameworks work
- A place to ask Ora about itself, with answers that accumulate here

For now, this is a placeholder. The thread is pinned to the top of your
conversation list and won't be removed by automatic cleanup. You can
manually delete it from the sidebar if you don't want it.

— Under construction —
"""


def ensure_welcome_thread(
    sessions_root: Path | None = None,
    *,
    only_if_first_launch: bool = True,
) -> bool:
    """Create the WELCOME conversation if it doesn't already exist.

    V3 spec §6.2 — first-launch behaviour. By default this only fires
    when the sessions directory has no existing conversations (a true
    first launch). Pass ``only_if_first_launch=False`` to force creation
    even if the user has prior conversations (used by tests or by an
    explicit "restore the welcome thread" UI action).

    Returns True if the WELCOME envelope was created on this call,
    False if it already existed or first-launch gating prevented it.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    welcome_path = _conversation_path(WELCOME_CONVERSATION_ID, root)
    if welcome_path.exists():
        return False

    if only_if_first_launch and root.exists() and root.is_dir():
        # Check whether ANY conversation.json files exist in the sessions
        # directory. If yes, this isn't a first launch — bail.
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            if (entry / "conversation.json").exists():
                return False

    welcome_path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = _dt.now().isoformat(timespec="seconds")
    envelope = {
        "conversation_id":         WELCOME_CONVERSATION_ID,
        "display_name":            "Welcome to Ora",
        "tag":                     "",
        "created":                 now_iso,
        "parent_conversation_id":  None,
        "fork_point_chunk_id":     None,
        "is_welcome":              True,
        "messages": [
            {
                "role":                      "assistant",
                "content":                   WELCOME_PLACEHOLDER_BODY,
                "timestamp":                 now_iso,
                "spatial_representation":    None,
                "annotations":               None,
                "vision_extraction_result":  None,
            }
        ],
    }
    try:
        welcome_path.write_text(
            json.dumps(envelope, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def fork_conversation(
    parent_id: str,
    new_id: str,
    *,
    fork_point_chunk_id: str | None = None,
    sessions_root: Path | None = None,
    timestamp: str | None = None,
) -> dict | None:
    """Create a child conversation that inherits the parent's tag + history.

    V3 spec §4.2 / §5.2 (fork from default) and §4.3 / §5.3 (fork from
    mode). The child conversation:

      * gets a fresh ``conversation_id`` (caller-supplied to keep the
        content-derived naming convention in the caller's hands)
      * inherits the parent's ``tag`` (forks of stealth are stealth;
        forks of private are private; forks of standard are standard)
      * gets ``parent_conversation_id`` pointing at the parent (V3
        Backlog 2C field name; this is the unambiguous fork-ancestry key
        used by pipeline reconstruction in conversation_closeout)
      * gets ``fork_point_chunk_id`` — the parent's chunk_id where this
        fork was created. None if not supplied. Uses chunk_id rather than
        turn number because pair_num resets within a session, so chunk_id
        is the only unambiguous global pointer.
      * gets ``created`` (the fork creation time) and a legacy
        ``forked_at`` mirror for any older callers
      * carries forward a deep copy of the parent's ``messages[]`` so the
        child has full conversational context from the fork point

    Returns the new envelope dict on success, or None if the parent is
    missing / unreadable.

    The parent envelope is NOT modified — fork is non-destructive.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    parent = load_conversation_json(parent_id, sessions_root=root)
    if parent is None:
        return None

    # Validate parent shape; default to standard mode if tag malformed.
    parent_tag = parent.get("tag", "")
    if not isinstance(parent_tag, str) or parent_tag not in CONVERSATION_TAGS:
        parent_tag = ""
    parent_messages = parent.get("messages") or []
    if not isinstance(parent_messages, list):
        parent_messages = []
    # Inherit display name with a "(fork)" suffix so the user sees a
    # distinct row but can rename it.
    parent_display = parent.get("display_name") or ""
    if isinstance(parent_display, str) and parent_display.strip():
        derived_display = (parent_display.strip() + " (fork)")[:200]
    else:
        derived_display = ""

    forked_at = timestamp or _dt.now().isoformat(timespec="seconds")

    child = {
        "conversation_id":         new_id,
        "display_name":            derived_display,
        "tag":                     parent_tag,
        "created":                 forked_at,
        "parent_conversation_id":  parent_id,
        "fork_point_chunk_id":     fork_point_chunk_id,
        "forked_at":               forked_at,
        "messages":                copy.deepcopy(parent_messages),
    }

    child_path = _conversation_path(new_id, root)
    try:
        child_path.parent.mkdir(parents=True, exist_ok=True)
        child_path.write_text(
            json.dumps(child, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return child


def mark_conversation_errored(
    conversation_id: str,
    summary: str,
    *,
    sessions_root: Path | None = None,
    timestamp: str | None = None,
) -> Path | None:
    """Mark a conversation's most recent run as errored on its envelope.

    Backlog item 11. The pipeline writes a separate error chunk file
    when a run fails (Backlog 2D), but the V3 sidebar list is driven
    off conversation.json envelopes — so we mirror the error state on
    the envelope: ``last_status: "errored"`` + ``last_error_summary``.

    The list endpoint then groups conversations with that status into
    an Errored group, and the sidebar UI surfaces retry + dismiss
    actions per row.

    Returns the path written, or None if conversation.json is
    missing / unreadable / unwriteable. Best-effort.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    data["last_status"]        = "errored"
    data["last_error_summary"] = summary or ""
    data["last_errored_at"]    = timestamp or _dt.now().isoformat(timespec="seconds")

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


def clear_conversation_error(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
) -> Path | None:
    """Dismiss the errored status on a conversation envelope.

    Companion to ``mark_conversation_errored``. Used by the dismiss
    action in the sidebar's Errored group, and by retry-on-success.
    Returns the path written, or None if conversation.json is missing.
    Removes ``last_status`` / ``last_error_summary`` / ``last_errored_at``
    if present; leaves the envelope otherwise untouched.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    changed = False
    for key in ("last_status", "last_error_summary", "last_errored_at"):
        if key in data:
            data.pop(key, None)
            changed = True
    if not changed:
        return path  # idempotent; nothing to write

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


def mark_conversation_read(
    conversation_id: str,
    *,
    timestamp: str | None = None,
    sessions_root: Path | None = None,
) -> Path | None:
    """Set the envelope's ``last_read_at`` field to ``timestamp`` (or now).

    Used by the UI to record that the user has viewed a conversation's
    output. The list endpoint compares ``last_activity_at`` against
    ``last_read_at`` to decide whether the conversation belongs in the
    Unread group.

    Returns the path written, or None if conversation.json is missing /
    unreadable / unwriteable. Best-effort — never raises.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    data["last_read_at"] = timestamp or _dt.now().isoformat(timespec="seconds")

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


def set_display_name(
    conversation_id: str,
    display_name: str,
    *,
    sessions_root: Path | None = None,
) -> Path | None:
    """Write the user-supplied ``display_name`` to the conversation envelope.

    V3 Backlog 2C — display_name is auto-generated from the first prompt
    (in iter_conversations title derivation) but the user can override it
    via this helper. The conversation_id is unchanged; only the surface
    name shown in the sidebar and output-pane header is affected.

    Empty string clears the override (UI falls back to derived title).
    Returns the path written, or None if the envelope is missing.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    cleaned = (display_name or "").strip()
    if cleaned:
        data["display_name"] = cleaned[:200]
    else:
        data.pop("display_name", None)

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


def set_conversation_pinned(
    conversation_id: str,
    pinned: bool,
    *,
    sessions_root: Path | None = None,
) -> Path | None:
    """Toggle the user-pinned state on the conversation envelope.

    V3 Backlog 3F — user-pinned conversations surface in the sidebar's
    Pinned group at the top of the list. WELCOME's auto-pin via
    ``is_welcome`` is independent of this field; the two coexist.

    Returns the path written, or None if the envelope is missing.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    if pinned:
        data["pinned"] = True
    else:
        data.pop("pinned", None)

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return None
    return path


__all__ = [
    "TURN_SPATIAL_FIELDS",
    "CONVERSATION_TAGS",
    "WELCOME_CONVERSATION_ID",
    "WELCOME_PLACEHOLDER_BODY",
    "load_conversation_json",
    "save_turn_spatial_state",
    "get_prior_spatial_state",
    "get_prior_annotations",
    "get_conversation_tag",
    "iter_conversations",
    "mark_conversation_read",
    "mark_conversation_errored",
    "clear_conversation_error",
    "fork_conversation",
    "ensure_welcome_thread",
    "set_display_name",
    "set_conversation_pinned",
]
