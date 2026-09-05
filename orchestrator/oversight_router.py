"""Observational project-event logging and parent-project fan-out.

Process Coherence is an explicitly invoked judgment framework. This module
does not invoke it, parse verdicts, or dispatch project or Programming
transitions. The event handler retains stealth suppression, a local event
audit, and asymmetric child-to-parent visibility.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


WORKSPACE = _rp.WORKSPACE
VAULT = _rp.VAULT_STR
ROUTER_LOG_PATH = os.path.join(_rp.DATA_DIR_STR, "oversight", "router.jsonl")
_ROUTER_LOG_DEFAULT = ROUTER_LOG_PATH
_DYNAMIC_PARENT_NOTIFICATION = object()


def _router_log_path() -> str:
    if ROUTER_LOG_PATH != _ROUTER_LOG_DEFAULT:
        return ROUTER_LOG_PATH
    return _rp.sandboxed_file(ROUTER_LOG_PATH)


def process_event(event: dict) -> dict:
    """Log one oversight event and surface eligible child events to a parent."""
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context

    event = dict(event)
    stealth, conversation_id = resolve_lifecycle_context(event)
    if conversation_id and not event.get("conversation_id"):
        event["conversation_id"] = conversation_id
    if stealth:
        return {
            "event_type": event.get("event_type", ""),
            "timestamp": _now_iso(),
            "project_nexus": event.get("project_nexus", ""),
            "conversation_id": event.get("conversation_id", ""),
            "action": "stealth_suppressed",
        }

    if event.get("publication_id"):
        return _process_watcher_publication(event)
    return _process_event_once(event)


def _process_watcher_publication(event: dict) -> dict:
    """Resume one stable watcher delivery through its first claimed plan."""
    try:
        from runtime_hygiene import EventLedger
    except ImportError:  # pragma: no cover
        from orchestrator.runtime_hygiene import EventLedger

    delivery_id, identity_subject = _watcher_delivery_identity(event)
    publication_id = identity_subject["publication_id"]
    ledger = EventLedger()
    record = prepare_watcher_publication(event)

    claimed_subject = _require_watcher_delivery_subject(record, identity_subject)
    publication_event = claimed_subject["publication_event"]
    parent_notification = claimed_subject["parent_notification"]

    if record.get("status") == "completed":
        receipt = record.get("receipt")
        return dict(receipt) if isinstance(receipt, dict) else {
            "event_type": event.get("event_type", ""),
            "publication_id": publication_id,
            "action": "already_delivered",
        }
    if record.get("status") != "claimed":
        raise RuntimeError(
            f"watcher router delivery is not resumable: {record.get('status')}"
        )

    receipt = record.get("receipt")
    if receipt is not None:
        if not isinstance(receipt, dict) or not record.get("effects_completed_at"):
            raise RuntimeError("watcher router delivery has invalid effects receipt")
        return dict(receipt)

    action = _process_event_once(
        publication_event,
        parent_notification=parent_notification,
    )
    current = ledger.get(delivery_id)
    if current and current.get("status") == "completed":
        receipt = current.get("receipt")
        return dict(receipt) if isinstance(receipt, dict) else action
    if (
        current
        and current.get("status") == "claimed"
        and current.get("receipt") is not None
    ):
        receipt = current.get("receipt")
        if not isinstance(receipt, dict) or not current.get("effects_completed_at"):
            raise RuntimeError("watcher router delivery has invalid effects receipt")
        return dict(receipt)
    if not current or current.get("status") != "claimed":
        raise RuntimeError("watcher router delivery changed while effects completed")
    try:
        # The effects receipt is durable while the delivery remains claimed.
        # Only oversight_events may complete it, after its delivery marker is
        # fsynced. A retry that sees this receipt must not replay the sinks.
        ledger.transition(
            delivery_id,
            {"claimed"},
            "claimed",
            receipt=action,
            effects_completed_at=_now_iso(),
        )
    except ValueError:
        # Another process may have recorded the same idempotent effects or
        # acknowledged them after our last read.
        current = ledger.get(delivery_id)
        receipt = (current or {}).get("receipt")
        if (
            not current
            or current.get("status") not in {"claimed", "completed"}
            or not isinstance(receipt, dict)
            or not current.get("effects_completed_at")
        ):
            raise
        return dict(receipt)
    return action


def prepare_watcher_publication(event: dict) -> dict:
    """Durably freeze one router plan without performing any router effect.

    ``oversight_events`` calls this under its cross-process event-log lock,
    after marker inspection and before it writes the watcher event row.
    ``process_event`` also calls it so a direct publication invocation retains
    the same first-plan-wins behavior.
    """
    try:
        from runtime_hygiene import EventLedger
    except ImportError:  # pragma: no cover
        from orchestrator.runtime_hygiene import EventLedger

    delivery_id, identity_subject = _watcher_delivery_identity(event)
    ledger = EventLedger()
    record = ledger.get(delivery_id)
    if record is None:
        try:
            from oversight_relationships import prepare_parent_notification
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_relationships import (
                prepare_parent_notification,
            )
        publication_event = json.loads(json.dumps(event, default=str))
        subject = {
            **identity_subject,
            "publication_event": publication_event,
            "parent_notification": prepare_parent_notification(
                publication_event,
            ),
        }
        try:
            record, _created = ledger.claim(
                event_id=delivery_id,
                event_type="watcher_router_delivery",
                subject=subject,
            )
        except ValueError:
            # Two processes may resolve the first attempt concurrently. The
            # winning claim owns the delivery plan; the loser must reuse it,
            # never replace it with the plan it happened to observe.
            record = ledger.get(delivery_id)
            if record is None:
                raise
    _require_watcher_delivery_subject(record, identity_subject)
    return record


def acknowledge_watcher_publication(event: dict) -> bool:
    """Complete this router claim only after the event marker is durable.

    The caller reaches this seam only after the authoritative event-log marker
    is durable. A missing/pruned claim and an already-completed claim are both
    idempotent success; any malformed surviving claim still fails.
    """
    try:
        from runtime_hygiene import EventLedger
    except ImportError:  # pragma: no cover
        from orchestrator.runtime_hygiene import EventLedger

    delivery_id, identity_subject = _watcher_delivery_identity(event)
    ledger = EventLedger()
    record = ledger.get(delivery_id)
    if record is None:
        return True
    _require_watcher_delivery_subject(record, identity_subject)
    if record.get("status") == "completed":
        return True
    receipt = record.get("receipt")
    if (
        record.get("status") != "claimed"
        or not isinstance(receipt, dict)
        or not record.get("effects_completed_at")
    ):
        raise RuntimeError("watcher router delivery effects are not complete")
    try:
        ledger.transition(
            delivery_id,
            {"claimed"},
            "completed",
            completed_at=_now_iso(),
        )
    except ValueError:
        current = ledger.get(delivery_id)
        if not current:
            raise
        _require_watcher_delivery_subject(current, identity_subject)
        if current.get("status") != "completed":
            raise
    return True


def _watcher_delivery_identity(event: dict) -> tuple[str, dict]:
    """Return the one delivery id and identity subject used by route and ack."""
    try:
        from runtime_hygiene import event_identity
    except ImportError:  # pragma: no cover
        from orchestrator.runtime_hygiene import event_identity

    publication_id = str(event.get("publication_id") or "")
    if not publication_id:
        raise ValueError("watcher publication has no stable identity")
    identity_subject = {
        "publication_id": publication_id,
        "handler": "oversight_router.process_event",
        "event_type": str(event.get("event_type") or ""),
    }
    return (
        event_identity("watcher_router_delivery", identity_subject),
        identity_subject,
    )


def _require_watcher_delivery_subject(
    record: dict,
    identity_subject: dict,
) -> dict:
    """Authenticate the frozen plan held by one watcher delivery claim."""
    claimed_subject = record.get("subject")
    if not isinstance(claimed_subject, dict) or any(
        claimed_subject.get(key) != value
        for key, value in identity_subject.items()
    ):
        raise RuntimeError("watcher router delivery identity does not match its claim")
    if "parent_notification" not in claimed_subject:
        raise RuntimeError("watcher router delivery has no claimed parent plan")
    publication_event = claimed_subject.get("publication_event")
    if (
        not isinstance(publication_event, dict)
        or publication_event.get("publication_id")
        != identity_subject["publication_id"]
        or publication_event.get("event_type") != identity_subject["event_type"]
    ):
        raise RuntimeError("watcher router delivery has no frozen publication event")
    return claimed_subject


def _process_event_once(
    event: dict,
    *,
    parent_notification=_DYNAMIC_PARENT_NOTIFICATION,
) -> dict:
    """Perform the router's effects once per stable publication identity."""

    from oversight_relationships import is_fan_out_event

    fan_out_audit = is_fan_out_event(event)
    action = {
        "event_type": event.get("event_type", ""),
        "timestamp": _now_iso(),
        "project_nexus": event.get("project_nexus", ""),
        "workflow_id": event.get("workflow_id", ""),
        "section_id": event.get("section_id", ""),
        "conversation_id": event.get("conversation_id", ""),
        "action": "fan_out_audit_only" if fan_out_audit else "logged_only",
    }
    if fan_out_audit:
        action["child_nexus"] = event.get("child_nexus", "")
    if event.get("publication_id"):
        action["publication_id"] = event["publication_id"]
    _append_router_log(action)
    if not fan_out_audit:
        _maybe_fan_out_to_parent(
            event,
            parent_notification=parent_notification,
        )
    return action


def _maybe_fan_out_to_parent(
    event: dict,
    *,
    parent_notification=_DYNAMIC_PARENT_NOTIFICATION,
) -> None:
    """Surface eligible child events; watcher delivery failures propagate."""
    try:
        try:
            from oversight_events import resolve_lifecycle_context
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_events import resolve_lifecycle_context
        stealth, conversation_id = resolve_lifecycle_context(event)
        if stealth:
            return
        if conversation_id and not event.get("conversation_id"):
            event = {**event, "conversation_id": conversation_id}
        from oversight_relationships import (
            deliver_parent_notification,
            get_parent_nexus,
            notify_parent,
            should_fan_out,
        )
        if parent_notification is not _DYNAMIC_PARENT_NOTIFICATION:
            if parent_notification is not None:
                deliver_parent_notification(parent_notification)
            return
        if not should_fan_out(event):
            return
        child_nexus = event.get("project_nexus", "")
        if not child_nexus:
            return
        parent_nexus = get_parent_nexus(child_nexus)
        if parent_nexus:
            notify_parent(event, parent_nexus)
    except Exception as exc:
        print(f"[oversight_router] fan-out to parent failed: {exc}")
        if event.get("publication_id"):
            raise


def _append_router_log(entry: dict) -> None:
    entry = dict(entry)
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(entry)
    if stealth:
        return
    if conversation_id and not entry.get("conversation_id"):
        entry["conversation_id"] = conversation_id
    log_path = _router_log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    encoded = (json.dumps(entry, default=str) + "\n").encode("utf-8")
    with _rp.locked_file(log_path):
        publication_id = entry.get("publication_id")
        flags = os.O_APPEND | os.O_CREAT
        flags |= os.O_RDWR if publication_id else os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(log_path, flags, 0o600)
        try:
            if publication_id:
                os.lseek(descriptor, 0, os.SEEK_SET)
                existing = b""
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    existing += chunk
                complete_end = existing.rfind(b"\n") + 1
                if complete_end != len(existing):
                    os.ftruncate(descriptor, complete_end)
                    os.fsync(descriptor)
                    existing = existing[:complete_end]
                for raw in existing.splitlines():
                    try:
                        recorded = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        continue
                    if recorded.get("publication_id") == publication_id:
                        os.fsync(descriptor)
                        return
                written = 0
                while written < len(encoded):
                    count = os.write(descriptor, encoded[written:])
                    if count <= 0:
                        raise OSError("oversight router audit write made no progress")
                    written += count
                os.fsync(descriptor)
            else:
                os.write(descriptor, encoded)
        finally:
            os.close(descriptor)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def install() -> None:
    """Register the observational handler once during daemon boot."""
    from oversight_events import register_handler

    register_handler(process_event)


if __name__ == "__main__":
    import sys

    sample = {
        "event_type": "MilestoneClaimed",
        "project_nexus": sys.argv[1] if len(sys.argv) > 1 else "test_project",
        "milestone_text": "First draft is complete",
        "claimer": "user",
    }
    print(json.dumps(process_event(sample), indent=2, default=str))
