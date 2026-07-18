"""Phase 2.3 canonical Programming plan, review, approval, and vault export.

The service keeps one versioned plan family on the Dialogue-bound Process Run.
Principal and Technical views are deterministic projections of that canonical
body.  Planning may inspect and persist Run-local evidence, but target mutation
and Phase 2.4 delegation remain mechanically unavailable.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import process_contracts as _contracts
    import runtime_paths as _runtime_paths
    from conversation_memory import (
        ConversationPlanLifecycleError,
        load_governing_process_binding,
        load_process_plan_lifecycle,
        persist_process_plan_lifecycle,
    )
    from governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
    )
    from process_entry_routing import load_programming_definition
    from process_management_interview import (
        INTERVIEW_NODE_ID,
        INTERVIEW_SCHEMA_VERSION,
        ManagementInterviewService,
        _binding_digest,
        _definition_ref,
        _digest_json,
    )
except ImportError:  # pragma: no cover - package-qualified imports
    from orchestrator import process_contracts as _contracts
    from orchestrator import runtime_paths as _runtime_paths
    from orchestrator.conversation_memory import (
        ConversationPlanLifecycleError,
        load_governing_process_binding,
        load_process_plan_lifecycle,
        persist_process_plan_lifecycle,
    )
    from orchestrator.governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
    )
    from orchestrator.process_entry_routing import load_programming_definition
    from orchestrator.process_management_interview import (
        INTERVIEW_NODE_ID,
        INTERVIEW_SCHEMA_VERSION,
        ManagementInterviewService,
        _binding_digest,
        _definition_ref,
        _digest_json,
    )


PLAN_SCHEMA_VERSION = "ora.plan-execution-contract/1.0"
PLAN_STATE_SCHEMA_VERSION = "ora.programming-plan-state/1.0"
PLAN_OBSERVATION_PREFIX = "programming_plan_"
PLAN_NODES = (
    "entry-route",
    "intent-interview",
    "inspect-scope",
    "scope-review",
    "mode-after-scope",
    "plan",
    "plan-review",
    "plan-approval",
    "post-plan-mode",
    "blocked",
)
PLAN_ACTIONS = (
    "approve_and_start",
    "approve_without_start",
    "request_changes",
    "change_scope_or_permissions",
    "stop_and_retain",
)
_PLAN_LOCK = threading.RLock()

_BASIS_FIELDS = {
    "target_path",
    "non_solutions",
    "scope",
    "instructions",
    "architecture",
    "dependencies",
    "implementation_sequence",
    "expected_transitions",
    "tool_permissions",
    "tests",
    "risks",
    "recovery",
    "completion_criteria",
    "replanning_triggers",
    "loop_policy",
    "execution_handoff",
    "activation",
    "versioning",
}


class ProcessPlanError(RuntimeError):
    """Base class for invalid or refused Phase 2.3 operations."""


class ProcessPlanConflict(ProcessPlanError):
    """The requested plan action conflicts with persisted Run state."""


class ProcessPlanIntegrityError(ProcessPlanError):
    """A plan, projection, baseline, approval, or export identity drifted."""


class ProcessPlanInputRequired(ProcessPlanError):
    """Required planning input is absent or materially incomplete."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_idempotency(value: str, *, field: str) -> str:
    key = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", key):
        raise ProcessPlanError(f"{field} is invalid")
    return key


def _strings(value: Any, *, field: str, minimum: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise ProcessPlanInputRequired(f"{field} must be a list")
    clean = [" ".join(str(item or "").split()) for item in value]
    if len(clean) < minimum or any(not item for item in clean):
        raise ProcessPlanInputRequired(f"{field} requires material entries")
    return clean


def _validate_basis(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BASIS_FIELDS:
        missing = sorted(_BASIS_FIELDS - set(value or {})) if isinstance(value, Mapping) else []
        extra = sorted(set(value or {}) - _BASIS_FIELDS) if isinstance(value, Mapping) else []
        raise ProcessPlanInputRequired(
            f"planning basis fields do not match the contract; missing={missing}, extra={extra}"
        )
    basis = copy.deepcopy(dict(value))
    target_path = str(basis["target_path"] or "").strip()
    supplied_target = Path(target_path)
    if not target_path or not supplied_target.is_absolute():
        raise ProcessPlanInputRequired("target_path must be an exact absolute path")
    if supplied_target.is_symlink():
        raise ProcessPlanInputRequired("target_path cannot be a symlink")
    try:
        target_root = supplied_target.resolve(strict=True)
    except OSError as exc:
        raise ProcessPlanInputRequired("target_path is unavailable") from exc
    if not target_root.is_dir():
        raise ProcessPlanInputRequired("target_path must identify a directory")
    basis["target_path"] = str(target_root)
    for field in (
        "non_solutions", "scope", "architecture", "dependencies",
        "expected_transitions", "tool_permissions", "tests", "risks",
        "recovery", "completion_criteria", "replanning_triggers", "versioning",
    ):
        basis[field] = _strings(basis[field], field=field)
    instructions = basis["instructions"]
    if not isinstance(instructions, list) or not instructions:
        raise ProcessPlanInputRequired("instructions requires exact source records")
    clean_instructions = []
    for index, item in enumerate(instructions):
        if not isinstance(item, Mapping) or set(item) != {
            "source", "digest", "precedence", "scope",
        }:
            raise ProcessPlanInputRequired(f"instructions[{index}] is invalid")
        source = str(item["source"] or "").strip()
        digest = str(item["digest"] or "").strip()
        precedence = str(item["precedence"] or "").strip()
        scope = str(item["scope"] or "").strip()
        if (
            not source or not precedence or not scope
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        ):
            raise ProcessPlanInputRequired(f"instructions[{index}] lacks exact identity")
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = target_root / source_path
        if source_path.is_symlink() or not source_path.is_file():
            raise ProcessPlanInputRequired(
                f"instructions[{index}] source is not an exact regular file"
            )
        source_hash = hashlib.sha256()
        with source_path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                source_hash.update(block)
        actual_digest = "sha256:" + source_hash.hexdigest()
        if actual_digest != digest:
            raise ProcessPlanInputRequired(
                f"instructions[{index}] digest does not match its source"
            )
        clean_instructions.append({
            "source": str(source_path.resolve(strict=True)),
            "digest": digest,
            "precedence": precedence,
            "scope": scope,
        })
    basis["instructions"] = clean_instructions
    steps = basis["implementation_sequence"]
    if not isinstance(steps, list) or not steps:
        raise ProcessPlanInputRequired("implementation_sequence must be non-empty")
    clean_steps = []
    step_ids: set[str] = set()
    for index, item in enumerate(steps):
        if not isinstance(item, Mapping) or set(item) != {
            "step_id", "description", "depends_on", "artifacts", "action",
        }:
            raise ProcessPlanInputRequired(f"implementation_sequence[{index}] is invalid")
        step_id = str(item["step_id"] or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", step_id) or step_id in step_ids:
            raise ProcessPlanInputRequired("implementation step IDs must be unique identifiers")
        step_ids.add(step_id)
        clean_steps.append({
            "step_id": step_id,
            "description": " ".join(str(item["description"] or "").split()),
            "depends_on": _strings(item["depends_on"], field=f"{step_id}.depends_on", minimum=0),
            "artifacts": _strings(item["artifacts"], field=f"{step_id}.artifacts"),
            "action": str(item["action"] or "").strip(),
        })
        if not clean_steps[-1]["description"] or not clean_steps[-1]["action"]:
            raise ProcessPlanInputRequired(f"implementation_sequence[{index}] is incomplete")
    prior_step_ids: set[str] = set()
    for step in clean_steps:
        unknown = sorted(set(step["depends_on"]) - step_ids)
        forward = sorted(set(step["depends_on"]) - prior_step_ids)
        if unknown or forward or step["step_id"] in step["depends_on"]:
            raise ProcessPlanInputRequired(
                f"{step['step_id']} has an invalid or non-prior dependency: "
                f"{sorted(set(unknown + forward))}"
            )
        prior_step_ids.add(step["step_id"])
    basis["implementation_sequence"] = clean_steps
    loop = basis["loop_policy"]
    if not isinstance(loop, Mapping) or set(loop) != {
        "max_attempts", "repeated_defect_limit", "progress_required", "on_no_progress",
    }:
        raise ProcessPlanInputRequired("loop_policy is invalid")
    if (
        not isinstance(loop["max_attempts"], int) or loop["max_attempts"] < 1
        or not isinstance(loop["repeated_defect_limit"], int)
        or loop["repeated_defect_limit"] < 1
        or not isinstance(loop["progress_required"], bool)
        or loop["on_no_progress"] not in {"REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"}
    ):
        raise ProcessPlanInputRequired("loop_policy values are invalid")
    basis["loop_policy"] = dict(loop)
    handoff = basis["execution_handoff"]
    if not isinstance(handoff, Mapping) or set(handoff) != {
        "requested_actions", "artifact_selectors", "stop_conditions",
    }:
        raise ProcessPlanInputRequired("execution_handoff is invalid")
    basis["execution_handoff"] = {
        "requested_actions": _strings(handoff["requested_actions"], field="requested_actions"),
        "artifact_selectors": _strings(handoff["artifact_selectors"], field="artifact_selectors"),
        "stop_conditions": _strings(handoff["stop_conditions"], field="stop_conditions"),
    }
    activation = basis["activation"]
    if not isinstance(activation, Mapping) or set(activation) != {
        "requested", "mode", "separate_approval_required",
    }:
        raise ProcessPlanInputRequired("activation is invalid")
    if (
        not isinstance(activation["requested"], bool)
        or not isinstance(activation["separate_approval_required"], bool)
        or activation["separate_approval_required"] is not True
        or not str(activation["mode"] or "").strip()
    ):
        raise ProcessPlanInputRequired(
            "activation must retain a separate approval boundary"
        )
    basis["activation"] = {
        "requested": activation["requested"],
        "mode": str(activation["mode"]).strip(),
        "separate_approval_required": True,
    }
    return basis


def _file_identity(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    try:
        relative.encode("utf-8")
        path_identity = {"path": relative, "path_encoding": "utf-8"}
    except UnicodeEncodeError:
        path_identity = {
            "path": os.fsencode(relative).hex(),
            "path_encoding": "filesystem-bytes-hex",
        }
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(path)
        try:
            target.encode("utf-8")
            target_identity = {"target": target, "target_encoding": "utf-8"}
        except UnicodeEncodeError:
            target_identity = {
                "target": os.fsencode(target).hex(),
                "target_encoding": "filesystem-bytes-hex",
            }
        return {**path_identity, "kind": "symlink", **target_identity}
    if stat.S_ISREG(info.st_mode):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return {
            **path_identity,
            "kind": "file",
            "mode": stat.S_IMODE(info.st_mode),
            "size": info.st_size,
            "digest": "sha256:" + digest.hexdigest(),
        }
    if stat.S_ISDIR(info.st_mode):
        return {
            **path_identity,
            "kind": "directory",
            "mode": stat.S_IMODE(info.st_mode),
        }
    raise ProcessPlanIntegrityError(
        f"target identity does not support special filesystem entry: {relative}"
    )


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ProcessPlanIntegrityError(
            f"Git identity command failed: {' '.join(args)}: "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout.decode("utf-8", errors="surrogateescape")


def capture_target_identity(target_path: str, *, captured_at: str) -> dict[str, Any]:
    """Capture a content-bound local directory or exact Git/worktree identity."""

    supplied = Path(target_path)
    if not supplied.is_absolute() or supplied.is_symlink():
        raise ProcessPlanIntegrityError("target root must be absolute and not a symlink")
    try:
        root = supplied.resolve(strict=True)
    except OSError as exc:
        raise ProcessPlanIntegrityError("target root is unavailable") from exc
    if not root.is_dir():
        raise ProcessPlanIntegrityError("target root must be a directory")
    git_probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if git_probe.returncode == 0:
        git_root = Path(git_probe.stdout.decode().strip()).resolve()
        if git_root != root:
            raise ProcessPlanIntegrityError(
                "a target inside a Git worktree must name the exact repository root"
            )
        raw_paths = _git(root, "ls-files", "-co", "--exclude-standard", "-z")
        paths = sorted({item for item in raw_paths.split("\0") if item})
        if len(paths) > 50_000:
            raise ProcessPlanIntegrityError("target inventory exceeds the planning ceiling")
        files = []
        for relative in paths:
            candidate = root / relative
            if candidate.exists() or candidate.is_symlink():
                files.append(_file_identity(candidate, root))
        state = {
            "kind": "git_worktree_composite",
            "root": str(root),
            "head": _git(root, "rev-parse", "HEAD").strip(),
            "index_filesystem_bytes_hex": os.fsencode(
                _git(root, "ls-files", "--stage", "-z")
            ).hex(),
            "status_filesystem_bytes_hex": os.fsencode(
                _git(root, "status", "--porcelain=v2", "-z", "--untracked-files=all")
            ).hex(),
            "files": files,
            "state_exclusions": ["ignored files", "Git object database except current HEAD"],
        }
        locator_kind = "git_ref"
    else:
        paths = []
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            base = Path(directory)
            symlink_directories = [
                name for name in dirnames if (base / name).is_symlink()
            ]
            paths.extend(base / name for name in sorted(symlink_directories))
            if len(paths) > 50_000:
                raise ProcessPlanIntegrityError(
                    "target inventory exceeds the planning ceiling"
                )
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name != ".git" and name not in symlink_directories
            )
            paths.extend(base / name for name in dirnames)
            for name in sorted(filenames):
                paths.append(base / name)
                if len(paths) > 50_000:
                    raise ProcessPlanIntegrityError(
                        "target inventory exceeds the planning ceiling"
                    )
        state = {
            "kind": "directory_composite",
            "root": str(root),
            "files": [_file_identity(path, root) for path in paths],
            "state_exclusions": [".git directory"],
        }
        locator_kind = "file"
    return {
        "locator": {"kind": locator_kind, "ref": str(root)},
        "identity": {
            "kind": "composite",
            "digest": _digest_json(state),
            "coverage": [
                "exact_target_root", "tracked_state", "unstaged_state",
                "untracked_state", "declared_exclusions",
            ],
            "captured_at": captured_at,
        },
        "state": state,
    }


def _instruction_state_digests(
    instructions: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    expected = []
    current = []
    for instruction in instructions:
        source = str(instruction["source"])
        declared = str(instruction["digest"])
        expected.append({"source": source, "digest": declared})
        path = Path(source)
        actual = "unavailable"
        if not path.is_symlink() and path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            actual = "sha256:" + digest.hexdigest()
        current.append({"source": source, "digest": actual})
    return _digest_json(expected), _digest_json(current)


def _planning_contracts(
    *,
    run_id: str,
    principal_id: str,
    approved_at: str,
    entry_contract_digest: str,
) -> dict[str, Any]:
    plan_body = {
        "plan_id": f"planning-{run_id}",
        "version": "2.3",
        "objective": "Inspect scope and prepare one independently reviewed canonical plan.",
        "approved_by": principal_id,
        "approved_at": approved_at,
        "approved_node_ids": list(PLAN_NODES),
        "constraints": [
            "No target mutation, invocation, registration, publication, or activation.",
            "Principal and Technical projections derive from one canonical plan.",
            "Approval must bind the exact plan and current target baseline.",
            f"Bind exact Phase 2.1 entry contract {entry_contract_digest}.",
        ],
        "non_goals": [
            "Do not begin Phase 2.4 delegation or execution.",
            "Do not infer an effect grant from permission to inspect or plan.",
        ],
    }
    approved_plan = {**plan_body, "digest": _digest_json(plan_body)}
    return {
        "approved_plan": approved_plan,
        "authority": {
            "principal_id": principal_id,
            "grants": [
                {
                    "grant_id": "grant-dialogue",
                    "actions": ["elicit_programming_intent"],
                    "resource_selectors": ["scope:dialogue"],
                    "effect_types": ["dialogue_only", "local_reversible"],
                    "conditions": ["exact_dialogue_binding", "no_target_mutation"],
                },
                {
                    "grant_id": "grant-inspect",
                    "actions": ["inspect_programming_scope", "evaluate_scope"],
                    "resource_selectors": ["scope:declared_inputs"],
                    "effect_types": ["read_only", "local_reversible"],
                    "conditions": ["exact_target_identity", "no_target_mutation"],
                },
                {
                    "grant_id": "grant-plan",
                    "actions": [
                        "produce_programming_plan", "record_planning_evidence",
                        "evaluate_evidence",
                    ],
                    "resource_selectors": ["scope:plan_outputs"],
                    "effect_types": ["local_reversible"],
                    "conditions": ["exact_plan_identity", "no_target_mutation"],
                },
            ],
            "reserved_actions": [
                "activate", "construct_definition", "execute", "expand_scope",
                "invoke_process", "mutate", "publish", "register_definition",
                "remote_git", "send_external",
            ],
        },
        "artifact_scope": {
            "read_selectors": [
                "scope:dialogue", "scope:declared_inputs", "scope:plan_outputs",
            ],
            "write_selectors": [
                "scope:dialogue", "scope:declared_inputs", "scope:plan_outputs",
            ],
            "external_effect_selectors": [],
        },
        "bounded_judgment": [
            {
                "judgment_id": "management-interview-boundary",
                "node_id": "intent-interview",
                "verified_circumstances": ["The completed interview is exact and current."],
                "question": "Is management intent complete enough for scope inspection?",
                "permitted_conclusions": ["interview_complete", "required_input_unavailable"],
                "permitted_directives": ["ESCALATE", "BLOCKED"],
                "permitted_actions": ["elicit_programming_intent"],
                "authority_grant_ids": ["grant-dialogue"],
                "artifact_selectors": ["scope:dialogue"],
                "required_evidence_ids": ["ev-intent"],
                "evaluator_boundary": "management-interview-question-boundary",
                "stop_conditions": ["interview_incomplete", "dialogue_binding_invalid"],
                "return_node_id": "intent-interview",
                "escalation_request_types": ["management_input", "scope_clarification"],
            },
            {
                "judgment_id": "programming-scope-boundary",
                "node_id": "scope-review",
                "verified_circumstances": ["Target, policy, intent, and authority are exact."],
                "question": "Is scope exact enough to plan without guessing?",
                "permitted_conclusions": ["scope_supported", "scope_defect"],
                "permitted_directives": [
                    "PROCEED", "REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED",
                ],
                "permitted_actions": ["evaluate_scope"],
                "authority_grant_ids": ["grant-inspect"],
                "artifact_selectors": ["scope:declared_inputs"],
                "required_evidence_ids": ["ev-intent", "ev-identity", "ev-policy", "ev-authority"],
                "evaluator_boundary": "programming-scope-review",
                "stop_conditions": ["identity_ambiguous", "policy_conflict", "authority_missing"],
                "return_node_id": "inspect-scope",
                "escalation_request_types": ["scope_clarification", "programming_reserved_authority"],
            },
            {
                "judgment_id": "programming-plan-boundary",
                "node_id": "plan-review",
                "verified_circumstances": ["The plan and both projections share one identity."],
                "question": "Is the exact canonical plan safe and sufficient for approval?",
                "permitted_conclusions": ["plan_supported", "plan_defect", "projection_fork"],
                "permitted_directives": [
                    "PROCEED", "REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED",
                ],
                "permitted_actions": ["evaluate_evidence"],
                "authority_grant_ids": ["grant-plan"],
                "artifact_selectors": ["scope:plan_outputs"],
                "required_evidence_ids": [
                    "ev-plan", "ev-plan-projection-parity", "ev-review", "ev-authority",
                ],
                "evaluator_boundary": "programming-plan-review",
                "stop_conditions": ["plan_incomplete", "projection_fork", "baseline_stale"],
                "return_node_id": "plan",
                "escalation_request_types": ["plan_approval", "programming_reserved_authority"],
            },
        ],
        "evidence": {
            "requirements": [
                {
                    "evidence_id": "ev-intent", "claim": "Management intent is exact.",
                    "method": "principal_dialogue_answers", "producer_independence": "external",
                    "artifact_selectors": ["scope:dialogue"], "freshness_seconds": 0,
                    "required": True,
                },
                {
                    "evidence_id": "ev-identity", "claim": "Target baseline is content-bound.",
                    "method": "target_composite_identity", "producer_independence": "same_step",
                    "artifact_selectors": ["scope:declared_inputs"], "freshness_seconds": 86400,
                    "required": True,
                },
                {
                    "evidence_id": "ev-policy", "claim": "Applicable instructions are exact.",
                    "method": "instruction_identity_inventory", "producer_independence": "same_step",
                    "artifact_selectors": ["scope:declared_inputs"], "freshness_seconds": 86400,
                    "required": True,
                },
                {
                    "evidence_id": "ev-authority", "claim": "Planning remains within authority.",
                    "method": "authority_contract_validation", "producer_independence": "same_step",
                    "artifact_selectors": ["scope:declared_inputs"], "freshness_seconds": 86400,
                    "required": True,
                },
                {
                    "evidence_id": "ev-plan", "claim": "One exact canonical plan exists.",
                    "method": "canonical_plan_digest", "producer_independence": "same_step",
                    "artifact_selectors": ["scope:plan_outputs"], "freshness_seconds": 86400,
                    "required": True,
                },
                {
                    "evidence_id": "ev-plan-projection-parity",
                    "claim": "Both projections derive from the exact canonical plan.",
                    "method": "deterministic_projection_validation",
                    "producer_independence": "independent_step",
                    "artifact_selectors": ["scope:plan_outputs"], "freshness_seconds": 86400,
                    "required": True,
                },
                {
                    "evidence_id": "ev-review", "claim": "Independent plan review passes.",
                    "method": "independent_plan_contract_review",
                    "producer_independence": "independent_step",
                    "artifact_selectors": ["scope:plan_outputs"], "freshness_seconds": 86400,
                    "required": True,
                },
            ],
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "invalidate",
        },
        "correction_loop": {
            "max_attempts": 3,
            "attempt": 0,
            "progress_evidence_required": True,
            "repeated_defect_limit": 3,
            "allowed_directives": ["REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
            "no_progress_directives": ["REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
        },
        "continuation": {
            "checkpoint_id": "phase-2.3-planning",
            "resume_node_id": "plan-approval",
            "required_state_fields": ["current_node_id", "last_sequence", "artifact_ids"],
            "child_return_fields": [], "parent_run_id": None, "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "never_replay_effects",
            "checkpoint_ref": "checkpoint:phase-2.3-planning",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": ["ev-intent", "ev-identity", "ev-policy", "ev-authority"],
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": [
                "plan_approval_required", "principal_cancelled", "phase_boundary_reached",
            ],
            "blocked_conditions": ["identity_ambiguous", "policy_conflict", "baseline_stale"],
            "authority_request_types": [
                "management_input", "scope_clarification", "plan_approval",
                "programming_reserved_authority",
            ],
            "authority_return_target": principal_id,
        },
    }


def _approved_phase_contracts(
    *,
    current_contracts: Mapping[str, Any],
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the approved M1 while withholding every Phase 2.4 write seam."""

    principal_id = current_contracts["authority"]["principal_id"]
    contracts = copy.deepcopy(dict(current_contracts))
    entry_constraints = [
        constraint
        for constraint in current_contracts["approved_plan"]["constraints"]
        if str(constraint).startswith("Bind exact Phase 2.1 entry contract ")
    ]
    if len(entry_constraints) != 1:
        raise ProcessPlanIntegrityError(
            "approved plan cannot preserve the exact Phase 2.1 entry contract"
        )
    contracts["approved_plan"] = {
        "plan_id": plan["plan_id"],
        "version": plan["version"],
        "digest": plan["digest"],
        "objective": plan["objective"],
        "approved_by": approval["decision_by"],
        "approved_at": approval["decided_at"],
        "approved_node_ids": list(PLAN_NODES),
        "constraints": [
            "Execution remains unavailable until Phase 2.4 binds delegation.",
            (
                "Exact baseline " + approval["baseline_digest"]
                + " must be revalidated before action."
            ),
            "Activation remains a separate approval even when requested.",
            entry_constraints[0],
        ],
        "non_goals": copy.deepcopy(plan["non_solutions"]),
    }
    contracts["authority"] = {
        "principal_id": principal_id,
        "grants": [
            {
                "grant_id": "grant-approved-plan-inspection",
                "actions": ["inspect_approved_plan"],
                "resource_selectors": ["scope:approved_plan"],
                "effect_types": ["read_only"],
                "conditions": ["exact_plan_identity", "phase_2_4_withheld"],
            }
        ],
        "reserved_actions": sorted({
            "activate", "construct_definition", "elicit_programming_intent",
            "evaluate_evidence", "evaluate_scope", "execute", "expand_scope",
            "invoke_process", "mutate", "produce_programming_plan",
            "publish", "record_planning_evidence", "register_definition",
            "remote_git", "send_external",
        }),
    }
    contracts["artifact_scope"] = {
        "read_selectors": ["scope:approved_plan"],
        "write_selectors": [],
        "external_effect_selectors": [],
    }
    contracts["bounded_judgment"] = [
        {
            "judgment_id": "approved-plan-phase-boundary",
            "node_id": "post-plan-mode",
            "verified_circumstances": [
                "The exact approved plan is available for nonmutating inspection."
            ],
            "question": "Does work remain withheld pending Phase 2.4 delegation?",
            "permitted_conclusions": ["phase_boundary_preserved"],
            "permitted_directives": ["BLOCKED"],
            "permitted_actions": ["inspect_approved_plan"],
            "authority_grant_ids": ["grant-approved-plan-inspection"],
            "artifact_selectors": ["scope:approved_plan"],
            "required_evidence_ids": ["ev-approved-plan"],
            "evaluator_boundary": "approved-plan-phase-boundary",
            "stop_conditions": ["phase_2_4_not_authorized"],
            "return_node_id": "post-plan-mode",
            "escalation_request_types": ["programming_reserved_authority"],
        }
    ]
    contracts["evidence"] = {
        "requirements": [
            {
                "evidence_id": "ev-approved-plan",
                "claim": "The exact approved plan identity remains current.",
                "method": "approved_plan_digest_validation",
                "producer_independence": "independent_step",
                "artifact_selectors": ["scope:approved_plan"],
                "freshness_seconds": 0,
                "required": True,
            }
        ],
        "acceptance_rule": "all_required",
        "stale_evidence_policy": "invalidate",
    }
    contracts["continuation"] = {
        **copy.deepcopy(contracts["continuation"]),
        "checkpoint_id": "phase-2.3-approved",
        "resume_node_id": "post-plan-mode",
    }
    contracts["recovery"] = {
        **copy.deepcopy(contracts["recovery"]),
        "checkpoint_ref": "checkpoint:phase-2.3-approved",
        "revalidation_evidence_ids": ["ev-approved-plan"],
    }
    contracts["stop_escalation"] = {
        **copy.deepcopy(contracts["stop_escalation"]),
        "stop_conditions": [
            "phase_2_4_not_authorized", "principal_cancelled",
            "approved_baseline_stale",
        ],
        "blocked_conditions": [
            "phase_2_4_not_authorized", "approved_baseline_stale",
        ],
        "authority_request_types": ["programming_reserved_authority"],
    }
    return contracts


def _plan_ref(plan: Mapping[str, Any]) -> dict[str, str]:
    return {
        "plan_id": str(plan["plan_id"]),
        "version": str(plan["version"]),
        "digest": str(plan["digest"]),
    }


def _dialogue_lifecycle_binding(state: Mapping[str, Any]) -> dict[str, Any]:
    plan = state.get("current_plan")
    if not isinstance(plan, Mapping):
        raise ProcessPlanIntegrityError(
            "Dialogue lifecycle requires an exact current plan"
        )
    approved = state.get("status") == "approved"
    approval = copy.deepcopy(state.get("approval")) if approved else None
    if approved and not isinstance(approval, dict):
        raise ProcessPlanIntegrityError(
            "approved Dialogue lifecycle requires an approval receipt"
        )
    body = {
        "schema_version": "ora.dialogue-plan-lifecycle/1.0",
        "lifecycle": "plan:approved" if approved else "plan:in-planning",
        "run_id": state["run_id"],
        "binding_digest": state["binding_digest"],
        "plan_ref": _plan_ref(plan),
        "approval_receipt": approval,
        "approval_receipt_digest": _digest_json(approval) if approval else None,
    }
    return {**body, "lifecycle_digest": _digest_json(body)}


def _principal_projection(plan: Mapping[str, Any]) -> dict[str, Any]:
    content = {
        "outcome": plan["objective"],
        "users": plan["management"]["affected_parties"],
        "scope": plan["repository_artifact_scope"],
        "authority": plan["authority"],
        "risks": plan["risk_controls"],
        "exceptions": plan["management"]["exceptions"],
        "proof": plan["completion_criteria"],
        "activation": plan["activation"],
    }
    projection = {"plan_ref": _plan_ref(plan), "content": content}
    projection["projection_digest"] = _digest_json(projection)
    return projection


def _technical_projection(plan: Mapping[str, Any]) -> dict[str, Any]:
    content = {
        "artifacts": plan["repository_artifact_scope"],
        "architecture": plan["architecture"],
        "dependencies": plan["dependencies"],
        "implementation_sequence": plan["ordered_changes"],
        "tests": plan["test_inspection_plan"],
        "evidence": plan["completion_criteria"],
        "versioning": plan["versioning"],
        "recovery": plan["recovery_strategy"],
    }
    projection = {"plan_ref": _plan_ref(plan), "content": content}
    projection["projection_digest"] = _digest_json(projection)
    return projection


def _project_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    principal = _principal_projection(plan)
    technical = _technical_projection(plan)
    parity = _digest_json({
        "plan_ref": _plan_ref(plan),
        "principal_projection_digest": principal["projection_digest"],
        "technical_projection_digest": technical["projection_digest"],
    })
    return {
        "principal_view": principal,
        "technical_view": technical,
        "projection_parity_digest": parity,
    }


def _build_plan(
    *,
    run: Mapping[str, Any],
    dialogue_ref: str,
    interview_state: Mapping[str, Any],
    basis: Mapping[str, Any],
    baseline: Mapping[str, Any],
    version: int,
    planner_id: str,
) -> dict[str, Any]:
    answers = interview_state["answers"]
    required = {
        "intended_result", "affected_parties", "inputs_outputs", "reuse",
        "initiation", "authority", "exceptions", "permissions", "evidence", "stopping",
    }
    if set(answers) != required or interview_state["status"] != "ready_for_plan":
        raise ProcessPlanInputRequired("the management interview is not complete")
    body = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": f"plan:{run['run_id']}",
        "version": f"{version}.0",
        "run_id": run["run_id"],
        "definition_ref": copy.deepcopy(run["definition_ref"]),
        "dialogue_ref": dialogue_ref,
        "project_ref": run["input_bindings"]["project_ref"],
        "planner_id": planner_id,
        "objective": answers["intended_result"]["answer"],
        "non_solutions": copy.deepcopy(basis["non_solutions"]),
        "management_answers_digest": interview_state["answers_digest"],
        "management": {
            dimension: answers[dimension]["answer"]
            for dimension in answers
        },
        "repository_artifact_scope": {
            "declared_scope": copy.deepcopy(basis["scope"]),
            "target": copy.deepcopy(baseline),
        },
        "applicable_instructions": copy.deepcopy(basis["instructions"]),
        "ordered_changes": copy.deepcopy(basis["implementation_sequence"]),
        "expected_artifact_state_transitions": copy.deepcopy(basis["expected_transitions"]),
        "tool_permission_requirements": copy.deepcopy(basis["tool_permissions"]),
        "test_inspection_plan": copy.deepcopy(basis["tests"]),
        "risk_controls": copy.deepcopy(basis["risks"]),
        "recovery_strategy": copy.deepcopy(basis["recovery"]),
        "completion_criteria": copy.deepcopy(basis["completion_criteria"]),
        "replanning_triggers": copy.deepcopy(basis["replanning_triggers"]),
        "loop_policy": copy.deepcopy(basis["loop_policy"]),
        "execution_handoff": copy.deepcopy(basis["execution_handoff"]),
        "authority": {
            "management_boundary": answers["authority"]["answer"],
            "permissions": answers["permissions"]["answer"],
            "requested_actions": copy.deepcopy(
                basis["execution_handoff"]["requested_actions"]
            ),
            "reserved_until_phase_2_4": True,
        },
        "architecture": copy.deepcopy(basis["architecture"]),
        "dependencies": copy.deepcopy(basis["dependencies"]),
        "versioning": copy.deepcopy(basis["versioning"]),
        "activation": copy.deepcopy(basis["activation"]),
    }
    plan = {**body, "digest": _digest_json(body)}
    projections = _project_plan(plan)
    return {**plan, **projections}


def _plan_request_digest(plan: Mapping[str, Any]) -> str:
    planning_basis = {
        "target_path": plan["repository_artifact_scope"]["target"]["locator"]["ref"],
        "non_solutions": plan["non_solutions"],
        "scope": plan["repository_artifact_scope"]["declared_scope"],
        "instructions": plan["applicable_instructions"],
        "architecture": plan["architecture"],
        "dependencies": plan["dependencies"],
        "implementation_sequence": plan["ordered_changes"],
        "expected_transitions": plan["expected_artifact_state_transitions"],
        "tool_permissions": plan["tool_permission_requirements"],
        "tests": plan["test_inspection_plan"],
        "risks": plan["risk_controls"],
        "recovery": plan["recovery_strategy"],
        "completion_criteria": plan["completion_criteria"],
        "replanning_triggers": plan["replanning_triggers"],
        "loop_policy": plan["loop_policy"],
        "execution_handoff": plan["execution_handoff"],
        "activation": plan["activation"],
        "versioning": plan["versioning"],
    }
    return _digest_json({
        "planner_id": plan["planner_id"],
        "planning_basis": planning_basis,
    })


def _validate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(plan))
    required = {
        "schema_version", "plan_id", "version", "run_id", "definition_ref",
        "dialogue_ref", "project_ref", "planner_id", "objective", "non_solutions",
        "management_answers_digest", "management", "repository_artifact_scope",
        "applicable_instructions", "ordered_changes", "expected_artifact_state_transitions",
        "tool_permission_requirements", "test_inspection_plan", "risk_controls",
        "recovery_strategy", "completion_criteria", "replanning_triggers", "loop_policy",
        "execution_handoff", "authority", "architecture", "dependencies", "versioning",
        "activation", "digest", "principal_view", "technical_view",
        "projection_parity_digest",
    }
    if set(candidate) != required or candidate.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ProcessPlanIntegrityError("canonical plan fields do not match the schema")
    body = {
        key: value for key, value in candidate.items()
        if key not in {"digest", "principal_view", "technical_view", "projection_parity_digest"}
    }
    if candidate["digest"] != _digest_json(body):
        raise ProcessPlanIntegrityError("canonical plan digest does not match its body")
    expected = _project_plan(candidate)
    for field in ("principal_view", "technical_view", "projection_parity_digest"):
        if candidate[field] != expected[field]:
            raise ProcessPlanIntegrityError("plan projection parity is invalid")
    return candidate


class ProcessPlanApprovalService:
    """Own one Dialogue-bound canonical plan family and approval checkpoint."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        sessions_root: str | Path | None = None,
        repository_root: str | Path | None = None,
        vault_root: str | Path | None = None,
        project_folder_resolver: Callable[[str], str | Path] | None = None,
        now: Callable[[], str] | None = None,
    ):
        self.runtime = runtime or GovernedProcessRuntime()
        self.sessions_root = Path(sessions_root) if sessions_root is not None else None
        self.repository_root = Path(repository_root) if repository_root is not None else None
        self.vault_root = Path(vault_root) if vault_root is not None else Path(
            _runtime_paths.vault_dir()
        )
        self.project_folder_resolver = project_folder_resolver
        self._now = now or _utc_now

    def _context(self, dialogue_ref: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
        binding = load_governing_process_binding(
            dialogue_ref, sessions_root=self.sessions_root
        )
        if binding is None:
            return None
        run = self.runtime.load_run(binding["run_id"])
        definition = self.runtime.load_definition(run["run_id"])
        authoritative = load_programming_definition(self.repository_root)
        expected_ref = _definition_ref(authoritative)
        if (
            definition != authoritative
            or run["definition_ref"] != expected_ref
            or binding["definition_ref"] != expected_ref
            or binding["binding_digest"]
            != _binding_digest(dialogue_ref, run["run_id"], expected_ref)
            or run["input_bindings"].get("dialogue_ref") != dialogue_ref
        ):
            raise ProcessPlanIntegrityError(
                "plan context does not match the exact Dialogue, Run, and definition"
            )
        return binding, run, definition

    def _interview_state(
        self,
        dialogue_ref: str,
        binding: Mapping[str, Any],
        run: Mapping[str, Any],
    ) -> dict[str, Any]:
        service = ManagementInterviewService(
            runtime=self.runtime,
            sessions_root=self.sessions_root,
            repository_root=self.repository_root,
            now=self._now,
        )
        state = service._fold_state(dialogue_ref, binding, run)
        if state["status"] != "ready_for_plan":
            raise ProcessPlanInputRequired("management interview is not ready for planning")
        return state

    def _observations(
        self, dialogue_ref: str, binding_digest: str, run_id: str,
    ) -> list[dict[str, Any]]:
        records = []
        for record in self.runtime.load_records(run_id):
            event = record.get("event") or {}
            details = event.get("details") or {}
            kind = str(details.get("observation_type") or "")
            if event.get("event_type") != "dialogue_observation_recorded" or not kind.startswith(
                PLAN_OBSERVATION_PREFIX
            ):
                continue
            payload = details.get("payload")
            if (
                details.get("dialogue_ref") != dialogue_ref
                or details.get("binding_digest") != binding_digest
                or not isinstance(payload, dict)
                or details.get("payload_digest") != _digest_json(payload)
            ):
                raise ProcessPlanIntegrityError("plan observation identity is invalid")
            records.append({
                "record_id": record["record_id"],
                "recorded_at": record["recorded_at"],
                "kind": kind,
                "payload": copy.deepcopy(payload),
            })
        return records

    def get_state(self, dialogue_ref: str) -> dict[str, Any] | None:
        with _PLAN_LOCK:
            context = self._context(dialogue_ref)
            if context is None:
                return None
            binding, run, _definition = context
            observations = self._observations(
                dialogue_ref, binding["binding_digest"], run["run_id"]
            )
            if not observations and "phase-2.3" not in run.get("labels", []):
                return None
            plans: list[dict[str, Any]] = []
            reviews: dict[str, dict[str, Any]] = {}
            revision_requests: list[dict[str, Any]] = []
            stale_records: list[dict[str, Any]] = []
            approvals: dict[str, dict[str, Any]] = {}
            exports: dict[str, dict[str, Any]] = {}
            retained = None
            proposal_keys: dict[str, dict[str, Any]] = {}
            approval_keys: dict[str, dict[str, Any]] = {}
            lifecycle_receipts: list[dict[str, Any]] = []
            for item in observations:
                kind = item["kind"]
                payload = item["payload"]
                if kind == "programming_plan_proposed":
                    if set(payload) != {
                        "schema_version", "idempotency_key", "request_digest",
                        "plan", "plan_ref",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("plan proposal observation is invalid")
                    plan = _validate_plan(payload["plan"])
                    if payload["plan_ref"] != _plan_ref(plan):
                        raise ProcessPlanIntegrityError("plan proposal reference drifted")
                    if payload["request_digest"] != _plan_request_digest(plan):
                        raise ProcessPlanIntegrityError(
                            "plan proposal request identity drifted"
                        )
                    key = str(payload["idempotency_key"] or "")
                    _stable_idempotency(key, field="proposal idempotency_key")
                    if key in proposal_keys or any(
                        existing["plan_id"] == plan["plan_id"]
                        and existing["version"] == plan["version"]
                        for existing in plans
                    ):
                        raise ProcessPlanIntegrityError("plan proposal identity is duplicated")
                    if plans and plan["plan_id"] != plans[0]["plan_id"]:
                        raise ProcessPlanIntegrityError("one Run cannot fork plan families")
                    if plan["version"] != f"{len(plans) + 1}.0":
                        raise ProcessPlanIntegrityError("plan versions must advance monotonically")
                    plans.append(plan)
                    proposal_keys[key] = {
                        "plan_ref": _plan_ref(plan),
                        "request_digest": payload["request_digest"],
                    }
                elif kind == "programming_plan_reviewed":
                    if set(payload) != {
                        "schema_version", "plan_ref", "outcome", "reviewer_id",
                        "independent", "projection_parity_digest",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("plan review observation is invalid")
                    ref_key = _digest_json(payload["plan_ref"])
                    matching = [plan for plan in plans if _plan_ref(plan) == payload["plan_ref"]]
                    if (
                        len(matching) != 1 or ref_key in reviews
                        or payload.get("outcome") != "PASS"
                        or payload.get("independent") is not True
                        or payload.get("reviewer_id") in {
                            run["contracts"]["authority"]["principal_id"],
                            matching[0]["planner_id"],
                        }
                        or payload.get("projection_parity_digest")
                        != matching[0]["projection_parity_digest"]
                    ):
                        raise ProcessPlanIntegrityError("plan review is not independently bound")
                    reviews[ref_key] = copy.deepcopy(payload)
                elif kind in {
                    "programming_plan_revision_requested",
                    "programming_plan_scope_change_requested",
                }:
                    if set(payload) != {
                        "schema_version", "plan_ref", "idempotency_key", "action",
                        "reason",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("plan revision request is invalid")
                    if not plans or payload["plan_ref"] != _plan_ref(plans[-1]):
                        raise ProcessPlanIntegrityError("revision request does not bind current plan")
                    expected_action = (
                        "request_changes"
                        if kind == "programming_plan_revision_requested"
                        else "change_scope_or_permissions"
                    )
                    if payload.get("action") != expected_action:
                        raise ProcessPlanIntegrityError("revision request action is invalid")
                    revision_requests.append(copy.deepcopy(payload))
                elif kind == "programming_plan_stale":
                    if set(payload) != {
                        "schema_version", "plan_ref", "stale_kind",
                        "expected_identity_digest", "current_identity_digest",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("stale-plan observation is invalid")
                    if payload.get("stale_kind") not in {"target", "instructions"}:
                        raise ProcessPlanIntegrityError("stale-plan kind is invalid")
                    stale_records.append(copy.deepcopy(payload))
                elif kind == "programming_plan_approval_decided":
                    if set(payload) != {
                        "schema_version", "plan_ref", "baseline_digest", "decision",
                        "decision_by", "decided_at", "idempotency_key",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("plan approval observation is invalid")
                    if not plans or payload["plan_ref"] != _plan_ref(plans[-1]):
                        raise ProcessPlanIntegrityError("approval does not bind current plan")
                    ref_key = _digest_json(payload["plan_ref"])
                    if (
                        ref_key in approvals
                        or ref_key not in reviews
                        or payload.get("baseline_digest")
                        != plans[-1]["repository_artifact_scope"]["target"]
                        ["identity"]["digest"]
                        or payload.get("decision_by")
                        != run["contracts"]["authority"]["principal_id"]
                        or not re.fullmatch(
                            r"\d{4}-\d{2}-\d{2}T[^\s]+Z",
                            str(payload.get("decided_at") or ""),
                        )
                    ):
                        raise ProcessPlanIntegrityError(
                            "plan approval authority or exact identity is invalid"
                        )
                    if payload["decision"] not in {"approve_and_start", "approve_without_start"}:
                        raise ProcessPlanIntegrityError("plan approval decision is invalid")
                    key = str(payload["idempotency_key"] or "")
                    _stable_idempotency(key, field="approval idempotency_key")
                    if key in approval_keys:
                        raise ProcessPlanIntegrityError("approval idempotency identity is duplicated")
                    approval_keys[key] = copy.deepcopy(payload)
                    approvals[ref_key] = copy.deepcopy(payload)
                elif kind == "programming_plan_exported":
                    if set(payload) != {
                        "schema_version", "plan_ref", "path", "content_digest",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("plan export observation is invalid")
                    ref_key = _digest_json(payload["plan_ref"])
                    if ref_key in exports or ref_key not in approvals:
                        raise ProcessPlanIntegrityError("plan export lacks exact approval")
                    exports[ref_key] = copy.deepcopy(payload)
                elif kind == "programming_plan_retained":
                    if retained is not None or set(payload) != {
                        "schema_version", "plan_ref", "decision_by", "reason",
                        "idempotency_key",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError("retained plan observation is invalid")
                    if not plans or payload["plan_ref"] != _plan_ref(plans[-1]):
                        raise ProcessPlanIntegrityError("retention does not bind current plan")
                    if (
                        _digest_json(payload["plan_ref"]) not in reviews
                        or payload.get("decision_by")
                        != run["contracts"]["authority"]["principal_id"]
                        or not str(payload.get("reason") or "").strip()
                    ):
                        raise ProcessPlanIntegrityError("retained plan authority is invalid")
                    _stable_idempotency(
                        str(payload["idempotency_key"] or ""),
                        field="retention idempotency_key",
                    )
                    retained = copy.deepcopy(payload)
                elif kind == "programming_plan_dialogue_lifecycle_persisted":
                    if set(payload) != {
                        "schema_version", "lifecycle", "plan_ref",
                        "approval_receipt_digest", "lifecycle_digest",
                    } or payload.get("schema_version") != PLAN_STATE_SCHEMA_VERSION:
                        raise ProcessPlanIntegrityError(
                            "Dialogue lifecycle receipt is invalid"
                        )
                    matching = [
                        plan for plan in plans if _plan_ref(plan) == payload["plan_ref"]
                    ]
                    if (
                        len(matching) != 1
                        or payload.get("lifecycle")
                        not in {"plan:in-planning", "plan:approved"}
                        or not re.fullmatch(
                            r"sha256:[0-9a-f]{64}",
                            str(payload.get("lifecycle_digest") or ""),
                        )
                        or any(
                            item["lifecycle_digest"] == payload["lifecycle_digest"]
                            for item in lifecycle_receipts
                        )
                    ):
                        raise ProcessPlanIntegrityError(
                            "Dialogue lifecycle receipt identity is invalid"
                        )
                    ref_key = _digest_json(payload["plan_ref"])
                    if payload["lifecycle"] == "plan:approved":
                        exact_approval = approvals.get(ref_key)
                        if (
                            exact_approval is None
                            or payload.get("approval_receipt_digest")
                            != _digest_json(exact_approval)
                        ):
                            raise ProcessPlanIntegrityError(
                                "approved Dialogue lifecycle lacks its exact receipt"
                            )
                    elif payload.get("approval_receipt_digest") is not None:
                        raise ProcessPlanIntegrityError(
                            "in-planning Dialogue lifecycle claims approval"
                        )
                    lifecycle_receipts.append(copy.deepcopy(payload))
                else:
                    raise ProcessPlanIntegrityError(f"unknown plan observation: {kind}")
            current = plans[-1] if plans else None
            current_ref_key = _digest_json(_plan_ref(current)) if current else None
            current_review = reviews.get(current_ref_key) if current_ref_key else None
            approval = approvals.get(current_ref_key) if current_ref_key else None
            export = exports.get(current_ref_key) if current_ref_key else None
            for plan in plans:
                ref_key = _digest_json(_plan_ref(plan))
                if ref_key not in reviews:
                    continue
                plan_text = json.dumps(plan, sort_keys=True, ensure_ascii=False)
                artifact_id = f"art-plan-v{plan['version'].replace('.', '-')}"
                try:
                    artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
                except GovernedRuntimeError as exc:
                    raise ProcessPlanIntegrityError(
                        "reviewed plan Artifact is unavailable"
                    ) from exc
                if artifact["identity"]["digest"] != _digest_text(plan_text):
                    raise ProcessPlanIntegrityError(
                        "reviewed plan Artifact does not match the canonical plan"
                    )
            plans_by_ref = {
                _digest_json(_plan_ref(plan)): plan for plan in plans
            }
            for ref_key, recorded_export in exports.items():
                exported_plan = plans_by_ref.get(ref_key)
                exported_approval = approvals.get(ref_key)
                if exported_plan is None or exported_approval is None:
                    raise ProcessPlanIntegrityError(
                        "approved plan export has no canonical plan and approval"
                    )
                export_path = Path(str(recorded_export["path"] or ""))
                try:
                    resolved_root = self.vault_root.resolve(strict=True)
                    resolved_export = export_path.resolve(strict=True)
                    resolved_export.relative_to(resolved_root)
                except (OSError, ValueError) as exc:
                    raise ProcessPlanIntegrityError(
                        "approved plan export is unavailable or outside the vault"
                    ) from exc
                expected_content = self._render_export(
                    exported_plan, exported_approval
                )
                if (
                    export_path.is_symlink()
                    or not resolved_export.is_file()
                    or recorded_export["content_digest"]
                    != _digest_text(expected_content)
                    or _digest_text(resolved_export.read_text(encoding="utf-8"))
                    != recorded_export["content_digest"]
                ):
                    raise ProcessPlanIntegrityError(
                        "approved plan export no longer matches its exact receipt"
                    )
            status = "planning"
            tags = ["plan:in-planning"]
            if current is not None and current_review is not None:
                status = "awaiting_approval"
            if revision_requests and current is not None:
                latest_request = revision_requests[-1]
                if latest_request["plan_ref"] == _plan_ref(current):
                    status = "revision_requested"
            relevant_stale = (
                stale_records
                and current is not None
                and stale_records[-1]["plan_ref"] == _plan_ref(current)
            )
            if retained is not None:
                status = "retained"
            if approval is not None:
                status = "approval_pending_commit"
            phase_2_4_active = (
                "phase-2.4" in run.get("labels", [])
                and "delegated" in run.get("labels", [])
            )
            phase_2_4_positioned = (
                phase_2_4_active
                and run["current_node_id"] != "post-plan-mode"
                and str(
                    run["contracts"]["continuation"].get("checkpoint_id") or ""
                ).startswith("delegation-")
            )
            if (
                approval is not None
                and export is not None
                and current is not None
                and (
                    run["current_node_id"] == "post-plan-mode"
                    or phase_2_4_active
                )
                and run["contracts"]["approved_plan"]["digest"] == current["digest"]
            ):
                status = "approved"
                tags = ["plan:approved"]
            if relevant_stale:
                status = "stale"
                tags = ["plan:in-planning"]
            result = {
                "schema_version": PLAN_STATE_SCHEMA_VERSION,
                "dialogue_ref": dialogue_ref,
                "run_id": run["run_id"],
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "binding_digest": binding["binding_digest"],
                "status": status,
                "plan_tags": tags,
                "current_plan": copy.deepcopy(current),
                "plan_versions": [_plan_ref(plan) for plan in plans],
                "current_review": copy.deepcopy(current_review),
                "revision_requests": revision_requests,
                "stale_records": stale_records,
                "approval": approval,
                "export": export,
                "retained": retained,
                "proposal_idempotency": proposal_keys,
                "approval_idempotency": approval_keys,
                "dialogue_lifecycle_receipts": lifecycle_receipts,
                "run_state": run["state"],
                "current_node_id": run["current_node_id"],
                "next_action": {
                    "planning": "submit_canonical_plan",
                    "awaiting_approval": "principal_plan_decision",
                    "revision_requested": "submit_revised_plan",
                    "stale": "submit_revised_plan",
                    "approval_pending_commit": "finish_approval_commit",
                    "approved": (
                        "review_completed_result"
                        if run["state"] == "completed"
                        else (
                            "resolve_blocked_run"
                            if run["state"] == "blocked"
                            else (
                                "delegated_execution_active"
                                if phase_2_4_positioned
                                else (
                                    "finish_phase_2_4_activation"
                                    if phase_2_4_active
                                    else "await_phase_2_4_delegation"
                                )
                            )
                        )
                    ),
                    "retained": "no_execution",
                }[status],
                "phase_2_4_authorized": phase_2_4_active,
                "target_mutation_authorized": (
                    phase_2_4_positioned
                    and run["state"] not in {"completed", "blocked"}
                    and any(
                        "execute_approved_programming_step" in grant["actions"]
                        for grant in run["contracts"]["authority"]["grants"]
                    )
                ),
            }
            try:
                persisted_lifecycle = load_process_plan_lifecycle(
                    dialogue_ref, sessions_root=self.sessions_root
                )
            except ConversationPlanLifecycleError as exc:
                raise ProcessPlanIntegrityError(
                    "persisted Dialogue plan lifecycle is invalid"
                ) from exc
            if lifecycle_receipts and persisted_lifecycle is None:
                raise ProcessPlanIntegrityError(
                    "authoritative Dialogue lifecycle receipt has no envelope binding"
                )
            if persisted_lifecycle is not None:
                if (
                    persisted_lifecycle["run_id"] != result["run_id"]
                    or persisted_lifecycle["binding_digest"]
                    != result["binding_digest"]
                    or not any(
                        persisted_lifecycle["plan_ref"] == _plan_ref(plan)
                        for plan in plans
                    )
                ):
                    raise ProcessPlanIntegrityError(
                        "Dialogue lifecycle does not bind this plan family"
                    )
                persisted_ref_key = _digest_json(
                    persisted_lifecycle["plan_ref"]
                )
                if persisted_lifecycle["lifecycle"] == "plan:approved":
                    exact_approval = approvals.get(persisted_ref_key)
                    if (
                        exact_approval is None
                        or persisted_lifecycle["approval_receipt"]
                        != exact_approval
                    ):
                        raise ProcessPlanIntegrityError(
                            "Dialogue approved lifecycle receipt drifted"
                        )
                latest_receipt_digest = (
                    lifecycle_receipts[-1]["lifecycle_digest"]
                    if lifecycle_receipts else None
                )
                expected_current = _dialogue_lifecycle_binding(result)
                if (
                    persisted_lifecycle["lifecycle_digest"]
                    != latest_receipt_digest
                    and persisted_lifecycle != expected_current
                ):
                    raise ProcessPlanIntegrityError(
                        "Dialogue lifecycle is neither receipted nor current"
                    )
            result["dialogue_lifecycle"] = copy.deepcopy(persisted_lifecycle)
            return result

    def _record(self, dialogue_ref: str, state: Mapping[str, Any], kind: str, payload: Mapping[str, Any]) -> None:
        self.runtime._record_dialogue_observation(
            state["run_id"],
            dialogue_ref=dialogue_ref,
            binding_digest=state["binding_digest"],
            observation_type=kind,
            payload=payload,
        )

    def _persist_dialogue_lifecycle(
        self,
        dialogue_ref: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist and receipt lifecycle without repurposing privacy tags."""

        lifecycle = _dialogue_lifecycle_binding(state)
        try:
            persist_process_plan_lifecycle(
                dialogue_ref,
                lifecycle,
                sessions_root=self.sessions_root,
            )
        except ConversationPlanLifecycleError as exc:
            raise ProcessPlanIntegrityError(
                "Dialogue plan lifecycle could not be persisted"
            ) from exc
        if not any(
            receipt["lifecycle_digest"] == lifecycle["lifecycle_digest"]
            for receipt in state["dialogue_lifecycle_receipts"]
        ):
            self._record(
                dialogue_ref,
                state,
                "programming_plan_dialogue_lifecycle_persisted",
                {
                    "schema_version": PLAN_STATE_SCHEMA_VERSION,
                    "lifecycle": lifecycle["lifecycle"],
                    "plan_ref": lifecycle["plan_ref"],
                    "approval_receipt_digest": lifecycle[
                        "approval_receipt_digest"
                    ],
                    "lifecycle_digest": lifecycle["lifecycle_digest"],
                },
            )
        persisted = self.get_state(dialogue_ref)
        if persisted is None:
            raise ProcessPlanIntegrityError(
                "plan state disappeared after Dialogue lifecycle persistence"
            )
        return persisted

    def _ensure_artifact(
        self,
        run_id: str,
        artifact_id: str,
        text: str,
        *,
        role: str,
        node_id: str,
        action: str,
        selector: str,
        sources: Sequence[str] = (),
        conditions: Sequence[str],
    ) -> dict[str, Any]:
        run = self.runtime.load_run(run_id)
        if artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run_id, artifact_id)
            if artifact["identity"]["digest"] != _digest_text(text):
                raise ProcessPlanIntegrityError(
                    f"persisted planning Artifact drifted: {artifact_id}"
                )
            return artifact
        recorded = self.runtime.record_inline_artifact(
            run_id,
            artifact_id,
            text,
            role=role,
            node_id=node_id,
            action=action,
            selector=selector,
            source_artifact_ids=sources,
            satisfied_conditions=conditions,
            media_type="application/json",
        )
        return recorded["artifact"]

    @staticmethod
    def _ref(evidence_id: str, artifact: Mapping[str, Any]) -> dict[str, str]:
        return {
            "evidence_id": evidence_id,
            "artifact_id": artifact["artifact_id"],
            "identity_digest": artifact["identity"]["digest"],
            "outcome": "PASS",
        }

    def _promote_planning_contracts(
        self,
        run: Mapping[str, Any],
        interview_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        labels = set(run.get("labels", []))
        if "phase-2.3" in labels and "plan:approved" not in labels:
            return dict(run)
        replacement = _planning_contracts(
            run_id=run["run_id"],
            principal_id=run["contracts"]["authority"]["principal_id"],
            approved_at=self._now(),
            entry_contract_digest=interview_state["entry_contract_digest"],
        )
        self.runtime._replace_contracts_for_nonmutating_phase(
            run["run_id"],
            replacement,
            expected_current_plan_digest=run["contracts"]["approved_plan"]["digest"],
            phase="phase-2.3-planning",
            labels=["management-interview", "phase-2.3"],
        )
        return self.runtime.load_run(run["run_id"])

    def _drive_initial_plan(
        self,
        dialogue_ref: str,
        binding: Mapping[str, Any],
        run: Mapping[str, Any],
        interview_state: Mapping[str, Any],
        plan: Mapping[str, Any],
    ) -> None:
        run_id = run["run_id"]
        intent_text = json.dumps({
            "answers": {
                key: value["answer"] for key, value in interview_state["answers"].items()
            },
            "answers_digest": interview_state["answers_digest"],
        }, sort_keys=True)
        intent = self._ensure_artifact(
            run_id, "art-intent", intent_text,
            role="input", node_id="intent-interview", action="elicit_programming_intent",
            selector="scope:dialogue",
            conditions=["exact_dialogue_binding", "no_target_mutation"],
        )
        current = self.runtime.load_run(run_id)
        if current["current_node_id"] == "intent-interview":
            self.runtime.complete_action_node(
                run_id, "elicit_programming_intent",
                reason="The exact management interview is complete.",
                artifact_ids=[intent["artifact_id"]],
            )
        scope_text = json.dumps({
            "target": plan["repository_artifact_scope"]["target"],
            "scope": plan["repository_artifact_scope"]["declared_scope"],
            "instructions": plan["applicable_instructions"],
            "authority": plan["authority"],
        }, sort_keys=True)
        scope = self._ensure_artifact(
            run_id, "art-planning-scope", scope_text,
            role="input", node_id="inspect-scope", action="inspect_programming_scope",
            selector="scope:declared_inputs",
            conditions=["exact_target_identity", "no_target_mutation"],
        )
        current = self.runtime.load_run(run_id)
        if current["current_node_id"] == "inspect-scope":
            self.runtime.complete_action_node(
                run_id, "inspect_programming_scope",
                reason="Exact target, instruction, and authority scope was captured read-only.",
                artifact_ids=[scope["artifact_id"]],
            )
        current = self.runtime.load_run(run_id)
        if current["current_node_id"] == "scope-review":
            refs = [
                self._ref("ev-intent", intent),
                self._ref("ev-identity", scope),
                self._ref("ev-policy", scope),
                self._ref("ev-authority", scope),
            ]
            self.runtime.apply_transition(
                run_id, "PROCEED", target_node_id="mode-after-scope",
                reason="Independent contract validation supports the exact scope.",
                evaluation_boundary="programming-scope-review",
                evidence_refs=refs,
            )
        current = self.runtime.load_run(run_id)
        if current["current_node_id"] == "mode-after-scope":
            self.runtime.advance_decision(
                run_id, "prg_run", reason="Continue the confirmed PRG-Run path to planning."
            )
        plan_text = json.dumps(plan, sort_keys=True, ensure_ascii=False)
        plan_artifact_id = f"art-plan-v{plan['version'].replace('.', '-')}"
        plan_artifact = self._ensure_artifact(
            run_id, plan_artifact_id, plan_text,
            role="working", node_id="plan", action="produce_programming_plan",
            selector="scope:plan_outputs",
            conditions=["exact_plan_identity", "no_target_mutation"],
        )
        current = self.runtime.load_run(run_id)
        if current["current_node_id"] == "plan":
            self.runtime.complete_action_node(
                run_id, "produce_programming_plan",
                reason="One canonical plan and two digest-bound projections were produced.",
                artifact_ids=[plan_artifact_id],
            )
        review_text = json.dumps({
            "outcome": "PASS",
            "plan_ref": _plan_ref(plan),
            "projection_parity_digest": plan["projection_parity_digest"],
            "checks": [
                "canonical_digest", "required_fields", "projection_derivation",
                "baseline_binding", "no_phase_2_4_authority",
            ],
        }, sort_keys=True)
        evidence_id = f"art-plan-review-v{plan['version'].replace('.', '-')}"
        evidence = self._ensure_artifact(
            run_id, evidence_id, review_text,
            role="evidence", node_id="plan-review", action="record_planning_evidence",
            selector="scope:plan_outputs", sources=[plan_artifact_id],
            conditions=["exact_plan_identity", "no_target_mutation"],
        )
        current = self.runtime.load_run(run_id)
        if current["current_node_id"] == "plan-review":
            reviewed = any(
                (record.get("event") or {}).get("event_type") == "final_review_completed"
                and ((record.get("event") or {}).get("details") or {}).get("artifact_id")
                == plan_artifact_id
                and ((record.get("event") or {}).get("details") or {}).get("evidence_id")
                == "ev-review"
                for record in self.runtime.load_records(run_id)
            )
            if not reviewed:
                self.runtime.record_final_review(
                    run_id,
                    artifact_id=plan_artifact_id,
                    evidence_id="ev-review",
                    evidence_artifact_id=evidence_id,
                    outcome="PASS",
                    reviewer_id="reviewer:plan-contract-validator",
                    independent=True,
                    satisfied_conditions=["exact_plan_identity", "no_target_mutation"],
                )
            refs = [
                self._ref("ev-plan", plan_artifact),
                self._ref("ev-plan-projection-parity", evidence),
                self._ref("ev-review", evidence),
                self._ref("ev-authority", scope),
            ]
            self.runtime.apply_transition(
                run_id, "PROCEED", target_node_id="plan-approval",
                reason="The exact canonical plan passed independent review.",
                evaluation_boundary="programming-plan-review",
                evidence_refs=refs,
            )

    def propose(
        self,
        dialogue_ref: str,
        planning_basis: Mapping[str, Any],
        *,
        planner_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        key = _stable_idempotency(idempotency_key, field="proposal idempotency_key")
        planner = str(planner_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", planner):
            raise ProcessPlanError("planner_id is invalid")
        basis = _validate_basis(planning_basis)
        request_digest = _digest_json({
            "planner_id": planner,
            "planning_basis": basis,
        })
        with _PLAN_LOCK:
            context = self._context(dialogue_ref)
            if context is None:
                raise ProcessPlanConflict("Dialogue has no governing Process Run")
            binding, run, _definition = context
            interview_state = self._interview_state(dialogue_ref, binding, run)
            existing = self.get_state(dialogue_ref)
            if existing is not None and key in existing["proposal_idempotency"]:
                receipt = existing["proposal_idempotency"][key]
                if receipt["request_digest"] != request_digest:
                    raise ProcessPlanConflict("proposal idempotency identity conflicts")
                ref = receipt["plan_ref"]
                matching = [
                    plan for plan in [existing["current_plan"]]
                    if plan is not None and _plan_ref(plan) == ref
                ]
                if len(matching) != 1:
                    raise ProcessPlanIntegrityError(
                        "proposal receipt no longer identifies the current plan"
                    )
                plan = matching[0]
                run = self._promote_planning_contracts(run, interview_state)
                if plan["version"] == "1.0":
                    self._drive_initial_plan(
                        dialogue_ref, binding, run, interview_state, plan
                    )
                else:
                    self._ensure_artifact(
                        run["run_id"],
                        f"art-plan-v{plan['version'].replace('.', '-')}",
                        json.dumps(plan, sort_keys=True, ensure_ascii=False),
                        role="working", node_id="plan",
                        action="produce_programming_plan",
                        selector="scope:plan_outputs",
                        conditions=["exact_plan_identity", "no_target_mutation"],
                    )
                if existing["current_review"] is None:
                    self._record(
                        dialogue_ref,
                        {"run_id": run["run_id"], "binding_digest": binding["binding_digest"]},
                        "programming_plan_reviewed",
                        {
                            "schema_version": PLAN_STATE_SCHEMA_VERSION,
                            "plan_ref": _plan_ref(plan),
                            "outcome": "PASS",
                            "reviewer_id": "reviewer:plan-contract-validator",
                            "independent": True,
                            "projection_parity_digest": plan["projection_parity_digest"],
                        },
                    )
                recovered = self.get_state(dialogue_ref)
                if recovered is None:
                    raise ProcessPlanIntegrityError("plan disappeared during retry recovery")
                return self._persist_dialogue_lifecycle(dialogue_ref, recovered)
            if existing is not None and existing["status"] in {"approved", "retained"}:
                raise ProcessPlanConflict("the plan family is already closed")
            if existing is not None and existing["current_plan"] is not None:
                current_ref = _plan_ref(existing["current_plan"])
                revisable = (
                    existing["status"] in {"revision_requested", "stale"}
                    and (
                        not existing["revision_requests"]
                        or existing["revision_requests"][-1]["plan_ref"] == current_ref
                    )
                )
                if not revisable:
                    raise ProcessPlanConflict(
                        "a current reviewed plan requires a Principal decision before revision"
                    )
                version = len(existing["plan_versions"]) + 1
            else:
                version = 1
            baseline = capture_target_identity(basis["target_path"], captured_at=self._now())
            plan = _build_plan(
                run=run,
                dialogue_ref=dialogue_ref,
                interview_state=interview_state,
                basis=basis,
                baseline=baseline,
                version=version,
                planner_id=planner,
            )
            run = self._promote_planning_contracts(run, interview_state)
            state_seed = {
                "run_id": run["run_id"],
                "binding_digest": binding["binding_digest"],
            }
            self._record(
                dialogue_ref,
                state_seed,
                "programming_plan_proposed",
                {
                    "schema_version": PLAN_STATE_SCHEMA_VERSION,
                    "idempotency_key": key,
                    "request_digest": request_digest,
                    "plan": plan,
                    "plan_ref": _plan_ref(plan),
                },
            )
            if version == 1:
                self._drive_initial_plan(
                    dialogue_ref, binding, run, interview_state, plan
                )
            else:
                plan_text = json.dumps(plan, sort_keys=True, ensure_ascii=False)
                self._ensure_artifact(
                    run["run_id"], f"art-plan-v{version}-0", plan_text,
                    role="working", node_id="plan", action="produce_programming_plan",
                    selector="scope:plan_outputs",
                    conditions=["exact_plan_identity", "no_target_mutation"],
                )
            self._record(
                dialogue_ref,
                state_seed,
                "programming_plan_reviewed",
                {
                    "schema_version": PLAN_STATE_SCHEMA_VERSION,
                    "plan_ref": _plan_ref(plan),
                    "outcome": "PASS",
                    "reviewer_id": "reviewer:plan-contract-validator",
                    "independent": True,
                    "projection_parity_digest": plan["projection_parity_digest"],
                },
            )
            state = self.get_state(dialogue_ref)
            if state is None:
                raise ProcessPlanIntegrityError("plan state disappeared after proposal")
            return self._persist_dialogue_lifecycle(dialogue_ref, state)

    def request_revision(
        self,
        dialogue_ref: str,
        *,
        action: str,
        plan_ref: Mapping[str, Any],
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if action not in {"request_changes", "change_scope_or_permissions"}:
            raise ProcessPlanError("revision action is invalid")
        key = _stable_idempotency(idempotency_key, field="revision idempotency_key")
        explanation = " ".join(str(reason or "").split())
        if not explanation:
            raise ProcessPlanInputRequired("a material revision reason is required")
        with _PLAN_LOCK:
            state = self.get_state(dialogue_ref)
            if state is None:
                raise ProcessPlanConflict("Dialogue has no active plan")
            for prior in state["revision_requests"]:
                if prior["idempotency_key"] == key:
                    if (
                        prior["plan_ref"] != dict(plan_ref)
                        or prior["action"] != action
                        or prior["reason"] != explanation
                    ):
                        raise ProcessPlanConflict("revision idempotency identity conflicts")
                    return self._persist_dialogue_lifecycle(dialogue_ref, state)
            if state["status"] != "awaiting_approval":
                raise ProcessPlanConflict("no reviewed plan is awaiting a revision decision")
            if dict(plan_ref) != _plan_ref(state["current_plan"]):
                raise ProcessPlanConflict("revision request does not bind the current plan")
            kind = (
                "programming_plan_revision_requested"
                if action == "request_changes"
                else "programming_plan_scope_change_requested"
            )
            self._record(
                dialogue_ref, state, kind,
                {
                    "schema_version": PLAN_STATE_SCHEMA_VERSION,
                    "plan_ref": dict(plan_ref),
                    "idempotency_key": key,
                    "action": action,
                    "reason": explanation,
                },
            )
            result = self.get_state(dialogue_ref)
            if result is None:
                raise ProcessPlanIntegrityError("plan state disappeared after revision request")
            return self._persist_dialogue_lifecycle(dialogue_ref, result)

    def _export_directory(self, project_ref: str) -> Path:
        if self.project_folder_resolver is not None:
            folder = Path(self.project_folder_resolver(project_ref))
            target = folder if folder.is_absolute() else self.vault_root / folder
        elif project_ref in {"", "commons", "general"}:
            target = self.vault_root
        else:
            try:
                from project_meta import project_folder_path, read_project_meta
            except ImportError:  # pragma: no cover
                from orchestrator.project_meta import project_folder_path, read_project_meta
            metadata = read_project_meta(project_ref)
            if not metadata or not metadata.get("folder_name"):
                raise ProcessPlanConflict("project has no exact vault folder identity")
            target = project_folder_path(
                metadata["folder_name"], self.vault_root / "Projects"
            )
        resolved_root = self.vault_root.resolve(strict=True)
        if target.is_symlink():
            raise ProcessPlanIntegrityError("plan export directory cannot be a symlink")
        resolved = target.resolve(strict=False)
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ProcessPlanIntegrityError("plan export escapes the configured vault") from exc
        # Validate the resolved destination before creating anything.  A
        # rejected resolver must not be able to create an out-of-vault path as
        # a side effect of the validation itself.
        resolved.mkdir(parents=True, exist_ok=True)
        resolved = resolved.resolve(strict=True)
        return resolved

    def _render_export(
        self,
        plan: Mapping[str, Any],
        approval: Mapping[str, Any],
    ) -> str:
        date = str(approval["decided_at"])[0:10].replace("-", "/")
        principal = plan["principal_view"]["content"]
        technical = plan["technical_view"]["content"]
        canonical = json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False)
        return (
            "---\n"
            f"nexus:\n  - {json.dumps(str(plan['project_ref']), ensure_ascii=False)}\n"
            "type: working\n"
            "tags:\n  - process\n  - \"plan:approved\"\n"
            f"date created: {date}\n"
            f"date modified: {date}\n"
            "---\n"
            f"# Plan Execution Contract — {plan['run_id']} — v{plan['version']}\n\n"
            f"plan id: `{plan['plan_id']}`\n"
            f"plan version: `{plan['version']}`\n"
            f"plan digest: `{plan['digest']}`\n"
            f"run id: `{plan['run_id']}`\n"
            f"approved by: `{approval['decision_by']}`\n"
            f"approved at: `{approval['decided_at']}`\n"
            f"approval decision: `{approval['decision']}`\n"
            f"baseline digest: `{approval['baseline_digest']}`\n\n"
            "## Principal View\n\n"
            f"- **Outcome:** {principal['outcome']}\n"
            f"- **Users:** {principal['users']}\n"
            f"- **Scope:** {json.dumps(principal['scope'], ensure_ascii=False)}\n"
            f"- **Authority:** {json.dumps(principal['authority'], ensure_ascii=False)}\n"
            f"- **Risks:** {'; '.join(principal['risks'])}\n"
            f"- **Exceptions:** {principal['exceptions']}\n"
            f"- **Proof:** {'; '.join(principal['proof'])}\n"
            f"- **Activation:** {json.dumps(principal['activation'], ensure_ascii=False)}\n\n"
            "## Technical View\n\n"
            f"- **Artifacts:** {json.dumps(technical['artifacts'], ensure_ascii=False)}\n"
            f"- **Architecture:** {'; '.join(technical['architecture'])}\n"
            f"- **Dependencies:** {'; '.join(technical['dependencies'])}\n"
            f"- **Implementation sequence:** {json.dumps(technical['implementation_sequence'], ensure_ascii=False)}\n"
            f"- **Tests:** {'; '.join(technical['tests'])}\n"
            f"- **Evidence:** {'; '.join(technical['evidence'])}\n"
            f"- **Versioning:** {'; '.join(technical['versioning'])}\n"
            f"- **Recovery:** {'; '.join(technical['recovery'])}\n\n"
            "## Canonical Machine-Readable Contract\n\n"
            "```json\n"
            f"{canonical}\n"
            "```\n"
        )

    def approve(
        self,
        dialogue_ref: str,
        *,
        decision: str,
        plan_ref: Mapping[str, Any],
        baseline_digest: str,
        decision_by: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if decision not in {"approve_and_start", "approve_without_start"}:
            raise ProcessPlanError("approval decision is invalid")
        key = _stable_idempotency(idempotency_key, field="approval idempotency_key")
        with _PLAN_LOCK:
            state = self.get_state(dialogue_ref)
            if state is None:
                raise ProcessPlanConflict("Dialogue has no active plan")

            def withhold_stale(
                plan_value: Mapping[str, Any],
                *,
                stale_kind: str,
                expected_identity: str,
                current_identity: str,
            ) -> dict[str, Any]:
                latest_state = self.get_state(dialogue_ref)
                if latest_state is None:
                    raise ProcessPlanIntegrityError("plan state disappeared")
                already_recorded = any(
                    item["plan_ref"] == _plan_ref(plan_value)
                    and item["stale_kind"] == stale_kind
                    and item["expected_identity_digest"] == expected_identity
                    and item["current_identity_digest"] == current_identity
                    for item in latest_state["stale_records"]
                )
                if not already_recorded:
                    self._record(
                        dialogue_ref, latest_state, "programming_plan_stale",
                        {
                            "schema_version": PLAN_STATE_SCHEMA_VERSION,
                            "plan_ref": _plan_ref(plan_value),
                            "stale_kind": stale_kind,
                            "expected_identity_digest": expected_identity,
                            "current_identity_digest": current_identity,
                        },
                    )
                stale_state = self.get_state(dialogue_ref)
                if stale_state is None:
                    raise ProcessPlanIntegrityError("stale plan state disappeared")
                return self._persist_dialogue_lifecycle(
                    dialogue_ref, stale_state
                )

            prior = state["approval_idempotency"].get(key)
            if prior is not None:
                if (
                    prior["decision"] != decision
                    or prior["plan_ref"] != dict(plan_ref)
                    or prior["baseline_digest"] != baseline_digest
                    or prior["decision_by"] != decision_by
                ):
                    raise ProcessPlanConflict("approval idempotency identity conflicts")
                if state["current_plan"] is None or _plan_ref(
                    state["current_plan"]
                ) != prior["plan_ref"]:
                    raise ProcessPlanConflict(
                        "approval retry no longer identifies the current plan"
                    )
                approval = prior
                plan = state["current_plan"]
                expected_baseline = prior["baseline_digest"]
            else:
                if state["status"] != "awaiting_approval":
                    raise ProcessPlanConflict("no exact reviewed plan is awaiting approval")
                plan = state["current_plan"]
                if dict(plan_ref) != _plan_ref(plan):
                    raise ProcessPlanConflict("approval does not bind the current plan version")
                expected_baseline = plan["repository_artifact_scope"]["target"]["identity"]["digest"]
                if baseline_digest != expected_baseline:
                    raise ProcessPlanConflict("approval baseline does not match the plan")
                principal = self.runtime.load_run(state["run_id"])["contracts"]["authority"][
                    "principal_id"
                ]
                if decision_by != principal:
                    raise AuthorityDeniedError("only the Run principal may approve the plan")
                expected_instructions, current_instructions = _instruction_state_digests(
                    plan["applicable_instructions"]
                )
                if current_instructions != expected_instructions:
                    return withhold_stale(
                        plan,
                        stale_kind="instructions",
                        expected_identity=expected_instructions,
                        current_identity=current_instructions,
                    )
                current = capture_target_identity(
                    plan["repository_artifact_scope"]["target"]["locator"]["ref"],
                    captured_at=self._now(),
                )
                current_digest = current["identity"]["digest"]
                if current_digest != expected_baseline:
                    return withhold_stale(
                        plan,
                        stale_kind="target",
                        expected_identity=expected_baseline,
                        current_identity=current_digest,
                    )
                approval = {
                    "schema_version": PLAN_STATE_SCHEMA_VERSION,
                    "plan_ref": _plan_ref(plan),
                    "baseline_digest": expected_baseline,
                    "decision": decision,
                    "decision_by": decision_by,
                    "decided_at": self._now(),
                    "idempotency_key": key,
                }
                self._record(
                    dialogue_ref, state, "programming_plan_approval_decided", approval
                )
            # Revalidate again after recovering or persisting the approval.  A
            # crash between decision persistence and export must not allow a
            # changed target or governing instruction to be committed as the
            # current execution contract.
            expected_instructions, current_instructions = _instruction_state_digests(
                plan["applicable_instructions"]
            )
            if current_instructions != expected_instructions:
                return withhold_stale(
                    plan,
                    stale_kind="instructions",
                    expected_identity=expected_instructions,
                    current_identity=current_instructions,
                )
            current = capture_target_identity(
                plan["repository_artifact_scope"]["target"]["locator"]["ref"],
                captured_at=self._now(),
            )
            current_digest = current["identity"]["digest"]
            if current_digest != expected_baseline:
                return withhold_stale(
                    plan,
                    stale_kind="target",
                    expected_identity=expected_baseline,
                    current_identity=current_digest,
                )
            export_dir = self._export_directory(plan["project_ref"])
            filename = (
                f"Plan Execution Contract — {state['run_id']} — v{plan['version']}.md"
            )
            export_path = export_dir / filename
            content = self._render_export(plan, approval)
            digest = _digest_text(content)
            if export_path.exists():
                if export_path.is_symlink() or export_path.read_text(encoding="utf-8") != content:
                    raise ProcessPlanIntegrityError(
                        "approved plan export path contains different content"
                    )
            else:
                _runtime_paths.atomic_write_text(export_path, content)
            latest = self.get_state(dialogue_ref)
            if latest is None:
                raise ProcessPlanIntegrityError("approval state disappeared before export")
            if latest["export"] is None:
                self._record(
                    dialogue_ref, latest, "programming_plan_exported",
                    {
                        "schema_version": PLAN_STATE_SCHEMA_VERSION,
                        "plan_ref": _plan_ref(plan),
                        "path": str(export_path),
                        "content_digest": digest,
                    },
                )
            elif latest["export"] != {
                "schema_version": PLAN_STATE_SCHEMA_VERSION,
                "plan_ref": _plan_ref(plan),
                "path": str(export_path),
                "content_digest": digest,
            }:
                raise ProcessPlanIntegrityError("persisted plan export receipt drifted")
            run = self.runtime.load_run(state["run_id"])
            if run["contracts"]["approved_plan"]["digest"] != plan["digest"]:
                approved_contracts = _approved_phase_contracts(
                    current_contracts=run["contracts"],
                    plan=plan,
                    approval=approval,
                )
                self.runtime._replace_contracts_for_nonmutating_phase(
                    run["run_id"], approved_contracts,
                    expected_current_plan_digest=run["contracts"]["approved_plan"]["digest"],
                    phase="phase-2.3-approved",
                    labels=["management-interview", "phase-2.3", "plan:approved"],
                )
            current_run = self.runtime.load_run(run["run_id"])
            if current_run["current_node_id"] == "plan-approval":
                self.runtime.resolve_human_checkpoint(
                    run["run_id"], "approved", decision_by=decision_by,
                    reason="The Principal approved the exact plan and current baseline.",
                )
            result = self.get_state(dialogue_ref)
            if result is None:
                raise ProcessPlanIntegrityError("approved plan state disappeared")
            return self._persist_dialogue_lifecycle(dialogue_ref, result)

    def stop_and_retain(
        self,
        dialogue_ref: str,
        *,
        plan_ref: Mapping[str, Any],
        decision_by: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        key = _stable_idempotency(idempotency_key, field="retention idempotency_key")
        explanation = " ".join(str(reason or "").split())
        if not explanation:
            raise ProcessPlanInputRequired("retention reason is required")
        with _PLAN_LOCK:
            state = self.get_state(dialogue_ref)
            if state is None:
                raise ProcessPlanConflict("Dialogue has no active plan")
            prior = state["retained"]
            if prior is not None and prior["idempotency_key"] == key:
                if (
                    prior["plan_ref"] != dict(plan_ref)
                    or prior["decision_by"] != decision_by
                    or prior["reason"] != explanation
                ):
                    raise ProcessPlanConflict("retention idempotency identity conflicts")
                run = self.runtime.load_run(state["run_id"])
                if run["current_node_id"] == "plan-approval":
                    self.runtime.resolve_human_checkpoint(
                        state["run_id"], "denied", decision_by=decision_by,
                        reason=(
                            "The Principal stopped execution and retained the reviewed plan."
                        ),
                    )
                recovered = self.get_state(dialogue_ref)
                if recovered is None:
                    raise ProcessPlanIntegrityError("retained plan state disappeared")
                return self._persist_dialogue_lifecycle(dialogue_ref, recovered)
            if state["status"] != "awaiting_approval":
                raise ProcessPlanConflict("no reviewed plan is awaiting a decision")
            if dict(plan_ref) != _plan_ref(state["current_plan"]):
                raise ProcessPlanConflict("retention does not bind the current plan")
            principal = self.runtime.load_run(state["run_id"])["contracts"]["authority"][
                "principal_id"
            ]
            if decision_by != principal:
                raise AuthorityDeniedError("only the Run principal may retain and stop")
            self._record(
                dialogue_ref, state, "programming_plan_retained",
                {
                    "schema_version": PLAN_STATE_SCHEMA_VERSION,
                    "plan_ref": dict(plan_ref),
                    "decision_by": decision_by,
                    "reason": explanation,
                    "idempotency_key": key,
                },
            )
            self.runtime.resolve_human_checkpoint(
                state["run_id"], "denied", decision_by=decision_by,
                reason="The Principal stopped execution and retained the reviewed plan.",
            )
            result = self.get_state(dialogue_ref)
            if result is None:
                raise ProcessPlanIntegrityError("retained plan state disappeared")
            return self._persist_dialogue_lifecycle(dialogue_ref, result)


__all__ = [
    "PLAN_ACTIONS",
    "PLAN_SCHEMA_VERSION",
    "PLAN_STATE_SCHEMA_VERSION",
    "ProcessPlanApprovalService",
    "ProcessPlanConflict",
    "ProcessPlanError",
    "ProcessPlanInputRequired",
    "ProcessPlanIntegrityError",
    "capture_target_identity",
]
