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
``CONVERSATION_TAGS``). Stealth is fixed at creation; Standard and Private
may be changed explicitly through the lifecycle API. Per-turn request payloads
never retag an existing envelope. The value is used by close-out dispatch and
by RAG queries to filter private content.

G1.4 adds a bounded ``description`` plus ``contributors`` to the envelope.
Contributors are reference identities, not copied text: a Dialogue may cite
another live/archive Dialogue or an exact atomic-note path without acquiring
fork ancestry.  The server resolves those references into read-only RAG
context on each turn.

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
import re
import threading
from collections import defaultdict
from datetime import datetime
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
    identity = str(conversation_id or "").strip().casefold()
    with _conv_locks_guard:
        return _conv_locks[identity]


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
# semantics. Stealth is creation-only. Standard/private may be changed later
# through set_conversation_tag(); per-turn request payloads never retag an
# existing envelope.
CONVERSATION_TAGS: tuple[str, ...] = ("", "stealth", "private")
MUTABLE_PRIVACY_TAGS: tuple[str, ...] = ("", "private")
CONTRIBUTOR_KINDS: tuple[str, ...] = ("conversation", "atomic_note")


def conversation_privacy_allows(source_tag: str, target_tag: str) -> bool:
    """Return whether ``target_tag`` may inherit content from ``source_tag``.

    Standard content may flow into any Dialogue, Private content only into
    Private or Stealth, and Stealth content only into Stealth.  Invalid tags
    fail closed; callers that intentionally support legacy malformed tags must
    normalize them before asking this question.
    """
    if source_tag not in CONVERSATION_TAGS or target_tag not in CONVERSATION_TAGS:
        return False
    if source_tag == "stealth":
        return target_tag == "stealth"
    if source_tag == "private":
        return target_tag in {"private", "stealth"}
    return True


def normalize_contributors(value: Any, *, strict: bool = False) -> list[dict[str, str]]:
    """Return the canonical additive contributor-reference shape.

    Conversation references use the browser/runtime identity under ``ref``
    (a live id or an ``archive:`` id). Atomic notes use one absolute ``path``.
    ``title`` is display-only provenance; runtime reads never trust it to
    locate content. Unknown or malformed legacy values are ignored on normal
    reads and rejected for authoritative creation when ``strict=True``.
    """

    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("contributors must be a list")
        return []
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("contributor entries must be objects")
            continue
        kind = item.get("kind")
        locator_key = "ref" if kind == "conversation" else "path"
        allowed = {"kind", locator_key, "title"}
        locator = item.get(locator_key)
        title = item.get("title", "")
        valid = (
            kind in CONTRIBUTOR_KINDS
            and set(item).issubset(allowed)
            and isinstance(locator, str)
            and bool(locator.strip())
            and len(locator.strip()) <= 4096
            and isinstance(title, str)
            and len(title.strip()) <= 300
        )
        if not valid:
            if strict:
                raise ValueError("contributor entry is invalid")
            continue
        locator = locator.strip()
        identity = (kind, locator)
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append({
            "kind": kind,
            locator_key: locator,
            "title": title.strip(),
        })
    return normalized


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


def _normalize_fork_point_message_count(value: Any) -> int | None:
    """Return a valid immutable parent-prefix length or ``None``.

    ``bool`` is excluded even though it subclasses ``int``: accepting it
    would turn malformed JSON into a plausible ancestry boundary.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


# ---------------------------------------------------------------------------
# Conversation JSON I/O
# ---------------------------------------------------------------------------


def validate_conversation_id(conversation_id: str) -> str:
    """Return a safe direct-child session id or raise ``ValueError``."""
    if not isinstance(conversation_id, str):
        raise ValueError("conversation_id must be a string")
    value = conversation_id.strip()
    if (not value or value in {".", ".."} or len(value) > 255
            or "/" in value or "\\" in value or "\x00" in value
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("invalid conversation_id")
    return value


def _conversation_path(
    conversation_id: str,
    sessions_root: Path,
    *,
    create_parent: bool = False,
) -> Path:
    """Return an owned envelope path without following a session symlink."""
    session_dir = _rp.safe_owned_subdir(
        Path(sessions_root),
        validate_conversation_id(conversation_id),
        create=create_parent,
    )
    target = session_dir / "conversation.json"
    if target.is_symlink():
        raise ValueError(f"conversation envelope is a symlink: {target}")
    if target.exists() and not target.is_file():
        raise ValueError(f"conversation envelope is not a file: {target}")
    return target


def _atomic_write_envelope(path: Path, data: dict[str, Any]) -> bool:
    """Atomically replace an envelope while its sidecar lock is held."""
    try:
        _rp.atomic_write_text(
            path,
            json.dumps(data, indent=2, ensure_ascii=False),
        )
        return True
    except OSError:
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
    try:
        path = _conversation_path(conversation_id, root)
    except (OSError, ValueError):
        return None
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
    data["fork_point_message_count"] = _normalize_fork_point_message_count(
        data.get("fork_point_message_count")
    )
    # Contributors are an additive v0 field. Sanitise the outward snapshot but
    # do not churn every pre-G1.4 envelope merely to add an empty list.
    data["contributors"] = normalize_contributors(data.get("contributors"))
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
                current["fork_point_message_count"] = (
                    _normalize_fork_point_message_count(
                        current.get("fork_point_message_count")
                    )
                )
                current["contributors"] = normalize_contributors(
                    current.get("contributors")
                )
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
    try:
        path = _conversation_path(conversation_id, root)
    except (OSError, ValueError):
        return None
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
                data["fork_point_message_count"] = (
                    _normalize_fork_point_message_count(
                        data.get("fork_point_message_count")
                    )
                )
                data["contributors"] = normalize_contributors(
                    data.get("contributors")
                )
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


def _read_history_envelope(
    conversation_id: str,
    root: Path,
) -> dict[str, Any] | None:
    """Read one live or retained envelope without healing or rewriting it.

    Effective-history resolution is a read path, including for malformed
    ancestry.  It therefore deliberately bypasses
    :func:`_read_normalized_envelope`, whose compatibility heal can rewrite
    unrelated metadata.  Closed conversations remain under ``sessions/``;
    the optional ``sessions/archived/`` lookup keeps a retained closed parent
    readable after the retention sweeper moves it.
    """
    for container in (root, root / "archived"):
        try:
            path = _conversation_path(conversation_id, container)
        except (OSError, ValueError):
            continue
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None
    return None


def read_conversation_history_envelope(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
) -> dict[str, Any] | None:
    """Read one live/closed/retained Dialogue envelope without mutation."""
    try:
        validated = validate_conversation_id(conversation_id)
    except ValueError:
        return None
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    return _read_history_envelope(validated, root)


def resolve_effective_conversation_history(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
    diagnostics: list[str] | None = None,
    lineage_sink: set[str] | list[str] | None = None,
) -> list[dict[str, Any]] | None:
    """Return ordered server-authoritative history for one Dialogue.

    Each ancestry edge contributes only the immutable prefix of its direct
    parent's local ``messages`` named by the child's
    ``fork_point_message_count``.  The parent's already-clipped ancestry and
    the child's local messages surround that prefix.  Resolution is
    recursive, so a nested fork applies every local cutoff in order and a
    later append to any ancestor cannot leak past an existing boundary.

    The function never writes.  Missing/unreadable target envelopes return
    ``None`` so a legacy caller can distinguish "no server history" from a
    real zero-turn Dialogue.  A cycle, orphan, malformed cutoff, or malformed
    ancestor discards that unsafe ancestry branch while preserving the target
    Dialogue's valid local messages.  Optional ``diagnostics`` receives terse
    reasons for observability and tests.

    Returned message snapshots preserve ordinary turn metadata for spatial
    continuity and carry private ``_ora_*`` routing hints used only by the
    capacity packer.  They are never persisted or sent to a provider.
    """
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    try:
        target_id = validate_conversation_id(conversation_id)
    except ValueError:
        if diagnostics is not None:
            diagnostics.append("invalid conversation_id")
        return None

    def note(message: str) -> None:
        if diagnostics is not None:
            diagnostics.append(message)

    def record_lineage(owner_id: str) -> None:
        if lineage_sink is None:
            return
        if isinstance(lineage_sink, set):
            lineage_sink.add(owner_id)
        elif owner_id not in lineage_sink:
            lineage_sink.append(owner_id)

    def local_messages(
        envelope: dict[str, Any],
        owner_id: str,
        ancestry_depth: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        raw_messages = envelope.get("messages")
        if not isinstance(raw_messages, list):
            note(f"{owner_id}: messages is not a list")
            return [], False
        result: list[dict[str, Any]] = []
        valid = True
        turn_index = 0
        pending_user = False
        for index, raw in enumerate(raw_messages):
            if not isinstance(raw, dict):
                note(f"{owner_id}: message {index} is not an object")
                valid = False
                continue
            role = raw.get("role")
            content = raw.get("content")
            if role not in {"user", "assistant", "system"} or not isinstance(
                content, str
            ):
                note(f"{owner_id}: message {index} has malformed role/content")
                valid = False
                continue
            snapshot = copy.deepcopy(raw)
            if role == "user":
                turn_index += 1
                pending_user = True
            elif role == "assistant" and not pending_user:
                turn_index += 1
            snapshot["_ora_history_owner"] = owner_id
            snapshot["_ora_history_message_index"] = index
            snapshot["_ora_history_turn_index"] = turn_index
            snapshot["_ora_ancestry_depth"] = ancestry_depth
            snapshot["_ora_history_segment"] = (
                "local" if ancestry_depth == 0 else "ancestry"
            )
            result.append(snapshot)
            if role == "assistant":
                pending_user = False
        return result, valid

    def visit(
        current_id: str,
        ancestry_depth: int,
        stack: tuple[str, ...],
    ) -> tuple[list[dict[str, Any]], int, bool]:
        identity = current_id.casefold()
        if identity in stack:
            note(f"{current_id}: ancestry cycle detected")
            return [], 0, False

        envelope = _read_history_envelope(current_id, root)
        if envelope is None:
            note(f"{current_id}: envelope missing or unreadable")
            return [], 0, False
        stored_id = envelope.get("conversation_id")
        if (stored_id is not None and (
            not isinstance(stored_id, str)
            or stored_id.strip().casefold() != identity
        )):
            note(f"{current_id}: envelope identity mismatch")
            return [], 0, False

        # Record every successfully authenticated envelope, including a
        # cutoff-zero parent whose messages do not appear in the effective
        # transcript.  Callers use this source-wide lineage to exclude global
        # Conversation RAG and to enforce privacy across contributor ancestry.
        record_lineage(current_id)

        local, local_valid = local_messages(
            envelope, current_id, ancestry_depth,
        )
        parent_raw = envelope.get("parent_conversation_id")
        if parent_raw is None:
            if envelope.get("fork_point_message_count") is not None:
                note(f"{current_id}: cutoff present without parent")
                return local, len(local), False
            return local, len(local), local_valid
        if not isinstance(parent_raw, str) or not parent_raw.strip():
            note(f"{current_id}: malformed parent_conversation_id")
            return local, len(local), False
        try:
            parent_id = validate_conversation_id(parent_raw)
        except ValueError:
            note(f"{current_id}: invalid parent_conversation_id")
            return local, len(local), False
        # A syntactically valid parent identity is exclusion-relevant even if
        # its retained envelope has gone missing.  Recording the edge before
        # the read prevents a stale global-RAG row for that parent from
        # bypassing the immutable fork boundary.
        record_lineage(parent_id)

        raw_cutoff = envelope.get("fork_point_message_count")
        cutoff = _normalize_fork_point_message_count(raw_cutoff)
        if cutoff is None:
            note(f"{current_id}: malformed fork_point_message_count")
            return local, len(local), False

        parent_history, parent_local_count, parent_valid = visit(
            parent_id,
            ancestry_depth + 1,
            stack + (identity,),
        )
        current_tag = (
            envelope.get("tag")
            if envelope.get("tag") in CONVERSATION_TAGS else ""
        )
        parent_envelope = _read_history_envelope(parent_id, root)
        parent_tag = (
            parent_envelope.get("tag")
            if isinstance(parent_envelope, dict)
            and parent_envelope.get("tag") in CONVERSATION_TAGS
            else ""
        )
        if (isinstance(parent_envelope, dict)
                and not conversation_privacy_allows(parent_tag, current_tag)):
            # A later Standard/Private retag can make an originally valid fork
            # edge incompatible.  The parent branch is no longer readable,
            # but the current Dialogue's own local turns remain authoritative.
            # ``visit`` already inventoried the discarded lineage so global
            # Conversation RAG cannot silently re-admit it.
            note(
                f"{current_id}: parent {parent_id} privacy {parent_tag!r} "
                f"is incompatible with child privacy {current_tag!r}"
            )
            return local, len(local), local_valid
        if not parent_valid:
            # An incomplete or cyclic branch is not a truthful ordered prefix.
            # Keep only this node's local record and propagate invalidity so a
            # descendant cannot accidentally re-admit part of the bad branch.
            return local, len(local), False
        if cutoff > parent_local_count:
            note(
                f"{current_id}: fork_point_message_count {cutoff} exceeds "
                f"parent local message length {parent_local_count}"
            )
            return local, len(local), False
        parent_ancestry_count = len(parent_history) - parent_local_count
        return (
            parent_history[:parent_ancestry_count + cutoff] + local,
            len(local),
            local_valid,
        )

    history, _, _ = visit(target_id, 0, ())
    return history


def ensure_conversation_envelope(
    conversation_id: str,
    *,
    tag: str = "",
    project_ids: list[str] | None = None,
    sessions_root: Path | None = None,
) -> Path | None:
    """Create a zero-turn envelope for a server-managed artifact if absent.

    Canvas, document, capture, and media artifacts can exist before the first
    chat turn. Giving them an envelope immediately makes their lifecycle and
    privacy state durable across browser/server restarts. Existing readable
    envelopes are never changed; existing unreadable envelopes are reported
    and never overwritten.
    """
    from datetime import datetime as _dt
    import sys as _sys

    cid = validate_conversation_id(conversation_id)
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    try:
        path = _conversation_path(cid, root, create_parent=True)
    except (OSError, ValueError) as exc:
        print(
            f"[conversation_memory] unsafe artifact envelope path for "
            f"{cid}: {exc}",
            file=_sys.stderr,
            flush=True,
        )
        return None
    envelope_tag = tag if tag in CONVERSATION_TAGS else ""
    envelope = {
        "conversation_id": cid,
        "display_name": "",
        "tag": envelope_tag,
        "created": _dt.now().isoformat(timespec="seconds"),
        "parent_conversation_id": None,
        "fork_point_message_count": None,
        "fork_point_chunk_id": None,
        "project_ids": normalize_project_ids(project_ids),
        "contributors": [],
        "messages": [],
    }
    with _conversation_write_lock(cid):
        try:
            with _rp.locked_file(path):
                if path.exists() or path.is_symlink():
                    existing = _read_normalized_envelope(
                        cid,
                        root,
                        require_messages=True,
                        persist_heal=False,
                    )
                    if existing is not None:
                        return path
                    print(
                        f"[conversation_memory] refused to overwrite unreadable "
                        f"envelope for artifact: {path}",
                        file=_sys.stderr,
                        flush=True,
                    )
                    return None
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps(envelope, indent=2, ensure_ascii=False))
                    stream.flush()
                    os.fsync(stream.fileno())
                return path
        except (OSError, TimeoutError) as exc:
            print(
                f"[conversation_memory] artifact envelope create failed for "
                f"{cid}: {exc}",
                file=_sys.stderr,
                flush=True,
            )
            return None


def create_conversation_envelope(
    conversation_id: str,
    *,
    title: str,
    description: str,
    contributors: list[dict[str, str]] | None = None,
    tag: str = "",
    project_ids: list[str] | None = None,
    sessions_root: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Exclusively create one reviewed, zero-turn G1.4 Dialogue.

    The description is durable creation intent but is not silently recorded as
    a user turn. The browser restores it as an unsent draft after selecting
    the new Dialogue, preserving the user's final control over submission.
    """

    from datetime import datetime as _dt

    cid = validate_conversation_id(conversation_id)
    if not isinstance(title, str):
        raise ValueError("title must be a string")
    clean_title = re.sub(r"\s+", " ", title).strip()
    if not clean_title or len(clean_title) > 200:
        raise ValueError("title must contain 1 to 200 characters")
    if not isinstance(description, str):
        raise ValueError("description must be a string")
    clean_description = description.strip()
    meaningful_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]+", clean_description)
    if (
        len(clean_description) < 20
        or len(clean_description) > 4000
        or len(meaningful_terms) < 3
    ):
        raise ValueError(
            "description must contain 20 to 4000 characters and at least 3 terms"
        )
    if tag not in CONVERSATION_TAGS:
        raise ValueError("invalid conversation tag")
    clean_contributors = normalize_contributors(contributors, strict=True)
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    path = _conversation_path(cid, root, create_parent=True)
    created = timestamp or _dt.now().isoformat(timespec="seconds")
    envelope: dict[str, Any] = {
        "conversation_id": cid,
        "display_name": clean_title,
        "description": clean_description,
        "tag": tag,
        "created": created,
        "parent_conversation_id": None,
        "fork_point_message_count": None,
        "fork_point_chunk_id": None,
        "project_ids": normalize_project_ids(project_ids),
        "contributors": clean_contributors,
        "messages": [],
    }
    with _conversation_write_lock(cid):
        with _rp.locked_file(path):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(envelope, indent=2, ensure_ascii=False))
                stream.flush()
                os.fsync(stream.fileno())
    return copy.deepcopy(envelope)


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
    try:
        path = _conversation_path(
            conversation_id, root, create_parent=True,
        )
    except (OSError, ValueError):
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
            "fork_point_message_count": None,
            "fork_point_chunk_id":     None,
            "project_ids":             normalize_project_ids(project_ids),
            "contributors":            [],
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
        existing["fork_point_message_count"] = (
            _normalize_fork_point_message_count(
                existing.get("fork_point_message_count")
            )
        )
        if "fork_point_chunk_id" not in existing:
            existing["fork_point_chunk_id"] = None
        # Preserve real memberships, but lazily heal legacy/default sentinels
        # and malformed values whenever an envelope is written.
        existing["project_ids"] = normalize_project_ids(existing.get("project_ids"))
        existing["contributors"] = normalize_contributors(
            existing.get("contributors")
        )

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


def set_conversation_tag(
    conversation_id: str,
    tag: str,
    *,
    sessions_root: Path | None = None,
) -> Path | None:
    """Change an existing envelope between Standard and Private.

    Stealth is creation-only: neither assigning Stealth nor changing an
    existing Stealth envelope is permitted here. Callers that need a Stealth
    conversation must create a new envelope (including a fork).

    Returns the written path, or None when the envelope is missing/unreadable.
    Raises ValueError for an invalid target and PermissionError for any
    attempted transition involving Stealth.
    """
    if tag not in MUTABLE_PRIVACY_TAGS:
        raise ValueError("conversation tag mutation accepts only standard or private")

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    class _StealthMutationRequested(Exception):
        pass

    def mutate(data: dict[str, Any]) -> None:
        current = data.get("tag", "")
        if current == "stealth":
            raise _StealthMutationRequested
        if current not in MUTABLE_PRIVACY_TAGS:
            current = ""
        if current != tag:
            data["tag"] = tag

    try:
        return _mutate_conversation_envelope(conversation_id, root, mutate)
    except _StealthMutationRequested:
        raise PermissionError(
            "Stealth is creation-only and cannot be retagged",
        ) from None


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


def effective_conversation_title(data: dict[str, Any], max_len: int = 60) -> str:
    """Return the stored display name or the same derived fallback used by UI.

    The default matches the sidebar's fallback exactly. A stored display name
    remains authoritative (up to its 200-character envelope limit).
    """
    display_name = data.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()[:200]
    if data.get("is_welcome"):
        return "Welcome to Ora"
    return _derive_title(data.get("messages") or [], max_len=max_len)


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
        # Session children are Ora-owned directories, never pointers to an
        # unrelated tree. Match the no-follow behavior of the read/write path.
        if entry.is_symlink() or not entry.is_dir():
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
        local_message_count = len(messages) if isinstance(messages, list) else 0
        inherited_message_count = (
            _normalize_fork_point_message_count(
                data.get("fork_point_message_count")
            ) or 0
        )
        summaries.append({
            "conversation_id": entry.name,
            "tag": tag,
            "title": title,
            "message_count": local_message_count,
            "local_message_count": local_message_count,
            "inherited_message_count": inherited_message_count,
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
            "fork_point_message_count": _normalize_fork_point_message_count(
                data.get("fork_point_message_count")
            ),
            "fork_point_chunk_id": (
                data.get("fork_point_chunk_id")
                if isinstance(data.get("fork_point_chunk_id"), str) else None
            ),
            "project_ids": list(data.get("project_ids") or []),
            "description": (
                data.get("description")
                if isinstance(data.get("description"), str) else ""
            ),
            "contributors": copy.deepcopy(data.get("contributors") or []),
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
    try:
        welcome_path = _conversation_path(WELCOME_CONVERSATION_ID, root)
    except (OSError, ValueError):
        return False
    if welcome_path.exists():
        _migrate_welcome_placeholder(welcome_path)
        return False

    if only_if_first_launch and root.exists() and root.is_dir():
        # Check whether ANY conversation.json files exist in the sessions
        # directory. If yes, this isn't a first launch — bail.
        for entry in root.iterdir():
            if entry.is_symlink() or not entry.is_dir():
                continue
            candidate = entry / "conversation.json"
            if not candidate.is_symlink() and candidate.is_file():
                return False

    now_iso = _dt.now().isoformat(timespec="seconds")
    envelope = {
        "conversation_id":         WELCOME_CONVERSATION_ID,
        "display_name":            "Welcome to Ora",
        "tag":                     "",
        "created":                 now_iso,
        "parent_conversation_id":  None,
        "fork_point_message_count": None,
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
            welcome_path = _conversation_path(
                WELCOME_CONVERSATION_ID, root, create_parent=True,
            )
            with _rp.locked_file(welcome_path):
                fd = os.open(
                    welcome_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
                )
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps(envelope, indent=2, ensure_ascii=False))
                    stream.flush()
                    os.fsync(stream.fileno())
                return True
        except (OSError, TimeoutError, ValueError):
            return False


def _fork_point_message_count_for_turn(
    messages: list[Any],
    turn_index: int | None,
) -> int:
    """Resolve a displayed turn to an exact raw-message prefix length.

    The grouping mirrors the browser's Dialogue renderer: a user message waits
    for an assistant, a second user closes the prior user-only turn, and a
    standalone assistant is its own turn. The stored count is the durable
    boundary; later parent appends cannot move it.
    """
    if turn_index is None:
        return len(messages)
    if isinstance(turn_index, bool) or not isinstance(turn_index, int):
        raise ValueError("fork_point_turn_index must be an integer")
    if turn_index < 0:
        raise ValueError("fork_point_turn_index is out of range")

    turn_boundaries: list[int] = []
    pending_user_index: int | None = None
    for message_index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user":
            if pending_user_index is not None:
                turn_boundaries.append(message_index)
            pending_user_index = message_index
        elif role == "assistant":
            turn_boundaries.append(message_index + 1)
            pending_user_index = None
    if pending_user_index is not None:
        turn_boundaries.append(pending_user_index + 1)

    if turn_index >= len(turn_boundaries):
        raise ValueError("fork_point_turn_index is out of range")
    return turn_boundaries[turn_index]


def fork_conversation(
    parent_id: str,
    new_id: str,
    *,
    fork_point_turn_index: int | None = None,
    fork_point_chunk_id: str | None = None,
    creation_tag: str | None = None,
    sessions_root: Path | None = None,
    timestamp: str | None = None,
) -> dict | None:
    """Create a child-local conversation with an immutable ancestry boundary.

    V3 spec §4.2 / §5.2 (fork from default) and §4.3 / §5.3 (fork from
    mode). The child conversation:

      * gets a fresh ``conversation_id`` (caller-supplied to keep the
        content-derived naming convention in the caller's hands)
      * inherits the parent's ``tag`` unless ``creation_tag`` explicitly
        selects a valid mode. This is a new envelope, so a Stealth override is
        allowed without making Stealth mutable on the parent.
      * gets ``fork_point_message_count``, the exact parent-message prefix
        visible at the fork. A requested ``fork_point_turn_index`` is resolved
        against the browser's displayed turns; when omitted, the boundary is
        the parent's latest message.
      * retains the legacy ``parent_conversation_id`` and
        ``fork_point_chunk_id`` fields for older readers.
      * gets ``created`` (the fork creation time) and a legacy
        ``forked_at`` mirror for any older callers
      * starts with an empty local ``messages[]``. Ancestry can be reconstructed
        read-only through the immutable cutoff rather than copied into the child.

    Returns the new envelope dict on success, or None if the parent is
    missing / unreadable.

    The parent envelope is NOT modified — fork is non-destructive.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    parent_id = validate_conversation_id(parent_id)
    new_id = validate_conversation_id(new_id)
    parent = load_conversation_json(parent_id, sessions_root=root)
    if parent is None:
        return None

    # Validate parent shape; default to standard mode if tag malformed.
    parent_tag = parent.get("tag", "")
    if not isinstance(parent_tag, str) or parent_tag not in CONVERSATION_TAGS:
        parent_tag = ""
    child_tag = creation_tag if creation_tag in CONVERSATION_TAGS else parent_tag
    if not conversation_privacy_allows(parent_tag, child_tag):
        raise ValueError(
            "fork privacy cannot make parent content visible at a weaker boundary"
        )
    # The fetch route and browser display the direct parent's local transcript.
    # Keep the API's zero-based displayed-turn index and the durable cutoff in
    # that same local coordinate system.  Recursive resolution carries the
    # parent's already-clipped ancestry ahead of this local prefix.
    parent_messages = parent.get("messages") or []
    if not isinstance(parent_messages, list):
        parent_messages = []
    boundary_message_count = _fork_point_message_count_for_turn(
        parent_messages, fork_point_turn_index,
    )
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
    parent_contributors = normalize_contributors(parent.get("contributors"))

    child = {
        "conversation_id":         new_id,
        "display_name":            derived_display,
        "tag":                     child_tag,
        "created":                 forked_at,
        "parent_conversation_id":  parent_id,
        "fork_point_message_count": boundary_message_count,
        "fork_point_chunk_id":     fork_point_chunk_id,
        "forked_at":               forked_at,
        "project_ids":             list(parent_projects),
        "description":             (
            parent.get("description")
            if isinstance(parent.get("description"), str) else ""
        ),
        "contributors":            copy.deepcopy(parent_contributors),
        "messages":                [],
    }

    try:
        child_path = _conversation_path(new_id, root, create_parent=True)
    except (OSError, ValueError):
        return None
    with _conversation_write_lock(new_id):
        try:
            with _rp.locked_file(child_path):
                # Exclusive creation is the low-level backstop: direct callers
                # and concurrent processes cannot overwrite an existing child
                # envelope even if they bypass the server lifecycle preflight.
                fd = os.open(
                    child_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
                )
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps(child, indent=2, ensure_ascii=False))
                    stream.flush()
                    os.fsync(stream.fileno())
        except (OSError, TimeoutError, ValueError):
            return None
    return child


def detach_direct_fork_children(
    parent_id: str,
    *,
    parent_messages: list[Any] | None,
    sessions_root: Path | None = None,
) -> dict[str, Any]:
    """Detach direct children before a parent transcript becomes unavailable.

    Current forks contain only local messages, so detachment clears their
    ancestry fields without touching ``messages``. Legacy forks copied the
    parent's transcript. That prefix is removed only when the child's messages
    begin with the parent's complete current message list; every less-certain
    legacy shape is preserved and reported.
    """
    parent_id = validate_conversation_id(parent_id)
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT
    parent_snapshot = (
        copy.deepcopy(parent_messages)
        if isinstance(parent_messages, list) else None
    )
    result: dict[str, Any] = {
        "children_detached": [],
        "legacy_prefix_messages_removed": 0,
        "ambiguous_children_preserved": [],
        "errors": [],
    }
    try:
        if root.is_symlink() or not root.is_dir():
            return result
    except OSError as exc:
        result["errors"].append(f"sessions root {root}: {exc}")
        return result

    containers = [root]
    archive_root = root / "archived"
    try:
        if (archive_root.exists() and not archive_root.is_symlink()
                and archive_root.is_dir()):
            containers.append(archive_root)
    except OSError as exc:
        result["errors"].append(f"sessions archive {archive_root}: {exc}")

    for container in containers:
        try:
            entries = list(container.iterdir())
        except OSError as exc:
            result["errors"].append(f"sessions scan {container}: {exc}")
            continue
        for session_dir in entries:
            if container == root and session_dir.name == "archived":
                continue
            try:
                if session_dir.is_symlink() or not session_dir.is_dir():
                    continue
                path = session_dir / "conversation.json"
                if path.is_symlink() or not path.is_file():
                    continue
                initial = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (not isinstance(initial, dict)
                    or not isinstance(initial.get("parent_conversation_id"), str)
                    or initial["parent_conversation_id"].strip().casefold()
                    != parent_id.casefold()):
                continue

            child_id = session_dir.name
            with _conversation_write_lock(child_id):
                try:
                    with _rp.locked_file(path):
                        current = json.loads(path.read_text(encoding="utf-8"))
                        if (not isinstance(current, dict)
                                or not isinstance(
                                    current.get("parent_conversation_id"), str,
                                )
                                or current["parent_conversation_id"].strip().casefold()
                                != parent_id.casefold()):
                            continue

                        raw_cutoff = current.get("fork_point_message_count")
                        cutoff = _normalize_fork_point_message_count(raw_cutoff)
                        messages = current.get("messages")
                        removed = 0
                        ambiguous = False

                        if raw_cutoff is not None and cutoff is None:
                            ambiguous = bool(messages)
                            result["errors"].append(
                                f"child {child_id}: invalid fork_point_message_count; "
                                "messages preserved"
                            )
                        elif cutoff is None and isinstance(messages, list) and messages:
                            if (parent_snapshot is not None
                                    and parent_snapshot
                                    and len(messages) >= len(parent_snapshot)
                                    and messages[:len(parent_snapshot)] == parent_snapshot):
                                removed = len(parent_snapshot)
                                current["messages"] = messages[removed:]
                            elif parent_snapshot:
                                ambiguous = True
                                result["errors"].append(
                                    f"child {child_id}: legacy messages do not contain "
                                    "the deleted parent's exact full prefix; preserved"
                                )
                            elif parent_snapshot is None:
                                ambiguous = True
                                result["errors"].append(
                                    f"child {child_id}: deleted parent messages are "
                                    "unavailable; legacy messages preserved"
                                )
                        elif not isinstance(messages, list):
                            ambiguous = True
                            result["errors"].append(
                                f"child {child_id}: messages is not a list; preserved"
                            )

                        current["parent_conversation_id"] = None
                        current["fork_point_message_count"] = None
                        current["fork_point_chunk_id"] = None
                        if not _atomic_write_envelope(path, current):
                            result["errors"].append(
                                f"child {child_id}: envelope rewrite failed"
                            )
                            continue
                        result["children_detached"].append(child_id)
                        result["legacy_prefix_messages_removed"] += removed
                        if ambiguous:
                            result["ambiguous_children_preserved"].append(child_id)
                except (OSError, TimeoutError, json.JSONDecodeError) as exc:
                    result["errors"].append(f"child {child_id}: {exc}")
    return result


def mark_conversation_errored(
    conversation_id: str,
    summary: str,
    *,
    sessions_root: Path | None = None,
    timestamp: str | None = None,
    interrupted_input: str | None = None,
    interrupted_submission_id: str | None = None,
) -> Path | None:
    """Mark a conversation's most recent run as errored on its envelope.

    Backlog item 11. The pipeline writes a separate error chunk file
    when a run fails (Backlog 2D), but the V3 sidebar list is driven
    off conversation.json envelopes — so we mirror the error state on
    the envelope: ``last_status: "errored"`` + ``last_error_summary``. When
    the authoritative append failed, ``interrupted_input`` also preserves the
    exact unacknowledged prompt for the existing retry path.

    The list endpoint then groups conversations with that status into
    an Errored group, and the sidebar UI surfaces retry + dismiss
    actions per row.

    Returns the path written, or None if conversation.json is
    missing / unreadable / unwriteable. Best-effort.
    """
    from datetime import datetime as _dt

    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT

    def mutate(data: dict[str, Any]) -> None:
        errored_at = timestamp or _dt.now().isoformat(timespec="seconds")
        data["last_status"] = "errored"
        data["last_error_summary"] = summary or ""
        data["last_errored_at"] = errored_at
        if interrupted_input is not None:
            data["interrupted_input"] = interrupted_input
            data["interrupted_at"] = errored_at
            if interrupted_submission_id:
                data["interrupted_submission_id"] = interrupted_submission_id

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
    "MUTABLE_PRIVACY_TAGS",
    "conversation_privacy_allows",
    "validate_conversation_id",
    "normalize_contributors",
    "create_conversation_envelope",
    "WELCOME_CONVERSATION_ID",
    "WELCOME_PLACEHOLDER_BODY",
    "load_conversation_json",
    "resolve_effective_conversation_history",
    "ensure_conversation_envelope",
    "save_turn_spatial_state",
    "get_prior_spatial_state",
    "get_prior_annotations",
    "get_conversation_tag",
    "set_conversation_tag",
    "effective_conversation_title",
    "iter_conversations",
    "mark_conversation_read",
    "mark_conversation_errored",
    "clear_conversation_error",
    "fork_conversation",
    "detach_direct_fork_children",
    "ensure_welcome_thread",
    "set_display_name",
    "set_conversation_pinned",
    "set_conversation_closed",
    "set_conversation_projects",
]
