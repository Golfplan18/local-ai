"""Generic Phase 1.4 runtime for governed Process Runs.

The runtime is deliberately mechanical.  It validates and persists the four
Phase 1.3 object families, enforces an already-approved plan and authority
contract, records observations, and applies an accepted transition directive.
It never calls a model, diagnoses a failure class, selects a cognitive route, or
contains a domain-specific controller.

Segment, attempt, controlled-probe contract/stop/attempt, checkpoint,
infrastructure-retry, invocation, and recovery state are event records.  They
are not additional persisted object families.  The current Process Run is a
materialized fold over those append-only records.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import process_contracts as _contracts
except ImportError:  # pragma: no cover
    from orchestrator import process_contracts as _contracts

try:
    import runtime_paths as _runtime_paths
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _runtime_paths


PROCESS_RUNS_DIR = os.path.join(
    os.environ.get("ORA_HOME", str(Path.home() / "ora")),
    "data",
    "process-runs",
)
PROCESS_RUNS_ENV = "ORA_PROCESS_RUNS_DIR"

FAILURE_CLASS_DIRECTIVES = {
    "execution": "REVISE",
    "plan": "REPLAN",
    "definition": "REDEFINE",
    "authority": "ESCALATE",
    "external": "BLOCKED",
}

DIRECTIVE_SOURCE_STATES = {
    "PROCEED": {"ready", "running", "pending", "redefining", "waiting_for_authority"},
    "ACCEPT": {"running"},
    "REVISE": {"running"},
    "REPLAN": {"running"},
    "REDEFINE": {"running", "pending"},
    "ESCALATE": {"ready", "running", "pending", "redefining"},
    "BLOCKED": {
        "created",
        "awaiting_plan_approval",
        "ready",
        "running",
        "pending",
        "redefining",
        "waiting_for_authority",
    },
}

INITIAL_RUN_STATES = frozenset({"created", "awaiting_plan_approval", "ready"})
TERMINAL_RUN_STATES = frozenset({"completed", "blocked", "cancelled"})

# Runtime-authoritative records are emitted only by their dedicated validated
# methods.  The public generic event surface may persist observations, but it
# must never be able to mint state, authority, review, retry, recovery, lineage,
# or invocation facts consumed by the runtime.
RESERVED_RUNTIME_EVENT_TYPES = frozenset({
    "run_created",
    "run_ready",
    "run_started",
    "run_paused",
    "run_resumed",
    "action_completed",
    "segment_started",
    "attempt_started",
    "attempt_completed",
    "infrastructure_attempt",
    "artifact_recorded",
    "final_review_completed",
    "checkpoint_created",
    "controlled_probe_contract_persisted",
    "controlled_probe_stop_state_recorded",
    "controlled_probe_attempt_started",
    "controlled_probe_attempt_completed",
    "controlled_probe_withheld",
    "process_invoked",
    "child_return_received",
    "process_returned",
})

_RESERVED_RUNTIME_EVENT_PREFIXES = (
    "action_",
    "artifact_",
    "attempt_",
    "checkpoint_",
    "child_",
    "controlled_probe_",
    "infrastructure_",
    "invocation_",
    "lifecycle_",
    "process_",
    "recovery_",
    "return_",
    "review_",
    "run_",
    "segment_",
)

INFRASTRUCTURE_OUTCOMES = (
    "success",
    "retryable_failure",
    "terminal_failure",
)

DEFAULT_CORRECTION_POLICY = {
    "max_attempts": 3,
    "progress_evidence_required": True,
    "repeated_defect_limit": 3,
    "allowed_directives": ["REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
    "no_progress_directives": ["REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
}

_PROCESS_LOCK = threading.RLock()


class GovernedRuntimeError(RuntimeError):
    """Base class for a refused runtime operation."""


class RunNotFoundError(GovernedRuntimeError):
    pass


class RunConflictError(GovernedRuntimeError):
    pass


class AuthorityDeniedError(GovernedRuntimeError):
    pass


class CorrectionDecisionRequired(GovernedRuntimeError):
    pass


class RecoveryBlockedError(GovernedRuntimeError):
    pass


class FinalReviewRequired(GovernedRuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _storage_key(identifier: str) -> str:
    digest = hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()[:24]
    return f"id-{digest}"


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _digest_text(body)


def _exact_digest(value: Any, label: str) -> str:
    result = str(value or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", result):
        raise GovernedRuntimeError(f"{label} must be an exact sha256 digest")
    return result


def _is_reserved_runtime_event_type(event_type: str) -> bool:
    normalized = str(event_type)
    return (
        normalized in RESERVED_RUNTIME_EVENT_TYPES
        or normalized.startswith(_RESERVED_RUNTIME_EVENT_PREFIXES)
    )


def _require_json(value: Any, label: str) -> None:
    try:
        json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise GovernedRuntimeError(f"{label} must be JSON-serializable: {exc}") from exc


def _safe_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        raw = Path(explicit)
    elif os.environ.get(PROCESS_RUNS_ENV):
        raw = Path(os.environ[PROCESS_RUNS_ENV])
    else:
        raw = Path(_runtime_paths.sandboxed_file(PROCESS_RUNS_DIR))
    raw = Path(os.path.abspath(os.path.expanduser(str(raw))))
    if raw.exists() and raw.is_symlink():
        raise GovernedRuntimeError(f"process-run root must not be a symlink: {raw}")
    raw.mkdir(parents=True, exist_ok=True)
    if not raw.is_dir():
        raise GovernedRuntimeError(f"process-run root is not a directory: {raw}")
    return raw


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    _require_json(payload, str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise GovernedRuntimeError(f"refusing to replace symlink: {path}")
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise RunNotFoundError(f"runtime object not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernedRuntimeError(f"cannot read runtime object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GovernedRuntimeError(f"runtime object must be a JSON object: {path}")
    return value


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    _require_json(payload, str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise GovernedRuntimeError(f"refusing to append through symlink: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        line = json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n"
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if not path.is_file() or path.is_symlink():
        raise GovernedRuntimeError(f"invalid event store: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GovernedRuntimeError(
                    f"invalid event record {path}:{number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise GovernedRuntimeError(f"event record {path}:{number} is not an object")
            _contracts.validate_event_transition_record(value)
            records.append(value)
    sequences = [record["sequence"] for record in records]
    if sequences != list(range(1, len(sequences) + 1)):
        raise GovernedRuntimeError(f"event sequence is not contiguous: {path}")
    record_ids = [record["record_id"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise GovernedRuntimeError(f"event record_id values are not unique: {path}")
    return records


@contextlib.contextmanager
def _locked() -> Any:
    with _PROCESS_LOCK:
        yield


def directive_for_failure_class(failure_class: str) -> str:
    """Map an already-judged failure class to its declared directive.

    Process Coherence owns the judgment that a failure is execution-, plan-,
    definition-, authority-, or external-level.  This function only applies
    the fixed policy table.
    """

    try:
        return FAILURE_CLASS_DIRECTIVES[str(failure_class)]
    except KeyError as exc:
        allowed = ", ".join(FAILURE_CLASS_DIRECTIVES)
        raise GovernedRuntimeError(
            f"failure_class must be one of {allowed}; got {failure_class!r}"
        ) from exc


def correction_policy_defaults(
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return explicit correction defaults with bounded, validated overrides.

    The returned policy is configuration material for a Process Run; the
    runtime never starts attempts merely because a ceiling is available.
    """

    policy = copy.deepcopy(DEFAULT_CORRECTION_POLICY)
    supplied = dict(overrides or {})
    unknown = sorted(set(supplied) - set(policy))
    if unknown:
        raise GovernedRuntimeError(
            f"unknown correction default(s): {', '.join(unknown)}"
        )
    policy.update(copy.deepcopy(supplied))
    if not isinstance(policy["max_attempts"], int) or policy["max_attempts"] < 1:
        raise GovernedRuntimeError("max_attempts must be an integer >= 1")
    if not isinstance(policy["repeated_defect_limit"], int) or policy["repeated_defect_limit"] < 1:
        raise GovernedRuntimeError("repeated_defect_limit must be an integer >= 1")
    if not isinstance(policy["progress_evidence_required"], bool):
        raise GovernedRuntimeError("progress_evidence_required must be boolean")
    correction_directives = {"REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"}
    for field in ("allowed_directives", "no_progress_directives"):
        values = policy[field]
        if not isinstance(values, list) or not values or any(
            value not in correction_directives for value in values
        ):
            raise GovernedRuntimeError(
                f"{field} must be a nonempty list of correction directives"
            )
    if not set(policy["no_progress_directives"]).issubset(policy["allowed_directives"]):
        raise GovernedRuntimeError("no_progress_directives must be allowed directives")
    return policy


class GovernedProcessRuntime:
    """Persistent, domain-general Process Run mechanics."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        *,
        now: Callable[[], str] | None = None,
    ):
        self.root = _safe_root(root)
        self._now = now or _utc_now

    # ------------------------------------------------------------------ paths
    def _run_dir(self, run_id: str, *, create: bool = False) -> Path:
        path = self.root / _storage_key(run_id)
        if path.exists() and path.is_symlink():
            raise GovernedRuntimeError(f"run directory must not be a symlink: {path}")
        if create:
            path.mkdir(parents=False, exist_ok=True)
        return path

    def _run_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "run.json"

    def _definition_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "definition.json"

    def _events_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "records.jsonl"

    def _artifact_path(self, run_id: str, artifact_id: str) -> Path:
        directory = self._run_dir(run_id) / "artifacts"
        if directory.exists() and directory.is_symlink():
            raise GovernedRuntimeError(f"artifact directory must not be a symlink: {directory}")
        return directory / f"{_storage_key(artifact_id)}.json"

    # ------------------------------------------------------------ root objects
    def create_run(self, definition: Mapping[str, Any], run: Mapping[str, Any]) -> dict[str, Any]:
        definition_copy = _contracts.validate_process_definition(definition)
        run_copy = _contracts.validate_process_run(run)
        self._validate_definition_binding(definition_copy, run_copy)
        correction = run_copy["contracts"]["correction_loop"]
        correction_policy_defaults({
            key: correction[key] for key in DEFAULT_CORRECTION_POLICY
        })
        if run_copy["artifact_ids"]:
            raise GovernedRuntimeError(
                "a new Process Run must start with no artifact_ids; record each input "
                "Artifact through the authority and lineage boundary after creation"
            )
        if run_copy["state"] not in INITIAL_RUN_STATES:
            raise GovernedRuntimeError(
                "a new Process Run must start in created, awaiting_plan_approval, "
                "or ready state; lifecycle advancement requires persisted events"
            )
        entry_node_id = definition_copy["graph"]["entry_node_id"]
        if run_copy["current_node_id"] != entry_node_id:
            raise GovernedRuntimeError(
                "a new Process Run must be positioned at its graph entry"
            )
        if int(run_copy["last_sequence"]) != 0:
            raise GovernedRuntimeError(
                "a new Process Run must start at sequence zero"
            )
        if int(run_copy["contracts"]["correction_loop"]["attempt"]) != 0:
            raise GovernedRuntimeError(
                "a new Process Run must start before its first correction attempt"
            )
        run_id = run_copy["run_id"]
        with _locked():
            run_dir = self._run_dir(run_id, create=True)
            if (run_dir / "run.json").exists() or (run_dir / "definition.json").exists():
                raise RunConflictError(f"Process Run already exists: {run_id}")
            _atomic_json(run_dir / "definition.json", definition_copy)
            _atomic_json(run_dir / "run.json", run_copy)
            self._append_event_locked(
                run_copy,
                "run_created",
                {
                    "entrypoint": run_copy["entrypoint"],
                    "current_node_id": run_copy["current_node_id"],
                    "definition_digest": run_copy["definition_ref"]["digest"],
                },
                node_id=run_copy["current_node_id"],
                runtime_authoritative=True,
            )
            return copy.deepcopy(run_copy)

    @staticmethod
    def _require_mutable_run(run: Mapping[str, Any], operation: str) -> None:
        if run["state"] in TERMINAL_RUN_STATES:
            raise RunConflictError(
                f"terminal Process Run is immutable; cannot {operation}"
            )

    def load_run(self, run_id: str) -> dict[str, Any]:
        with _locked():
            run = _contracts.validate_process_run(_read_json(self._run_path(run_id)))
            if run["run_id"] != run_id:
                raise GovernedRuntimeError("Process Run storage key resolved to a different run_id")
            records = _read_jsonl(self._events_path(run_id))
            for record in records:
                if record["run_id"] != run_id or record["definition_ref"] != run["definition_ref"]:
                    raise GovernedRuntimeError(
                        "event record identity does not match its Process Run store"
                    )
            record_sequence = records[-1]["sequence"] if records else 0
            if int(run["last_sequence"]) < record_sequence:
                run = self._materialize_records_locked(run, records)
                _contracts.validate_process_run(run)
                _atomic_json(self._run_path(run_id), run)
            elif int(run["last_sequence"]) > record_sequence:
                raise GovernedRuntimeError(
                    f"run/event sequence mismatch for {run_id}: "
                    f"run={run['last_sequence']} records={record_sequence}"
                )
            return run

    def _materialize_records_locked(
        self,
        run: dict[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Complete an interrupted event→Process-Run materialization.

        The append-only record is written before the materialized Run. If a
        process stops between those writes, replaying only records after the
        Run's last committed sequence restores state without replaying any
        mutation or external effect.
        """

        materialized = copy.deepcopy(run)
        for record in records:
            if int(record["sequence"]) <= int(materialized["last_sequence"]):
                continue
            if record["run_id"] != materialized["run_id"]:
                raise GovernedRuntimeError("event record run_id does not match its store")
            if record["definition_ref"] != materialized["definition_ref"]:
                raise GovernedRuntimeError("event record definition identity does not match its Run")
            if record["record_type"] == "transition":
                transition = record["transition"]
                materialized["state"] = transition["to_state"]
                materialized["current_node_id"] = transition["target_node_id"]
                if transition["directive"] in ("REPLAN", "REDEFINE"):
                    materialized["contracts"]["correction_loop"]["attempt"] = 0
            else:
                event = record["event"]
                details = event["details"]
                event_type = event["event_type"]
                if event_type == "attempt_started":
                    materialized["contracts"]["correction_loop"]["attempt"] = int(
                        details["attempt"]
                    )
                elif event_type == "artifact_recorded":
                    artifact_id = details["artifact_id"]
                    if artifact_id not in materialized["artifact_ids"]:
                        materialized["artifact_ids"].append(artifact_id)
                elif event_type == "checkpoint_created":
                    materialized["contracts"]["continuation"]["checkpoint_id"] = details[
                        "checkpoint_id"
                    ]
                    materialized["contracts"]["continuation"]["resume_node_id"] = details[
                        "resume_node_id"
                    ]
                elif event_type == "run_paused":
                    materialized["state"] = "pending"
                elif event_type == "run_ready":
                    materialized["state"] = "ready"
                elif event_type == "run_started":
                    materialized["state"] = "running"
                elif event_type == "run_resumed":
                    materialized["state"] = "running"
                    materialized["current_node_id"] = details["resume_node_id"]
                elif event_type == "process_invoked":
                    child_ref = details["child_definition_ref"]
                    if child_ref not in materialized["relationships"]["invoked_definition_refs"]:
                        materialized["relationships"]["invoked_definition_refs"].append(child_ref)
                    child_ids = materialized["contracts"]["continuation"]["child_run_ids"]
                    if details["child_run_id"] not in child_ids:
                        child_ids.append(details["child_run_id"])
                    materialized["state"] = "pending"
                elif event_type == "child_return_received":
                    materialized["state"] = "running"
                    materialized["current_node_id"] = details["return_node_id"]
            materialized["last_sequence"] = int(record["sequence"])
            materialized["updated_at"] = record["recorded_at"]
        return materialized

    def load_definition(self, run_id: str) -> dict[str, Any]:
        with _locked():
            return _contracts.validate_process_definition(_read_json(self._definition_path(run_id)))

    def load_records(self, run_id: str) -> list[dict[str, Any]]:
        with _locked():
            if not self._run_path(run_id).is_file():
                raise RunNotFoundError(f"Process Run not found: {run_id}")
            return copy.deepcopy(_read_jsonl(self._events_path(run_id)))

    def load_artifact(self, run_id: str, artifact_id: str) -> dict[str, Any]:
        with _locked():
            artifact = _contracts.validate_artifact(
                _read_json(self._artifact_path(run_id, artifact_id))
            )
            if artifact["artifact_id"] != artifact_id:
                raise GovernedRuntimeError(
                    "Artifact storage key resolved to a different artifact_id"
                )
            recorded_digest = None
            for record in reversed(_read_jsonl(self._events_path(run_id))):
                event = record.get("event") or {}
                details = event.get("details") or {}
                if (
                    event.get("event_type") == "artifact_recorded"
                    and details.get("artifact_id") == artifact_id
                ):
                    recorded_digest = details.get("identity_digest")
                    break
            if recorded_digest is None:
                raise GovernedRuntimeError(
                    f"Artifact has no committed lineage record: {artifact_id}"
                )
            if artifact["identity"]["digest"] != recorded_digest:
                raise GovernedRuntimeError(
                    f"Artifact identity differs from its latest committed record: {artifact_id}"
                )
            return artifact

    def _validate_definition_binding(self, definition: Mapping[str, Any], run: Mapping[str, Any]) -> None:
        expected_ref = {
            "definition_id": definition["definition_id"],
            "version": definition["version"],
            "digest": definition["digest"],
        }
        if run["definition_ref"] != expected_ref:
            raise GovernedRuntimeError("Process Run must bind the exact Process Definition identity")
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        node_refs = {run["current_node_id"], run["contracts"]["continuation"]["resume_node_id"]}
        node_refs.update(run["contracts"]["approved_plan"]["approved_node_ids"])
        for judgment in run["contracts"]["bounded_judgment"]:
            node_refs.add(judgment["node_id"])
            node_refs.add(judgment["return_node_id"])
        unknown = sorted(node_refs - set(nodes))
        if unknown:
            raise GovernedRuntimeError(
                f"Run contracts reference node(s) absent from the definition: {', '.join(unknown)}"
            )

    # --------------------------------------------------------------- records
    def _event_record(
        self,
        run: Mapping[str, Any],
        event_type: str,
        details: Mapping[str, Any],
        *,
        node_id: str,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        artifact_ids: Sequence[str] = (),
        record_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
            "object_family": "event_transition_record",
            "record_id": record_id or f"event-{uuid.uuid4().hex}",
            "run_id": run["run_id"],
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "sequence": int(run["last_sequence"]) + 1,
            "recorded_at": self._now(),
            "node_id": node_id,
            "record_type": "event",
            "event": {"event_type": event_type, "details": copy.deepcopy(dict(details))},
            "evidence_refs": copy.deepcopy(list(evidence_refs)),
            "artifact_ids": list(artifact_ids),
        }

    def _append_event_locked(
        self,
        run: dict[str, Any],
        event_type: str,
        details: Mapping[str, Any],
        *,
        node_id: str,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        artifact_ids: Sequence[str] = (),
        record_id: str | None = None,
        allow_terminal_metadata: bool = False,
        runtime_authoritative: bool = False,
    ) -> dict[str, Any]:
        reserved = _is_reserved_runtime_event_type(event_type)
        if runtime_authoritative:
            if event_type not in RESERVED_RUNTIME_EVENT_TYPES:
                raise GovernedRuntimeError(
                    f"runtime event type is not registered: {event_type!r}"
                )
        elif reserved:
            raise AuthorityDeniedError(
                f"runtime-authoritative event type requires its validated method: "
                f"{event_type!r}"
            )
        if allow_terminal_metadata:
            if not runtime_authoritative or event_type != "process_returned":
                raise GovernedRuntimeError(
                    "only a deterministic process_returned record is safe terminal metadata"
                )
        else:
            self._require_mutable_run(run, f"record {event_type}")
        record = self._event_record(
            run,
            event_type,
            details,
            node_id=node_id,
            evidence_refs=evidence_refs,
            artifact_ids=artifact_ids,
            record_id=record_id,
        )
        _contracts.validate_event_transition_record(record)
        _append_jsonl(self._events_path(run["run_id"]), record)
        run["last_sequence"] = record["sequence"]
        run["updated_at"] = record["recorded_at"]
        _contracts.validate_process_run(run)
        _atomic_json(self._run_path(run["run_id"]), run)
        return record

    def _record_runtime_event(
        self,
        run_id: str,
        event_type: str,
        details: Mapping[str, Any],
        *,
        node_id: str | None = None,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        artifact_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Persist one event emitted by its dedicated validated method."""

        if event_type not in RESERVED_RUNTIME_EVENT_TYPES:
            raise GovernedRuntimeError(
                f"internal runtime event type is not registered: {event_type!r}"
            )
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            target = node_id or run["current_node_id"]
            if target not in {node["node_id"] for node in definition["graph"]["nodes"]}:
                raise GovernedRuntimeError(f"event node is not in the Process Definition: {target}")
            return self._append_event_locked(
                run,
                event_type,
                details,
                node_id=target,
                evidence_refs=evidence_refs,
                artifact_ids=artifact_ids,
                runtime_authoritative=True,
            )

    def record_event(
        self,
        run_id: str,
        event_type: str,
        details: Mapping[str, Any],
        *,
        node_id: str | None = None,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        artifact_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Persist a non-authoritative observation event.

        Runtime-consumed event families are reserved for dedicated methods
        such as ``record_final_review``, ``begin_attempt``, and
        ``create_checkpoint``.  Generic observations are append-only evidence;
        the Run materializer and transition/correction policies never consume
        them as authority-bearing facts.
        """

        if _is_reserved_runtime_event_type(event_type):
            raise AuthorityDeniedError(
                f"runtime-authoritative event type is reserved for its validated method: "
                f"{event_type!r}"
            )
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            target = node_id or run["current_node_id"]
            if target not in {node["node_id"] for node in definition["graph"]["nodes"]}:
                raise GovernedRuntimeError(f"event node is not in the Process Definition: {target}")
            return self._append_event_locked(
                run,
                event_type,
                details,
                node_id=target,
                evidence_refs=evidence_refs,
                artifact_ids=artifact_ids,
            )

    def mark_run_ready(self, run_id: str, *, reason: str) -> dict[str, Any]:
        """Persist approval/preparation before a created Run becomes startable."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if run["state"] not in ("created", "awaiting_plan_approval"):
                raise RunConflictError(
                    "only a created or awaiting_plan_approval Process Run can become ready"
                )
            entry_node_id = definition["graph"]["entry_node_id"]
            if run["current_node_id"] != entry_node_id:
                raise RunConflictError("Process Run is not positioned at its graph entry")
            if entry_node_id not in run["contracts"]["approved_plan"]["approved_node_ids"]:
                raise AuthorityDeniedError("graph entry is outside the approved plan")
            run["state"] = "ready"
            return self._append_event_locked(
                run,
                "run_ready",
                {"entry_node_id": entry_node_id, "reason": reason},
                node_id=entry_node_id,
                runtime_authoritative=True,
            )

    def start_run(self, run_id: str, *, reason: str) -> dict[str, Any]:
        """Start a ready Run at its declared graph entry without inventing a route."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if run["state"] != "ready":
                raise RunConflictError("only a ready Process Run can start")
            entry_node_id = definition["graph"]["entry_node_id"]
            if run["current_node_id"] != entry_node_id:
                raise RunConflictError("ready Process Run is not positioned at its graph entry")
            if entry_node_id not in run["contracts"]["approved_plan"]["approved_node_ids"]:
                raise AuthorityDeniedError("graph entry is outside the approved plan")
            run["state"] = "running"
            return self._append_event_locked(
                run,
                "run_started",
                {"entry_node_id": entry_node_id, "reason": reason},
                node_id=entry_node_id,
                runtime_authoritative=True,
            )

    # -------------------------------------------------------------- authority
    def authorize_action(
        self,
        run_id: str,
        action: str,
        selectors: Sequence[str],
        *,
        satisfied_conditions: Sequence[str] = (),
        effect_type: str | None = None,
        scope_kind: str | None = None,
    ) -> list[str]:
        if not selectors:
            raise AuthorityDeniedError("an authorized action requires at least one selector")
        if effect_type is None:
            raise AuthorityDeniedError("an authorized action requires an explicit effect_type")
        run = self.load_run(run_id)
        self._require_mutable_run(run, f"authorize action {action}")
        authority = run["contracts"]["authority"]
        expires_at = authority.get("expires_at")
        if expires_at and _parse_time(expires_at) < _parse_time(self._now()):
            raise AuthorityDeniedError("authority contract has expired")
        if action in authority["reserved_actions"]:
            raise AuthorityDeniedError(f"action is reserved for higher authority: {action}")
        scope = run["contracts"]["artifact_scope"]
        scope_fields = {
            "read": "read_selectors",
            "write": "write_selectors",
            "external": "external_effect_selectors",
        }
        if scope_kind not in (None, *scope_fields):
            raise AuthorityDeniedError(f"unknown artifact scope kind: {scope_kind}")
        allowed_scope = (
            set(scope[scope_fields[scope_kind]])
            if scope_kind
            else {
                *scope["read_selectors"],
                *scope["write_selectors"],
                *scope["external_effect_selectors"],
            }
        )
        outside_scope = sorted(set(selectors) - allowed_scope)
        if outside_scope:
            raise AuthorityDeniedError(
                f"selector(s) outside {scope_kind or 'declared'} artifact scope: "
                f"{', '.join(outside_scope)}"
            )
        satisfied = set(satisfied_conditions)
        matched_ids: set[str] = set()
        uncovered: list[str] = []
        requested = list(selectors) or [None]
        for selector in requested:
            matches = []
            for grant in authority["grants"]:
                if action not in grant["actions"]:
                    continue
                if selector is not None and selector not in grant["resource_selectors"]:
                    continue
                if effect_type is not None and effect_type not in grant["effect_types"]:
                    continue
                if not set(grant["conditions"]).issubset(satisfied):
                    continue
                matches.append(grant)
            if not matches:
                uncovered.append(selector or "<no-selector>")
            matched_ids.update(grant["grant_id"] for grant in matches)
        if uncovered:
            raise AuthorityDeniedError(
                f"action {action!r} is not authorized for selector(s): {', '.join(uncovered)}"
            )
        return sorted(matched_ids)

    def record_action(
        self,
        run_id: str,
        *,
        action: str,
        selectors: Sequence[str],
        satisfied_conditions: Sequence[str] = (),
        effect_type: str,
        external_effect: bool,
        receipt_artifact_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        scope_kind = "external" if external_effect else "write"
        grant_ids = self.authorize_action(
            run_id,
            action,
            selectors,
            satisfied_conditions=satisfied_conditions,
            effect_type=effect_type,
            scope_kind=scope_kind,
        )
        if receipt_artifact_id is not None:
            receipt = self.load_artifact(run_id, receipt_artifact_id)
            if receipt["role"] != "external_effect_receipt":
                raise GovernedRuntimeError("external-effect receipt must use that artifact role")
        else:
            receipt = None
        if receipt is not None and not external_effect:
            raise GovernedRuntimeError("a receipt may be bound only to an external effect")
        return self._record_runtime_event(
            run_id,
            "action_completed",
            {
                "action": action,
                "selectors": list(selectors),
                "grant_ids": grant_ids,
                "effect_type": effect_type,
                "external_effect": bool(external_effect),
                "receipt_artifact_id": receipt_artifact_id,
                "receipt_identity_digest": (
                    receipt["identity"]["digest"] if receipt is not None else None
                ),
                "details": copy.deepcopy(dict(details or {})),
            },
            artifact_ids=[receipt_artifact_id] if receipt_artifact_id else [],
        )

    # ---------------------------------------------------- controlled probes
    @staticmethod
    def _controlled_probe_contract_from_records(
        records: Sequence[Mapping[str, Any]],
        probe_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        matches = []
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "controlled_probe_contract_persisted"
                and details.get("probe_id") == probe_id
            ):
                matches.append((record, details))
        if not matches:
            raise RunNotFoundError(f"controlled probe contract not found: {probe_id}")
        if len(matches) != 1:
            raise GovernedRuntimeError(
                f"controlled probe contract identity is ambiguous: {probe_id}"
            )
        record, details = matches[0]
        contract = details.get("contract")
        if not isinstance(contract, dict):
            raise GovernedRuntimeError("controlled probe contract record is malformed")
        expected = _digest_json(contract)
        if details.get("contract_digest") != expected:
            raise GovernedRuntimeError("controlled probe contract digest does not match")
        return copy.deepcopy(contract), copy.deepcopy(record)

    @staticmethod
    def _latest_controlled_probe_stop_states(
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}
        for record in records:
            event = record.get("event") or {}
            if event.get("event_type") != "controlled_probe_stop_state_recorded":
                continue
            details = copy.deepcopy(event.get("details") or {})
            details["record_id"] = record.get("record_id")
            details["sequence"] = record.get("sequence")
            states[str(details.get("condition_id") or "")] = details
        states.pop("", None)
        return states

    def record_controlled_probe_stop_state(
        self,
        run_id: str,
        condition_id: str,
        *,
        active: bool,
        state_identity_digest: str,
        source: str,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist an exact stop-state observation for later probe enforcement."""

        condition_id = str(condition_id or "").strip()
        source = str(source or "").strip()
        if not condition_id:
            raise GovernedRuntimeError("controlled probe stop condition_id is required")
        if not isinstance(active, bool):
            raise GovernedRuntimeError("controlled probe stop state active must be boolean")
        if not source:
            raise GovernedRuntimeError("controlled probe stop state source is required")
        state_identity_digest = _exact_digest(
            state_identity_digest, "controlled probe stop state identity"
        )
        return self._record_runtime_event(
            run_id,
            "controlled_probe_stop_state_recorded",
            {
                "condition_id": condition_id,
                "active": active,
                "state_identity_digest": state_identity_digest,
                "source": source,
            },
            node_id=node_id,
        )

    def persist_controlled_probe_contract(
        self,
        run_id: str,
        contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist one immutable, identity-bound Controlled Probe Contract."""

        if not isinstance(contract, Mapping):
            raise GovernedRuntimeError("controlled probe contract must be an object")
        supplied = copy.deepcopy(dict(contract))
        _require_json(supplied, "controlled probe contract")
        required = {
            "contract_version",
            "run_id",
            "definition_ref",
            "approved_plan_ref",
            "probe_id",
            "assumption_id",
            "capability_identity",
            "action_identity",
            "selector",
            "node_id",
            "segment_id",
            "authority_conditions",
            "matched_grant_ids",
            "evidence_selector",
            "evidence_grant_ids",
            "evidence_requirement",
            "success_condition",
            "failure_condition",
            "ambiguous_route",
            "max_attempts",
            "stop_condition_ids",
            "mutation_safety",
        }
        missing = sorted(required - set(supplied))
        unknown = sorted(set(supplied) - required)
        if missing or unknown:
            problem = []
            if missing:
                problem.append(f"missing: {', '.join(missing)}")
            if unknown:
                problem.append(f"unknown: {', '.join(unknown)}")
            raise GovernedRuntimeError(
                "invalid controlled probe contract fields (" + "; ".join(problem) + ")"
            )

        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "persist a controlled probe contract")
            records = self.load_records(run_id)
            probe_id = str(supplied.get("probe_id") or "").strip()
            if not probe_id:
                raise GovernedRuntimeError("controlled probe contract probe_id is required")
            for record in records:
                event = record.get("event") or {}
                details = event.get("details") or {}
                if (
                    event.get("event_type") == "controlled_probe_contract_persisted"
                    and details.get("probe_id") == probe_id
                ):
                    raise RunConflictError(
                        f"controlled probe contract is immutable and already exists: {probe_id}"
                    )

            if supplied["run_id"] != run_id:
                raise GovernedRuntimeError("controlled probe contract run identity does not match")
            if supplied["definition_ref"] != run["definition_ref"]:
                raise GovernedRuntimeError(
                    "controlled probe contract definition identity does not match"
                )
            plan = run["contracts"]["approved_plan"]
            expected_plan_ref = {
                "plan_id": plan["plan_id"],
                "version": plan["version"],
                "digest": plan["digest"],
            }
            if supplied["approved_plan_ref"] != expected_plan_ref:
                raise GovernedRuntimeError(
                    "controlled probe contract approved-plan identity does not match"
                )
            if supplied["contract_version"] != "1.0":
                raise GovernedRuntimeError("unsupported controlled probe contract version")
            maximum = supplied["max_attempts"]
            if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
                raise GovernedRuntimeError(
                    "controlled probe max_attempts must be an integer >= 1"
                )
            for field in ("probe_id", "assumption_id", "selector", "node_id", "segment_id"):
                if not isinstance(supplied[field], str) or not supplied[field].strip():
                    raise GovernedRuntimeError(f"controlled probe {field} is required")
            for field in (
                "evidence_selector",
                "evidence_requirement",
                "success_condition",
                "failure_condition",
                "ambiguous_route",
            ):
                if not isinstance(supplied[field], str) or not supplied[field].strip():
                    raise GovernedRuntimeError(f"controlled probe {field} is required")
            for field in ("authority_conditions", "matched_grant_ids", "evidence_grant_ids", "stop_condition_ids"):
                value = supplied[field]
                if not isinstance(value, list) or any(
                    not isinstance(item, str) or not item for item in value
                ):
                    raise GovernedRuntimeError(
                        f"controlled probe {field} must be a string list"
                    )
                if field != "authority_conditions" and not value:
                    raise GovernedRuntimeError(
                        f"controlled probe {field} must contain at least one identity"
                    )
                if len(set(value)) != len(value):
                    raise GovernedRuntimeError(
                        f"controlled probe {field} contains duplicate identities"
                    )
            capability_identity = supplied["capability_identity"]
            action_identity = supplied["action_identity"]
            if not isinstance(capability_identity, dict) or not isinstance(action_identity, dict):
                raise GovernedRuntimeError(
                    "controlled probe capability and action identities must be objects"
                )
            capability_fields = {
                "capability_id", "category", "version", "identity_digest", "locator"
            }
            action_fields = {"action", "effect_class", "effect_type"}
            if set(capability_identity) != capability_fields:
                raise GovernedRuntimeError(
                    "controlled probe capability identity fields are incomplete or ambiguous"
                )
            if set(action_identity) != action_fields:
                raise GovernedRuntimeError(
                    "controlled probe action identity fields are incomplete or ambiguous"
                )
            for field in ("capability_id", "category", "version", "locator"):
                if not isinstance(capability_identity[field], str) or not capability_identity[field]:
                    raise GovernedRuntimeError(
                        f"controlled probe capability {field} is required"
                    )
            for field in ("action", "effect_type"):
                if not isinstance(action_identity[field], str) or not action_identity[field]:
                    raise GovernedRuntimeError(
                        f"controlled probe action {field} is required"
                    )
            _exact_digest(
                capability_identity.get("identity_digest"),
                "controlled probe capability identity",
            )
            effect_class = action_identity.get("effect_class")
            if effect_class not in ("inspection", "mutation"):
                raise GovernedRuntimeError(
                    "controlled probe action effect_class must be inspection or mutation"
                )
            definition = self.load_definition(run_id)
            node_ids = {node["node_id"] for node in definition["graph"]["nodes"]}
            if supplied["node_id"] not in node_ids:
                raise GovernedRuntimeError(
                    "controlled probe node identity is not in the Process Definition"
                )
            if supplied["node_id"] not in plan["approved_node_ids"]:
                raise AuthorityDeniedError(
                    "controlled probe node identity is outside the approved plan"
                )
            scope_kind = "external" if effect_class == "mutation" else "read"
            action_grants = self.authorize_action(
                run_id,
                action_identity["action"],
                [supplied["selector"]],
                satisfied_conditions=supplied["authority_conditions"],
                effect_type=action_identity["effect_type"],
                scope_kind=scope_kind,
            )
            if action_grants != sorted(supplied["matched_grant_ids"]):
                raise AuthorityDeniedError(
                    "controlled probe matched grant identities do not match current authority"
                )
            evidence_grants = self.authorize_action(
                run_id,
                "record_evidence",
                [supplied["evidence_selector"]],
                satisfied_conditions=supplied["authority_conditions"],
                effect_type="local_reversible",
                scope_kind="write",
            )
            if evidence_grants != sorted(supplied["evidence_grant_ids"]):
                raise AuthorityDeniedError(
                    "controlled probe evidence grant identities do not match current authority"
                )
            mutation_safety = supplied["mutation_safety"]
            if effect_class == "mutation":
                if not isinstance(mutation_safety, dict):
                    raise GovernedRuntimeError(
                        "mutation controlled probe requires mutation_safety"
                    )
                required_safety = {
                    "reversible",
                    "pre_state_digest",
                    "idempotency_key",
                    "checkpoint_id",
                    "required_receipt_fields",
                    "recovery_route",
                    "recovery_identity_digest",
                }
                if set(mutation_safety) != required_safety:
                    raise GovernedRuntimeError(
                        "controlled probe mutation_safety fields are incomplete or ambiguous"
                    )
                if mutation_safety["reversible"] is not True:
                    raise GovernedRuntimeError(
                        "mutation controlled probe must be explicitly reversible"
                    )
                _exact_digest(
                    mutation_safety.get("pre_state_digest"),
                    "controlled probe pre-state identity",
                )
                _exact_digest(
                    mutation_safety.get("recovery_identity_digest"),
                    "controlled probe recovery identity",
                )
                idempotency_key = str(mutation_safety.get("idempotency_key") or "")
                if not idempotency_key:
                    raise GovernedRuntimeError(
                        "mutation controlled probe requires an idempotency key"
                    )
                for field in ("checkpoint_id", "recovery_route"):
                    if not isinstance(mutation_safety[field], str) or not mutation_safety[field]:
                        raise GovernedRuntimeError(
                            f"mutation controlled probe requires {field}"
                        )
                required_receipt_fields = [
                    "effect_id",
                    "pre_state_digest",
                    "post_state_digest",
                    "idempotency_key",
                ]
                if mutation_safety["required_receipt_fields"] != required_receipt_fields:
                    raise GovernedRuntimeError(
                        "mutation controlled probe receipt fields do not match the runtime contract"
                    )
                expected_recovery_identity = _digest_json(
                    {"recovery_route": mutation_safety["recovery_route"]}
                )
                if mutation_safety["recovery_identity_digest"] != expected_recovery_identity:
                    raise GovernedRuntimeError(
                        "controlled probe recovery identity does not bind its route"
                    )
                if maximum != 1:
                    raise GovernedRuntimeError(
                        "a mutation controlled probe has one immutable idempotency key "
                        "and therefore requires max_attempts = 1"
                    )
                for record in records:
                    event = record.get("event") or {}
                    details = event.get("details") or {}
                    if event.get("event_type") != "controlled_probe_contract_persisted":
                        continue
                    prior = details.get("contract") or {}
                    prior_safety = prior.get("mutation_safety") or {}
                    if prior_safety.get("idempotency_key") == idempotency_key:
                        raise RunConflictError(
                            "controlled probe idempotency key is already bound to another "
                            "immutable contract"
                        )
            elif mutation_safety is not None:
                raise GovernedRuntimeError(
                    "inspection controlled probe must not contain mutation_safety"
                )

            latest_stops = self._latest_controlled_probe_stop_states(records)
            bound_stops = []
            for condition_id in supplied.pop("stop_condition_ids"):
                state = latest_stops.get(condition_id)
                if state is None:
                    raise AuthorityDeniedError(
                        "controlled probe stop state must be persisted before contract "
                        f"creation: {condition_id}"
                    )
                bound_stops.append(
                    {
                        "condition_id": condition_id,
                        "active": state["active"],
                        "state_identity_digest": state["state_identity_digest"],
                        "state_record_id": state["record_id"],
                        "state_sequence": state["sequence"],
                    }
                )
            supplied["stop_conditions"] = bound_stops
            contract_digest = _digest_json(supplied)
            record = self._append_event_locked(
                run,
                "controlled_probe_contract_persisted",
                {
                    "probe_id": probe_id,
                    "contract_digest": contract_digest,
                    "contract": supplied,
                },
                node_id=supplied["node_id"],
                runtime_authoritative=True,
            )
            return {
                "contract": copy.deepcopy(supplied),
                "contract_digest": contract_digest,
                "record": record,
            }

    def load_controlled_probe_contract(
        self,
        run_id: str,
        probe_id: str,
    ) -> dict[str, Any]:
        with _locked():
            if not self._run_path(run_id).is_file():
                raise RunNotFoundError(f"Process Run not found: {run_id}")
            contract, record = self._controlled_probe_contract_from_records(
                self.load_records(run_id), probe_id
            )
            return {
                "contract": contract,
                "contract_digest": (record.get("event") or {}).get("details", {}).get(
                    "contract_digest"
                ),
                "record": record,
            }

    def begin_controlled_probe_attempt(
        self,
        run_id: str,
        probe_id: str,
    ) -> dict[str, Any]:
        """Allocate an attempt from persisted contract and stop state only."""

        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "begin a controlled probe attempt")
            records = self.load_records(run_id)
            contract, contract_record = self._controlled_probe_contract_from_records(
                records, probe_id
            )
            contract_details = (contract_record.get("event") or {}).get("details") or {}
            contract_digest = contract_details.get("contract_digest")
            latest_stops = self._latest_controlled_probe_stop_states(records)
            stop_hits = []
            for bound in contract["stop_conditions"]:
                condition_id = bound["condition_id"]
                current = latest_stops.get(condition_id)
                if current is None:
                    stop_hits.append(
                        {"condition_id": condition_id, "reason": "state_missing"}
                    )
                elif current["active"]:
                    stop_hits.append(
                        {
                            "condition_id": condition_id,
                            "reason": "active",
                            "state_identity_digest": current["state_identity_digest"],
                        }
                    )
                elif current["state_identity_digest"] != bound["state_identity_digest"]:
                    stop_hits.append(
                        {
                            "condition_id": condition_id,
                            "reason": "identity_changed",
                            "state_identity_digest": current["state_identity_digest"],
                        }
                    )
            if stop_hits:
                record = self._append_event_locked(
                    run,
                    "controlled_probe_withheld",
                    {
                        "probe_id": probe_id,
                        "contract_digest": contract_digest,
                        "stop_conditions": stop_hits,
                    },
                    node_id=contract["node_id"],
                    runtime_authoritative=True,
                )
                return {
                    "status": "withheld",
                    "record": record,
                    "stop_conditions": stop_hits,
                }

            started = []
            completed_keys = set()
            for record in records:
                event = record.get("event") or {}
                details = event.get("details") or {}
                if details.get("probe_id") != probe_id:
                    continue
                if event.get("event_type") == "controlled_probe_attempt_started":
                    started.append(details)
                elif event.get("event_type") == "controlled_probe_attempt_completed":
                    completed_keys.add(details.get("attempt"))
            active_attempts = [
                details for details in started if details.get("attempt") not in completed_keys
            ]
            if active_attempts:
                raise RunConflictError(
                    "controlled probe has an active attempt; replay is refused"
                )
            maximum = int(contract["max_attempts"])
            if len(started) >= maximum:
                raise CorrectionDecisionRequired(
                    "controlled probe attempt ceiling reached in persisted Run state"
                )
            attempt = len(started) + 1
            mutation_safety = contract.get("mutation_safety") or {}
            idempotency_key = mutation_safety.get("idempotency_key")
            if idempotency_key:
                for record in records:
                    event = record.get("event") or {}
                    details = event.get("details") or {}
                    if (
                        event.get("event_type") == "controlled_probe_attempt_started"
                        and details.get("idempotency_key") == idempotency_key
                    ):
                        raise RunConflictError(
                            "controlled probe mutation idempotency key has already been consumed; "
                            "replay is refused"
                        )
            record = self._append_event_locked(
                run,
                "controlled_probe_attempt_started",
                {
                    "probe_id": probe_id,
                    "contract_digest": contract_digest,
                    "attempt": attempt,
                    "max_attempts": maximum,
                    "idempotency_key": idempotency_key,
                },
                node_id=contract["node_id"],
                runtime_authoritative=True,
            )
            return {
                "status": "started",
                "attempt": attempt,
                "max_attempts": maximum,
                "record": record,
                "contract": contract,
                "contract_digest": contract_digest,
            }

    def complete_controlled_probe_attempt(
        self,
        run_id: str,
        probe_id: str,
        *,
        status: str,
        outcome: str | None,
        details: Mapping[str, Any] | None = None,
        artifact_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Close one attempt, proof-checking every authoritative completion."""

        if status not in ("completed", "failed"):
            raise GovernedRuntimeError(
                "controlled probe attempt status must be completed or failed"
            )
        with _locked():
            run = self.load_run(run_id)
            records = self.load_records(run_id)
            contract, contract_record = self._controlled_probe_contract_from_records(
                records, probe_id
            )
            contract_digest = (
                (contract_record.get("event") or {}).get("details") or {}
            ).get("contract_digest")
            started = []
            completed = set()
            for record in records:
                event = record.get("event") or {}
                event_details = event.get("details") or {}
                if event_details.get("probe_id") != probe_id:
                    continue
                if event.get("event_type") == "controlled_probe_attempt_started":
                    started.append(event_details)
                elif event.get("event_type") == "controlled_probe_attempt_completed":
                    completed.add(event_details.get("attempt"))
            open_attempts = [
                item for item in started if item.get("attempt") not in completed
            ]
            if len(open_attempts) != 1:
                raise RunConflictError(
                    "controlled probe completion requires exactly one active attempt"
                )
            attempt = int(open_attempts[0]["attempt"])
            if open_attempts[0].get("contract_digest") != contract_digest:
                raise GovernedRuntimeError(
                    "controlled probe active attempt contract digest does not match"
                )
            supplied_details = copy.deepcopy(dict(details or {}))
            if status == "failed":
                if outcome is not None:
                    raise GovernedRuntimeError(
                        "failed controlled probe completion cannot claim an outcome"
                    )
                if artifact_ids:
                    raise GovernedRuntimeError(
                        "failed controlled probe completion cannot bind accepted artifacts"
                    )
            else:
                if outcome not in ("confirmed", "disconfirmed", "ambiguous"):
                    raise GovernedRuntimeError(
                        "completed controlled probe outcome is invalid"
                    )
                completion_fields = {
                    "contract_digest",
                    "attempt",
                    "assumption_id",
                    "capability_id",
                    "capability_identity_digest",
                    "action",
                    "effect_class",
                    "effect_type",
                    "selector",
                    "evidence_artifact_id",
                    "evidence_identity_digest",
                    "receipt_artifact_id",
                    "receipt_identity_digest",
                    "success_condition",
                    "failure_condition",
                    "ambiguous_route",
                    "stop_conditions",
                    "recovery_identity_digest",
                }
                if set(supplied_details) != completion_fields:
                    raise GovernedRuntimeError(
                        "controlled probe authoritative completion fields are incomplete "
                        "or ambiguous"
                    )
                capability = contract["capability_identity"]
                action = contract["action_identity"]
                exact_bindings = {
                    "contract_digest": contract_digest,
                    "attempt": attempt,
                    "assumption_id": contract["assumption_id"],
                    "capability_id": capability["capability_id"],
                    "capability_identity_digest": capability["identity_digest"],
                    "action": action["action"],
                    "effect_class": action["effect_class"],
                    "effect_type": action["effect_type"],
                    "selector": contract["selector"],
                    "success_condition": contract["success_condition"],
                    "failure_condition": contract["failure_condition"],
                    "ambiguous_route": contract["ambiguous_route"],
                    "stop_conditions": contract["stop_conditions"],
                    "recovery_identity_digest": (
                        (contract.get("mutation_safety") or {}).get(
                            "recovery_identity_digest"
                        )
                    ),
                }
                mismatched = [
                    field
                    for field, expected in exact_bindings.items()
                    if supplied_details.get(field) != expected
                ]
                if mismatched:
                    raise GovernedRuntimeError(
                        "controlled probe completion contradicts persisted contract: "
                        + ", ".join(sorted(mismatched))
                    )

                evidence_artifact_id = str(
                    supplied_details.get("evidence_artifact_id") or ""
                )
                if not evidence_artifact_id:
                    raise GovernedRuntimeError(
                        "controlled probe completion requires an evidence artifact"
                    )
                evidence_identity_digest = _exact_digest(
                    supplied_details.get("evidence_identity_digest"),
                    "controlled probe completion evidence identity",
                )
                mutation = action["effect_class"] == "mutation"
                receipt_artifact_id = supplied_details.get("receipt_artifact_id")
                receipt_identity_digest = supplied_details.get(
                    "receipt_identity_digest"
                )
                expected_artifact_ids = [evidence_artifact_id]
                if mutation:
                    if not isinstance(receipt_artifact_id, str) or not receipt_artifact_id:
                        raise GovernedRuntimeError(
                            "mutation probe completion requires a receipt artifact"
                        )
                    receipt_identity_digest = _exact_digest(
                        receipt_identity_digest,
                        "controlled probe completion receipt identity",
                    )
                    expected_artifact_ids.append(receipt_artifact_id)
                elif receipt_artifact_id is not None or receipt_identity_digest is not None:
                    raise GovernedRuntimeError(
                        "inspection probe completion cannot bind a mutation receipt"
                    )
                if len(set(artifact_ids)) != len(artifact_ids) or set(artifact_ids) != set(
                    expected_artifact_ids
                ):
                    raise GovernedRuntimeError(
                        "controlled probe completion artifact IDs do not match exact evidence "
                        "and receipt bindings"
                    )

                started_record = next(
                    record
                    for record in reversed(records)
                    if (record.get("event") or {}).get("event_type")
                    == "controlled_probe_attempt_started"
                    and ((record.get("event") or {}).get("details") or {}).get(
                        "probe_id"
                    )
                    == probe_id
                    and ((record.get("event") or {}).get("details") or {}).get(
                        "attempt"
                    )
                    == attempt
                )

                def artifact_record(artifact_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
                    matches = []
                    for candidate in records:
                        event = candidate.get("event") or {}
                        event_details = event.get("details") or {}
                        if (
                            event.get("event_type") == "artifact_recorded"
                            and event_details.get("artifact_id") == artifact_id
                        ):
                            matches.append((candidate, event_details))
                    if not matches:
                        raise GovernedRuntimeError(
                            f"controlled probe completion artifact is not persisted: {artifact_id}"
                        )
                    candidate, event_details = matches[-1]
                    if int(candidate["sequence"]) <= int(started_record["sequence"]):
                        raise GovernedRuntimeError(
                            "controlled probe completion artifact predates its active attempt"
                        )
                    if event_details.get("action") != "record_evidence":
                        raise GovernedRuntimeError(
                            "controlled probe completion artifact bypassed evidence authority"
                        )
                    if event_details.get("selectors") != [contract["evidence_selector"]]:
                        raise GovernedRuntimeError(
                            "controlled probe completion artifact selector does not match"
                        )
                    if event_details.get("grant_ids") != contract["evidence_grant_ids"]:
                        raise GovernedRuntimeError(
                            "controlled probe completion evidence grants do not match"
                        )
                    return candidate, event_details

                _evidence_record, evidence_record_details = artifact_record(
                    evidence_artifact_id
                )
                evidence = self.load_artifact(run_id, evidence_artifact_id)
                if evidence["role"] != "evidence":
                    raise GovernedRuntimeError(
                        "controlled probe completion evidence has the wrong artifact role"
                    )
                if evidence["identity"]["digest"] != evidence_identity_digest:
                    raise GovernedRuntimeError(
                        "controlled probe completion evidence identity changed"
                    )
                if evidence_record_details.get("identity_digest") != evidence_identity_digest:
                    raise GovernedRuntimeError(
                        "controlled probe completion evidence record identity does not match"
                    )
                if evidence["lineage"]["run_id"] != run_id:
                    raise GovernedRuntimeError(
                        "controlled probe completion evidence belongs to another Run"
                    )
                if evidence["lineage"]["definition_ref"] != contract["definition_ref"]:
                    raise GovernedRuntimeError(
                        "controlled probe completion evidence definition identity does not match"
                    )
                if evidence["lineage"]["producing_node_id"] != contract["node_id"]:
                    raise GovernedRuntimeError(
                        "controlled probe completion evidence node identity does not match"
                    )

                if mutation:
                    receipt_record, receipt_record_details = artifact_record(
                        receipt_artifact_id
                    )
                    receipt = self.load_artifact(run_id, receipt_artifact_id)
                    if receipt["role"] != "external_effect_receipt":
                        raise GovernedRuntimeError(
                            "mutation probe completion receipt has the wrong artifact role"
                        )
                    if receipt["identity"]["digest"] != receipt_identity_digest:
                        raise GovernedRuntimeError(
                            "mutation probe completion receipt identity changed"
                        )
                    if receipt_record_details.get("identity_digest") != receipt_identity_digest:
                        raise GovernedRuntimeError(
                            "mutation probe completion receipt record identity does not match"
                        )
                    matching_actions = []
                    safety = contract["mutation_safety"]
                    for candidate in records:
                        event = candidate.get("event") or {}
                        event_details = event.get("details") or {}
                        nested = event_details.get("details") or {}
                        if (
                            event.get("event_type") == "action_completed"
                            and nested.get("probe_id") == probe_id
                            and nested.get("contract_digest") == contract_digest
                            and nested.get("attempt") == attempt
                        ):
                            matching_actions.append((candidate, event_details, nested))
                    if len(matching_actions) != 1:
                        raise GovernedRuntimeError(
                            "mutation probe completion requires exactly one matching external action"
                        )
                    action_record, action_details, nested = matching_actions[0]
                    if int(action_record["sequence"]) <= int(receipt_record["sequence"]):
                        raise GovernedRuntimeError(
                            "mutation probe action was not bound after its receipt"
                        )
                    expected_action = {
                        "action": action["action"],
                        "selectors": [contract["selector"]],
                        "grant_ids": contract["matched_grant_ids"],
                        "effect_type": action["effect_type"],
                        "external_effect": True,
                        "receipt_artifact_id": receipt_artifact_id,
                        "receipt_identity_digest": receipt_identity_digest,
                    }
                    action_mismatch = [
                        field
                        for field, expected in expected_action.items()
                        if action_details.get(field) != expected
                    ]
                    expected_nested = {
                        "probe_id": probe_id,
                        "attempt": attempt,
                        "contract_digest": contract_digest,
                        "capability_id": capability["capability_id"],
                        "capability_identity_digest": capability["identity_digest"],
                        "receipt_identity_digest": receipt_identity_digest,
                        "pre_state_digest": safety["pre_state_digest"],
                        "idempotency_key": safety["idempotency_key"],
                    }
                    action_mismatch.extend(
                        field
                        for field, expected in expected_nested.items()
                        if nested.get(field) != expected
                    )
                    if action_mismatch:
                        raise GovernedRuntimeError(
                            "mutation probe completion action binding does not match: "
                            + ", ".join(sorted(set(action_mismatch)))
                        )
                else:
                    for candidate in records:
                        event = candidate.get("event") or {}
                        nested = ((event.get("details") or {}).get("details") or {})
                        if (
                            event.get("event_type") == "action_completed"
                            and nested.get("probe_id") == probe_id
                            and nested.get("contract_digest") == contract_digest
                        ):
                            raise GovernedRuntimeError(
                                "inspection probe completion cannot bind an external action"
                            )
            record = self._append_event_locked(
                run,
                "controlled_probe_attempt_completed",
                {
                    "probe_id": probe_id,
                    "contract_digest": contract_digest,
                    "attempt": attempt,
                    "status": status,
                    "outcome": outcome,
                    "details": supplied_details,
                },
                node_id=contract["node_id"],
                artifact_ids=artifact_ids,
                runtime_authoritative=True,
            )
            return record

    # --------------------------------------------------------- attempt policy
    def start_segment(self, run_id: str, segment_id: str, *, node_id: str | None = None) -> dict[str, Any]:
        return self._record_runtime_event(
            run_id,
            "segment_started",
            {"segment_id": segment_id},
            node_id=node_id,
        )

    def begin_attempt(self, run_id: str, segment_id: str) -> dict[str, Any]:
        with _locked():
            run = self.load_run(run_id)
            latest_attempt_event = None
            for record in reversed(self.load_records(run_id)):
                event = record.get("event") or {}
                if event.get("event_type") in ("attempt_started", "attempt_completed"):
                    latest_attempt_event = event
                    break
            if (
                latest_attempt_event
                and latest_attempt_event.get("event_type") == "attempt_started"
            ):
                raise RunConflictError("the active attempt must complete before another begins")
            correction = run["contracts"]["correction_loop"]
            current = int(correction["attempt"])
            maximum = int(correction["max_attempts"])
            if current >= maximum:
                raise CorrectionDecisionRequired(
                    "attempt ceiling reached; Process Coherence must select an allowed "
                    "non-REVISE route from current evidence"
                )
            correction["attempt"] = current + 1
            return self._append_event_locked(
                run,
                "attempt_started",
                {"segment_id": segment_id, "attempt": correction["attempt"], "max_attempts": maximum},
                node_id=run["current_node_id"],
                runtime_authoritative=True,
            )

    def complete_attempt(
        self,
        run_id: str,
        segment_id: str,
        *,
        defect_codes: Sequence[str],
        evidence_refs: Sequence[Mapping[str, Any]],
        artifact_digests: Sequence[str],
    ) -> dict[str, Any]:
        with _locked():
            run = self.load_run(run_id)
            records = self.load_records(run_id)
            latest_attempt_event = None
            for record in reversed(records):
                event = record.get("event") or {}
                if event.get("event_type") in ("attempt_started", "attempt_completed"):
                    latest_attempt_event = event
                    break
            if not latest_attempt_event or latest_attempt_event.get("event_type") != "attempt_started":
                raise RunConflictError("attempt completion requires one active attempt")
            started = latest_attempt_event.get("details") or {}
            if started.get("segment_id") != segment_id:
                raise RunConflictError("attempt must complete in the segment where it started")
            if int(started.get("attempt") or -1) != int(
                run["contracts"]["correction_loop"]["attempt"]
            ):
                raise RunConflictError("attempt number does not match persisted Run state")
            prior = None
            for record in reversed(records):
                event = record.get("event") or {}
                details = event.get("details") or {}
                if (
                    event.get("event_type") == "attempt_completed"
                    and details.get("segment_id") == segment_id
                ):
                    prior = event.get("details") or {}
                    break
            evidence_ids = sorted(
                ref["evidence_id"]
                for ref in evidence_refs
                if ref.get("outcome") == "PASS"
            )
            artifact_digests = sorted(set(artifact_digests))
            prior_evidence = set((prior or {}).get("passing_evidence_ids") or [])
            prior_artifacts = set((prior or {}).get("artifact_digests") or [])
            progress = bool(
                (set(evidence_ids) - prior_evidence)
                or (set(artifact_digests) - prior_artifacts)
            )
            defect_fingerprint = _digest_json(sorted(set(defect_codes)))
            repeated = 1
            if prior and prior.get("defect_fingerprint") == defect_fingerprint:
                repeated = int(prior.get("repeated_defect_count") or 1) + 1
            details = {
                "segment_id": segment_id,
                "attempt": run["contracts"]["correction_loop"]["attempt"],
                "defect_codes": sorted(set(defect_codes)),
                "defect_fingerprint": defect_fingerprint,
                "repeated_defect_count": repeated,
                "passing_evidence_ids": evidence_ids,
                "artifact_digests": artifact_digests,
                "progress_evidence": progress,
            }
            record = self._append_event_locked(
                run,
                "attempt_completed",
                details,
                node_id=run["current_node_id"],
                evidence_refs=evidence_refs,
                runtime_authoritative=True,
            )
            return {"record": record, **details}

    def validate_correction_directive(self, run_id: str, directive: str) -> None:
        run = self.load_run(run_id)
        correction = run["contracts"]["correction_loop"]
        if directive not in correction["allowed_directives"]:
            raise CorrectionDecisionRequired(
                f"directive {directive} is not allowed by the correction contract"
            )
        latest = None
        for record in reversed(self.load_records(run_id)):
            event = record.get("event") or {}
            if event.get("event_type") == "attempt_completed":
                latest = event.get("details") or {}
                break
        if latest is None:
            return
        no_progress = (
            bool(correction["progress_evidence_required"])
            and not bool(latest.get("progress_evidence"))
        )
        repeated = int(latest.get("repeated_defect_count") or 0)
        repeated_limit = int(correction["repeated_defect_limit"])
        at_ceiling = int(correction["attempt"]) >= int(correction["max_attempts"])
        if no_progress or repeated >= repeated_limit or at_ceiling:
            if directive not in correction["no_progress_directives"]:
                reasons = []
                if no_progress:
                    reasons.append("no new progress evidence")
                if repeated >= repeated_limit:
                    reasons.append("repeated defect limit reached")
                if at_ceiling:
                    reasons.append("attempt ceiling reached")
                raise CorrectionDecisionRequired(
                    f"{'; '.join(reasons)}; directive must be one of "
                    f"{', '.join(correction['no_progress_directives'])}"
                )

    # -------------------------------------------- infrastructure vs quality
    def record_infrastructure_attempt(
        self,
        run_id: str,
        operation_id: str,
        *,
        attempt: int,
        max_retries: int,
        outcome: str,
        reason: str,
    ) -> dict[str, Any]:
        if outcome not in INFRASTRUCTURE_OUTCOMES:
            raise GovernedRuntimeError(
                f"infrastructure outcome must be one of {', '.join(INFRASTRUCTURE_OUTCOMES)}"
            )
        if attempt < 1 or max_retries < 0:
            raise GovernedRuntimeError("attempt must be >= 1 and max_retries must be >= 0")
        prior_attempts = []
        for record in self.load_records(run_id):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "infrastructure_attempt"
                and details.get("operation_id") == operation_id
            ):
                prior_attempts.append(details)
        expected_attempt = len(prior_attempts) + 1
        if attempt != expected_attempt:
            raise RunConflictError(
                f"infrastructure attempt must be {expected_attempt}; got {attempt}"
            )
        if prior_attempts and int(prior_attempts[-1]["max_retries"]) != max_retries:
            raise RunConflictError("max_retries cannot change within one operation")
        if prior_attempts and (
            prior_attempts[-1]["outcome"] == "success"
            or not prior_attempts[-1]["can_retry"]
        ):
            raise RunConflictError("infrastructure operation has already reached a terminal outcome")
        can_retry = outcome == "retryable_failure" and attempt <= max_retries
        requires_transition_evaluation = outcome != "success" and not can_retry
        record = self._record_runtime_event(
            run_id,
            "infrastructure_attempt",
            {
                "operation_id": operation_id,
                "attempt": attempt,
                "max_retries": max_retries,
                "outcome": outcome,
                "reason": reason,
                "can_retry": can_retry,
                "requires_transition_evaluation": requires_transition_evaluation,
                "quality_directive": None,
            },
        )
        return {
            "record": record,
            "can_retry": can_retry,
            "requires_transition_evaluation": requires_transition_evaluation,
            "directive": None,
        }

    # ---------------------------------------------------------- artifacts
    def _latest_artifact_record_details(
        self,
        run_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        for record in reversed(self.load_records(run_id)):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "artifact_recorded"
                and details.get("artifact_id") == artifact_id
            ):
                return copy.deepcopy(details)
        raise GovernedRuntimeError(
            f"Artifact has no committed lineage record: {artifact_id}"
        )

    @staticmethod
    def _local_artifact_binding(
        artifact: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "artifact_id": artifact["artifact_id"],
            "producing_run_id": artifact["lineage"]["run_id"],
            "definition_ref": copy.deepcopy(artifact["lineage"]["definition_ref"]),
            "identity_digest": artifact["identity"]["digest"],
            "role": artifact["role"],
        }

    def _returned_child_artifact_bindings(
        self,
        parent_run_id: str,
    ) -> dict[str, dict[str, Any]]:
        bindings: dict[str, dict[str, Any]] = {}
        for record in self.load_records(parent_run_id):
            event = record.get("event") or {}
            if event.get("event_type") != "child_return_received":
                continue
            details = event.get("details") or {}
            exact_bindings = details.get("output_bindings")
            if not isinstance(exact_bindings, list):
                raise GovernedRuntimeError(
                    "child return lacks exact output identity bindings"
                )
            for raw_binding in exact_bindings:
                if not isinstance(raw_binding, dict):
                    raise GovernedRuntimeError("invalid child output identity binding")
                binding = copy.deepcopy(raw_binding)
                artifact_id = str(binding.get("artifact_id") or "")
                if not artifact_id:
                    raise GovernedRuntimeError("child output binding lacks artifact_id")
                prior = bindings.get(artifact_id)
                if prior is not None and prior != binding:
                    raise GovernedRuntimeError(
                        f"ambiguous child Artifact identity collision: {artifact_id}"
                    )
                self._validate_child_output_binding(binding)
                bindings[artifact_id] = binding
        return bindings

    def _source_artifact_bindings(
        self,
        run_id: str,
    ) -> dict[str, dict[str, Any]]:
        run = self.load_run(run_id)
        bindings: dict[str, dict[str, Any]] = {}
        for artifact_id in run["artifact_ids"]:
            artifact = self.load_artifact(run_id, artifact_id)
            bindings[artifact_id] = self._local_artifact_binding(artifact)
        for artifact_id, binding in self._returned_child_artifact_bindings(run_id).items():
            if artifact_id in bindings:
                raise GovernedRuntimeError(
                    f"local/child Artifact identity collision: {artifact_id}"
                )
            bindings[artifact_id] = binding
        return bindings

    def record_artifact(
        self,
        artifact: Mapping[str, Any],
        *,
        action: str,
        selectors: Sequence[str],
        satisfied_conditions: Sequence[str] = (),
    ) -> dict[str, Any]:
        artifact_copy = _contracts.validate_artifact(artifact)
        run_id = artifact_copy["lineage"]["run_id"]
        grant_ids = self.authorize_action(
            run_id,
            action,
            selectors,
            satisfied_conditions=satisfied_conditions,
            effect_type="local_reversible",
            scope_kind="write",
        )
        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "record or replace an Artifact")
            if artifact_copy["lineage"]["definition_ref"] != run["definition_ref"]:
                raise GovernedRuntimeError("Artifact lineage must bind the Run definition")
            returned_bindings = self._returned_child_artifact_bindings(run_id)
            if artifact_copy["artifact_id"] in returned_bindings:
                raise GovernedRuntimeError(
                    "local Artifact ID collides with an identity-bound child return: "
                    f"{artifact_copy['artifact_id']}"
                )
            source_bindings = self._source_artifact_bindings(run_id)
            source_ids = list(artifact_copy["lineage"]["source_artifact_ids"])
            unknown_sources = sorted(set(source_ids) - set(source_bindings))
            if unknown_sources:
                raise GovernedRuntimeError(
                    f"Artifact lineage references unknown source(s): {', '.join(unknown_sources)}"
                )
            exact_source_bindings = [source_bindings[source_id] for source_id in source_ids]
            path = self._artifact_path(run_id, artifact_copy["artifact_id"])
            prior = _read_json(path) if path.exists() else None
            prior_digest = ((prior or {}).get("identity") or {}).get("digest")
            current_digest = artifact_copy["identity"]["digest"]
            _atomic_json(path, artifact_copy)
            if artifact_copy["artifact_id"] not in run["artifact_ids"]:
                run["artifact_ids"].append(artifact_copy["artifact_id"])
            record = self._append_event_locked(
                run,
                "artifact_recorded",
                {
                    "artifact_id": artifact_copy["artifact_id"],
                    "role": artifact_copy["role"],
                    "identity_digest": current_digest,
                    "prior_identity_digest": prior_digest,
                    "stale_review_invalidated": bool(prior_digest and prior_digest != current_digest),
                    "action": action,
                    "selectors": list(selectors),
                    "grant_ids": grant_ids,
                    "source_artifact_identities": exact_source_bindings,
                },
                node_id=artifact_copy["lineage"]["producing_node_id"],
                artifact_ids=[artifact_copy["artifact_id"]],
                record_id=artifact_copy["lineage"]["event_record_id"],
                runtime_authoritative=True,
            )
            return {"artifact": artifact_copy, "record": record}

    def record_inline_artifact(
        self,
        run_id: str,
        artifact_id: str,
        text: str,
        *,
        role: str,
        node_id: str,
        action: str,
        selector: str,
        source_artifact_ids: Sequence[str] = (),
        satisfied_conditions: Sequence[str] = (),
        media_type: str = "text/markdown",
    ) -> dict[str, Any]:
        run = self.load_run(run_id)
        now = self._now()
        artifact = {
            "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": artifact_id,
            "role": role,
            "status": "candidate" if role != "evidence" else "verified",
            "media_type": media_type,
            "locator": {"kind": "inline", "ref": f"inline:{run_id}:{artifact_id}"},
            "identity": {
                "kind": "content_digest",
                "digest": _digest_text(text),
                "coverage": ["complete_content"],
                "captured_at": now,
                "fresh_until": (
                    _parse_time(now) + timedelta(days=3650)
                ).isoformat().replace("+00:00", "Z"),
            },
            "lineage": {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "producing_node_id": node_id,
                "source_artifact_ids": list(source_artifact_ids),
                "event_record_id": f"event-{uuid.uuid4().hex}",
            },
            "created_at": now,
        }
        return self.record_artifact(
            artifact,
            action=action,
            selectors=[selector],
            satisfied_conditions=satisfied_conditions,
        )

    def _assert_evidence_bound_to_subject(
        self,
        run_id: str,
        evidence_artifact: Mapping[str, Any],
        subject: Mapping[str, Any],
    ) -> None:
        subject_id = subject["artifact_id"]
        if subject_id not in evidence_artifact["lineage"]["source_artifact_ids"]:
            raise FinalReviewRequired(
                "final review evidence has no lineage to the reviewed result"
            )
        details = self._latest_artifact_record_details(
            run_id, evidence_artifact["artifact_id"]
        )
        exact_sources = details.get("source_artifact_identities")
        if not isinstance(exact_sources, list):
            raise FinalReviewRequired(
                "final review evidence lacks an exact source identity binding"
            )
        expected = {
            "artifact_id": subject_id,
            "producing_run_id": run_id,
            "definition_ref": subject["lineage"]["definition_ref"],
            "identity_digest": subject["identity"]["digest"],
            "role": subject["role"],
        }
        if expected not in exact_sources:
            raise FinalReviewRequired(
                "final review evidence is not bound to the current result identity"
            )

    def _latest_final_review_record(
        self,
        run_id: str,
        artifact_id: str,
        evidence_id: str,
    ) -> dict[str, Any] | None:
        for record in reversed(self.load_records(run_id)):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "final_review_completed"
                and details.get("artifact_id") == artifact_id
                and details.get("evidence_id") == evidence_id
            ):
                return copy.deepcopy(record)
        return None

    def _current_passing_review(
        self,
        run_id: str,
        artifact_id: str,
        evidence_id: str,
    ) -> dict[str, Any]:
        run = self.load_run(run_id)
        requirements = {
            requirement["evidence_id"]: requirement
            for requirement in run["contracts"]["evidence"]["requirements"]
        }
        requirement = requirements.get(evidence_id)
        if requirement is None:
            raise FinalReviewRequired(
                f"required final review is undeclared: {artifact_id}/{evidence_id}"
            )
        record = self._latest_final_review_record(run_id, artifact_id, evidence_id)
        if record is None:
            raise FinalReviewRequired(
                f"required final review missing: {artifact_id}/{evidence_id}"
            )
        details = record["event"]["details"]
        subject = self.load_artifact(run_id, artifact_id)
        if details.get("subject_digest") != subject["identity"]["digest"]:
            raise FinalReviewRequired(f"final review is stale for Artifact {artifact_id}")
        if details.get("outcome") != "PASS":
            raise FinalReviewRequired(
                f"final review did not pass: {artifact_id}/{evidence_id}"
            )
        if not details.get("independent"):
            raise FinalReviewRequired(
                f"final review is not independent: {artifact_id}/{evidence_id}"
            )
        try:
            evidence_artifact = self.load_artifact(
                run_id, details["evidence_artifact_id"]
            )
        except (KeyError, RunNotFoundError) as exc:
            raise FinalReviewRequired(
                f"final-review evidence Artifact is missing: {artifact_id}/{evidence_id}"
            ) from exc
        if evidence_artifact["identity"]["digest"] != details.get("evidence_digest"):
            raise FinalReviewRequired(
                f"final-review evidence is stale: {artifact_id}/{evidence_id}"
            )
        self._assert_evidence_bound_to_subject(run_id, evidence_artifact, subject)
        captured = _parse_time(evidence_artifact["identity"]["captured_at"])
        fresh_until = _parse_time(evidence_artifact["identity"]["fresh_until"])
        acceptance_time = _parse_time(self._now())
        declared_expiry = captured + timedelta(
            seconds=int(requirement["freshness_seconds"])
        )
        if acceptance_time > min(fresh_until, declared_expiry):
            raise FinalReviewRequired(
                f"final-review evidence expired: {artifact_id}/{evidence_id}"
            )
        return record

    def record_final_review(
        self,
        run_id: str,
        *,
        artifact_id: str,
        evidence_id: str,
        evidence_artifact_id: str,
        outcome: str,
        reviewer_id: str,
        independent: bool,
        satisfied_conditions: Sequence[str] = (),
    ) -> dict[str, Any]:
        if outcome not in _contracts.OBSERVATION_OUTCOMES:
            raise GovernedRuntimeError(f"unknown review outcome: {outcome}")
        run = self.load_run(run_id)
        subject = self.load_artifact(run_id, artifact_id)
        evidence_artifact = self.load_artifact(run_id, evidence_artifact_id)
        if evidence_artifact["role"] != "evidence":
            raise GovernedRuntimeError("final review evidence must be an evidence Artifact")
        if evidence_artifact_id == artifact_id:
            raise FinalReviewRequired("final review evidence must differ from its subject")
        self._assert_evidence_bound_to_subject(run_id, evidence_artifact, subject)
        requirements = {
            requirement["evidence_id"]: requirement
            for requirement in run["contracts"]["evidence"]["requirements"]
        }
        if evidence_id not in requirements:
            raise GovernedRuntimeError(f"undeclared evidence requirement: {evidence_id}")
        requirement = requirements[evidence_id]
        active_judgments = [
            judgment
            for judgment in run["contracts"]["bounded_judgment"]
            if judgment["node_id"] == run["current_node_id"]
            and evidence_id in judgment["required_evidence_ids"]
        ]
        if len(active_judgments) != 1:
            raise FinalReviewRequired(
                "final review must occur at its declared bounded-judgment node"
            )
        judgment = active_judgments[0]
        self.authorize_action(
            run_id,
            "evaluate_evidence",
            judgment["artifact_selectors"],
            satisfied_conditions=satisfied_conditions,
            effect_type="local_reversible",
            scope_kind=None,
        )
        if requirement["producer_independence"] != "same_step" and not independent:
            raise FinalReviewRequired("final review must be independent for this evidence requirement")
        if independent and reviewer_id == run["contracts"]["authority"]["principal_id"]:
            raise FinalReviewRequired("independent reviewer must differ from the Run principal")
        if (
            requirement["producer_independence"] == "independent_step"
            and evidence_artifact["lineage"]["producing_node_id"]
            == subject["lineage"]["producing_node_id"]
        ):
            raise FinalReviewRequired(
                "independent-step evidence must be produced at a different process node"
            )
        review_time = _parse_time(self._now())
        if _parse_time(evidence_artifact["identity"]["fresh_until"]) < review_time:
            raise FinalReviewRequired("final review evidence Artifact is stale")
        evidence_ref = {
            "evidence_id": evidence_id,
            "artifact_id": artifact_id,
            "identity_digest": subject["identity"]["digest"],
            "outcome": outcome,
        }
        return self._record_runtime_event(
            run_id,
            "final_review_completed",
            {
                "artifact_id": artifact_id,
                "subject_digest": subject["identity"]["digest"],
                "evidence_id": evidence_id,
                "evidence_artifact_id": evidence_artifact_id,
                "evidence_digest": evidence_artifact["identity"]["digest"],
                "reviewer_id": reviewer_id,
                "independent": bool(independent),
                "outcome": outcome,
            },
            node_id=subject["lineage"]["producing_node_id"],
            evidence_refs=[evidence_ref],
            artifact_ids=[artifact_id, evidence_artifact_id],
        )

    def record_reviewed_text_candidate(
        self,
        run_id: str,
        *,
        candidate_text: str,
        review_text: str,
        outcome: str,
        candidate_artifact_id: str,
        evidence_artifact_id: str,
        evidence_id: str,
        candidate_node_id: str,
        evidence_node_id: str,
        candidate_action: str,
        evidence_action: str,
        candidate_selector: str,
        evidence_selector: str,
        reviewer_id: str,
        satisfied_conditions: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Persist one F-framework candidate identity and its review evidence.

        This is transport only: ``outcome`` remains an observation. The caller
        must obtain a Process Coherence decision and pass it to transition
        dispatch before a terminal state can be reached.
        """

        candidate = self.record_inline_artifact(
            run_id,
            candidate_artifact_id,
            candidate_text,
            role="result",
            node_id=candidate_node_id,
            action=candidate_action,
            selector=candidate_selector,
            satisfied_conditions=satisfied_conditions,
        )
        evidence = self.record_inline_artifact(
            run_id,
            evidence_artifact_id,
            review_text,
            role="evidence",
            node_id=evidence_node_id,
            action=evidence_action,
            selector=evidence_selector,
            source_artifact_ids=[candidate_artifact_id],
            satisfied_conditions=satisfied_conditions,
        )
        review = self.record_final_review(
            run_id,
            artifact_id=candidate_artifact_id,
            evidence_id=evidence_id,
            evidence_artifact_id=evidence_artifact_id,
            outcome=outcome,
            reviewer_id=reviewer_id,
            independent=True,
            satisfied_conditions=satisfied_conditions,
        )
        return {
            "candidate": candidate,
            "evidence": evidence,
            "review": review,
            "evidence_ref": {
                "evidence_id": evidence_id,
                "artifact_id": candidate_artifact_id,
                "identity_digest": candidate["artifact"]["identity"]["digest"],
                "outcome": outcome,
            },
        }

    def _acceptance_ready(self, run_id: str) -> tuple[bool, str]:
        run = self.load_run(run_id)
        requirements = {
            requirement["evidence_id"]: requirement
            for requirement in run["contracts"]["evidence"]["requirements"]
            if requirement["required"]
        }
        result_ids = []
        for artifact_id in run["artifact_ids"]:
            artifact = self.load_artifact(run_id, artifact_id)
            if artifact["role"] == "result":
                result_ids.append(artifact_id)
        if not result_ids:
            return False, "no result Artifact is bound to the Run"
        for artifact_id in result_ids:
            artifact = self.load_artifact(run_id, artifact_id)
            if _parse_time(artifact["identity"]["fresh_until"]) < _parse_time(self._now()):
                return False, f"result Artifact identity is stale: {artifact_id}"
            for evidence_id in requirements:
                try:
                    self._current_passing_review(run_id, artifact_id, evidence_id)
                except GovernedRuntimeError as exc:
                    return False, str(exc)
        return True, "all required final reviews pass for current Artifact identities"

    def _transition_judgment(
        self,
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
        directive: str,
        target_node_id: str,
        evaluation_boundary: str,
        evidence_refs: Sequence[Mapping[str, Any]],
        authority_request: Mapping[str, Any] | None,
    ) -> None:
        if directive not in _contracts.TRANSITION_DIRECTIVES:
            raise GovernedRuntimeError(f"unknown transition directive: {directive!r}")
        if run["state"] not in DIRECTIVE_SOURCE_STATES[directive]:
            raise GovernedRuntimeError(
                f"{directive} is not valid from Process Run state {run['state']!r}"
            )
        approved_nodes = set(run["contracts"]["approved_plan"]["approved_node_ids"])
        if target_node_id not in approved_nodes:
            raise AuthorityDeniedError(
                f"transition target is outside the approved plan: {target_node_id}"
            )
        judgments = [
            judgment
            for judgment in run["contracts"]["bounded_judgment"]
            if judgment["node_id"] == run["current_node_id"]
            and judgment["evaluator_boundary"] == evaluation_boundary
        ]
        if len(judgments) != 1:
            raise AuthorityDeniedError(
                "transition must bind exactly one active bounded-judgment boundary"
            )
        judgment = judgments[0]
        if directive not in judgment["permitted_directives"]:
            raise AuthorityDeniedError(
                f"directive {directive} is not permitted by judgment {judgment['judgment_id']}"
            )
        required_evidence = set(judgment["required_evidence_ids"])
        supplied_evidence = {ref.get("evidence_id") for ref in evidence_refs}
        missing = sorted(required_evidence - supplied_evidence)
        if missing:
            raise GovernedRuntimeError(
                f"transition is missing required evidence: {', '.join(missing)}"
            )
        declared_evidence = {
            requirement["evidence_id"]
            for requirement in run["contracts"]["evidence"]["requirements"]
        }
        for ref in evidence_refs:
            if ref.get("evidence_id") not in declared_evidence:
                raise GovernedRuntimeError(
                    f"transition references undeclared evidence: {ref.get('evidence_id')!r}"
                )
            artifact = self.load_artifact(run["run_id"], str(ref.get("artifact_id")))
            if ref.get("identity_digest") != artifact["identity"]["digest"]:
                raise GovernedRuntimeError(
                    f"transition evidence identity is stale: {ref.get('artifact_id')!r}"
                )
        if directive == "ACCEPT":
            required_acceptance_ids = {
                requirement["evidence_id"]
                for requirement in run["contracts"]["evidence"]["requirements"]
                if requirement["required"]
            }
            result_ids = {
                artifact_id
                for artifact_id in run["artifact_ids"]
                if self.load_artifact(run["run_id"], artifact_id)["role"] == "result"
            }
            expected_pairs = {
                (artifact_id, evidence_id)
                for artifact_id in result_ids
                for evidence_id in required_acceptance_ids
            }
            supplied_pairs = [
                (str(ref.get("artifact_id")), str(ref.get("evidence_id")))
                for ref in evidence_refs
            ]
            if len(supplied_pairs) != len(set(supplied_pairs)):
                raise FinalReviewRequired(
                    "ACCEPT evidence references must be unique current PASS reviews"
                )
            if set(supplied_pairs) != expected_pairs:
                raise FinalReviewRequired(
                    "ACCEPT evidence references must exactly cover every required "
                    "current result review"
                )
            refs_by_pair = {
                pair: ref for pair, ref in zip(supplied_pairs, evidence_refs)
            }
            for artifact_id, evidence_id in sorted(expected_pairs):
                supplied_ref = refs_by_pair[(artifact_id, evidence_id)]
                review_record = self._current_passing_review(
                    run["run_id"], artifact_id, evidence_id
                )
                if supplied_ref.get("outcome") != "PASS":
                    raise FinalReviewRequired(
                        "ACCEPT evidence references must report PASS"
                    )
                persisted_refs = review_record["evidence_refs"]
                if len(persisted_refs) != 1 or supplied_ref != persisted_refs[0]:
                    raise FinalReviewRequired(
                        "ACCEPT evidence reference does not match the current persisted PASS review"
                    )
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        current_node = nodes[run["current_node_id"]]
        if current_node["kind"] == "verification_boundary":
            routed_target = current_node["routes"].get(directive)
            if routed_target is not None and target_node_id != routed_target:
                raise GovernedRuntimeError(
                    f"{directive} must follow the declared graph route to {routed_target}"
                )
            if routed_target is None and target_node_id != judgment["return_node_id"]:
                raise GovernedRuntimeError(
                    f"unrouted {directive} must return to bounded node "
                    f"{judgment['return_node_id']}"
                )
        if directive == "ESCALATE":
            request_type = (authority_request or {}).get("request_type")
            if request_type not in judgment["escalation_request_types"]:
                raise AuthorityDeniedError(
                    f"ESCALATE request type is outside bounded judgment: {request_type!r}"
                )

    # -------------------------------------------------------- transitions
    def apply_transition(
        self,
        run_id: str,
        directive: str,
        *,
        target_node_id: str,
        reason: str,
        evaluation_boundary: str,
        authority_request: Mapping[str, Any] | None = None,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
            if target_node_id not in nodes:
                raise GovernedRuntimeError(f"transition target is not in the graph: {target_node_id}")
            self._transition_judgment(
                run,
                definition,
                directive,
                target_node_id,
                evaluation_boundary,
                evidence_refs,
                authority_request,
            )
            if directive in ("REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"):
                self.validate_correction_directive(run_id, directive)
            if directive == "ACCEPT":
                ready, why = self._acceptance_ready(run_id)
                if not ready:
                    raise FinalReviewRequired(why)
            if directive == "ESCALATE":
                request_type = (authority_request or {}).get("request_type")
                declared = run["contracts"]["stop_escalation"]["authority_request_types"]
                if request_type not in declared:
                    raise AuthorityDeniedError(
                        f"ESCALATE request type is not declared: {request_type!r}"
                    )
            node = nodes[target_node_id]
            if directive == "ACCEPT" and not (
                node["kind"] == "terminal_state" and node["outcome"] == "accepted"
            ):
                raise GovernedRuntimeError("ACCEPT must target an accepted terminal_state")
            if directive == "BLOCKED" and not (
                node["kind"] == "terminal_state" and node["outcome"] == "blocked"
            ):
                raise GovernedRuntimeError("BLOCKED must target a blocked terminal_state")

            record = {
                "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
                "object_family": "event_transition_record",
                "record_id": f"transition-{uuid.uuid4().hex}",
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "sequence": int(run["last_sequence"]) + 1,
                "recorded_at": self._now(),
                "node_id": run["current_node_id"],
                "record_type": "transition",
                "transition": {
                    "directive": directive,
                    "from_state": run["state"],
                    "to_state": _contracts.DIRECTIVE_TARGET_STATES[directive],
                    "reason": reason,
                    "evaluation_boundary": evaluation_boundary,
                    "target_node_id": target_node_id,
                },
                "evidence_refs": copy.deepcopy(list(evidence_refs)),
                "artifact_ids": list(run["artifact_ids"]),
            }
            if authority_request is not None:
                record["transition"]["authority_request"] = copy.deepcopy(dict(authority_request))
            _contracts.validate_event_transition_record(record)
            _append_jsonl(self._events_path(run_id), record)
            run["last_sequence"] = record["sequence"]
            run["updated_at"] = record["recorded_at"]
            run["state"] = record["transition"]["to_state"]
            run["current_node_id"] = target_node_id
            if directive in ("REPLAN", "REDEFINE"):
                run["contracts"]["correction_loop"]["attempt"] = 0
            _contracts.validate_process_run(run)
            _atomic_json(self._run_path(run_id), run)
            return copy.deepcopy(record)

    def dispatch_evaluated_failure(
        self,
        run_id: str,
        failure_class: str,
        *,
        target_node_id: str,
        reason: str,
        evaluation_boundary: str,
        authority_request: Mapping[str, Any] | None = None,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        directive = directive_for_failure_class(failure_class)
        return self.apply_transition(
            run_id,
            directive,
            target_node_id=target_node_id,
            reason=reason,
            evaluation_boundary=evaluation_boundary,
            authority_request=authority_request,
            evidence_refs=evidence_refs,
        )

    # ------------------------------------------------ checkpoint/recovery
    def _latest_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        for record in reversed(self.load_records(run_id)):
            event = record.get("event") or {}
            if event.get("event_type") == "checkpoint_created":
                return record
        return None

    def create_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        *,
        segment_id: str,
        resume_node_id: str,
    ) -> dict[str, Any]:
        with _locked():
            run = self.load_run(run_id)
            for record in self.load_records(run_id):
                event = record.get("event") or {}
                if (
                    event.get("event_type") == "checkpoint_created"
                    and (event.get("details") or {}).get("checkpoint_id") == checkpoint_id
                ):
                    raise RunConflictError(f"checkpoint already exists: {checkpoint_id}")
            definition = self.load_definition(run_id)
            node_ids = {node["node_id"] for node in definition["graph"]["nodes"]}
            if resume_node_id not in node_ids:
                raise GovernedRuntimeError(f"checkpoint resume node is not in graph: {resume_node_id}")
            records = self.load_records(run_id)
            latest = self._latest_checkpoint(run_id)
            after_sequence = latest["sequence"] if latest else 0
            if run["contracts"]["recovery"]["external_effect_receipts_required"]:
                for record in records:
                    if record["sequence"] <= after_sequence:
                        continue
                    event = record.get("event") or {}
                    details = event.get("details") or {}
                    if (
                        event.get("event_type") == "action_completed"
                        and details.get("external_effect")
                        and not details.get("receipt_artifact_id")
                    ):
                        raise RecoveryBlockedError(
                            "cannot checkpoint an external effect without its receipt"
                        )
                    if (
                        event.get("event_type") == "action_completed"
                        and details.get("external_effect")
                        and details.get("receipt_artifact_id")
                    ):
                        receipt = self.load_artifact(
                            run_id, details["receipt_artifact_id"]
                        )
                        if (
                            receipt["identity"]["digest"]
                            != details.get("receipt_identity_digest")
                        ):
                            raise RecoveryBlockedError(
                                "cannot checkpoint an external effect with a changed receipt"
                            )
            artifact_identities = {}
            receipt_ids = []
            for artifact_id in run["artifact_ids"]:
                artifact = self.load_artifact(run_id, artifact_id)
                artifact_identities[artifact_id] = artifact["identity"]["digest"]
                if artifact["role"] == "external_effect_receipt":
                    receipt_ids.append(artifact_id)
            run["contracts"]["continuation"]["checkpoint_id"] = checkpoint_id
            run["contracts"]["continuation"]["resume_node_id"] = resume_node_id
            return self._append_event_locked(
                run,
                "checkpoint_created",
                {
                    "checkpoint_id": checkpoint_id,
                    "segment_id": segment_id,
                    "resume_node_id": resume_node_id,
                    "state": run["state"],
                    "attempt": run["contracts"]["correction_loop"]["attempt"],
                    "artifact_identities": artifact_identities,
                    "external_effect_receipt_ids": sorted(receipt_ids),
                    "replay_mutations": False,
                },
                node_id=run["current_node_id"],
                artifact_ids=run["artifact_ids"],
                runtime_authoritative=True,
            )

    def pause_run(
        self,
        run_id: str,
        checkpoint_id: str,
        *,
        segment_id: str,
        resume_node_id: str,
        reason: str,
    ) -> dict[str, Any]:
        if self.load_run(run_id)["state"] not in ("ready", "running"):
            raise RunConflictError("only a ready or running Process Run can pause")
        checkpoint = self.create_checkpoint(
            run_id,
            checkpoint_id,
            segment_id=segment_id,
            resume_node_id=resume_node_id,
        )
        with _locked():
            run = self.load_run(run_id)
            run["state"] = "pending"
            paused = self._append_event_locked(
                run,
                "run_paused",
                {"checkpoint_id": checkpoint_id, "reason": reason},
                node_id=run["current_node_id"],
                runtime_authoritative=True,
            )
        return {"checkpoint": checkpoint, "pause": paused}

    def recovery_decision(self, run_id: str) -> dict[str, Any]:
        run = self.load_run(run_id)
        checkpoint = self._latest_checkpoint(run_id)
        if checkpoint is None:
            return {
                "safe_to_resume": False,
                "replay_mutations": False,
                "reason": "no checkpoint exists",
                "resume_node_id": None,
                "revalidate_evidence_ids": [],
            }
        details = checkpoint["event"]["details"]
        for record in self.load_records(run_id):
            if record["sequence"] <= checkpoint["sequence"]:
                continue
            event = record.get("event") or {}
            action = event.get("details") or {}
            if (
                event.get("event_type") == "action_completed"
                and action.get("external_effect")
                and not action.get("receipt_artifact_id")
            ):
                return {
                    "safe_to_resume": False,
                    "replay_mutations": False,
                    "reason": "external effect after checkpoint lacks a receipt",
                    "resume_node_id": details["resume_node_id"],
                    "revalidate_evidence_ids": [],
                }
            if (
                event.get("event_type") == "action_completed"
                and action.get("external_effect")
                and action.get("receipt_artifact_id")
            ):
                receipt_id = str(action["receipt_artifact_id"])
                try:
                    receipt = self.load_artifact(run_id, receipt_id)
                except GovernedRuntimeError:
                    return {
                        "safe_to_resume": False,
                        "replay_mutations": False,
                        "reason": "post-checkpoint external-effect receipt is missing or changed",
                        "resume_node_id": details["resume_node_id"],
                        "changed_artifact_ids": [receipt_id],
                        "revalidate_evidence_ids": [],
                    }
                if receipt["identity"]["digest"] != action.get("receipt_identity_digest"):
                    return {
                        "safe_to_resume": False,
                        "replay_mutations": False,
                        "reason": "post-checkpoint external-effect receipt identity changed",
                        "resume_node_id": details["resume_node_id"],
                        "changed_artifact_ids": [receipt_id],
                        "revalidate_evidence_ids": [],
                    }
        changed = []
        for artifact_id, digest in details.get("artifact_identities", {}).items():
            try:
                current = self.load_artifact(run_id, artifact_id)
            except RunNotFoundError:
                changed.append(artifact_id)
                continue
            if current["identity"]["digest"] != digest:
                changed.append(artifact_id)
        changed_receipts = sorted(
            set(changed) & set(details.get("external_effect_receipt_ids") or [])
        )
        if changed_receipts:
            return {
                "safe_to_resume": False,
                "replay_mutations": False,
                "reason": "external-effect receipt identity changed after checkpoint",
                "resume_node_id": details["resume_node_id"],
                "changed_artifact_ids": sorted(changed),
                "revalidate_evidence_ids": [],
            }
        return {
            "safe_to_resume": True,
            "replay_mutations": False,
            "reason": "checkpoint is complete; resume without replaying prior actions",
            "resume_node_id": details["resume_node_id"],
            "changed_artifact_ids": sorted(changed),
            "revalidate_evidence_ids": (
                list(run["contracts"]["recovery"]["revalidation_evidence_ids"])
                if changed
                else []
            ),
        }

    def resume_run(self, run_id: str) -> dict[str, Any]:
        if self.load_run(run_id)["state"] not in ("pending", "running"):
            raise RunConflictError("only a pending or interrupted running Process Run can resume")
        decision = self.recovery_decision(run_id)
        if not decision["safe_to_resume"]:
            raise RecoveryBlockedError(decision["reason"])
        with _locked():
            run = self.load_run(run_id)
            run["state"] = "running"
            run["current_node_id"] = decision["resume_node_id"]
            record = self._append_event_locked(
                run,
                "run_resumed",
                {
                    "resume_node_id": decision["resume_node_id"],
                    "replay_mutations": False,
                    "revalidate_evidence_ids": decision["revalidate_evidence_ids"],
                },
                node_id=decision["resume_node_id"],
                runtime_authoritative=True,
            )
            return {"decision": decision, "record": record}

    # ---------------------------------------------------------- child runs
    def _child_output_binding(
        self,
        child_run_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        child = self.load_run(child_run_id)
        artifact = self.load_artifact(child_run_id, artifact_id)
        if artifact["role"] != "result":
            raise GovernedRuntimeError("child return outputs must be result Artifacts")
        if artifact["lineage"]["definition_ref"] != child["definition_ref"]:
            raise GovernedRuntimeError(
                "child output Artifact does not bind the child definition identity"
            )
        required_evidence_ids = sorted(
            requirement["evidence_id"]
            for requirement in child["contracts"]["evidence"]["requirements"]
            if requirement["required"]
        )
        acceptance_evidence = []
        for evidence_id in required_evidence_ids:
            review_record = self._current_passing_review(
                child_run_id, artifact_id, evidence_id
            )
            review = review_record["event"]["details"]
            acceptance_evidence.append({
                "evidence_id": evidence_id,
                "outcome": "PASS",
                "subject_digest": review["subject_digest"],
                "evidence_artifact_id": review["evidence_artifact_id"],
                "evidence_digest": review["evidence_digest"],
                "review_record_id": review_record["record_id"],
                "reviewer_id": review["reviewer_id"],
                "independent": bool(review["independent"]),
            })
        acceptance_record = None
        for record in reversed(self.load_records(child_run_id)):
            transition = record.get("transition") or {}
            if transition.get("directive") == "ACCEPT":
                acceptance_record = record
                break
        if acceptance_record is None:
            raise GovernedRuntimeError(
                "completed child Run lacks its persisted ACCEPT transition"
            )
        accepted_refs = [
            copy.deepcopy(ref)
            for ref in acceptance_record["evidence_refs"]
            if ref.get("artifact_id") == artifact_id
        ]
        expected_ref_ids = {(artifact_id, evidence_id) for evidence_id in required_evidence_ids}
        actual_ref_ids = {
            (str(ref.get("artifact_id")), str(ref.get("evidence_id")))
            for ref in accepted_refs
        }
        if actual_ref_ids != expected_ref_ids or any(
            ref.get("outcome") != "PASS" for ref in accepted_refs
        ):
            raise GovernedRuntimeError(
                "child ACCEPT transition does not bind current PASS evidence for its output"
            )
        return {
            "artifact_id": artifact_id,
            "producing_run_id": child_run_id,
            "definition_ref": copy.deepcopy(child["definition_ref"]),
            "identity_digest": artifact["identity"]["digest"],
            "role": artifact["role"],
            "acceptance_evidence": acceptance_evidence,
            "acceptance_transition": {
                "record_id": acceptance_record["record_id"],
                "recorded_at": acceptance_record["recorded_at"],
                "directive": "ACCEPT",
                "evidence_refs": accepted_refs,
            },
        }

    def _validate_child_output_binding(self, binding: Mapping[str, Any]) -> None:
        required_fields = {
            "artifact_id",
            "producing_run_id",
            "definition_ref",
            "identity_digest",
            "role",
            "acceptance_evidence",
            "acceptance_transition",
        }
        if set(binding) != required_fields:
            raise GovernedRuntimeError("child output identity binding is incomplete")
        producing_run_id = str(binding["producing_run_id"])
        artifact_id = str(binding["artifact_id"])
        child = self.load_run(producing_run_id)
        if child["state"] != "completed":
            raise GovernedRuntimeError(
                "returned child output no longer belongs to a completed Run"
            )
        current = self._child_output_binding(producing_run_id, artifact_id)
        if current != dict(binding):
            raise GovernedRuntimeError(
                f"returned child Artifact identity or acceptance evidence changed: {artifact_id}"
            )

    def invoke_child(
        self,
        parent_run_id: str,
        child_definition: Mapping[str, Any],
        child_run: Mapping[str, Any],
        *,
        call_node_id: str,
        satisfied_conditions: Sequence[str] = (),
    ) -> dict[str, Any]:
        parent = self.load_run(parent_run_id)
        definition = self.load_definition(parent_run_id)
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        call_node = nodes.get(call_node_id)
        if not call_node or call_node["kind"] != "process_call":
            raise GovernedRuntimeError("child invocation must originate at a process_call node")
        if parent["current_node_id"] != call_node_id or parent["state"] != "running":
            raise GovernedRuntimeError(
                "parent Process Run must be running at the process_call node"
            )
        child_ref = {
            "definition_id": child_definition["definition_id"],
            "version": child_definition["version"],
            "digest": child_definition["digest"],
        }
        if call_node["definition_ref"] != child_ref:
            raise GovernedRuntimeError("process_call does not bind the supplied child definition")
        selector = f"definition:{child_ref['definition_id']}@{child_ref['version']}"
        self.authorize_action(
            parent_run_id,
            "invoke_process",
            [selector],
            satisfied_conditions=satisfied_conditions,
            effect_type="local_reversible",
        )
        child_copy = copy.deepcopy(dict(child_run))
        child_copy["relationships"]["parent_run_id"] = parent_run_id
        child_copy["relationships"]["invoked_by_run_id"] = parent_run_id
        child_copy["relationships"]["return_to_run_id"] = parent_run_id
        child_copy["contracts"]["continuation"]["parent_run_id"] = parent_run_id
        self.create_checkpoint(
            parent_run_id,
            f"call-{child_copy['run_id']}",
            segment_id=call_node_id,
            resume_node_id=call_node["return_node_id"],
        )
        self.create_run(child_definition, child_copy)
        with _locked():
            parent = self.load_run(parent_run_id)
            if child_ref not in parent["relationships"]["invoked_definition_refs"]:
                parent["relationships"]["invoked_definition_refs"].append(child_ref)
            child_ids = parent["contracts"]["continuation"]["child_run_ids"]
            if child_copy["run_id"] not in child_ids:
                child_ids.append(child_copy["run_id"])
            parent["state"] = "pending"
            record = self._append_event_locked(
                parent,
                "process_invoked",
                {
                    "child_run_id": child_copy["run_id"],
                    "child_definition_ref": child_ref,
                    "call_node_id": call_node_id,
                    "return_node_id": call_node["return_node_id"],
                },
                node_id=call_node_id,
                runtime_authoritative=True,
            )
            return {"child_run": self.load_run(child_copy["run_id"]), "parent_record": record}

    def return_child(
        self,
        child_run_id: str,
        *,
        output_artifact_ids: Sequence[str],
    ) -> dict[str, Any]:
        child = self.load_run(child_run_id)
        if child["state"] != "completed":
            raise GovernedRuntimeError("child Process Run must be completed before return")
        parent_run_id = child["relationships"]["return_to_run_id"]
        if not parent_run_id:
            raise GovernedRuntimeError("child Process Run has no deterministic return target")
        if not output_artifact_ids:
            raise GovernedRuntimeError(
                "child return requires at least one identity-bound output Artifact"
            )
        if len(output_artifact_ids) != len(set(output_artifact_ids)):
            raise GovernedRuntimeError("child return output Artifact IDs must be unique")
        output_bindings = [
            self._child_output_binding(child_run_id, artifact_id)
            for artifact_id in output_artifact_ids
        ]
        invocation = None
        for record in reversed(self.load_records(parent_run_id)):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") == "process_invoked" and details.get("child_run_id") == child_run_id:
                invocation = details
                break
        if invocation is None:
            raise GovernedRuntimeError("parent has no invocation record for child")
        if invocation.get("child_definition_ref") != child["definition_ref"]:
            raise GovernedRuntimeError(
                "child return does not match the invoked definition identity"
            )
        parent_return_record = None
        for record in self.load_records(parent_run_id):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "child_return_received"
                and details.get("child_run_id") == child_run_id
            ):
                parent_return_record = record
                break
        child_return_record = None
        for record in self.load_records(child_run_id):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if (
                event.get("event_type") == "process_returned"
                and details.get("parent_run_id") == parent_run_id
            ):
                child_return_record = record
                break
        exact_return = {
            "child_definition_ref": copy.deepcopy(child["definition_ref"]),
            "output_artifact_ids": list(output_artifact_ids),
            "output_bindings": output_bindings,
        }
        for existing in (parent_return_record, child_return_record):
            if existing is None:
                continue
            prior = existing["event"]["details"]
            if (
                prior.get("child_definition_ref") != exact_return["child_definition_ref"]
                or prior.get("output_artifact_ids") != exact_return["output_artifact_ids"]
                or prior.get("output_bindings") != exact_return["output_bindings"]
            ):
                raise RunConflictError(
                    "recovered child return must preserve exact definition, output, "
                    "and acceptance-evidence bindings"
                )
        if parent_return_record is not None and child_return_record is not None:
            raise RunConflictError("child Process Run has already returned")
        with _locked():
            parent = self.load_run(parent_run_id)
            if child_run_id not in parent["contracts"]["continuation"]["child_run_ids"]:
                raise GovernedRuntimeError("parent continuation contract does not bind child")
            if parent_return_record is None:
                if parent["state"] != "pending":
                    raise RunConflictError(
                        "parent Process Run must be pending when its child returns"
                    )
                local_collisions = sorted(
                    set(output_artifact_ids) & set(parent["artifact_ids"])
                )
                returned_collisions = sorted(
                    set(output_artifact_ids)
                    & set(self._returned_child_artifact_bindings(parent_run_id))
                )
                collisions = sorted(set(local_collisions + returned_collisions))
                if collisions:
                    raise GovernedRuntimeError(
                        "child return Artifact ID collision: " + ", ".join(collisions)
                    )
                parent["current_node_id"] = invocation["return_node_id"]
                parent["state"] = "running"
                parent_record = self._append_event_locked(
                    parent,
                    "child_return_received",
                    {
                        "child_run_id": child_run_id,
                        "return_node_id": invocation["return_node_id"],
                        **exact_return,
                        "replay_mutations": False,
                    },
                    node_id=invocation["return_node_id"],
                    artifact_ids=output_artifact_ids,
                    runtime_authoritative=True,
                )
            else:
                parent_record = parent_return_record
            child = self.load_run(child_run_id)
            if child_return_record is None:
                child_record = self._append_event_locked(
                    child,
                    "process_returned",
                    {
                        "parent_run_id": parent_run_id,
                        "return_node_id": invocation["return_node_id"],
                        **exact_return,
                    },
                    node_id=child["current_node_id"],
                    artifact_ids=output_artifact_ids,
                    allow_terminal_metadata=True,
                    runtime_authoritative=True,
                )
            else:
                child_record = child_return_record
            return {"parent_record": parent_record, "child_record": child_record}


__all__ = [
    "AuthorityDeniedError",
    "CorrectionDecisionRequired",
    "DEFAULT_CORRECTION_POLICY",
    "DIRECTIVE_SOURCE_STATES",
    "FAILURE_CLASS_DIRECTIVES",
    "FinalReviewRequired",
    "GovernedProcessRuntime",
    "GovernedRuntimeError",
    "INITIAL_RUN_STATES",
    "INFRASTRUCTURE_OUTCOMES",
    "PROCESS_RUNS_DIR",
    "PROCESS_RUNS_ENV",
    "RecoveryBlockedError",
    "RESERVED_RUNTIME_EVENT_TYPES",
    "RunConflictError",
    "RunNotFoundError",
    "TERMINAL_RUN_STATES",
    "correction_policy_defaults",
    "directive_for_failure_class",
]
