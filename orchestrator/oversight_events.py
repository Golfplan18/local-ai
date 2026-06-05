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

    Stealth awareness: when the per-thread stealth-context flag is set
    (server's ``_pipeline_stream`` sets it for stealth-tagged conversation
    turns), the event is annotated with ``stealth: True`` and the durable
    log write is skipped. In-process handlers still receive the event so
    runtime behaviour (cross-project fan-out, downstream actions) is not
    altered — only the on-disk persistence surface is suppressed.
    """
    if is_dataclass(event):
        event = asdict(event)

    if not isinstance(event, dict):
        raise TypeError(f"emit() requires dict or dataclass, got {type(event)}")

    # Always include a wall-clock timestamp
    event.setdefault("timestamp", _now_iso())

    # Conversation-id context: thread-local set by the server's
    # _pipeline_stream so every event emitted during a turn carries the
    # conversation_id that triggered it. This is what makes
    # ``conversation_closeout._purge_stealth`` Layer 9's post-hoc scrub
    # over events.jsonl / actions.jsonl / human-queue.jsonl actually
    # findable — without this stamp the records have no key tying them
    # back to the stealth conversation that emitted them.
    cid = _get_conversation_id_context()
    if cid and "conversation_id" not in event:
        event["conversation_id"] = cid

    # Stealth context: thread-local flag set by the server's _pipeline_stream
    # for stealth-tagged conversation turns. When set, skip the durable log
    # write so events derived from stealth conversations leave no on-disk
    # residue in ~/ora/data/oversight/events.jsonl.
    if _is_stealth_context():
        event["stealth"] = True
    else:
        _append_to_log(event)

    for handler in list(_handlers):
        try:
            handler(event)
        except Exception as e:
            print(f"[oversight_events] handler failed: {e}")

    return event


# Per-thread stealth context — set by the server's _pipeline_stream at the
# top of each turn. Threading-local rather than contextvars: Flask's request
# handler runs each turn on its own thread, and the flag persists across every
# function call made on that same thread for the turn's duration.
#
# CAUTION: threading.local does NOT propagate to child threads. A
# ThreadPoolExecutor worker or a Thread() spawned mid-turn (e.g. the Gear-4
# parallel analysts) gets its own empty local and will NOT see the stealth
# flag. No code currently emits oversight events from a spawned worker, so the
# gap is latent — but if that changes, the worker must call
# set_stealth_context() itself, or the durable-log skip in emit() silently
# leaks stealth-derived content.
import threading as _threading
_stealth_ctx = _threading.local()


def set_stealth_context(stealth: bool) -> None:
    """Mark the current thread as serving a stealth-tagged conversation.

    Called by ``server.py::_pipeline_stream`` at the top of each turn when
    the conversation's tag is ``"stealth"``. Subsequent ``emit()`` calls on
    the same thread skip the durable event-log write. Clear by calling
    again with ``stealth=False`` at the end of the turn.
    """
    _stealth_ctx.stealth = bool(stealth)


def clear_stealth_context() -> None:
    """Convenience: explicitly clear the stealth flag for the current thread."""
    _stealth_ctx.stealth = False


def _is_stealth_context() -> bool:
    return bool(getattr(_stealth_ctx, "stealth", False))


def set_conversation_id_context(conversation_id: str | None) -> None:
    """Mark the current thread as serving the given conversation_id.

    Called by ``server.py::_pipeline_stream`` at the top of each turn
    alongside ``set_stealth_context``. Subsequent ``emit()`` calls (and
    on-disk writes in ``oversight_actions``) stamp the record with
    ``conversation_id`` if it isn't already present, so post-hoc purge
    layers (``conversation_closeout._purge_stealth`` Layer 9) can find
    records emitted on behalf of a stealth conversation if the primary
    skip-the-write defence is ever bypassed by a bug.

    Independent of ``set_stealth_context`` — the stamp is added for
    every turn, not just stealth turns — so audit data interpretation
    gains a stable join key without coupling to the stealth flag.
    """
    _stealth_ctx.conversation_id = (conversation_id or "") or None


def clear_conversation_id_context() -> None:
    """Convenience: explicitly clear the conversation_id stamp for the
    current thread.
    """
    _stealth_ctx.conversation_id = None


def _get_conversation_id_context() -> str | None:
    return getattr(_stealth_ctx, "conversation_id", None) or None


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
