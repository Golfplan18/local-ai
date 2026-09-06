"""Read-only widget projections for the Overview Desktop.

This module is intentionally only an adapter.  The Project, Oversight,
Trigger, and Daily Note modules remain authoritative for their own records;
this code gives a renderer one small, stable shape without adding a cache,
store, scheduler, or mutation path.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import operation_matrix
    import oversight_queue
    import triggers
    from tools import daily_note
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import operation_matrix, oversight_queue, triggers
    from orchestrator.tools import daily_note


SOURCE_ORDER = ("project-priority", "oversight", "triggers", "daily-note", "matrix-tasks")
DAILY_NOTE_READ_MAX_BYTES = 4 * 1024 * 1024


def load_overview_widget_sources(
    *, observed_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return the five core Overview sources in a stable order.

    Every source is read independently.  A failed source therefore reports an
    unavailable record while the other sources remain usable.  ``observed_at``
    exists for deterministic callers and tests; production uses local time for
    the completed-day Daily Note and records the observation in UTC.
    """
    local_now = observed_at or datetime.now().astimezone()
    if local_now.tzinfo is None:
        local_now = local_now.astimezone()
    stamp = local_now.astimezone(timezone.utc).isoformat()
    completed_day = completed_daily_note_day(observed_at=local_now)
    skipped = []
    records = []
    project_error = None
    try:
        records = operation_matrix.list_active_project_meta(skipped_authority=skipped)
    except Exception as exc:
        project_error = exc
    return [
        _project_priority_source(stamp, records, skipped, project_error),
        _oversight_source(stamp),
        _trigger_source(stamp),
        _daily_note_source(stamp, completed_day),
        _matrix_tasks_source(stamp, records, skipped, project_error),
    ]


def completed_daily_note_day(*, observed_at: datetime | None = None) -> str:
    """Return the completed previous local day used by the Daily Note source."""
    local_now = observed_at or datetime.now().astimezone()
    if local_now.tzinfo is None:
        local_now = local_now.astimezone()
    return (local_now.date() - timedelta(days=1)).isoformat()


def inspect_daily_note_path(completed_day: str) -> tuple[Path, bool]:
    """Resolve one canonical Daily Note without following a root or file link.

    The boolean reports whether the target exists as a regular file.  A
    missing root and a missing target are both honest missing-note states;
    unsafe or unreadable filesystem objects raise instead.
    """
    parsed_day = datetime.strptime(completed_day, "%Y-%m-%d").date()
    if parsed_day.isoformat() != completed_day:
        raise ValueError("Daily Note date must use YYYY-MM-DD")

    root = Path(daily_note.daily_dir()).expanduser().absolute()
    target = root / f"{completed_day}.md"
    try:
        root_stat = root.lstat()
    except FileNotFoundError:
        return target, False
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise OSError(f"Daily Notes root is not a regular directory: {root}")

    try:
        target_stat = target.lstat()
    except FileNotFoundError:
        return target, False
    if stat.S_ISLNK(target_stat.st_mode) or not stat.S_ISREG(target_stat.st_mode):
        raise OSError(f"Daily Note is not a regular file: {target}")
    return target, True


def read_daily_note(completed_day: str) -> str:
    """Read only the body of one authenticated, bounded completed-day note."""
    import yaml

    target, exists = inspect_daily_note_path(completed_day)
    if not exists:
        raise FileNotFoundError("The Daily Note is no longer available.")

    def identity(item):
        return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)

    changed = "The Daily Note is unsafe or changed while being read. Reopen Overview and try again."
    try:
        # Bind the directory as well as the file: O_NOFOLLOW on the final file
        # alone would still follow a Daily Notes directory swapped to a link.
        root_before = target.parent.lstat()
        before = target.lstat()
        if (not stat.S_ISDIR(root_before.st_mode)
                or not stat.S_ISREG(before.st_mode)):
            raise ValueError(changed)
        if before.st_size > DAILY_NOTE_READ_MAX_BYTES:
            raise ValueError("This Daily Note exceeds Ora's safe 4 MiB rendered-document bound. Open externally to read it.")
        if not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("Safe Daily Note reading is unavailable on this host. Open externally to read it.")
        root_fd = os.open(target.parent, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_DIRECTORY", 0))
        try:
            root_opened = os.fstat(root_fd)
            if (not stat.S_ISDIR(root_opened.st_mode)
                    or identity(root_before) != identity(root_opened)):
                raise ValueError(changed)
            descriptor = os.open(
                target.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                dir_fd=root_fd,
            )
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
                    raise ValueError(changed)
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    data = stream.read(DAILY_NOTE_READ_MAX_BYTES + 1)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            current = target.lstat()
            if (identity(opened) != identity(after)
                    or identity(after) != identity(current)
                    or identity(root_opened) != identity(os.fstat(root_fd))
                    or identity(root_opened) != identity(target.parent.lstat())
                    or len(data) != after.st_size
                    or len(data) > DAILY_NOTE_READ_MAX_BYTES):
                raise ValueError(changed)
        finally:
            os.close(root_fd)
    except OSError as exc:
        raise ValueError(changed) from exc

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("This Daily Note is not valid UTF-8 text.") from exc
    frontmatter = re.match(r"\A---\r?\n(.*?)^---(?:\r?\n|\Z)", text, re.DOTALL | re.MULTILINE)
    if frontmatter is None:
        raise ValueError("This Daily Note has invalid or mismatched frontmatter.")
    try:
        metadata = yaml.safe_load(frontmatter.group(1))
    except (yaml.YAMLError, ValueError, RecursionError) as exc:
        raise ValueError("This Daily Note has invalid or mismatched frontmatter.") from exc
    if (not isinstance(metadata, dict) or metadata.get("type") != "daily-note"
            or not isinstance(metadata.get("date"), (str, date))
            or str(metadata["date"]) != completed_day):
        raise ValueError("This Daily Note has invalid or mismatched frontmatter.")
    return text[frontmatter.end():]


def _source(
    source_id: str,
    title: str,
    items: list[dict[str, Any]],
    stamp: str,
    *,
    state: str | None = None,
    count: int | None = None,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolved_state = state or ("ready" if items else "empty")
    available = resolved_state != "unavailable"
    return {
        "source_id": source_id,
        "title": title,
        "state": resolved_state,
        "count": len(items) if count is None else count,
        "available": available,
        "freshness": {
            "observed_at": stamp,
            "last_success_at": stamp if available else None,
        },
        "error": error,
        "items": items,
    }


def _item(
    source_id: str,
    item_id: str,
    title: str,
    text: str,
    state: str,
    *,
    count: int | None = None,
    time: str | None = None,
    scope: dict[str, str] | None = None,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "item_id": item_id,
        "title": title,
        "text": text,
        "state": state,
        "count": count,
        "time": time,
        "scope": scope,
        "actions": list(actions or []),
    }


def _error(code: str, exc: BaseException | str) -> dict[str, str]:
    message = str(exc).strip() or type(exc).__name__
    return {"code": code, "message": message}


def _required_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is missing")
    return value.strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _project_priority_source(stamp: str, records, skipped, project_error) -> dict[str, Any]:
    source_id = "project-priority"
    try:
        if project_error is not None:
            raise project_error
        items = []
        for record in records:
            nexus = _required_id(record.get("nexus"), "project nexus")
            title = _text(record.get("name") or record.get("display_name")) or nexus
            priority = record.get("priority")
            position = (
                f"Priority {priority + 1}"
                if isinstance(priority, int) and priority >= 0
                else "Unranked"
            )
            state = _text(record.get("status")) or "active"
            items.append(_item(
                source_id,
                f"project:{nexus}",
                title,
                f"{position} · {state}",
                state,
                time=_text(record.get("last_accessed_at") or record.get("created")) or None,
                scope={"project_nexus": nexus},
                actions=["open_project", "open_project_files", "open_project_dialogues", "open_project_knowledge"],
            ))
    except Exception as exc:
        return _source(
            source_id, "Project priority", [], stamp,
            state="unavailable", error=_error("project_source_unavailable", exc),
        )

    if skipped:
        names = ", ".join(sorted(set(skipped)))
        return _source(
            source_id, "Project priority", items, stamp, state="partial",
            error=_error("project_records_skipped", f"Unreadable project records: {names}"),
        )
    return _source(source_id, "Project priority", items, stamp)


def _matrix_tasks_source(stamp: str, records, skipped, project_error) -> dict[str, Any]:
    try:
        from . import matrix_tasks
    except ImportError:
        import matrix_tasks
    source_id = "matrix-tasks"
    items = []
    failures = list(skipped)
    try:
        if project_error is not None:
            raise project_error
        vault = operation_matrix.vault_root()
        requests = {record["nexus"]: record.get("folder_name") for record in records}
        snapshots = operation_matrix.resolve_matrix_snapshots(requests, vault=vault) if requests else {}
        for record in records:
            nexus = _required_id(record.get("nexus"), "project nexus")
            title = _text(record.get("name") or record.get("display_name")) or nexus
            group = matrix_tasks.group_from_snapshot(nexus, record.get("folder_name"), snapshots[nexus], vault=vault)
            count = group["counts"]["total"]
            text = group["reason"] or f"{count} tasks · {group['counts']['incomplete']} incomplete"
            item = _item(source_id, f"project:{nexus}", title, text, group["state"],
                         count=count, scope={"project_nexus": nexus}, actions=group["actions"])
            item.update(group)
            items.append(item)
    except Exception as exc:
        result = _source(source_id, "Tasks", [], stamp, state="unavailable", error=_error("task_source_unavailable", exc))
        result["count"] = None
        return result
    known = [item["counts"]["total"] for item in items if item["counts"]["total"] is not None]
    partial = bool(failures or any(item["state"] not in ("ready", "empty") for item in items))
    state = "partial" if partial else "ready" if items else "empty"
    if items and not known:
        state = "unavailable"
    error = (_error("project_records_skipped", "Unreadable project records: " + ", ".join(failures)) if failures
             else _error("task_source_incomplete", "Known task counts only; some Matrix content or project authority needs attention.") if partial else None)
    result = _source(source_id, "Tasks", items, stamp, state=state, error=error)
    result["count"] = sum(known) if known else None if items or failures else 0
    return result


def _oversight_source(stamp: str) -> dict[str, Any]:
    source_id = "oversight"
    items: list[dict[str, Any]] = []
    failures: list[str] = []
    usable_lanes = 0

    try:
        paused = oversight_queue.list_paused()
        for entry in paused:
            entry_id = _required_id(getattr(entry, "id", None), "paused entry id")
            event = getattr(entry, "event", None) or {}
            verdict = getattr(entry, "verdict", None) or {}
            context = getattr(entry, "context_summary", None) or {}
            project = _text(
                event.get("project_nexus")
                or context.get("project_nexus")
            )
            detail = (
                _text(getattr(entry, "forced_reason", ""))
                or _text(verdict.get("reasoning"))
                or _text(event.get("summary") or event.get("event_type"))
                or "Awaiting review"
            )
            actions = ["discuss"]
            if _text(getattr(entry, "discussion_conversation_id", "")):
                actions.insert(0, "open_discussion")
            items.append(_item(
                source_id,
                f"paused:{entry_id}",
                _text(getattr(entry, "name", "")) or "Paused item",
                detail,
                "paused",
                time=_text(getattr(entry, "queued_at", "")) or None,
                scope={"project_nexus": project} if project else None,
                actions=actions,
            ))
        paused_issue = _jsonl_reader_issue(
            oversight_queue._queue_path(), len(paused), "Paused queue",
        )
        if paused_issue:
            failures.append(paused_issue)
            if paused:
                usable_lanes += 1
        else:
            usable_lanes += 1
    except Exception as exc:
        failures.append(f"Paused queue: {exc}")

    try:
        operating = oversight_queue.list_operating()
        for entry in operating:
            entry_id = _required_id(getattr(entry, "id", None), "operating entry id")
            project = _text(getattr(entry, "project_nexus", ""))
            framework = _text(getattr(entry, "framework_id", ""))
            mode = _text(getattr(entry, "mode", ""))
            detail = " / ".join(part for part in (framework, mode) if part)
            if not detail:
                detail = _text((getattr(entry, "detail", None) or {}).get("display_name"))
            items.append(_item(
                source_id,
                f"operating:{entry_id}",
                _text(getattr(entry, "name", "")) or "Operating item",
                detail or "In progress",
                "operating",
                time=_text(getattr(entry, "started_at", "")) or None,
                scope={"project_nexus": project} if project else None,
                actions=(
                    ["open_conversation"]
                    if _text(getattr(entry, "conversation_id", "")) else []
                ),
            ))
        operating_issues, operating_usable = _operating_source_health(operating)
        failures.extend(operating_issues)
        if operating_usable:
            usable_lanes += 1
    except Exception as exc:
        failures.append(f"Operating queue: {exc}")

    if failures:
        state = "partial" if usable_lanes else "unavailable"
        return _source(
            source_id, "Oversight", items, stamp, state=state,
            error=_error("oversight_source_incomplete", "; ".join(failures)),
        )
    return _source(source_id, "Oversight", items, stamp)


def _jsonl_reader_issue(path_value: str, returned_count: int, label: str) -> str | None:
    """Detect a canonical JSONL reader silently dropping its source.

    The queue module remains the only record parser.  This check only compares
    its result with the number of non-blank physical records and verifies that
    the exact effective source path it used is readable.
    """
    path = Path(path_value)
    try:
        source_stat = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"{label} is unreadable: {exc}"
    if not stat.S_ISREG(source_stat.st_mode):
        return f"{label} is not a regular file: {path}"
    try:
        with path.open(encoding="utf-8") as stream:
            stored_count = sum(1 for line in stream if line.strip())
    except OSError as exc:
        return f"{label} is unreadable: {exc}"
    if stored_count != returned_count:
        return (
            f"{label} returned {returned_count} of {stored_count} stored records; "
            "the source is malformed or changed during the read"
        )
    return None


def _operating_source_health(entries: list[Any]) -> tuple[list[str], bool]:
    issues: list[str] = []
    usable_parts = 0

    reeval_count = sum(
        1 for entry in entries if getattr(entry, "kind", "") == "reeval"
    )
    reeval_issue = _jsonl_reader_issue(
        oversight_queue._reeval_path(), reeval_count, "Operating re-evaluation queue",
    )
    if reeval_issue:
        issues.append(reeval_issue)
        if reeval_count:
            usable_parts += 1
    else:
        usable_parts += 1

    session_issues, sessions_usable = _elicitation_source_health()
    issues.extend(session_issues)
    if sessions_usable:
        usable_parts += 1

    return issues, bool(usable_parts)


def _elicitation_source_health() -> tuple[list[str], bool]:
    """Report session envelopes that the canonical collector silently skips."""
    root = Path(oversight_queue.SESSIONS_ROOT)
    try:
        root_stat = root.stat()
    except FileNotFoundError:
        return [], True
    except OSError as exc:
        return [f"Operating sessions source is unreadable: {exc}"], False
    if not stat.S_ISDIR(root_stat.st_mode):
        return [f"Operating sessions source is not a directory: {root}"], False
    try:
        session_dirs = list(root.iterdir())
    except OSError as exc:
        return [f"Operating sessions source is unreadable: {exc}"], False

    issues: list[str] = []
    for session_dir in session_dirs:
        try:
            try:
                session_stat = session_dir.stat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(session_stat.st_mode):
                continue
            envelope = session_dir / "conversation.json"
            try:
                envelope_stat = envelope.stat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(envelope_stat.st_mode):
                issues.append(f"Operating session is not a regular file: {envelope}")
                continue
            try:
                json.loads(envelope.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(f"Operating session is unreadable or malformed: {envelope}: {exc}")
        except OSError as exc:
            issues.append(f"Operating session cannot be inspected: {session_dir}: {exc}")
    return issues, True


def _trigger_source(stamp: str) -> dict[str, Any]:
    source_id = "triggers"
    try:
        records = triggers.TriggerService().list_triggers()
        items = []
        for record in records:
            spec = record.get("spec") or {}
            trigger_id = _required_id(spec.get("trigger_id"), "trigger id")
            action = spec.get("action") or {}
            state = _text(record.get("status")) or "draft"
            cause = (_text(spec.get("cause")) or "unknown").replace("_", " ")
            action_kind = (_text(action.get("kind")) or "unknown").replace("_", " ")
            firings = record.get("firings") or []
            latest = firings[0] if firings else {}
            outcome = _text(latest.get("outcome"))
            display = f"{cause} · {action_kind}"
            if outcome:
                display += f" · last firing {outcome}"
            project = _text(action.get("project_nexus") or action.get("nexus"))
            items.append(_item(
                source_id,
                f"trigger:{trigger_id}",
                _text(spec.get("name")) or trigger_id,
                display,
                state,
                time=(
                    _text(record.get("next_due_at"))
                    or _text(latest.get("finished_at") or latest.get("claimed_at"))
                    or _text(record.get("activated_at") or record.get("created_at"))
                    or None
                ),
                scope={"project_nexus": project} if project else None,
                actions=_trigger_actions(state, action_kind),
            ))
    except Exception as exc:
        return _source(
            source_id, "Triggers", [], stamp,
            state="unavailable", error=_error("trigger_source_unavailable", exc),
        )
    return _source(source_id, "Triggers", items, stamp)


def _trigger_actions(state: str, action_kind: str) -> list[str]:
    actions = ["open_scheduled"]
    if action_kind == "email send":
        actions.append("inspect")
    if state == "draft":
        actions.extend(("review", "run", "retire"))
    elif state == "active":
        actions.extend(("run", "pause", "retire"))
    elif state == "paused":
        actions.extend(("run", "resume", "retire"))
    return actions


def _daily_note_source(stamp: str, completed_day: str) -> dict[str, Any]:
    source_id = "daily-note"
    try:
        target, exists = inspect_daily_note_path(completed_day)
        if not exists:
            placeholder = _item(
                source_id,
                f"daily-note:{completed_day}",
                completed_day,
                "No Daily Note is available for the completed day.",
                "missing",
                count=0,
                time=completed_day,
                scope={"date": completed_day, "path": str(target)},
            )
            return _source(
                source_id, "Daily Note", [placeholder], stamp,
                state="missing", count=0,
            )
        body = target.read_text(encoding="utf-8")
        item = _item(
            source_id,
            f"daily-note:{completed_day}",
            completed_day,
            _daily_note_preview(body),
            "available",
            time=completed_day,
            scope={"date": completed_day, "path": str(target)},
            actions=["read_note", "open_note"],
        )
    except Exception as exc:
        return _source(
            source_id, "Daily Note", [], stamp,
            state="unavailable", error=_error("daily_note_source_unavailable", exc),
        )
    return _source(source_id, "Daily Note", [item], stamp)


def _daily_note_preview(body: str, *, limit: int = 280) -> str:
    lines = body.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                lines = lines[index + 1:]
                break
    visible: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue
        if line.startswith("# ") or (line.startswith("[[") and "·" in line):
            continue
        visible.append(line.lstrip("#*- ").strip())
        if len(visible) == 3:
            break
    preview = " · ".join(part for part in visible if part)
    if not preview:
        preview = "No activity was recorded in this Daily Note."
    if len(preview) <= limit:
        return preview
    return preview[: limit - 1].rstrip() + "…"


__all__ = [
    "SOURCE_ORDER",
    "completed_daily_note_day",
    "inspect_daily_note_path",
    "read_daily_note",
    "load_overview_widget_sources",
]
