"""Read-only widget projections for the Overview Desktop.

This module is intentionally only an adapter.  The Project, Oversight,
Trigger, and Daily Note modules remain authoritative for their own records;
this code gives a renderer one small, stable shape without adding a cache,
store, scheduler, or mutation path.
"""
from __future__ import annotations

import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import oversight_queue
    import project_meta
    import triggers
    from tools import daily_note
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import oversight_queue, project_meta, triggers
    from orchestrator.tools import daily_note


SOURCE_ORDER = ("project-priority", "oversight", "triggers", "daily-note")


def load_overview_widget_sources(
    *, observed_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return the four core Overview sources in a stable order.

    Every source is read independently.  A failed source therefore reports an
    unavailable record while the other sources remain usable.  ``observed_at``
    exists for deterministic callers and tests; production uses local time for
    the completed-day Daily Note and records the observation in UTC.
    """
    local_now = observed_at or datetime.now().astimezone()
    if local_now.tzinfo is None:
        local_now = local_now.astimezone()
    stamp = local_now.astimezone(timezone.utc).isoformat()
    completed_day = (local_now.date() - timedelta(days=1)).isoformat()
    return [
        _project_priority_source(stamp),
        _oversight_source(stamp),
        _trigger_source(stamp),
        _daily_note_source(stamp, completed_day),
    ]


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


def _project_priority_source(stamp: str) -> dict[str, Any]:
    source_id = "project-priority"
    skipped: list[str] = []
    try:
        records = project_meta.list_project_meta(skipped_authority=skipped)
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
            if record.get("is_default"):
                position = "All projects"
            state = _text(record.get("status")) or "active"
            items.append(_item(
                source_id,
                f"project:{nexus}",
                title,
                f"{position} · {state}",
                state,
                time=_text(record.get("last_accessed_at") or record.get("created")) or None,
                scope={"project_nexus": nexus},
                actions=["open_project"],
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
    actions: list[str] = []
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
        root = Path(daily_note.daily_dir())
        try:
            root_stat = root.lstat()
        except FileNotFoundError:
            root_stat = None
        if root_stat is not None and (
            stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode)
        ):
            raise OSError(f"Daily Notes root is not a regular directory: {root}")
        target = root / f"{completed_day}.md"
        try:
            target_stat = target.lstat()
        except FileNotFoundError:
            target_stat = None
        if target_stat is not None and (
            stat.S_ISLNK(target_stat.st_mode) or not stat.S_ISREG(target_stat.st_mode)
        ):
            raise OSError(f"Daily Note is not a regular file: {target}")
        if target_stat is None:
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
            actions=["open_note"],
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


__all__ = ["SOURCE_ORDER", "load_overview_widget_sources"]
