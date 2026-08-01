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
      "process_plan_lifecycle": { ... } | absent,
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

``process_plan_lifecycle`` is a separate digest-bound governed-work field.
It never shares or changes the privacy ``tag`` namespace.

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
import hashlib
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
MAX_CONTRIBUTORS = 20


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
    if len(value) > MAX_CONTRIBUTORS:
        if strict:
            raise ValueError(f"contributors exceeds the {MAX_CONTRIBUTORS}-item limit")
        value = value[:MAX_CONTRIBUTORS]

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
                data["contributors"] = normalize_contributors(
                    data.get("contributors")
                )
                mutate(data)
                return path if _atomic_write_envelope(path, data) else None
        except (OSError, TimeoutError):
            return None


class ConversationProcessBindingError(RuntimeError):
    """A Dialogue cannot safely establish or read its governing Run binding."""


class ConversationPlanLifecycleError(RuntimeError):
    """A Dialogue plan-lifecycle binding is invalid or cannot be persisted."""


_PROCESS_BINDING_SCHEMA_VERSION = "ora.dialogue-process-binding/1.0"
_PROCESS_BINDING_FIELDS = frozenset({
    "schema_version",
    "run_id",
    "definition_ref",
    "binding_digest",
    "bound_at",
})
_PROCESS_BINDING_REF_FIELDS = frozenset({"definition_id", "version", "digest"})

_PLAN_LIFECYCLE_SCHEMA_VERSION = "ora.dialogue-plan-lifecycle/1.0"
_PLAN_APPROVAL_SCHEMA_VERSION = "ora.programming-plan-state/1.0"
_PLAN_LIFECYCLE_FIELD = "process_plan_lifecycle"
_PLAN_LIFECYCLE_VALUES = frozenset({"plan:in-planning", "plan:approved"})
_PLAN_REF_FIELDS = frozenset({"plan_id", "version", "digest"})
_PLAN_LIFECYCLE_FIELDS = frozenset({
    "schema_version",
    "lifecycle",
    "run_id",
    "binding_digest",
    "plan_ref",
    "approval_receipt",
    "approval_receipt_digest",
    "lifecycle_digest",
})
_APPROVAL_RECEIPT_FIELDS = frozenset({
    "schema_version",
    "plan_ref",
    "baseline_digest",
    "decision",
    "decision_by",
    "decided_at",
    "idempotency_key",
})


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _validate_plan_lifecycle(value: Any) -> dict[str, Any]:
    """Validate one digest-bound plan lifecycle stored outside privacy tag."""

    if not isinstance(value, dict) or set(value) != _PLAN_LIFECYCLE_FIELDS:
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle has an invalid field set"
        )
    if value.get("schema_version") != _PLAN_LIFECYCLE_SCHEMA_VERSION:
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle has an unsupported schema version"
        )
    lifecycle = value.get("lifecycle")
    if lifecycle not in _PLAN_LIFECYCLE_VALUES:
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle value is invalid"
        )
    plan_ref = value.get("plan_ref")
    if (
        not isinstance(plan_ref, dict)
        or set(plan_ref) != _PLAN_REF_FIELDS
        or not str(plan_ref.get("plan_id") or "").strip()
        or not re.fullmatch(r"[1-9][0-9]*\.0", str(plan_ref.get("version") or ""))
        or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(plan_ref.get("digest") or "")
        )
    ):
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle plan_ref is invalid"
        )
    run_id = str(value.get("run_id") or "").strip()
    if not run_id or plan_ref.get("plan_id") != f"plan:{run_id}":
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle does not bind its exact Run"
        )
    binding_digest = str(value.get("binding_digest") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", binding_digest):
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle binding digest is invalid"
        )
    approval = value.get("approval_receipt")
    approval_digest = value.get("approval_receipt_digest")
    if lifecycle == "plan:in-planning":
        if approval is not None or approval_digest is not None:
            raise ConversationPlanLifecycleError(
                "in-planning lifecycle cannot claim an approval receipt"
            )
    else:
        if not isinstance(approval, dict) or set(approval) != _APPROVAL_RECEIPT_FIELDS:
            raise ConversationPlanLifecycleError(
                "approved lifecycle lacks an exact approval receipt"
            )
        if (
            approval.get("schema_version") != _PLAN_APPROVAL_SCHEMA_VERSION
            or approval.get("plan_ref") != plan_ref
            or approval.get("decision")
            not in {"approve_and_start", "approve_without_start"}
            or not str(approval.get("decision_by") or "").strip()
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(approval.get("baseline_digest") or ""),
            )
            or approval_digest != _digest_json(approval)
        ):
            raise ConversationPlanLifecycleError(
                "approved lifecycle receipt identity is invalid"
            )
        try:
            datetime.fromisoformat(
                str(approval.get("decided_at") or "").replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ConversationPlanLifecycleError(
                "approved lifecycle decision time is invalid"
            ) from exc
    body = {
        key: copy.deepcopy(item)
        for key, item in value.items()
        if key != "lifecycle_digest"
    }
    if value.get("lifecycle_digest") != _digest_json(body):
        raise ConversationPlanLifecycleError(
            "process_plan_lifecycle digest does not match its body"
        )
    return copy.deepcopy(value)


def persist_process_plan_lifecycle(
    conversation_id: str,
    lifecycle: dict[str, Any],
    *,
    sessions_root: Path | None = None,
) -> Path:
    """Persist plan lifecycle independently while preserving privacy exactly."""

    validated = _validate_plan_lifecycle(lifecycle)
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT

    def mutate(data: dict[str, Any]) -> None:
        prior_tag = data.get("tag", "")
        existing = data.get(_PLAN_LIFECYCLE_FIELD)
        if existing is not None:
            current = _validate_plan_lifecycle(existing)
            if current["lifecycle_digest"] == validated["lifecycle_digest"]:
                return
            if current["lifecycle"] == "plan:approved":
                raise ConversationPlanLifecycleError(
                    "approved Dialogue lifecycle is immutable in Phase 2.3"
                )
            if current["plan_ref"]["plan_id"] != validated["plan_ref"]["plan_id"]:
                raise ConversationPlanLifecycleError(
                    "Dialogue cannot switch plan families"
                )
            current_version = int(current["plan_ref"]["version"].split(".", 1)[0])
            next_version = int(validated["plan_ref"]["version"].split(".", 1)[0])
            if next_version < current_version or (
                next_version == current_version
                and current["plan_ref"] != validated["plan_ref"]
            ):
                raise ConversationPlanLifecycleError(
                    "Dialogue plan lifecycle cannot rewrite a plan version"
                )
        data[_PLAN_LIFECYCLE_FIELD] = copy.deepcopy(validated)
        if data.get("tag", "") != prior_tag:
            raise ConversationPlanLifecycleError(
                "plan lifecycle persistence changed Dialogue privacy"
            )

    path = _mutate_conversation_envelope(conversation_id, root, mutate)
    if path is None:
        raise ConversationPlanLifecycleError(
            "Dialogue envelope is unavailable for plan lifecycle persistence"
        )
    return path


def load_process_plan_lifecycle(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
) -> dict[str, Any] | None:
    """Load and authenticate the Dialogue's separate plan lifecycle."""

    envelope = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if envelope is None or envelope.get(_PLAN_LIFECYCLE_FIELD) is None:
        return None
    return _validate_plan_lifecycle(envelope[_PLAN_LIFECYCLE_FIELD])


def _validate_process_binding(value: Any) -> dict[str, Any]:
    """Validate the immutable pointer stored on a Dialogue envelope."""

    if not isinstance(value, dict) or set(value) != _PROCESS_BINDING_FIELDS:
        raise ConversationProcessBindingError(
            "governing_process has an invalid field set"
        )
    if value.get("schema_version") != _PROCESS_BINDING_SCHEMA_VERSION:
        raise ConversationProcessBindingError(
            "governing_process has an unsupported schema version"
        )
    run_id = str(value.get("run_id") or "").strip()
    if not run_id:
        raise ConversationProcessBindingError("governing_process run_id is empty")
    definition_ref = value.get("definition_ref")
    if (not isinstance(definition_ref, dict)
            or set(definition_ref) != _PROCESS_BINDING_REF_FIELDS
            or any(not str(definition_ref.get(field) or "").strip()
                   for field in _PROCESS_BINDING_REF_FIELDS)):
        raise ConversationProcessBindingError(
            "governing_process definition_ref is invalid"
        )
    if not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(definition_ref.get("digest") or "")
    ):
        raise ConversationProcessBindingError(
            "governing_process definition digest is invalid"
        )
    digest = str(value.get("binding_digest") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ConversationProcessBindingError(
            "governing_process binding_digest is invalid"
        )
    bound_at = str(value.get("bound_at") or "").strip()
    if not bound_at:
        raise ConversationProcessBindingError("governing_process bound_at is empty")
    try:
        datetime.fromisoformat(bound_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConversationProcessBindingError(
            "governing_process bound_at is not ISO-8601"
        ) from exc
    return copy.deepcopy(value)


def bind_governing_process(
    conversation_id: str,
    binding: dict[str, Any],
    *,
    sessions_root: Path | None = None,
) -> Path:
    """Bind one immutable governing Process Run to an existing Dialogue.

    Repeating the exact binding is idempotent.  A different binding is never
    allowed to replace the active Run implicitly; callers must use a future
    explicit lifecycle operation instead.
    """

    validated = _validate_process_binding(binding)
    root = Path(sessions_root) if sessions_root else _DEFAULT_SESSIONS_ROOT

    def mutate(data: dict[str, Any]) -> None:
        existing = data.get("governing_process")
        if existing is None:
            data["governing_process"] = copy.deepcopy(validated)
            return
        current = _validate_process_binding(existing)
        immutable_fields = (
            "schema_version", "run_id", "definition_ref", "binding_digest",
        )
        if any(current[field] != validated[field] for field in immutable_fields):
            raise ConversationProcessBindingError(
                "Dialogue already has a different governing Process Run"
            )

    path = _mutate_conversation_envelope(conversation_id, root, mutate)
    if path is None:
        raise ConversationProcessBindingError(
            "Dialogue envelope is unavailable for governing Run binding"
        )
    return path


def load_governing_process_binding(
    conversation_id: str,
    *,
    sessions_root: Path | None = None,
) -> dict[str, Any] | None:
    """Return the validated governing Run pointer for one Dialogue."""

    envelope = load_conversation_json(conversation_id, sessions_root=sessions_root)
    if envelope is None or envelope.get("governing_process") is None:
        return None
    return _validate_process_binding(envelope["governing_process"])


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


def fork_conversation(
    parent_id: str,
    new_id: str,
    *,
    fork_point_chunk_id: str | None = None,
    creation_tag: str | None = None,
    sessions_root: Path | None = None,
    timestamp: str | None = None,
) -> dict | None:
    """Create a child conversation with copied history and a creation tag.

    V3 spec §4.2 / §5.2 (fork from default) and §4.3 / §5.3 (fork from
    mode). The child conversation:

      * gets a fresh ``conversation_id`` (caller-supplied to keep the
        content-derived naming convention in the caller's hands)
      * inherits the parent's ``tag`` unless ``creation_tag`` explicitly
        selects a valid mode. This is a new envelope, so a Stealth override is
        allowed without making Stealth mutable on the parent.
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
    child_tag = creation_tag if creation_tag in CONVERSATION_TAGS else parent_tag
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
    parent_contributors = normalize_contributors(parent.get("contributors"))

    child = {
        "conversation_id":         new_id,
        "display_name":            derived_display,
        "tag":                     child_tag,
        "created":                 forked_at,
        "parent_conversation_id":  parent_id,
        "fork_point_chunk_id":     fork_point_chunk_id,
        "forked_at":               forked_at,
        "project_ids":             list(parent_projects),
        "description":             (
            parent.get("description")
            if isinstance(parent.get("description"), str) else ""
        ),
        "contributors":            copy.deepcopy(parent_contributors),
        "messages":                copy.deepcopy(parent_messages),
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
    "MUTABLE_PRIVACY_TAGS",
    "ConversationPlanLifecycleError",
    "validate_conversation_id",
    "normalize_contributors",
    "create_conversation_envelope",
    "WELCOME_CONVERSATION_ID",
    "WELCOME_PLACEHOLDER_BODY",
    "load_conversation_json",
    "load_process_plan_lifecycle",
    "ensure_conversation_envelope",
    "save_turn_spatial_state",
    "persist_process_plan_lifecycle",
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
    "ensure_welcome_thread",
    "set_display_name",
    "set_conversation_pinned",
    "set_conversation_closed",
    "set_conversation_projects",
]
