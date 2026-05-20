"""Per-endpoint circuit breaker for graceful degradation.

When an endpoint repeatedly fails (transport errors, 5xx responses,
model-load failures), the routing layer should stop trying it for a
while — repeatedly hitting a broken endpoint just produces more
errors and burns retry budget. After a cooldown period, one "probe"
call is allowed through: success returns it to the healthy pool;
failure extends the cooldown.

Same mechanism for both API endpoints (HTTP-level failures) and local
endpoints (model-load failures). The router's chain walk consults
``is_in_cooldown(endpoint_id)`` alongside its existing same-machine
and per-machine-mutex checks.

Configuration defaults match the concurrency spec section 5:
- 3 failures within a 60-second rolling window triggers cooldown.
- Cooldown lasts 5 minutes (300 seconds).
- After cooldown, the next call is a "probe": success → fully
  healthy, failure → extend cooldown.

See vault Working — Framework — Concurrency Architecture.md.archived-2026-05-18
section 5 ("Worker health monitoring").
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque

_registry_lock = threading.Lock()


@dataclass
class _EndpointState:
    failures: Deque[float]  # timestamps of recent failures
    cooldown_until: float = 0.0  # epoch seconds; 0 = healthy
    probe_pending: bool = False  # True after cooldown expires, until next call


_state: dict[str, _EndpointState] = {}


# Tunable thresholds. Mutated by ``configure``; defaults from the spec.
_failure_window_seconds: float = 60.0
_failure_threshold: int = 3
_cooldown_seconds: float = 300.0


def configure(
    failure_window_seconds: float | None = None,
    failure_threshold: int | None = None,
    cooldown_seconds: float | None = None,
) -> None:
    """Adjust circuit-breaker thresholds. Pass None to leave a knob unchanged."""
    global _failure_window_seconds, _failure_threshold, _cooldown_seconds
    with _registry_lock:
        if failure_window_seconds is not None:
            _failure_window_seconds = float(failure_window_seconds)
        if failure_threshold is not None:
            _failure_threshold = int(failure_threshold)
        if cooldown_seconds is not None:
            _cooldown_seconds = float(cooldown_seconds)


def _get_state(endpoint_id: str) -> _EndpointState:
    st = _state.get(endpoint_id)
    if st is None:
        st = _EndpointState(failures=deque())
        _state[endpoint_id] = st
    return st


def _prune_old_failures(st: _EndpointState, now: float) -> None:
    cutoff = now - _failure_window_seconds
    while st.failures and st.failures[0] < cutoff:
        st.failures.popleft()


def record_failure(endpoint_id: str) -> None:
    """Record a failed call. Trips the breaker on threshold cross."""
    now = time.time()
    with _registry_lock:
        st = _get_state(endpoint_id)
        _prune_old_failures(st, now)
        st.failures.append(now)
        if len(st.failures) >= _failure_threshold:
            st.cooldown_until = now + _cooldown_seconds
            st.probe_pending = False
        if st.probe_pending:
            # Probe failed during half-open — extend the cooldown.
            st.cooldown_until = now + _cooldown_seconds
            st.probe_pending = False


def record_success(endpoint_id: str) -> None:
    """Record a successful call. Resets state when the breaker was tripped."""
    with _registry_lock:
        st = _state.get(endpoint_id)
        if st is None:
            return
        if st.probe_pending or st.cooldown_until > 0:
            st.failures.clear()
            st.cooldown_until = 0.0
            st.probe_pending = False


def is_in_cooldown(endpoint_id: str) -> bool:
    """Should the router skip this endpoint right now?

    True when the breaker is tripped AND the cooldown window hasn't
    expired AND a probe hasn't been issued yet. The first call after
    cooldown elapses is allowed through as a probe (returns False);
    subsequent calls block (return True) until the probe records a
    result.
    """
    now = time.time()
    with _registry_lock:
        st = _state.get(endpoint_id)
        if st is None:
            return False
        if st.cooldown_until == 0:
            return False
        if now < st.cooldown_until:
            return True
        # Cooldown expired — let the next caller through as a probe.
        if not st.probe_pending:
            st.probe_pending = True
            return False
        return True


def endpoint_status(endpoint_id: str) -> dict:
    """Inspect state for debugging / observability.

    Returns a dict with the recent-failure count, cooldown deadline
    (epoch seconds, 0 if healthy), and whether a probe is pending.
    """
    now = time.time()
    with _registry_lock:
        st = _state.get(endpoint_id)
        if st is None:
            return {
                "endpoint_id": endpoint_id,
                "healthy": True,
                "recent_failures": 0,
                "cooldown_remaining": 0,
                "probe_pending": False,
            }
        _prune_old_failures(st, now)
        cooldown_remaining = max(0, int(st.cooldown_until - now))
        return {
            "endpoint_id": endpoint_id,
            "healthy": st.cooldown_until == 0,
            "recent_failures": len(st.failures),
            "cooldown_remaining": cooldown_remaining,
            "probe_pending": st.probe_pending,
        }


def reset_for_tests() -> None:
    """Clear all state. Test-only."""
    global _failure_window_seconds, _failure_threshold, _cooldown_seconds
    with _registry_lock:
        _state.clear()
        _failure_window_seconds = 60.0
        _failure_threshold = 3
        _cooldown_seconds = 300.0


__all__ = [
    "configure",
    "record_failure",
    "record_success",
    "is_in_cooldown",
    "endpoint_status",
    "reset_for_tests",
]
