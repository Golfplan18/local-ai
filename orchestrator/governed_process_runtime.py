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
import stat
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from . import process_contracts as _contracts
except ImportError:  # pragma: no cover - direct module execution
    import process_contracts as _contracts

try:
    from . import runtime_paths as _runtime_paths
except ImportError:  # pragma: no cover - direct module execution
    import runtime_paths as _runtime_paths

try:
    from .process_definition_registry import ProcessDefinitionRegistry
except ImportError:  # pragma: no cover - direct module execution
    from process_definition_registry import ProcessDefinitionRegistry


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
    "node_advanced",
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
    "controlled_probe_execution_started",
    "controlled_probe_execution_completed",
    "controlled_probe_attempt_completed",
    "controlled_probe_withheld",
    "dialogue_observation_recorded",
    "run_contracts_replaced",
    "delegation_activated",
    "external_action_authorized",
    "repository_state_captured",
    "repository_mutation_receipt_issued",
    "authority_request_resolved",
    "manual_process_invoked",
    "manual_process_output_captured",
    "manual_process_result_recorded",
    "process_invoked",
    "process_definition_registered",
    "process_worker_started",
    "process_worker_finished",
    "process_run_control_requested",
    "process_run_control_applied",
    "process_quality_evaluation_started",
    "process_quality_evaluation_completed",
    "process_quality_evaluation_failed",
    "automation_authoring_proposed",
    "automation_authoring_revision_requested",
    "isolated_process_step_completed",
    "isolated_process_verification_started",
    "isolated_process_verification_failed",
    "isolated_process_verification_completed",
    "child_return_received",
    "process_returned",
    "lifecycle_disposition_recorded",
})

_RESERVED_RUNTIME_EVENT_PREFIXES = (
    "action_",
    "artifact_",
    "attempt_",
    "automation_",
    "checkpoint_",
    "child_",
    "controlled_probe_",
    "dialogue_",
    "infrastructure_",
    "invocation_",
    "isolated_process_",
    "lifecycle_",
    "node_",
    "process_",
    "repository_",
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

_READ_ONLY_INSPECTION_SANDBOX_PROFILE = """(version 1)
(deny default)
(allow file-read*)
(allow process-exec)
(allow sysctl-read)
"""

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


class ControlledProbeExecutionError(GovernedRuntimeError):
    """A runtime-owned probe invocation failed before an execution record."""

    def __init__(self, message: str, *, external_effect_possible: bool = False):
        super().__init__(message)
        self.external_effect_possible = bool(external_effect_possible)


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


def lifecycle_disposition_idempotency_key(
    run_id: str,
    disposition: str,
    promoted_definition_ref: Mapping[str, Any] | None = None,
    capability_artifact_id: str | None = None,
) -> str:
    """Return the bounded identity for one exact terminal disposition request."""

    basis = {
        "run_id": str(run_id),
        "disposition": str(disposition),
        "promoted_definition_ref": (
            copy.deepcopy(dict(promoted_definition_ref))
            if promoted_definition_ref is not None else None
        ),
        "capability_artifact_id": capability_artifact_id,
    }
    body = json.dumps(
        basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "lifecycle:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


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


def _git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise GovernedRuntimeError(
            "live Git identity command failed: "
            + " ".join(args)
            + ": "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _capture_repository_composite_v1(root: Path) -> dict[str, Any]:
    """Reproduce the issued Phase 1.7 repository-composite identity.

    The Part 1 trial predates the planning target-composite schema.  Its issued
    Artifact identity remains valid and therefore needs an explicit verifier,
    rather than being silently reinterpreted as the later schema.
    """

    head = _git_bytes(root, "rev-parse", "HEAD").decode().strip()
    status = _git_bytes(
        root, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    listed = _git_bytes(
        root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    )
    entries: list[dict[str, Any]] = []
    for raw_name in sorted(item for item in listed.split(b"\0") if item):
        relative = os.fsdecode(raw_name)
        path = root / relative
        if path.is_symlink():
            kind = "symlink"
            digest = _digest_text(os.readlink(path))
            mode = None
        else:
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise GovernedRuntimeError(
                    f"live repository identity does not support {relative!r}"
                )
            kind = "file"
            digest = _digest_file(path)
            mode = oct(info.st_mode & 0o777)
        entries.append({
            "path": relative,
            "kind": kind,
            "mode": mode,
            "digest": digest,
        })
    return {
        "schema_version": "ora.repository-composite/1.0",
        "repository": str(root),
        "git_head": head,
        "git_status_digest": "sha256:" + hashlib.sha256(status).hexdigest(),
        "worktree_entries": entries,
    }


def inspect_live_artifact_identity(
    artifact: Mapping[str, Any],
    *,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Compare one persisted Artifact with the live resource it names.

    This is deliberately read-only.  It supports the content-bound local
    identity schemas Ora has actually issued.  Unsupported or unavailable
    live resources fail closed for current-evidence purposes while remaining
    valid historical Artifacts in the append-only Run.
    """

    candidate = _contracts.validate_artifact(artifact)
    locator = candidate["locator"]
    identity = candidate["identity"]
    result: dict[str, Any] = {
        "applicable": False,
        "supported": False,
        "available": True,
        "matches": None,
        "expected_digest": identity["digest"],
        "current_digest": None,
        "locator": copy.deepcopy(locator),
        "current_state": None,
        "reason": "Artifact locator has no live local identity boundary.",
    }
    if locator["kind"] not in {"file", "git_ref"}:
        return result
    result["applicable"] = True
    raw_ref = str(locator["ref"])
    supplied = Path(raw_ref)
    try:
        if not supplied.is_absolute() or supplied.is_symlink():
            raise GovernedRuntimeError(
                "live Artifact locator must be an absolute nonsymlink path"
            )
        target = supplied.resolve(strict=True)
        if str(target) != raw_ref:
            raise GovernedRuntimeError(
                "live Artifact locator must be its canonical resolved path"
            )
        if identity["kind"] == "content_digest" and target.is_file():
            current_digest = _digest_file(target)
            state = {"kind": "file_content", "path": str(target)}
        elif identity["kind"] == "composite" and target.is_dir():
            coverage = set(identity["coverage"])
            if coverage == {"git_head", "git_status", "nonignored_worktree_files"}:
                state = _capture_repository_composite_v1(target)
                current_digest = _digest_json(state)
            elif {
                "exact_target_root", "tracked_state", "unstaged_state",
                "untracked_state", "declared_exclusions",
            }.issubset(coverage):
                try:
                    from process_plan_approval import capture_target_identity
                except ImportError:  # pragma: no cover
                    from orchestrator.process_plan_approval import capture_target_identity
                capture = capture_target_identity(
                    str(target), captured_at=captured_at or _utc_now()
                )
                state = capture["state"]
                current_digest = capture["identity"]["digest"]
            else:
                result["reason"] = (
                    "Artifact uses an unsupported live composite identity schema."
                )
                return result
        else:
            result["reason"] = (
                "Artifact identity kind does not match the live local resource."
            )
            return result
    except (OSError, RuntimeError) as exc:
        result.update({
            "supported": True,
            "available": False,
            "matches": False,
            "reason": f"Live Artifact resource is unavailable: {exc}",
        })
        return result
    result.update({
        "supported": True,
        "available": True,
        "matches": current_digest == identity["digest"],
        "current_digest": current_digest,
        "current_state": state,
        "reason": (
            "Live resource matches the persisted Artifact identity."
            if current_digest == identity["digest"]
            else "Live resource changed after the persisted Artifact identity was captured."
        ),
    })
    return result


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
                elif event_type == "node_advanced":
                    materialized["current_node_id"] = details["to_node_id"]
                elif event_type == "authority_request_resolved":
                    # The authority decision is committed before its declared
                    # graph edge.  Recovering that record must make the same
                    # edge resumable without replaying the human decision.
                    materialized["state"] = "running"
                    materialized["current_node_id"] = details["source_node_id"]
                elif event_type == "run_contracts_replaced":
                    materialized["contracts"] = copy.deepcopy(details["contracts"])
                    materialized["labels"] = list(details["labels"])
                elif event_type == "delegation_activated":
                    materialized["contracts"] = copy.deepcopy(details["contracts"])
                    materialized["labels"] = list(details["labels"])
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
            if (
                not runtime_authoritative
                or event_type not in {
                    "process_returned", "lifecycle_disposition_recorded",
                    "process_quality_evaluation_started",
                    "process_quality_evaluation_completed",
                    "process_quality_evaluation_failed",
                }
            ):
                raise GovernedRuntimeError(
                    "only deterministic return, lifecycle, or read-only quality "
                    "observation records are safe terminal metadata"
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

    def record_process_quality_evaluation(
        self,
        run_id: str,
        event_type: str,
        details: Mapping[str, Any],
        *,
        node_id: str,
    ) -> dict[str, Any]:
        """Persist one authority-inert, exact-subject G1.20 evaluation record."""

        if event_type not in {
            "process_quality_evaluation_started",
            "process_quality_evaluation_completed",
            "process_quality_evaluation_failed",
        }:
            raise GovernedRuntimeError("process quality event type is invalid")
        body = copy.deepcopy(dict(details))
        common = {
            "run_id", "definition_ref", "evaluation_id", "idempotency_key",
            "subject_digest", "eligible_reason", "source_record_id", "source_sequence",
            "evaluator_binding",
        }
        expected = set(common)
        if event_type == "process_quality_evaluation_completed":
            expected |= {"evaluation_start_record_id", "response_digest", "verdict"}
        elif event_type == "process_quality_evaluation_failed":
            expected |= {"evaluation_start_record_id", "error_type", "error_digest"}
        if set(body) != expected:
            raise GovernedRuntimeError("process quality event fields are invalid")
        run = self.load_run(run_id)
        if (
            body.get("run_id") != run_id
            or body.get("definition_ref") != run["definition_ref"]
            or body.get("eligible_reason") not in {"human_handoff", "output_failure"}
            or not isinstance(body.get("source_sequence"), int)
            or body["source_sequence"] < 1
            or not isinstance(body.get("source_record_id"), str)
            or not body["source_record_id"]
            or not isinstance(body.get("evaluator_binding"), Mapping)
        ):
            raise GovernedRuntimeError("process quality event binding is invalid")
        _exact_digest(str(body.get("subject_digest") or ""), "quality subject")
        if event_type == "process_quality_evaluation_completed":
            _exact_digest(str(body.get("response_digest") or ""), "quality response")
            verdict = body.get("verdict")
            if (
                not isinstance(verdict, Mapping)
                or set(verdict) != {
                    "verdict", "drift_verdict", "quality_verdict",
                    "findings", "rationale",
                }
                or verdict.get("verdict") not in {
                    "PASS", "WARN", "FAIL", "INDETERMINATE",
                }
                or verdict.get("drift_verdict") not in {
                    "NONE", "POSSIBLE", "PRESENT", "INDETERMINATE",
                }
                or verdict.get("quality_verdict") not in {
                    "PASS", "WARN", "FAIL", "INDETERMINATE",
                }
                or not isinstance(verdict.get("findings"), list)
                or not all(isinstance(item, str) for item in verdict["findings"])
                or not isinstance(verdict.get("rationale"), str)
            ):
                raise GovernedRuntimeError("process quality verdict is invalid")
            if body["response_digest"] != _digest_json(verdict):
                raise GovernedRuntimeError(
                    "process quality response digest does not match the verdict"
                )
        with _locked():
            current = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if node_id not in {
                node["node_id"] for node in definition["graph"]["nodes"]
            }:
                raise GovernedRuntimeError("quality event node is outside the definition")
            records = self.load_records(run_id)
            if event_type == "process_quality_evaluation_started":
                source = next(
                    (
                        record for record in records
                        if record["record_id"] == body["source_record_id"]
                        and record["sequence"] == body["source_sequence"]
                    ),
                    None,
                )
                if source is None:
                    raise GovernedRuntimeError(
                        "process quality start does not bind its exact source record"
                    )
                if any(
                    (record.get("event") or {}).get("event_type")
                    == "process_quality_evaluation_started"
                    and (
                        (record.get("event") or {}).get("details", {}).get(
                            "evaluation_id"
                        ) == body["evaluation_id"]
                        or (record.get("event") or {}).get("details", {}).get(
                            "idempotency_key"
                        ) == body["idempotency_key"]
                    )
                    for record in records
                ):
                    raise RunConflictError(
                        "process quality evaluation identity already exists"
                    )
                nodes = self._graph_nodes(definition)
                if body["eligible_reason"] == "human_handoff":
                    if not (
                        current["state"] == "pending"
                        and nodes[current["current_node_id"]]["kind"]
                        == "human_checkpoint"
                        and node_id == current["current_node_id"]
                    ):
                        raise AuthorityDeniedError(
                            "quality evaluation is not at a current human handoff"
                        )
                else:
                    source_event = source.get("event") or {}
                    source_details = source_event.get("details") or {}
                    output_failure = bool(
                        (
                            source_event.get("event_type") == "attempt_completed"
                            and source_details.get("defect_codes")
                        )
                        or source_event.get("event_type")
                        == "isolated_process_verification_failed"
                        or (
                            source_event.get("event_type")
                            in {
                                "isolated_process_verification_completed",
                                "final_review_completed",
                            }
                            and source_details.get("outcome") != "PASS"
                        )
                    )
                    if not output_failure:
                        raise AuthorityDeniedError(
                            "quality evaluation source is not an output failure"
                        )
            else:
                starts = [
                    record for record in records
                    if (record.get("event") or {}).get("event_type")
                    == "process_quality_evaluation_started"
                    and record["record_id"]
                    == body.get("evaluation_start_record_id")
                ]
                outcomes = [
                    record for record in records
                    if (record.get("event") or {}).get("event_type") in {
                        "process_quality_evaluation_completed",
                        "process_quality_evaluation_failed",
                    }
                    and (record.get("event") or {}).get("details", {}).get(
                        "evaluation_start_record_id"
                    ) == body.get("evaluation_start_record_id")
                ]
                if len(starts) != 1 or outcomes:
                    raise RunConflictError(
                        "quality outcome lacks one unfinished exact start"
                    )
                start_details = starts[0]["event"]["details"]
                if any(
                    body.get(field) != start_details.get(field)
                    for field in common
                ):
                    raise GovernedRuntimeError(
                        "quality outcome does not authenticate its exact start"
                    )
                if node_id != starts[0]["node_id"]:
                    raise GovernedRuntimeError(
                        "quality outcome node differs from its exact start"
                    )
            return self._append_event_locked(
                current,
                event_type,
                body,
                node_id=node_id,
                allow_terminal_metadata=current["state"] in TERMINAL_RUN_STATES,
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

    def record_automation_authoring_event(
        self,
        run_id: str,
        event_type: str,
        details: Mapping[str, Any],
        *,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist one exact, retry-safe Process-authoring decision record.

        G1.18 authoring lives on the existing management Run.  This dedicated
        boundary prevents the public observation API from minting proposals or
        revisions and makes concurrent delivery of one identity exactly-once.
        """

        if event_type not in {
            "automation_authoring_proposed",
            "automation_authoring_revision_requested",
        }:
            raise GovernedRuntimeError("unsupported automation authoring event type")
        supplied = copy.deepcopy(dict(details))
        _require_json(supplied, "automation authoring event details")
        identity_fields = (
            ("idempotency_key",)
            if event_type == "automation_authoring_proposed"
            else ("proposal_id", "proposal_digest", "reason_digest")
        )
        if any(not supplied.get(field) for field in identity_fields):
            raise GovernedRuntimeError(
                "automation authoring event lacks its exact retry identity"
            )
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            target = node_id or run["current_node_id"]
            if target not in {node["node_id"] for node in definition["graph"]["nodes"]}:
                raise GovernedRuntimeError(
                    f"event node is not in the Process Definition: {target}"
                )
            matches = []
            for record in self.load_records(run_id):
                event = record.get("event") or {}
                persisted = event.get("details") or {}
                if event.get("event_type") != event_type:
                    continue
                if all(
                    persisted.get(field) == supplied.get(field)
                    for field in identity_fields
                ):
                    matches.append(record)
            if len(matches) > 1:
                raise GovernedRuntimeError(
                    "automation authoring retry identity has multiple persisted records"
                )
            if matches:
                if (matches[0].get("event") or {}).get("details") != supplied:
                    raise RunConflictError(
                        "automation authoring retry identity was reused with different content"
                    )
                return matches[0]
            return self._append_event_locked(
                run,
                event_type,
                supplied,
                node_id=target,
                runtime_authoritative=True,
            )

    def bind_manual_process_invocation(
        self,
        run_id: str,
        *,
        invocation_id: str,
        dialogue_ref: str,
        project_ref: str,
        objective: str,
        definition_inputs: Mapping[str, Any],
        definition_input_digest: str,
        entry_contract_digest: str,
        request_context_digest: str,
    ) -> dict[str, Any]:
        """Persist one exact top-level manual invocation before execution."""

        body = {
            "invocation_id": str(invocation_id),
            "dialogue_ref": str(dialogue_ref),
            "project_ref": str(project_ref),
            "objective": str(objective),
            "definition_inputs": copy.deepcopy(dict(definition_inputs)),
            "definition_input_digest": str(definition_input_digest),
            "entry_contract_digest": str(entry_contract_digest),
            "request_context_digest": str(request_context_digest),
        }
        for field in (
            "invocation_id", "dialogue_ref", "project_ref", "objective",
            "definition_input_digest", "entry_contract_digest",
            "request_context_digest",
        ):
            if not body[field]:
                raise GovernedRuntimeError(
                    f"manual Process invocation requires {field}"
                )
        _exact_digest(
            body["definition_input_digest"], "definition_input_digest"
        )
        _exact_digest(body["entry_contract_digest"], "entry_contract_digest")
        _exact_digest(body["request_context_digest"], "request_context_digest")
        _require_json(body["definition_inputs"], "definition_inputs")

        with _locked():
            run = self.load_run(run_id)
            if run["input_bindings"] != body:
                raise RunConflictError(
                    "manual invocation differs from the persisted Run inputs"
                )
            details_body = {
                **body,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "entry_node_id": self.load_definition(run_id)["graph"][
                    "entry_node_id"
                ],
            }
            details = {
                **details_body,
                "invocation_digest": _digest_json(details_body),
            }
            existing = [
                record for record in self.load_records(run_id)
                if (record.get("event") or {}).get("event_type")
                == "manual_process_invoked"
            ]
            if len(existing) > 1:
                raise GovernedRuntimeError(
                    "Process Run has multiple manual invocation records"
                )
            if existing:
                if existing[0]["event"]["details"] != details:
                    raise RunConflictError(
                        "manual invocation record differs from the exact request"
                    )
                return copy.deepcopy(existing[0])
            if run["state"] != "ready":
                raise RunConflictError(
                    "manual invocation must be bound before the Process Run starts"
                )
            return self._append_event_locked(
                run,
                "manual_process_invoked",
                details,
                node_id=run["current_node_id"],
                runtime_authoritative=True,
            )

    def record_manual_process_result(
        self,
        run_id: str,
        *,
        invocation_record_id: str,
        result_artifact_id: str,
        evidence_artifact_id: str,
        response_text: str,
    ) -> dict[str, Any]:
        """Bind a pipeline response to exact result and execution evidence."""

        if not response_text:
            raise GovernedRuntimeError(
                "manual Process result requires a non-empty response"
            )
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            records = self.load_records(run_id)
            invocations = [
                record for record in records
                if record["record_id"] == invocation_record_id
                and (record.get("event") or {}).get("event_type")
                == "manual_process_invoked"
            ]
            if len(invocations) != 1:
                raise GovernedRuntimeError(
                    "manual result lacks its exact runtime invocation record"
                )
            invocation = invocations[0]
            entry_node_id = str(
                invocation["event"]["details"].get("entry_node_id") or ""
            )
            nodes = self._graph_nodes(definition)
            entry_node = nodes.get(entry_node_id)
            if (
                entry_node is None
                or entry_node.get("kind") != "action"
                or entry_node.get("external_effect") is not False
                or run["current_node_id"] != entry_node.get("next_node_id")
                or nodes[run["current_node_id"]].get("kind")
                != "verification_boundary"
            ):
                raise GovernedRuntimeError(
                    "manual result is outside its exact non-external execution path"
                )
            result = self.load_artifact(run_id, result_artifact_id)
            evidence = self.load_artifact(run_id, evidence_artifact_id)
            if (
                result["role"] != "result"
                or result["identity"]["digest"] != _digest_text(response_text)
                or evidence["role"] != "evidence"
                or result_artifact_id
                not in evidence["lineage"]["source_artifact_ids"]
                or result["lineage"]["producing_node_id"] != entry_node_id
                or evidence["lineage"]["producing_node_id"]
                != run["current_node_id"]
            ):
                raise GovernedRuntimeError(
                    "manual result and execution evidence identities do not bind"
                )
            started = [
                record for record in records
                if (record.get("event") or {}).get("event_type") == "run_started"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "entry_node_id"
                ) == entry_node_id
            ]
            captures = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "manual_process_output_captured"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "invocation_record_id"
                ) == invocation_record_id
                and ((record.get("event") or {}).get("details") or {}).get(
                    "response_digest"
                ) == _digest_text(response_text)
            ]
            result_artifact_records = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "artifact_recorded"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "artifact_id"
                ) == result_artifact_id
            ]
            action_advances = [
                record for record in records
                if (record.get("event") or {}).get("event_type") == "node_advanced"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "from_node_id"
                ) == entry_node_id
                and ((record.get("event") or {}).get("details") or {}).get(
                    "to_node_id"
                ) == run["current_node_id"]
                and ((record.get("event") or {}).get("details") or {}).get(
                    "advance_kind"
                ) == "action"
                and (((record.get("event") or {}).get("details") or {}).get(
                    "route"
                ) or {}).get("operation") == entry_node["operation"]
                and result_artifact_id in record.get("artifact_ids", [])
            ]
            evidence_artifact_records = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "artifact_recorded"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "artifact_id"
                ) == evidence_artifact_id
            ]
            if not all(len(group) == 1 for group in (
                started,
                captures,
                result_artifact_records,
                action_advances,
                evidence_artifact_records,
            )):
                raise GovernedRuntimeError(
                    "manual result lacks one exact runtime execution sequence"
                )
            ordered = [
                int(invocation["sequence"]),
                int(started[0]["sequence"]),
                int(captures[0]["sequence"]),
                int(result_artifact_records[0]["sequence"]),
                int(action_advances[0]["sequence"]),
                int(evidence_artifact_records[0]["sequence"]),
            ]
            if ordered != sorted(set(ordered)):
                raise GovernedRuntimeError(
                    "manual invocation, execution, and evidence ordering is invalid"
                )
            details_body = {
                "invocation_id": invocation["event"]["details"]["invocation_id"],
                "invocation_record_id": invocation_record_id,
                "invocation_digest": invocation["event"]["details"][
                    "invocation_digest"
                ],
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "result_artifact_id": result_artifact_id,
                "result_identity_digest": result["identity"]["digest"],
                "evidence_artifact_id": evidence_artifact_id,
                "evidence_identity_digest": evidence["identity"]["digest"],
                "response_text": response_text,
                "response_digest": _digest_text(response_text),
                "current_node_id": run["current_node_id"],
            }
            details = {
                **details_body,
                "result_binding_digest": _digest_json(details_body),
            }
            existing = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "manual_process_result_recorded"
            ]
            if len(existing) > 1:
                raise GovernedRuntimeError(
                    "Process Run has multiple manual result records"
                )
            if existing:
                if existing[0]["event"]["details"] != details:
                    raise RunConflictError(
                        "manual result was already recorded with another identity"
                    )
                return copy.deepcopy(existing[0])
            if run["state"] not in {"running", "pending"}:
                raise RunConflictError(
                    "manual result requires a live Process Run"
                )
            return self._append_event_locked(
                run,
                "manual_process_result_recorded",
                details,
                node_id=run["current_node_id"],
                artifact_ids=[result_artifact_id, evidence_artifact_id],
                runtime_authoritative=True,
            )

    def capture_manual_process_output(
        self,
        run_id: str,
        *,
        invocation_record_id: str,
        response_text: str,
    ) -> dict[str, Any]:
        """Durably capture exact pipeline bytes before result graph mutation."""

        if not response_text:
            raise GovernedRuntimeError(
                "manual Process output capture requires a non-empty response"
            )
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            records = self.load_records(run_id)
            invocations = [
                record for record in records
                if record["record_id"] == invocation_record_id
                and (record.get("event") or {}).get("event_type")
                == "manual_process_invoked"
            ]
            if len(invocations) != 1:
                raise GovernedRuntimeError(
                    "manual output capture lacks its exact invocation record"
                )
            invocation = invocations[0]
            entry_node_id = str(
                invocation["event"]["details"].get("entry_node_id") or ""
            )
            entry_node = self._graph_nodes(definition).get(entry_node_id)
            details_body = {
                "invocation_id": invocation["event"]["details"]["invocation_id"],
                "invocation_record_id": invocation_record_id,
                "invocation_digest": invocation["event"]["details"][
                    "invocation_digest"
                ],
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "entry_node_id": entry_node_id,
                "response_text": response_text,
                "response_digest": _digest_text(response_text),
            }
            details = {
                **details_body,
                "output_capture_digest": _digest_json(details_body),
            }
            existing = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "manual_process_output_captured"
            ]
            if len(existing) > 1:
                raise GovernedRuntimeError(
                    "Process Run has multiple manual output captures"
                )
            if existing:
                if existing[0]["event"]["details"] != details:
                    raise RunConflictError(
                        "manual Process output was already captured differently"
                    )
                return copy.deepcopy(existing[0])
            if (
                run["state"] not in {"running", "pending"}
                or entry_node is None
                or entry_node.get("kind") != "action"
                or entry_node.get("external_effect") is not False
                or run["current_node_id"] != entry_node_id
            ):
                raise GovernedRuntimeError(
                    "manual output capture is outside its exact execution entry"
                )
            return self._append_event_locked(
                run,
                "manual_process_output_captured",
                details,
                node_id=entry_node_id,
                runtime_authoritative=True,
            )

    def record_lifecycle_disposition(
        self,
        run_id: str,
        disposition: str,
        *,
        decision_by: str,
        promoted_definition_ref: Mapping[str, Any] | None = None,
        capability_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        """Record one principal-authorized post-terminal Run disposition.

        This is safe terminal metadata only. It neither rewrites the Run nor
        mutates, activates, archives, or deletes an Artifact. The owning
        Process Library service independently validates any promotion against
        the exact registry definition and capability Artifact before treating
        this record as manual-invocation authority.
        """

        exact_disposition = str(disposition or "").strip().lower()
        if exact_disposition not in {"promote", "preserve", "archive", "discard"}:
            raise GovernedRuntimeError(
                "lifecycle disposition must be promote, preserve, archive, or discard"
            )
        principal = str(decision_by or "").strip()

        exact_ref = None
        exact_artifact_id = None
        if exact_disposition == "promote":
            if not isinstance(promoted_definition_ref, Mapping):
                raise GovernedRuntimeError(
                    "promotion requires an exact promoted_definition_ref"
                )
            exact_ref = copy.deepcopy(dict(promoted_definition_ref))
            if set(exact_ref) != {"definition_id", "version", "digest"}:
                raise GovernedRuntimeError(
                    "promoted_definition_ref must contain exact ID, version, and digest"
                )
            for field in ("definition_id", "version"):
                if not isinstance(exact_ref[field], str) or not exact_ref[field]:
                    raise GovernedRuntimeError(
                        f"promoted_definition_ref {field} must be non-empty"
                    )
            exact_ref["digest"] = _exact_digest(
                exact_ref["digest"], "promoted_definition_ref digest"
            )
            exact_artifact_id = str(capability_artifact_id or "").strip()
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:/-]*", exact_artifact_id
            ):
                raise GovernedRuntimeError(
                    "promotion requires an exact capability_artifact_id"
                )
        elif promoted_definition_ref is not None or capability_artifact_id is not None:
            raise GovernedRuntimeError(
                "only promotion may bind a Process Definition or capability Artifact"
            )
        key = lifecycle_disposition_idempotency_key(
            run_id,
            exact_disposition,
            exact_ref,
            exact_artifact_id,
        )

        with _locked():
            run = self.load_run(run_id)
            if run["state"] not in TERMINAL_RUN_STATES:
                raise RunConflictError(
                    "Run lifecycle disposition requires a terminal Process Run"
                )
            if principal != run["contracts"]["authority"]["principal_id"]:
                raise AuthorityDeniedError(
                    "Run lifecycle disposition must come from the Run principal"
                )
            if exact_disposition == "promote" and run["state"] != "completed":
                raise AuthorityDeniedError(
                    "only an accepted completed Run may promote a capability"
                )

            records = self.load_records(run_id)
            existing = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "lifecycle_disposition_recorded"
            ]
            artifacts = [
                self.load_artifact(run_id, artifact_id)
                for artifact_id in run["artifact_ids"]
            ]
            output_bindings = [
                {
                    "artifact_id": artifact["artifact_id"],
                    "role": artifact["role"],
                    "identity_digest": artifact["identity"]["digest"],
                    "recorded_status": artifact["status"],
                }
                for artifact in artifacts
                if artifact["role"] in {"working", "result", "process_definition"}
            ]
            output_bindings.sort(key=lambda item: item["artifact_id"])
            terminal_record = next(
                (
                    record for record in reversed(records)
                    if record.get("record_type") == "transition"
                    and (record.get("transition") or {}).get("to_state")
                    == run["state"]
                ),
                None,
            )
            if terminal_record is None:
                raise GovernedRuntimeError(
                    "terminal Process Run lacks its authoritative terminal transition"
                )
            if exact_disposition == "promote":
                artifact = next(
                    (
                        item for item in artifacts
                        if item["artifact_id"] == exact_artifact_id
                    ),
                    None,
                )
                if artifact is None or artifact["role"] != "process_definition":
                    raise AuthorityDeniedError(
                        "promotion requires the exact Process Definition Artifact"
                    )

            details = {
                "schema_version": "ora.process-lifecycle-disposition/1.0",
                "disposition": exact_disposition,
                "decision_by": principal,
                "idempotency_key": key,
                "terminal_state": run["state"],
                "terminal_record_id": terminal_record["record_id"],
                "terminal_sequence": terminal_record["sequence"],
                "output_bindings": output_bindings,
                "output_bindings_digest": _digest_json(output_bindings),
                "promoted_definition_ref": exact_ref,
                "capability_artifact_id": exact_artifact_id,
            }
            if existing:
                if len(existing) != 1 or existing[0]["event"]["details"] != details:
                    raise RunConflictError(
                        "Process Run already has a different lifecycle disposition"
                    )
                return copy.deepcopy(existing[0])

            evidence_refs = copy.deepcopy(terminal_record["evidence_refs"])
            record_id = "event-lifecycle-" + hashlib.sha256(
                f"{run_id}\0{key}".encode("utf-8")
            ).hexdigest()[:32]
            return self._append_event_locked(
                run,
                "lifecycle_disposition_recorded",
                details,
                node_id=run["current_node_id"],
                evidence_refs=evidence_refs,
                artifact_ids=[item["artifact_id"] for item in output_bindings],
                record_id=record_id,
                allow_terminal_metadata=True,
                runtime_authoritative=True,
            )

    def _record_dialogue_observation(
        self,
        run_id: str,
        *,
        dialogue_ref: str,
        binding_digest: str,
        observation_type: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Internal append for a validated Run-bound Dialogue observation.

        The owning Dialogue service validates question order and payload
        semantics before calling this internal seam. These records use a
        reserved runtime event so neither the public generic event API nor a
        direct public completion method can forge facts later folded by that
        service.
        """

        dialogue = str(dialogue_ref or "").strip()
        observation = str(observation_type or "").strip()
        if not dialogue:
            raise GovernedRuntimeError("dialogue_ref must be non-empty")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", observation):
            raise GovernedRuntimeError("observation_type must be a stable identifier")
        exact_binding = _exact_digest(binding_digest, "binding_digest")
        _require_json(payload, "dialogue observation payload")
        with _locked():
            run = self.load_run(run_id)
            if run["input_bindings"].get("dialogue_ref") != dialogue:
                raise AuthorityDeniedError(
                    "Dialogue observation does not match the Process Run dialogue_ref"
                )
            expected_binding = _digest_json({
                "schema_version": "ora.dialogue-process-binding/1.0",
                "dialogue_ref": dialogue,
                "run_id": run["run_id"],
                "definition_ref": run["definition_ref"],
            })
            if expected_binding != exact_binding:
                raise AuthorityDeniedError(
                    "Dialogue observation does not match the Process Run binding digest"
                )
            return self._append_event_locked(
                run,
                "dialogue_observation_recorded",
                {
                    "dialogue_ref": dialogue,
                    "binding_digest": exact_binding,
                    "observation_type": observation,
                    "payload_digest": _digest_json(payload),
                    "payload": copy.deepcopy(dict(payload)),
                },
                node_id=run["current_node_id"],
                runtime_authoritative=True,
            )

    def _replace_contracts_for_nonmutating_phase(
        self,
        run_id: str,
        contracts: Mapping[str, Any],
        *,
        expected_current_plan_digest: str,
        phase: str,
        labels: Sequence[str],
    ) -> dict[str, Any]:
        """Replace attached contracts only for a fail-closed nonmutating phase.

        This internal seam exists for a governing service that moves one Run
        from its interview authorization into reviewed planning, or binds the
        approved M1 while execution remains withheld.  It cannot introduce an
        external-effect selector, an external-effect node, or an effect type
        beyond Dialogue/read-only/local-reversible state.
        """

        exact_expected = _exact_digest(
            expected_current_plan_digest, "expected_current_plan_digest"
        )
        phase_id = str(phase or "").strip()
        if not re.fullmatch(r"phase-2\.3-(?:planning|approved)", phase_id):
            raise GovernedRuntimeError("nonmutating phase contract identifier is invalid")
        clean_labels = [str(label or "").strip() for label in labels]
        if not clean_labels or any(not label for label in clean_labels):
            raise GovernedRuntimeError("nonmutating phase labels must be non-empty")
        replacement = copy.deepcopy(dict(contracts))
        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "replace nonmutating phase contracts")
            current_digest = run["contracts"]["approved_plan"]["digest"]
            if current_digest != exact_expected:
                raise RunConflictError(
                    "Process Run contracts changed before phase replacement"
                )
            definition = self.load_definition(run_id)
            nodes = self._graph_nodes(definition)
            approved_nodes = set(
                (replacement.get("approved_plan") or {}).get("approved_node_ids") or []
            )
            if run["current_node_id"] not in approved_nodes:
                raise AuthorityDeniedError(
                    "replacement contracts omit the current Process node"
                )
            for node_id in approved_nodes:
                node = nodes.get(str(node_id))
                if node is None:
                    raise GovernedRuntimeError(
                        f"replacement contracts reference an unknown node: {node_id}"
                    )
                if node["kind"] == "action" and node.get("external_effect") is True:
                    raise AuthorityDeniedError(
                        "nonmutating phase contracts cannot approve external-effect nodes"
                    )
            scope = replacement.get("artifact_scope") or {}
            if scope.get("external_effect_selectors"):
                raise AuthorityDeniedError(
                    "nonmutating phase contracts cannot grant external-effect scope"
                )
            safe_effect_types = {"dialogue_only", "read_only", "local_reversible"}
            for grant in (replacement.get("authority") or {}).get("grants") or []:
                outside = set(grant.get("effect_types") or []) - safe_effect_types
                if outside:
                    raise AuthorityDeniedError(
                        "nonmutating phase contracts contain an unsafe effect type"
                    )
            candidate = copy.deepcopy(run)
            candidate["contracts"] = replacement
            candidate["labels"] = clean_labels
            _contracts.validate_process_run(candidate)
            self._validate_definition_binding(definition, candidate)
            old_ref = copy.deepcopy(run["contracts"]["approved_plan"])
            run["contracts"] = replacement
            run["labels"] = clean_labels
            return self._append_event_locked(
                run,
                "run_contracts_replaced",
                {
                    "phase": phase_id,
                    "prior_plan_ref": {
                        "plan_id": old_ref["plan_id"],
                        "version": old_ref["version"],
                        "digest": old_ref["digest"],
                    },
                    "replacement_plan_ref": {
                        "plan_id": replacement["approved_plan"]["plan_id"],
                        "version": replacement["approved_plan"]["version"],
                        "digest": replacement["approved_plan"]["digest"],
                    },
                    "contracts": replacement,
                    "labels": clean_labels,
                },
                node_id=run["current_node_id"],
                runtime_authoritative=True,
            )

    def _activate_approved_delegation(
        self,
        run_id: str,
        contracts: Mapping[str, Any],
        *,
        plan_ref: Mapping[str, Any],
        approval_receipt_digest: str,
        delegation_digest: str,
        target_binding: Mapping[str, Any],
        idempotency_key: str,
        labels: Sequence[str],
    ) -> dict[str, Any]:
        """Bind one exact approved plan to the generic execution kernel.

        This is an internal Phase 2.4 seam.  It changes only attached Run
        contracts and never performs a target action.  The owning delegation
        service has already authenticated the Dialogue, approval receipt,
        current target baseline, and idempotency identity.  This boundary
        repeats the load-bearing checks before making execution nodes
        reachable and records the complete replacement for crash recovery.
        """

        replacement = copy.deepcopy(dict(contracts))
        exact_approval = _exact_digest(
            approval_receipt_digest, "approval_receipt_digest"
        )
        exact_delegation = _exact_digest(delegation_digest, "delegation_digest")
        exact_target = copy.deepcopy(dict(target_binding))
        if set(exact_target) != {"locator", "baseline_identity_digest"}:
            raise GovernedRuntimeError("delegation target binding is incomplete")
        locator = exact_target.get("locator")
        if (
            not isinstance(locator, dict)
            or set(locator) != {"kind", "ref"}
            or locator.get("kind") not in {"file", "git_ref"}
            or not isinstance(locator.get("ref"), str)
            or not Path(locator["ref"]).is_absolute()
        ):
            raise GovernedRuntimeError("delegation target locator is invalid")
        exact_target["baseline_identity_digest"] = _exact_digest(
            exact_target.get("baseline_identity_digest"),
            "target baseline_identity_digest",
        )
        key = str(idempotency_key or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", key):
            raise GovernedRuntimeError("delegation idempotency key is invalid")
        clean_labels = [str(label or "").strip() for label in labels]
        if not clean_labels or any(not label for label in clean_labels):
            raise GovernedRuntimeError("delegation labels must be non-empty")

        with _locked():
            run = self.load_run(run_id)
            existing = [
                record
                for record in self.load_records(run_id)
                if (record.get("event") or {}).get("event_type")
                == "delegation_activated"
            ]
            if existing:
                details = existing[-1]["event"]["details"]
                if (
                    len(existing) != 1
                    or details.get("delegation_digest") != exact_delegation
                    or details.get("approval_receipt_digest") != exact_approval
                    or details.get("plan_ref") != dict(plan_ref)
                    or details.get("target_binding") != exact_target
                    or details.get("idempotency_key") != key
                    or details.get("contracts") != replacement
                    or details.get("labels") != clean_labels
                ):
                    raise RunConflictError(
                        "Process Run already carries a different delegation identity"
                    )
                return copy.deepcopy(existing[-1])

            self._require_mutable_run(run, "activate approved delegation")
            if run["state"] != "running" or run["current_node_id"] != "post-plan-mode":
                raise RunConflictError(
                    "delegation requires the approved post-plan execution boundary"
                )
            expected_plan_ref = {
                field: run["contracts"]["approved_plan"][field]
                for field in ("plan_id", "version", "digest")
            }
            if dict(plan_ref) != expected_plan_ref:
                raise AuthorityDeniedError(
                    "delegation does not bind the exact approved plan"
                )
            if "plan:approved" not in run.get("labels", []):
                raise AuthorityDeniedError(
                    "delegation requires the persisted approved-plan boundary"
                )
            replacement_plan_ref = {
                field: replacement.get("approved_plan", {}).get(field)
                for field in ("plan_id", "version", "digest")
            }
            if replacement_plan_ref != expected_plan_ref:
                raise AuthorityDeniedError(
                    "delegation contracts replace the approved plan identity"
                )
            candidate = copy.deepcopy(run)
            candidate["contracts"] = replacement
            candidate["labels"] = clean_labels
            _contracts.validate_process_run(candidate)
            definition = self.load_definition(run_id)
            self._validate_definition_binding(definition, candidate)

            required_nodes = {
                "post-plan-mode", "execute-preflight", "execute-step",
                "attempt-review", "final-review", "authority", "accepted",
                "blocked",
            }
            approved_nodes = set(
                replacement["approved_plan"]["approved_node_ids"]
            )
            missing_nodes = sorted(required_nodes - approved_nodes)
            if missing_nodes:
                raise AuthorityDeniedError(
                    "delegation omits required execution node(s): "
                    + ", ".join(missing_nodes)
                )
            always_reserved = {
                "activate", "construct_definition", "expand_scope", "publish",
                "register_definition", "remote_git", "send_external",
            }
            reserved = set(replacement["authority"]["reserved_actions"])
            if not always_reserved.issubset(reserved):
                raise AuthorityDeniedError(
                    "delegation releases authority that requires a separate approval"
                )
            granted = {
                action
                for grant in replacement["authority"]["grants"]
                for action in grant["actions"]
            }
            allowed = {
                "programming_preflight", "execute_approved_programming_step",
                "correct_programming_defect", "inspect_programming_result",
                "record_programming_mutation_receipt",
                "persist_programming_resume_execute",
                "persist_programming_resume_final",
            }
            outside = sorted(granted - allowed)
            if outside:
                raise AuthorityDeniedError(
                    "delegation grants an unsupported action: " + ", ".join(outside)
                )
            external_selectors = set(
                replacement["artifact_scope"]["external_effect_selectors"]
            )
            write_selectors = set(
                replacement["artifact_scope"]["write_selectors"]
            )
            mutation_selectors = {
                selector
                for grant in replacement["authority"]["grants"]
                if set(grant["actions"]) & {
                    "execute_approved_programming_step",
                    "correct_programming_defect",
                }
                for selector in grant["resource_selectors"]
            }
            if (
                not external_selectors
                or any(
                    not selector.startswith("artifact:")
                    for selector in external_selectors
                )
                or mutation_selectors != external_selectors
                or external_selectors & write_selectors
            ):
                raise AuthorityDeniedError(
                    "delegation must bind exact, non-write target selectors to "
                    "its external-effect mutation grant"
                )

            run["contracts"] = replacement
            run["labels"] = clean_labels
            return self._append_event_locked(
                run,
                "delegation_activated",
                {
                    "plan_ref": copy.deepcopy(dict(plan_ref)),
                    "approval_receipt_digest": exact_approval,
                    "delegation_digest": exact_delegation,
                    "target_binding": exact_target,
                    "idempotency_key": key,
                    "contracts": replacement,
                    "labels": clean_labels,
                },
                node_id=run["current_node_id"],
                runtime_authoritative=True,
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

    # ------------------------------------------------------ graph traversal
    @staticmethod
    def _graph_nodes(definition: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        return {
            str(node["node_id"]): node
            for node in definition["graph"]["nodes"]
        }

    def _mechanical_block_locked(
        self,
        run: dict[str, Any],
        *,
        source_node_id: str,
        target_node_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Apply a graph-declared fail-closed route without cognitive judgment."""

        record = {
            "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
            "object_family": "event_transition_record",
            "record_id": f"transition-{uuid.uuid4().hex}",
            "run_id": run["run_id"],
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "sequence": int(run["last_sequence"]) + 1,
            "recorded_at": self._now(),
            "node_id": source_node_id,
            "record_type": "transition",
            "transition": {
                "directive": "BLOCKED",
                "from_state": run["state"],
                "to_state": "blocked",
                "reason": reason,
                "evaluation_boundary": "mechanical_graph_route",
                "target_node_id": target_node_id,
            },
            "evidence_refs": [],
            "artifact_ids": list(run["artifact_ids"]),
        }
        _contracts.validate_event_transition_record(record)
        _append_jsonl(self._events_path(run["run_id"]), record)
        run["last_sequence"] = record["sequence"]
        run["updated_at"] = record["recorded_at"]
        run["state"] = "blocked"
        run["current_node_id"] = target_node_id
        _contracts.validate_process_run(run)
        _atomic_json(self._run_path(run["run_id"]), run)
        return copy.deepcopy(record)

    def _advance_graph_locked(
        self,
        run: dict[str, Any],
        definition: Mapping[str, Any],
        *,
        target_node_id: str,
        advance_kind: str,
        reason: str,
        route: Mapping[str, Any],
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        artifact_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        if run["state"] != "running":
            raise RunConflictError("graph traversal requires a running Process Run")
        nodes = self._graph_nodes(definition)
        source_node_id = str(run["current_node_id"])
        target = nodes.get(target_node_id)
        if target is None:
            raise GovernedRuntimeError(
                f"graph traversal target is not in the definition: {target_node_id}"
            )
        if target_node_id not in run["contracts"]["approved_plan"]["approved_node_ids"]:
            raise AuthorityDeniedError(
                f"graph traversal target is outside the approved plan: {target_node_id}"
            )
        if target["kind"] == "terminal_state":
            if target["outcome"] == "blocked":
                return self._mechanical_block_locked(
                    run,
                    source_node_id=source_node_id,
                    target_node_id=target_node_id,
                    reason=reason,
                )
            raise GovernedRuntimeError(
                "accepted, cancelled, or returned terminal states require their "
                "dedicated transition/return boundary"
            )
        known_artifacts = set(run["artifact_ids"])
        unknown_artifacts = sorted(set(artifact_ids) - known_artifacts)
        if unknown_artifacts:
            raise GovernedRuntimeError(
                "graph advancement references unknown Artifact(s): "
                + ", ".join(unknown_artifacts)
            )
        _require_json(evidence_refs, "graph advancement evidence_refs")
        _require_json(route, "graph advancement route")
        run["current_node_id"] = target_node_id
        return self._append_event_locked(
            run,
            "node_advanced",
            {
                "from_node_id": source_node_id,
                "to_node_id": target_node_id,
                "advance_kind": advance_kind,
                "reason": reason,
                "route": copy.deepcopy(dict(route)),
            },
            node_id=source_node_id,
            evidence_refs=evidence_refs,
            artifact_ids=artifact_ids,
            runtime_authoritative=True,
        )

    def advance_decision(
        self,
        run_id: str,
        condition: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        """Apply one declared decision route without inventing direction."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "decision":
                raise GovernedRuntimeError("advance_decision requires a decision node")
            route = next(
                (
                    item
                    for item in node["routes"]
                    if item["condition"] == condition
                ),
                None,
            )
            entrypoints = set(
                (((definition.get("input_schema") or {}).get("properties") or {})
                .get("entrypoint", {})
                .get("enum", []))
            )
            condition_entrypoint = str(condition).split(":", 1)[0]
            if condition_entrypoint in entrypoints and condition_entrypoint != run["entrypoint"]:
                raise AuthorityDeniedError(
                    "decision condition belongs to a different Process Run entrypoint"
                )
            target = (
                str(route["target_node_id"])
                if route is not None
                else str(node["default_node_id"])
            )
            return self._advance_graph_locked(
                run,
                definition,
                target_node_id=target,
                advance_kind="decision",
                reason=reason,
                route={
                    "condition": condition,
                    "matched": route is not None,
                    "default_used": route is None,
                },
            )

    def complete_action_node(
        self,
        run_id: str,
        operation: str,
        *,
        reason: str,
        completion_details: Mapping[str, Any] | None = None,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        artifact_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Advance an exact action only after its required completion proof exists."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "action":
                raise GovernedRuntimeError("complete_action_node requires an action node")
            if operation != node["operation"]:
                raise GovernedRuntimeError(
                    f"action operation mismatch: expected {node['operation']}, got {operation}"
                )
            details = copy.deepcopy(dict(completion_details or {}))
            if not details and not evidence_refs and not artifact_ids:
                raise GovernedRuntimeError(
                    "action completion requires details, evidence, or an Artifact identity"
                )
            records = self.load_records(run_id)
            entered_sequence = 0
            for record in records:
                transition = record.get("transition") or {}
                event = record.get("event") or {}
                event_details = event.get("details") or {}
                if transition.get("target_node_id") == run["current_node_id"]:
                    entered_sequence = int(record["sequence"])
                elif (
                    event.get("event_type") == "node_advanced"
                    and event_details.get("to_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(record["sequence"])
                elif (
                    event.get("event_type") == "run_started"
                    and event_details.get("entry_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(record["sequence"])
                elif (
                    event.get("event_type") == "run_resumed"
                    and event_details.get("resume_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(record["sequence"])
                elif (
                    event.get("event_type") == "child_return_received"
                    and event_details.get("return_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(record["sequence"])
            action_records: list[Mapping[str, Any]] = []
            current_artifact_records: dict[str, Mapping[str, Any]] = {}
            for record in reversed(records):
                if int(record["sequence"]) <= entered_sequence:
                    break
                if record["node_id"] != run["current_node_id"]:
                    continue
                event = record.get("event") or {}
                event_details = event.get("details") or {}
                if (
                    event.get("event_type") == "action_completed"
                    and event_details.get("completion_operation") == operation
                ):
                    action_records.append(record)
                if event.get("event_type") == "artifact_recorded":
                    artifact_id = str(event_details.get("artifact_id") or "")
                    current_artifact_records.setdefault(artifact_id, record)
            if len(action_records) > 1:
                raise GovernedRuntimeError(
                    "action completion has multiple runtime-bound action records"
                )
            action_record = action_records[0] if action_records else None
            action_record_id = (
                str(action_record["record_id"]) if action_record is not None else None
            )
            if action_record is not None:
                action_details = action_record["event"]["details"]
                if (
                    action_details.get("node_external_effect")
                    is not bool(node["external_effect"])
                    or bool(action_details.get("external_effect"))
                    != bool(node["external_effect"])
                ):
                    raise GovernedRuntimeError(
                        "action record external-effect classification differs from "
                        "the Process Definition node"
                    )
                action_selectors = list(action_details.get("selectors") or [])
                scope_kind = "external" if node["external_effect"] else "write"
                allowed_scope = set(
                    run["contracts"]["artifact_scope"][
                        "external_effect_selectors"
                        if node["external_effect"]
                        else "write_selectors"
                    ]
                )
                if not action_selectors or not set(action_selectors).issubset(
                    allowed_scope
                ):
                    raise GovernedRuntimeError(
                        "action record selectors differ from the node's authoritative scope"
                    )
                if not self._node_allows_action_selectors(
                    run, node, action_selectors, records
                ):
                    raise GovernedRuntimeError(
                        "action record selectors are outside the Process Definition node"
                    )
                expected_grants = self._authorize_action(
                    run_id,
                    str(action_details.get("action") or ""),
                    action_selectors,
                    satisfied_conditions=list(
                        action_details.get("satisfied_conditions") or []
                    ),
                    effect_type=str(action_details.get("effect_type") or ""),
                    scope_kind=scope_kind,
                    effect_recording=True,
                )
                if action_details.get("grant_ids") != expected_grants:
                    raise GovernedRuntimeError(
                        "action record authority grants are stale or substituted"
                    )
            proof_artifact_ids = {
                *artifact_ids,
                *(str(ref.get("artifact_id") or "") for ref in evidence_refs),
            }
            exact_artifact_proof = bool(proof_artifact_ids)
            for artifact_id in proof_artifact_ids:
                artifact_record = current_artifact_records.get(artifact_id)
                if artifact_record is None:
                    exact_artifact_proof = False
                    break
                record_details = artifact_record["event"]["details"]
                artifact = self.load_artifact(run_id, artifact_id)
                if (
                    record_details.get("identity_digest")
                    != artifact["identity"]["digest"]
                    or not set(record_details.get("selectors") or []).issubset(
                        set(node["artifact_access"])
                    )
                ):
                    exact_artifact_proof = False
                    break
            if exact_artifact_proof:
                for ref in evidence_refs:
                    artifact = self.load_artifact(run_id, str(ref.get("artifact_id")))
                    if ref.get("identity_digest") != artifact["identity"]["digest"]:
                        exact_artifact_proof = False
                        break
            automation_contract = (
                (definition.get("output_schema") or {}).get("x-ora-process")
            )
            if (
                isinstance(automation_contract, Mapping)
                and automation_contract.get("schema_version")
                == "ora.process-automation/1.0"
            ):
                execution_records = []
                for record in records:
                    if (
                        int(record["sequence"]) <= entered_sequence
                        or record["node_id"] != run["current_node_id"]
                    ):
                        continue
                    event = record.get("event") or {}
                    event_details = event.get("details") or {}
                    if (
                        event.get("event_type") == "isolated_process_step_completed"
                        and event_details.get("operation") == operation
                    ):
                        execution_records.append((record, event_details))
                if len(execution_records) != 1:
                    raise GovernedRuntimeError(
                        "automated Process action completion requires exactly one "
                        "runtime-issued isolated execution record"
                    )
                execution_record, execution_details = execution_records[0]
                if len(artifact_ids) != 1:
                    raise GovernedRuntimeError(
                        "automated Process action completion requires one exact output Artifact"
                    )
                output_artifact = self.load_artifact(run_id, artifact_ids[0])
                expected_execution = {
                    "run_id": run_id,
                    "definition_ref": run["definition_ref"],
                    "node_id": run["current_node_id"],
                    "operation": operation,
                    "artifact_id": output_artifact["artifact_id"],
                    "artifact_identity_digest": output_artifact["identity"]["digest"],
                    "execution_context_binding_digest": (
                        (run.get("input_bindings") or {})
                        .get("execution_context", {})
                        .get("binding_digest")
                    ),
                    "attempt": run["contracts"]["correction_loop"]["attempt"],
                }
                mismatches = [
                    field for field, expected in expected_execution.items()
                    if execution_details.get(field) != expected
                ]
                for field in ("worker_request_digest", "worker_response_digest"):
                    try:
                        _exact_digest(execution_details.get(field), field)
                    except GovernedRuntimeError:
                        mismatches.append(field)
                if execution_details.get("worker_boundary") not in {
                    "separate_no_tools_process", "injected_test_worker",
                }:
                    mismatches.append("worker_boundary")
                artifact_record = current_artifact_records.get(output_artifact["artifact_id"])
                if (
                    artifact_record is None
                    or int(artifact_record["sequence"]) >= int(execution_record["sequence"])
                    or output_artifact["artifact_id"] not in execution_record["artifact_ids"]
                ):
                    mismatches.append("artifact_record_order")
                if any(
                    details.get(field) != execution_details.get(field)
                    for field in (
                        "worker_boundary", "worker_request_digest",
                        "worker_response_digest", "execution_context_binding_digest",
                    )
                ):
                    mismatches.append("completion_details")
                if mismatches:
                    raise GovernedRuntimeError(
                        "isolated execution binding does not match the current action: "
                        + ", ".join(sorted(set(mismatches)))
                    )
            if node["external_effect"]:
                if action_record is None:
                    raise GovernedRuntimeError(
                        "external-effect action completion requires a current validated "
                        "action record bound to the exact operation and artifact selectors"
                    )
                action_details = action_record["event"]["details"]
                action_sequence = int(action_record["sequence"])
                checkpoints = [
                    record for record in records
                    if entered_sequence < int(record["sequence"]) < action_sequence
                    and record["node_id"] == run["current_node_id"]
                    and (record.get("event") or {}).get("event_type")
                    == "checkpoint_created"
                    and ((record.get("event") or {}).get("details") or {}).get(
                        "resume_node_id"
                    ) == run["current_node_id"]
                ]
                if not checkpoints:
                    raise GovernedRuntimeError(
                        "external-effect action completion requires an exact pre-action "
                        "checkpoint created during the current node entry"
                    )
                checkpoint = checkpoints[-1]
                checkpoint_details = checkpoint["event"]["details"]
                receipt_id = str(
                    action_details.get("receipt_artifact_id") or ""
                )
                receipt_digest = str(
                    action_details.get("receipt_identity_digest") or ""
                )
                if not receipt_id or not receipt_digest:
                    raise GovernedRuntimeError(
                        "external-effect action completion requires an exact receipt"
                    )
                receipt = self.load_artifact(run_id, receipt_id)
                receipt_record = current_artifact_records.get(receipt_id)
                if (
                    receipt["role"] != "external_effect_receipt"
                    or receipt["identity"]["digest"] != receipt_digest
                    or receipt_record is None
                    or not (
                        int(checkpoint["sequence"])
                        < int(receipt_record["sequence"])
                        < action_sequence
                    )
                    or receipt_id not in action_record["artifact_ids"]
                ):
                    raise GovernedRuntimeError(
                        "external-effect receipt identity or ordering is invalid"
                    )
                mutation = action_details.get("details") or {}
                pre_state = mutation.get("pre_state_identity")
                post_state = mutation.get("post_state_identity")
                if not isinstance(pre_state, dict) or not isinstance(post_state, dict):
                    raise GovernedRuntimeError(
                        "external-effect action must bind exact pre- and post-state identities"
                    )
                pre_id = str(pre_state.get("artifact_id") or "")
                post_id = str(post_state.get("artifact_id") or "")
                pre_digest = str(pre_state.get("identity_digest") or "")
                post_digest = str(post_state.get("identity_digest") or "")
                if not pre_id or not post_id or not pre_digest or not post_digest:
                    raise GovernedRuntimeError(
                        "external-effect pre/post-state identity is incomplete"
                    )
                pre_artifact = self.load_artifact(run_id, pre_id)
                post_artifact = self.load_artifact(run_id, post_id)
                post_record = current_artifact_records.get(post_id)
                if (
                    pre_artifact["identity"]["digest"] != pre_digest
                    or post_artifact["identity"]["digest"] != post_digest
                    or checkpoint_details.get("artifact_identities", {}).get(pre_id)
                    != pre_digest
                    or post_record is None
                    or not (
                        int(checkpoint["sequence"])
                        < int(post_record["sequence"])
                        < action_sequence
                    )
                    or not {pre_id, post_id}.issubset(
                        set(receipt["lineage"]["source_artifact_ids"])
                    )
                ):
                    raise GovernedRuntimeError(
                        "external-effect checkpoint, state, and receipt lineage do not bind"
                    )
            if action_record_id is None and not exact_artifact_proof:
                raise GovernedRuntimeError(
                    "action completion requires a current validated action record or "
                    "exact Artifact proof produced during this node entry"
                )
            details["operation"] = operation
            details["action_record_id"] = action_record_id
            return self._advance_graph_locked(
                run,
                definition,
                target_node_id=str(node["next_node_id"]),
                advance_kind="action",
                reason=reason,
                route=details,
                evidence_refs=evidence_refs,
                artifact_ids=artifact_ids,
            )

    def resolve_human_checkpoint(
        self,
        run_id: str,
        outcome: str,
        *,
        decision_by: str,
        reason: str,
    ) -> dict[str, Any]:
        """Apply an explicit human-checkpoint result to its declared route."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "human_checkpoint":
                raise GovernedRuntimeError(
                    "resolve_human_checkpoint requires a human_checkpoint node"
                )
            if outcome not in {"approved", "denied", "unavailable"}:
                raise GovernedRuntimeError(
                    "human checkpoint outcome must be approved, denied, or unavailable"
                )
            if not decision_by:
                raise AuthorityDeniedError("human checkpoint requires a decision maker")
            if outcome == "approved" and decision_by != run["contracts"]["authority"]["principal_id"]:
                raise AuthorityDeniedError(
                    "checkpoint approval must come from the Run principal"
                )
            target_field = {
                "approved": "on_approved_node_id",
                "denied": "on_denied_node_id",
                "unavailable": "on_unavailable_node_id",
            }[outcome]
            if target_field not in node:
                target_field = "on_denied_node_id"
            return self._advance_graph_locked(
                run,
                definition,
                target_node_id=str(node[target_field]),
                advance_kind="human_checkpoint",
                reason=reason,
                route={
                    "outcome": outcome,
                    "decision_by": decision_by,
                    "authority_request_type": node["authority_request_type"],
                },
            )

    def resolve_authority_request(
        self,
        run_id: str,
        request_id: str,
        outcome: str,
        *,
        decision_by: str,
    ) -> dict[str, Any]:
        """Resolve one exact persisted ESCALATE request through its graph route.

        Unlike :meth:`resolve_human_checkpoint`, this boundary is specifically
        for a Run stopped in ``waiting_for_authority``.  The runtime, not the
        caller, authenticates the escalation, derives the target edge, persists
        the human decision, and then resumes traversal.  A retry can finish an
        interrupted decision-to-route commit but can never consume a different
        request or select an undeclared node.
        """

        request_id = str(request_id or "").strip()
        decision_by = str(decision_by or "").strip()
        if not request_id:
            raise GovernedRuntimeError("authority resolution requires request_id")
        if outcome not in {"approved", "denied", "unavailable"}:
            raise GovernedRuntimeError(
                "authority resolution outcome must be approved, denied, or unavailable"
            )
        if not decision_by:
            raise AuthorityDeniedError(
                "authority resolution requires a decision maker"
            )

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            records = self.load_records(run_id)
            principal_id = str(run["contracts"]["authority"]["principal_id"])
            if decision_by != principal_id:
                raise AuthorityDeniedError(
                    "authority request may be resolved only by the Run principal"
                )

            escalations = []
            for record in records:
                transition = record.get("transition") or {}
                request = transition.get("authority_request") or {}
                if (
                    transition.get("directive") == "ESCALATE"
                    and request.get("request_id") == request_id
                ):
                    escalations.append(record)
            if len(escalations) != 1:
                raise RunConflictError(
                    "authority resolution requires exactly one persisted ESCALATE request"
                )
            escalation = _contracts.validate_event_transition_record(escalations[0])
            transition = escalation["transition"]
            request = transition["authority_request"]
            nodes = self._graph_nodes(definition)
            source_node_id = str(transition["target_node_id"])
            source = nodes.get(source_node_id)
            if source is None or source.get("kind") != "human_checkpoint":
                raise GovernedRuntimeError(
                    "authority request does not target a human checkpoint"
                )
            if (
                request["requested_from"] != principal_id
                or request["request_type"] != source["authority_request_type"]
                or request["request_type"]
                not in run["contracts"]["stop_escalation"][
                    "authority_request_types"
                ]
            ):
                raise AuthorityDeniedError(
                    "authority request is not bound to the Run principal and declared type"
                )

            target_field = {
                "approved": "on_approved_node_id",
                "denied": "on_denied_node_id",
                "unavailable": "on_unavailable_node_id",
            }[outcome]
            if target_field not in source:
                target_field = "on_denied_node_id"
            target_node_id = str(source[target_field])
            if (
                outcome == "approved"
                and request["resume_node_id"] != target_node_id
            ):
                raise GovernedRuntimeError(
                    "authority request resume node differs from the approved graph route"
                )
            if target_node_id not in set(
                run["contracts"]["approved_plan"]["approved_node_ids"]
            ):
                raise AuthorityDeniedError(
                    "authority resolution target is outside the approved plan"
                )

            binding = {
                "run_id": run_id,
                "request_id": request_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "escalation_record_id": escalation["record_id"],
                "request": copy.deepcopy(request),
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "outcome": outcome,
                "decision_by": decision_by,
            }
            resolution_digest = _digest_json(binding)
            idempotency_key = (
                "authority:" + resolution_digest.split(":", 1)[1]
            )
            expected_details = {
                **binding,
                "idempotency_key": idempotency_key,
                "resolution_digest": resolution_digest,
            }
            resolutions = [
                record
                for record in records
                if (record.get("event") or {}).get("event_type")
                == "authority_request_resolved"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "request_id"
                )
                == request_id
            ]
            if len(resolutions) > 1:
                raise GovernedRuntimeError(
                    "authority request has multiple authoritative resolutions"
                )
            resolution = resolutions[0] if resolutions else None
            if resolution is not None:
                resolution = _contracts.validate_event_transition_record(resolution)
                if (
                    resolution["event"]["details"] != expected_details
                    or resolution["node_id"] != source_node_id
                    or resolution["evidence_refs"] != escalation["evidence_refs"]
                    or resolution["artifact_ids"] != escalation["artifact_ids"]
                    or int(resolution["sequence"]) <= int(escalation["sequence"])
                ):
                    raise RunConflictError(
                        "authority request was already resolved with a different identity"
                    )
            else:
                if (
                    run["state"] != "waiting_for_authority"
                    or run["current_node_id"] != source_node_id
                ):
                    raise RunConflictError(
                        "Process Run is not waiting at this authority request"
                    )
                run["state"] = "running"
                resolution = self._append_event_locked(
                    run,
                    "authority_request_resolved",
                    expected_details,
                    node_id=source_node_id,
                    evidence_refs=escalation["evidence_refs"],
                    artifact_ids=escalation["artifact_ids"],
                    runtime_authoritative=True,
                )
                records = [*records, resolution]

            route_reason = (
                f"Authority request {request_id} resolved as {outcome} by "
                f"{decision_by}"
            )
            later = [
                record
                for record in records
                if int(record["sequence"]) > int(resolution["sequence"])
            ]
            matching_routes = []
            for record in later:
                event = record.get("event") or {}
                details = event.get("details") or {}
                route = details.get("route") or {}
                transition_after = record.get("transition") or {}
                expected_route = {
                    "outcome": outcome,
                    "decision_by": decision_by,
                    "authority_request_type": request["request_type"],
                    "authority_request_id": request_id,
                    "authority_resolution_record_id": resolution["record_id"],
                    "authority_resolution_digest": resolution_digest,
                }
                if (
                    event.get("event_type") == "node_advanced"
                    and record.get("node_id") == source_node_id
                    and set(details) == {
                        "from_node_id", "to_node_id", "advance_kind",
                        "reason", "route",
                    }
                    and details.get("from_node_id") == source_node_id
                    and details.get("to_node_id") == target_node_id
                    and details.get("advance_kind") == "human_checkpoint"
                    and details.get("reason") == route_reason
                    and route == expected_route
                    and int(record["sequence"]) == int(resolution["sequence"]) + 1
                ) or (
                    transition_after.get("directive") == "BLOCKED"
                    and record.get("node_id") == source_node_id
                    and transition_after.get("target_node_id") == target_node_id
                    and transition_after.get("reason") == route_reason
                    and transition_after.get("from_state") == "running"
                    and transition_after.get("to_state") == "blocked"
                    and transition_after.get("evaluation_boundary")
                    == "mechanical_graph_route"
                    and int(record["sequence"]) == int(resolution["sequence"]) + 1
                ):
                    matching_routes.append(record)
            if len(matching_routes) > 1:
                raise GovernedRuntimeError(
                    "authority resolution has multiple graph routes"
                )
            if matching_routes:
                return {
                    "resolution_record": copy.deepcopy(resolution),
                    "route_record": copy.deepcopy(matching_routes[0]),
                    "idempotent_replay": True,
                }
            if later:
                raise RunConflictError(
                    "authority resolution is followed by an unrelated runtime record"
                )

            # If the decision record was committed but its Run materialization
            # was interrupted, load_run above restores this exact resumable state.
            run = self.load_run(run_id)
            if (
                run["state"] != "running"
                or run["current_node_id"] != source_node_id
            ):
                raise RunConflictError(
                    "authority resolution cannot resume from the persisted Run state"
                )
            route_record = self._advance_graph_locked(
                run,
                definition,
                target_node_id=target_node_id,
                advance_kind="human_checkpoint",
                reason=route_reason,
                route={
                    "outcome": outcome,
                    "decision_by": decision_by,
                    "authority_request_type": request["request_type"],
                    "authority_request_id": request_id,
                    "authority_resolution_record_id": resolution["record_id"],
                    "authority_resolution_digest": resolution_digest,
                },
            )
            return {
                "resolution_record": copy.deepcopy(resolution),
                "route_record": copy.deepcopy(route_record),
                "idempotent_replay": False,
            }

    def advance_bounded_loop(
        self,
        run_id: str,
        *,
        continue_loop: bool,
        reason: str,
    ) -> dict[str, Any]:
        """Enter or exit one graph-declared bounded loop mechanically."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "bounded_loop":
                raise GovernedRuntimeError(
                    "advance_bounded_loop requires a bounded_loop node"
                )
            attempt = int(run["contracts"]["correction_loop"]["attempt"])
            if continue_loop and attempt >= int(node["max_iterations"]):
                raise CorrectionDecisionRequired(
                    "bounded-loop ceiling reached; exit and classify the failure"
                )
            target = (
                str(node["body_node_id"])
                if continue_loop
                else str(node["exit_node_id"])
            )
            return self._advance_graph_locked(
                run,
                definition,
                target_node_id=target,
                advance_kind="bounded_loop",
                reason=reason,
                route={"continue_loop": bool(continue_loop), "attempt": attempt},
            )

    def complete_process_return_node(
        self,
        run_id: str,
        *,
        child_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Advance a process_return only from its exact persisted child return."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "process_return":
                raise GovernedRuntimeError(
                    "complete_process_return_node requires a process_return node"
                )
            records = self.load_records(run_id)
            entered_sequence = 0
            for candidate in records:
                transition = candidate.get("transition") or {}
                event = candidate.get("event") or {}
                details = event.get("details") or {}
                if transition.get("target_node_id") == run["current_node_id"]:
                    entered_sequence = int(candidate["sequence"])
                elif (
                    event.get("event_type") == "node_advanced"
                    and details.get("to_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(candidate["sequence"])
                elif (
                    event.get("event_type") == "run_resumed"
                    and details.get("resume_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(candidate["sequence"])
                elif (
                    event.get("event_type") == "child_return_received"
                    and details.get("return_node_id") == run["current_node_id"]
                ):
                    entered_sequence = int(candidate["sequence"])
            matching = []
            for record in records:
                event = record.get("event") or {}
                details = event.get("details") or {}
                if (
                    int(record["sequence"]) >= entered_sequence
                    and event.get("event_type") == "child_return_received"
                    and details.get("child_run_id") == child_run_id
                    and details.get("return_node_id") == run["current_node_id"]
                ):
                    matching.append((record, details))
            if len(matching) != 1:
                raise GovernedRuntimeError(
                    "process return requires exactly one identity-bound child return"
                )
            record, details = matching[0]
            output_bindings = details.get("output_bindings") or []
            if not output_bindings:
                raise GovernedRuntimeError(
                    "process return requires an identity-bound output Artifact"
                )
            for binding in output_bindings:
                self._validate_child_output_binding(binding)
            return self._advance_graph_locked(
                run,
                definition,
                target_node_id=str(node["next_node_id"]),
                advance_kind="process_return",
                reason=reason,
                route={
                    "child_run_id": child_run_id,
                    "child_return_record_id": record["record_id"],
                    "output_bindings": copy.deepcopy(output_bindings),
                },
            )

    # -------------------------------------------------------------- authority
    @staticmethod
    def _node_entry_sequence(
        run: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
    ) -> int:
        entered_sequence = 0
        current_node_id = run["current_node_id"]
        for record in records:
            transition = record.get("transition") or {}
            event = record.get("event") or {}
            details = event.get("details") or {}
            if transition.get("target_node_id") == current_node_id:
                entered_sequence = int(record["sequence"])
            elif (
                event.get("event_type") == "node_advanced"
                and details.get("to_node_id") == current_node_id
            ):
                entered_sequence = int(record["sequence"])
            elif (
                event.get("event_type") == "run_started"
                and details.get("entry_node_id") == current_node_id
            ):
                entered_sequence = int(record["sequence"])
            elif (
                event.get("event_type") == "run_resumed"
                and details.get("resume_node_id") == current_node_id
            ):
                entered_sequence = int(record["sequence"])
            elif (
                event.get("event_type") == "child_return_received"
                and details.get("return_node_id") == current_node_id
            ):
                entered_sequence = int(record["sequence"])
        return entered_sequence

    def _delegation_target_binding(
        self,
        run: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any] | None:
        activations = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "delegation_activated"
        ]
        if not activations:
            return None
        if len(activations) != 1:
            raise AuthorityDeniedError(
                "delegated mutation authority has an ambiguous activation"
            )
        details = activations[0]["event"]["details"]
        binding = details.get("target_binding")
        if (
            not isinstance(binding, dict)
            or set(binding) != {"locator", "baseline_identity_digest"}
            or details.get("plan_ref")
            != {
                field: run["contracts"]["approved_plan"][field]
                for field in ("plan_id", "version", "digest")
            }
        ):
            raise AuthorityDeniedError(
                "delegated mutation authority lacks its exact approved target binding"
            )
        locator = binding.get("locator")
        if (
            not isinstance(locator, dict)
            or set(locator) != {"kind", "ref"}
            or locator.get("kind") not in {"file", "git_ref"}
            or not isinstance(locator.get("ref"), str)
            or not Path(locator["ref"]).is_absolute()
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(binding.get("baseline_identity_digest") or ""),
            )
        ):
            raise AuthorityDeniedError(
                "delegated mutation target binding is invalid"
            )
        return copy.deepcopy(binding)

    def _delegated_mutation_authority_context(
        self,
        run: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
        *,
        effect_recording: bool,
    ) -> dict[str, Any] | None:
        target = self._delegation_target_binding(run, records)
        if target is None:
            return None
        entered_sequence = self._node_entry_sequence(run, records)
        current = [
            record for record in records
            if int(record["sequence"]) > entered_sequence
            and record["node_id"] == run["current_node_id"]
        ]
        captures = [
            record for record in current
            if (record.get("event") or {}).get("event_type")
            == "repository_state_captured"
        ]
        pre_captures = [
            record for record in captures
            if ((record.get("event") or {}).get("details") or {}).get("phase")
            == "pre_action"
        ]
        post_captures = [
            record for record in captures
            if ((record.get("event") or {}).get("details") or {}).get("phase")
            == "post_action"
        ]
        if len(pre_captures) != 1:
            raise AuthorityDeniedError(
                "delegated mutation authority requires one authenticated repository "
                "pre-state capture at the current node"
            )
        pre = pre_captures[0]
        pre_details = pre["event"]["details"]
        pre_artifact = self.load_artifact(
            str(run["run_id"]), str(pre_details.get("artifact_id") or "")
        )
        if (
            pre_details.get("target_binding") != target
            or pre_artifact["locator"] != target["locator"]
            or pre_artifact["identity"]["kind"] != "composite"
            or pre_artifact["identity"]["digest"]
            != pre_details.get("identity_digest")
            or pre_artifact["media_type"]
            != "application/vnd.ora.repository-state+json"
        ):
            raise AuthorityDeniedError(
                "repository pre-state capture does not bind the approved target"
            )
        checkpoints = [
            record for record in current
            if int(record["sequence"]) > int(pre["sequence"])
            and (record.get("event") or {}).get("event_type")
            == "checkpoint_created"
            and ((record.get("event") or {}).get("details") or {}).get(
                "resume_node_id"
            ) == run["current_node_id"]
            and ((record.get("event") or {}).get("details") or {}).get(
                "artifact_identities", {}
            ).get(pre_details.get("artifact_id"))
            == pre_details.get("identity_digest")
        ]
        if len(checkpoints) != 1:
            raise AuthorityDeniedError(
                "delegated mutation authority requires one exact node-local checkpoint "
                "after the authenticated repository pre-state"
            )
        checkpoint = checkpoints[0]
        if effect_recording:
            authorizations = [
                record for record in current
                if (record.get("event") or {}).get("event_type")
                == "external_action_authorized"
            ]
            if len(authorizations) != 1:
                raise AuthorityDeniedError(
                    "recording a delegated mutation requires one prior runtime-issued "
                    "action authorization"
                )
            authorization = authorizations[0]
            authorization_details = authorization["event"]["details"]
            if (
                int(authorization["sequence"]) <= int(checkpoint["sequence"])
                or authorization_details.get("node_id") != run["current_node_id"]
                or authorization_details.get("node_external_effect") is not True
                or authorization_details.get("checkpoint_record_id")
                != checkpoint["record_id"]
                or authorization_details.get("target_binding") != target
                or authorization_details.get("approved_plan_digest")
                != run["contracts"]["approved_plan"]["digest"]
            ):
                raise AuthorityDeniedError(
                    "runtime-issued mutation authority is not bound to the current "
                    "checkpoint and approved target"
                )
            if len(post_captures) != 1:
                raise AuthorityDeniedError(
                    "recording a delegated mutation requires one authenticated "
                    "repository post-state capture"
                )
            post = post_captures[0]
            post_details = post["event"]["details"]
            post_artifact = self.load_artifact(
                str(run["run_id"]), str(post_details.get("artifact_id") or "")
            )
            if (
                int(post["sequence"]) <= int(checkpoint["sequence"])
                or int(post["sequence"]) <= int(authorization["sequence"])
                or post_details.get("target_binding") != target
                or post_artifact["locator"] != target["locator"]
                or post_artifact["identity"]["kind"] != "composite"
                or post_artifact["identity"]["digest"]
                != post_details.get("identity_digest")
                or post_artifact["media_type"]
                != "application/vnd.ora.repository-state+json"
            ):
                raise AuthorityDeniedError(
                    "repository post-state capture does not follow the exact checkpoint"
                )
        else:
            if post_captures or any(
                (record.get("event") or {}).get("event_type")
                in {"repository_mutation_receipt_issued", "action_completed"}
                for record in current
            ):
                raise AuthorityDeniedError(
                    "delegated mutation authority has already been exercised at this node"
                )
            post = None
            authorization = None
        return {
            "target_binding": target,
            "entered_sequence": entered_sequence,
            "pre_capture": pre,
            "checkpoint": checkpoint,
            "post_capture": post,
            "authorization": authorization,
            "current_records": current,
        }

    def _assert_delegated_target_current(
        self,
        context: Mapping[str, Any],
    ) -> None:
        """Recapture the approved target immediately before authority issuance."""

        try:
            from process_plan_approval import capture_target_identity
        except ImportError:  # pragma: no cover - package-qualified import
            from orchestrator.process_plan_approval import capture_target_identity
        current = capture_target_identity(
            context["target_binding"]["locator"]["ref"],
            captured_at=self._now(),
        )
        pre_details = context["pre_capture"]["event"]["details"]
        if (
            current["locator"] != context["target_binding"]["locator"]
            or current["identity"]["digest"] != pre_details["identity_digest"]
        ):
            raise AuthorityDeniedError(
                "approved repository target changed after the checkpointed pre-state; "
                "mutation authority is withheld"
            )

    def _node_allows_action_selectors(
        self,
        run: Mapping[str, Any],
        node: Mapping[str, Any],
        selectors: Sequence[str],
        records: Sequence[Mapping[str, Any]],
    ) -> bool:
        """Resolve graph access markers without widening delegated selectors."""

        direct_access = set(node["artifact_access"])
        exact_selectors = set(selectors)
        if exact_selectors.issubset(direct_access):
            return True
        if not node["external_effect"]:
            return "scope:declared_outputs" in direct_access
        if "scope:declared_external_effects" in direct_access:
            return True
        delegated_target = self._delegation_target_binding(run, records)
        external_scope = set(
            run["contracts"]["artifact_scope"]["external_effect_selectors"]
        )
        return bool(
            delegated_target is not None
            and "scope:declared_outputs" in direct_access
            and exact_selectors
            and exact_selectors.issubset(external_scope)
            and all(selector.startswith("artifact:") for selector in exact_selectors)
        )

    def preview_action_authorization(
        self,
        run_id: str,
        action: str,
        selectors: Sequence[str],
        *,
        satisfied_conditions: Sequence[str] = (),
        effect_type: str | None = None,
        scope_kind: str | None = None,
    ) -> list[str]:
        """Validate whether authority is issuable without issuing it."""

        with _locked():
            grant_ids = self._authorize_action(
                run_id,
                action,
                selectors,
                satisfied_conditions=satisfied_conditions,
                effect_type=effect_type,
                scope_kind=scope_kind,
                effect_recording=False,
            )
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if (
                node["kind"] == "action"
                and node["external_effect"] is True
                and node["operation"] == action
            ):
                context = self._delegated_mutation_authority_context(
                    run, self.load_records(run_id), effect_recording=False
                )
                if context is not None:
                    self._assert_delegated_target_current(context)
            return grant_ids

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
        with _locked():
            grant_ids = self._authorize_action(
                run_id,
                action,
                selectors,
                satisfied_conditions=satisfied_conditions,
                effect_type=effect_type,
                scope_kind=scope_kind,
                effect_recording=False,
            )
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            records = self.load_records(run_id)
            if (
                node["kind"] == "action"
                and node["external_effect"] is True
                and node["operation"] == action
            ):
                context = self._delegated_mutation_authority_context(
                    run, records, effect_recording=False
                )
                if context is not None:
                    self._assert_delegated_target_current(context)
                    authorization = {
                        "action": action,
                        "selectors": list(selectors),
                        "grant_ids": grant_ids,
                        "satisfied_conditions": list(satisfied_conditions),
                        "effect_type": effect_type,
                        "scope_kind": scope_kind,
                        "node_id": run["current_node_id"],
                        "node_external_effect": True,
                        "checkpoint_record_id": context["checkpoint"]["record_id"],
                        "pre_state_identity": {
                            "artifact_id": context["pre_capture"]["event"][
                                "details"
                            ]["artifact_id"],
                            "identity_digest": context["pre_capture"]["event"][
                                "details"
                            ]["identity_digest"],
                        },
                        "target_binding": context["target_binding"],
                        "approved_plan_digest": run["contracts"]["approved_plan"][
                            "digest"
                        ],
                    }
                    prior = [
                        record for record in context["current_records"]
                        if (record.get("event") or {}).get("event_type")
                        == "external_action_authorized"
                    ]
                    if prior:
                        if (
                            len(prior) != 1
                            or prior[0]["event"]["details"] != authorization
                        ):
                            raise AuthorityDeniedError(
                                "a different mutation authority was already issued "
                                "at this node"
                            )
                    else:
                        self._append_event_locked(
                            run,
                            "external_action_authorized",
                            authorization,
                            node_id=run["current_node_id"],
                            runtime_authoritative=True,
                        )
            return grant_ids

    def _authorize_action(
        self,
        run_id: str,
        action: str,
        selectors: Sequence[str],
        *,
        satisfied_conditions: Sequence[str] = (),
        effect_type: str | None = None,
        scope_kind: str | None = None,
        effect_recording: bool,
    ) -> list[str]:
        if not selectors:
            raise AuthorityDeniedError("an authorized action requires at least one selector")
        if effect_type is None:
            raise AuthorityDeniedError("an authorized action requires an explicit effect_type")
        run = self.load_run(run_id)
        self._require_mutable_run(run, f"authorize action {action}")
        definition = self.load_definition(run_id)
        nodes = self._graph_nodes(definition)
        graph_bound_nodes = [
            node for node in nodes.values()
            if node["kind"] == "action"
            and node["external_effect"] is True
            and node["operation"] == action
        ]
        bound_node = None
        if graph_bound_nodes:
            current_node = nodes[run["current_node_id"]]
            if (
                current_node["kind"] != "action"
                or current_node["operation"] != action
            ):
                raise AuthorityDeniedError(
                    "graph-bound action authority is available only at its exact "
                    "current Process Definition node"
                )
            expected_scope_kind = (
                "external" if current_node["external_effect"] else "write"
            )
            if scope_kind != expected_scope_kind:
                raise AuthorityDeniedError(
                    "graph-bound action scope must match the Process Definition "
                    "external-effect classification"
                )
            if current_node["external_effect"]:
                self._delegated_mutation_authority_context(
                    run,
                    self.load_records(run_id),
                    effect_recording=effect_recording,
                )
            bound_node = current_node
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
        if bound_node is not None and not self._node_allows_action_selectors(
            run,
            bound_node,
            selectors,
            self.load_records(run_id),
        ):
            raise AuthorityDeniedError(
                "graph-bound action selectors are outside the Process Definition "
                "node access contract"
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
        action_details = copy.deepcopy(dict(details or {}))
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            nodes = self._graph_nodes(definition)
            node = nodes[run["current_node_id"]]
            requested_external = bool(external_effect)
            completion_operation = str(action_details.get("operation") or "")
            graph_bound_action = any(
                candidate["kind"] == "action"
                and candidate["external_effect"] is True
                and candidate["operation"] == action
                for candidate in nodes.values()
            )
            if graph_bound_action and (
                node["kind"] != "action" or node["operation"] != action
            ):
                raise AuthorityDeniedError(
                    "graph-bound action cannot fall through to generic effect "
                    "recording at another Process Definition node"
                )
            if graph_bound_action and completion_operation != action:
                raise AuthorityDeniedError(
                    "graph-bound action record must identify its exact current "
                    "Process Definition operation"
                )
            completion_bound = (
                node["kind"] == "action"
                and completion_operation == node["operation"]
            )
            if completion_bound:
                declared_external = bool(node["external_effect"])
                if requested_external != declared_external:
                    raise AuthorityDeniedError(
                        "action external-effect classification is fixed by the "
                        "current Process Definition node"
                    )
                authoritative_external = declared_external
            else:
                # Generic effect observations remain useful to recovery and
                # controlled-probe machinery, but cannot complete this action
                # node because they carry no runtime-issued node binding.
                authoritative_external = requested_external

            scope_kind = "external" if authoritative_external else "write"
            grant_ids = self._authorize_action(
                run_id,
                action,
                selectors,
                satisfied_conditions=satisfied_conditions,
                effect_type=effect_type,
                scope_kind=scope_kind,
                effect_recording=completion_bound and authoritative_external,
            )
            if receipt_artifact_id is not None:
                receipt = self.load_artifact(run_id, receipt_artifact_id)
                if receipt["role"] != "external_effect_receipt":
                    raise GovernedRuntimeError(
                        "external-effect receipt must use that artifact role"
                    )
            else:
                receipt = None
            if receipt is not None and not authoritative_external:
                raise GovernedRuntimeError(
                    "a receipt may be bound only to an external effect"
                )
            if completion_bound and authoritative_external:
                records = self.load_records(run_id)
                repository_context = self._delegated_mutation_authority_context(
                    run, records, effect_recording=True
                )
                if repository_context is not None:
                    issued = [
                        record for record in repository_context["current_records"]
                        if (record.get("event") or {}).get("event_type")
                        == "repository_mutation_receipt_issued"
                    ]
                    if len(issued) != 1 or receipt is None:
                        raise GovernedRuntimeError(
                            "delegated mutation recording requires one runtime-issued "
                            "repository receipt"
                        )
                    issued_record = issued[0]
                    issued_details = issued_record["event"]["details"]
                    pre_details = repository_context["pre_capture"]["event"][
                        "details"
                    ]
                    post_details = repository_context["post_capture"]["event"][
                        "details"
                    ]
                    authorization = repository_context["authorization"]
                    authorization_details = authorization["event"]["details"]
                    expected_pre = {
                        "artifact_id": pre_details["artifact_id"],
                        "identity_digest": pre_details["identity_digest"],
                    }
                    expected_post = {
                        "artifact_id": post_details["artifact_id"],
                        "identity_digest": post_details["identity_digest"],
                    }
                    if (
                        issued_details.get("operation") != node["operation"]
                        or authorization_details.get("action") != action
                        or authorization_details.get("selectors") != list(selectors)
                        or authorization_details.get("grant_ids") != grant_ids
                        or authorization_details.get("effect_type") != effect_type
                        or authorization_details.get("scope_kind") != "external"
                        or int(authorization["sequence"])
                        >= int(repository_context["post_capture"]["sequence"])
                        or issued_details.get("target_binding")
                        != repository_context["target_binding"]
                        or issued_details.get("checkpoint_record_id")
                        != repository_context["checkpoint"]["record_id"]
                        or issued_details.get("pre_state_identity") != expected_pre
                        or issued_details.get("post_state_identity") != expected_post
                        or issued_details.get("receipt_artifact_id")
                        != receipt_artifact_id
                        or issued_details.get("receipt_identity_digest")
                        != receipt["identity"]["digest"]
                        or action_details.get("pre_state_identity") != expected_pre
                        or action_details.get("post_state_identity") != expected_post
                        or set(receipt["lineage"]["source_artifact_ids"])
                        != {expected_pre["artifact_id"], expected_post["artifact_id"]}
                        or int(issued_record["sequence"])
                        <= int(repository_context["post_capture"]["sequence"])
                    ):
                        raise GovernedRuntimeError(
                            "delegated mutation receipt does not bind the exact "
                            "approved repository transition"
                        )
            return self._record_runtime_event(
                run_id,
                "action_completed",
                {
                    "action": action,
                    "selectors": list(selectors),
                    "grant_ids": grant_ids,
                    "satisfied_conditions": list(satisfied_conditions),
                    "effect_type": effect_type,
                    "external_effect": authoritative_external,
                    "node_external_effect": (
                        bool(node["external_effect"]) if completion_bound else None
                    ),
                    "completion_operation": (
                        node["operation"] if completion_bound else None
                    ),
                    "receipt_artifact_id": receipt_artifact_id,
                    "receipt_identity_digest": (
                        receipt["identity"]["digest"] if receipt is not None else None
                    ),
                    "details": action_details,
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

    def execute_controlled_probe_action(
        self,
        run_id: str,
        probe_id: str,
        *,
        inspection_command: Mapping[str, Any] | None = None,
        mutation_executor: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Invoke the persisted action and mint its reserved execution record.

        This is the only public path that may create
        ``controlled_probe_execution_completed``. Inspection commands run in
        the runtime-owned deny-default sandbox. Mutation execution creates the
        persisted contract checkpoint before the callable is invoked.
        """

        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "execute a controlled probe action")
            records = self.load_records(run_id)
            contract, contract_record = self._controlled_probe_contract_from_records(
                records, probe_id
            )
            contract_digest = (
                (contract_record.get("event") or {}).get("details") or {}
            ).get("contract_digest")
            starts = []
            completions = set()
            executions = []
            execution_starts = []
            for record in records:
                event = record.get("event") or {}
                details = event.get("details") or {}
                if details.get("probe_id") != probe_id:
                    continue
                if event.get("event_type") == "controlled_probe_attempt_started":
                    starts.append((record, details))
                elif event.get("event_type") == "controlled_probe_attempt_completed":
                    completions.add(details.get("attempt"))
                elif event.get("event_type") == "controlled_probe_execution_completed":
                    executions.append(details)
                elif event.get("event_type") == "controlled_probe_execution_started":
                    execution_starts.append(details)
            active = [
                (record, details)
                for record, details in starts
                if details.get("attempt") not in completions
            ]
            if len(active) != 1:
                raise RunConflictError(
                    "controlled probe execution requires exactly one active attempt"
                )
            started_record, started_details = active[0]
            attempt = int(started_details["attempt"])
            if started_details.get("contract_digest") != contract_digest:
                raise GovernedRuntimeError(
                    "controlled probe execution contract digest does not match"
                )
            if any(
                item.get("attempt") == attempt
                and item.get("contract_digest") == contract_digest
                for item in [*execution_starts, *executions]
            ):
                raise RunConflictError(
                    "controlled probe action already has a runtime execution claim; "
                    "replay is refused"
                )
            execution_start_record = self._append_event_locked(
                run,
                "controlled_probe_execution_started",
                {
                    "probe_id": probe_id,
                    "attempt": attempt,
                    "contract_digest": contract_digest,
                    "capability_id": contract["capability_identity"]["capability_id"],
                    "capability_identity_digest": contract["capability_identity"][
                        "identity_digest"
                    ],
                    "action": contract["action_identity"]["action"],
                    "effect_class": contract["action_identity"]["effect_class"],
                    "effect_type": contract["action_identity"]["effect_type"],
                    "selector": contract["selector"],
                },
                node_id=contract["node_id"],
                runtime_authoritative=True,
            )

        action = contract["action_identity"]
        capability = contract["capability_identity"]
        safety = contract.get("mutation_safety") or {}
        mutation = action["effect_class"] == "mutation"
        request = {
            "run_id": run_id,
            "probe_id": probe_id,
            "assumption_id": contract["assumption_id"],
            "contract_digest": contract_digest,
            "definition_ref": copy.deepcopy(contract["definition_ref"]),
            "approved_plan_ref": copy.deepcopy(contract["approved_plan_ref"]),
            "capability_id": capability["capability_id"],
            "capability_identity_digest": capability["identity_digest"],
            "action": action["action"],
            "effect_class": action["effect_class"],
            "effect_type": action["effect_type"],
            "selector": contract["selector"],
            "attempt": attempt,
            "max_attempts": contract["max_attempts"],
            "pre_state_digest": safety.get("pre_state_digest"),
            "idempotency_key": safety.get("idempotency_key"),
        }
        boundary_identity: dict[str, Any]
        if mutation:
            if inspection_command is not None or not callable(mutation_executor):
                raise ControlledProbeExecutionError(
                    "mutation controlled probe requires only a callable executor"
                )
            try:
                checkpoint = self.create_checkpoint(
                    run_id,
                    safety["checkpoint_id"],
                    segment_id=contract["segment_id"],
                    resume_node_id=contract["node_id"],
                )
            except Exception as exc:
                raise ControlledProbeExecutionError(
                    f"controlled probe checkpoint failed: {type(exc).__name__}: {exc}"
                ) from exc
            try:
                raw_result = mutation_executor(copy.deepcopy(request))
            except Exception as exc:
                raise ControlledProbeExecutionError(
                    f"controlled probe mutation executor failed: {type(exc).__name__}: {exc}",
                    external_effect_possible=True,
                ) from exc
            boundary_identity = {
                "kind": "runtime_mutation_executor",
                "checkpoint_record_id": checkpoint["record_id"],
                "checkpoint_id": safety["checkpoint_id"],
            }
        else:
            if mutation_executor is not None or not isinstance(inspection_command, Mapping):
                raise ControlledProbeExecutionError(
                    "inspection controlled probe requires only a sandbox command descriptor"
                )
            descriptor = copy.deepcopy(dict(inspection_command))
            if set(descriptor) != {"argv", "cwd", "timeout_seconds"}:
                raise ControlledProbeExecutionError(
                    "inspection sandbox descriptor fields are incomplete or ambiguous"
                )
            argv = descriptor["argv"]
            cwd = descriptor["cwd"]
            timeout_seconds = descriptor["timeout_seconds"]
            if not isinstance(argv, list) or not argv or any(
                not isinstance(item, str) or not item for item in argv
            ):
                raise ControlledProbeExecutionError(
                    "inspection sandbox argv must be a nonempty string list"
                )
            executable = Path(argv[0])
            if not executable.is_absolute() or not executable.is_file():
                raise ControlledProbeExecutionError(
                    "inspection sandbox executable must be an existing absolute path"
                )
            if cwd is not None and (not isinstance(cwd, str) or not Path(cwd).is_dir()):
                raise ControlledProbeExecutionError(
                    "inspection sandbox cwd must be an existing directory"
                )
            if (
                not isinstance(timeout_seconds, int)
                or isinstance(timeout_seconds, bool)
                or timeout_seconds < 1
            ):
                raise ControlledProbeExecutionError(
                    "inspection sandbox timeout must be an integer >= 1"
                )
            sandbox = Path("/usr/bin/sandbox-exec")
            if not sandbox.is_file():
                raise ControlledProbeExecutionError(
                    "read-only inspection sandbox is unavailable"
                )
            environment = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            }
            try:
                completed = subprocess.run(
                    [
                        str(sandbox),
                        "-p",
                        _READ_ONLY_INSPECTION_SANDBOX_PROFILE,
                        *argv,
                    ],
                    input=json.dumps(request, sort_keys=True, separators=(",", ":")),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=cwd,
                    env=environment,
                    timeout=timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ControlledProbeExecutionError(
                    f"read-only inspection boundary failed: {type(exc).__name__}: {exc}"
                ) from exc
            if completed.returncode != 0:
                reason = completed.stderr.strip() or f"exit status {completed.returncode}"
                raise ControlledProbeExecutionError(
                    f"read-only inspection boundary refused or failed the command: {reason}"
                )
            try:
                raw_result = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise ControlledProbeExecutionError(
                    "read-only inspection command must emit exactly one JSON result"
                ) from exc
            boundary_identity = {
                "kind": "deny_default_inspection_sandbox",
                "command_identity_digest": _digest_json(descriptor),
                "sandbox_profile_digest": _digest_text(
                    _READ_ONLY_INSPECTION_SANDBOX_PROFILE
                ),
            }

        try:
            _require_json(raw_result, "controlled probe execution output")
            output = copy.deepcopy(raw_result)
            output_digest = _digest_json(output)
            reported_outcome = (
                output.get("outcome") if isinstance(output, Mapping) else None
            )
            evidence_text = (
                output.get("evidence") if isinstance(output, Mapping) else None
            )
            evidence_identity_digest = (
                _digest_text(evidence_text)
                if isinstance(evidence_text, str) and evidence_text
                else None
            )
            raw_receipt = output.get("receipt") if isinstance(output, Mapping) else None
            receipt_identity_digest = None
            if isinstance(raw_receipt, Mapping):
                receipt_text = json.dumps(
                    raw_receipt, sort_keys=True, separators=(",", ":")
                )
                receipt_identity_digest = _digest_text(receipt_text)
            record = self._record_runtime_event(
                run_id,
                "controlled_probe_execution_completed",
                {
                    "probe_id": probe_id,
                    "attempt": attempt,
                    "contract_digest": contract_digest,
                    "capability_id": capability["capability_id"],
                    "capability_identity_digest": capability["identity_digest"],
                    "action": action["action"],
                    "effect_class": action["effect_class"],
                    "effect_type": action["effect_type"],
                    "selector": contract["selector"],
                    "execution_start_record_id": execution_start_record["record_id"],
                    "boundary_identity": boundary_identity,
                    "output_digest": output_digest,
                    "reported_outcome": reported_outcome,
                    "evidence_identity_digest": evidence_identity_digest,
                    "receipt_identity_digest": receipt_identity_digest,
                },
                node_id=contract["node_id"],
            )
        except Exception as exc:
            if isinstance(exc, ControlledProbeExecutionError):
                raise
            raise ControlledProbeExecutionError(
                f"controlled probe execution record failed: {type(exc).__name__}: {exc}",
                external_effect_possible=mutation,
            ) from exc
        return {
            "result": output,
            "request": request,
            "record": record,
            "output_digest": output_digest,
            "evidence_identity_digest": evidence_identity_digest,
            "receipt_identity_digest": receipt_identity_digest,
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
                    "execution_record_id",
                    "execution_output_digest",
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

                execution_matches = []
                for candidate in records:
                    event = candidate.get("event") or {}
                    event_details = event.get("details") or {}
                    if (
                        event.get("event_type")
                        == "controlled_probe_execution_completed"
                        and event_details.get("probe_id") == probe_id
                        and event_details.get("attempt") == attempt
                        and event_details.get("contract_digest") == contract_digest
                    ):
                        execution_matches.append((candidate, event_details))
                if len(execution_matches) != 1:
                    raise GovernedRuntimeError(
                        "controlled probe completion requires exactly one runtime-issued "
                        "execution record"
                    )
                execution_record, execution_details = execution_matches[0]
                if int(execution_record["sequence"]) <= int(started_record["sequence"]):
                    raise GovernedRuntimeError(
                        "controlled probe execution record predates its active attempt"
                    )
                execution_start_matches = []
                for candidate in records:
                    event = candidate.get("event") or {}
                    event_details = event.get("details") or {}
                    if (
                        event.get("event_type") == "controlled_probe_execution_started"
                        and event_details.get("probe_id") == probe_id
                        and event_details.get("attempt") == attempt
                        and event_details.get("contract_digest") == contract_digest
                    ):
                        execution_start_matches.append((candidate, event_details))
                if len(execution_start_matches) != 1:
                    raise GovernedRuntimeError(
                        "controlled probe completion requires one runtime execution start"
                    )
                execution_start_record, execution_start_details = (
                    execution_start_matches[0]
                )
                if not (
                    int(started_record["sequence"])
                    < int(execution_start_record["sequence"])
                    < int(execution_record["sequence"])
                ):
                    raise GovernedRuntimeError(
                        "controlled probe runtime execution ordering is invalid"
                    )
                if (
                    execution_details.get("execution_start_record_id")
                    != execution_start_record["record_id"]
                ):
                    raise GovernedRuntimeError(
                        "controlled probe execution output does not bind its start record"
                    )
                execution_bindings = {
                    "execution_record_id": execution_record["record_id"],
                    "execution_output_digest": execution_details.get("output_digest"),
                }
                execution_mismatch = [
                    field
                    for field, expected in execution_bindings.items()
                    if supplied_details.get(field) != expected
                ]
                expected_execution = {
                    "capability_id": capability["capability_id"],
                    "capability_identity_digest": capability["identity_digest"],
                    "action": action["action"],
                    "effect_class": action["effect_class"],
                    "effect_type": action["effect_type"],
                    "selector": contract["selector"],
                    "reported_outcome": outcome,
                    "evidence_identity_digest": evidence_identity_digest,
                    "receipt_identity_digest": receipt_identity_digest,
                }
                expected_execution_start = {
                    "capability_id": capability["capability_id"],
                    "capability_identity_digest": capability["identity_digest"],
                    "action": action["action"],
                    "effect_class": action["effect_class"],
                    "effect_type": action["effect_type"],
                    "selector": contract["selector"],
                }
                execution_mismatch.extend(
                    field
                    for field, expected in expected_execution.items()
                    if execution_details.get(field) != expected
                )
                execution_mismatch.extend(
                    f"execution_start.{field}"
                    for field, expected in expected_execution_start.items()
                    if execution_start_details.get(field) != expected
                )
                expected_boundary_kind = (
                    "runtime_mutation_executor"
                    if mutation
                    else "deny_default_inspection_sandbox"
                )
                boundary_identity = execution_details.get("boundary_identity") or {}
                if boundary_identity.get("kind") != expected_boundary_kind:
                    execution_mismatch.append("boundary_identity")
                if execution_mismatch:
                    raise GovernedRuntimeError(
                        "controlled probe completion is not bound to exact runtime execution: "
                        + ", ".join(sorted(set(execution_mismatch)))
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
                    if int(candidate["sequence"]) <= int(execution_record["sequence"]):
                        raise GovernedRuntimeError(
                            "controlled probe completion artifact predates runtime execution"
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
                    checkpoint_id = contract["mutation_safety"]["checkpoint_id"]
                    checkpoints = []
                    for candidate in records:
                        event = candidate.get("event") or {}
                        event_details = event.get("details") or {}
                        if (
                            event.get("event_type") == "checkpoint_created"
                            and event_details.get("checkpoint_id") == checkpoint_id
                        ):
                            checkpoints.append(candidate)
                    if len(checkpoints) != 1:
                        raise GovernedRuntimeError(
                            "mutation probe completion requires its exact checkpoint"
                        )
                    checkpoint_record = checkpoints[0]
                    if not (
                        int(started_record["sequence"])
                        < int(checkpoint_record["sequence"])
                        < int(execution_record["sequence"])
                    ):
                        raise GovernedRuntimeError(
                            "mutation probe checkpoint must occur after attempt start and "
                            "before execution"
                        )
                    if boundary_identity.get("checkpoint_id") != checkpoint_id:
                        raise GovernedRuntimeError(
                            "mutation execution record checkpoint identity does not match"
                        )
                    if (
                        boundary_identity.get("checkpoint_record_id")
                        != checkpoint_record["record_id"]
                    ):
                        raise GovernedRuntimeError(
                            "mutation execution record does not bind the checkpoint record"
                        )
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

    @staticmethod
    def _is_automation_definition(definition: Mapping[str, Any]) -> bool:
        return isinstance(
            (definition.get("output_schema") or {}).get("x-ora-process"),
            Mapping,
        )

    def begin_attempt(self, run_id: str, segment_id: str) -> dict[str, Any]:
        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if self._is_automation_definition(definition):
                raise AuthorityDeniedError(
                    "G1.18 Runs require the dedicated automation attempt API"
                )
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

    def _automation_attempt_budget(
        self,
        run_id: str,
        definition: Mapping[str, Any],
        segment_id: str,
    ) -> tuple[int, int, int]:
        metadata = (
            (definition.get("output_schema") or {})
            .get("x-ora-process")
        )
        if not isinstance(metadata, Mapping):
            raise GovernedRuntimeError(
                "automation attempt accounting requires x-ora-process metadata"
            )
        allowance = metadata.get("max_correction_attempts")
        if isinstance(allowance, bool) or not isinstance(allowance, int) or allowance < 0:
            raise GovernedRuntimeError(
                "automation correction-attempt allowance is invalid"
            )
        attempts_by_segment: dict[str, int] = {}
        for record in self.load_records(run_id):
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") != "attempt_started":
                continue
            persisted_segment = str(details.get("segment_id") or "")
            attempts_by_segment[persisted_segment] = (
                attempts_by_segment.get(persisted_segment, 0) + 1
            )
        corrections_used = sum(
            max(0, count - 1) for count in attempts_by_segment.values()
        )
        return allowance, corrections_used, attempts_by_segment.get(segment_id, 0)

    def begin_automation_attempt(
        self,
        run_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        """Reserve an automation baseline or correction attempt without stealing future baselines."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if segment_id != run["current_node_id"]:
                raise RunConflictError(
                    "automation attempt segment must match the current graph node"
                )
            current_node = self._graph_nodes(definition).get(segment_id)
            if not current_node or current_node["kind"] not in {
                "action", "verification_boundary",
            }:
                raise GovernedRuntimeError(
                    "automation attempts require an action or verification boundary"
                )
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
                raise RunConflictError(
                    "the active attempt must complete before another begins"
                )
            correction = run["contracts"]["correction_loop"]
            current = int(correction["attempt"])
            maximum = int(correction["max_attempts"])
            allowance, corrections_used, prior_segment_attempts = (
                self._automation_attempt_budget(run_id, definition, segment_id)
            )
            if current >= maximum or (
                prior_segment_attempts > 0 and corrections_used >= allowance
            ):
                raise CorrectionDecisionRequired(
                    "automation attempt ceiling reached; reserved baseline attempts "
                    "cannot be consumed as additional corrections"
                )
            correction["attempt"] = current + 1
            return self._append_event_locked(
                run,
                "attempt_started",
                {
                    "segment_id": segment_id,
                    "attempt": correction["attempt"],
                    "max_attempts": maximum,
                    "attempt_api": "automation",
                },
                node_id=run["current_node_id"],
                runtime_authoritative=True,
            )

    def block_at_attempt_ceiling(
        self,
        run_id: str,
        *,
        segment_id: str,
        target_node_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Persist the fail-closed terminal route after attempt admission is denied."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            correction = run["contracts"]["correction_loop"]
            if run["state"] != "running":
                raise RunConflictError(
                    "attempt-ceiling blocking requires a running Process Run"
                )
            if segment_id != run["current_node_id"]:
                raise RunConflictError(
                    "attempt-ceiling segment must match the current graph node"
                )
            allowance, corrections_used, prior_segment_attempts = (
                self._automation_attempt_budget(run_id, definition, segment_id)
            )
            global_ceiling = int(correction["attempt"]) >= int(
                correction["max_attempts"]
            )
            correction_ceiling = (
                prior_segment_attempts > 0 and corrections_used >= allowance
            )
            if not global_ceiling and not correction_ceiling:
                raise CorrectionDecisionRequired(
                    "attempt-ceiling blocking is unavailable before the ceiling"
                )
            nodes = self._graph_nodes(definition)
            target = nodes.get(target_node_id)
            if not target or not (
                target["kind"] == "terminal_state"
                and target["outcome"] == "blocked"
            ):
                raise GovernedRuntimeError(
                    "attempt ceiling must route to a declared blocked terminal state"
                )
            if target_node_id not in set(
                run["contracts"]["approved_plan"]["approved_node_ids"]
            ):
                raise AuthorityDeniedError(
                    "attempt-ceiling target is outside the approved plan"
                )
            return self._mechanical_block_locked(
                run,
                source_node_id=run["current_node_id"],
                target_node_id=target_node_id,
                reason=reason,
            )

    def block_by_process_run_control(
        self,
        run_id: str,
        *,
        control_request_record_id: str,
        target_node_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Apply a Principal-authenticated stop as a mechanical blocked route.

        A user stop is not a model judgment.  It may therefore reach the
        graph-declared blocked terminal only after the dedicated control path
        has persisted one exact request and its matching applied record.
        """

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if run["state"] != "running":
                raise RunConflictError(
                    "Process Run control blocking requires a running Run"
                )
            if not self._is_automation_definition(definition):
                raise AuthorityDeniedError(
                    "Process Run control blocking is reserved for automated Processes"
                )
            nodes = self._graph_nodes(definition)
            target = nodes.get(target_node_id)
            if not target or not (
                target["kind"] == "terminal_state"
                and target["outcome"] == "blocked"
            ):
                raise GovernedRuntimeError(
                    "Process Run control must use a declared blocked terminal state"
                )
            if target_node_id not in set(
                run["contracts"]["approved_plan"]["approved_node_ids"]
            ):
                raise AuthorityDeniedError(
                    "Process Run control target is outside the approved plan"
                )
            records = self.load_records(run_id)
            requests = [
                record for record in records
                if record["record_id"] == control_request_record_id
                and (record.get("event") or {}).get("event_type")
                == "process_run_control_requested"
            ]
            applied = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "process_run_control_applied"
                and (record.get("event") or {}).get("details", {}).get(
                    "control_request_record_id"
                ) == control_request_record_id
            ]
            if len(requests) != 1 or len(applied) != 1:
                raise AuthorityDeniedError(
                    "Process Run stop lacks one exact authenticated request/application pair"
                )
            request = requests[0]
            request_details = request["event"]["details"]
            applied_details = applied[0]["event"]["details"]
            if (
                request_details.get("action") != "stop"
                or applied_details.get("action") != "stop"
                or request_details.get("run_id") != run_id
                or applied_details.get("run_id") != run_id
                or request_details.get("definition_ref") != run["definition_ref"]
                or applied_details.get("definition_ref") != run["definition_ref"]
                or request_details.get("node_id") != run["current_node_id"]
                or applied_details.get("node_id") != run["current_node_id"]
                or request_details.get("idempotency_key")
                != applied_details.get("idempotency_key")
                or request_details.get("decision_by")
                != run["contracts"]["authority"]["principal_id"]
            ):
                raise AuthorityDeniedError(
                    "Process Run stop records do not bind the current Run authority"
                )
            return self._mechanical_block_locked(
                run,
                source_node_id=run["current_node_id"],
                target_node_id=target_node_id,
                reason=reason,
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
            definition = self.load_definition(run_id)
            if self._is_automation_definition(definition):
                raise AuthorityDeniedError(
                    "G1.18 Runs require the dedicated automation attempt API"
                )
            return self._complete_attempt_locked(
                run_id,
                run,
                segment_id,
                defect_codes=defect_codes,
                evidence_refs=evidence_refs,
                artifact_digests=artifact_digests,
            )

    def complete_automation_attempt(
        self,
        run_id: str,
        segment_id: str,
        *,
        defect_codes: Sequence[str],
        evidence_refs: Sequence[Mapping[str, Any]],
        artifact_digests: Sequence[str],
    ) -> dict[str, Any]:
        """Complete only the active current-node G1.18 attempt."""

        with _locked():
            run = self.load_run(run_id)
            definition = self.load_definition(run_id)
            if not self._is_automation_definition(definition):
                raise AuthorityDeniedError(
                    "the dedicated automation attempt API requires a G1.18 Run"
                )
            if segment_id != run["current_node_id"]:
                raise RunConflictError(
                    "automation attempt segment must match the current graph node"
                )
            current_node = self._graph_nodes(definition).get(segment_id)
            if not current_node or current_node["kind"] not in {
                "action", "verification_boundary",
            }:
                raise GovernedRuntimeError(
                    "automation attempts require an action or verification boundary"
                )
            latest_attempt = next(
                (
                    record.get("event") or {}
                    for record in reversed(self.load_records(run_id))
                    if (record.get("event") or {}).get("event_type")
                    in {"attempt_started", "attempt_completed"}
                ),
                None,
            )
            if (
                not latest_attempt
                or latest_attempt.get("event_type") != "attempt_started"
                or (latest_attempt.get("details") or {}).get("attempt_api")
                != "automation"
            ):
                raise AuthorityDeniedError(
                    "automation completion requires a specialized automation start"
                )
            return self._complete_attempt_locked(
                run_id,
                run,
                segment_id,
                defect_codes=defect_codes,
                evidence_refs=evidence_refs,
                artifact_digests=artifact_digests,
            )

    def _complete_attempt_locked(
        self,
        run_id: str,
        run: dict[str, Any],
        segment_id: str,
        *,
        defect_codes: Sequence[str],
        evidence_refs: Sequence[Mapping[str, Any]],
        artifact_digests: Sequence[str],
    ) -> dict[str, Any]:
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

    def _record_repository_state_capture(
        self,
        run_id: str,
        artifact_id: str,
        capture: Mapping[str, Any],
        *,
        phase: str,
        satisfied_conditions: Sequence[str],
    ) -> dict[str, Any]:
        """Persist a service-captured approved repository identity.

        Only the Phase 2.4 delegation service calls this seam, after it has
        captured the target itself.  Ordinary Artifact recording cannot mint
        the reserved ``repository_state_captured`` authority fact.
        """

        if phase not in {"pre_action", "post_action"}:
            raise GovernedRuntimeError(
                "repository state phase must be pre_action or post_action"
            )
        exact_capture = copy.deepcopy(dict(capture))
        if set(exact_capture) != {"locator", "identity", "state"}:
            raise GovernedRuntimeError("repository state capture is incomplete")
        locator = exact_capture.get("locator")
        identity = exact_capture.get("identity")
        state = exact_capture.get("state")
        if (
            not isinstance(locator, dict)
            or set(locator) != {"kind", "ref"}
            or not isinstance(identity, dict)
            or set(identity) != {"kind", "digest", "coverage", "captured_at"}
            or not isinstance(state, dict)
            or identity.get("kind") != "composite"
            or identity.get("digest") != _digest_json(state)
            or state.get("root") != locator.get("ref")
            or (
                locator.get("kind") == "git_ref"
                and state.get("kind") != "git_worktree_composite"
            )
            or (
                locator.get("kind") == "file"
                and state.get("kind") != "directory_composite"
            )
        ):
            raise GovernedRuntimeError(
                "repository state capture is not a normalized target composite"
            )
        captured_at = str(identity.get("captured_at") or "")
        captured_time = _parse_time(captured_at)
        fresh_until = (captured_time + timedelta(hours=1)).isoformat().replace(
            "+00:00", "Z"
        )

        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "capture approved repository state")
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "action" or not node["external_effect"]:
                raise AuthorityDeniedError(
                    "repository state capture requires the current external-effect node"
                )
            records = self.load_records(run_id)
            target = self._delegation_target_binding(run, records)
            if target is None or locator != target["locator"]:
                raise AuthorityDeniedError(
                    "repository state capture locator differs from the approved target"
                )
            entered_sequence = self._node_entry_sequence(run, records)
            current = [
                record for record in records
                if int(record["sequence"]) > entered_sequence
                and record["node_id"] == run["current_node_id"]
            ]
            current_captures = [
                record for record in current
                if (record.get("event") or {}).get("event_type")
                == "repository_state_captured"
            ]
            current_checkpoints = [
                record for record in current
                if (record.get("event") or {}).get("event_type")
                == "checkpoint_created"
                and ((record.get("event") or {}).get("details") or {}).get(
                    "resume_node_id"
                ) == run["current_node_id"]
            ]
            if phase == "pre_action":
                if current_captures or current_checkpoints:
                    raise RunConflictError(
                        "repository pre-state must be captured exactly once before "
                        "the node-local checkpoint"
                    )
                prior_posts = [
                    record for record in records
                    if int(record["sequence"]) <= entered_sequence
                    and (record.get("event") or {}).get("event_type")
                    == "repository_state_captured"
                    and ((record.get("event") or {}).get("details") or {}).get(
                        "phase"
                    ) == "post_action"
                ]
                expected_digest = (
                    prior_posts[-1]["event"]["details"]["identity_digest"]
                    if prior_posts
                    else target["baseline_identity_digest"]
                )
                if identity["digest"] != expected_digest:
                    raise AuthorityDeniedError(
                        "repository pre-state differs from the approved or last "
                        "authenticated target identity"
                    )
                source_ids: list[str] = []
            else:
                pre_captures = [
                    record for record in current_captures
                    if record["event"]["details"].get("phase") == "pre_action"
                ]
                post_captures = [
                    record for record in current_captures
                    if record["event"]["details"].get("phase") == "post_action"
                ]
                if len(pre_captures) != 1 or post_captures:
                    raise RunConflictError(
                        "repository post-state requires one current pre-state and "
                        "cannot be recorded twice"
                    )
                pre = pre_captures[0]
                checkpoints = [
                    record for record in current_checkpoints
                    if int(record["sequence"]) > int(pre["sequence"])
                    and ((record.get("event") or {}).get("details") or {}).get(
                        "artifact_identities", {}
                    ).get(pre["event"]["details"]["artifact_id"])
                    == pre["event"]["details"]["identity_digest"]
                ]
                if len(checkpoints) != 1:
                    raise AuthorityDeniedError(
                        "repository post-state requires the exact authorized checkpoint"
                    )
                authorizations = [
                    record for record in current
                    if (record.get("event") or {}).get("event_type")
                    == "external_action_authorized"
                ]
                if (
                    len(authorizations) != 1
                    or int(authorizations[0]["sequence"])
                    <= int(checkpoints[0]["sequence"])
                    or authorizations[0]["event"]["details"].get(
                        "checkpoint_record_id"
                    ) != checkpoints[0]["record_id"]
                    or authorizations[0]["event"]["details"].get(
                        "target_binding"
                    ) != target
                    or authorizations[0]["event"]["details"].get("action")
                    != node["operation"]
                ):
                    raise AuthorityDeniedError(
                        "repository post-state requires prior runtime-issued mutation "
                        "authority for this checkpoint"
                    )
                source_ids = [pre["event"]["details"]["artifact_id"]]

            artifact = {
                "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
                "object_family": "artifact",
                "artifact_id": artifact_id,
                "role": "working",
                "status": "candidate",
                "media_type": "application/vnd.ora.repository-state+json",
                "locator": copy.deepcopy(locator),
                "identity": {
                    **copy.deepcopy(identity),
                    "fresh_until": fresh_until,
                },
                "lineage": {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(run["definition_ref"]),
                    "producing_node_id": run["current_node_id"],
                    "source_artifact_ids": source_ids,
                    "event_record_id": f"event-{uuid.uuid4().hex}",
                },
                "created_at": captured_at,
            }
            recorded = self.record_artifact(
                artifact,
                action="record_programming_mutation_receipt",
                selectors=["scope:declared_outputs"],
                satisfied_conditions=satisfied_conditions,
            )
            materialized = self.load_run(run_id)
            capture_record = self._append_event_locked(
                materialized,
                "repository_state_captured",
                {
                    "phase": phase,
                    "artifact_id": artifact_id,
                    "identity_digest": identity["digest"],
                    "target_binding": target,
                    "operation": node["operation"],
                    "approved_plan_digest": run["contracts"]["approved_plan"][
                        "digest"
                    ],
                },
                node_id=run["current_node_id"],
                artifact_ids=[artifact_id],
                runtime_authoritative=True,
            )
            return {**recorded, "capture_record": capture_record}

    def _issue_repository_mutation_receipt(
        self,
        run_id: str,
        artifact_id: str,
        *,
        pre_state_artifact_id: str,
        post_state_artifact_id: str,
        satisfied_conditions: Sequence[str],
    ) -> dict[str, Any]:
        """Issue the only receipt accepted for a delegated repository mutation."""

        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "issue repository mutation receipt")
            definition = self.load_definition(run_id)
            node = self._graph_nodes(definition)[run["current_node_id"]]
            if node["kind"] != "action" or not node["external_effect"]:
                raise AuthorityDeniedError(
                    "repository mutation receipt requires the current external-effect node"
                )
            records = self.load_records(run_id)
            context = self._delegated_mutation_authority_context(
                run, records, effect_recording=True
            )
            if context is None:
                raise AuthorityDeniedError(
                    "repository mutation receipt requires an approved delegation"
                )
            current_receipts = [
                record for record in context["current_records"]
                if (record.get("event") or {}).get("event_type")
                == "repository_mutation_receipt_issued"
            ]
            if current_receipts:
                raise RunConflictError(
                    "repository mutation receipt was already issued at this node"
                )
            pre_details = context["pre_capture"]["event"]["details"]
            post_details = context["post_capture"]["event"]["details"]
            if (
                pre_state_artifact_id != pre_details["artifact_id"]
                or post_state_artifact_id != post_details["artifact_id"]
            ):
                raise GovernedRuntimeError(
                    "repository receipt state IDs differ from authenticated captures"
                )
            payload = {
                "schema_version": "ora.repository-mutation-receipt/1.0",
                "operation": node["operation"],
                "approved_plan_digest": run["contracts"]["approved_plan"]["digest"],
                "target_binding": context["target_binding"],
                "checkpoint_record_id": context["checkpoint"]["record_id"],
                "pre_state_identity": {
                    "artifact_id": pre_details["artifact_id"],
                    "identity_digest": pre_details["identity_digest"],
                },
                "post_state_identity": {
                    "artifact_id": post_details["artifact_id"],
                    "identity_digest": post_details["identity_digest"],
                },
            }
            now = self._now()
            artifact = {
                "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
                "object_family": "artifact",
                "artifact_id": artifact_id,
                "role": "external_effect_receipt",
                "status": "verified",
                "media_type": "application/json",
                "locator": {
                    "kind": "inline",
                    "ref": f"inline:{run_id}:{artifact_id}",
                },
                "identity": {
                    "kind": "content_digest",
                    "digest": _digest_json(payload),
                    "coverage": [
                        "approved_target_locator", "pre_state", "post_state",
                        "checkpoint", "operation", "approved_plan",
                    ],
                    "captured_at": now,
                    "fresh_until": (
                        _parse_time(now) + timedelta(hours=1)
                    ).isoformat().replace("+00:00", "Z"),
                },
                "lineage": {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(run["definition_ref"]),
                    "producing_node_id": run["current_node_id"],
                    "source_artifact_ids": [
                        pre_details["artifact_id"], post_details["artifact_id"],
                    ],
                    "event_record_id": f"event-{uuid.uuid4().hex}",
                },
                "created_at": now,
            }
            recorded = self.record_artifact(
                artifact,
                action="record_programming_mutation_receipt",
                selectors=["scope:declared_outputs"],
                satisfied_conditions=satisfied_conditions,
            )
            materialized = self.load_run(run_id)
            issued = self._append_event_locked(
                materialized,
                "repository_mutation_receipt_issued",
                {
                    **payload,
                    "receipt_artifact_id": artifact_id,
                    "receipt_identity_digest": artifact["identity"]["digest"],
                },
                node_id=run["current_node_id"],
                artifact_ids=[artifact_id],
                runtime_authoritative=True,
            )
            return {**recorded, "receipt_record": issued, "payload": payload}

    def register_process_definition(
        self,
        run_id: str,
        registry: ProcessDefinitionRegistry,
        definition: Mapping[str, Any],
        *,
        definition_artifact_id: str,
        registration_artifact_id: str,
        selector: str,
        satisfied_conditions: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Register one constructed definition and issue an exact runtime receipt.

        This is the only runtime-authoritative registration bridge used by the
        Phase 2.7 construction-label gate.  It requires the Run to have just
        completed the declared construction operation, performs the immutable
        registry write itself, re-resolves the exact stored identity, records
        the registry receipt as a lineage-bound Artifact, and finally emits a
        reserved event that generic observation APIs cannot forge.
        """

        definition_copy = _contracts.validate_process_definition(definition)
        definition_ref = {
            "definition_id": definition_copy["definition_id"],
            "version": definition_copy["version"],
            "digest": definition_copy["digest"],
        }
        with _locked():
            run = self.load_run(run_id)
            self._require_mutable_run(run, "register a Process Definition")
            if run["state"] != "running":
                raise RunConflictError(
                    "Process Definition registration requires a running Process Run"
                )
            construction_definition = self.load_definition(run_id)
            nodes = self._graph_nodes(construction_definition)
            registration_node = nodes[run["current_node_id"]]
            if (
                registration_node["kind"] != "action"
                or registration_node["operation"]
                != "register_reusable_process_definition"
                or registration_node["external_effect"] is not False
            ):
                raise GovernedRuntimeError(
                    "Process Definition registration requires the exact governed "
                    "registration operation"
                )
            if selector not in registration_node["artifact_access"]:
                raise AuthorityDeniedError(
                    "definition registration selector is outside the exact graph node"
                )
            registration_grant_ids = self.authorize_action(
                run_id,
                "register_definition",
                [selector],
                satisfied_conditions=satisfied_conditions,
                effect_type="local_reversible",
                scope_kind="write",
            )
            if not set(registration_grant_ids).issubset(
                set(registration_node["authority_grant_ids"])
            ):
                raise AuthorityDeniedError(
                    "definition registration authority is outside the exact graph node"
                )
            target_contract = (
                (((construction_definition.get("input_schema") or {}).get(
                    "properties"
                ) or {}).get("target_definition_ref") or {}).get("const")
            )
            if target_contract != definition_ref:
                raise GovernedRuntimeError(
                    "construction Run target does not bind the exact definition identity"
                )

            definition_artifact = self.load_artifact(
                run_id, definition_artifact_id
            )
            expected_definition_digest = _digest_text(json.dumps(
                definition_copy, sort_keys=True, ensure_ascii=False
            ))
            construction_node_id = str(
                definition_artifact["lineage"]["producing_node_id"]
            )
            construction_node = nodes.get(construction_node_id)
            if (
                definition_artifact["role"] != "process_definition"
                or definition_artifact["identity"]["kind"] != "content_digest"
                or "complete_content"
                not in definition_artifact["identity"]["coverage"]
                or definition_artifact["identity"]["digest"]
                != expected_definition_digest
                or construction_node is None
                or construction_node["kind"] != "action"
                or construction_node["operation"]
                != "construct_reusable_process_definition"
                or construction_node["external_effect"] is not False
                or construction_node.get("next_node_id") != run["current_node_id"]
            ):
                raise GovernedRuntimeError(
                    "registration requires the exact complete Artifact produced by "
                    "the governed construction operation"
                )

            records = self.load_records(run_id)
            construction_completions = [
                record for record in records
                if (record.get("event") or {}).get("event_type")
                == "node_advanced"
                and record["node_id"] == construction_node_id
                and ((record.get("event") or {}).get("details") or {}).get(
                    "from_node_id"
                ) == construction_node_id
                and ((record.get("event") or {}).get("details") or {}).get(
                    "to_node_id"
                ) == run["current_node_id"]
                and ((record.get("event") or {}).get("details") or {}).get(
                    "advance_kind"
                ) == "action"
                and ((((record.get("event") or {}).get("details") or {}).get(
                    "route"
                ) or {}).get("operation"))
                == "construct_reusable_process_definition"
                and definition_artifact_id in record.get("artifact_ids", [])
            ]
            if len(construction_completions) != 1:
                raise GovernedRuntimeError(
                    "registration requires one runtime-authenticated construction "
                    "node completion"
                )
            if any(
                (record.get("event") or {}).get("event_type")
                == "process_definition_registered"
                for record in records
            ):
                raise RunConflictError(
                    "Process Run already contains a definition registration record"
                )
            if type(registry) is not ProcessDefinitionRegistry:
                raise GovernedRuntimeError(
                    "registration requires an exact Process Definition registry"
                )
            registry_root = registry.root.resolve()
            if (
                not registry_root.is_dir()
                or registry.root.is_symlink()
            ):
                raise GovernedRuntimeError(
                    "registration requires a real canonical registry root"
                )
            registry_root_digest = _digest_text(str(registry_root))

            try:
                receipt = copy.deepcopy(registry.register(definition_copy))
                resolved = registry.resolve(
                    definition_ref["definition_id"],
                    definition_ref["version"],
                    definition_ref["digest"],
                )
            except Exception as exc:
                raise GovernedRuntimeError(
                    f"Process Definition registry rejected the exact identity: {exc}"
                ) from exc
            receipt_fields = {
                "definition_ref", "registered_at", "registry_locator",
                "idempotent", "activated", "storage_content_digest",
                "receipt_digest",
            }
            receipt_body = {
                key: copy.deepcopy(value)
                for key, value in receipt.items()
                if key != "receipt_digest"
            }
            expected_locator = (
                "registry:process-definitions/"
                f"{definition_ref['definition_id']}@{definition_ref['version']}"
            )
            if (
                set(receipt) != receipt_fields
                or resolved != definition_copy
                or receipt.get("definition_ref") != definition_ref
                or receipt.get("registry_locator") != expected_locator
                or receipt.get("activated") is not False
                or not isinstance(receipt.get("idempotent"), bool)
                or receipt.get("storage_content_digest")
                != _digest_json(definition_copy)
                or receipt.get("receipt_digest") != _digest_json(receipt_body)
            ):
                raise GovernedRuntimeError(
                    "registry receipt does not authenticate the exact stored definition"
                )

            recorded = self.record_inline_artifact(
                run_id,
                registration_artifact_id,
                json.dumps(receipt, sort_keys=True, ensure_ascii=False),
                role="result",
                node_id=run["current_node_id"],
                action="register_definition",
                selector=selector,
                source_artifact_ids=[definition_artifact_id],
                satisfied_conditions=satisfied_conditions,
                media_type="application/vnd.ora.process-definition-registration+json",
            )
            registration_artifact = recorded["artifact"]
            artifact_record = recorded["record"]
            if artifact_record["event"]["details"].get(
                "grant_ids"
            ) != registration_grant_ids:
                raise GovernedRuntimeError(
                    "registration Artifact authority differs from its pre-write grant"
                )
            materialized = self.load_run(run_id)
            registration_record = self._append_event_locked(
                materialized,
                "process_definition_registered",
                {
                    "operation": "register_reusable_process_definition",
                    "construction_node_id": construction_node_id,
                    "construction_completion_record_id": construction_completions[
                        0
                    ]["record_id"],
                    "registration_node_id": run["current_node_id"],
                    "definition_ref": copy.deepcopy(definition_ref),
                    "definition_artifact_id": definition_artifact_id,
                    "definition_artifact_digest": definition_artifact[
                        "identity"
                    ]["digest"],
                    "registration_artifact_id": registration_artifact_id,
                    "registration_artifact_digest": registration_artifact[
                        "identity"
                    ]["digest"],
                    "registration_artifact_record_id": artifact_record[
                        "record_id"
                    ],
                    "registration_selector": selector,
                    "authority_grant_ids": registration_grant_ids,
                    "registration_receipt": copy.deepcopy(receipt),
                    "registry_locator": receipt["registry_locator"],
                    "registry_root_digest": registry_root_digest,
                    "registry_storage_content_digest": receipt[
                        "storage_content_digest"
                    ],
                    "registry_receipt_digest": receipt["receipt_digest"],
                },
                node_id=run["current_node_id"],
                artifact_ids=[definition_artifact_id, registration_artifact_id],
                runtime_authoritative=True,
            )
            return {
                **recorded,
                "registration": receipt,
                "registration_record": registration_record,
            }

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
            if prior is not None:
                stable_bindings = {
                    "role": (prior.get("role"), artifact_copy.get("role")),
                    "media_type": (
                        prior.get("media_type"), artifact_copy.get("media_type")
                    ),
                    "locator": (prior.get("locator"), artifact_copy.get("locator")),
                    "identity.kind": (
                        (prior.get("identity") or {}).get("kind"),
                        artifact_copy["identity"].get("kind"),
                    ),
                    "identity.coverage": (
                        (prior.get("identity") or {}).get("coverage"),
                        artifact_copy["identity"].get("coverage"),
                    ),
                }
                changed_bindings = sorted(
                    field
                    for field, (old, new) in stable_bindings.items()
                    if old != new
                )
                if changed_bindings:
                    raise GovernedRuntimeError(
                        "Artifact replacement cannot change its semantic identity "
                        "binding: " + ", ".join(changed_bindings)
                    )
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
        live_evidence = inspect_live_artifact_identity(
            evidence_artifact, captured_at=self._now()
        )
        if live_evidence["applicable"] and (
            not live_evidence["supported"]
            or not live_evidence["available"]
            or live_evidence["matches"] is not True
        ):
            raise FinalReviewRequired(
                "final-review evidence live identity is stale: "
                f"{artifact_id}/{evidence_id}: {live_evidence['reason']}"
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
        definition = self.load_definition(run_id)
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
        automation_contract = (
            (definition.get("output_schema") or {}).get("x-ora-process")
        )
        if (
            isinstance(automation_contract, Mapping)
            and automation_contract.get("schema_version")
            == "ora.process-automation/1.0"
        ):
            verification_records = []
            for record in self.load_records(run_id):
                event = record.get("event") or {}
                details = event.get("details") or {}
                if (
                    event.get("event_type")
                    == "isolated_process_verification_completed"
                    and details.get("result_artifact_id") == artifact_id
                    and details.get("evidence_artifact_id") == evidence_artifact_id
                ):
                    verification_records.append((record, details))
            if len(verification_records) != 1:
                raise FinalReviewRequired(
                    "automated Process review requires exactly one runtime-issued "
                    "isolated verification record"
                )
            verification_record, verification_details = verification_records[0]
            expected_verification = {
                "run_id": run_id,
                "definition_ref": run["definition_ref"],
                "node_id": run["current_node_id"],
                "attempt": run["contracts"]["correction_loop"]["attempt"],
                "result_artifact_id": artifact_id,
                "result_identity_digest": subject["identity"]["digest"],
                "evidence_artifact_id": evidence_artifact_id,
                "evidence_identity_digest": evidence_artifact["identity"]["digest"],
                "outcome": outcome,
                "execution_context_binding_digest": (
                    (run.get("input_bindings") or {})
                    .get("execution_context", {})
                    .get("binding_digest")
                ),
            }
            mismatches = [
                field for field, expected in expected_verification.items()
                if verification_details.get(field) != expected
            ]
            for field in ("worker_request_digest", "worker_response_digest"):
                try:
                    _exact_digest(verification_details.get(field), field)
                except GovernedRuntimeError:
                    mismatches.append(field)
            if verification_details.get("worker_boundary") not in {
                "separate_no_tools_process", "injected_test_worker",
            }:
                mismatches.append("worker_boundary")
            if set(verification_record["artifact_ids"]) != {
                artifact_id, evidence_artifact_id,
            }:
                mismatches.append("artifact_ids")
            declared_criteria = automation_contract.get("acceptance_criteria")
            declared_ids = (
                [criterion.get("criterion_id") for criterion in declared_criteria]
                if isinstance(declared_criteria, list)
                and all(isinstance(criterion, Mapping) for criterion in declared_criteria)
                else []
            )
            assessments = verification_details.get("criteria_assessments")
            if (
                not declared_ids
                or len(declared_ids) != len(set(declared_ids))
                or verification_details.get("declared_criteria_digest")
                != _digest_json(declared_criteria)
                or verification_details.get("declared_criterion_ids") != declared_ids
                or not isinstance(assessments, list)
                or len(assessments) != len(declared_ids)
                or verification_details.get("criteria_assessments_digest")
                != _digest_json(assessments)
            ):
                mismatches.append("criterion_assessment_set")
            else:
                for criterion, assessment in zip(declared_criteria, assessments):
                    criterion_id = criterion.get("criterion_id")
                    if (
                        not isinstance(assessment, Mapping)
                        or set(assessment) != {
                            "criterion_id", "kind", "satisfied", "reason",
                            "observation_digest",
                        }
                        or assessment.get("criterion_id") != criterion_id
                        or assessment.get("kind") != criterion.get("kind")
                        or not isinstance(assessment.get("satisfied"), bool)
                        or not isinstance(assessment.get("reason"), str)
                    ):
                        mismatches.append("criterion_assessment")
                        continue
                    try:
                        _exact_digest(
                            assessment.get("observation_digest"),
                            "criterion observation digest",
                        )
                    except GovernedRuntimeError:
                        mismatches.append("criterion_assessment")
                all_satisfied = all(
                    assessment.get("satisfied") is True
                    for assessment in assessments
                    if isinstance(assessment, Mapping)
                ) and len(assessments) == len(declared_ids)
                if (outcome == "PASS") != all_satisfied:
                    mismatches.append("criterion_outcome")
            start_id = verification_details.get("verification_start_record_id")
            start_records = [
                candidate for candidate in self.load_records(run_id)
                if candidate.get("record_id") == start_id
                and (candidate.get("event") or {}).get("event_type")
                == "isolated_process_verification_started"
            ]
            if len(start_records) != 1:
                mismatches.append("verification_start_record")
            else:
                start_record = start_records[0]
                start_details = (start_record.get("event") or {}).get("details") or {}
                for field in (
                    "run_id", "definition_ref", "node_id", "attempt",
                    "worker_request_digest", "execution_context_binding_digest",
                    "result_artifact_id", "result_identity_digest",
                    "declared_criteria_digest", "declared_criterion_ids",
                ):
                    if start_details.get(field) != verification_details.get(field):
                        mismatches.append("verification_start_binding")
                        break
                if (
                    int(start_record.get("sequence") or 0)
                    >= int(verification_record.get("sequence") or 0)
                    or start_record.get("artifact_ids") != [artifact_id]
                ):
                    mismatches.append("verification_start_order")
            if mismatches:
                raise FinalReviewRequired(
                    "isolated verification binding does not match the current result: "
                    + ", ".join(sorted(set(mismatches)))
                )
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
        repository_result_ids = [
            artifact_id
            for artifact_id in result_ids
            if (
                self.load_artifact(run_id, artifact_id)["identity"]["kind"]
                == "composite"
                and self.load_artifact(run_id, artifact_id)["locator"]["kind"]
                == "git_ref"
            )
        ]
        latest_attempt = None
        latest_attempt_record = None
        if repository_result_ids:
            for record in reversed(self.load_records(run_id)):
                event = record.get("event") or {}
                if event.get("event_type") == "attempt_completed":
                    latest_attempt = event.get("details") or {}
                    latest_attempt_record = record
                    break
            if latest_attempt is None:
                return (
                    False,
                    "repository result acceptance requires at least one successful "
                    "completed attempt",
                )
        if latest_attempt is not None:
            if latest_attempt.get("defect_codes"):
                return False, "the latest persisted attempt still reports defects"
            attempt_digests = set(latest_attempt.get("artifact_digests") or [])
            for artifact_id in repository_result_ids:
                result_digest = self.load_artifact(run_id, artifact_id)["identity"][
                    "digest"
                ]
                if result_digest not in attempt_digests:
                    return (
                        False,
                        "result Artifact identity is not bound to the latest "
                        f"successful attempt: {artifact_id}",
                    )
            attempt_evidence_refs = (latest_attempt_record or {}).get(
                "evidence_refs"
            ) or []
            for artifact_id in repository_result_ids:
                subject = self.load_artifact(run_id, artifact_id)
                passing_evidence_ids = set()
                for ref in attempt_evidence_refs:
                    if ref.get("outcome") != "PASS":
                        continue
                    try:
                        evidence_artifact = self.load_artifact(
                            run_id, str(ref.get("artifact_id") or "")
                        )
                        if (
                            evidence_artifact["role"] != "evidence"
                            or evidence_artifact["identity"]["digest"]
                            != ref.get("identity_digest")
                        ):
                            continue
                        self._assert_evidence_bound_to_subject(
                            run_id, evidence_artifact, subject
                        )
                    except GovernedRuntimeError:
                        continue
                    passing_evidence_ids.add(str(ref.get("evidence_id") or ""))
                missing_attempt_evidence = sorted(
                    set(requirements) - passing_evidence_ids
                )
                if missing_attempt_evidence:
                    return (
                        False,
                        "repository result acceptance requires current PASS attempt "
                        "evidence bound to the repository identity: "
                        + ", ".join(missing_attempt_evidence),
                    )
        for artifact_id in result_ids:
            artifact = self.load_artifact(run_id, artifact_id)
            if _parse_time(artifact["identity"]["fresh_until"]) < _parse_time(self._now()):
                return False, f"result Artifact identity is stale: {artifact_id}"
            live_identity = inspect_live_artifact_identity(
                artifact, captured_at=self._now()
            )
            if live_identity["applicable"] and (
                not live_identity["supported"]
                or not live_identity["available"]
                or live_identity["matches"] is not True
            ):
                return (
                    False,
                    "result Artifact live identity is stale: "
                    f"{artifact_id}: {live_identity['reason']}",
                )
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
    "lifecycle_disposition_idempotency_key",
]
