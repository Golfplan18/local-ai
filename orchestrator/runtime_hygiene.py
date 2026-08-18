"""Event and deadline substrate for Runtime-Principle maintenance.

The substrate has two deliberately small primitives:

* an authenticated, idempotent event ledger for work caused by an exact
  runtime event; and
* a persisted one-shot deadline queue for work whose cause is genuinely
  temporal.

Neither primitive scans for work on a cadence. Event handlers receive exact
identities. Deadline workers sleep until the earliest recorded instant. Full
historical sweeps remain explicit campaigns outside this module.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


SCHEMA_VERSION = 1
_PROCESS_LOCK = threading.RLock()

# Size at which an append-only audit sink is rolled to a dated sibling.
# Provisional — 32 MB is roughly a month of ordinary event volume while
# staying small enough to open. The append IS the size-threshold event the
# hygiene framework names; nothing here runs on a clock.
def _audit_rotate_mb() -> float:
    """Threshold in MB. A malformed value falls back rather than raising.

    This is read at import in two places; a typo in the env var must not stop
    the runtime from starting.
    """
    try:
        return float(os.environ.get("ORA_RUNTIME_AUDIT_ROTATE_MB") or 32)
    except (TypeError, ValueError):
        return 32.0


AUDIT_ROTATE_MB = _audit_rotate_mb()
# Terminal ledger records retained in the live state map. Provisional. The
# state file is rewritten and fsync'd in full on every claim and transition, so
# its size is a per-event write cost, not just disk: 4,311 finished records had
# grown it to 3.21 MB by 2026-08-17. Records carrying `autonomous_judgment` are
# NEVER counted or pruned — see EventLedger._prune_terminal.
LEDGER_TERMINAL_RETENTION = int(os.environ.get("ORA_LEDGER_STATE_RETENTION") or 500)

# Rotated siblings kept per sink. Provisional. Bounding one file while letting
# its archives accumulate forever would just relocate the unbounded growth, and
# there is no clock left to prune them: the retention sweeper's interval was
# removed by G1.10, so rotation time is the only reliable moment to enforce it.
AUDIT_ARCHIVE_KEEP = int(os.environ.get("ORA_RUNTIME_AUDIT_ARCHIVE_KEEP") or 6)


def rotate_if_oversized(path: Path | str, *, limit_mb: float | None = None) -> str | None:
    """Roll an append-only sink aside once it exceeds the size threshold.

    Returns the archive path when a rotation happened, else None. Never
    raises: a failure to rotate must not take down the caller's write — the
    sink growing is strictly less bad than the event being lost.
    """
    limit = (AUDIT_ROTATE_MB if limit_mb is None else limit_mb) * 1024 * 1024
    target = Path(path)
    try:
        if limit <= 0 or not target.is_file() or target.stat().st_size <= limit:
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = target.with_name(f"{target.name}.{stamp}")
        # Path.rename replaces an existing destination silently on POSIX, so
        # two rotations inside the same second would destroy the first
        # archive with no error. Never overwrite evidence.
        suffix = 0
        while archive.exists():
            suffix += 1
            archive = target.with_name(f"{target.name}.{stamp}.{suffix}")
        target.rename(archive)
        _prune_archives(target)
        return str(archive)
    except OSError:
        return None


def _prune_archives(target: Path) -> None:
    """Keep only the newest AUDIT_ARCHIVE_KEEP siblings of one sink.

    Ordered by modification time, not by name. The name carries a one-second
    stamp plus a collision suffix, and pruning frees suffixes for reuse — so a
    name sort can rank a freshly written archive below an older one and delete
    the very archive just created.
    """
    try:
        if AUDIT_ARCHIVE_KEEP <= 0:
            return
        siblings = sorted(
            (p for p in target.parent.glob(f"{target.name}.*") if p.is_file()),
            key=lambda p: (p.stat().st_mtime_ns, p.name),
        )
        for stale in siblings[:max(0, len(siblings) - AUDIT_ARCHIVE_KEEP)]:
            try:
                stale.unlink()
            except OSError:
                pass
    except OSError:
        return


def _root() -> Path:
    return Path(_rp.DATA_DIR_STR) / "runtime-hygiene"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_instant(value: str) -> str:
    """Return one timezone-aware timestamp as a canonical UTC instant."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("deadline must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def instant_timestamp(value: str) -> float:
    return datetime.fromisoformat(normalized_instant(value)).timestamp()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_identity(path: str | Path) -> dict:
    exact = Path(path).expanduser().resolve()
    stat = exact.stat()
    return {
        "path": str(exact),
        "sha256": sha256_file(exact),
        "size": stat.st_size,
    }


def event_identity(event_type: str, subject: dict) -> str:
    body = json.dumps(
        {"event_type": event_type, "subject": subject},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return "evt-" + hashlib.sha256(body).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise


@contextlib.contextmanager
def _exclusive(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def mutation_path_locks(paths: Iterable[str | Path]):
    """Hold deterministic cross-process locks for an exact mutation set."""
    exact = sorted({str(Path(path).expanduser().resolve()) for path in paths})
    locks = [
        _root() / "path-locks" /
        (hashlib.sha256(path.encode("utf-8")).hexdigest() + ".lock")
        for path in exact
    ]
    with contextlib.ExitStack() as stack:
        for lock in locks:
            stack.enter_context(_exclusive(lock))
        yield exact


def subject_digest(subject: dict | None) -> str:
    """Deterministic digest of an event's immutable subject."""
    canonical = json.dumps(subject or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EventLedger:
    """Append-only evidence plus restart-safe current event state."""

    @property
    def state_file(self) -> Path:
        return _root() / "event-state.json"

    @property
    def audit_file(self) -> Path:
        return _root() / "events.jsonl"

    @property
    def lock_file(self) -> Path:
        return _root() / ".event-ledger.lock"

    def _state(self) -> dict:
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("unsupported runtime-hygiene state")
            return value
        except FileNotFoundError:
            return {"schema_version": SCHEMA_VERSION, "events": {}}

    def _append(self, record: dict) -> None:
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        rotate_if_oversized(self.audit_file)
        envelope = {"schema_version": SCHEMA_VERSION, "recorded_at": _now(), **record}
        with open(self.audit_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def claim(self, *, event_id: str, event_type: str, subject: dict) -> tuple[dict, bool]:
        """Persist the immutable event contract before any handler acts."""
        with _PROCESS_LOCK, _exclusive(self.lock_file):
            state = self._state()
            existing = state["events"].get(event_id)
            if existing is not None:
                if (existing.get("event_type") != event_type
                        or existing.get("subject") != subject):
                    raise ValueError("event identity collision")
                return dict(existing), False
            record = {
                "event_id": event_id,
                "event_type": event_type,
                "subject": subject,
                "status": "claimed",
                "claimed_at": _now(),
            }
            state["events"][event_id] = record
            self._prune_terminal(state)
            _atomic_json(self.state_file, state)
            # The claim line carries the whole contract — event type and
            # subject — exactly once. Later lines reference it by digest.
            self._append({"kind": "event_claimed", **record})
            return dict(record), True

    def _prune_terminal(self, state: dict) -> int:
        """Bound the finished records held in the live state map.

        Every claim and transition rewrites this file in full and fsyncs it, so
        history that nothing reads is paid for on each event.

        Records carrying ``autonomous_judgment`` are never pruned, at any age:
        ``completed_mutation_causing`` scans them to recognise Ora's own
        rollback-protected writes when the OS reports them back. Dropping one
        would let a bounded autonomous judgment recurse into another and expand
        its authority beyond the originating write, which is the exact failure
        that join exists to prevent. Non-terminal records are likewise retained
        regardless of age. Everything pruned here remains permanently in the
        append-only audit log.
        """
        events = state.get("events") or {}
        prunable = [
            (record.get("completed_at") or record.get("updated_at")
             or record.get("claimed_at") or "", key)
            for key, record in events.items()
            if record.get("status") in ("completed", "failed")
            and not record.get("autonomous_judgment")
        ]
        if len(prunable) <= LEDGER_TERMINAL_RETENTION:
            return 0
        prunable.sort()
        excess = len(prunable) - LEDGER_TERMINAL_RETENTION
        for _stamp, key in prunable[:excess]:
            events.pop(key, None)
        return excess

    def transition(self, event_id: str, expected: set[str], status: str, **fields) -> dict:
        with _PROCESS_LOCK, _exclusive(self.lock_file):
            state = self._state()
            current = state["events"].get(event_id)
            if current is None:
                raise KeyError(event_id)
            if current.get("status") not in expected:
                raise ValueError(
                    f"event {event_id} is {current.get('status')}, expected {sorted(expected)}"
                )
            updated = {**current, **fields, "status": status, "updated_at": _now()}
            state["events"][event_id] = updated
            _atomic_json(self.state_file, state)
            # Only what this transition contributes. Re-emitting the whole
            # accumulated record repeated the immutable subject, the event
            # type, and every field an earlier transition had already
            # recorded — once per remaining transition. The digest keeps each
            # line joined to its contract without carrying the subject again.
            self._append({
                "kind": f"event_{status}",
                "event_id": event_id,
                "status": status,
                "updated_at": updated["updated_at"],
                "subject_digest": subject_digest(current.get("subject")),
                **fields,
            })
            return dict(updated)

    def get(self, event_id: str) -> dict | None:
        with _PROCESS_LOCK, _exclusive(self.lock_file):
            value = self._state()["events"].get(event_id)
            return dict(value) if value else None

    def append_evidence(self, event_id: str, kind: str, **fields) -> None:
        with _PROCESS_LOCK, _exclusive(self.lock_file):
            if event_id not in self._state()["events"]:
                raise KeyError(event_id)
            self._append({"kind": kind, "event_id": event_id, **fields})

    def completed_mutation_causing(self, subject: dict) -> str | None:
        """Return the completed event that produced this exact after-identity.

        OS notifications include Ora's own rollback-protected writes. Without
        this authenticated join, one bounded autonomous judgment could recurse
        into another and expand its authority beyond the originating write.
        """
        expected_path = str(subject.get("path") or "")
        expected_sha = subject.get("sha256")
        if not self.state_file.is_file():
            return None
        with _PROCESS_LOCK, _exclusive(self.lock_file):
            events = self._state().get("events", {})
            for event_id, record in events.items():
                if record.get("status") != "completed":
                    continue
                if not record.get("autonomous_judgment"):
                    continue
                for after in record.get("after", []):
                    if (after.get("exists") is True
                            and after.get("path") == expected_path
                            and after.get("sha256") == expected_sha):
                        return event_id
        return None


@dataclass
class Snapshot:
    path: str
    existed: bool
    before_sha256: str | None
    backup: str | None


class MutationTransaction:
    """Persisted rollback material for an exact event mutation set."""

    def __init__(self, ledger: EventLedger, event_id: str,
                 paths: Iterable[str | Path], *,
                 expected_identities: Iterable[dict] | None = None):
        self.ledger = ledger
        self.event_id = event_id
        self.paths = sorted({str(Path(path).expanduser().resolve()) for path in paths})
        self.directory = _root() / "rollback" / event_id
        self.manifest = self.directory / "manifest.json"
        self.snapshots: list[Snapshot] = []
        self.expected_identities = {
            str(Path(value["path"]).expanduser().resolve()): dict(value)
            for value in (expected_identities or [])
        }
        self._committed = False

    def prepare(self) -> None:
        for raw, expected in self.expected_identities.items():
            path = Path(raw)
            try:
                current = artifact_identity(path)
            except FileNotFoundError as exc:
                raise RuntimeError(f"judgment input drifted before mutation: {path}") from exc
            if current != expected:
                raise RuntimeError(f"judgment input drifted before mutation: {path}")
        self.directory.mkdir(parents=True, exist_ok=False)
        for index, raw in enumerate(self.paths):
            path = Path(raw)
            if path.exists():
                backup = self.directory / f"{index:04d}.before"
                shutil.copy2(path, backup)
                self.snapshots.append(Snapshot(raw, True, sha256_file(path), str(backup)))
            else:
                self.snapshots.append(Snapshot(raw, False, None, None))
        _atomic_json(self.manifest, {
            "schema_version": SCHEMA_VERSION,
            "event_id": self.event_id,
            "prepared_at": _now(),
            "snapshots": [snapshot.__dict__ for snapshot in self.snapshots],
        })
        self.ledger.transition(
            self.event_id, {"claimed"}, "prepared",
            rollback_manifest=str(self.manifest),
        )

    def __enter__(self):
        self.prepare()
        self.ledger.transition(self.event_id, {"prepared"}, "applying")
        return self

    def commit(self, **fields) -> dict:
        after = []
        for snapshot in self.snapshots:
            path = Path(snapshot.path)
            after.append({
                "path": snapshot.path,
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.exists() else None,
            })
        result = self.ledger.transition(
            self.event_id, {"applying"}, "completed",
            after=after, completed_at=_now(), **fields,
        )
        self._committed = True
        return result

    def rollback(self, *, reason: str, final_status: str = "failed") -> None:
        for snapshot in reversed(self.snapshots):
            path = Path(snapshot.path)
            if snapshot.existed:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(snapshot.backup), path)
            elif path.exists():
                path.unlink()
        current = self.ledger.get(self.event_id)
        if current and current.get("status") in {"prepared", "applying"}:
            self.ledger.transition(
                self.event_id, {current["status"]}, final_status,
                error=reason, rolled_back_at=_now(),
            )

    def __exit__(self, exc_type, exc, _tb):
        if exc is not None and not self._committed:
            self.rollback(reason=str(exc))
        return False


def restore_incomplete_events(ledger: EventLedger | None = None) -> list[str]:
    """Roll back events interrupted after snapshot but before commit."""
    ledger = ledger or EventLedger()
    state = ledger._state()
    restored: list[str] = []
    for event_id, record in state.get("events", {}).items():
        if record.get("status") == "claimed":
            ledger.transition(
                event_id, {"claimed"}, "failed",
                error="restart recovery: interrupted before mutation",
                mutation_count=0,
            )
            restored.append(event_id)
            continue
        if record.get("status") not in {"prepared", "applying"}:
            continue
        manifest_path = record.get("rollback_manifest")
        if not manifest_path:
            ledger.transition(event_id, {record["status"]}, "failed",
                              error="interrupted before rollback material was bound")
            continue
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        tx = MutationTransaction(ledger, event_id, [])
        tx.snapshots = [Snapshot(**value) for value in manifest["snapshots"]]
        tx.rollback(reason="restart recovery of incomplete mutation")
        restored.append(event_id)
    return restored


def rollback_completed_event(event_id: str, ledger: EventLedger | None = None) -> dict:
    """Restore a completed event only while every after-identity still matches.

    The drift check prevents a rollback from erasing later user work. Rollback
    itself is an authenticated event-state transition and remains in the
    append-only audit.
    """
    ledger = ledger or EventLedger()
    record = ledger.get(event_id)
    if record is None or record.get("status") != "completed":
        raise ValueError("only a completed event can be rolled back")
    for identity in record.get("after", []):
        path = Path(identity["path"])
        if path.exists() != bool(identity["exists"]):
            raise ValueError(f"rollback refused after artifact drift: {path}")
        if path.exists() and sha256_file(path) != identity["sha256"]:
            raise ValueError(f"rollback refused after artifact drift: {path}")
    manifest_path = record.get("rollback_manifest")
    if not manifest_path:
        raise ValueError("completed event has no rollback manifest")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    snapshots = [Snapshot(**value) for value in manifest["snapshots"]]
    for snapshot in reversed(snapshots):
        path = Path(snapshot.path)
        if snapshot.existed:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(snapshot.backup), path)
        elif path.exists():
            path.unlink()
    return ledger.transition(
        event_id, {"completed"}, "rolled_back", rolled_back_at=_now(),
        rollback_reason="explicit authenticated rollback",
    )


class DeadlineQueue:
    """Persisted one-shot deadlines; no periodic discovery loop."""

    def __init__(self, storage_root: str | Path | None = None):
        self._condition = threading.Condition()
        self._storage_root = (Path(storage_root).expanduser().resolve()
                              if storage_root is not None else None)

    @property
    def storage_root(self) -> Path:
        return self._storage_root or _root()

    @property
    def path(self) -> Path:
        return self.storage_root / "deadlines.json"

    @property
    def lock_path(self) -> Path:
        return self.storage_root / ".deadlines.lock"

    @property
    def audit_path(self) -> Path:
        return self.storage_root / "deadline-events.jsonl"

    def _append(self, kind: str, record: dict) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        rotate_if_oversized(self.audit_path)
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "recorded_at": _now(),
            **record,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("unsupported deadline queue")
            return value
        except FileNotFoundError:
            return {"schema_version": SCHEMA_VERSION, "deadlines": {}}

    def put(self, key: str, due_at: str, event_type: str, payload: dict) -> dict:
        due = normalized_instant(due_at)
        record = {
            "key": key, "due_at": due, "event_type": event_type,
            "payload": payload, "status": "pending",
        }
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            state = self._load()
            existing = state["deadlines"].get(key)
            if existing is not None:
                same_instant = (
                    instant_timestamp(str(existing.get("due_at")))
                    == instant_timestamp(record["due_at"])
                )
                if (not same_instant
                        or existing.get("key") != key
                        or existing.get("event_type") != event_type
                        or existing.get("payload") != payload):
                    raise ValueError("deadline key already binds a different contract")
                return dict(existing)
            state["deadlines"][key] = record
            _atomic_json(self.path, state)
            self._append("deadline_registered", record)
        with self._condition:
            self._condition.notify_all()
        return record

    def wake(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def next_due(self) -> dict | None:
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            pending = [value for value in self._load()["deadlines"].values()
                       if value.get("status") == "pending"]
        return min(
            pending,
            key=lambda value: (instant_timestamp(value["due_at"]), value["key"]),
        ) if pending else None

    def get(self, key: str) -> dict | None:
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            value = self._load()["deadlines"].get(key)
            return dict(value) if value is not None else None

    def cancel(self, key: str, *, reason: str) -> dict | None:
        """Cancel one pending contract under queue lock, preserving evidence."""
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            state = self._load()
            current = state["deadlines"].get(key)
            if current is None:
                return None
            if current.get("status") != "pending":
                return dict(current)
            current = {
                **current, "status": "cancelled", "cancelled_at": _now(),
                "cancellation_reason": reason,
            }
            state["deadlines"][key] = current
            _atomic_json(self.path, state)
            self._append("deadline_cancelled", current)
        with self._condition:
            self._condition.notify_all()
        return dict(current)

    def run(self, handlers: dict[str, Callable[[dict], None]], stop: threading.Event) -> None:
        """Sleep to the exact next due time; wake only on queue changes."""
        while not stop.is_set():
            next_record = self.next_due()
            if next_record is None:
                if stop.is_set():
                    return
                with self._condition:
                    self._condition.wait()
                continue
            due = instant_timestamp(next_record["due_at"])
            delay = max(0.0, due - time.time())
            if delay:
                with self._condition:
                    self._condition.wait(timeout=delay)
                # A newly inserted earlier deadline changes the next record;
                # re-read rather than dispatching stale queue state.
                if self.next_due() != next_record:
                    continue
                # The wait also returns on any queue change that leaves this
                # record at the head — every finalized trace registers one.
                # Without this check the head deadline fires the moment an
                # unrelated deadline is inserted, which walked the daily-note
                # chain days into the future in a single burst on 2026-08-11.
                # Time is the cause here: re-sleep until it has actually come.
                if time.time() < due:
                    continue
            if stop.is_set():
                return
            receipt = None
            error = None
            handler = handlers.get(next_record["event_type"])
            if handler is None:
                error = f"no deadline handler for {next_record['event_type']}"
            else:
                try:
                    receipt = handler(dict(next_record["payload"]))
                except Exception as exc:
                    error = str(exc)
            with _PROCESS_LOCK, _exclusive(self.lock_path):
                state = self._load()
                current = state["deadlines"].get(next_record["key"])
                if current == next_record:
                    current["status"] = "failed" if error else "completed"
                    current["completed_at"] = _now()
                    if error:
                        current["error"] = error
                    elif receipt is not None:
                        current["receipt"] = receipt
                    _atomic_json(self.path, state)
                    self._append(
                        "deadline_failed" if error else "deadline_completed",
                        current,
                    )


class RetentionIntentStore:
    """Write-ahead retention contracts recovered once at runtime startup."""

    def __init__(self, storage_root: str | Path | None = None):
        self.storage_root = (Path(storage_root).expanduser().resolve()
                             if storage_root is not None else _root())

    @property
    def path(self) -> Path:
        return self.storage_root / "retention-intents.json"

    @property
    def audit_path(self) -> Path:
        return self.storage_root / "retention-intent-events.jsonl"

    @property
    def lock_path(self) -> Path:
        return self.storage_root / ".retention-intents.lock"

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("unsupported retention-intent store")
            return value
        except FileNotFoundError:
            return {"schema_version": SCHEMA_VERSION, "intents": {}}

    def _append(self, kind: str, record: dict) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": SCHEMA_VERSION, "kind": kind,
            "recorded_at": _now(), **record,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def put(self, *, key: str, due_at: str, event_type: str,
            payload: dict, guard: dict) -> dict:
        record = {
            "key": key, "due_at": normalized_instant(due_at),
            "event_type": event_type, "payload": payload,
            "guard": guard, "status": "pending", "created_at": _now(),
        }
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            state = self._load()
            existing = state["intents"].get(key)
            if existing is not None:
                immutable = ("key", "due_at", "event_type", "payload", "guard")
                if any(existing.get(field) != record.get(field) for field in immutable):
                    raise ValueError("retention intent key collision")
                return dict(existing)
            state["intents"][key] = record
            _atomic_json(self.path, state)
            self._append("retention_intent_persisted", record)
            return dict(record)

    def pending(self) -> list[dict]:
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            return [dict(value) for value in self._load()["intents"].values()
                    if value.get("status") == "pending"]

    def get(self, key: str) -> dict | None:
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            value = self._load()["intents"].get(key)
            return dict(value) if value is not None else None

    def mark_registered(self, key: str, deadline: dict) -> dict:
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            state = self._load()
            current = state["intents"].get(key)
            if current is None:
                raise KeyError(key)
            if current.get("status") == "registered":
                return dict(current)
            if current.get("status") != "pending":
                raise ValueError("retention intent is not pending")
            updated = {
                **current, "status": "registered", "registered_at": _now(),
                "deadline_receipt": deadline,
            }
            state["intents"][key] = updated
            _atomic_json(self.path, state)
            self._append("retention_intent_registered", updated)
            return dict(updated)

    def record_failure(self, key: str, error: str) -> None:
        with _PROCESS_LOCK, _exclusive(self.lock_path):
            state = self._load()
            current = state["intents"].get(key)
            if current is None or current.get("status") != "pending":
                return
            current = {**current, "last_error": error, "last_failed_at": _now()}
            state["intents"][key] = current
            _atomic_json(self.path, state)
            self._append("retention_intent_registration_failed", current)


def retention_intent_store(data_dir: str | Path | None = None) -> RetentionIntentStore:
    storage = ((Path(data_dir).expanduser().resolve() / "runtime-hygiene")
               if data_dir is not None else _root().resolve())
    return RetentionIntentStore(storage)


def _retention_guard_matches(guard: dict) -> bool:
    try:
        value = json.loads(Path(guard["manifest_path"]).read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False
    if value.get("finalized_at") != guard.get("finalized_at"):
        return False
    required = guard.get("retention_state")
    if required == "finalized":
        return True
    current = value.get("retention_state", "default")
    return current == required


def register_retention_intent(key: str, *,
                              store: RetentionIntentStore | None = None,
                              queue: DeadlineQueue | None = None) -> dict:
    store = store or retention_intent_store()
    queue = queue or deadline_queue()
    record = store.get(key)
    if record is None:
        raise KeyError(key)
    if record.get("status") == "registered":
        return record
    if record.get("status") != "pending":
        raise ValueError("retention intent is not pending")
    if not _retention_guard_matches(record["guard"]):
        raise RuntimeError("retention intent guard does not match lifecycle state")
    try:
        deadline = queue.put(
            record["key"], record["due_at"], record["event_type"],
            record["payload"],
        )
        return store.mark_registered(key, deadline)
    except Exception as exc:
        store.record_failure(key, str(exc))
        raise


def recover_retention_intents(*, store: RetentionIntentStore | None = None,
                              queue: DeadlineQueue | None = None) -> dict:
    """Replay exact pending intents once on startup; never scan trace trees."""
    store = store or retention_intent_store()
    queue = queue or deadline_queue()
    report = {"registered": [], "failed": []}
    for record in store.pending():
        try:
            register_retention_intent(record["key"], store=store, queue=queue)
            report["registered"].append(record["key"])
        except Exception as exc:
            report["failed"].append({"key": record["key"], "error": str(exc)})
    return report


_DEADLINE_QUEUES: dict[str, DeadlineQueue] = {}
_DEADLINE_QUEUES_LOCK = threading.Lock()


def deadline_queue(data_dir: str | Path | None = None) -> DeadlineQueue:
    """Return the process-shared queue for one canonical data root.

    Callers that are importable both as ``pipeline_trace`` and
    ``orchestrator.pipeline_trace`` pass their own resolved data directory.
    Canonical path interning ensures both contexts still wake the daemon's one
    blocking queue rather than writing an unnoticed sibling queue object.
    """
    storage = ((Path(data_dir).expanduser().resolve() / "runtime-hygiene")
               if data_dir is not None else _root().resolve())
    key = str(storage)
    with _DEADLINE_QUEUES_LOCK:
        queue = _DEADLINE_QUEUES.get(key)
        if queue is None:
            queue = DeadlineQueue(storage)
            _DEADLINE_QUEUES[key] = queue
        return queue
