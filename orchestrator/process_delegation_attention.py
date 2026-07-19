"""G1.1 Phase 2.4 — exact delegation and quiet attention projection.

This module does not introduce another execution engine or a Run Inspector.
It binds an already-approved Plan Execution Contract to the generic governed
runtime, advances only the definition-declared ``prg_run`` route, and projects
the durable objects into the three Ora management surfaces required here:

* Pending — every live Process Run;
* Automated Processes — independently deployed standing definitions with
  trigger and authority bindings (none can be inferred from registration); and
* Unread — returned results and focused human decisions newer than the
  governing Dialogue's read marker.

Attention is a projection, never a Process Run or Artifact lifecycle state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import conversation_memory as _memory
    import process_contracts as _contracts
    import runtime_paths as _runtime_paths
    from governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        TERMINAL_RUN_STATES,
    )
    from process_definition_registry import (
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
    )
    from process_plan_approval import (
        ProcessPlanApprovalService,
        capture_target_identity,
    )
except ImportError:  # pragma: no cover - package-qualified imports
    from orchestrator import conversation_memory as _memory
    from orchestrator import process_contracts as _contracts
    from orchestrator import runtime_paths as _runtime_paths
    from orchestrator.governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        TERMINAL_RUN_STATES,
    )
    from orchestrator.process_definition_registry import (
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
    )
    from orchestrator.process_plan_approval import (
        ProcessPlanApprovalService,
        capture_target_identity,
    )


DELEGATION_SCHEMA_VERSION = "ora.programming-delegation/1.0"
ATTENTION_SCHEMA_VERSION = "ora.process-attention-projection/1.0"
DELEGATION_OBSERVATION_PREFIX = "programming_delegation_"

_DELEGATION_LOCK = threading.RLock()
_SUPPORTED_REQUESTED_ACTIONS = frozenset({"inspect", "mutate", "test"})
_SEPARATELY_RESERVED_ACTIONS = frozenset({
    "activate",
    "construct_definition",
    "expand_scope",
    "publish",
    "register_definition",
    "remote_git",
    "send_external",
})
_EXECUTION_NODE_IDS = (
    "post-plan-mode",
    "execute-preflight",
    "execute-step",
    "attempt-review",
    "work-remaining",
    "execution-work-remaining",
    "revision-route",
    "correction-loop",
    "correct",
    "no-progress",
    "replan-route",
    "attempt-redefine-route",
    "final-redefine-route",
    "persist-definition-resume-execute",
    "persist-definition-resume-final",
    "definition-plan",
    "definition-plan-review",
    "definition-plan-approval",
    "redefine",
    "definition-review",
    "definition-resume-route",
    "authority",
    "resume-route",
    "final-review",
    "accepted",
    "returned",
    "blocked",
)


class ProcessDelegationError(RuntimeError):
    """Base class for invalid or refused Phase 2.4 operations."""


class ProcessDelegationConflict(ProcessDelegationError):
    """A delegation request conflicts with persisted identity or state."""


class ProcessDelegationIntegrityError(ProcessDelegationError):
    """A Run, plan, approval, attention, or registry identity drifted."""


class ProcessDelegationInputRequired(ProcessDelegationError):
    """A delegation request omits an exact required input."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _stable_id(value: str, *, field: str) -> str:
    clean = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", clean):
        raise ProcessDelegationInputRequired(f"{field} is invalid")
    return clean


def _exact_digest(value: str, *, field: str) -> str:
    clean = str(value or "").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", clean):
        raise ProcessDelegationInputRequired(f"{field} is invalid")
    return clean


def _plan_ref(plan: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: str(plan[field]) for field in ("plan_id", "version", "digest")
    }


def _delegation_checkpoint_id(delegation_digest: str) -> str:
    return "delegation-" + delegation_digest.split(":", 1)[1][:24]


def _execution_contracts(
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    *,
    delegation_digest: str,
) -> dict[str, Any]:
    """Derive the execution authority solely from the exact approved plan."""

    handoff = plan["execution_handoff"]
    requested = set(handoff["requested_actions"])
    unsupported = sorted(requested - _SUPPORTED_REQUESTED_ACTIONS)
    if unsupported:
        raise ProcessDelegationInputRequired(
            "approved execution handoff contains unsupported action(s): "
            + ", ".join(unsupported)
        )
    if not {"mutate", "test"}.issubset(requested):
        raise ProcessDelegationInputRequired(
            "Programming delegation requires exact mutation and test authority"
        )

    exact_selectors = [
        "artifact:" + str(selector).strip()
        for selector in handoff["artifact_selectors"]
    ]
    if any(selector == "artifact:" for selector in exact_selectors):
        raise ProcessDelegationInputRequired(
            "approved execution handoff has an empty artifact selector"
        )
    condition = f"delegation_identity={delegation_digest}"
    baseline = plan["repository_artifact_scope"]["target"]["identity"]["digest"]
    scope_condition = f"approved_baseline={baseline}"
    plan_condition = f"approved_plan={plan['digest']}"

    read_selectors = [
        "scope:approved_plan",
        "scope:declared_inputs",
        "scope:declared_outputs",
        "scope:process_definition",
        *exact_selectors,
    ]
    # Exact target mutations are external effects because they change the
    # repository outside the Run record. They deliberately do not overlap the
    # ordinary write scope, which is reserved for local evidence/receipt
    # Artifacts. Higher-order effects remain separately reserved below.
    write_selectors = ["scope:declared_outputs"]
    external_selectors = list(exact_selectors)
    grants = [
        {
            "grant_id": "grant-inspect",
            "actions": [
                "programming_preflight",
                "persist_programming_resume_execute",
                "persist_programming_resume_final",
            ],
            "resource_selectors": [
                "scope:declared_inputs",
                "scope:declared_outputs",
                "scope:process_definition",
                *exact_selectors,
            ],
            "effect_types": ["read_only", "local_reversible"],
            "conditions": [condition, scope_condition, plan_condition],
        },
        {
            "grant_id": "grant-test",
            "actions": ["inspect_programming_result"],
            "resource_selectors": ["scope:declared_outputs", *exact_selectors],
            "effect_types": ["read_only", "local_reversible"],
            "conditions": [condition, scope_condition, plan_condition],
        },
        {
            "grant_id": "grant-execute-approved-step",
            "actions": [
                "execute_approved_programming_step",
                "correct_programming_defect",
            ],
            "resource_selectors": list(exact_selectors),
            "effect_types": ["local_reversible"],
            "conditions": [
                condition,
                scope_condition,
                plan_condition,
                "checkpoint_persisted_before_mutation",
            ],
        },
        {
            "grant_id": "grant-record-mutation-receipt",
            "actions": ["record_programming_mutation_receipt"],
            "resource_selectors": ["scope:declared_outputs"],
            "effect_types": ["local_reversible"],
            "conditions": [condition, scope_condition, plan_condition],
        },
    ]

    evidence = [
        ("ev-identity", "Current target identity matches the approved baseline.", "target_composite_identity", "same_step", ["scope:declared_inputs"]),
        ("ev-authority", "Every action remains within the exact delegation.", "authority_contract_validation", "independent_step", ["scope:approved_plan"]),
        ("ev-recovery", "A safe checkpoint precedes mutation.", "checkpoint_identity_validation", "same_step", ["scope:declared_outputs"]),
        ("ev-action", "The approved action completed with a receipt.", "action_receipt_validation", "same_step", ["scope:declared_outputs"]),
        ("ev-delta", "The exact artifact delta is current.", "artifact_delta_identity", "same_step", ["scope:declared_outputs"]),
        ("ev-check", "The approved checks ran against the current result.", "current_test_evidence", "independent_step", ["scope:declared_outputs"]),
        ("ev-review", "Independent judgment reviewed current evidence.", "independent_review", "independent_step", ["scope:declared_outputs"]),
        ("ev-progress", "Correction made evidence-backed progress.", "progress_evidence", "independent_step", ["scope:declared_outputs"]),
        ("ev-final-binding", "Final evidence binds the exact result identity.", "final_result_binding", "independent_step", ["scope:declared_outputs"]),
        ("ev-definition-defect", "A definition defect is exact if redefinition is requested.", "definition_defect_evidence", "independent_step", ["scope:process_definition"]),
        ("ev-plan", "The exact approved plan remains bound.", "approved_plan_digest_validation", "same_step", ["scope:approved_plan"]),
        ("ev-definition", "Any replacement definition has exact identity.", "definition_identity_validation", "independent_step", ["scope:process_definition"]),
    ]
    requirements = [
        {
            "evidence_id": evidence_id,
            "claim": claim,
            "method": method,
            "producer_independence": independence,
            "artifact_selectors": selectors,
            "freshness_seconds": 86400,
            "required": evidence_id in {
                "ev-identity", "ev-authority", "ev-recovery", "ev-delta",
                "ev-check", "ev-review", "ev-final-binding",
            },
        }
        for evidence_id, claim, method, independence, selectors in evidence
    ]
    judgments = [
        {
            "judgment_id": "delegated-attempt-review",
            "node_id": "attempt-review",
            "verified_circumstances": [
                "The exact attempt, result identity, and evidence are current."
            ],
            "question": "Which declared route is supported by the current attempt evidence?",
            "permitted_conclusions": [
                "continue", "local_defect", "plan_defect", "authority_required",
                "blocked",
            ],
            "permitted_directives": [
                "PROCEED", "REVISE", "REPLAN", "ESCALATE", "BLOCKED",
            ],
            "permitted_actions": ["inspect_programming_result"],
            "authority_grant_ids": ["grant-test"],
            "artifact_selectors": ["scope:declared_outputs"],
            "required_evidence_ids": [
                "ev-identity", "ev-delta", "ev-check", "ev-review",
            ],
            "evaluator_boundary": "delegated-programming-attempt-review",
            "stop_conditions": list(handoff["stop_conditions"]),
            "return_node_id": "execute-step",
            "escalation_request_types": [
                "programming_reserved_authority", "scope_expansion", "material_replan",
            ],
        },
        {
            "judgment_id": "delegated-final-review",
            "node_id": "final-review",
            "verified_circumstances": [
                "The exact current result received independent final review."
            ],
            "question": "Does current evidence support final acceptance or another declared route?",
            "permitted_conclusions": [
                "accepted", "local_defect", "plan_defect", "authority_required",
                "blocked",
            ],
            "permitted_directives": [
                "ACCEPT", "REVISE", "REPLAN", "ESCALATE", "BLOCKED",
            ],
            "permitted_actions": ["inspect_programming_result"],
            "authority_grant_ids": ["grant-test"],
            "artifact_selectors": ["scope:declared_outputs"],
            "required_evidence_ids": [
                "ev-identity", "ev-delta", "ev-check", "ev-review",
                "ev-final-binding",
            ],
            "evaluator_boundary": "delegated-programming-final-review",
            "stop_conditions": list(handoff["stop_conditions"]),
            "return_node_id": "final-review",
            "escalation_request_types": [
                "programming_reserved_authority", "scope_expansion", "material_replan",
            ],
        },
    ]
    loop = plan["loop_policy"]
    approved_plan = {
        "plan_id": plan["plan_id"],
        "version": plan["version"],
        "digest": plan["digest"],
        "objective": plan["objective"],
        "approved_by": approval["decision_by"],
        "approved_at": approval["decided_at"],
        "approved_node_ids": list(_EXECUTION_NODE_IDS),
        "constraints": [
            f"Bind exact delegation {delegation_digest}.",
            f"Bind exact approved baseline {baseline}.",
            "Only the approved execution handoff selectors may be mutated.",
            "Every external effect requires a pre-action checkpoint and exact receipt.",
            "Activation, registration, publication, remote Git, and scope expansion remain separately reserved.",
        ],
        "non_goals": list(plan["non_solutions"]),
    }
    contracts = {
        "approved_plan": approved_plan,
        "authority": {
            "principal_id": approval["decision_by"],
            "grants": grants,
            "reserved_actions": sorted(_SEPARATELY_RESERVED_ACTIONS),
        },
        "artifact_scope": {
            "read_selectors": read_selectors,
            "write_selectors": write_selectors,
            "external_effect_selectors": external_selectors,
        },
        "bounded_judgment": judgments,
        "evidence": {
            "requirements": requirements,
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "invalidate",
        },
        "correction_loop": {
            "max_attempts": loop["max_attempts"],
            "attempt": 0,
            "progress_evidence_required": loop["progress_required"],
            "repeated_defect_limit": loop["repeated_defect_limit"],
            "allowed_directives": [
                "REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED",
            ],
            "no_progress_directives": [
                loop["on_no_progress"], "ESCALATE", "BLOCKED",
            ],
        },
        "continuation": {
            "checkpoint_id": "phase-2.4-delegation",
            "resume_node_id": "execute-preflight",
            "required_state_fields": [
                "current_node_id", "last_sequence", "artifact_ids", "contracts",
            ],
            "child_return_fields": [
                "definition_ref", "output_artifact_bindings", "acceptance_evidence_refs",
            ],
            "parent_run_id": None,
            "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "never_replay_effects",
            "checkpoint_ref": "checkpoint:phase-2.4-delegation",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": [
                "ev-identity", "ev-authority", "ev-recovery",
            ],
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": list(handoff["stop_conditions"]),
            "blocked_conditions": [
                "approved_baseline_stale", "missing_evidence",
                "unsafe_recovery", "no_permitted_transition",
            ],
            "authority_request_types": [
                "programming_reserved_authority", "scope_expansion", "material_replan",
            ],
            "authority_return_target": approval["decision_by"],
        },
    }
    return _contracts.validate_process_run({
        "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_run",
        "run_id": "validation-only",
        "definition_ref": {
            "definition_id": "validation/only",
            "version": "1.0",
            "digest": "sha256:" + ("0" * 64),
        },
        "state": "running",
        "entrypoint": "validation",
        "current_node_id": "post-plan-mode",
        "input_bindings": {},
        "contracts": contracts,
        "relationships": {
            "parent_run_id": None,
            "invoked_by_run_id": None,
            "invoked_definition_refs": [],
            "constructed_definition_refs": [],
            "return_to_run_id": None,
        },
        "artifact_ids": [],
        "last_sequence": 0,
        "created_at": approval["decided_at"],
        "updated_at": approval["decided_at"],
    })["contracts"]


class ProcessDelegationAttentionService:
    """Own Phase 2.4 delegation and read-only management projections."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        plan_service: ProcessPlanApprovalService | None = None,
        registry: ProcessDefinitionRegistry | None = None,
        sessions_root: str | Path | None = None,
        repository_root: str | Path | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.runtime = runtime or GovernedProcessRuntime()
        self.sessions_root = Path(sessions_root) if sessions_root else (
            _runtime_paths.ORA_HOME / "sessions"
        )
        self.repository_root = Path(repository_root) if repository_root else Path(
            _runtime_paths.ORA_HOME
        )
        self._now = now or _utc_now
        self.plan_service = plan_service or ProcessPlanApprovalService(
            runtime=self.runtime,
            sessions_root=self.sessions_root,
            repository_root=self.repository_root,
            now=self._now,
        )
        self.registry = registry or ProcessDefinitionRegistry()

    def _observations(
        self, dialogue_ref: str, run_id: str, binding_digest: str
    ) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for record in self.runtime.load_records(run_id):
            event = record.get("event") or {}
            details = event.get("details") or {}
            kind = str(details.get("observation_type") or "")
            if (
                event.get("event_type") != "dialogue_observation_recorded"
                or not kind.startswith(DELEGATION_OBSERVATION_PREFIX)
            ):
                continue
            payload = details.get("payload")
            if (
                details.get("dialogue_ref") != dialogue_ref
                or details.get("binding_digest") != binding_digest
                or not isinstance(payload, dict)
                or details.get("payload_digest") != _digest_json(payload)
            ):
                raise ProcessDelegationIntegrityError(
                    "delegation observation identity is invalid"
                )
            observations.append({
                "record_id": record["record_id"],
                "recorded_at": record["recorded_at"],
                "kind": kind,
                "payload": copy.deepcopy(payload),
            })
        return observations

    def get_delegation(self, dialogue_ref: str) -> dict[str, Any] | None:
        plan_state = self.plan_service.get_state(dialogue_ref)
        if plan_state is None or plan_state.get("current_plan") is None:
            return None
        observations = self._observations(
            dialogue_ref, plan_state["run_id"], plan_state["binding_digest"]
        )
        latest = observations[-1] if observations else None
        activation_records = [
            record
            for record in self.runtime.load_records(plan_state["run_id"])
            if (record.get("event") or {}).get("event_type")
            == "delegation_activated"
        ]
        if len(activation_records) > 1:
            raise ProcessDelegationIntegrityError(
                "Process Run has multiple delegation activations"
            )
        activation = activation_records[0] if activation_records else None
        if activation is not None:
            if latest is None or latest["kind"] != "programming_delegation_authorized":
                raise ProcessDelegationIntegrityError(
                    "delegation activation lacks its authoritative Dialogue receipt"
                )
            details = activation["event"]["details"]
            payload = latest["payload"]
            plan = plan_state["current_plan"]
            approval = plan_state["approval"]
            authorization_body = {
                "schema_version": DELEGATION_SCHEMA_VERSION,
                "idempotency_key": payload.get("idempotency_key"),
                "dialogue_ref": dialogue_ref,
                "run_id": plan_state["run_id"],
                "binding_digest": plan_state["binding_digest"],
                "plan_ref": _plan_ref(plan),
                "approval_receipt_digest": _digest_json(approval),
                "approval_decision": approval["decision"],
                "requested_by": approval["decision_by"],
                "target_baseline_digest": plan[
                    "repository_artifact_scope"
                ]["target"]["identity"]["digest"],
                "target_binding": {
                    "locator": copy.deepcopy(
                        plan["repository_artifact_scope"]["target"]["locator"]
                    ),
                    "baseline_identity_digest": plan[
                        "repository_artifact_scope"
                    ]["target"]["identity"]["digest"],
                },
            }
            expected_delegation_digest = _digest_json(authorization_body)
            expected_contracts = _execution_contracts(
                plan, approval, delegation_digest=expected_delegation_digest
            )
            expected_payload = {
                **authorization_body,
                "delegation_digest": expected_delegation_digest,
                "contracts": expected_contracts,
                "contracts_digest": _digest_json(expected_contracts),
            }
            if (
                payload != expected_payload
                or
                details.get("delegation_digest") != payload.get("delegation_digest")
                or details.get("approval_receipt_digest")
                != payload.get("approval_receipt_digest")
                or details.get("plan_ref") != payload.get("plan_ref")
                or details.get("target_binding") != payload.get("target_binding")
                or details.get("idempotency_key") != payload.get("idempotency_key")
                or details.get("contracts") != payload.get("contracts")
                or payload.get("contracts_digest")
                != _digest_json(payload.get("contracts"))
            ):
                raise ProcessDelegationIntegrityError(
                    "delegation activation drifted from its exact authorization"
                )
        run = self.runtime.load_run(plan_state["run_id"])
        checkpoint = None
        if activation is not None:
            checkpoint_id = _delegation_checkpoint_id(
                latest["payload"]["delegation_digest"]
            )
            checkpoints = [
                record for record in self.runtime.load_records(plan_state["run_id"])
                if (record.get("event") or {}).get("event_type")
                == "checkpoint_created"
                and (record["event"].get("details") or {}).get("checkpoint_id")
                == checkpoint_id
            ]
            if len(checkpoints) > 1:
                raise ProcessDelegationIntegrityError(
                    "delegation has multiple exact checkpoints"
                )
            checkpoint = checkpoints[0] if checkpoints else None
            positioning_records = [
                record for record in self.runtime.load_records(plan_state["run_id"])
                if (record.get("event") or {}).get("event_type") == "node_advanced"
                and (record["event"].get("details") or {}).get("from_node_id")
                == "post-plan-mode"
            ]
            if len(positioning_records) > 1:
                raise ProcessDelegationIntegrityError(
                    "delegation has multiple post-plan positioning records"
                )
            positioning = positioning_records[0] if positioning_records else None
            expected_materialized_contracts = copy.deepcopy(
                latest["payload"]["contracts"]
            )
            if checkpoint is not None:
                checkpoint_details = checkpoint["event"]["details"]
                if (
                    checkpoint_details.get("segment_id")
                    != "phase-2.4-delegated-execution"
                    or checkpoint_details.get("resume_node_id")
                    != "execute-preflight"
                    or checkpoint["sequence"] <= activation["sequence"]
                ):
                    raise ProcessDelegationIntegrityError(
                        "delegation checkpoint identity or ordering is invalid"
                    )
                expected_materialized_contracts["continuation"][
                    "checkpoint_id"
                ] = checkpoint_id
            latest_checkpoint = next(
                (
                    record for record in reversed(
                        self.runtime.load_records(plan_state["run_id"])
                    )
                    if (record.get("event") or {}).get("event_type")
                    == "checkpoint_created"
                ),
                None,
            )
            if latest_checkpoint is not None:
                latest_checkpoint_details = latest_checkpoint["event"]["details"]
                expected_materialized_contracts["continuation"][
                    "checkpoint_id"
                ] = latest_checkpoint_details["checkpoint_id"]
                expected_materialized_contracts["continuation"][
                    "resume_node_id"
                ] = latest_checkpoint_details["resume_node_id"]
            if (
                run["contracts"] != expected_materialized_contracts
                or run.get("labels")
                != activation["event"]["details"].get("labels")
            ):
                raise ProcessDelegationIntegrityError(
                    "materialized delegation differs from its authorization"
                )
            if positioning is not None:
                positioning_details = positioning["event"]["details"]
                if (
                    checkpoint is None
                    or positioning["sequence"] <= checkpoint["sequence"]
                    or positioning_details.get("to_node_id") != "execute-preflight"
                    or positioning_details.get("advance_kind") != "decision"
                    or positioning_details.get("route") != {
                        "condition": "prg_run",
                        "matched": True,
                        "default_used": False,
                    }
                ):
                    raise ProcessDelegationIntegrityError(
                        "delegation did not follow its exact declared PRG-Run route"
                    )
            if run["current_node_id"] != "post-plan-mode" and positioning is None:
                raise ProcessDelegationIntegrityError(
                    "delegation left the approval boundary without its exact route"
                )
        status = "not_delegated"
        if latest is not None and latest["kind"] == "programming_delegation_withheld":
            status = "withheld"
        if (
            activation is not None
            and checkpoint is not None
            and positioning is not None
        ):
            status = "delegated"
        elif activation is not None:
            status = "activation_incomplete"
        return {
            "schema_version": DELEGATION_SCHEMA_VERSION,
            "dialogue_ref": dialogue_ref,
            "run_id": run["run_id"],
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "binding_digest": plan_state["binding_digest"],
            "plan_ref": _plan_ref(plan_state["current_plan"]),
            "status": status,
            "observation": copy.deepcopy(latest),
            "activation_record_id": activation["record_id"] if activation else None,
            "run_state": run["state"],
            "current_node_id": run["current_node_id"],
            "phase_2_5_authorized": False,
        }

    def _record(
        self,
        dialogue_ref: str,
        plan_state: Mapping[str, Any],
        kind: str,
        payload: Mapping[str, Any],
    ) -> None:
        self.runtime._record_dialogue_observation(
            plan_state["run_id"],
            dialogue_ref=dialogue_ref,
            binding_digest=plan_state["binding_digest"],
            observation_type=kind,
            payload=payload,
        )

    def delegate(
        self,
        dialogue_ref: str,
        *,
        plan_ref: Mapping[str, Any],
        approval_receipt_digest: str,
        requested_by: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Authorize and position one exact approved Run for execution."""

        key = _stable_id(idempotency_key, field="delegation idempotency_key")
        principal = _stable_id(requested_by, field="delegation principal")
        approval_digest = _exact_digest(
            approval_receipt_digest, field="approval_receipt_digest"
        )
        with _DELEGATION_LOCK:
            state = self.plan_service.get_state(dialogue_ref)
            if state is None or state.get("status") != "approved":
                raise ProcessDelegationConflict(
                    "delegation requires one exact committed approved plan"
                )
            plan = state["current_plan"]
            approval = state["approval"]
            exact_plan_ref = _plan_ref(plan)
            if dict(plan_ref) != exact_plan_ref:
                raise ProcessDelegationConflict(
                    "delegation does not bind the current approved plan"
                )
            if approval_digest != _digest_json(approval):
                raise ProcessDelegationConflict(
                    "delegation approval receipt identity is stale"
                )
            if principal != approval["decision_by"]:
                raise AuthorityDeniedError(
                    "only the approving Run principal may delegate execution"
                )

            prior = self._observations(
                dialogue_ref, state["run_id"], state["binding_digest"]
            )
            authorizations = [
                item for item in prior
                if item["kind"] == "programming_delegation_authorized"
            ]
            if len(authorizations) > 1:
                raise ProcessDelegationIntegrityError(
                    "approved plan has multiple delegation authorizations"
                )
            if authorizations:
                authorized_payload = authorizations[0]["payload"]
                if prior[-1] != authorizations[0]:
                    raise ProcessDelegationIntegrityError(
                        "delegation authorization was superseded by an invalid observation"
                    )
                if authorized_payload.get("idempotency_key") != key:
                    raise ProcessDelegationConflict(
                        "the approved plan already has a different delegation identity"
                    )
                if (
                    authorized_payload.get("plan_ref") != exact_plan_ref
                    or authorized_payload.get("approval_receipt_digest")
                    != approval_digest
                    or authorized_payload.get("requested_by") != principal
                ):
                    raise ProcessDelegationIntegrityError(
                        "persisted delegation authorization has drifted"
                    )
                existing = self.get_delegation(dialogue_ref)
                if existing is not None and existing["status"] == "delegated":
                    return existing

            current = capture_target_identity(
                plan["repository_artifact_scope"]["target"]["locator"]["ref"],
                captured_at=self._now(),
            )
            expected_baseline = plan["repository_artifact_scope"]["target"][
                "identity"
            ]["digest"]
            current_baseline = current["identity"]["digest"]
            matching = [
                item for item in prior
                if item["payload"].get("idempotency_key") == key
            ]
            if len(matching) > 1:
                raise ProcessDelegationIntegrityError(
                    "delegation idempotency identity is duplicated"
                )

            if current_baseline != expected_baseline:
                withheld_body = {
                    "schema_version": DELEGATION_SCHEMA_VERSION,
                    "idempotency_key": key,
                    "plan_ref": exact_plan_ref,
                    "approval_receipt_digest": approval_digest,
                    "requested_by": principal,
                    "condition": "approved_baseline_stale",
                    "expected_baseline_digest": expected_baseline,
                    "current_baseline_digest": current_baseline,
                    "required_decision": (
                        "Revise and approve a new plan against the current target baseline."
                    ),
                }
                withheld = {
                    **withheld_body,
                    "withholding_digest": _digest_json(withheld_body),
                }
                if matching:
                    if (
                        matching[0]["kind"] != "programming_delegation_withheld"
                        or matching[0]["payload"] != withheld
                    ):
                        raise ProcessDelegationConflict(
                            "delegation retry identity conflicts with persisted withholding"
                        )
                else:
                    self._record(
                        dialogue_ref, state,
                        "programming_delegation_withheld", withheld,
                    )
                return self.get_delegation(dialogue_ref)  # type: ignore[return-value]

            authorization_body = {
                "schema_version": DELEGATION_SCHEMA_VERSION,
                "idempotency_key": key,
                "dialogue_ref": dialogue_ref,
                "run_id": state["run_id"],
                "binding_digest": state["binding_digest"],
                "plan_ref": exact_plan_ref,
                "approval_receipt_digest": approval_digest,
                "approval_decision": approval["decision"],
                "requested_by": principal,
                "target_baseline_digest": current_baseline,
                "target_binding": {
                    "locator": copy.deepcopy(
                        plan["repository_artifact_scope"]["target"]["locator"]
                    ),
                    "baseline_identity_digest": current_baseline,
                },
            }
            delegation_digest = _digest_json(authorization_body)
            contracts = _execution_contracts(
                plan, approval, delegation_digest=delegation_digest
            )
            authorized = {
                **authorization_body,
                "delegation_digest": delegation_digest,
                "contracts": contracts,
                "contracts_digest": _digest_json(contracts),
            }
            if matching:
                if (
                    matching[0]["kind"] != "programming_delegation_authorized"
                    or matching[0]["payload"] != authorized
                ):
                    raise ProcessDelegationConflict(
                        "delegation retry identity conflicts with persisted authorization"
                    )
            else:
                self._record(
                    dialogue_ref, state,
                    "programming_delegation_authorized", authorized,
                )

            labels = [
                "management-interview", "phase-2.3", "plan:approved",
                "phase-2.4", "delegated",
            ]
            self.runtime._activate_approved_delegation(
                state["run_id"],
                contracts,
                plan_ref=exact_plan_ref,
                approval_receipt_digest=approval_digest,
                delegation_digest=delegation_digest,
                target_binding=authorization_body["target_binding"],
                idempotency_key=key,
                labels=labels,
            )
            checkpoint_id = _delegation_checkpoint_id(delegation_digest)
            checkpoint = next(
                (
                    record for record in self.runtime.load_records(state["run_id"])
                    if (record.get("event") or {}).get("event_type")
                    == "checkpoint_created"
                    and (record["event"].get("details") or {}).get("checkpoint_id")
                    == checkpoint_id
                ),
                None,
            )
            if checkpoint is None:
                self.runtime.create_checkpoint(
                    state["run_id"], checkpoint_id,
                    segment_id="phase-2.4-delegated-execution",
                    resume_node_id="execute-preflight",
                )
            run = self.runtime.load_run(state["run_id"])
            if run["current_node_id"] == "post-plan-mode":
                self.runtime.advance_decision(
                    state["run_id"], "prg_run",
                    reason=(
                        "The exact approved plan is delegated; begin at the declared "
                        "preflight without performing a target action."
                    ),
                )
            delegated = self.get_delegation(dialogue_ref)
            if (
                delegated is None
                or delegated["status"] != "delegated"
                or delegated["current_node_id"] != "execute-preflight"
            ):
                raise ProcessDelegationIntegrityError(
                    "delegation did not reach its exact persisted execution boundary"
                )
            return delegated

    def capture_repository_state(
        self,
        dialogue_ref: str,
        *,
        artifact_id: str,
        phase: str,
    ) -> dict[str, Any]:
        """Capture the approved target itself at the current mutation node."""

        with _DELEGATION_LOCK:
            delegated = self.get_delegation(dialogue_ref)
            plan_state = self.plan_service.get_state(dialogue_ref)
            if (
                delegated is None
                or delegated.get("status") != "delegated"
                or plan_state is None
                or plan_state.get("current_plan") is None
            ):
                raise ProcessDelegationIntegrityError(
                    "repository capture requires one active approved delegation"
                )
            run = self.runtime.load_run(plan_state["run_id"])
            definition = self.runtime.load_definition(plan_state["run_id"])
            node = {
                item["node_id"]: item for item in definition["graph"]["nodes"]
            }[run["current_node_id"]]
            if (
                node["kind"] != "action"
                or node["external_effect"] is not True
                or node["operation"] not in {
                    "execute_approved_programming_step",
                    "correct_programming_defect",
                }
            ):
                raise AuthorityDeniedError(
                    "approved repository capture requires the exact mutation node"
                )
            plan = plan_state["current_plan"]
            target = plan["repository_artifact_scope"]["target"]
            capture = capture_target_identity(
                target["locator"]["ref"], captured_at=self._now()
            )
            if capture["locator"] != target["locator"]:
                raise ProcessDelegationIntegrityError(
                    "captured repository locator differs from the approved target"
                )
            conditions = next(
                grant["conditions"]
                for grant in run["contracts"]["authority"]["grants"]
                if "record_programming_mutation_receipt" in grant["actions"]
            )
            return self.runtime._record_repository_state_capture(
                run["run_id"], artifact_id, capture,
                phase=phase,
                satisfied_conditions=conditions,
            )

    def issue_repository_mutation_receipt(
        self,
        dialogue_ref: str,
        *,
        artifact_id: str,
        pre_state_artifact_id: str,
        post_state_artifact_id: str,
    ) -> dict[str, Any]:
        """Issue a receipt only for the exact authenticated target transition."""

        with _DELEGATION_LOCK:
            delegated = self.get_delegation(dialogue_ref)
            plan_state = self.plan_service.get_state(dialogue_ref)
            if (
                delegated is None
                or delegated.get("status") != "delegated"
                or plan_state is None
            ):
                raise ProcessDelegationIntegrityError(
                    "repository receipt requires one active approved delegation"
                )
            run = self.runtime.load_run(plan_state["run_id"])
            conditions = next(
                grant["conditions"]
                for grant in run["contracts"]["authority"]["grants"]
                if "record_programming_mutation_receipt" in grant["actions"]
            )
            return self.runtime._issue_repository_mutation_receipt(
                run["run_id"], artifact_id,
                pre_state_artifact_id=pre_state_artifact_id,
                post_state_artifact_id=post_state_artifact_id,
                satisfied_conditions=conditions,
            )

    @staticmethod
    def _parse_time(value: str, *, field: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProcessDelegationIntegrityError(f"{field} is invalid") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_unread(self, dialogue_ref: str, recorded_at: str) -> bool:
        if not dialogue_ref:
            return True
        envelope = _memory.load_conversation_json(
            dialogue_ref, sessions_root=self.sessions_root
        )
        if envelope is None:
            return True
        last_read = envelope.get("last_read_at")
        if not last_read:
            return True
        return self._parse_time(recorded_at, field="attention recorded_at") > self._parse_time(
            str(last_read), field="Dialogue last_read_at"
        )

    def _run_row(self, run: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        run_id = str(run["run_id"])
        definition = self.runtime.load_definition(run_id)
        records = self.runtime.load_records(run_id)
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        node = nodes.get(run["current_node_id"])
        if node is None:
            raise ProcessDelegationIntegrityError(
                f"Process Run {run_id} current node is unavailable"
            )
        dialogue_ref = str(run.get("input_bindings", {}).get("dialogue_ref") or "")
        objective = str(run["contracts"]["approved_plan"]["objective"] or "")
        row = {
            "run_id": run_id,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "dialogue_ref": dialogue_ref,
            "title": objective or str(definition["title"]),
            "project_ref": str(run.get("input_bindings", {}).get("project_ref") or ""),
            "run_state": run["state"],
            "current_node_id": run["current_node_id"],
            "current_step": str(node.get("label") or run["current_node_id"]),
            "updated_at": run["updated_at"],
            "quiet": True,
            "needs_attention": False,
            "visible_status": "Operating",
            "attention": None,
        }
        latest_attention_record = None
        delegation_observations = []
        activation_records = []
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") == "delegation_activated":
                activation_records.append(record)
                continue
            observation_type = str(details.get("observation_type") or "")
            if (
                event.get("event_type") != "dialogue_observation_recorded"
                or not observation_type.startswith(DELEGATION_OBSERVATION_PREFIX)
            ):
                continue
            payload = details.get("payload")
            if (
                not dialogue_ref
                or details.get("dialogue_ref") != dialogue_ref
                or not isinstance(payload, dict)
                or details.get("payload_digest") != _digest_json(payload)
            ):
                raise ProcessDelegationIntegrityError(
                    f"Process Run {run_id} has an invalid delegation observation"
                )
            delegation_observations.append((record, observation_type, payload))
        delegation_state = None
        if delegation_observations:
            delegation_state = self.get_delegation(dialogue_ref)
            if (
                delegation_state is None
                or delegation_state["run_id"] != run_id
            ):
                raise ProcessDelegationIntegrityError(
                    f"Process Run {run_id} delegation lacks its exact plan lifecycle"
                )
        if len(activation_records) > 1:
            raise ProcessDelegationIntegrityError(
                f"Process Run {run_id} has multiple delegation activations"
            )
        if activation_records and (
            not delegation_observations
            or delegation_observations[-1][1]
            != "programming_delegation_authorized"
        ):
            raise ProcessDelegationIntegrityError(
                f"Process Run {run_id} delegation activation lacks authorization"
            )
        if activation_records:
            activation_details = activation_records[0]["event"]["details"]
            authorization_payload = delegation_observations[-1][2]
            if (
                activation_details.get("delegation_digest")
                != authorization_payload.get("delegation_digest")
                or activation_details.get("approval_receipt_digest")
                != authorization_payload.get("approval_receipt_digest")
                or activation_details.get("plan_ref")
                != authorization_payload.get("plan_ref")
                or activation_details.get("idempotency_key")
                != authorization_payload.get("idempotency_key")
                or activation_details.get("contracts")
                != authorization_payload.get("contracts")
                or authorization_payload.get("contracts_digest")
                != _digest_json(authorization_payload.get("contracts"))
            ):
                raise ProcessDelegationIntegrityError(
                    f"Process Run {run_id} delegation identity has drifted"
                )

        incomplete_delegation = None
        if delegation_observations and not activation_records:
            incomplete_delegation = delegation_observations[-1]
        elif (
            delegation_observations
            and activation_records
            and delegation_state is not None
            and delegation_state["status"] == "activation_incomplete"
        ):
            incomplete_delegation = (
                records[-1],
                "programming_delegation_activation_incomplete",
                delegation_observations[-1][2],
            )

        if incomplete_delegation is not None:
            latest_attention_record, observation_type, payload = incomplete_delegation
            if observation_type == "programming_delegation_withheld":
                evidence_refs = [
                    payload["expected_baseline_digest"],
                    payload["current_baseline_digest"],
                ]
                visible_status = "Waiting for You"
                condition = str(payload["condition"])
                required_decision = str(payload["required_decision"])
            elif observation_type in {
                "programming_delegation_authorized",
                "programming_delegation_activation_incomplete",
            }:
                evidence_refs = [
                    str(payload["delegation_digest"]),
                    str(payload["approval_receipt_digest"]),
                    str(payload["target_baseline_digest"]),
                ]
                visible_status = "Blocked"
                condition = "delegation_activation_incomplete"
                required_decision = (
                    "Retry the exact delegation request so activation can resume "
                    "from its persisted authorization."
                )
            else:
                raise ProcessDelegationIntegrityError(
                    f"Process Run {run_id} has an unknown delegation observation"
                )
            row.update({
                "quiet": False,
                "needs_attention": True,
                "visible_status": visible_status,
                "attention": {
                    "kind": "decision" if visible_status == "Waiting for You" else "blocked",
                    "condition": condition,
                    "evidence_refs": evidence_refs,
                    "required_decision": required_decision,
                },
            })
        elif run["state"] == "waiting_for_authority":
            latest_attention_record = next(
                (
                    record for record in reversed(records)
                    if (record.get("transition") or {}).get("directive") == "ESCALATE"
                ),
                None,
            )
            if latest_attention_record is None:
                raise ProcessDelegationIntegrityError(
                    f"Process Run {run_id} waits for authority without a request"
                )
            transition = latest_attention_record["transition"]
            request = transition["authority_request"]
            row.update({
                "quiet": False,
                "needs_attention": True,
                "visible_status": "Waiting for You",
                "attention": {
                    "kind": "decision",
                    "condition": transition["reason"],
                    "evidence_refs": copy.deepcopy(latest_attention_record["evidence_refs"]),
                    "required_decision": {
                        "request_id": request["request_id"],
                        "request_type": request["request_type"],
                        "requested_authority": request["requested_authority"],
                        "options": request["options"],
                        "resume_node_id": request["resume_node_id"],
                    },
                },
            })
        elif run["state"] == "blocked":
            latest_attention_record = next(
                (
                    record for record in reversed(records)
                    if (record.get("transition") or {}).get("directive") == "BLOCKED"
                ),
                None,
            )
            if latest_attention_record is None:
                raise ProcessDelegationIntegrityError(
                    f"blocked Process Run {run_id} lacks its transition condition"
                )
            transition = latest_attention_record["transition"]
            row.update({
                "quiet": False,
                "needs_attention": True,
                "visible_status": "Blocked",
                "attention": {
                    "kind": "blocked",
                    "condition": transition["reason"],
                    "evidence_refs": copy.deepcopy(latest_attention_record["evidence_refs"]),
                    "required_decision": (
                        "Provide the missing authority or evidence, revise scope, or start a replacement Run."
                    ),
                },
            })
        elif run["state"] == "completed":
            latest_attention_record = next(
                (
                    record for record in reversed(records)
                    if (record.get("transition") or {}).get("directive") == "ACCEPT"
                ),
                None,
            )
            if latest_attention_record is None:
                raise ProcessDelegationIntegrityError(
                    f"completed Process Run {run_id} lacks exact ACCEPT evidence"
                )
            results = []
            for artifact_id in run["artifact_ids"]:
                artifact = self.runtime.load_artifact(run_id, artifact_id)
                if artifact["role"] == "result":
                    results.append({
                        "artifact_id": artifact_id,
                        "identity_digest": artifact["identity"]["digest"],
                        "media_type": artifact["media_type"],
                        "locator": copy.deepcopy(artifact["locator"]),
                    })
            if not results:
                raise ProcessDelegationIntegrityError(
                    f"completed Process Run {run_id} has no exact result Artifact"
                )
            row.update({
                "quiet": False,
                "needs_attention": True,
                "visible_status": "Completed",
                "attention": {
                    "kind": "result",
                    "condition": latest_attention_record["transition"]["reason"],
                    "evidence_refs": copy.deepcopy(latest_attention_record["evidence_refs"]),
                    "result_artifacts": results,
                    "required_decision": "Review the returned result.",
                },
            })
        elif node["kind"] == "human_checkpoint":
            latest_attention_record = next(
                (
                    record for record in reversed(records)
                    if (
                        (record.get("transition") or {}).get("target_node_id")
                        == run["current_node_id"]
                        or (
                            (record.get("event") or {}).get("event_type")
                            == "node_advanced"
                            and ((record.get("event") or {}).get("details") or {}).get(
                                "to_node_id"
                            ) == run["current_node_id"]
                        )
                        or (
                            (record.get("event") or {}).get("event_type")
                            == "run_created"
                            and record.get("node_id") == run["current_node_id"]
                        )
                    )
                ),
                None,
            )
            if latest_attention_record is None:
                raise ProcessDelegationIntegrityError(
                    f"Process Run {run_id} lacks its human-checkpoint entry record"
                )
            row.update({
                "quiet": False,
                "needs_attention": True,
                "visible_status": "Waiting for You",
                "attention": {
                    "kind": "decision",
                    "condition": str(node.get("label") or "Human authority is required."),
                    "evidence_refs": copy.deepcopy(latest_attention_record["evidence_refs"]),
                    "required_decision": {
                        "request_type": node["authority_request_type"],
                        "options": ["approve", "deny", "discuss"],
                    },
                },
            })
        elif run["state"] == "pending":
            row["visible_status"] = "Paused"
        elif run["state"] == "redefining":
            row["visible_status"] = "Redefining"
        elif run["state"] in {"created", "awaiting_plan_approval", "ready"}:
            row["visible_status"] = "Preparing"

        if latest_attention_record is not None:
            attention_body = {
                "run_id": run_id,
                "record_id": latest_attention_record["record_id"],
                "kind": row["attention"]["kind"],
            }
            row["attention_id"] = _digest_json(attention_body)
            row["attention_recorded_at"] = latest_attention_record["recorded_at"]
        else:
            row["attention_id"] = None
            row["attention_recorded_at"] = None
        row["row_digest"] = _digest_json(row)
        unread = bool(
            row["needs_attention"]
            and latest_attention_record is not None
            and self._is_unread(dialogue_ref, latest_attention_record["recorded_at"])
        )
        return row, unread

    def _iter_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for entry in sorted(self.runtime.root.iterdir()):
            if entry.is_symlink() or not entry.is_dir():
                raise ProcessDelegationIntegrityError(
                    f"invalid Process Run storage entry: {entry}"
                )
            run_path = entry / "run.json"
            if not run_path.is_file() or run_path.is_symlink():
                raise ProcessDelegationIntegrityError(
                    f"Process Run storage entry lacks a real run.json: {entry}"
                )
            try:
                raw = json.loads(run_path.read_text(encoding="utf-8"))
                run_id = str(raw["run_id"])
                run = self.runtime.load_run(run_id)
            except (OSError, KeyError, ValueError, json.JSONDecodeError, GovernedRuntimeError) as exc:
                raise ProcessDelegationIntegrityError(
                    f"Process Run storage integrity failed at {entry}"
                ) from exc
            expected_entry = self.runtime._run_dir(run_id)
            if entry != expected_entry:
                raise ProcessDelegationIntegrityError(
                    "Process Run storage path differs from its declared identity"
                )
            runs.append(run)
        return runs

    def _automated_definitions(self) -> list[dict[str, Any]]:
        """Authenticate the registry without inventing deployment state.

        The accepted exact-version registry is discovery-only: every
        registration receipt explicitly records ``activated: false``, even if
        a submitted definition self-declares an ``active`` status or standing
        labels. Phase 2.4 therefore projects no Automated Process from registry
        content alone. Phase 2.6 may later add an independently authorized,
        persisted activation/deployment record; this phase neither creates nor
        anticipates that record's schema.
        """

        try:
            refs = self.registry.list_definition_refs()
            for ref in refs:
                self.registry.resolve(
                    ref["definition_id"], ref["version"], ref["digest"]
                )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessDelegationIntegrityError(
                "Automated Processes registry integrity failed"
            ) from exc
        return []

    def projection(self) -> dict[str, Any]:
        """Return one authenticated, restart-derived management projection."""

        pending: list[dict[str, Any]] = []
        unread: list[dict[str, Any]] = []
        for run in self._iter_runs():
            row, is_unread = self._run_row(run)
            if run["state"] not in TERMINAL_RUN_STATES:
                pending.append(row)
            if is_unread:
                unread.append(copy.deepcopy(row))
        pending.sort(key=lambda item: item["updated_at"], reverse=True)
        unread.sort(key=lambda item: item["attention_recorded_at"] or "", reverse=True)
        body = {
            "schema_version": ATTENTION_SCHEMA_VERSION,
            "generated_at": self._now(),
            "pending": pending,
            "automated_processes": self._automated_definitions(),
            "unread": unread,
            "phase_2_5_authorized": False,
        }
        return {**body, "projection_digest": _digest_json(body)}


__all__ = [
    "ATTENTION_SCHEMA_VERSION",
    "DELEGATION_SCHEMA_VERSION",
    "ProcessDelegationAttentionService",
    "ProcessDelegationConflict",
    "ProcessDelegationError",
    "ProcessDelegationInputRequired",
    "ProcessDelegationIntegrityError",
]
