"""Extension Bridge — communication layer between the Ora server and Chrome extension.

The Chrome extension polls the server for pending evaluation requests,
performs them in authenticated browser tabs, and posts results back.

This module manages the request queue and result store. It is imported by:
  - server.py (to expose the pending/result/evaluate endpoints)
  - browser_evaluate.py (to submit evaluation requests and wait for results)
"""

from __future__ import annotations

import time
import threading
import uuid
from queue import Queue, Empty


# ── Shared State ────────────────────────────────────────────────────────────

_requests: Queue = Queue()
_results: dict = {}          # req_id -> {"event": Event, "result": str|None, "error": str|None}
_lock = threading.Lock()
_last_poll: float = 0.0      # timestamp of last poll from extension

# Extension is "connected" if it polled within the last 10 seconds
_POLL_TIMEOUT = 10.0


# ── Connection Management ───────────────────────────────────────────────────

def is_connected() -> bool:
    """Check if the Chrome extension is actively polling."""
    return (time.time() - _last_poll) < _POLL_TIMEOUT


def record_poll():
    """Called each time the extension polls for work. Updates connection state."""
    global _last_poll
    _last_poll = time.time()


# ── Request/Result Flow ─────────────────────────────────────────────────────

def get_pending_request_nowait() -> dict | None:
    """Non-blocking: return the next queued request, or None."""
    try:
        return _requests.get_nowait()
    except Empty:
        return None


def get_pending_request(timeout: float = 30) -> dict | None:
    """Blocking: wait up to `timeout` seconds for a request."""
    try:
        return _requests.get(timeout=timeout)
    except Empty:
        return None


def submit_result(req_id: str, response: str | None = None, error: str | None = None):
    """Called when the extension posts an evaluation result."""
    with _lock:
        entry = _results.get(req_id)
    if entry:
        entry["result"] = response
        entry["error"] = error
        entry["event"].set()


def evaluate(service: str, prompt: str, config: dict | None = None, timeout: float = 120) -> str | None:
    """Send an evaluation request to the Chrome extension and wait for a result.

    Returns the response text, an error string, or None if the extension
    is not connected (caller should fall back to another channel).
    """
    if not is_connected():
        return None

    req_id = str(uuid.uuid4())
    event = threading.Event()

    with _lock:
        _results[req_id] = {"event": event, "result": None, "error": None}

    _requests.put({
        "id": req_id,
        "type": "evaluate",
        "service": service,
        "prompt": prompt,
        "config": config or {},
    })

    if event.wait(timeout=timeout):
        with _lock:
            entry = _results.pop(req_id, None)
        if not entry:
            return None
        if entry["error"]:
            return f"[extension] {entry['error']}"
        return entry["result"]
    else:
        # Timeout — clean up
        with _lock:
            _results.pop(req_id, None)
        return None
