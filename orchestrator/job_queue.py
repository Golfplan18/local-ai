"""Async job queue for capability dispatch (WP-7.6.1).

A *job* represents one async capability invocation (e.g.,
``video_generates``, ``style_trains``) — the slot itself declares
``execution_pattern: async`` in ``capabilities.json`` and the dispatcher
files the work here instead of returning inline. The queue keeps every
in-flight job per conversation, mirrors the state to disk so jobs survive
a server restart, and exposes a clean event-bus that downstream WPs
consume:

* **WP-7.6.2** consumes ``status_changed`` events to land async results
  in the same chat output stream as sync results.
* **WP-7.6.3** uses ``cancel_job`` / ``request_cancel`` to wire the
  with-warning cancellation flow.
* **WP-7.3.4** (Replicate / video / training providers) registers
  completion callbacks via ``mark_in_progress`` / ``mark_complete`` /
  ``mark_failed``.

This module is provider-agnostic. Jobs can be stub-mocked for tests; the
queue does not call providers directly. Provider integration happens at
the dispatcher layer where a job's ``capability`` slot resolves to a
handler — the handler returns a job-handle (the queue's ``id``), and
later, when the handler eventually completes, it calls back into the
queue with ``mark_complete(id, result_ref)``.

Design notes
------------

* **Per-conversation persistence.** Jobs live in
  ``~/ora/sessions/<conversation_id>/jobs.json``. Same path convention
  as the existing ``vision-retry-queue.json`` mirror in
  ``server/server.py`` so future operators have one mental model.
* **In-memory + disk mirror.** All mutations write through to disk in
  the same call. Read paths are in-memory (no per-call disk hit).
  Reload-on-init rehydrates from disk so a server restart picks up
  exactly where it left off.
* **No active polling / no provider integration.** This module only
  manages state and emits events. The placeholders in the canvas + the
  queue UI in the chat bridge are JavaScript components that listen for
  the SSE frames the server emits when ``status_changed`` fires.
* **Event hooks.** ``subscribe(handler)`` registers a callback the
  queue calls synchronously on every state transition. The Flask SSE
  generator subscribes once at process start and emits ``job_status``
  frames so the browser can update.
* **Status taxonomy.** ``queued`` → ``in_progress`` →
  ``complete`` | ``failed`` | ``cancelled``. ``request_cancel``
  marks a job ``cancelled`` if it has not yet started, or sets
  ``cancel_requested`` for the provider to honour mid-flight (WP-7.6.3
  fleshes out provider-side cancellation; this module only tracks the
  request).

Public API
----------

``JobQueue(sessions_root=None)``
    Construct a queue rooted at ``~/ora/sessions/`` (overridable for
    tests). One queue instance covers all conversations; jobs are keyed
    by ``conversation_id`` internally.

``queue.dispatch(conversation_id, capability, parameters,
                 placeholder_anchor=None)``
    Create a new job in ``queued`` status, persist, return the job dict.

``queue.list_jobs(conversation_id)``
    Return the in-memory list of jobs for the conversation in
    insertion order.

``queue.get_job(conversation_id, job_id)``
    Return the job dict or raise ``JobNotFound``.

``queue.mark_in_progress(conversation_id, job_id)``
    Transition ``queued → in_progress``. Records ``started_at``.

``queue.mark_complete(conversation_id, job_id, result_ref)``
    Transition to ``complete`` and store the result reference (typically
    a canvas-object id, file path, or canonical output identifier the
    chat output stream knows how to render).

``queue.mark_failed(conversation_id, job_id, error)``
    Transition to ``failed``. ``error`` is a free-form string; the
    queue does not inspect it.

``queue.request_cancel(conversation_id, job_id)``
    If the job is still ``queued``, transition immediately to
    ``cancelled``. If ``in_progress``, set ``cancel_requested = True``
    and emit a ``cancel_requested`` event so the provider hook can act.
    WP-7.6.3 wires the provider-side cancellation; for now this is a
    flag plus an event.

``queue.cancel_job(conversation_id, job_id)``
    Force-cancel: set status to ``cancelled`` regardless of current
    state. Used by WP-7.6.3 once the user confirms the billing
    warning.

``queue.subscribe(handler)``
    Register ``handler(event_dict)`` for every state transition. Returns
    an unsubscribe callable.

Errors
------

``JobNotFound`` and ``InvalidStatusTransition`` are raised on bad input.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_SESSIONS_ROOT = Path(os.path.expanduser("~/ora/sessions"))
JOBS_FILENAME = "jobs.json"


def _slug(conversation_id: str) -> str:
    """Filesystem-safe slug for a conversation id (matches the
    ``vision-retry-queue`` convention in ``server.py``)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id or "default") or "default"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class JobNotFound(Exception):
    """No job with the given id in the conversation's queue."""


class InvalidStatusTransition(Exception):
    """The requested transition is not permitted from the current state."""


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

STATUS_QUEUED = "queued"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETE = "complete"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"

ALL_STATUSES = {
    STATUS_QUEUED, STATUS_IN_PROGRESS, STATUS_COMPLETE,
    STATUS_CANCELLED, STATUS_FAILED,
}

# Terminal statuses cannot transition further.
TERMINAL_STATUSES = {STATUS_COMPLETE, STATUS_CANCELLED, STATUS_FAILED}


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class Job:
    """One async capability invocation.

    Persisted shape — every field round-trips through ``jobs.json``.
    """
    id: str
    capability: str
    parameters: dict
    dispatched_at: float
    status: str = STATUS_QUEUED
    result_ref: Any = None
    placeholder_anchor: dict | None = None
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    cancel_requested: bool = False
    # Free-form metadata bag for downstream WPs (e.g., provider job-id
    # from Replicate, ETA estimates, progress percentage). The queue
    # itself does not interpret it — it's just round-tripped to disk.
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

class JobQueue:
    """In-memory job queue with per-conversation disk mirror."""

    def __init__(self, sessions_root: str | Path | None = None):
        self._root = Path(sessions_root) if sessions_root else DEFAULT_SESSIONS_ROOT
        # conversation_id -> list[Job] in insertion order.
        self._jobs: dict[str, list[Job]] = {}
        # subscriber callables for the event bus.
        self._subscribers: list[Callable[[dict], None]] = []
        # one lock guards everything — the queue is low-volume, and Flask
        # serves SSE generators across threads, so we keep it simple.
        self._lock = threading.RLock()

    # --- Persistence ----------------------------------------------------

    def _jobs_path(self, conversation_id: str) -> Path:
        return self._root / _slug(conversation_id) / JOBS_FILENAME

    def _load(self, conversation_id: str) -> list[Job]:
        """Read the on-disk mirror for ``conversation_id``.

        Returns an empty list when the file is missing or malformed —
        fail-open matches the ``vision-retry-queue`` precedent.
        """
        path = self._jobs_path(conversation_id)
        if not path.exists():
            return []
        try:
            with open(path) as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                return []
            return [Job(**entry) for entry in data]
        except Exception as exc:  # pragma: no cover — log + empty
            print(f"[job-queue] load failed for {conversation_id}: {exc}")
            return []

    def _persist(self, conversation_id: str) -> None:
        """Mirror the in-memory list to disk. Fail-open."""
        path = self._jobs_path(conversation_id)
        try:
            os.makedirs(path.parent, exist_ok=True)
            entries = [job.to_dict() for job in self._jobs.get(conversation_id, [])]
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w") as fh:
                json.dump(entries, fh, indent=2)
            os.replace(tmp, path)
        except Exception as exc:  # pragma: no cover — log only
            print(f"[job-queue] persist failed for {conversation_id}: {exc}")

    def _ensure_loaded(self, conversation_id: str) -> list[Job]:
        """Lazy-load the conversation's jobs from disk on first touch."""
        if conversation_id not in self._jobs:
            self._jobs[conversation_id] = self._load(conversation_id)
        return self._jobs[conversation_id]

    # --- Event bus ------------------------------------------------------

    def subscribe(self, handler: Callable[[dict], None]) -> Callable[[], None]:
        """Register a synchronous handler for state-change events.

        Each event is a dict::

            {
                "type": "job_dispatched" | "status_changed" |
                        "cancel_requested",
                "conversation_id": "...",
                "job": {...full job dict...},
                "previous_status": "queued",   # status_changed only
            }

        Returns an unsubscribe callable.
        """
        with self._lock:
            self._subscribers.append(handler)

        def _unsub():
            with self._lock:
                if handler in self._subscribers:
                    self._subscribers.remove(handler)
        return _unsub

    def _emit(self, event: dict) -> None:
        """Fire ``event`` to every subscriber. Errors swallowed so one
        bad subscriber does not break the rest."""
        for sub in list(self._subscribers):
            try:
                sub(event)
            except Exception as exc:  # pragma: no cover — log
                print(f"[job-queue] subscriber error: {exc}")

    # --- Mutators -------------------------------------------------------

    def dispatch(
        self,
        conversation_id: str,
        capability: str,
        parameters: dict,
        placeholder_anchor: dict | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create a new ``queued`` job. Returns its serialized form.

        ``placeholder_anchor`` is the canvas position where the
        persistent placeholder should render (``{"x": 100, "y": 200,
        "width": 256, "height": 256}`` is a typical shape — exact schema
        is the canvas's call). The queue does not interpret it — it
        round-trips to disk and back.
        """
        with self._lock:
            jobs = self._ensure_loaded(conversation_id)
            job = Job(
                id=str(uuid.uuid4()),
                capability=capability,
                parameters=dict(parameters or {}),
                dispatched_at=time.time(),
                placeholder_anchor=dict(placeholder_anchor) if placeholder_anchor else None,
                metadata=dict(metadata or {}),
            )
            jobs.append(job)
            self._persist(conversation_id)
            event = {
                "type": "job_dispatched",
                "conversation_id": conversation_id,
                "job": job.to_dict(),
            }
        self._emit(event)
        return job.to_dict()

    def _find(self, conversation_id: str, job_id: str) -> Job:
        jobs = self._ensure_loaded(conversation_id)
        for job in jobs:
            if job.id == job_id:
                return job
        raise JobNotFound(
            f"No job '{job_id}' in conversation '{conversation_id}'"
        )

    def _transition(
        self,
        conversation_id: str,
        job_id: str,
        new_status: str,
        *,
        require_from: set[str] | None = None,
        mutate: Callable[[Job], None] | None = None,
        event_type: str = "status_changed",
    ) -> dict:
        """Internal helper — guarded transition with persist + event."""
        if new_status not in ALL_STATUSES:
            raise InvalidStatusTransition(
                f"Unknown status '{new_status}'. Allowed: {sorted(ALL_STATUSES)}"
            )
        with self._lock:
            job = self._find(conversation_id, job_id)
            previous = job.status
            if require_from is not None and previous not in require_from:
                raise InvalidStatusTransition(
                    f"Cannot transition job '{job_id}' from '{previous}' "
                    f"to '{new_status}'. Allowed source states: "
                    f"{sorted(require_from)}"
                )
            job.status = new_status
            if mutate is not None:
                mutate(job)
            self._persist(conversation_id)
            event = {
                "type": event_type,
                "conversation_id": conversation_id,
                "job": job.to_dict(),
                "previous_status": previous,
            }
        self._emit(event)
        return job.to_dict()

    def mark_in_progress(self, conversation_id: str, job_id: str) -> dict:
        def _mut(job: Job) -> None:
            job.started_at = time.time()
        return self._transition(
            conversation_id, job_id, STATUS_IN_PROGRESS,
            require_from={STATUS_QUEUED},
            mutate=_mut,
        )

    def mark_complete(
        self, conversation_id: str, job_id: str, result_ref: Any
    ) -> dict:
        def _mut(job: Job) -> None:
            job.completed_at = time.time()
            job.result_ref = result_ref
        return self._transition(
            conversation_id, job_id, STATUS_COMPLETE,
            require_from={STATUS_QUEUED, STATUS_IN_PROGRESS},
            mutate=_mut,
        )

    def mark_failed(
        self, conversation_id: str, job_id: str, error: str
    ) -> dict:
        def _mut(job: Job) -> None:
            job.completed_at = time.time()
            job.error = str(error)
        return self._transition(
            conversation_id, job_id, STATUS_FAILED,
            require_from={STATUS_QUEUED, STATUS_IN_PROGRESS},
            mutate=_mut,
        )

    def request_cancel(self, conversation_id: str, job_id: str) -> dict:
        """User asked to cancel.

        * If the job is ``queued`` we cancel right now — nothing is
          running, no billing risk.
        * If it's ``in_progress`` we set ``cancel_requested = True``
          and emit ``cancel_requested``; WP-7.6.3 wires provider-side
          stop. The status stays ``in_progress`` until the provider
          confirms via ``cancel_job`` (or completes / fails first).
        * Terminal statuses raise ``InvalidStatusTransition`` —
          there's nothing to cancel.
        """
        with self._lock:
            job = self._find(conversation_id, job_id)
            if job.status == STATUS_QUEUED:
                # Already-not-running ⇒ cancel immediately.
                return self._transition(
                    conversation_id, job_id, STATUS_CANCELLED,
                    require_from={STATUS_QUEUED},
                    mutate=lambda j: setattr(j, "completed_at", time.time()),
                )
            if job.status == STATUS_IN_PROGRESS:
                job.cancel_requested = True
                self._persist(conversation_id)
                event = {
                    "type": "cancel_requested",
                    "conversation_id": conversation_id,
                    "job": job.to_dict(),
                    "previous_status": STATUS_IN_PROGRESS,
                }
                self._emit(event)
                return job.to_dict()
            raise InvalidStatusTransition(
                f"Cannot cancel job '{job_id}' in terminal status "
                f"'{job.status}'."
            )

    def cancel_job(self, conversation_id: str, job_id: str) -> dict:
        """Force-cancel regardless of current state. WP-7.6.3 calls this
        once the user confirms the billing warning."""
        def _mut(job: Job) -> None:
            job.completed_at = time.time()
        return self._transition(
            conversation_id, job_id, STATUS_CANCELLED,
            require_from={STATUS_QUEUED, STATUS_IN_PROGRESS},
            mutate=_mut,
        )

    # --- Readers --------------------------------------------------------

    def list_jobs(self, conversation_id: str) -> list[dict]:
        """All jobs for this conversation in insertion order (serialised)."""
        with self._lock:
            return [j.to_dict() for j in self._ensure_loaded(conversation_id)]

    def list_active_jobs(self, conversation_id: str) -> list[dict]:
        """Just the non-terminal jobs (``queued`` + ``in_progress``)."""
        with self._lock:
            return [
                j.to_dict() for j in self._ensure_loaded(conversation_id)
                if j.status not in TERMINAL_STATUSES
            ]

    def list_all_active_across_conversations(self) -> dict[str, list[dict]]:
        """Active jobs grouped by conversation. Used by the queue UI when
        it needs a global view (e.g., the chat bridge area listing all
        in-progress jobs across the conversation surface)."""
        with self._lock:
            out: dict[str, list[dict]] = {}
            for cid, jobs in self._jobs.items():
                active = [j.to_dict() for j in jobs
                          if j.status not in TERMINAL_STATUSES]
                if active:
                    out[cid] = active
            return out

    def get_job(self, conversation_id: str, job_id: str) -> dict:
        with self._lock:
            return self._find(conversation_id, job_id).to_dict()

    # --- Maintenance ----------------------------------------------------

    def reload_from_disk(self, conversation_id: str) -> list[dict]:
        """Drop the in-memory copy and re-read from disk. Used when an
        external process (test harness, future maintenance script) has
        edited ``jobs.json`` directly."""
        with self._lock:
            self._jobs.pop(conversation_id, None)
            return [j.to_dict() for j in self._ensure_loaded(conversation_id)]

    def purge_terminal(self, conversation_id: str) -> int:
        """Drop terminal jobs from the on-disk + in-memory queue. Returns
        the count removed. Useful in tests + as a future user-triggered
        clean-up."""
        with self._lock:
            jobs = self._ensure_loaded(conversation_id)
            kept = [j for j in jobs if j.status not in TERMINAL_STATUSES]
            removed = len(jobs) - len(kept)
            if removed:
                self._jobs[conversation_id] = kept
                self._persist(conversation_id)
            return removed


# ---------------------------------------------------------------------------
# Module-level singleton — the typical caller imports this directly.
# Tests instantiate their own JobQueue with a tmp sessions_root.
# ---------------------------------------------------------------------------

_default_queue: JobQueue | None = None


def get_default_queue() -> JobQueue:
    """Return the process-wide JobQueue (lazy-init).

    The Flask SSE generator subscribes to this queue at process start so
    every state change becomes a ``job_status`` SSE frame. Provider
    handlers in WP-7.3.4 import this and call ``mark_complete`` /
    ``mark_failed`` from their own threads.
    """
    global _default_queue
    if _default_queue is None:
        _default_queue = JobQueue()
    return _default_queue
