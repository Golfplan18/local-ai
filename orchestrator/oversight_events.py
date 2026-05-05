"""Oversight event emission and subscription.

A tiny event bus used by the meta-layer apparatus. Events are emitted by
hooks in milestone_executor (framework events), watchers (PED, corpus,
workflow spec), and the policy engine. Consumers (oversight_router) register
handlers; events are also durably appended to an event log for audit.

Per Reference — Meta-Layer Architecture §5 (event taxonomy).

Usage:
    from oversight_events import emit, register_handler

    register_handler(my_handler)  # called for every emitted event

    emit({
        "event_type": "FrameworkComplete",
        "framework_id": "...",
        ...
    })
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Callable


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
EVENT_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "events.jsonl")

_handlers: list[Callable[[dict], None]] = []
_log_lock = threading.Lock()


def register_handler(handler: Callable[[dict], None]):
    """Register an in-process event handler."""
    _handlers.append(handler)


def clear_handlers():
    """Clear all registered handlers. Used in tests."""
    _handlers.clear()


def emit(event) -> dict:
    """Emit an event. Accepts a dict or a dataclass; normalizes to dict.

    Writes the event to the durable log, then calls each registered handler.
    Handler exceptions are caught and logged but don't propagate.

    Returns the normalized event dict.
    """
    if is_dataclass(event):
        event = asdict(event)

    if not isinstance(event, dict):
        raise TypeError(f"emit() requires dict or dataclass, got {type(event)}")

    # Always include a wall-clock timestamp
    event.setdefault("timestamp", _now_iso())

    _append_to_log(event)

    for handler in list(_handlers):
        try:
            handler(event)
        except Exception as e:
            print(f"[oversight_events] handler failed: {e}")

    return event


def read_event_log(since_offset: int = 0, max_events: int = 1000) -> tuple[list[dict], int]:
    """Read events from the log starting at the given byte offset.

    Returns (events, new_offset). Used by polling consumers to track progress
    through the durable log.
    """
    if not os.path.isfile(EVENT_LOG_PATH):
        return ([], since_offset)

    events: list[dict] = []
    new_offset = since_offset
    try:
        with open(EVENT_LOG_PATH, "rb") as f:
            f.seek(since_offset)
            for _ in range(max_events):
                line = f.readline()
                if not line:
                    break
                try:
                    events.append(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError:
                    pass  # skip malformed line
                new_offset = f.tell()
    except OSError:
        return ([], since_offset)

    return (events, new_offset)


def _append_to_log(event: dict):
    """Append a JSONL line to the event log. Thread-safe."""
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    line = json.dumps(event, default=str) + "\n"
    with _log_lock:
        with open(EVENT_LOG_PATH, "a") as f:
            f.write(line)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
