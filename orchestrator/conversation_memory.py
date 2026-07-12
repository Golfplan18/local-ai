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
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

try:
    from active_project import (
        DEFAULT as _DEFAULT_PROJECT_ID,
        canonicalize_project_nexus,
    )
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator.active_project import (
        DEFAULT as _DEFAULT_PROJECT_ID,
        canonicalize_project_nexus,
    )


# ---------------------------------------------------------------------------
# Per-conversation write locks
# ---------------------------------------------------------------------------
# Two simultaneous writes to the same conversation.json would race and
# last-writer-wins — the losing turn's appended user+assistant pair would
# silently disappear from the envelope. The atomic .tmp+rename added in
# sweep 3 prevented torn files but didn't prevent the lost-update race.
#
# A per-conversation Lock serialises the read-modify-write sequence so
# both turns land. Different conversations still write in parallel.
_conv_locks_guard = threading.Lock()
_conv_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _conversation_write_lock(conversation_id: str) -> threading.Lock:
    """Return the per-conversation Lock, creating it on first access."""
    with _conv_locks_guard:
        return _conv_locks[conversation_id]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default sessions root. Tests override via ``sessions_root=`` kwarg on
# :func:`save_turn_spatial_state` / :func:`load_conversation_json`.
# Flows from runtime_paths (ORA_HOME-relocatable) so the envelope writer
# and the stealth purge (conversation_closeout) agree on location.
_DEFAULT_SESSIONS_ROOT = _rp.ORA_HOME / "sessions"

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


def normalize_project_ids(project_ids: Any) -> list[str]:
    """Normalize explicit project memberships while preserving order.

    Commons is a universal view, not a stored membership.  Both its current
    and legacy sentinels therefore collapse out of an envelope, along with
    empty/non-string entries and duplicates.
    """
    if not isinstance(project_ids, (list, tuple)):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for project_id in project_ids:
        if not isinstance(project_id, str):
            continue
        slug = canonicalize_project_nexus(project_id)
        if slug == _DEFAULT_PROJECT_ID or slug in seen:
            continue
        seen.add(slug)
        cleaned.append(slug)
    return cleaned


# ---------------------------------------------------------------------------
# Conversation JSON I/O
# ---------------------------------------------------------------------------


def _conversation_path(conversation_id: str, sessions_root: Path) -> Path:
    """Return the absolute path to the conversation.json for a given id."""
    return Path(sessions_root) / conversation_id / "conversation.json"


def _atomic_write_envelope(path: Path, data: dict[str, Any]) -> bool:
    """Atomically replace an envelope while its sidecar lock is held."""
    tmp_path = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
        return True
    except OSError:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _read_normalized_envelope(
    conversation_id: str,
    root: Path,
    *,
    require_messages: bool,
    persist_heal: bool = True,
) -> dict[str, Any] | None:
    """Read one envelope and remove explicit Commons memberships.

    The targeted runtime heal is performed under the conversation's write
    lock and uses an atomic replace.  This makes a mixed-version envelope safe
    for both current callers and a later pre-rename rollback before the data is
    exposed through APIs or counts.
    """
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if require_messages and not isinstance(data.get("messages"), list):
        return None
    normalized = normalize_project_ids(data.get("project_ids"))
    needs_heal = "project_ids" in data and data.get("project_ids") != normalized
    data["project_ids"] = normalized
    if not (needs_heal and persist_heal):
        return data

    # Only the rare mixed/default-sentinel case pays for a sidecar lock. Reread
    # after acquiring it so an intervening turn or metadata mutation cannot be
    # replaced by the stale pre-lock snapshot.
    with _conversation_write_lock(conversation_id):
        try:
            with _rp.locked_file(path):
                try:
                    current = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return data
                if not isinstance(current, dict):
                    return data
                if require_messages and not isinstance(current.get("messages"), list):
                    return data
                current_normalized = normalize_project_ids(current.get("project_ids"))
                current_needs_heal = (
                    "project_ids" in current
                    and current.get("project_ids") != current_normalized
                )
                current["project_ids"] = current_normalized
                if current_needs_heal:
                    _atomic_write_envelope(path, current)
                return current
        except (OSError, TimeoutError):
            # Persistence is best-effort. The pre-lock snapshot was already
            # parsed and normalized, so never turn lock contention into a
            # transient API 404/list omission.
            return data


def _mutate_conversation_envelope(
    conversation_id: str,
    root: Path,
    mutate,
) -> Path | None:
    """Normalize, mutate, and atomically rewrite one conversation envelope."""
    path = _conversation_path(conversation_id, root)
    if not path.exists():
        return None
    with _conversation_write_lock(conversation_id):
        try:
            with _rp.locked_file(path):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
                if not isinstance(data, dict):
                    return None
                data["project_ids"] = normalize_project_ids(data.get("project_ids"))
                mutate(data)
                return path if _atomic_write_envelope(path, data) else None
        except (OSError, TimeoutError):
            return None


def load_conversation_json(
    conversation_id: str,
    sessions_root: Path | None = None,
) -> dict[str, Any] | None:
    """Read the conversation.json for a conversation_id, or None if missing.

    Returns the canonical dict including the ``messages`` list. Explicit
    ``commons`` / legacy ``general`` memberships are removed from the outward
    value and persisted through a best-effort atomic heal. Never raises on
    parse error — corrupted files return ``None``, so callers can fall back to
    the in-memory ``history`` arg without blowing up the pipeline.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    return _read_normalized_envelope(
        conversation_id,
        root,
        require_messages=True,
        persist_heal=True,
    )


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
    project_ids: list[str] | None = None,
    trace_ref: str | None = None,
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

    The ``project_ids`` argument (G1.33) carries the explicit project
    memberships (by nexus slug) to stamp on a NEW envelope, sourced from the
    active-project pointer at the call site. Like ``tag`` it is honored on
    FIRST save only — an existing envelope's ``project_ids`` is preserved
    semantically (membership is edited via the project modal, not per turn),
    while malformed/default sentinels are normalized on write.
    ``None`` / empty means the default ``Commons`` project.  Default
    sentinels are discarded rather than stored as explicit membership.

    The ``trace_ref`` argument (trace manifest, Chunk 0) is the turn's
    pipeline-trace ref ("<conversation_id>/<turn_timestamp>", relative to
    the trace root). Stamped on the ASSISTANT turn — the turn the trace
    explains. ``None`` (stealth / tracing off / no trace) writes ``null``;
    the key is always present, matching the reserved-``None`` field
    convention on the assistant turn.

    Returns the path written, or ``None`` on I/O failure (non-blocking; the
    persistence step must never break the conversation flow).
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(conversation_id, root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    # Per-conversation lock around the read-modify-write so concurrent
    # writes to the SAME conversation can't last-writer-wins each other.
    # The advisory sidecar lock extends that serialization across duplicate
    # module identities and processes; different conversations still write in
    # parallel.
    with _conversation_write_lock(conversation_id):
        try:
            with _rp.locked_file(path):
                return _do_write(path, conversation_id, user_input, ai_response,
                                 tag, timestamp, spatial_representation,
                                 annotations, vision_extraction_result,
                                 project_ids, trace_ref)
        except (OSError, TimeoutError):
            return None


def _do_write(
    path: Path,
    conversation_id: str,
    user_input: str,
    ai_response: str,
    tag: str,
    timestamp: str | None,
    spatial_representation: dict | None,
    annotations: dict | list | None,
    vision_extraction_result: dict | None,
    project_ids: list[str] | None = None,
    trace_ref: str | None = None,
) -> Path | None:
    """Inner read-modify-write helper. Runs inside the per-conversation
    lock; do not call directly."""
    existing: dict[str, Any] | None = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = None
            elif not isinstance(existing.get("messages"), list):
                existing = None
        except (OSError, json.JSONDecodeError) as _read_exc:
            # A corrupt conversation.json was previously silently
            # overwritten with a fresh envelope — discarding every prior
            # turn. Now: move the corrupt file aside to a .corrupt-<ts>
            # sidecar so the data is recoverable, log loudly to stderr,
            # then continue with a fresh envelope so the current turn
            # doesn't fail. Manual recovery is possible from the sidecar.
            existing = None
            try:
                import sys as _sys
                from datetime import datetime as _dt2
                ts = _dt2.utcnow().strftime("%Y%m%dT%H%M%SZ")
                sidecar = path.with_suffix(path.suffix + f".corrupt-{ts}")
                if not sidecar.exists():
                    path.rename(sidecar)
                print(
                    f"[conversation_memory] CORRUPT conversation.json "
                    f"for {conversation_id}: {_read_exc}; moved aside to "
                    f"{sidecar} for manual recovery. A fresh envelope "
                    f"will capture the current turn.",
                    file=_sys.stderr, flush=True,
                )
            except Exception as _sidecar_exc:
                import sys as _sys2
                print(
                    f"[conversation_memory] CORRUPT conversation.json "
                    f"for {conversation_id} AND failed to move it aside: "
                    f"read_error={_read_exc} move_error={_sidecar_exc}",
                    file=_sys2.stderr, flush=True,
                )

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
            "project_ids":             normalize_project_ids(project_ids),
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
        # Preserve real memberships, but lazily heal legacy/default sentinels
        # and malformed values whenever an envelope is written.
        existing["project_ids"] = normalize_project_ids(existing.get("project_ids"))

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
        "trace_ref": trace_ref,
    }

    existing["messages"].append(user_turn)
    existing["messages"].append(assistant_turn)

    return path if _atomic_write_envelope(path, existing) else None


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
    *,
    include_closed: bool = False,
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
          "project_ids": ["<nexus slug>", ...],   # [] == Commons (G1.33)
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
        data = _read_normalized_envelope(
            entry.name,
            root,
            require_messages=False,
            persist_heal=True,
        )
        if data is None:
            continue
        is_closed = data.get("closed") is True
        if is_closed and not include_closed:
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
            "closed": is_closed,
            "parent_conversation_id": (
                data.get("parent_conversation_id")
                if isinstance(data.get("parent_conversation_id"), str) else None
            ),
            "fork_point_chunk_id": (
                data.get("fork_point_chunk_id")
                if isinstance(data.get("fork_point_chunk_id"), str) else None
            ),
            "project_ids": list(data.get("project_ids") or []),
        })
    return summaries


# V3 spec §6.2 — WELCOME Dialogue reserved id and envelope marker. The
# Dialogue is created on first launch when the sessions directory has no
# existing Dialogues, pinned to the top of the sidebar regardless of
# recency, and exempt from automatic cleanup. The user can manually
# delete it.
WELCOME_CONVERSATION_ID = "welcome"

_WELCOME_PLACEHOLDER_LEGACY_BODY = """**Welcome to Ora**

This is your orientation thread. The full help system is under construction.

Once it's ready, this thread will offer:
- A guided introduction to Ora's interface and the eight-step pipeline
- Searchable answers about how modes, gears, and frameworks work
- A place to ask Ora about itself, with answers that accumulate here

For now, this is a placeholder. The thread is pinned to the top of your
Dialogue list and won't be removed by automatic cleanup. You can
manually delete it from the sidebar if you don't want it.

— Under construction —
"""

WELCOME_PLACEHOLDER_BODY = """**Welcome to Ora**

This is your orientation Dialogue. The full help system is under construction.

Once it's ready, this Dialogue will offer:
- A guided introduction to Ora's interface and the eight-step pipeline
- Searchable answers about how modes, gears, and frameworks work
- A place to ask Ora about itself, with answers that accumulate here

For now, this is a placeholder. The Dialogue is pinned to the top of your
Dialogue list and won't be removed by automatic cleanup. You can
manually delete it from the sidebar if you don't want it.

— Under construction —
"""


def _migrate_welcome_placeholder(welcome_path: Path) -> bool:
    """Upgrade only the exact pre-nomenclature WELCOME placeholder.

    User-edited WELCOME content is deliberately left untouched. The migration
    runs at startup through :func:`ensure_welcome_thread`, so existing installs
    self-heal without a scheduled or one-off cleanup job.
    """
    with _conversation_write_lock(WELCOME_CONVERSATION_ID):
        try:
            with _rp.locked_file(welcome_path):
                try:
                    envelope = json.loads(welcome_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return False
                if not isinstance(envelope, dict) or not envelope.get("is_welcome"):
                    return False
                messages = envelope.get("messages")
                if not isinstance(messages, list):
                    return False
                changed = False
                for message in messages:
                    if (
                        isinstance(message, dict)
                        and message.get("role") == "assistant"
                        and message.get("content") == _WELCOME_PLACEHOLDER_LEGACY_BODY
                    ):
                        message["content"] = WELCOME_PLACEHOLDER_BODY
                        changed = True
                if not changed:
                    return False
                envelope["project_ids"] = normalize_project_ids(
                    envelope.get("project_ids")
                )
                return _atomic_write_envelope(welcome_path, envelope)
        except (OSError, TimeoutError):
            return False


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

    Returns True if the WELCOME envelope was created on this call. An existing
    untouched legacy placeholder is upgraded in place but still returns False;
    user-edited content is never rewritten.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    welcome_path = _conversation_path(WELCOME_CONVERSATION_ID, root)
    if welcome_path.exists():
        _migrate_welcome_placeholder(welcome_path)
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
        "project_ids":             [],
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
    with _conversation_write_lock(WELCOME_CONVERSATION_ID):
        try:
            with _rp.locked_file(welcome_path):
                if welcome_path.exists():
                    return False
                return _atomic_write_envelope(welcome_path, envelope)
        except (OSError, TimeoutError):
            return False


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

    # A fork stays in the same projects as its parent (G1.33).
    parent_projects = normalize_project_ids(parent.get("project_ids"))

    child = {
        "conversation_id":         new_id,
        "display_name":            derived_display,
        "tag":                     parent_tag,
        "created":                 forked_at,
        "parent_conversation_id":  parent_id,
        "fork_point_chunk_id":     fork_point_chunk_id,
        "forked_at":               forked_at,
        "project_ids":             list(parent_projects),
        "messages":                copy.deepcopy(parent_messages),
    }

    child_path = _conversation_path(new_id, root)
    try:
        child_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    with _conversation_write_lock(new_id):
        try:
            with _rp.locked_file(child_path):
                if not _atomic_write_envelope(child_path, child):
                    return None
        except (OSError, TimeoutError):
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

    def mutate(data: dict[str, Any]) -> None:
        data["last_status"] = "errored"
        data["last_error_summary"] = summary or ""
        data["last_errored_at"] = timestamp or _dt.now().isoformat(timespec="seconds")

    return _mutate_conversation_envelope(conversation_id, root, mutate)


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

    def mutate(data: dict[str, Any]) -> None:
        for key in ("last_status", "last_error_summary", "last_errored_at"):
            data.pop(key, None)

    return _mutate_conversation_envelope(conversation_id, root, mutate)


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

    def mutate(data: dict[str, Any]) -> None:
        data["last_read_at"] = timestamp or _dt.now().isoformat(timespec="seconds")

    return _mutate_conversation_envelope(conversation_id, root, mutate)


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
    cleaned = (display_name or "").strip()

    def mutate(data: dict[str, Any]) -> None:
        if cleaned:
            data["display_name"] = cleaned[:200]
        else:
            data.pop("display_name", None)

    return _mutate_conversation_envelope(conversation_id, root, mutate)


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

    def mutate(data: dict[str, Any]) -> None:
        if pinned:
            data["pinned"] = True
        else:
            data.pop("pinned", None)

    return _mutate_conversation_envelope(conversation_id, root, mutate)


def set_conversation_closed(
    conversation_id: str,
    closed: bool,
    *,
    sessions_root: Path | None = None,
) -> Path | None:
    """Toggle the closed (hidden-from-sidebar) state on the envelope.

    A closed conversation is retained on disk but filtered out of
    ``iter_conversations`` so it no longer appears in the sidebar.
    Reversible: pass ``closed=False`` to restore.

    Returns the path written, or None if the envelope is missing.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT

    def mutate(data: dict[str, Any]) -> None:
        if closed:
            data["closed"] = True
        else:
            data.pop("closed", None)

    return _mutate_conversation_envelope(conversation_id, root, mutate)


def set_conversation_projects(
    conversation_id: str,
    project_ids: list[str],
    *,
    sessions_root: Path | None = None,
) -> Path | None:
    """Replace a conversation's explicit project memberships (G1.33).

    ``project_ids`` is the full new list of project nexus slugs the
    conversation belongs to. The implicit ``Commons`` project is never
    stored (an empty list == Commons), so ``commons``, its legacy id
    ``general``, and empty entries are stripped and the list is
    de-duplicated preserving order. This is the
    membership-edit path used by the project modal; conversation *creation*
    sets membership via ``save_turn_spatial_state``'s ``project_ids`` arg.

    Returns the path written, or None if the envelope is missing.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT

    def mutate(data: dict[str, Any]) -> None:
        data["project_ids"] = normalize_project_ids(project_ids)

    return _mutate_conversation_envelope(conversation_id, root, mutate)


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
    "set_conversation_closed",
    "set_conversation_projects",
]
