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
  ``server/app.py`` so future operators have one mental model.
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
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Flows from runtime_paths (ORA_HOME-relocatable) so job files land in the
# same sessions root the envelope writer and stealth purge use.
DEFAULT_SESSIONS_ROOT = _rp.ORA_HOME / "sessions"
JOBS_FILENAME = "jobs.json"


def _conversation_segment(conversation_id: str) -> str:
    """Validate and return the canonical on-disk conversation segment.

    Replacing punctuation with ``_`` made distinct IDs share one jobs.json
    (for example ``a:b`` and ``a?b``). New persistent queue writes therefore
    accept only the same portable ID alphabet as the server and use that ID
    verbatim. Delete Forever's in-memory ``forget_conversation`` remains able
    to tombstone a legacy safe path segment without touching the filesystem.
    """
    if not isinstance(conversation_id, str):
        raise ValueError("conversation_id must be a string")
    if not conversation_id or len(conversation_id) > 255:
        raise ValueError("invalid conversation_id")
    if conversation_id != conversation_id.strip():
        raise ValueError("invalid conversation_id")
    if not all(ch.isascii() and (ch.isdigit() or ch.islower() or ch in "_-")
               for ch in conversation_id):
        raise ValueError("invalid conversation_id")
    return conversation_id


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class JobNotFound(Exception):
    """No job with the given id in the conversation's queue."""


class InvalidStatusTransition(Exception):
    """The requested transition is not permitted from the current state."""


class JobOwnerUnavailable(Exception):
    """The job's owning Dialogue is not live and authoritative."""


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
        self._deleted_conversations: set[str] = set()
        # subscriber callables for the event bus.
        self._subscribers: list[Callable[[dict], None]] = []
        # one lock guards everything — the queue is low-volume, and Flask
        # serves SSE generators across threads, so we keep it simple.
        self._lock = threading.RLock()

    # --- Persistence ----------------------------------------------------

    def _jobs_path(self, conversation_id: str) -> Path:
        return self._root / _conversation_segment(conversation_id) / JOBS_FILENAME

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

    def _persist(self, conversation_id: str) -> bool:
        """Mirror the in-memory list to disk and report durability.

        Ordinary queue mutations retain the existing fail-open behavior. A
        provider that must prove a paid remote identity was recorded before it
        continues can use :meth:`update_metadata` with ``require_persisted``.
        """
        try:
            path = _rp.safe_owned_subdir(
                self._root,
                _conversation_segment(conversation_id),
                create=True,
            ) / JOBS_FILENAME
            entries = [
                job.to_dict()
                for job in self._jobs.get(conversation_id.casefold(), [])
            ]
            _rp.atomic_write_text(path, json.dumps(entries, indent=2))
            return True
        except Exception as exc:  # pragma: no cover — log only
            print(f"[job-queue] persist failed for {conversation_id}: {exc}")
            return False

    def _persisted_conversation_ids(self) -> list[str]:
        """Return safe direct-child Dialogue ids that own a jobs mirror."""
        try:
            if not self._root.is_dir() or self._root.is_symlink():
                return []
            found: list[str] = []
            for child in self._root.iterdir():
                if child.is_symlink() or not child.is_dir():
                    continue
                try:
                    conversation_id = _conversation_segment(child.name)
                except ValueError:
                    continue
                jobs_path = child / JOBS_FILENAME
                if jobs_path.is_file() and not jobs_path.is_symlink():
                    found.append(conversation_id)
            return sorted(found)
        except Exception as exc:  # pragma: no cover — log + loaded-only view
            print(f"[job-queue] persisted job discovery failed: {exc}")
            return []

    def _ensure_loaded(self, conversation_id: str) -> list[Job]:
        """Lazy-load the conversation's jobs from disk on first touch."""
        identity = conversation_id.casefold()
        if identity in self._deleted_conversations:
            return []
        if identity not in self._jobs:
            self._jobs[identity] = self._load(conversation_id)
        return self._jobs[identity]

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

    @contextmanager
    def authenticated_conversation(
        self,
        conversation_id: str,
        job_id: str | None = None,
    ):
        """Hold the existing lifecycle boundary for one live Dialogue/job.

        Paid provider work may proceed only while its owning envelope remains
        readable and names the same Dialogue.  When ``job_id`` is supplied,
        the queue binding must also still exist.  Delete Forever shares this
        lifecycle lock through :meth:`forget_conversation`.
        """
        conversation_id = _conversation_segment(conversation_id)
        with _rp.conversation_lifecycle_lock(conversation_id):
            try:
                from orchestrator.conversation_memory import (
                    read_conversation_history_envelope,
                )
            except ImportError:  # pragma: no cover - direct module context
                from conversation_memory import read_conversation_history_envelope
            envelope = read_conversation_history_envelope(
                conversation_id,
                sessions_root=self._root,
            )
            if (not isinstance(envelope, dict)
                    or envelope.get("conversation_id") != conversation_id
                    or not isinstance(envelope.get("messages"), list)):
                raise JobOwnerUnavailable(
                    f"Dialogue '{conversation_id}' is not live and authoritative"
                )
            with self._lock:
                if conversation_id.casefold() in self._deleted_conversations:
                    raise JobOwnerUnavailable(
                        f"Dialogue '{conversation_id}' was permanently deleted"
                    )
                if job_id is not None:
                    try:
                        self._find(conversation_id, job_id)
                    except JobNotFound as exc:
                        raise JobOwnerUnavailable(
                            f"job '{job_id}' no longer belongs to Dialogue "
                            f"'{conversation_id}'"
                        ) from exc
            yield

    def begin_submission(
        self,
        conversation_id: str,
        job_id: str,
        metadata: dict,
    ) -> dict:
        """Durably claim a queued job before any paid provider contact.

        Status and provider submission metadata are one persisted transition,
        so cancellation either wins while still queued (and no submission may
        begin) or records intent against an already in-progress submission.
        """
        if not isinstance(metadata, dict):
            raise TypeError("submission metadata must be a dict")
        with self._lock:
            job = self._find(conversation_id, job_id)
            if job.status != STATUS_QUEUED:
                raise InvalidStatusTransition(
                    f"Cannot begin submission for job '{job_id}' from "
                    f"'{job.status}'."
                )
            previous_metadata = dict(job.metadata)
            previous_started_at = job.started_at
            job.status = STATUS_IN_PROGRESS
            job.started_at = time.time()
            job.metadata.update(dict(metadata))
            if not self._persist(conversation_id):
                job.status = STATUS_QUEUED
                job.started_at = previous_started_at
                job.metadata = previous_metadata
                raise OSError("submission start could not be persisted")
            event = {
                "type": "status_changed",
                "conversation_id": conversation_id,
                "job": job.to_dict(),
                "previous_status": STATUS_QUEUED,
            }
        self._emit(event)
        return job.to_dict()

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
        conversation_id = _conversation_segment(conversation_id)
        with self._lock:
            if conversation_id.casefold() in self._deleted_conversations:
                raise RuntimeError("conversation was permanently deleted")
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

    def update_metadata(
        self,
        conversation_id: str,
        job_id: str,
        updates: dict,
        *,
        require_persisted: bool = False,
    ) -> dict:
        """Merge provider metadata into a job and mirror it immediately.

        ``require_persisted`` is for the narrow paid-submission boundary: a
        caller must not contact or poll a provider unless the corresponding
        state is durably attached to this existing job.
        """
        if not isinstance(updates, dict):
            raise TypeError("metadata updates must be a dict")
        with self._lock:
            job = self._find(conversation_id, job_id)
            previous = dict(job.metadata)
            job.metadata.update(dict(updates))
            persisted = self._persist(conversation_id)
            if require_persisted and not persisted:
                job.metadata = previous
                raise OSError("job metadata could not be persisted")
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
                if job.metadata.get("provider") == "replicate":
                    previous_completed_at = job.completed_at
                    job.status = STATUS_CANCELLED
                    job.completed_at = time.time()
                    if not self._persist(conversation_id):
                        job.status = STATUS_QUEUED
                        job.completed_at = previous_completed_at
                        raise OSError(
                            "paid-job queued cancellation could not be persisted"
                        )
                    event = {
                        "type": "status_changed",
                        "conversation_id": conversation_id,
                        "job": job.to_dict(),
                        "previous_status": STATUS_QUEUED,
                    }
                    self._emit(event)
                    return job.to_dict()
                return self._transition(
                    conversation_id, job_id, STATUS_CANCELLED,
                    require_from={STATUS_QUEUED},
                    mutate=lambda j: setattr(j, "completed_at", time.time()),
                )
            if job.status == STATUS_IN_PROGRESS:
                previous_cancel_requested = job.cancel_requested
                job.cancel_requested = True
                persisted = self._persist(conversation_id)
                if (not persisted and job.metadata.get("provider") == "replicate"):
                    job.cancel_requested = previous_cancel_requested
                    raise OSError("paid-job cancellation intent could not be persisted")
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
        in-progress jobs across the conversation surface). Persisted Dialogue
        mirrors are discovered here so startup recovery is not limited to
        conversations already touched in this process."""
        with self._lock:
            for conversation_id in self._persisted_conversation_ids():
                identity = conversation_id.casefold()
                if (identity not in self._jobs
                        and identity not in self._deleted_conversations):
                    self._jobs[identity] = self._load(conversation_id)
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
            self._jobs.pop(conversation_id.casefold(), None)
            return [j.to_dict() for j in self._ensure_loaded(conversation_id)]

    def forget_conversation(self, conversation_id: str) -> int:
        """Quiesce paid work, then forget one permanently deleted Dialogue.

        Replicate predictions are metered remote work.  Delete Forever must
        therefore receive provider-terminal acknowledgement while the durable
        binding still exists.  A missing callback, malformed binding, failed
        cancellation, or unavailable confirmation leaves both the in-memory
        jobs and ``jobs.json`` untouched and raises for the lifecycle caller to
        treat as a pre-purge failure.

        The session directory remains the core deletion path's responsibility.
        On success this method only tombstones the Dialogue in this process and
        drops the queue cache after every bound or indeterminate Replicate
        prediction is known to be terminal.
        """
        if not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string")
        legacy_id = conversation_id.strip()
        if (not legacy_id or legacy_id in {".", ".."}
                or len(legacy_id) > 255 or "/" in legacy_id
                or "\\" in legacy_id or "\x00" in legacy_id
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in legacy_id)):
            raise ValueError("invalid conversation_id")

        def needs_provider_quiesce(job: Job) -> bool:
            metadata = job.metadata if isinstance(job.metadata, dict) else {}
            return (
                metadata.get("provider") == "replicate"
                and (
                    job.status == STATUS_IN_PROGRESS
                    or metadata.get("provider_submission_state") in {
                        "submitting", "bound",
                    }
                    or bool(metadata.get("provider_prediction_id"))
                )
            )

        with _rp.conversation_lifecycle_lock(legacy_id):
            identity = legacy_id.casefold()
            with self._lock:
                canonical_id = True
                try:
                    jobs = list(self._ensure_loaded(legacy_id))
                except ValueError:
                    # Legacy IDs were accepted before queue paths adopted the
                    # canonical portable alphabet.  They can still be
                    # tombstoned in memory, but must never be mapped to a new
                    # or lossy on-disk path.
                    canonical_id = False
                    jobs = list(self._jobs.get(identity, []))
                paid_jobs = [
                    job.to_dict()
                    for job in jobs
                    if needs_provider_quiesce(job)
                ]

            cancellations: list[dict] = []
            errors: list[str] = []
            if paid_jobs:
                try:
                    from orchestrator.integrations import replicate
                    cancel_bound = getattr(
                        replicate, "cancel_bound_predictions", None,
                    )
                    if not callable(cancel_bound):
                        raise RuntimeError(
                            "Replicate cancellation callback is unavailable"
                        )
                    outcome = cancel_bound(legacy_id, paid_jobs)
                    if not isinstance(outcome, dict):
                        raise RuntimeError(
                            "Replicate cancellation callback returned no result"
                        )
                    cancellations = list(outcome.get("confirmed") or [])
                    errors.extend(str(item) for item in outcome.get("errors") or [])
                except Exception as exc:
                    errors.append(
                        "Replicate cancellation confirmation failed: "
                        f"{type(exc).__name__}: {exc}"
                    )

            if errors:
                raise RuntimeError("; ".join(errors))

            with self._lock:
                # The provider worker and paid dispatcher share the lifecycle
                # lock above.  Re-read before erasure so an unsupported direct
                # queue mutation cannot silently add a fresh paid binding while
                # cancellation is in flight.
                current = (
                    self._ensure_loaded(legacy_id)
                    if canonical_id
                    else self._jobs.get(identity, [])
                )
                current_paid_ids = {
                    job.id
                    for job in current
                    if needs_provider_quiesce(job)
                }
                confirmed_ids = {
                    str(item.get("job_id"))
                    for item in cancellations
                    if isinstance(item, dict) and item.get("job_id")
                }
                if current_paid_ids != confirmed_ids:
                    raise RuntimeError(
                        "Replicate job bindings changed before deletion could "
                        "erase them"
                    )
                forgotten = len(current)
                self._deleted_conversations.add(identity)
                self._jobs.pop(identity, None)
            return forgotten

    def release_cached(self, conversation_id: str) -> int:
        """Drop a conversation's in-memory jobs, keeping jobs.json intact.

        For Close, which is reversible and retains data. Unlike
        ``forget_conversation`` this does not tombstone the conversation, and
        unlike ``purge_terminal`` it removes nothing from disk — the queue is
        mirrored to ``jobs.json`` and reloads on the next read. Purely a
        memory release; a restored Dialogue sees the same jobs it had.
        """
        if not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string")
        identity = conversation_id.strip().casefold()
        if not identity:
            raise ValueError("invalid conversation_id")
        with self._lock:
            return len(self._jobs.pop(identity, []))

    def purge_terminal(self, conversation_id: str) -> int:
        """Drop terminal jobs from the on-disk + in-memory queue. Returns
        the count removed. Useful in tests + as a future user-triggered
        clean-up."""
        with self._lock:
            jobs = self._ensure_loaded(conversation_id)
            kept = [j for j in jobs if j.status not in TERMINAL_STATUSES]
            removed = len(jobs) - len(kept)
            if removed:
                self._jobs[conversation_id.casefold()] = kept
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


_default_recovery_started = False
_default_recovery_lock = threading.Lock()


def start_default_queue_recovery() -> list[threading.Thread]:
    """Reattach paid jobs from the core queue startup seam exactly once."""
    global _default_recovery_started
    with _default_recovery_lock:
        if _default_recovery_started:
            return []
        try:
            from orchestrator.integrations import replicate
            reconcile = getattr(replicate, "reconcile_unfinished_jobs", None)
            if not callable(reconcile):
                return []
            threads = reconcile()
            _default_recovery_started = True
            return threads
        except Exception as exc:  # pragma: no cover - startup remains fail-open
            print(
                f"[job-queue] Replicate startup reconciliation failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            return []
