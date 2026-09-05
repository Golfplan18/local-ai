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

import contextlib
import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Callable

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

# Roots flow from runtime_paths (ORA_HOME-relocatable): the execution gate's
# failure telemetry rides this bus, so its durable log must live under the
# same root as tool events and the gate queue.
WORKSPACE = _rp.WORKSPACE
OVERSIGHT_DATA_DIR = os.path.join(_rp.DATA_DIR_STR, "oversight")
EVENT_LOG_PATH = os.path.join(OVERSIGHT_DATA_DIR, "events.jsonl")
_EVENT_LOG_DEFAULT = EVENT_LOG_PATH  # import-time value; patch-detection anchor


def _log_path() -> str:
    """Effective event-log path: an explicit monkeypatch of EVENT_LOG_PATH
    wins; otherwise the ORA_OVERSIGHT_SANDBOX quarantine (test runs) applies;
    otherwise the live log."""
    if EVENT_LOG_PATH != _EVENT_LOG_DEFAULT:
        return EVENT_LOG_PATH
    return _rp.sandboxed_file(EVENT_LOG_PATH)


_handlers: list[Callable[[dict], None]] = []
_log_lock = threading.RLock()
_DELIVERY_MARKER = "_watcher_delivery"
_APPEND_DELIVER = "deliver"
_APPEND_ALREADY_DELIVERED = "already_delivered"


def register_handler(handler: Callable[[dict], None]):
    """Register an in-process event handler."""
    _handlers.append(handler)


def clear_handlers():
    """Clear all registered handlers. Used in tests."""
    _handlers.clear()


def emit(event) -> dict:
    """Emit an event. Accepts a dict or a dataclass; normalizes to dict.

    Writes the event to the durable log, then calls each registered handler.
    Ordinary-event handler exceptions retain the historical fail-open behavior.
    A watcher publication is acknowledged only after every handler succeeds;
    its handler failure propagates so the watcher cannot advance its snapshot.

    Returns the normalized event dict.

    Stealth awareness: when the per-thread stealth-context flag is set
    (server's ``_pipeline_stream`` sets it for stealth-tagged conversation
    turns), the event is annotated with ``stealth: True`` and the durable
    log write is skipped. In-process handlers still receive the annotated
    event, but durable handlers use the same lifecycle resolver to suppress
    PED mutations, counters, queue writes, and parent fan-out.
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
    stealth, cid = resolve_lifecycle_context(event)
    if cid and "conversation_id" not in event:
        event["conversation_id"] = cid

    # Stealth context: thread-local flag set by the server's _pipeline_stream
    # for stealth-tagged conversation turns. When set, skip the durable log
    # write so events derived from stealth conversations leave no on-disk
    # residue in ~/ora/data/oversight/events.jsonl.
    publication_id = event.get("publication_id")
    # A watcher publication's log-byte identity and downstream-delivery
    # identity are distinct. Keep their check/delivery/ack sequence atomic to
    # other emitter threads; the re-entrant lock lets a handler emit an
    # ordinary nested event without deadlocking.
    guard = _log_lock if publication_id and not stealth else contextlib.nullcontext()
    with guard:
        if stealth:
            if publication_id:
                raise RuntimeError(
                    "watcher publication cannot be durably recorded in stealth context"
                )
            event["stealth"] = True
        else:
            append_outcome = _append_to_log(event)
            if append_outcome == _APPEND_ALREADY_DELIVERED:
                _acknowledge_watcher_router(event)
                return event

        for handler in list(_handlers):
            try:
                handler(event)
            except Exception as e:
                print(f"[oversight_events] handler failed: {e}")
                if publication_id:
                    raise

        if publication_id and not stealth:
            _mark_publication_delivered(publication_id)
            _acknowledge_watcher_router(event)

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
import sys as _sys
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


@contextlib.contextmanager
def lifecycle_context_scope(
    *,
    stealth: bool,
    conversation_id: str | None,
    tool_context: dict | None = None,
):
    """Temporarily seed and then exactly restore lifecycle context.

    Both loaded ``oversight_events`` import identities are covered. When
    ``tool_context`` is supplied, both loaded ``tool_events`` identities are
    also set with the same authoritative conversation/Stealth values and
    restored through their native ContextVar tokens. This is the turn/direct-
    run API: callers wrap the full generator body in this scope so every early
    return and exception restores the prior worker-thread state.

    Example::

        with lifecycle_context_scope(
            stealth=tag == "stealth",
            conversation_id=conversation_id,
            tool_context={"trace_dir": trace_dir, "surface": "chat"},
        ):
            yield from run_turn()
    """
    missing = object()
    oversight_snapshots: list[tuple[object, object, object]] = []
    seen: set[int] = set()
    for module_name in (__name__, "oversight_events", "orchestrator.oversight_events"):
        module = _sys.modules.get(module_name)
        if module is None or id(module) in seen:
            continue
        seen.add(id(module))
        local = getattr(module, "_stealth_ctx", None)
        if local is None:
            continue
        prior_stealth = getattr(local, "stealth", missing)
        prior_conversation_id = getattr(local, "conversation_id", missing)
        oversight_snapshots.append((local, prior_stealth, prior_conversation_id))
        module.set_stealth_context(bool(stealth))
        module.set_conversation_id_context(conversation_id)

    tool_tokens: list[tuple[object, object]] = []
    if tool_context is not None:
        payload = dict(tool_context)
        payload["conversation_id"] = conversation_id
        payload["stealth"] = bool(stealth)
        seen.clear()
        for module_name in ("tool_events", "orchestrator.tool_events"):
            module = _sys.modules.get(module_name)
            if module is None or id(module) in seen:
                continue
            seen.add(id(module))
            try:
                token = module.set_turn_context(**payload)
                tool_tokens.append((module, token))
            except Exception as exc:
                print(
                    f"[oversight_events] tool lifecycle context seed failed: {exc}",
                    flush=True,
                )
    try:
        yield
    finally:
        for module, token in reversed(tool_tokens):
            try:
                module.reset_turn_context(token)
            except Exception as exc:
                print(
                    f"[oversight_events] tool lifecycle context restore failed: {exc}",
                    flush=True,
                )
        for local, prior_stealth, prior_conversation_id in reversed(
            oversight_snapshots
        ):
            if prior_stealth is missing:
                try:
                    delattr(local, "stealth")
                except AttributeError:
                    pass
            else:
                local.stealth = prior_stealth
            if prior_conversation_id is missing:
                try:
                    delattr(local, "conversation_id")
                except AttributeError:
                    pass
            else:
                local.conversation_id = prior_conversation_id


def _get_conversation_id_context() -> str | None:
    return getattr(_stealth_ctx, "conversation_id", None) or None


def _combined_lifecycle_context() -> tuple[bool, str | None]:
    """Read both supported import identities' thread-local lifecycle state.

    Ora still has legacy top-level imports alongside package-qualified imports.
    A long-running process can therefore contain two ``oversight_events``
    module objects. Durable writers must treat Stealth in either copy as
    authoritative and use the first available conversation identity.
    """
    stealth = _is_stealth_context()
    conversation_id = _get_conversation_id_context()
    seen = {id(_sys.modules.get(__name__))}
    for module_name in ("oversight_events", "orchestrator.oversight_events"):
        module = _sys.modules.get(module_name)
        if module is None or id(module) in seen:
            continue
        seen.add(id(module))
        try:
            stealth = bool(stealth or module._is_stealth_context())
            conversation_id = (
                conversation_id or module._get_conversation_id_context()
            )
        except Exception:
            continue
    return stealth, conversation_id


def resolve_lifecycle_context(event: dict | None = None) -> tuple[bool, str | None]:
    """Return authoritative ``(stealth, conversation_id)`` for an event.

    Oversight still runs through both top-level and package-qualified import
    identities, and some direct execution paths seed only the tool-event turn
    context.  Every durable oversight handler uses this resolver so an
    explicitly Stealth event, either thread-local copy, or either tool-event
    context is sufficient to suppress persistence.  The explicit event
    identity wins when choosing the owner stamped on derived records.
    """
    candidate = event if isinstance(event, dict) else {}
    nested = candidate.get("event")
    nested = nested if isinstance(nested, dict) else {}

    conversation_id = (
        candidate.get("conversation_id")
        or nested.get("conversation_id")
        or None
    )
    if conversation_id is not None:
        conversation_id = str(conversation_id).strip() or None
    stealth = bool(
        candidate.get("stealth")
        or nested.get("stealth")
        or candidate.get("conversation_tag") == "stealth"
        or nested.get("conversation_tag") == "stealth"
        or candidate.get("tag") == "stealth"
        or nested.get("tag") == "stealth"
    )

    context_stealth, context_conversation_id = _combined_lifecycle_context()
    stealth = bool(stealth or context_stealth)
    conversation_id = conversation_id or context_conversation_id

    seen: set[int] = set()
    for module_name in ("tool_events", "orchestrator.tool_events"):
        module = _sys.modules.get(module_name)
        if module is None or id(module) in seen:
            continue
        seen.add(id(module))
        try:
            tool_context = module.get_turn_context() or {}
            stealth = bool(stealth or tool_context.get("stealth"))
            conversation_id = (
                conversation_id or tool_context.get("conversation_id") or None
            )
        except Exception:
            continue
    if conversation_id is not None:
        conversation_id = str(conversation_id).strip() or None
    return stealth, conversation_id


def read_event_log(since_offset: int = 0, max_events: int = 1000) -> tuple[list[dict], int]:
    """Read events from the log starting at the given byte offset.

    Returns (events, new_offset). Used by polling consumers to track progress
    through the durable log.
    """
    log_path = _log_path()
    if not os.path.isfile(log_path):
        return ([], since_offset)

    events: list[dict] = []
    new_offset = since_offset
    try:
        with open(log_path, "rb") as f:
            f.seek(since_offset)
            while len(events) < max_events:
                line = f.readline()
                if not line:
                    break
                try:
                    event = json.loads(line.decode("utf-8"))
                    if not isinstance(event, dict) or _DELIVERY_MARKER not in event:
                        events.append(event)
                except (UnicodeError, json.JSONDecodeError):
                    pass  # skip malformed line
                new_offset = f.tell()
    except OSError:
        return ([], since_offset)

    return (events, new_offset)


def _append_to_log(event: dict) -> str:
    """Durably append one event and return its explicit delivery outcome.

    ``publication_id`` is intentionally a watcher-only contract. Ordinary
    callers retain the existing append-every-emission behavior. A complete
    event line without a separate delivery marker is retried downstream.
    """
    log_path = _log_path()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    publication_id = event.get("publication_id")
    with _log_lock:
        with _rp.locked_file(log_path):
            flags = os.O_APPEND | os.O_CREAT
            flags |= os.O_RDWR if publication_id else os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(log_path, flags, 0o600)
            try:
                if publication_id:
                    # A failed append may have left either a complete but
                    # un-fsynced event or an unterminated JSON fragment.  Work
                    # from the locked descriptor so the retry can prove the
                    # former durable and remove the latter before appending.
                    os.lseek(fd, 0, os.SEEK_SET)
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(fd, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    existing = b"".join(chunks)
                    complete_end = existing.rfind(b"\n") + 1
                    if complete_end != len(existing):
                        os.ftruncate(fd, complete_end)
                        os.fsync(fd)
                        existing = existing[:complete_end]
                    event_recorded = None
                    delivery_recorded = False
                    for raw in existing.splitlines():
                        try:
                            recorded = json.loads(raw.decode("utf-8"))
                        except (UnicodeError, json.JSONDecodeError):
                            continue
                        if (
                            event_recorded is None
                            and recorded.get("publication_id") == publication_id
                        ):
                            event_recorded = recorded
                        if recorded.get(_DELIVERY_MARKER) == publication_id:
                            delivery_recorded = True

                    # The first durable event row is the publication payload.
                    # Reuse it on every retry so changed watcher metadata can
                    # neither alter the router identity nor retarget effects.
                    if isinstance(event_recorded, dict):
                        event.clear()
                        event.update(event_recorded)
                    if delivery_recorded:
                        os.fsync(fd)
                        return _APPEND_ALREADY_DELIVERED

                    # Preparation sits under this same cross-process event-log
                    # lock, after marker inspection and before a new row.  The
                    # installed router freezes the complete original payload
                    # and performs no sink effect here.
                    _prepare_watcher_router(event)
                    if event_recorded is not None:
                        # A prior fsync may have reported failure even though
                        # the complete line is visible. Prove it durable before
                        # any handler is allowed to run.
                        os.fsync(fd)
                        return _APPEND_DELIVER

                    line = (json.dumps(event, default=str) + "\n").encode("utf-8")
                    written = 0
                    while written < len(line):
                        count = os.write(fd, line[written:])
                        if count <= 0:
                            raise OSError("watcher event log write made no progress")
                        written += count
                    os.fsync(fd)
                else:
                    line = (json.dumps(event, default=str) + "\n").encode("utf-8")
                    os.write(fd, line)
            finally:
                os.close(fd)
    return _APPEND_DELIVER


def _mark_publication_delivered(publication_id) -> None:
    """Durably acknowledge downstream delivery in the existing event log."""
    log_path = _log_path()
    marker = (json.dumps({
        _DELIVERY_MARKER: publication_id,
        "recorded_at": _now_iso(),
    }, default=str) + "\n").encode("utf-8")
    with _log_lock:
        with _rp.locked_file(log_path):
            flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(log_path, flags, 0o600)
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                existing = b""
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    existing += chunk
                for raw in existing.splitlines():
                    try:
                        recorded = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        continue
                    if recorded.get(_DELIVERY_MARKER) == publication_id:
                        os.fsync(fd)
                        return
                written = 0
                while written < len(marker):
                    count = os.write(fd, marker[written:])
                    if count <= 0:
                        raise OSError(
                            "watcher delivery acknowledgment made no progress"
                        )
                    written += count
                os.fsync(fd)
            finally:
                os.close(fd)


def _acknowledge_watcher_router(event: dict) -> None:
    """Close the matching router claim after its log marker is durable."""
    try:
        from oversight_router import acknowledge_watcher_publication
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_router import acknowledge_watcher_publication
    acknowledge_watcher_publication(event)


def _prepare_watcher_router(event: dict) -> bool:
    """Freeze and reuse the installed router's full watcher plan.

    This is deliberately router-specific.  Other in-process handlers retain
    the historical post-publication call contract and gain no preparation
    callback or persistence mechanism.
    """
    try:
        import oversight_router
    except ImportError:  # pragma: no cover
        from orchestrator import oversight_router
    expected_identity = (
        oversight_router.process_event.__module__.removeprefix("orchestrator."),
        oversight_router.process_event.__qualname__,
    )
    installed = any(
        (
            getattr(handler, "__module__", "").removeprefix("orchestrator."),
            getattr(handler, "__qualname__", ""),
        ) == expected_identity
        for handler in _handlers
    )
    if not installed:
        return False
    record = oversight_router.prepare_watcher_publication(event)
    subject = record.get("subject") if isinstance(record, dict) else None
    planned_event = (
        subject.get("publication_event") if isinstance(subject, dict) else None
    )
    if not isinstance(planned_event, dict):
        raise RuntimeError("watcher router plan has no frozen publication event")
    event.clear()
    event.update(planned_event)
    return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
