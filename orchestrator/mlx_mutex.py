"""Per-machine MLX mutex layer.

The MLX runtime on Apple Silicon segfaults when two threads try to load
or invoke a model on the same machine simultaneously. The unit of
locking is the machine, not the endpoint and not the pipeline — any
local model call on machine M, regardless of which model, must hold M's
mutex during the call.

Replaces the prior single global lock in ``server.py`` (``_pipeline_lock``)
which guarded the entire chat handler including conversation save and
oversight health check. The mutex here is acquired around the model call
only; everything else runs outside it, so a second user submitting while
the first is mid-run no longer waits at the gate for the entire pipeline.

API endpoints don't go through this layer's blocking acquire — they go
through ``track_api_call`` for in-flight observability only. API
providers handle their own concurrency on their side.

See vault ``Working — Framework — Concurrency Architecture.md.archived-2026-05-18``
for the full design.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

_registry_lock = threading.Lock()

_machine_mutex: dict[str, threading.Lock] = {}
_machine_waiting: dict[str, int] = {}
_api_in_flight: dict[str, int] = {}


def _get_or_create_mutex(machine_id: str) -> threading.Lock:
    with _registry_lock:
        lock = _machine_mutex.get(machine_id)
        if lock is None:
            lock = threading.Lock()
            _machine_mutex[machine_id] = lock
            _machine_waiting[machine_id] = 0
        return lock


@contextmanager
def acquire(machine_id: str) -> Iterator[None]:
    """Blocking acquire of the per-machine MLX mutex.

    The waiting counter is incremented before the acquire so the chat
    UI can surface queue position ("Waiting for local model — N ahead
    of you"); decremented once the acquire succeeds.

    Usage::

        with acquire("studio-128"):
            response = run_mlx_inference(...)
    """
    lock = _get_or_create_mutex(machine_id)
    with _registry_lock:
        _machine_waiting[machine_id] += 1
    acquired = False
    try:
        lock.acquire()
        acquired = True
        with _registry_lock:
            _machine_waiting[machine_id] -= 1
        yield
    finally:
        if not acquired:
            with _registry_lock:
                _machine_waiting[machine_id] = max(
                    0, _machine_waiting[machine_id] - 1
                )
        else:
            lock.release()


@contextmanager
def try_acquire(machine_id: str) -> Iterator[bool]:
    """Non-blocking acquire of the per-machine MLX mutex.

    Yields ``True`` if the mutex was acquired (lock held for the
    duration of the ``with`` block), ``False`` if it was busy (no lock
    held). The waiting counter is not touched — try_acquire is for
    callers that want to advance to a fallback rather than wait.

    Usage by the router's failover chain walk::

        for endpoint in slot_chain:
            if endpoint["type"] != "local":
                return endpoint
            with try_acquire(endpoint["machine"]) as got_it:
                if got_it:
                    return endpoint
        return slot_chain[0]  # all busy — caller will block on acquire()
    """
    lock = _get_or_create_mutex(machine_id)
    acquired = lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


def is_machine_busy(machine_id: str) -> bool:
    """Non-blocking poll: is this machine's MLX mutex currently held?

    Used by the router's failover-chain walk to decide whether to
    advance to the next entry on local-endpoint contention. There is a
    short TOCTOU window between this poll and the eventual
    ``call_model`` blocking acquire — if the mutex becomes free in
    between, call_model proceeds immediately; if it becomes busy in
    between, call_model blocks for one model-call's duration. Either
    way the behaviour is sound and the worst case is bounded.
    """
    lock = _get_or_create_mutex(machine_id)
    if lock.acquire(blocking=False):
        lock.release()
        return False
    return True


def waiting_count(machine_id: str) -> int:
    """Number of pipelines waiting at this machine's MLX mutex.

    Only the blocking ``acquire`` path increments this counter;
    ``try_acquire`` is non-blocking and never waits.
    """
    with _registry_lock:
        return _machine_waiting.get(machine_id, 0)


@contextmanager
def track_api_call(endpoint_id: str) -> Iterator[None]:
    """Track an in-flight API call for observability.

    No locking, no blocking — pure counter. The router will eventually
    use this to display in-flight calls per endpoint in the UI.
    """
    with _registry_lock:
        _api_in_flight[endpoint_id] = _api_in_flight.get(endpoint_id, 0) + 1
    try:
        yield
    finally:
        with _registry_lock:
            _api_in_flight[endpoint_id] = max(
                0, _api_in_flight.get(endpoint_id, 0) - 1
            )


def in_flight_count(endpoint_id: str) -> int:
    """Current in-flight API calls on this endpoint."""
    with _registry_lock:
        return _api_in_flight.get(endpoint_id, 0)


def reset_for_tests() -> None:
    """Test-only: clear all module state."""
    with _registry_lock:
        _machine_mutex.clear()
        _machine_waiting.clear()
        _api_in_flight.clear()


__all__ = [
    "acquire",
    "try_acquire",
    "is_machine_busy",
    "waiting_count",
    "track_api_call",
    "in_flight_count",
    "reset_for_tests",
]
