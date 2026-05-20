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

import datetime
import json
import os
import threading
from contextlib import contextmanager
from typing import Iterator

_registry_lock = threading.Lock()

_machine_mutex: dict[str, threading.Lock] = {}
_machine_waiting: dict[str, int] = {}
_api_in_flight: dict[str, int] = {}

# Sized API concurrency cap (Phase 2a). When configured to a positive
# integer, ``track_api_call`` acquires from this semaphore before the
# call and releases after — capping the number of concurrent outbound
# API calls per Ora process. Defaults to None (unbounded) so single-user
# installs see no behaviour change.
#
# Configured via ``configure_api_pool(size)``, typically from
# install-state.json::profile at server startup. Per the concurrency
# spec section 6: Solo 0 (interpreted here as unbounded — Solo has no
# API endpoints, but if a user adds one we shouldn't deadlock), Hybrid
# 8, Organization 32. Bounded so over-release surfaces as ValueError
# rather than silently corrupting the count.
_api_pool_semaphore: threading.BoundedSemaphore | None = None
_api_pool_size: int | None = None

# Per-profile API pool cap. Mirrors scripts/install.py::DEPLOYMENT_PROFILES
# — duplicated here so server.py can read the size without importing from
# scripts/ (which isn't on the Python path in production runs). Keep these
# two in sync; the test suite checks parity.
PROFILE_API_POOL_SIZES = {
    "solo": 0,
    "hybrid": 8,
    "organization": 32,
}


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


def configure_api_pool(size: int | None) -> None:
    """Configure the maximum number of concurrent outbound API calls.

    Pass an integer ``> 0`` to cap concurrency at that many in-flight
    calls — additional callers will block at ``track_api_call`` until
    a slot frees. Pass ``None`` or ``0`` to remove the cap entirely
    (the default; suitable for single-user installs).

    Typically called once at Ora startup from server.py based on the
    install profile (Hybrid: 8, Organization: 32, Solo: unbounded).
    Reconfiguring at runtime is allowed — the new semaphore takes
    effect for subsequent calls; in-flight callers under the old
    semaphore complete normally.
    """
    global _api_pool_semaphore, _api_pool_size
    with _registry_lock:
        if size is None or size <= 0:
            _api_pool_semaphore = None
            _api_pool_size = None
        else:
            _api_pool_semaphore = threading.BoundedSemaphore(size)
            _api_pool_size = size


def api_pool_size() -> int | None:
    """Return the current API pool cap, or None when unbounded."""
    with _registry_lock:
        return _api_pool_size


def configure_api_pool_from_install_state(
    state_path: str | None = None,
    env: dict[str, str] | None = None,
) -> int | None:
    """Configure the API pool from install-state.json + env override.

    Precedence:
      1. ``ORA_API_POOL_SIZE`` env var (positive integer) — overrides
         everything. Useful for testing or one-off tuning.
      2. ``install-state.json::profile`` mapped through
         ``PROFILE_API_POOL_SIZES``.
      3. Unbounded (no cap) if neither source is usable.

    Safe to call when install-state.json is missing or malformed —
    falls back to unbounded silently. Returns the configured size
    (or None for unbounded).
    """
    import json
    import os

    env = env if env is not None else dict(os.environ)
    state_path = state_path or os.path.expanduser("~/ora/install-state.json")

    env_cap = env.get("ORA_API_POOL_SIZE", "").strip()
    if env_cap.isdigit() and int(env_cap) > 0:
        size = int(env_cap)
        configure_api_pool(size)
        return size

    try:
        with open(state_path) as f:
            state = json.load(f)
        profile = state.get("profile")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        configure_api_pool(None)
        return None

    size = PROFILE_API_POOL_SIZES.get(profile, 0)
    if size > 0:
        configure_api_pool(size)
        return size
    configure_api_pool(None)
    return None


@contextmanager
def track_api_call(endpoint_id: str) -> Iterator[None]:
    """Track an in-flight API call, with optional sized cap.

    When ``configure_api_pool`` has set a positive cap, this acquires
    a slot from the semaphore (blocking until one frees) before the
    call and releases on exit. The per-endpoint in-flight counter is
    always maintained for observability — the cap is a separate
    global concern.
    """
    sem = _api_pool_semaphore
    if sem is not None:
        sem.acquire()
    try:
        with _registry_lock:
            _api_in_flight[endpoint_id] = _api_in_flight.get(endpoint_id, 0) + 1
        try:
            yield
        finally:
            with _registry_lock:
                _api_in_flight[endpoint_id] = max(
                    0, _api_in_flight.get(endpoint_id, 0) - 1
                )
    finally:
        if sem is not None:
            sem.release()


def in_flight_count(endpoint_id: str) -> int:
    """Current in-flight API calls on this endpoint."""
    with _registry_lock:
        return _api_in_flight.get(endpoint_id, 0)


_DEFAULT_HEARTBEAT_PATH = os.path.expanduser(
    "~/ora/data/oversight/mlx-worker-heartbeat.json"
)


def write_heartbeat(
    machine_id: str = "studio-128",
    path: str | None = None,
) -> str:
    """Write a single heartbeat record. Returns the path written.

    Records ``beat_at`` (UTC ISO timestamp), the machine id, and the
    current per-machine waiting count — the same fields oversight_health
    reads to flag staleness. Creates the parent directory on first call.
    Safe to call from any thread.
    """
    target = path or _DEFAULT_HEARTBEAT_PATH
    os.makedirs(os.path.dirname(target), exist_ok=True)
    payload = {
        "beat_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "machine_id": machine_id,
        "queue_depth": waiting_count(machine_id),
    }
    tmp = f"{target}.tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, target)
    return target


_heartbeat_thread: threading.Thread | None = None
_heartbeat_stop: threading.Event | None = None


def start_heartbeat(
    interval_seconds: float = 30.0,
    machine_id: str = "studio-128",
    path: str | None = None,
) -> threading.Thread:
    """Spawn a daemon thread that writes mlx-worker heartbeats periodically.

    Surfaces "this Ora process's MLX-aware code path is responsive" to
    oversight_health (which reads the heartbeat file every check). The
    thread is a daemon — exits when the process exits. Idempotent: a
    second call replaces the running thread without leaking.

    Returns the spawned thread (you generally don't need to hold a
    reference; the module tracks it internally so ``stop_heartbeat``
    can find it).
    """
    global _heartbeat_thread, _heartbeat_stop

    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        stop_heartbeat()

    stop = threading.Event()

    def _loop():
        while not stop.is_set():
            try:
                write_heartbeat(machine_id=machine_id, path=path)
            except OSError:
                pass
            stop.wait(interval_seconds)

    t = threading.Thread(target=_loop, name="mlx-heartbeat", daemon=True)
    _heartbeat_stop = stop
    _heartbeat_thread = t
    t.start()
    return t


def stop_heartbeat() -> None:
    """Signal the heartbeat thread to exit. Used in tests + shutdown."""
    global _heartbeat_thread, _heartbeat_stop
    if _heartbeat_stop is not None:
        _heartbeat_stop.set()
    if _heartbeat_thread is not None:
        _heartbeat_thread.join(timeout=2)
    _heartbeat_thread = None
    _heartbeat_stop = None


def reset_for_tests() -> None:
    """Test-only: clear all module state."""
    global _api_pool_semaphore, _api_pool_size
    stop_heartbeat()
    with _registry_lock:
        _machine_mutex.clear()
        _machine_waiting.clear()
        _api_in_flight.clear()
        _api_pool_semaphore = None
        _api_pool_size = None


__all__ = [
    "acquire",
    "try_acquire",
    "is_machine_busy",
    "waiting_count",
    "track_api_call",
    "in_flight_count",
    "configure_api_pool",
    "configure_api_pool_from_install_state",
    "api_pool_size",
    "PROFILE_API_POOL_SIZES",
    "write_heartbeat",
    "start_heartbeat",
    "stop_heartbeat",
    "reset_for_tests",
]
