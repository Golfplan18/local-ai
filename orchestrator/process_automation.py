"""G1.18 automated Process authoring and isolated execution.

This module is deliberately an adapter over the accepted G1.1 objects.  It
does not own a second process state machine: definitions are validated by
``process_contracts``, registered by ``ProcessDefinitionRegistry``, Runs are
advanced only by ``GovernedProcessRuntime``, and availability is conferred only
by ``ProcessLibraryLifecycleService``.

The older Project Integration Program described Trigger, Model Profile, and
Style fields on a Process Definition and execution through
``milestone_executor``.  The issued G1.1 contract does not permit those root
fields.  G1.18 therefore keeps model/style selection in the exact Run input
binding, leaves Trigger to G1.19, and uses a separate no-tools worker only as an
actuator for a G1.1 action node.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from . import process_contracts as contracts
    from . import project_meta
    from .governed_process_runtime import (
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
    )
    from .model_profiles import ModelProfileError, resolve_effective_profile
    from .process_definition_registry import (
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
        process_definition_content_digest,
    )
    from .process_library_lifecycle import (
        ProcessLibraryError,
        ProcessLibraryLifecycleService,
    )
    from .process_management_interview import (
        ManagementInterviewError,
        ManagementInterviewService,
    )
    from .runtime_paths import atomic_write_text
except ImportError:  # pragma: no cover - direct module execution/tests
    import process_contracts as contracts  # type: ignore
    import project_meta  # type: ignore
    from governed_process_runtime import (  # type: ignore
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
    )
    from model_profiles import ModelProfileError, resolve_effective_profile  # type: ignore
    from process_definition_registry import (  # type: ignore
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
        process_definition_content_digest,
    )
    from process_library_lifecycle import (  # type: ignore
        ProcessLibraryError,
        ProcessLibraryLifecycleService,
    )
    from process_management_interview import (  # type: ignore
        ManagementInterviewError,
        ManagementInterviewService,
    )
    from runtime_paths import atomic_write_text  # type: ignore


AUTOMATION_SCHEMA_VERSION = "ora.process-automation/1.0"
BLUEPRINT_SCHEMA_VERSION = "ora.process-blueprint/1.0"
WORKER_SCHEMA_VERSION = "ora.process-worker-request/1.0"
AUTHORING_PROPOSED_EVENT = "automation_authoring_proposed"
AUTHORING_REVISION_EVENT = "automation_authoring_revision_requested"
CONDITIONS = ["approved_plan_digest_matches"]
INPUT_SELECTOR = "scope:declared_inputs"
OUTPUT_SELECTOR = "scope:declared_outputs"
DEFINITION_SELECTOR = "scope:process_definition"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]*$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_EXTERNAL_OPERATION_RE = re.compile(
    r"(?:send|publish|upload|delete|remove|write[_-]?(?:file|repo)|mutate|"
    r"commit|push|message|email[_-]?send|activate|schedule|trigger)",
    flags=re.IGNORECASE,
)


class ProcessAutomationError(RuntimeError):
    """Base class for G1.18 input, authority, and execution refusals."""


class ProcessAutomationInputRequired(ProcessAutomationError):
    pass


class ProcessAutomationConflict(ProcessAutomationError):
    pass


class ProcessAutomationIntegrityError(ProcessAutomationError):
    pass


class ProcessAutomationWorkerError(ProcessAutomationError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    return _digest_text(_canonical_json(value))


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def _safe_id(value: str, label: str) -> str:
    result = str(value or "").strip().lower()
    if not _ID_RE.fullmatch(result):
        raise ProcessAutomationInputRequired(f"{label} must be a stable lowercase identifier")
    return result


def _safe_text(value: Any, label: str, *, limit: int = 20_000) -> str:
    result = " ".join(str(value or "").split())
    if not result:
        raise ProcessAutomationInputRequired(f"{label} must be non-empty")
    if len(result) > limit:
        raise ProcessAutomationInputRequired(f"{label} exceeds {limit} characters")
    return result


def _seal_definition(definition: Mapping[str, Any]) -> dict[str, Any]:
    """Bind normalized JSON content while preserving G1.1's self-reference rule."""

    out = copy.deepcopy(dict(definition))
    placeholder = "sha256:" + ("0" * 64)
    out["digest"] = placeholder
    manifest = out["package_manifest"]
    manifest["definition_ref"] = {
        "definition_id": out["definition_id"],
        "version": out["version"],
        "digest": placeholder,
    }
    entry = next(
        item for item in manifest["members"]
        if item["member_id"] == manifest["entry_member_id"]
    )
    entry["identity"]["digest"] = placeholder
    digest = process_definition_content_digest(out)
    out["digest"] = digest
    manifest["definition_ref"]["digest"] = digest
    entry["identity"]["digest"] = digest
    contracts.validate_process_definition(out)
    return out


def _normalize_json_schema(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProcessAutomationInputRequired(f"{label} must be an object schema")
    schema = copy.deepcopy(dict(value))
    if schema.get("type") != "object":
        raise ProcessAutomationInputRequired(f"{label}.type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        raise ProcessAutomationInputRequired(f"{label}.properties must be non-empty")
    clean_properties: dict[str, Any] = {}
    for raw_name, raw_property in properties.items():
        name = str(raw_name)
        if not _FIELD_RE.fullmatch(name) or not isinstance(raw_property, Mapping):
            raise ProcessAutomationInputRequired(
                f"{label} contains an invalid field declaration: {name!r}"
            )
        prop = copy.deepcopy(dict(raw_property))
        if prop.get("type") not in {"string", "number", "integer", "boolean", "object", "array"}:
            raise ProcessAutomationInputRequired(
                f"{label}.{name}.type is unsupported"
            )
        clean_properties[name] = prop
    required = schema.get("required", [])
    if not isinstance(required, list) or any(item not in clean_properties for item in required):
        raise ProcessAutomationInputRequired(f"{label}.required references an unknown field")
    if len(required) != len(set(required)):
        raise ProcessAutomationInputRequired(f"{label}.required contains duplicates")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": clean_properties,
        "required": list(required),
    }


def validate_blueprint(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the G1.18 authoring result before it can become a definition."""

    if not isinstance(value, Mapping):
        raise ProcessAutomationInputRequired("process blueprint must be an object")
    allowed = {
        "schema_version", "definition_id", "version", "title", "purpose",
        "project_ref", "input_schema", "output_schema", "stages",
        "acceptance_criteria", "max_attempts", "labels",
    }
    if set(value) != allowed:
        missing = sorted(allowed - set(value))
        extra = sorted(set(value) - allowed)
        bits = []
        if missing:
            bits.append("missing " + ", ".join(missing))
        if extra:
            bits.append("unsupported " + ", ".join(extra))
        raise ProcessAutomationInputRequired("process blueprint fields are invalid: " + "; ".join(bits))
    if value.get("schema_version") != BLUEPRINT_SCHEMA_VERSION:
        raise ProcessAutomationInputRequired("unsupported process blueprint schema")
    definition_id = _safe_id(str(value["definition_id"]), "definition_id")
    if not definition_id.startswith("user/"):
        raise ProcessAutomationInputRequired("authored Process definition_id must begin with user/")
    version = _safe_id(str(value["version"]), "version")
    title = _safe_text(value["title"], "title", limit=200)
    purpose = _safe_text(value["purpose"], "purpose", limit=2_000)
    project_ref = _safe_id(str(value["project_ref"]), "project_ref")
    input_schema = _normalize_json_schema(value["input_schema"], "input_schema")
    output_schema = _normalize_json_schema(value["output_schema"], "output_schema")
    raw_stages = value["stages"]
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ProcessAutomationInputRequired("stages must be a non-empty array")
    stages: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_operations: set[str] = set()
    seen_output_keys: set[str] = set()
    action_count = checkpoint_count = 0
    for index, raw_stage in enumerate(raw_stages):
        if not isinstance(raw_stage, Mapping):
            raise ProcessAutomationInputRequired(f"stages[{index}] must be an object")
        kind = str(raw_stage.get("kind") or "")
        node_id = _safe_id(str(raw_stage.get("node_id") or ""), f"stages[{index}].node_id")
        if node_id in seen or node_id in {"final-review", "accepted", "blocked"}:
            raise ProcessAutomationInputRequired(f"stages[{index}].node_id is duplicate or reserved")
        seen.add(node_id)
        if kind == "action":
            if set(raw_stage) != {"kind", "node_id", "label", "operation", "instruction", "output_key"}:
                raise ProcessAutomationInputRequired(
                    f"action stage {node_id!r} has missing or unsupported fields"
                )
            operation = _safe_id(str(raw_stage["operation"]), f"stages[{index}].operation")
            if _EXTERNAL_OPERATION_RE.search(operation):
                raise ProcessAutomationInputRequired(
                    f"action {operation!r} names an effect reserved beyond G1.18"
                )
            if operation in seen_operations:
                raise ProcessAutomationInputRequired(
                    f"action operation {operation!r} is duplicated"
                )
            seen_operations.add(operation)
            output_key = str(raw_stage["output_key"])
            if not _FIELD_RE.fullmatch(output_key) or output_key not in output_schema["properties"]:
                raise ProcessAutomationInputRequired(
                    f"action {node_id!r} output_key must name a declared output"
                )
            if output_key in seen_output_keys:
                raise ProcessAutomationInputRequired(
                    f"action output_key {output_key!r} is duplicated"
                )
            seen_output_keys.add(output_key)
            stages.append({
                "kind": "action",
                "node_id": node_id,
                "label": _safe_text(raw_stage["label"], f"stages[{index}].label", limit=240),
                "operation": operation,
                "instruction": _safe_text(raw_stage["instruction"], f"stages[{index}].instruction"),
                "output_key": output_key,
            })
            action_count += 1
        elif kind == "human_checkpoint":
            if set(raw_stage) != {"kind", "node_id", "label", "authority_request_type"}:
                raise ProcessAutomationInputRequired(
                    f"human checkpoint {node_id!r} has missing or unsupported fields"
                )
            stages.append({
                "kind": "human_checkpoint",
                "node_id": node_id,
                "label": _safe_text(raw_stage["label"], f"stages[{index}].label", limit=240),
                "authority_request_type": _safe_id(
                    str(raw_stage["authority_request_type"]),
                    f"stages[{index}].authority_request_type",
                ),
            })
            checkpoint_count += 1
        else:
            raise ProcessAutomationInputRequired(
                f"stages[{index}].kind must be action or human_checkpoint"
            )
    if action_count < 1 or checkpoint_count < 1:
        raise ProcessAutomationInputRequired(
            "an authored Process requires at least one action and one human checkpoint"
        )
    if stages[-1]["kind"] != "action":
        raise ProcessAutomationInputRequired("the final authored stage must produce the result")
    missing_outputs = sorted(set(output_schema["required"]) - seen_output_keys)
    if missing_outputs:
        raise ProcessAutomationInputRequired(
            "required outputs have no producing action: " + ", ".join(missing_outputs)
        )
    criteria = value["acceptance_criteria"]
    if not isinstance(criteria, list) or not criteria:
        raise ProcessAutomationInputRequired("acceptance_criteria must be non-empty")
    clean_criteria = [_safe_text(item, "acceptance criterion", limit=1_000) for item in criteria]
    if len(clean_criteria) != len(set(clean_criteria)):
        raise ProcessAutomationInputRequired("acceptance_criteria contains duplicates")
    max_attempts = value["max_attempts"]
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not (1 <= max_attempts <= 8):
        raise ProcessAutomationInputRequired("max_attempts must be an integer from 1 through 8")
    labels = value["labels"]
    if not isinstance(labels, list):
        raise ProcessAutomationInputRequired("labels must be an array")
    clean_labels = [_safe_id(str(item), "label") for item in labels]
    if len(clean_labels) != len(set(clean_labels)):
        raise ProcessAutomationInputRequired("labels contains duplicates")
    return {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "definition_id": definition_id,
        "version": version,
        "title": title,
        "purpose": purpose,
        "project_ref": project_ref,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "stages": stages,
        "acceptance_criteria": clean_criteria,
        "max_attempts": max_attempts,
        "labels": clean_labels,
    }


def compile_blueprint(value: Mapping[str, Any]) -> dict[str, Any]:
    """Compile one reviewed blueprint to the issued G1.1 definition schema."""

    blueprint = validate_blueprint(value)
    nodes: list[dict[str, Any]] = []
    operation_contracts: dict[str, dict[str, str]] = {}
    stages = blueprint["stages"]
    for index, stage in enumerate(stages):
        next_id = stages[index + 1]["node_id"] if index + 1 < len(stages) else "final-review"
        if stage["kind"] == "action":
            nodes.append({
                "node_id": stage["node_id"],
                "kind": "action",
                "label": stage["label"],
                "operation": stage["operation"],
                "next_node_id": next_id,
                "authority_grant_ids": ["process-execution"],
                "artifact_access": [INPUT_SELECTOR, OUTPUT_SELECTOR],
                "evidence_requirement_ids": ["result_verified"],
                "external_effect": False,
            })
            operation_contracts[stage["operation"]] = {
                "node_id": stage["node_id"],
                "instruction": stage["instruction"],
                "output_key": stage["output_key"],
            }
        else:
            nodes.append({
                "node_id": stage["node_id"],
                "kind": "human_checkpoint",
                "label": stage["label"],
                "authority_request_type": stage["authority_request_type"],
                "on_approved_node_id": next_id,
                "on_denied_node_id": "blocked",
                "on_unavailable_node_id": "blocked",
            })
    nodes.extend([
        {
            "node_id": "final-review",
            "kind": "verification_boundary",
            "label": "Independently verify the exact Process result",
            "evidence_requirement_ids": ["result_verified"],
            "routes": {"ACCEPT": "accepted", "REVISE": stages[-1]["node_id"], "BLOCKED": "blocked"},
        },
        {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
        {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
    ])
    output_schema = copy.deepcopy(blueprint["output_schema"])
    output_schema["x-ora-process"] = {
        "schema_version": AUTOMATION_SCHEMA_VERSION,
        "operation_contracts": operation_contracts,
        "acceptance_criteria": blueprint["acceptance_criteria"],
        "max_correction_attempts": blueprint["max_attempts"],
        "max_attempts": (
            sum(stage["kind"] == "action" for stage in stages)
            + blueprint["max_attempts"]
        ),
        "external_effects": False,
        "triggers": False,
    }
    definition_id = blueprint["definition_id"]
    version = blueprint["version"]
    placeholder = "sha256:" + ("0" * 64)
    definition = {
        "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_definition",
        "definition_id": definition_id,
        "version": version,
        "digest": placeholder,
        "title": blueprint["title"],
        "purpose": blueprint["purpose"],
        "status": "approved",
        "scope": {"kind": "project", "selector": blueprint["project_ref"]},
        "input_schema": blueprint["input_schema"],
        "output_schema": output_schema,
        "graph": {
            "schema_version": contracts.GRAPH_SCHEMA_VERSION,
            "graph_id": f"{definition_id}/{version}",
            "entry_node_id": stages[0]["node_id"],
            "nodes": nodes,
        },
        "package_manifest": {
            "schema_version": contracts.PACKAGE_SCHEMA_VERSION,
            "package_id": definition_id,
            "package_version": version,
            "definition_ref": {
                "definition_id": definition_id,
                "version": version,
                "digest": placeholder,
            },
            "entry_member_id": "definition",
            "members": [{
                "member_id": "definition",
                "role": "process_definition",
                "required": True,
                "media_type": "application/vnd.ora.process-definition+json",
                "locator": {"kind": "registry", "ref": f"processes/{definition_id}@{version}"},
                "identity": {
                    "kind": "content_digest",
                    "digest": placeholder,
                    "coverage": ["complete_content"],
                    "captured_at": "2026-01-01T00:00:00Z",
                    "fresh_until": "9999-12-31T23:59:59Z",
                },
            }],
        },
        "labels": sorted({"automated-process", *blueprint["labels"]}),
    }
    return _seal_definition(definition)


def email_processing_blueprint(project_ref: str = "ora") -> dict[str, Any]:
    """The bounded G1.18 worked proof: process an email, never send it."""

    return validate_blueprint({
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "definition_id": "user/email-processing",
        "version": "1.0.0",
        "title": "Email Processing",
        "purpose": "Classify and summarize one inbound email, then prepare a draft only after human review.",
        "project_ref": project_ref,
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "sender": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["message_id", "sender", "subject", "body"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "classification": {"type": "string"},
                "summary": {"type": "string"},
                "draft": {"type": "string"},
            },
            "required": ["classification", "summary", "draft"],
        },
        "stages": [
            {
                "kind": "action", "node_id": "classify", "label": "Classify the inbound email",
                "operation": "email.classify", "instruction": "Classify urgency and intent without changing or sending anything.",
                "output_key": "classification",
            },
            {
                "kind": "action", "node_id": "summarize", "label": "Summarize the email",
                "operation": "email.summarize", "instruction": "Produce a faithful concise summary of the exact inbound email.",
                "output_key": "summary",
            },
            {
                "kind": "human_checkpoint", "node_id": "draft-approval",
                "label": "Approve preparation of a reply draft; this does not authorize sending",
                "authority_request_type": "prepare_email_draft",
            },
            {
                "kind": "action", "node_id": "draft", "label": "Prepare an unsent reply draft",
                "operation": "email.draft", "instruction": "Prepare a reply draft. Do not send, publish, or contact anyone.",
                "output_key": "draft",
            },
        ],
        "acceptance_criteria": [
            "The classification and summary are grounded in the exact inbound message.",
            "The reply is explicitly an unsent draft.",
            "No outbound communication or external mutation occurred.",
        ],
        "max_attempts": 3,
        "labels": ["email", "proof"],
    })


def _base_contracts(
    definition: Mapping[str, Any],
    *,
    principal_id: str,
    max_attempts: int,
    plan_id: str,
    objective: str,
    selectors: Sequence[str],
    granted_actions: Sequence[str],
) -> dict[str, Any]:
    node_ids = [str(node["node_id"]) for node in definition["graph"]["nodes"]]
    verification_nodes = [
        node for node in definition["graph"]["nodes"]
        if node["kind"] == "verification_boundary"
    ]
    now = _utc_now()
    plan_body = {
        "plan_id": plan_id,
        "version": "1.0.0",
        "objective": objective,
        "approved_by": principal_id,
        "approved_at": now,
        "approved_node_ids": node_ids,
        "constraints": [
            "No external effects are authorized.",
            "Every action executes through the exact persisted Process Run node.",
        ],
        "non_goals": ["scheduling", "outbound communication", "Persona selection"],
    }
    plan_body["digest"] = _digest_json(plan_body)
    return {
        "approved_plan": plan_body,
        "authority": {
            "principal_id": principal_id,
            "grants": [{
                "grant_id": "process-execution",
                "actions": sorted(set(granted_actions)),
                "resource_selectors": sorted(set(selectors)),
                "effect_types": ["local_reversible"],
                "conditions": CONDITIONS,
            }],
            "reserved_actions": [
                "activate", "delete", "message", "publish", "schedule", "send",
            ],
        },
        "artifact_scope": {
            "read_selectors": sorted(set(selectors)),
            "write_selectors": sorted(set(selectors)),
            "external_effect_selectors": [],
        },
        "bounded_judgment": [{
            "judgment_id": f"judgment-{node['node_id']}",
            "node_id": node["node_id"],
            "verified_circumstances": [
                "The exact result and independent evidence identities are persisted.",
            ],
            "question": "Does the exact result satisfy every declared acceptance criterion?",
            "permitted_conclusions": ["criteria_met", "execution_defect", "blocked"],
            "permitted_directives": sorted(node["routes"]),
            "permitted_actions": ["evaluate_evidence"],
            "authority_grant_ids": ["process-execution"],
            "artifact_selectors": [OUTPUT_SELECTOR],
            "required_evidence_ids": ["result_verified"],
            "evaluator_boundary": f"review-{node['node_id']}",
            "stop_conditions": ["stale_evidence", "unsupported_result"],
            "return_node_id": node["node_id"],
            "escalation_request_types": [],
        } for node in verification_nodes],
        "evidence": {
            "requirements": [{
                "evidence_id": "result_verified",
                "claim": "The exact Process result satisfies every declared acceptance criterion.",
                "method": "isolated_worker_verification",
                "producer_independence": "independent_step",
                "artifact_selectors": [OUTPUT_SELECTOR],
                "freshness_seconds": 3600,
                "required": True,
            }],
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "recapture",
        },
        "correction_loop": {
            "max_attempts": max_attempts,
            "attempt": 0,
            "progress_evidence_required": True,
            "repeated_defect_limit": min(3, max_attempts),
            "allowed_directives": ["REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
            "no_progress_directives": ["REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
        },
        "continuation": {
            "checkpoint_id": "initial",
            "resume_node_id": definition["graph"]["entry_node_id"],
            "required_state_fields": ["current_node_id", "artifact_ids", "input_bindings"],
            "child_return_fields": [],
            "parent_run_id": None,
            "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "never_replay_effects",
            "checkpoint_ref": "checkpoint:initial",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": ["result_verified"],
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": ["authority_required", "attempt_ceiling", "worker_unavailable"],
            "blocked_conditions": ["identity_drift", "recovery_unsafe"],
            "authority_request_types": [],
            "authority_return_target": principal_id,
        },
    }


def _process_run(
    definition: Mapping[str, Any],
    *,
    run_id: str,
    entrypoint: str,
    principal_id: str,
    input_bindings: Mapping[str, Any],
    parent_run_id: str | None = None,
    constructed_definition_refs: Sequence[Mapping[str, Any]] = (),
    max_attempts: int = 3,
    selectors: Sequence[str] = (INPUT_SELECTOR, OUTPUT_SELECTOR),
    granted_actions: Sequence[str] = (
        "evaluate_evidence", "execute_process_step", "produce_artifact", "record_evidence",
    ),
) -> dict[str, Any]:
    now = _utc_now()
    contracts_value = _base_contracts(
        definition,
        principal_id=principal_id,
        max_attempts=max_attempts,
        plan_id=f"plan-{run_id}",
        objective=f"Execute exact Process Definition {_definition_ref(definition)}",
        selectors=selectors,
        granted_actions=granted_actions,
    )
    contracts_value["continuation"]["parent_run_id"] = parent_run_id
    run = {
        "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_run",
        "run_id": run_id,
        "definition_ref": _definition_ref(definition),
        "state": "created",
        "entrypoint": entrypoint,
        "current_node_id": definition["graph"]["entry_node_id"],
        "input_bindings": copy.deepcopy(dict(input_bindings)),
        "contracts": contracts_value,
        "relationships": {
            "parent_run_id": parent_run_id,
            "invoked_by_run_id": parent_run_id,
            "invoked_definition_refs": [],
            "constructed_definition_refs": [copy.deepcopy(dict(item)) for item in constructed_definition_refs],
            "return_to_run_id": parent_run_id,
        },
        "artifact_ids": [],
        "last_sequence": 0,
        "created_at": now,
        "updated_at": now,
        "labels": ["automated-process", "g1-18"],
    }
    contracts.validate_process_run(run)
    return run


def _construction_definition(target: Mapping[str, Any]) -> dict[str, Any]:
    target_ref = _definition_ref(target)
    blueprint = {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "definition_id": "ora/reusable-process-construction",
        "version": "1.0.0",
        "title": "Reusable Process Construction",
        "purpose": "Review, construct, register, and independently verify one exact reusable Process Definition.",
        "project_ref": "ora",
        "input_schema": {
            "type": "object",
            "properties": {"target_definition_ref": {"type": "object"}},
            "required": ["target_definition_ref"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"registration_receipt": {"type": "object"}},
            "required": ["registration_receipt"],
        },
        "stages": [],
        "acceptance_criteria": ["The exact reviewed definition is registered without activation."],
        "max_attempts": 3,
        "labels": ["construction"],
    }
    placeholder = "sha256:" + ("0" * 64)
    definition = {
        "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_definition",
        "definition_id": blueprint["definition_id"],
        "version": blueprint["version"],
        "digest": placeholder,
        "title": blueprint["title"],
        "purpose": blueprint["purpose"],
        "status": "approved",
        "scope": {"kind": "universal", "selector": "all"},
        "input_schema": {
            "type": "object",
            "properties": {"target_definition_ref": {"const": target_ref}},
            "required": ["target_definition_ref"],
        },
        "output_schema": blueprint["output_schema"],
        "graph": {
            "schema_version": contracts.GRAPH_SCHEMA_VERSION,
            "graph_id": "ora/reusable-process-construction/1.0.0",
            "entry_node_id": "review-definition",
            "nodes": [
                {
                    "node_id": "review-definition", "kind": "human_checkpoint",
                    "label": "Approve this exact reusable Process Definition",
                    "authority_request_type": "process_definition_approval",
                    "on_approved_node_id": "construct-definition",
                    "on_denied_node_id": "blocked", "on_unavailable_node_id": "blocked",
                },
                {
                    "node_id": "construct-definition", "kind": "action",
                    "label": "Construct the exact approved reusable Process Definition",
                    "operation": "construct_reusable_process_definition",
                    "next_node_id": "register-definition",
                    "authority_grant_ids": ["process-execution"],
                    "artifact_access": [DEFINITION_SELECTOR],
                    "evidence_requirement_ids": ["result_verified"],
                    "external_effect": False,
                },
                {
                    "node_id": "register-definition", "kind": "action",
                    "label": "Register the exact version without activation",
                    "operation": "register_reusable_process_definition",
                    "next_node_id": "final-review",
                    "authority_grant_ids": ["process-execution"],
                    "artifact_access": [DEFINITION_SELECTOR, OUTPUT_SELECTOR],
                    "evidence_requirement_ids": ["result_verified"],
                    "external_effect": False,
                },
                {
                    "node_id": "final-review", "kind": "verification_boundary",
                    "label": "Independently verify construction and registration",
                    "evidence_requirement_ids": ["result_verified"],
                    "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"},
                },
                {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
                {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
            ],
        },
        "package_manifest": {
            "schema_version": contracts.PACKAGE_SCHEMA_VERSION,
            "package_id": blueprint["definition_id"],
            "package_version": blueprint["version"],
            "definition_ref": {
                "definition_id": blueprint["definition_id"],
                "version": blueprint["version"], "digest": placeholder,
            },
            "entry_member_id": "definition",
            "members": [{
                "member_id": "definition", "role": "process_definition", "required": True,
                "media_type": "application/vnd.ora.process-definition+json",
                "locator": {"kind": "registry", "ref": "processes/ora/reusable-process-construction@1.0.0"},
                "identity": {
                    "kind": "content_digest", "digest": placeholder,
                    "coverage": ["complete_content"],
                    "captured_at": "2026-01-01T00:00:00Z", "fresh_until": "9999-12-31T23:59:59Z",
                },
            }],
        },
        "labels": ["construction", "g1-18"],
    }
    return _seal_definition(definition)


def _latest_result_artifact(runtime: GovernedProcessRuntime, run_id: str) -> dict[str, Any] | None:
    run = runtime.load_run(run_id)
    for artifact_id in reversed(run["artifact_ids"]):
        artifact = runtime.load_artifact(run_id, artifact_id)
        if artifact["role"] == "result":
            return artifact
    return None


def _json_type_ok(value: Any, declared: str) -> bool:
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "object":
        return isinstance(value, Mapping)
    if declared == "array":
        return isinstance(value, list)
    return False


def _validate_instance(value: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProcessAutomationInputRequired(f"{label} must be an object")
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = sorted(set(required) - set(value))
    extra = sorted(set(value) - set(properties)) if schema.get("additionalProperties") is False else []
    if missing or extra:
        raise ProcessAutomationInputRequired(
            f"{label} fields are invalid; missing={missing}, unsupported={extra}"
        )
    for name, item in value.items():
        if name in properties and not _json_type_ok(item, str(properties[name].get("type") or "")):
            raise ProcessAutomationInputRequired(f"{label}.{name} has the wrong type")
    return copy.deepcopy(dict(value))


class IsolatedProcessWorker:
    """Run one no-tools action in a separate process with an exact request."""

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout_seconds: int = 180,
        runner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ):
        self.command = list(command) if command else [
            sys.executable, str(Path(__file__).with_name("process_automation_worker.py")),
        ]
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def invoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(dict(request))
        if payload.get("schema_version") != WORKER_SCHEMA_VERSION:
            raise ProcessAutomationWorkerError("worker request schema is invalid")
        request_digest = _digest_json(payload)
        if self._runner is not None:
            raw = self._runner(copy.deepcopy(payload))
            boundary = "injected_test_worker"
        else:
            env = {
                key: value for key, value in os.environ.items()
                if key in {
                    "HOME", "PATH", "LANG", "LC_ALL", "ORA_HOME", "ORA_VAULT",
                    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
                }
            }
            env["ORA_PROCESS_WORKER"] = "1"
            try:
                completed = subprocess.run(
                    self.command,
                    input=_canonical_json(payload),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    cwd=str(Path(__file__).resolve().parents[1]),
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProcessAutomationWorkerError(
                    f"isolated worker unavailable: {type(exc).__name__}: {exc}"
                ) from exc
            if completed.returncode != 0:
                reason = completed.stderr.strip() or f"exit status {completed.returncode}"
                raise ProcessAutomationWorkerError(f"isolated worker failed: {reason[:1000]}")
            try:
                raw = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise ProcessAutomationWorkerError("isolated worker returned invalid JSON") from exc
            boundary = "separate_no_tools_process"
        if not isinstance(raw, Mapping):
            raise ProcessAutomationWorkerError("isolated worker result must be an object")
        required = {"status", "request_digest", "output", "report"}
        if set(raw) != required or raw.get("request_digest") != request_digest:
            raise ProcessAutomationWorkerError("isolated worker result does not bind the exact request")
        if raw.get("status") not in {"PASS", "FAIL"}:
            raise ProcessAutomationWorkerError("isolated worker status is invalid")
        result = copy.deepcopy(dict(raw))
        result["boundary"] = boundary
        result["response_digest"] = _digest_json(raw)
        return result


class ProcessAutomationService:
    """Author, register, promote, and execute reusable G1.1 Processes."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        registry: ProcessDefinitionRegistry | None = None,
        registry_root: str | Path | None = None,
        management_interview: ManagementInterviewService | None = None,
        library: ProcessLibraryLifecycleService | None = None,
        worker: IsolatedProcessWorker | None = None,
    ):
        self.runtime = runtime or GovernedProcessRuntime()
        self.registry = registry or ProcessDefinitionRegistry(registry_root)
        self.interview = management_interview or ManagementInterviewService(runtime=self.runtime)
        self.library = library or ProcessLibraryLifecycleService(
            runtime=self.runtime, registry_root=self.registry.root,
        )
        self.worker = worker or IsolatedProcessWorker()

    # ----------------------------------------------------------- authoring
    def _authoring_records(self, dialogue_ref: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        state = self.interview.get_state(dialogue_ref)
        if state is None:
            raise ProcessAutomationInputRequired("Dialogue has no management interview")
        if state["status"] != "ready_for_plan":
            raise ProcessAutomationInputRequired("management interview must be complete before authoring")
        records = [
            record for record in self.runtime.load_records(state["run_id"])
            if (record.get("event") or {}).get("event_type")
            in {AUTHORING_PROPOSED_EVENT, AUTHORING_REVISION_EVENT}
        ]
        return state, records

    def get_authoring(self, dialogue_ref: str) -> dict[str, Any]:
        interview, records = self._authoring_records(dialogue_ref)
        proposal_records = [
            record for record in records
            if record["event"]["event_type"] == AUTHORING_PROPOSED_EVENT
        ]
        latest = proposal_records[-1] if proposal_records else None
        proposal = None
        status = "ready_to_author"
        construction = None
        if latest is not None:
            details = latest["event"]["details"]
            required = {
                "schema_version", "proposal_id", "proposal_digest", "answers_digest",
                "definition", "definition_ref", "blueprint_digest", "idempotency_key",
                "execution_context", "worker_receipt",
            }
            if set(details) != required or details.get("schema_version") != AUTOMATION_SCHEMA_VERSION:
                raise ProcessAutomationIntegrityError("authoring proposal envelope is invalid")
            definition = contracts.validate_process_definition(details["definition"])
            if (
                details["definition_ref"] != _definition_ref(definition)
                or definition["digest"] != process_definition_content_digest(definition)
                or details["proposal_digest"] != _digest_json({
                    "answers_digest": details["answers_digest"],
                    "definition": definition,
                    "blueprint_digest": details["blueprint_digest"],
                    "execution_context": details["execution_context"],
                })
                or details["answers_digest"] != interview["answers_digest"]
            ):
                raise ProcessAutomationIntegrityError("authoring proposal identity is stale or forged")
            later_revisions = [
                record for record in records
                if int(record["sequence"]) > int(latest["sequence"])
                and record["event"]["event_type"] == AUTHORING_REVISION_EVENT
            ]
            status = "revision_requested" if later_revisions else "awaiting_definition_approval"
            proposal = copy.deepcopy(details)
            run_id = "process-construction-" + details["proposal_digest"].split(":", 1)[1][:32]
            try:
                run = self.runtime.load_run(run_id)
            except RunNotFoundError:
                run = None
            if run is not None:
                if (
                    run["input_bindings"].get("proposal_digest") != details["proposal_digest"]
                    or run["relationships"].get("parent_run_id") != interview["run_id"]
                ):
                    raise ProcessAutomationIntegrityError("construction Run does not bind the proposal")
                closure = self.library.get_run_lifecycle(run_id)
                construction = {
                    "run_id": run_id,
                    "run_state": run["state"],
                    "current_node_id": run["current_node_id"],
                    "lifecycle": closure,
                }
                if closure.get("closure", {}).get("disposition") == "promote":
                    status = "available"
                elif run["state"] == "completed":
                    status = "awaiting_promotion"
                else:
                    status = "constructing"
        return {
            "schema_version": AUTOMATION_SCHEMA_VERSION,
            "dialogue_ref": dialogue_ref,
            "management_run_id": interview["run_id"],
            "project_ref": interview["project_ref"],
            "answers_digest": interview["answers_digest"],
            "status": status,
            "proposal": proposal,
            "construction": construction,
            "persona_available": False,
            "trigger_created": False,
            "authority_effects": [],
        }

    def _default_author_blueprint(self, interview: Mapping[str, Any], *, project_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
        request = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "kind": "author",
            "operation": "author.process_definition",
            "instruction": (
                "Produce one deterministic, non-effectful Process blueprint from the exact "
                "management answers. Include at least one human checkpoint. Do not include "
                "triggers, scheduling, outbound communication, Persona, file mutation, or activation."
            ),
            "inputs": {"answers": interview["answers"], "project_ref": project_ref},
            "prior_outputs": {},
            "expected_output_key": "blueprint",
            "acceptance_criteria": ["The output conforms exactly to ora.process-blueprint/1.0."],
            "execution_context": {"config_name": None, "style_prompt": ""},
        }
        receipt = self.worker.invoke(request)
        if receipt["status"] != "PASS" or not isinstance(receipt["output"], Mapping):
            raise ProcessAutomationWorkerError("authoring worker did not produce a valid blueprint")
        output = receipt["output"]
        blueprint = output.get("blueprint") if isinstance(output.get("blueprint"), Mapping) else output
        return validate_blueprint(blueprint), receipt

    def propose(
        self,
        dialogue_ref: str,
        *,
        idempotency_key: str,
        blueprint: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = _safe_id(idempotency_key, "idempotency_key")
        interview, records = self._authoring_records(dialogue_ref)
        existing = [
            record for record in records
            if record["event"]["event_type"] == AUTHORING_PROPOSED_EVENT
            and record["event"]["details"].get("idempotency_key") == key
        ]
        if existing:
            return self.get_authoring(dialogue_ref)
        project_ref = _safe_id(interview["project_ref"], "project_ref")
        if blueprint is None:
            exact_blueprint, worker_receipt = self._default_author_blueprint(
                interview, project_ref=project_ref,
            )
        else:
            exact_blueprint = validate_blueprint(blueprint)
            worker_receipt = {
                "boundary": "principal_supplied_blueprint",
                "request_digest": _digest_json({"answers_digest": interview["answers_digest"]}),
                "response_digest": _digest_json(exact_blueprint),
                "status": "PASS",
            }
        if exact_blueprint["project_ref"] != project_ref:
            raise ProcessAutomationConflict("blueprint project differs from the management interview")
        definition = compile_blueprint(exact_blueprint)
        execution_context = {
            "project_ref": project_ref,
            "model_profile_binding": "resolved_per_run_and_step",
            "style_profile_binding": "resolved_per_run",
        }
        proposal_body = {
            "answers_digest": interview["answers_digest"],
            "definition": definition,
            "blueprint_digest": _digest_json(exact_blueprint),
            "execution_context": execution_context,
        }
        proposal_digest = _digest_json(proposal_body)
        proposal_id = "proposal-" + proposal_digest.split(":", 1)[1][:32]
        prior_proposals = [
            record for record in records
            if record["event"]["event_type"] == AUTHORING_PROPOSED_EVENT
        ]
        if prior_proposals:
            prior = prior_proposals[-1]
            revision_after_prior = any(
                int(record["sequence"]) > int(prior["sequence"])
                and record["event"]["event_type"] == AUTHORING_REVISION_EVENT
                for record in records
            )
            if (
                revision_after_prior
                and prior["event"]["details"].get("proposal_digest")
                == proposal_digest
            ):
                raise ProcessAutomationConflict(
                    "a requested revision must produce a changed proposal identity"
                )
        self.runtime.record_automation_authoring_event(
            interview["run_id"],
            AUTHORING_PROPOSED_EVENT,
            {
                "schema_version": AUTOMATION_SCHEMA_VERSION,
                "proposal_id": proposal_id,
                "proposal_digest": proposal_digest,
                **proposal_body,
                "definition_ref": _definition_ref(definition),
                "idempotency_key": key,
                "worker_receipt": worker_receipt,
            },
            node_id=self.runtime.load_run(interview["run_id"])["current_node_id"],
        )
        return self.get_authoring(dialogue_ref)

    def request_revision(
        self, dialogue_ref: str, *, proposal_id: str, reason: str,
    ) -> dict[str, Any]:
        state = self.get_authoring(dialogue_ref)
        proposal = state.get("proposal")
        if not proposal or proposal["proposal_id"] != proposal_id:
            raise ProcessAutomationConflict("revision does not name the current proposal")
        if state["construction"] is not None:
            raise ProcessAutomationConflict("an approved construction cannot be revised in place")
        exact_reason = _safe_text(reason, "revision reason", limit=2_000)
        self.runtime.record_automation_authoring_event(
            state["management_run_id"],
            AUTHORING_REVISION_EVENT,
            {
                "schema_version": AUTOMATION_SCHEMA_VERSION,
                "proposal_id": proposal_id,
                "proposal_digest": proposal["proposal_digest"],
                "reason": exact_reason,
                "reason_digest": _digest_text(exact_reason),
            },
        )
        return self.get_authoring(dialogue_ref)

    def approve_and_register(
        self,
        dialogue_ref: str,
        *,
        proposal_id: str,
        proposal_digest: str,
        decision_by: str,
    ) -> dict[str, Any]:
        state = self.get_authoring(dialogue_ref)
        proposal = state.get("proposal")
        if not proposal or state["status"] not in {
            "awaiting_definition_approval", "constructing", "awaiting_promotion", "available",
        }:
            raise ProcessAutomationConflict("no current approvable Process proposal exists")
        if (
            proposal["proposal_id"] != proposal_id
            or proposal["proposal_digest"] != proposal_digest
        ):
            raise ProcessAutomationConflict("approval does not bind the current proposal identity")
        principal = _safe_id(decision_by, "decision_by")
        if principal != "principal:user":
            raise ProcessAutomationConflict("Process Definition approval requires principal:user")
        target = contracts.validate_process_definition(proposal["definition"])
        construction = _construction_definition(target)
        run_id = "process-construction-" + proposal_digest.split(":", 1)[1][:32]
        run = _process_run(
            construction,
            run_id=run_id,
            entrypoint="process_authoring",
            principal_id=principal,
            input_bindings={
                "dialogue_ref": dialogue_ref,
                "project_ref": state["project_ref"],
                "management_run_id": state["management_run_id"],
                "answers_digest": state["answers_digest"],
                "proposal_id": proposal_id,
                "proposal_digest": proposal_digest,
                "target_definition_ref": _definition_ref(target),
            },
            parent_run_id=state["management_run_id"],
            constructed_definition_refs=[_definition_ref(target)],
            max_attempts=3,
            selectors=[DEFINITION_SELECTOR, OUTPUT_SELECTOR],
            granted_actions=[
                "construct_definition", "evaluate_evidence", "produce_artifact",
                "record_evidence", "register_definition",
            ],
        )
        try:
            self.runtime.create_run(construction, run)
            self.runtime.mark_run_ready(run_id, reason="Exact Process proposal is ready for principal review")
            self.runtime.start_run(run_id, reason="Begin exact reusable Process construction")
        except RunConflictError:
            persisted = self.runtime.load_run(run_id)
            if persisted["input_bindings"] != run["input_bindings"]:
                raise ProcessAutomationIntegrityError("deterministic construction Run identity collided")
        current = self.runtime.load_run(run_id)
        if current["state"] == "running" and current["current_node_id"] == "review-definition":
            self.runtime.resolve_human_checkpoint(
                run_id, "approved", decision_by=principal,
                reason="Principal approved the exact proposal identity",
            )
        current = self.runtime.load_run(run_id)
        definition_artifact_id = "definition-" + target["digest"].split(":", 1)[1][:24]
        if current["state"] == "running" and current["current_node_id"] == "construct-definition":
            try:
                self.runtime.load_artifact(run_id, definition_artifact_id)
            except RunNotFoundError:
                self.runtime.record_inline_artifact(
                    run_id,
                    definition_artifact_id,
                    json.dumps(target, sort_keys=True, ensure_ascii=False),
                    role="process_definition",
                    node_id="construct-definition",
                    action="construct_definition",
                    selector=DEFINITION_SELECTOR,
                    satisfied_conditions=CONDITIONS,
                    media_type="application/vnd.ora.process-definition+json",
                )
            self.runtime.complete_action_node(
                run_id, "construct_reusable_process_definition",
                reason="Exact reviewed definition constructed",
                artifact_ids=[definition_artifact_id],
            )
        current = self.runtime.load_run(run_id)
        registration_artifact_id = "registration-" + target["digest"].split(":", 1)[1][:24]
        if current["state"] == "running" and current["current_node_id"] == "register-definition":
            result = self.runtime.register_process_definition(
                run_id,
                self.registry,
                target,
                definition_artifact_id=definition_artifact_id,
                registration_artifact_id=registration_artifact_id,
                selector=DEFINITION_SELECTOR,
                satisfied_conditions=CONDITIONS,
            )
            self.runtime.complete_action_node(
                run_id, "register_reusable_process_definition",
                reason="Exact Process Definition registered without activation",
                artifact_ids=[result["artifact"]["artifact_id"]],
            )
        current = self.runtime.load_run(run_id)
        if current["state"] == "running" and current["current_node_id"] == "final-review":
            receipt = self.runtime.load_artifact(run_id, registration_artifact_id)
            evidence_id = "registration-evidence-" + target["digest"].split(":", 1)[1][:24]
            try:
                evidence = self.runtime.load_artifact(run_id, evidence_id)
            except RunNotFoundError:
                evidence = self.runtime.record_inline_artifact(
                    run_id,
                    evidence_id,
                    _canonical_json({
                        "definition_ref": _definition_ref(target),
                        "registration_artifact_id": receipt["artifact_id"],
                        "registration_digest": receipt["identity"]["digest"],
                        "registry_root": str(self.registry.root.resolve()),
                        "verified": True,
                    }),
                    role="evidence",
                    node_id="final-review",
                    action="record_evidence",
                    selector=OUTPUT_SELECTOR,
                    source_artifact_ids=[registration_artifact_id],
                    satisfied_conditions=CONDITIONS,
                    media_type="application/json",
                )["artifact"]
            review = self.runtime.record_final_review(
                run_id,
                artifact_id=registration_artifact_id,
                evidence_id="result_verified",
                evidence_artifact_id=evidence["artifact_id"],
                outcome="PASS",
                reviewer_id="reviewer:process-registry",
                independent=True,
                satisfied_conditions=CONDITIONS,
            )
            self.runtime.apply_transition(
                run_id, "ACCEPT", target_node_id="accepted",
                reason="Exact construction and registration identities verified",
                evaluation_boundary="review-final-review",
                evidence_refs=review["evidence_refs"],
            )
        lifecycle = self.library.get_run_lifecycle(run_id)
        if lifecycle["status"] == "awaiting_disposition":
            lifecycle = self.library.close_run(
                run_id,
                disposition="promote",
                decision_by=principal,
                promoted_definition_ref=_definition_ref(target),
                capability_artifact_id=definition_artifact_id,
            )
        return self.get_authoring(dialogue_ref)

    # ----------------------------------------------------------- execution
    def _available_definition(
        self, definition_ref: Mapping[str, Any], project_ref: str,
    ) -> dict[str, Any]:
        if not isinstance(definition_ref, Mapping):
            raise ProcessAutomationInputRequired("definition_ref must be an exact object")
        try:
            definition = self.registry.resolve(
                str(definition_ref.get("definition_id") or ""),
                str(definition_ref.get("version") or ""),
                str(definition_ref.get("digest") or ""),
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessAutomationInputRequired("exact Process Definition is unavailable") from exc
        entries = self.library.list_entries(project_ref=project_ref)["entries"]
        matches = [
            item for item in entries
            if item["definition_ref"] == _definition_ref(definition)
            and item["lifecycle_status"] == "available"
        ]
        if len(matches) != 1:
            raise ProcessAutomationInputRequired(
                "automated execution requires one exact promoted Process Library entry"
            )
        metadata = (definition.get("output_schema") or {}).get("x-ora-process")
        if not isinstance(metadata, Mapping) or metadata.get("schema_version") != AUTOMATION_SCHEMA_VERSION:
            raise ProcessAutomationInputRequired("Process Definition lacks the G1.18 execution contract")
        if metadata.get("external_effects") is not False or metadata.get("triggers") is not False:
            raise ProcessAutomationInputRequired("G1.18 executes only non-effectful unscheduled Processes")
        return definition

    def _execution_context(
        self,
        *,
        project_ref: str,
        process_profile: str | None,
        step_profiles: Mapping[str, Any] | None,
        one_run_profile: str | None,
        style_profile: str | None,
        definition: Mapping[str, Any],
    ) -> dict[str, Any]:
        step_profiles = copy.deepcopy(dict(step_profiles or {}))
        operations = {
            node["operation"] for node in definition["graph"]["nodes"]
            if node["kind"] == "action"
        }
        if sorted(set(step_profiles) - operations):
            raise ProcessAutomationInputRequired("step Model Profile names an unknown operation")
        resolutions: dict[str, Any] = {}
        for operation in sorted(operations):
            try:
                resolutions[operation] = resolve_effective_profile(
                    project_nexus=project_ref,
                    process_profile=process_profile,
                    step_profile=(str(step_profiles[operation]) if operation in step_profiles else None),
                    one_run_profile=one_run_profile,
                )
            except ModelProfileError as exc:
                raise ProcessAutomationInputRequired(
                    f"Model Profile resolution failed for {operation}: {exc}"
                ) from exc
        style_id = style_profile
        if style_id is None:
            try:
                record = project_meta.read_project_meta(project_ref) or {}
            except Exception:
                record = {}
            candidate = record.get("output_style")
            style_id = candidate if isinstance(candidate, str) and candidate.strip() else None
        style_prompt = ""
        if style_id:
            try:
                try:
                    from . import style_assembly, style_store
                except ImportError:
                    import style_assembly  # type: ignore
                    import style_store  # type: ignore
                style_prompt = style_assembly.compose(
                    style_id, register="written", gear=4,
                    custom_entries=style_store.load_custom_profiles() or None,
                )
            except Exception as exc:
                raise ProcessAutomationInputRequired(
                    f"Style Profile {style_id!r} cannot be resolved: {exc}"
                ) from exc
        body = {
            "project_ref": project_ref,
            "process_profile": process_profile,
            "step_profiles": step_profiles,
            "one_run_profile": one_run_profile,
            "model_resolutions": resolutions,
            "style_profile": style_id,
            "style_prompt": style_prompt,
            "style_prompt_digest": _digest_text(style_prompt),
        }
        return {**body, "binding_digest": _digest_json(body)}

    def begin_run(
        self,
        *,
        definition_ref: Mapping[str, Any],
        project_ref: str,
        inputs: Mapping[str, Any],
        idempotency_key: str,
        principal_id: str = "principal:user",
        process_profile: str | None = None,
        step_profiles: Mapping[str, Any] | None = None,
        one_run_profile: str | None = None,
        style_profile: str | None = None,
    ) -> dict[str, Any]:
        project = _safe_id(project_ref, "project_ref")
        key = _safe_id(idempotency_key, "idempotency_key")
        principal = _safe_id(principal_id, "principal_id")
        definition = self._available_definition(definition_ref, project)
        exact_inputs = _validate_instance(inputs, definition["input_schema"], "inputs")
        execution_context = self._execution_context(
            project_ref=project,
            process_profile=process_profile,
            step_profiles=step_profiles,
            one_run_profile=one_run_profile,
            style_profile=style_profile,
            definition=definition,
        )
        identity = {
            "definition_ref": _definition_ref(definition),
            "project_ref": project,
            "inputs": exact_inputs,
            "idempotency_key": key,
            "execution_context": execution_context,
        }
        invocation_digest = _digest_json(identity)
        run_id = "automated-run-" + invocation_digest.split(":", 1)[1][:32]
        metadata = definition["output_schema"]["x-ora-process"]
        run = _process_run(
            definition,
            run_id=run_id,
            entrypoint="automated_process",
            principal_id=principal,
            input_bindings={
                **identity,
                "invocation_digest": invocation_digest,
            },
            max_attempts=int(metadata["max_attempts"]),
        )
        try:
            self.runtime.create_run(definition, run)
            self.runtime.mark_run_ready(run_id, reason="Exact promoted definition and inputs are bound")
            self.runtime.start_run(run_id, reason="Begin isolated automated Process execution")
        except RunConflictError:
            persisted = self.runtime.load_run(run_id)
            if persisted["input_bindings"] != run["input_bindings"]:
                raise ProcessAutomationIntegrityError("automated Run identity collided")
        return self.run_state(run_id)

    def _content_dir(self, run_id: str) -> Path:
        directory = self.runtime._run_dir(run_id) / "artifact-content"
        if directory.exists() and directory.is_symlink():
            raise ProcessAutomationIntegrityError("artifact content directory may not be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _record_content_artifact(
        self,
        run_id: str,
        artifact_id: str,
        value: Any,
        *,
        role: str,
        node_id: str,
        source_artifact_ids: Sequence[str],
    ) -> dict[str, Any]:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        path = self._content_dir(run_id) / f"{artifact_id}.json"
        if path.exists() and path.is_symlink():
            raise ProcessAutomationIntegrityError("artifact content path may not be a symlink")
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise ProcessAutomationIntegrityError("artifact content identity collided")
        else:
            atomic_write_text(path, text)
        now = _utc_now()
        run = self.runtime.load_run(run_id)
        artifact = {
            "schema_version": contracts.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": artifact_id,
            "role": role,
            "status": "candidate",
            "media_type": "application/json",
            "locator": {"kind": "file", "ref": str(path.resolve())},
            "identity": {
                "kind": "content_digest",
                "digest": _digest_text(text),
                "coverage": ["complete_content"],
                "captured_at": now,
                "fresh_until": (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat().replace("+00:00", "Z"),
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
        return self.runtime.record_artifact(
            artifact,
            action="produce_artifact",
            selectors=[OUTPUT_SELECTOR],
            satisfied_conditions=CONDITIONS,
        )["artifact"]

    @staticmethod
    def _read_content(artifact: Mapping[str, Any]) -> Any:
        locator = artifact.get("locator") or {}
        if locator.get("kind") != "file":
            raise ProcessAutomationIntegrityError("automation output is not a durable file Artifact")
        path = Path(str(locator.get("ref") or ""))
        if not path.is_file() or path.is_symlink():
            raise ProcessAutomationIntegrityError("automation output content is unavailable")
        text = path.read_text(encoding="utf-8")
        if _digest_text(text) != artifact["identity"]["digest"]:
            raise ProcessAutomationIntegrityError("automation output content has drifted")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProcessAutomationIntegrityError("automation output content is invalid JSON") from exc

    def _prior_outputs(self, run_id: str) -> tuple[dict[str, Any], list[str]]:
        run = self.runtime.load_run(run_id)
        outputs: dict[str, Any] = {}
        ids: list[str] = []
        definition = self.runtime.load_definition(run_id)
        metadata = definition["output_schema"]["x-ora-process"]["operation_contracts"]
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run_id, artifact_id)
            node = nodes.get(artifact["lineage"]["producing_node_id"])
            if artifact["role"] not in {"working", "result"} or not node or node["kind"] != "action":
                continue
            contract = metadata.get(node["operation"])
            if not contract:
                continue
            content = self._read_content(artifact)
            if not isinstance(content, Mapping) or contract["output_key"] not in content:
                raise ProcessAutomationIntegrityError("persisted step output violates its definition")
            outputs[contract["output_key"]] = copy.deepcopy(content[contract["output_key"]])
            ids.append(artifact_id)
        return outputs, ids

    def _reauthenticate_execution_context(self, run: Mapping[str, Any]) -> None:
        stored = run["input_bindings"].get("execution_context")
        if not isinstance(stored, Mapping):
            raise ProcessAutomationIntegrityError("Run lacks an execution-context binding")
        definition = self.runtime.load_definition(run["run_id"])
        current = self._execution_context(
            project_ref=stored["project_ref"],
            process_profile=stored.get("process_profile"),
            step_profiles=stored.get("step_profiles"),
            one_run_profile=stored.get("one_run_profile"),
            style_profile=stored.get("style_profile"),
            definition=definition,
        )
        if current != stored:
            raise ProcessAutomationIntegrityError(
                "Project, Model Profile, or Style binding changed after Run creation"
            )

    def execute(self, run_id: str) -> dict[str, Any]:
        """Advance until terminal or a persisted human/failure checkpoint."""

        while True:
            run = self.runtime.load_run(run_id)
            if run["state"] in {"completed", "blocked", "cancelled"}:
                return self.run_state(run_id)
            if run["state"] == "pending":
                # A checkpoint with an unresolved human decision remains pending;
                # callers must use resolve_checkpoint rather than replay execution.
                if self.run_state(run_id)["status"] == "awaiting_human_checkpoint":
                    return self.run_state(run_id)
                self.runtime.resume_run(run_id)
                run = self.runtime.load_run(run_id)
            if run["state"] != "running":
                raise ProcessAutomationConflict(f"Run is not executable from state {run['state']!r}")
            self._reauthenticate_execution_context(run)
            definition = self.runtime.load_definition(run_id)
            nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
            node = nodes[run["current_node_id"]]
            if node["kind"] == "human_checkpoint":
                checkpoint_id = f"human-{node['node_id']}-{run['last_sequence']}"
                self.runtime.pause_run(
                    run_id, checkpoint_id,
                    segment_id=node["node_id"], resume_node_id=node["node_id"],
                    reason="Explicit human checkpoint requires the Principal",
                )
                return self.run_state(run_id)
            if node["kind"] == "action":
                self._execute_action(run_id, definition, node)
                continue
            if node["kind"] == "verification_boundary":
                self._verify_result(run_id, definition, node)
                continue
            raise ProcessAutomationIntegrityError(
                f"G1.18 executor does not support node kind {node['kind']!r}"
            )

    def _execute_action(
        self, run_id: str, definition: Mapping[str, Any], node: Mapping[str, Any],
    ) -> None:
        run = self.runtime.load_run(run_id)
        checkpoint_id = f"pre-{node['node_id']}-{run['contracts']['correction_loop']['attempt'] + 1}"
        self.runtime.create_checkpoint(
            run_id, checkpoint_id,
            segment_id=node["node_id"], resume_node_id=node["node_id"],
        )
        self.runtime.begin_attempt(run_id, node["node_id"])
        prior_outputs, source_ids = self._prior_outputs(run_id)
        metadata = definition["output_schema"]["x-ora-process"]
        contract = metadata["operation_contracts"][node["operation"]]
        execution_context = run["input_bindings"]["execution_context"]
        resolution = execution_context["model_resolutions"][node["operation"]]
        request = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "kind": "execute",
            "operation": node["operation"],
            "instruction": contract["instruction"],
            "inputs": copy.deepcopy(run["input_bindings"]["inputs"]),
            "prior_outputs": prior_outputs,
            "expected_output_key": contract["output_key"],
            "acceptance_criteria": metadata["acceptance_criteria"],
            "execution_context": {
                "config_name": resolution["selected"]["runtime_name"],
                "model_profile_digest": resolution["selected"]["digest"],
                "style_profile": execution_context["style_profile"],
                "style_prompt": execution_context["style_prompt"],
            },
        }
        try:
            receipt = self.worker.invoke(request)
            if receipt["status"] != "PASS":
                raise ProcessAutomationWorkerError(receipt["report"])
            output = receipt["output"]
            if not isinstance(output, Mapping) or set(output) != {contract["output_key"]}:
                raise ProcessAutomationWorkerError("worker output does not match the exact step contract")
            artifact_id = (
                f"step-{node['node_id']}-"
                f"{receipt['response_digest'].split(':', 1)[1][:20]}"
            )
            next_node = next(
                item for item in definition["graph"]["nodes"]
                if item["node_id"] == node["next_node_id"]
            )
            role = "result" if next_node["kind"] == "verification_boundary" else "working"
            artifact_value = (
                {**copy.deepcopy(prior_outputs), **copy.deepcopy(dict(output))}
                if role == "result" else output
            )
            if role == "result":
                _validate_instance(
                    artifact_value, definition["output_schema"], "result",
                )
            artifact = self._record_content_artifact(
                run_id, artifact_id, artifact_value,
                role=role, node_id=node["node_id"], source_artifact_ids=source_ids,
            )
            self.runtime.complete_attempt(
                run_id, node["node_id"], defect_codes=[], evidence_refs=[],
                artifact_digests=[artifact["identity"]["digest"]],
            )
            execution_context_digest = execution_context["binding_digest"]
            self.runtime._record_runtime_event(
                run_id,
                "isolated_process_step_completed",
                {
                    "run_id": run_id,
                    "definition_ref": copy.deepcopy(run["definition_ref"]),
                    "node_id": node["node_id"],
                    "operation": node["operation"],
                    "attempt": self.runtime.load_run(run_id)["contracts"]["correction_loop"]["attempt"],
                    "worker_boundary": receipt["boundary"],
                    "worker_request_digest": receipt["request_digest"],
                    "worker_response_digest": receipt["response_digest"],
                    "execution_context_binding_digest": execution_context_digest,
                    "artifact_id": artifact["artifact_id"],
                    "artifact_identity_digest": artifact["identity"]["digest"],
                },
                node_id=node["node_id"],
                artifact_ids=[artifact["artifact_id"]],
            )
            self.runtime.complete_action_node(
                run_id, node["operation"],
                reason="Isolated worker produced the exact declared output",
                completion_details={
                    "worker_boundary": receipt["boundary"],
                    "worker_request_digest": receipt["request_digest"],
                    "worker_response_digest": receipt["response_digest"],
                    "model_profile_digest": request["execution_context"]["model_profile_digest"],
                    "execution_context_binding_digest": execution_context_digest,
                },
                artifact_ids=[artifact_id],
            )
        except Exception as exc:
            if isinstance(exc, (ProcessAutomationIntegrityError, GovernedRuntimeError)):
                defect = "runtime_integrity_failure"
            else:
                defect = "isolated_worker_failure"
            try:
                self.runtime.complete_attempt(
                    run_id, node["node_id"], defect_codes=[defect],
                    evidence_refs=[], artifact_digests=[],
                )
            except RunConflictError:
                pass
            current = self.runtime.load_run(run_id)
            if current["state"] == "running" and current["current_node_id"] == node["node_id"]:
                failure_checkpoint = f"failure-{node['node_id']}-{current['last_sequence']}"
                self.runtime.pause_run(
                    run_id, failure_checkpoint,
                    segment_id=node["node_id"], resume_node_id=node["node_id"],
                    reason=f"{defect}: {type(exc).__name__}",
                )
            raise ProcessAutomationWorkerError(
                f"Process action {node['node_id']} failed and is restart-safe: {exc}"
            ) from exc

    def _verify_result(
        self, run_id: str, definition: Mapping[str, Any], node: Mapping[str, Any],
    ) -> None:
        result = _latest_result_artifact(self.runtime, run_id)
        if result is None:
            raise ProcessAutomationIntegrityError("verification boundary has no result Artifact")
        content = self._read_content(result)
        metadata = definition["output_schema"]["x-ora-process"]
        request = {
            "schema_version": WORKER_SCHEMA_VERSION,
            "kind": "verify",
            "operation": "verify.process_result",
            "instruction": "Independently verify the exact result against every declared criterion.",
            "inputs": copy.deepcopy(self.runtime.load_run(run_id)["input_bindings"]["inputs"]),
            "prior_outputs": content,
            "expected_output_key": "verification",
            "acceptance_criteria": metadata["acceptance_criteria"],
            "execution_context": {"config_name": None, "style_prompt": ""},
        }
        receipt = self.worker.invoke(request)
        outcome = "PASS" if receipt["status"] == "PASS" else "FAIL"
        evidence_id = "evidence-" + receipt["response_digest"].split(":", 1)[1][:24]
        evidence = self.runtime.record_inline_artifact(
            run_id, evidence_id,
            _canonical_json({
                "worker_boundary": receipt["boundary"],
                "request_digest": receipt["request_digest"],
                "response_digest": receipt["response_digest"],
                "outcome": outcome,
                "report": receipt["report"],
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
            }),
            role="evidence", node_id=node["node_id"],
            action="record_evidence", selector=OUTPUT_SELECTOR,
            source_artifact_ids=[result["artifact_id"]],
            satisfied_conditions=CONDITIONS, media_type="application/json",
        )["artifact"]
        execution_context_digest = (
            self.runtime.load_run(run_id)["input_bindings"]
            ["execution_context"]["binding_digest"]
        )
        self.runtime._record_runtime_event(
            run_id,
            "isolated_process_verification_completed",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(
                    self.runtime.load_run(run_id)["definition_ref"]
                ),
                "node_id": node["node_id"],
                "worker_boundary": receipt["boundary"],
                "worker_request_digest": receipt["request_digest"],
                "worker_response_digest": receipt["response_digest"],
                "execution_context_binding_digest": execution_context_digest,
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
                "evidence_artifact_id": evidence["artifact_id"],
                "evidence_identity_digest": evidence["identity"]["digest"],
                "outcome": outcome,
            },
            node_id=node["node_id"],
            artifact_ids=[result["artifact_id"], evidence["artifact_id"]],
        )
        review = self.runtime.record_final_review(
            run_id,
            artifact_id=result["artifact_id"],
            evidence_id="result_verified",
            evidence_artifact_id=evidence["artifact_id"],
            outcome=outcome,
            reviewer_id="reviewer:isolated-process-worker",
            independent=True,
            satisfied_conditions=CONDITIONS,
        )
        directive = "ACCEPT" if outcome == "PASS" else "REVISE"
        target = node["routes"][directive]
        self.runtime.apply_transition(
            run_id, directive, target_node_id=target,
            reason="Isolated verification completed for the exact result identity",
            evaluation_boundary=f"review-{node['node_id']}",
            evidence_refs=review["evidence_refs"],
        )

    def resolve_checkpoint(
        self,
        run_id: str,
        *,
        outcome: str,
        decision_by: str,
    ) -> dict[str, Any]:
        state = self.run_state(run_id)
        if state["status"] != "awaiting_human_checkpoint":
            raise ProcessAutomationConflict("Run is not awaiting a human checkpoint")
        exact_decision_by = _safe_id(decision_by, "decision_by")
        if outcome not in {"approved", "denied", "unavailable"}:
            raise ProcessAutomationInputRequired("checkpoint outcome is invalid")
        run = self.runtime.load_run(run_id)
        if exact_decision_by != run["contracts"]["authority"]["principal_id"]:
            raise ProcessAutomationConflict(
                "the exact Run principal must resolve this human checkpoint"
            )
        self.runtime.resume_run(run_id)
        self.runtime.resolve_human_checkpoint(
            run_id, outcome,
            decision_by=exact_decision_by,
            reason="Principal resolved the exact persisted Process checkpoint",
        )
        if outcome == "approved":
            return self.execute(run_id)
        return self.run_state(run_id)

    def run_state(self, run_id: str) -> dict[str, Any]:
        run = self.runtime.load_run(run_id)
        definition = self.runtime.load_definition(run_id)
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        node = nodes[run["current_node_id"]]
        result = _latest_result_artifact(self.runtime, run_id)
        status = run["state"]
        if run["state"] == "pending" and node["kind"] == "human_checkpoint":
            status = "awaiting_human_checkpoint"
        elif run["state"] == "pending":
            status = "paused_after_failure"
        body = {
            "schema_version": AUTOMATION_SCHEMA_VERSION,
            "run_id": run_id,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "project_ref": run["input_bindings"].get("project_ref"),
            "invocation_digest": run["input_bindings"].get("invocation_digest"),
            "run_state": run["state"],
            "status": status,
            "current_node": {
                "node_id": node["node_id"], "kind": node["kind"], "label": node["label"],
                "authority_request_type": node.get("authority_request_type"),
            },
            "attempt": run["contracts"]["correction_loop"]["attempt"],
            "max_attempts": run["contracts"]["correction_loop"]["max_attempts"],
            "checkpoint_id": run["contracts"]["continuation"]["checkpoint_id"],
            "result": None,
            "standing_automation": False,
        }
        if result is not None:
            body["result"] = {
                "artifact_id": result["artifact_id"],
                "identity_digest": result["identity"]["digest"],
                "content": self._read_content(result),
            }
        return {**body, "state_digest": _digest_json(body)}


__all__ = [
    "AUTOMATION_SCHEMA_VERSION",
    "BLUEPRINT_SCHEMA_VERSION",
    "IsolatedProcessWorker",
    "ProcessAutomationConflict",
    "ProcessAutomationError",
    "ProcessAutomationInputRequired",
    "ProcessAutomationIntegrityError",
    "ProcessAutomationService",
    "ProcessAutomationWorkerError",
    "compile_blueprint",
    "email_processing_blueprint",
    "validate_blueprint",
]
