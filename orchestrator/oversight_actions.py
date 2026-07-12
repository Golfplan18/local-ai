"""Oversight verdict-action handlers.

Implements PROCEED / REVISE / ESCALATE / ESCALATE-redefinition handlers per
Reference — Meta-Layer Architecture §9. Each verdict translates into actual
state changes: Decision Log appends, framework chain dispatch, human-queue
surfacing, dependent-corpus actions.

Includes a small file-lock primitive for PED, corpus, and workflow spec
write coordination (per §10 O4 — concurrent PED writes).

Author: meta-layer implementation per Reference — Meta-Layer Architecture §9.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from oversight_context import OversightContextBundle
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator.oversight_context import OversightContextBundle

# Cross-platform file lock (fcntl on POSIX, msvcrt on Windows) — replaces the
# former top-level `import fcntl`, which crashed the whole oversight system on
# Windows import.
try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


# Roots flow from runtime_paths (ORA_HOME-relocatable) so gate-queued
# Paused entries land under the same root as tool events and approvals.
WORKSPACE = _rp.WORKSPACE
OVERSIGHT_DATA_DIR = os.path.join(_rp.DATA_DIR_STR, "oversight")
HUMAN_QUEUE_PATH = os.path.join(OVERSIGHT_DATA_DIR, "human-queue.jsonl")
ACTIONS_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "actions.jsonl")
PED_DERIVATIVES_PATH = os.path.join(
    OVERSIGHT_DATA_DIR, "conversation-ped-derivatives.json",
)
_HUMAN_QUEUE_DEFAULT = HUMAN_QUEUE_PATH   # import-time values; patch anchors
_ACTIONS_LOG_DEFAULT = ACTIONS_LOG_PATH
_PED_DERIVATIVES_DEFAULT = PED_DERIVATIVES_PATH

DEFAULT_LOCK_TIMEOUT = 30  # seconds, per §10 O4
REVISE_LIMIT = 3  # per §10 O3


def human_queue_path() -> str:
    """Effective human-queue path: an explicit monkeypatch of
    HUMAN_QUEUE_PATH wins; otherwise the ORA_OVERSIGHT_SANDBOX quarantine
    (test runs) applies; otherwise the live queue. Shared with
    slash_commands so /queue, /approve and /deny address the same file the
    escalation writers append to."""
    if HUMAN_QUEUE_PATH != _HUMAN_QUEUE_DEFAULT:
        return HUMAN_QUEUE_PATH
    return _rp.sandboxed_file(HUMAN_QUEUE_PATH)


def _actions_log_path() -> str:
    if ACTIONS_LOG_PATH != _ACTIONS_LOG_DEFAULT:
        return ACTIONS_LOG_PATH
    return _rp.sandboxed_file(ACTIONS_LOG_PATH)


def _ped_derivatives_path() -> str:
    if PED_DERIVATIVES_PATH != _PED_DERIVATIVES_DEFAULT:
        return PED_DERIVATIVES_PATH
    return _rp.sandboxed_file(PED_DERIVATIVES_PATH)


def _lifecycle_context(record: dict | None = None) -> tuple[bool, str | None]:
    """Resolve lifecycle state through the canonical oversight helper."""
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover - package-qualified import context
        from orchestrator.oversight_events import resolve_lifecycle_context
    return resolve_lifecycle_context(record)


def _private_context(record: dict | None, conversation_id: str | None) -> bool:
    """Return whether a managed derivative must stay out of the vault.

    Explicit event metadata wins.  Direct execution paths do not all carry a
    tag, so the conversation envelope is the runtime source of truth fallback.
    """
    candidate = record if isinstance(record, dict) else {}
    nested = candidate.get("event")
    nested = nested if isinstance(nested, dict) else {}
    for value in (
        candidate.get("conversation_tag"), candidate.get("tag"),
        nested.get("conversation_tag"), nested.get("tag"),
    ):
        if value == "private":
            return True
        if value in {"", "standard"}:
            return False
    # The server seeds boot's ContextVar before the first turn begins, while
    # the conversation envelope is intentionally not created until save. This
    # is therefore the authoritative first-turn Private signal.
    boot_module = sys.modules.get("boot") or sys.modules.get("orchestrator.boot")
    if boot_module is not None:
        try:
            if boot_module._CONVERSATION_TAG_CV.get() == "private":
                return True
        except Exception:
            pass
    if not conversation_id:
        return False
    try:
        try:
            from conversation_memory import get_conversation_tag
        except ImportError:  # pragma: no cover
            from orchestrator.conversation_memory import get_conversation_tag
        return get_conversation_tag(conversation_id) == "private"
    except Exception:
        return False


# ---------- File lock primitive ----------

@contextlib.contextmanager
def file_lock(path: str, timeout: float = DEFAULT_LOCK_TIMEOUT):
    """Acquire an exclusive advisory lock on a sidecar lockfile for `path`.

    Delegates to the cross-platform ``runtime_paths.locked_file`` (fcntl on
    POSIX, msvcrt on Windows); the sidecar-lockfile semantics are preserved.
    Kept as a thin wrapper so existing oversight callers are unchanged.
    """
    with _rp.locked_file(path, timeout=timeout):
        yield


# ---------- Conversation-owned PED Decision Log derivatives ----------

_PED_DERIVATIVE_VERSION = 1
_PED_MARKER_START_RE = re.compile(
    r"^<!-- ora:oversight-derivative:start "
    r"id=([0-9a-f]{32}) owner=([0-9a-f]{64}) -->$",
)


def _owner_key(conversation_id: str) -> str:
    identity = str(conversation_id or "").strip().casefold()
    if not identity:
        raise ValueError("conversation_id is required")
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _marker_start(derivative_id: str, owner_key: str) -> str:
    return (
        "<!-- ora:oversight-derivative:start "
        f"id={derivative_id} owner={owner_key} -->"
    )


def _marker_end(derivative_id: str) -> str:
    return f"<!-- ora:oversight-derivative:end id={derivative_id} -->"


def _managed_block(derivative_id: str, owner_key: str, entry_text: str) -> str:
    return (
        f"{_marker_start(derivative_id, owner_key)}\n"
        f"{entry_text.rstrip()}\n"
        f"{_marker_end(derivative_id)}\n"
    )


def _read_text_no_follow(path: Path) -> tuple[str, int]:
    """Read a regular file without following a final-component symlink."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"refusing non-regular file: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            return stream.read(), stat.S_IMODE(info.st_mode)
    finally:
        if fd >= 0:
            os.close(fd)


def _rewrite_regular_text(path: Path, transform) -> tuple[bool, object]:
    """Lock, transform, and atomically rewrite one regular PED file."""
    with file_lock(str(path)):
        content, mode = _read_text_no_follow(path)
        replacement, detail = transform(content)
        if replacement == content:
            return False, detail
        _rp.atomic_write_text(path, replacement, mode=mode)
        return True, detail


def _empty_derivatives_manifest() -> dict:
    return {"version": _PED_DERIVATIVE_VERSION, "derivatives": []}


def _load_derivatives_manifest(path: Path) -> dict:
    if not path.exists() and not path.is_symlink():
        return _empty_derivatives_manifest()
    text, _mode = _read_text_no_follow(path)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("PED derivative manifest is not an object")
    if payload.get("version") != _PED_DERIVATIVE_VERSION:
        raise ValueError(
            f"unsupported PED derivative manifest version: "
            f"{payload.get('version')!r}",
        )
    entries = payload.get("derivatives")
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) for entry in entries
    ):
        raise ValueError("PED derivative manifest entries are invalid")
    return payload


def _save_derivatives_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing symlink PED derivative manifest: {path}")
    _rp.atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _add_managed_block(
    content: str,
    derivative_id: str,
    owner_key: str,
    entry_text: str,
) -> tuple[str, int]:
    start = _marker_start(derivative_id, owner_key)
    end = _marker_end(derivative_id)
    has_start = start in content
    has_end = end in content
    if has_start != has_end:
        raise ValueError(
            f"incomplete managed PED marker pair for {derivative_id}",
        )
    if has_start:
        return content, 0
    return _insert_into_decision_log(
        content, _managed_block(derivative_id, owner_key, entry_text),
    ), 1


def _remove_managed_blocks(
    content: str,
    owner_key: str,
    derivative_ids: set[str] | None = None,
) -> tuple[str, int]:
    """Remove only complete hidden blocks owned by ``owner_key``."""
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    removed = 0
    index = 0
    while index < len(lines):
        marker = _PED_MARKER_START_RE.match(lines[index].rstrip("\r\n"))
        if not marker or marker.group(2) != owner_key or (
            derivative_ids is not None and marker.group(1) not in derivative_ids
        ):
            output.append(lines[index])
            index += 1
            continue
        derivative_id = marker.group(1)
        expected_end = _marker_end(derivative_id)
        end_index = index + 1
        while end_index < len(lines):
            if lines[end_index].rstrip("\r\n") == expected_end:
                break
            end_index += 1
        if end_index >= len(lines):
            raise ValueError(
                f"unterminated managed PED block {derivative_id}",
            )
        index = end_index + 1
        # The insertion helper puts a blank separator after the block. Remove
        # at most that one separator; never consume user-authored content.
        if index < len(lines) and not lines[index].strip():
            index += 1
        removed += 1
    return "".join(output), removed


def _extract_managed_blocks(
    content: str,
    owner_key: str,
) -> list[tuple[str, str]]:
    """Return complete ``(derivative_id, entry_text)`` blocks for an owner."""
    lines = content.splitlines(keepends=True)
    extracted: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        marker = _PED_MARKER_START_RE.match(lines[index].rstrip("\r\n"))
        if not marker or marker.group(2) != owner_key:
            index += 1
            continue
        derivative_id = marker.group(1)
        expected_end = _marker_end(derivative_id)
        end_index = index + 1
        while end_index < len(lines):
            if lines[end_index].rstrip("\r\n") == expected_end:
                break
            end_index += 1
        if end_index >= len(lines):
            raise ValueError(
                f"unterminated managed PED block {derivative_id}",
            )
        extracted.append((derivative_id, "".join(lines[index + 1:end_index])))
        index = end_index + 1
    return extracted


def _manifest_entry_matches(
    entry: dict, conversation_id: str, owner_key: str,
) -> bool:
    if entry.get("owner_key") == owner_key:
        return True
    value = entry.get("conversation_id")
    return isinstance(value, str) and value.casefold() == conversation_id.casefold()


def _current_manifest_ped_path(entry: dict) -> Path:
    """Resolve a moved PED through its registered project nexus when possible."""
    raw_path = entry.get("ped_path")
    path = Path(raw_path) if isinstance(raw_path, str) and raw_path else None
    if path is not None and (path.exists() or path.is_symlink()):
        return path
    project_nexus = entry.get("project_nexus")
    if isinstance(project_nexus, str) and project_nexus:
        try:
            try:
                from ped_watcher import load_ped_path
            except ImportError:  # pragma: no cover
                from orchestrator.ped_watcher import load_ped_path
            current = load_ped_path(project_nexus)
            if current:
                replacement = Path(current)
                entry["ped_path"] = str(replacement)
                return replacement
        except Exception:
            pass
    if path is None:
        raise ValueError(
            f"manifest entry {entry.get('derivative_id')} has no PED path",
        )
    return path


def _trusted_manifest_ped_path(
    path: Path,
    discover_root: str | Path | None,
) -> Path:
    """Normalize and enforce the closeout caller's trusted vault boundary."""
    target = Path(os.path.abspath(os.path.expanduser(str(path))))
    if discover_root is not None and not _rp.within_base(target, discover_root):
        raise ValueError(f"PED path is outside trusted root: {target}")
    if target.is_symlink():
        raise ValueError(f"refusing symlink PED path: {target}")
    if target.exists() and not target.is_file():
        raise ValueError(f"refusing non-regular PED path: {target}")
    return target


def append_managed_decision_log_entry(
    ped_path: str,
    entry_text: str,
    event: dict,
    *,
    kind: str,
    action_record: dict | None = None,
) -> str | None:
    """Persist one conversation-owned Decision Log derivative.

    Standard entries are wrapped in exact hidden markers inside the PED.
    Private entries are retained only in the non-vault manifest so a later
    move back to Standard is reversible. Stealth entries are never written.
    The manifest is written before the PED, making a crash recoverable without
    risking an unowned visible block.
    """
    action_record = action_record if action_record is not None else {}
    stealth, conversation_id = _lifecycle_context(event)
    if stealth:
        action_record["decision_log_suppressed"] = "stealth"
        return None

    target = Path(os.path.abspath(os.path.expanduser(str(ped_path))))
    if not conversation_id:
        # Daemon-originated oversight has no conversation lifecycle owner. It
        # remains a normal PED audit entry, but still uses the safe writer.
        try:
            _rewrite_regular_text(
                target,
                lambda content: (_insert_into_decision_log(content, entry_text), 1),
            )
        except Exception as exc:
            action_record["decision_log_write_failed"] = str(exc)
            print(f"[oversight] Decision Log write failed: {exc}", flush=True)
        return None

    owner_key = _owner_key(conversation_id)
    derivative_id = uuid.uuid4().hex
    private = _private_context(event, conversation_id)
    manifest_path = Path(_ped_derivatives_path())
    manifest_entry = {
        "derivative_id": derivative_id,
        "conversation_id": conversation_id,
        "owner_key": owner_key,
        "ped_path": str(target),
        "project_nexus": str(event.get("project_nexus") or ""),
        "kind": str(kind),
        "entry_text": entry_text,
        "visible": False,
        "created_at": _now_iso(),
    }
    try:
        with file_lock(str(manifest_path)):
            payload = _load_derivatives_manifest(manifest_path)
            payload["derivatives"].append(manifest_entry)
            _save_derivatives_manifest(manifest_path, payload)
            if not private:
                changed, _ = _rewrite_regular_text(
                    target,
                    lambda content: _add_managed_block(
                        content, derivative_id, owner_key, entry_text,
                    ),
                )
                manifest_entry["visible"] = True
                _save_derivatives_manifest(manifest_path, payload)
                if changed:
                    action_record["decision_log_ped_path"] = str(target)
            action_record["decision_log_derivative_id"] = derivative_id
            if private:
                action_record["decision_log_visibility"] = "private_sidecar"
        return derivative_id
    except Exception as exc:
        action_record["decision_log_write_failed"] = str(exc)
        print(f"[oversight] managed Decision Log write failed: {exc}", flush=True)
        return None


def _discover_owned_ped_paths(
    root: Path,
    owner_key: str,
) -> tuple[set[Path], set[Path], list[str]]:
    """Find marker-owned Markdown files without following symlink children."""
    found: set[Path] = set()
    failed: set[Path] = set()
    errors: list[str] = []
    if not root.exists():
        return found, failed, errors
    marker_fragment = f"owner={owner_key} -->"
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name for name in dirnames
            if name not in {".git", ".obsidian"}
            and not (Path(directory) / name).is_symlink()
        ]
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            path = Path(directory) / filename
            try:
                text, _mode = _read_text_no_follow(path)
                if marker_fragment in text:
                    found.add(path)
            except Exception as exc:
                failed.add(path)
                errors.append(f"PED ownership scan {path}: {exc}")
    return found, failed, errors


def purge_conversation_revise_counters(conversation_id: str) -> dict:
    """Remove revision counters owned by one conversation."""
    owner_prefix = f"conversation:{_owner_key(conversation_id)}::"
    path = Path(_revise_counters_path())
    result = {"counter_entries": 0, "errors": []}
    if not path.exists() and not path.is_symlink():
        return result
    try:
        with file_lock(str(path)):
            text, mode = _read_text_no_follow(path)
            counters = json.loads(text)
            if not isinstance(counters, dict):
                raise ValueError("revise counters are not an object")
            matching = [key for key in counters if key.startswith(owner_prefix)]
            for key in matching:
                counters.pop(key, None)
            if matching:
                _rp.atomic_write_text(
                    path,
                    json.dumps(counters, ensure_ascii=False, indent=2) + "\n",
                    mode=mode,
                )
            result["counter_entries"] = len(matching)
    except Exception as exc:
        result["errors"].append(f"revise counters: {exc}")
    return result


def set_conversation_ped_derivatives_private(
    conversation_id: str,
    private: bool,
    *,
    discover_root: str | Path | None = None,
) -> dict:
    """Hide or restore every tracked PED derivative for a conversation.

    ``requires_reindex`` names the project files whose knowledge-index rows
    must be replaced by the caller after this surgical Markdown mutation.
    """
    cid = str(conversation_id or "").strip()
    owner_key = _owner_key(cid)
    manifest_path = Path(_ped_derivatives_path())
    report = {
        "conversation_id": cid,
        "private": bool(private),
        "manifest_entries": 0,
        "ped_blocks": 0,
        "modified_paths": [],
        "failed_paths": [],
        "requires_reindex": [],
        "errors": [],
    }
    if (not manifest_path.exists() and not manifest_path.is_symlink()
            and not (private and discover_root is not None)):
        return report
    try:
        with file_lock(str(manifest_path)):
            payload = _load_derivatives_manifest(manifest_path)
            entries = [
                entry for entry in payload["derivatives"]
                if _manifest_entry_matches(entry, cid, owner_key)
            ]
            if private and discover_root is not None:
                discovered, scan_failed, scan_errors = _discover_owned_ped_paths(
                    Path(discover_root), owner_key,
                )
                report["failed_paths"].extend(str(path) for path in scan_failed)
                report["errors"].extend(scan_errors)
                for path in sorted(discovered, key=str):
                    report["requires_reindex"].append(str(path))
                    try:
                        text, _mode = _read_text_no_follow(path)
                        for derivative_id, entry_text in _extract_managed_blocks(
                            text, owner_key,
                        ):
                            matching_id = [
                                entry for entry in entries
                                if entry.get("derivative_id") == derivative_id
                            ]
                            relocated = next(
                                (
                                    entry for entry in matching_id
                                    if not Path(str(entry.get("ped_path") or "")).exists()
                                ),
                                None,
                            )
                            same_path = any(
                                os.path.normcase(os.path.abspath(
                                    str(entry.get("ped_path") or "")
                                )) == os.path.normcase(os.path.abspath(str(path)))
                                for entry in matching_id
                            )
                            if relocated is not None:
                                relocated["ped_path"] = str(path)
                            elif not same_path:
                                recovered = {
                                    "derivative_id": derivative_id,
                                    "conversation_id": cid,
                                    "owner_key": owner_key,
                                    "ped_path": str(path),
                                    "project_nexus": "",
                                    "kind": "recovered_marker_block",
                                    "entry_text": entry_text,
                                    "visible": True,
                                    "created_at": _now_iso(),
                                }
                                payload["derivatives"].append(recovered)
                                entries.append(recovered)
                    except Exception as exc:
                        report["failed_paths"].append(str(path))
                        report["errors"].append(
                            f"PED derivative recovery {path}: {exc}",
                        )
            report["manifest_entries"] = len(entries)
            by_path: dict[Path, list[dict]] = {}
            for entry in entries:
                try:
                    path = _trusted_manifest_ped_path(
                        _current_manifest_ped_path(entry), discover_root,
                    )
                except Exception as exc:
                    raw_path = entry.get("ped_path")
                    if isinstance(raw_path, str) and raw_path:
                        report["failed_paths"].append(raw_path)
                    report["errors"].append(
                        f"manifest entry {entry.get('derivative_id')}: {exc}",
                    )
                    continue
                by_path.setdefault(path, []).append(entry)

            for path, path_entries in by_path.items():
                report["requires_reindex"].append(str(path))
                try:
                    if private:
                        ids = {
                            str(entry.get("derivative_id"))
                            for entry in path_entries
                        }
                        changed, removed = _rewrite_regular_text(
                            path,
                            lambda content, _ids=ids: _remove_managed_blocks(
                                content, owner_key, _ids,
                            ),
                        )
                        report["ped_blocks"] += int(removed)
                        if changed:
                            report["modified_paths"].append(str(path))
                        for entry in path_entries:
                            entry["visible"] = False
                    else:
                        changed_any = False
                        added = 0
                        for entry in path_entries:
                            derivative_id = str(entry.get("derivative_id") or "")
                            entry_text = entry.get("entry_text")
                            if not re.fullmatch(r"[0-9a-f]{32}", derivative_id):
                                raise ValueError(
                                    f"invalid derivative id {derivative_id!r}",
                                )
                            if not isinstance(entry_text, str):
                                raise ValueError(
                                    f"derivative {derivative_id} has no reversible text",
                                )
                            changed, count = _rewrite_regular_text(
                                path,
                                lambda content, _id=derivative_id, _text=entry_text:
                                    _add_managed_block(
                                        content, _id, owner_key, _text,
                                    ),
                            )
                            changed_any = bool(changed_any or changed)
                            added += int(count)
                            entry["visible"] = True
                        report["ped_blocks"] += added
                        if changed_any:
                            report["modified_paths"].append(str(path))
                except Exception as exc:
                    report["failed_paths"].append(str(path))
                    report["errors"].append(f"PED derivative {path}: {exc}")
            _save_derivatives_manifest(manifest_path, payload)
    except Exception as exc:
        report["errors"].append(f"PED derivative manifest: {exc}")
    report["requires_reindex"] = sorted(set(report["requires_reindex"]))
    report["modified_paths"] = sorted(set(report["modified_paths"]))
    report["failed_paths"] = sorted(set(report["failed_paths"]))
    return report


def purge_conversation_ped_derivatives(
    conversation_id: str,
    *,
    discover_root: str | Path | None = None,
) -> dict:
    """Delete exact PED blocks and reversible sidecar entries for one owner.

    ``discover_root`` enables a marker scan as a recovery backstop when a
    prior crash wrote the PED but did not finish the manifest transaction.
    """
    cid = str(conversation_id or "").strip()
    owner_key = _owner_key(cid)
    manifest_path = Path(_ped_derivatives_path())
    report = {
        "conversation_id": cid,
        "manifest_entries": 0,
        "ped_blocks": 0,
        "counter_entries": 0,
        "modified_paths": [],
        "failed_paths": [],
        "requires_reindex": [],
        "errors": [],
    }
    payload: dict | None = None
    matching_entries: list[dict] = []
    known_paths: set[Path] = set()
    failed_derivative_ids: set[str] = set()
    manifest_error = False
    try:
        with file_lock(str(manifest_path)):
            payload = _load_derivatives_manifest(manifest_path)
            matching_entries = [
                entry for entry in payload["derivatives"]
                if _manifest_entry_matches(entry, cid, owner_key)
            ]
            report["manifest_entries"] = len(matching_entries)
            for entry in matching_entries:
                try:
                    known_paths.add(_trusted_manifest_ped_path(
                        _current_manifest_ped_path(entry), discover_root,
                    ))
                except Exception as exc:
                    failed_derivative_ids.add(str(entry.get("derivative_id") or ""))
                    raw_path = entry.get("ped_path")
                    if isinstance(raw_path, str) and raw_path:
                        report["failed_paths"].append(raw_path)
                    report["errors"].append(
                        f"manifest entry {entry.get('derivative_id')}: {exc}",
                    )

            if discover_root is not None:
                discovered, scan_failed, scan_errors = _discover_owned_ped_paths(
                    Path(discover_root), owner_key,
                )
                known_paths.update(discovered)
                report["failed_paths"].extend(str(path) for path in scan_failed)
                report["errors"].extend(scan_errors)

            failed_paths: set[str] = set()
            for path in sorted(known_paths, key=str):
                report["requires_reindex"].append(str(path))
                if not path.exists() and not path.is_symlink():
                    continue
                try:
                    changed, removed = _rewrite_regular_text(
                        path,
                        lambda content: _remove_managed_blocks(
                            content, owner_key,
                        ),
                    )
                    report["ped_blocks"] += int(removed)
                    if changed:
                        report["modified_paths"].append(str(path))
                except Exception as exc:
                    failed_paths.add(os.path.normcase(os.path.abspath(str(path))))
                    report["failed_paths"].append(str(path))
                    report["errors"].append(f"PED derivative {path}: {exc}")

            kept: list[dict] = []
            removed_entries = 0
            for entry in payload["derivatives"]:
                if not _manifest_entry_matches(entry, cid, owner_key):
                    kept.append(entry)
                    continue
                if str(entry.get("derivative_id") or "") in failed_derivative_ids:
                    kept.append(entry)
                    continue
                raw_path = entry.get("ped_path")
                key = os.path.normcase(os.path.abspath(str(raw_path or "")))
                if key in failed_paths:
                    kept.append(entry)
                else:
                    removed_entries += 1
            payload["derivatives"] = kept
            if removed_entries:
                _save_derivatives_manifest(manifest_path, payload)
            report["manifest_entries"] = removed_entries
    except Exception as exc:
        manifest_error = True
        report["errors"].append(f"PED derivative manifest: {exc}")

    # A corrupt manifest must remain intact and loud. The marker scan can
    # still remove visible derivatives, but Delete must not report clean while
    # the reversible sidecar may retain conversation content.
    if manifest_error and discover_root is not None:
        discovered, scan_failed, scan_errors = _discover_owned_ped_paths(
            Path(discover_root), owner_key,
        )
        report["failed_paths"].extend(str(path) for path in scan_failed)
        report["errors"].extend(scan_errors)
        for path in sorted(discovered, key=str):
            try:
                changed, removed = _rewrite_regular_text(
                    path,
                    lambda content: _remove_managed_blocks(content, owner_key),
                )
                report["ped_blocks"] += int(removed)
                report["requires_reindex"].append(str(path))
                if changed:
                    report["modified_paths"].append(str(path))
            except Exception as exc:
                report["failed_paths"].append(str(path))
                report["errors"].append(f"PED derivative {path}: {exc}")

    counters = purge_conversation_revise_counters(cid)
    report["counter_entries"] = counters["counter_entries"]
    report["errors"].extend(counters["errors"])
    report["requires_reindex"] = sorted(set(report["requires_reindex"]))
    report["modified_paths"] = sorted(set(report["modified_paths"]))
    report["failed_paths"] = sorted(set(report["failed_paths"]))
    return report


# ---------- Verdict tracking ----------

REVISE_COUNTERS_PATH = os.path.join(OVERSIGHT_DATA_DIR, "revise-counters.json")
_REVISE_COUNTERS_DEFAULT = REVISE_COUNTERS_PATH


def _revise_counters_path() -> str:
    if REVISE_COUNTERS_PATH != _REVISE_COUNTERS_DEFAULT:
        return REVISE_COUNTERS_PATH
    return _rp.sandboxed_file(REVISE_COUNTERS_PATH)


def _load_revise_counters() -> dict:
    counters_path = _revise_counters_path()
    if not os.path.isfile(counters_path):
        return {}
    try:
        with open(counters_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_revise_counters(counters: dict, event: dict | None = None):
    stealth, _conversation_id = _lifecycle_context(event)
    if stealth:
        print("[oversight] revise-counter write skipped (Stealth context)", flush=True)
        return False
    counters_path = _revise_counters_path()
    os.makedirs(os.path.dirname(counters_path), exist_ok=True)
    with file_lock(counters_path):
        _rp.atomic_write_text(
            counters_path,
            json.dumps(counters, ensure_ascii=False, indent=2) + "\n",
        )
    return True


def _mutate_revise_counters(event: dict, transform) -> dict:
    """Run one lock-protected revise-counter read/modify/write transaction."""
    stealth, _conversation_id = _lifecycle_context(event)
    if stealth:
        print("[oversight] revise-counter mutation skipped (Stealth context)", flush=True)
        return {}
    path = Path(_revise_counters_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(str(path)):
        mode = 0o600
        if path.exists() or path.is_symlink():
            text, mode = _read_text_no_follow(path)
            counters = json.loads(text)
            if not isinstance(counters, dict):
                raise ValueError("revise counters are not an object")
        else:
            counters = {}
        before = json.dumps(counters, sort_keys=True, default=str)
        replacement = transform(dict(counters))
        if not isinstance(replacement, dict):
            raise ValueError("revise counter transform did not return an object")
        after = json.dumps(replacement, sort_keys=True, default=str)
        if before != after:
            _rp.atomic_write_text(
                path,
                json.dumps(replacement, ensure_ascii=False, indent=2) + "\n",
                mode=mode,
            )
        return replacement


def _revise_key(event: dict) -> str:
    """Per §10 O3, count REVISE verdicts per (milestone_id, project_nexus)."""
    base = (
        f"{event.get('project_nexus', '') or event.get('workflow_id', '')}::"
        f"{event.get('milestone_id') or event.get('section_id') or event.get('milestone_text', '')}"
    )
    _stealth, conversation_id = _lifecycle_context(event)
    if not conversation_id:
        return base
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"conversation:{_owner_key(conversation_id)}::{digest}"


# ---------- Main entry point ----------

def apply_verdict(
    event: dict,
    bundle: OversightContextBundle,
    mode: str,
    verdict: dict,
):
    """Apply the verdict-action for the given Process Coherence verdict."""
    event = dict(event)
    stealth, conversation_id = _lifecycle_context(event)
    if conversation_id and not event.get("conversation_id"):
        event["conversation_id"] = conversation_id
    verdict_label = (verdict.get("verdict") or "UNKNOWN").upper()
    action_record: dict = {
        "timestamp": _now_iso(),
        "event_type": event.get("event_type", ""),
        "project_nexus": event.get("project_nexus", ""),
        "workflow_id": event.get("workflow_id", ""),
        "mode": mode,
        "verdict": verdict_label,
        "reasoning": (verdict.get("reasoning") or "")[:500],
        "conversation_id": event.get("conversation_id", ""),
    }

    if stealth:
        action_record["action"] = "stealth_suppressed"
        return action_record

    if verdict_label == "PROCEED":
        _apply_proceed(event, bundle, action_record)
    elif verdict_label == "REVISE":
        _apply_revise(event, bundle, verdict, action_record)
    elif verdict_label.startswith("ESCALATE"):
        _apply_escalate(event, bundle, verdict, action_record, redefinition="REDEFINITION" in verdict_label)
    else:
        action_record["action"] = "unknown_verdict"

    _append_actions_log(action_record)
    return action_record


# ---------- Verdict implementations ----------

def _apply_proceed(event: dict, bundle: OversightContextBundle, action_record: dict):
    """PROCEED — record Decision Log entry; dispatch downstream where appropriate."""
    _append_decision_log_entry(event, bundle, "PROCEED", action_record)

    # Reset REVISE counter for this milestone
    key = _revise_key(event)
    _mutate_revise_counters(
        event,
        lambda counters: {k: v for k, v in counters.items() if k != key},
    )

    et = event.get("event_type", "")
    if et == "FrameworkComplete":
        # If the project's oversight spec has a framework chain, dispatch the next one
        chain = bundle.framework_chain or []
        current_idx = _find_framework_in_chain(chain, event.get("framework_id", ""))
        if current_idx is not None and current_idx + 1 < len(chain):
            next_framework = chain[current_idx + 1]
            action_record["next_framework_dispatch"] = (
                next_framework.get("id") if isinstance(next_framework, dict) else next_framework
            )

    if et == "CorpusValidated":
        # Auto-dispatch eligible OFFs
        action_record["off_dispatch_pending"] = True

    if et == "ChainPropagationRequired":
        # Dispatch the propagation action per the chain rule
        action_record["chain_propagation_dispatched"] = event.get("dependent_corpora", [])

    action_record["action"] = "proceed"


def _apply_revise(event: dict, bundle: OversightContextBundle, verdict: dict, action_record: dict):
    """REVISE — record corrective action; cap revisions at 3 per §10 O3."""
    key = _revise_key(event)
    state: dict[str, int] = {"count": 0}

    def increment(counters: dict) -> dict:
        count = int(counters.get(key, 0)) + 1
        state["count"] = count
        if count >= REVISE_LIMIT:
            counters.pop(key, None)
        else:
            counters[key] = count
        return counters

    _mutate_revise_counters(event, increment)

    if state["count"] >= REVISE_LIMIT:
        # Force escalate after 3 revisions
        _apply_escalate(
            event,
            bundle,
            verdict,
            action_record,
            redefinition=False,
            forced_reason=f"REVISE limit ({REVISE_LIMIT}) reached for {key}",
        )
        return

    _append_decision_log_entry(event, bundle, "REVISE", action_record, extra_text=verdict.get("reasoning", ""))
    action_record["action"] = "revise"
    action_record["revise_count"] = state["count"]
    action_record["corrective_specification"] = verdict.get("reasoning", "")


def _apply_escalate(
    event: dict,
    bundle: OversightContextBundle,
    verdict: dict,
    action_record: dict,
    redefinition: bool = False,
    forced_reason: str = "",
):
    """ESCALATE — pause chain, surface to human queue."""
    _append_decision_log_entry(
        event, bundle,
        "ESCALATE (redefinition)" if redefinition else "ESCALATE",
        action_record,
        extra_text=verdict.get("reasoning", "") + (f"\n\nForced: {forced_reason}" if forced_reason else ""),
    )

    queue_entry = {
        "queued_at": _now_iso(),
        "conversation_id": event.get("conversation_id", ""),
        "event": event,
        "verdict": verdict,
        "redefinition": redefinition,
        "forced_reason": forced_reason,
        "context_summary": {
            "project_nexus": event.get("project_nexus", ""),
            "workflow_id": event.get("workflow_id", ""),
            "claim": bundle.claim,
            "load_errors": bundle.load_errors,
        },
    }
    # Route through oversight_queue so the entry gets a stable id and an
    # AI-generated default name (used by the V3 sidebar Paused panel).
    # Falls back to a direct write if oversight_queue is unavailable for
    # any reason — preserves the existing behavior.
    try:
        from oversight_queue import add_entry as _add_queue_entry
        _add_queue_entry(queue_entry)
    except Exception:
        _append_human_queue(queue_entry)
    action_record["action"] = "escalate" + ("_redefinition" if redefinition else "")
    action_record["queued_for_human_review"] = True


# ---------- Decision Log appending ----------

def _append_decision_log_entry(
    event: dict,
    bundle: OversightContextBundle,
    verdict_label: str,
    action_record: dict,
    extra_text: str = "",
):
    """Append a Decision Log entry to the project's PED.

    Section: ## Decision Log. Lock-protected fields (Mission, Excluded
    Outcomes, Constraints) are NOT modified — only the Decision Log section.
    Per §10 O5, lock-protected mutations are rejected at the writer level.
    """
    stealth, conversation_id = _lifecycle_context(event)
    if stealth:
        action_record["decision_log_suppressed"] = "stealth"
        return
    if conversation_id and not event.get("conversation_id"):
        event = {**event, "conversation_id": conversation_id}

    project_nexus = event.get("project_nexus", "")
    if not project_nexus:
        return

    from ped_watcher import load_ped_path
    ped_path = load_ped_path(project_nexus)
    if not ped_path or not os.path.isfile(ped_path):
        return

    entry_lines = [
        f"### {_today_iso()} — Process Coherence Verdict: {verdict_label}",
        f"- Event type: {event.get('event_type', '')}",
        f"- Mode: {action_record.get('mode', '')}",
    ]
    milestone_ref = (
        event.get("milestone_text")
        or event.get("milestone_id")
        or event.get("section_id")
        or ""
    )
    if milestone_ref:
        entry_lines.append(f"- Milestone/section: {milestone_ref}")
    if extra_text:
        entry_lines.append("- Reasoning:")
        for line in extra_text.split("\n"):
            entry_lines.append(f"  > {line}")
    entry_text = "\n".join(entry_lines) + "\n\n"

    append_managed_decision_log_entry(
        ped_path,
        entry_text,
        event,
        kind="process_coherence_verdict",
        action_record=action_record,
    )


def _insert_into_decision_log(content: str, entry_text: str) -> str:
    """Insert entry into the ## Decision Log section. If the section doesn't
    exist, append it to the end of the file.
    """
    import re
    # Find the Decision Log section
    match = re.search(r"^##\s+Decision Log\s*$", content, re.MULTILINE)
    if not match:
        # Append a new section at end
        return content.rstrip() + "\n\n## Decision Log\n\n" + entry_text

    insert_pos = match.end()
    # Insert immediately after the heading line
    return (
        content[:insert_pos] + "\n\n" + entry_text + content[insert_pos:].lstrip("\n")
    )


# ---------- Human queue ----------

def _append_human_queue(entry: dict):
    # Stealth-context awareness: skip persistence for events derived from
    # stealth-tagged conversations. The escalation still surfaces to the
    # in-process handlers; only the on-disk human-queue.jsonl write is
    # suppressed so stealth conversations leave no residue.
    stealth, cid = _lifecycle_context(entry)
    if stealth:
        print(
            f"[oversight] human-queue write skipped (Stealth context); "
            f"entry: {entry.get('event_type', '_unknown_')}",
            flush=True,
        )
        return
    if cid and not entry.get("conversation_id"):
        entry = dict(entry)
        entry["conversation_id"] = cid
    queue_path = human_queue_path()
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)
    encoded = (json.dumps(entry, default=str) + "\n").encode("utf-8")
    with file_lock(queue_path):
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(queue_path, flags, 0o600)
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)


def read_human_queue() -> list[dict]:
    """Read pending human-queue entries. Used by UI to surface escalations."""
    queue_path = human_queue_path()
    if not os.path.isfile(queue_path):
        return []
    out = []
    try:
        with open(queue_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


# ---------- Helpers ----------

def _find_framework_in_chain(chain: list, framework_id: str) -> Optional[int]:
    for i, f in enumerate(chain):
        if isinstance(f, dict) and f.get("id") == framework_id:
            return i
        if f == framework_id:
            return i
    return None


def _append_actions_log(record: dict):
    # Stealth-context awareness: same pattern as _append_human_queue —
    # skip the on-disk write when the current thread is serving a
    # stealth-tagged conversation. In-process callers still observe the
    # action.
    stealth, cid = _lifecycle_context(record)
    if stealth:
        print(
            f"[oversight] actions-log write skipped (Stealth context); "
            f"record: {record.get('action', '_unknown_')}",
            flush=True,
        )
        return
    if cid and not record.get("conversation_id"):
        record = dict(record)
        record["conversation_id"] = cid
    log_path = _actions_log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    encoded = (json.dumps(record, default=str) + "\n").encode("utf-8")
    with file_lock(log_path):
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(log_path, flags, 0o600)
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
