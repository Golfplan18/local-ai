"""Versioned, domain-general contracts for governed cognitive processes.

This module is the Phase 1.3 contract boundary.  It deliberately contains no
dispatcher, persistence adapter, controller, model call, file mutation, or
canonical-document loader.  It defines and validates the four persisted object
families authorized by the architecture:

* Process Definition
* Process Run
* Artifact
* event/transition record

Plans, authority, artifact scope, bounded judgment, evidence, correction,
continuation, recovery, and stop/escalation are nested contracts.  The process
graph and package manifest are nested definition contracts.  They are not
additional persisted object families.

The validators reject unknown semantic fields.  Domain-specific meaning belongs
in the declared input/output JSON Schemas and runtime bindings, not in private
controllers or per-domain root fields.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any


CONTRACT_SCHEMA_VERSION = "ora.process-contracts/1.0"
GRAPH_SCHEMA_VERSION = "ora.process-graph/1.0"
PACKAGE_SCHEMA_VERSION = "ora.process-package/1.0"

ROOT_OBJECT_FAMILIES = (
    "process_definition",
    "process_run",
    "artifact",
    "event_transition_record",
)

ATTACHED_CONTRACTS = (
    "approved_plan",
    "authority",
    "artifact_scope",
    "bounded_judgment",
    "evidence",
    "correction_loop",
    "continuation",
    "recovery",
    "stop_escalation",
)

TRANSITION_DIRECTIVES = (
    "PROCEED",
    "ACCEPT",
    "REVISE",
    "REPLAN",
    "REDEFINE",
    "ESCALATE",
    "BLOCKED",
)

OBSERVATION_OUTCOMES = ("PASS", "FAIL", "BROKEN", "INDETERMINATE")

GRAPH_NODE_KINDS = (
    "action",
    "sequence",
    "parallel_branch",
    "join",
    "decision",
    "bounded_loop",
    "verification_boundary",
    "human_checkpoint",
    "process_call",
    "process_return",
    "terminal_state",
)

DEFINITION_STATUSES = ("draft", "approved", "active", "retired", "archived")
RUN_STATES = (
    "created",
    "awaiting_plan_approval",
    "ready",
    "running",
    "pending",
    "redefining",
    "waiting_for_authority",
    "completed",
    "blocked",
    "cancelled",
)

DIRECTIVE_TARGET_STATES = {
    "PROCEED": "running",
    "ACCEPT": "completed",
    "REVISE": "running",
    "REPLAN": "pending",
    "REDEFINE": "redefining",
    "ESCALATE": "waiting_for_authority",
    "BLOCKED": "blocked",
}

ARTIFACT_STATUSES = ("candidate", "withheld", "verified", "accepted", "archived", "discarded")
ARTIFACT_ROLES = (
    "input",
    "working",
    "result",
    "evidence",
    "external_effect_receipt",
    "process_definition",
    "package_member",
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_DIGEST_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*:[A-Fa-f0-9]{16,}$")


class ContractValidationError(ValueError):
    """A persisted or attached process contract is structurally invalid."""

    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def _fail(path: str, message: str) -> None:
    raise ContractValidationError(path, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, "must be an object")
    return value


def _list(value: Any, path: str, *, minimum: int = 0) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(path, "must be an array")
    result = list(value)
    if len(result) < minimum:
        _fail(path, f"must contain at least {minimum} item(s)")
    return result


def _keys(value: Mapping[str, Any], path: str, *, required: set[str], allowed: set[str]) -> None:
    missing = sorted(required - set(value))
    if missing:
        _fail(path, f"missing required field(s): {', '.join(missing)}")
    extra = sorted(set(value) - allowed)
    if extra:
        _fail(path, f"unknown field(s): {', '.join(extra)}")


def _string(value: Any, path: str, *, identifier: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "must be a non-empty string")
    result = value.strip()
    if identifier and not _ID_RE.fullmatch(result):
        _fail(path, "must be a stable identifier")
    return result


def _optional_string(value: Any, path: str, *, identifier: bool = False) -> str | None:
    if value is None:
        return None
    return _string(value, path, identifier=identifier)


def _enum(value: Any, allowed: Sequence[str], path: str) -> str:
    result = _string(value, path)
    if result not in allowed:
        _fail(path, f"must be one of: {', '.join(allowed)}")
    return result


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(path, f"must be an integer >= {minimum}")
    return value


def _strings(value: Any, path: str, *, minimum: int = 0, identifiers: bool = False) -> list[str]:
    values = _list(value, path, minimum=minimum)
    result = [_string(item, f"{path}[{index}]", identifier=identifiers) for index, item in enumerate(values)]
    if len(set(result)) != len(result):
        _fail(path, "must not contain duplicates")
    return result


def _timestamp(value: Any, path: str) -> str:
    result = _string(value, path)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError:
        _fail(path, "must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        _fail(path, "must include a timezone")
    return result


def _digest(value: Any, path: str) -> str:
    result = _string(value, path)
    if not _DIGEST_RE.fullmatch(result):
        _fail(path, "must be '<algorithm>:<hex>' with at least 16 hex characters")
    return result


def _json_schema(value: Any, path: str) -> None:
    schema = _mapping(value, path)
    if "$schema" in schema:
        _string(schema["$schema"], f"{path}.$schema")
    if "type" in schema and not isinstance(schema["type"], (str, list)):
        _fail(f"{path}.type", "must be a string or array")


def _validate_definition_ref(value: Any, path: str) -> None:
    ref = _mapping(value, path)
    _keys(
        ref,
        path,
        required={"definition_id", "version", "digest"},
        allowed={"definition_id", "version", "digest"},
    )
    _string(ref["definition_id"], f"{path}.definition_id", identifier=True)
    _string(ref["version"], f"{path}.version", identifier=True)
    _digest(ref["digest"], f"{path}.digest")


def _validate_identity(value: Any, path: str) -> None:
    identity = _mapping(value, path)
    _keys(
        identity,
        path,
        required={"kind", "digest", "coverage", "captured_at", "fresh_until"},
        allowed={"kind", "digest", "coverage", "captured_at", "fresh_until", "external_version"},
    )
    _enum(identity["kind"], ("content_digest", "git_object", "external_version", "composite"), f"{path}.kind")
    _digest(identity["digest"], f"{path}.digest")
    _strings(identity["coverage"], f"{path}.coverage", minimum=1)
    _timestamp(identity["captured_at"], f"{path}.captured_at")
    _timestamp(identity["fresh_until"], f"{path}.fresh_until")
    captured = datetime.fromisoformat(str(identity["captured_at"]).replace("Z", "+00:00"))
    fresh = datetime.fromisoformat(str(identity["fresh_until"]).replace("Z", "+00:00"))
    if fresh < captured:
        _fail(f"{path}.fresh_until", "must not precede captured_at")
    if "external_version" in identity:
        _optional_string(identity["external_version"], f"{path}.external_version")
    if identity["kind"] == "external_version" and not identity.get("external_version"):
        _fail(f"{path}.external_version", "is required for external_version identity")


def _validate_locator(value: Any, path: str) -> None:
    locator = _mapping(value, path)
    _keys(locator, path, required={"kind", "ref"}, allowed={"kind", "ref"})
    _enum(locator["kind"], ("file", "uri", "git_ref", "registry", "inline"), f"{path}.kind")
    _string(locator["ref"], f"{path}.ref")


def _validate_approved_plan(value: Any, path: str) -> None:
    plan = _mapping(value, path)
    required = {
        "plan_id", "version", "digest", "objective", "approved_by", "approved_at",
        "approved_node_ids", "constraints", "non_goals",
    }
    _keys(plan, path, required=required, allowed=required)
    _string(plan["plan_id"], f"{path}.plan_id", identifier=True)
    _string(plan["version"], f"{path}.version", identifier=True)
    _digest(plan["digest"], f"{path}.digest")
    _string(plan["objective"], f"{path}.objective")
    _string(plan["approved_by"], f"{path}.approved_by", identifier=True)
    _timestamp(plan["approved_at"], f"{path}.approved_at")
    _strings(plan["approved_node_ids"], f"{path}.approved_node_ids", minimum=1, identifiers=True)
    _strings(plan["constraints"], f"{path}.constraints")
    _strings(plan["non_goals"], f"{path}.non_goals")


def _validate_authority(value: Any, path: str) -> None:
    authority = _mapping(value, path)
    required = {"principal_id", "grants", "reserved_actions"}
    _keys(authority, path, required=required, allowed=required | {"expires_at"})
    _string(authority["principal_id"], f"{path}.principal_id", identifier=True)
    grants = _list(authority["grants"], f"{path}.grants", minimum=1)
    grant_ids: list[str] = []
    granted_actions: set[str] = set()
    for index, raw in enumerate(grants):
        grant_path = f"{path}.grants[{index}]"
        grant = _mapping(raw, grant_path)
        fields = {"grant_id", "actions", "resource_selectors", "effect_types", "conditions"}
        _keys(grant, grant_path, required=fields, allowed=fields)
        grant_ids.append(_string(grant["grant_id"], f"{grant_path}.grant_id", identifier=True))
        granted_actions.update(
            _strings(grant["actions"], f"{grant_path}.actions", minimum=1, identifiers=True)
        )
        _strings(grant["resource_selectors"], f"{grant_path}.resource_selectors", minimum=1)
        _strings(grant["effect_types"], f"{grant_path}.effect_types", minimum=1, identifiers=True)
        _strings(grant["conditions"], f"{grant_path}.conditions")
    if len(set(grant_ids)) != len(grant_ids):
        _fail(f"{path}.grants", "grant_id values must be unique")
    reserved_actions = set(
        _strings(authority["reserved_actions"], f"{path}.reserved_actions", identifiers=True)
    )
    reserved_grants = sorted(reserved_actions & granted_actions)
    if reserved_grants:
        _fail(
            f"{path}.reserved_actions",
            f"reserved action(s) must not also be granted: {', '.join(reserved_grants)}",
        )
    if "expires_at" in authority:
        _timestamp(authority["expires_at"], f"{path}.expires_at")


def _validate_artifact_scope(value: Any, path: str) -> None:
    scope = _mapping(value, path)
    fields = {"read_selectors", "write_selectors", "external_effect_selectors"}
    _keys(scope, path, required=fields, allowed=fields)
    _strings(scope["read_selectors"], f"{path}.read_selectors")
    _strings(scope["write_selectors"], f"{path}.write_selectors")
    _strings(scope["external_effect_selectors"], f"{path}.external_effect_selectors")


def _validate_bounded_judgments(value: Any, path: str) -> None:
    judgments = _list(value, path, minimum=1)
    ids: list[str] = []
    for index, raw in enumerate(judgments):
        item_path = f"{path}[{index}]"
        judgment = _mapping(raw, item_path)
        fields = {
            "judgment_id", "node_id", "verified_circumstances", "question",
            "permitted_conclusions", "permitted_directives", "permitted_actions",
            "authority_grant_ids", "artifact_selectors", "required_evidence_ids",
            "evaluator_boundary", "stop_conditions", "return_node_id",
            "escalation_request_types",
        }
        _keys(judgment, item_path, required=fields, allowed=fields)
        ids.append(_string(judgment["judgment_id"], f"{item_path}.judgment_id", identifier=True))
        _string(judgment["node_id"], f"{item_path}.node_id", identifier=True)
        _strings(judgment["verified_circumstances"], f"{item_path}.verified_circumstances", minimum=1)
        _string(judgment["question"], f"{item_path}.question")
        _strings(judgment["permitted_conclusions"], f"{item_path}.permitted_conclusions", minimum=1)
        directives = _strings(judgment["permitted_directives"], f"{item_path}.permitted_directives", minimum=1)
        for directive in directives:
            _enum(directive, TRANSITION_DIRECTIVES, f"{item_path}.permitted_directives")
        _strings(judgment["permitted_actions"], f"{item_path}.permitted_actions", identifiers=True)
        _strings(judgment["authority_grant_ids"], f"{item_path}.authority_grant_ids", identifiers=True)
        _strings(judgment["artifact_selectors"], f"{item_path}.artifact_selectors")
        _strings(judgment["required_evidence_ids"], f"{item_path}.required_evidence_ids", identifiers=True)
        _string(judgment["evaluator_boundary"], f"{item_path}.evaluator_boundary", identifier=True)
        _strings(judgment["stop_conditions"], f"{item_path}.stop_conditions", minimum=1)
        _string(judgment["return_node_id"], f"{item_path}.return_node_id", identifier=True)
        _strings(judgment["escalation_request_types"], f"{item_path}.escalation_request_types", identifiers=True)
    if len(set(ids)) != len(ids):
        _fail(path, "judgment_id values must be unique")


def _validate_evidence(value: Any, path: str) -> None:
    evidence = _mapping(value, path)
    fields = {"requirements", "acceptance_rule", "stale_evidence_policy"}
    _keys(evidence, path, required=fields, allowed=fields)
    requirements = _list(evidence["requirements"], f"{path}.requirements", minimum=1)
    ids: list[str] = []
    for index, raw in enumerate(requirements):
        req_path = f"{path}.requirements[{index}]"
        requirement = _mapping(raw, req_path)
        req_fields = {
            "evidence_id", "claim", "method", "producer_independence",
            "artifact_selectors", "freshness_seconds", "required",
        }
        _keys(requirement, req_path, required=req_fields, allowed=req_fields)
        ids.append(_string(requirement["evidence_id"], f"{req_path}.evidence_id", identifier=True))
        _string(requirement["claim"], f"{req_path}.claim")
        _string(requirement["method"], f"{req_path}.method", identifier=True)
        _enum(
            requirement["producer_independence"],
            ("same_step", "independent_step", "external"),
            f"{req_path}.producer_independence",
        )
        _strings(requirement["artifact_selectors"], f"{req_path}.artifact_selectors", minimum=1)
        _integer(requirement["freshness_seconds"], f"{req_path}.freshness_seconds", minimum=0)
        _boolean(requirement["required"], f"{req_path}.required")
    if len(set(ids)) != len(ids):
        _fail(f"{path}.requirements", "evidence_id values must be unique")
    _enum(evidence["acceptance_rule"], ("all_required", "declared_threshold"), f"{path}.acceptance_rule")
    _enum(evidence["stale_evidence_policy"], ("invalidate", "recapture", "escalate"), f"{path}.stale_evidence_policy")


def _validate_correction(value: Any, path: str) -> None:
    correction = _mapping(value, path)
    fields = {
        "max_attempts", "attempt", "progress_evidence_required", "repeated_defect_limit",
        "allowed_directives", "no_progress_directives",
    }
    _keys(correction, path, required=fields, allowed=fields)
    maximum = _integer(correction["max_attempts"], f"{path}.max_attempts", minimum=1)
    attempt = _integer(correction["attempt"], f"{path}.attempt", minimum=0)
    if attempt > maximum:
        _fail(f"{path}.attempt", "must not exceed max_attempts")
    _boolean(correction["progress_evidence_required"], f"{path}.progress_evidence_required")
    _integer(correction["repeated_defect_limit"], f"{path}.repeated_defect_limit", minimum=1)
    allowed = _strings(correction["allowed_directives"], f"{path}.allowed_directives", minimum=1)
    no_progress = _strings(correction["no_progress_directives"], f"{path}.no_progress_directives", minimum=1)
    correction_directives = ("REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED")
    for directive in allowed + no_progress:
        _enum(directive, correction_directives, path)


def _validate_continuation(value: Any, path: str) -> None:
    continuation = _mapping(value, path)
    fields = {
        "checkpoint_id", "resume_node_id", "required_state_fields", "child_return_fields",
        "parent_run_id", "child_run_ids",
    }
    _keys(continuation, path, required=fields, allowed=fields)
    _string(continuation["checkpoint_id"], f"{path}.checkpoint_id", identifier=True)
    _string(continuation["resume_node_id"], f"{path}.resume_node_id", identifier=True)
    _strings(continuation["required_state_fields"], f"{path}.required_state_fields", minimum=1, identifiers=True)
    _strings(continuation["child_return_fields"], f"{path}.child_return_fields", identifiers=True)
    _optional_string(continuation["parent_run_id"], f"{path}.parent_run_id", identifier=True)
    _strings(continuation["child_run_ids"], f"{path}.child_run_ids", identifiers=True)


def _validate_recovery(value: Any, path: str) -> None:
    recovery = _mapping(value, path)
    fields = {
        "replay_policy", "checkpoint_ref", "external_effect_receipts_required",
        "revalidation_evidence_ids", "on_recovery_failure",
    }
    _keys(recovery, path, required=fields, allowed=fields)
    _enum(
        recovery["replay_policy"],
        ("never_replay_effects", "idempotent_only", "receipt_guarded"),
        f"{path}.replay_policy",
    )
    _string(recovery["checkpoint_ref"], f"{path}.checkpoint_ref")
    _boolean(recovery["external_effect_receipts_required"], f"{path}.external_effect_receipts_required")
    _strings(recovery["revalidation_evidence_ids"], f"{path}.revalidation_evidence_ids", identifiers=True)
    _enum(recovery["on_recovery_failure"], ("ESCALATE", "BLOCKED"), f"{path}.on_recovery_failure")


def _validate_stop_escalation(value: Any, path: str) -> None:
    contract = _mapping(value, path)
    fields = {"stop_conditions", "blocked_conditions", "authority_request_types", "authority_return_target"}
    _keys(contract, path, required=fields, allowed=fields)
    _strings(contract["stop_conditions"], f"{path}.stop_conditions", minimum=1)
    _strings(contract["blocked_conditions"], f"{path}.blocked_conditions", minimum=1)
    _strings(contract["authority_request_types"], f"{path}.authority_request_types", identifiers=True)
    _string(contract["authority_return_target"], f"{path}.authority_return_target", identifier=True)


def _validate_contract_set(value: Any, path: str) -> None:
    contracts = _mapping(value, path)
    required = set(ATTACHED_CONTRACTS)
    _keys(contracts, path, required=required, allowed=required)
    _validate_approved_plan(contracts["approved_plan"], f"{path}.approved_plan")
    _validate_authority(contracts["authority"], f"{path}.authority")
    _validate_artifact_scope(contracts["artifact_scope"], f"{path}.artifact_scope")
    _validate_bounded_judgments(contracts["bounded_judgment"], f"{path}.bounded_judgment")
    _validate_evidence(contracts["evidence"], f"{path}.evidence")
    _validate_correction(contracts["correction_loop"], f"{path}.correction_loop")
    _validate_continuation(contracts["continuation"], f"{path}.continuation")
    _validate_recovery(contracts["recovery"], f"{path}.recovery")
    _validate_stop_escalation(contracts["stop_escalation"], f"{path}.stop_escalation")

    grants_by_id = {
        grant["grant_id"]: grant for grant in contracts["authority"]["grants"]
    }
    grant_ids = set(grants_by_id)
    evidence_ids = {item["evidence_id"] for item in contracts["evidence"]["requirements"]}
    reserved_actions = set(contracts["authority"]["reserved_actions"])
    artifact_scope = contracts["artifact_scope"]
    scoped_selectors = {
        *artifact_scope["read_selectors"],
        *artifact_scope["write_selectors"],
        *artifact_scope["external_effect_selectors"],
    }
    declared_escalation_types = set(
        contracts["stop_escalation"]["authority_request_types"]
    )
    for index, judgment in enumerate(contracts["bounded_judgment"]):
        judgment_path = f"{path}.bounded_judgment[{index}]"
        unknown_grants = sorted(set(judgment["authority_grant_ids"]) - grant_ids)
        if unknown_grants:
            _fail(
                f"{judgment_path}.authority_grant_ids",
                f"references unknown authority grant(s): {', '.join(unknown_grants)}",
            )

        referenced_grants = [
            grants_by_id[grant_id] for grant_id in judgment["authority_grant_ids"]
        ]
        permitted_actions = set(judgment["permitted_actions"])
        reserved_permitted = sorted(permitted_actions & reserved_actions)
        if reserved_permitted:
            _fail(
                f"{judgment_path}.permitted_actions",
                f"reserved action(s) must not be permitted: {', '.join(reserved_permitted)}",
            )
        granted_actions = {
            action for grant in referenced_grants for action in grant["actions"]
        }
        unauthorized_actions = sorted(permitted_actions - granted_actions)
        if unauthorized_actions:
            _fail(
                f"{judgment_path}.permitted_actions",
                "action(s) are not authorized by the referenced grant(s): "
                f"{', '.join(unauthorized_actions)}",
            )

        judgment_selectors = set(judgment["artifact_selectors"])
        granted_selectors = {
            selector
            for grant in referenced_grants
            for selector in grant["resource_selectors"]
        }
        outside_grants = sorted(judgment_selectors - granted_selectors)
        if outside_grants:
            _fail(
                f"{judgment_path}.artifact_selectors",
                "selector(s) are outside the referenced authority grant(s): "
                f"{', '.join(outside_grants)}",
            )
        outside_scope = sorted(judgment_selectors - scoped_selectors)
        if outside_scope:
            _fail(
                f"{judgment_path}.artifact_selectors",
                f"selector(s) are outside artifact scope: {', '.join(outside_scope)}",
            )

        undeclared_escalations = sorted(
            set(judgment["escalation_request_types"]) - declared_escalation_types
        )
        if undeclared_escalations:
            _fail(
                f"{judgment_path}.escalation_request_types",
                "authority request type(s) are not declared by stop_escalation: "
                f"{', '.join(undeclared_escalations)}",
            )

        unknown_evidence = sorted(set(judgment["required_evidence_ids"]) - evidence_ids)
        if unknown_evidence:
            _fail(
                f"{judgment_path}.required_evidence_ids",
                f"references unknown evidence requirement(s): {', '.join(unknown_evidence)}",
            )
    unknown_revalidation = sorted(
        set(contracts["recovery"]["revalidation_evidence_ids"]) - evidence_ids
    )
    if unknown_revalidation:
        _fail(
            f"{path}.recovery.revalidation_evidence_ids",
            f"references unknown evidence requirement(s): {', '.join(unknown_revalidation)}",
        )


_NODE_FIELDS: dict[str, tuple[set[str], set[str]]] = {
    "action": (
        {
            "operation", "next_node_id", "authority_grant_ids", "artifact_access",
            "evidence_requirement_ids", "external_effect",
        },
        set(),
    ),
    "sequence": ({"member_node_ids", "next_node_id"}, set()),
    "parallel_branch": ({"branch_node_ids", "join_node_id"}, set()),
    "join": ({"expected_branch_node_ids", "next_node_id"}, set()),
    "decision": ({"routes", "default_node_id"}, set()),
    "bounded_loop": ({"body_node_id", "exit_node_id", "max_iterations", "progress_evidence_requirement_ids"}, set()),
    "verification_boundary": ({"evidence_requirement_ids", "routes"}, set()),
    "human_checkpoint": (
        {"authority_request_type", "on_approved_node_id", "on_denied_node_id"},
        {"on_unavailable_node_id"},
    ),
    "process_call": (
        {"definition_ref", "input_bindings", "return_node_id"},
        {"on_error_node_id"},
    ),
    "process_return": ({"output_bindings", "next_node_id"}, set()),
    "terminal_state": ({"outcome"}, set()),
}


def _node_references(node: Mapping[str, Any]) -> list[str]:
    kind = str(node["kind"])
    if kind == "action":
        return [str(node["next_node_id"])]
    if kind == "sequence":
        return [*map(str, node["member_node_ids"]), str(node["next_node_id"])]
    if kind == "parallel_branch":
        return [*map(str, node["branch_node_ids"]), str(node["join_node_id"])]
    if kind == "join":
        return [str(node["next_node_id"])]
    if kind == "decision":
        return [str(route["target_node_id"]) for route in node["routes"]] + [str(node["default_node_id"])]
    if kind == "bounded_loop":
        return [str(node["body_node_id"]), str(node["exit_node_id"])]
    if kind == "verification_boundary":
        return [str(target) for target in node["routes"].values()]
    if kind == "human_checkpoint":
        refs = [str(node["on_approved_node_id"]), str(node["on_denied_node_id"])]
        if node.get("on_unavailable_node_id"):
            refs.append(str(node["on_unavailable_node_id"]))
        return refs
    if kind == "process_call":
        refs = [str(node["return_node_id"])]
        if node.get("on_error_node_id"):
            refs.append(str(node["on_error_node_id"]))
        return refs
    if kind == "process_return":
        return [str(node["next_node_id"])]
    return []


def validate_process_graph(value: Any, path: str = "graph") -> dict[str, Any]:
    """Validate the domain-general process graph grammar and return a copy."""

    graph = _mapping(value, path)
    fields = {"schema_version", "graph_id", "entry_node_id", "nodes"}
    _keys(graph, path, required=fields, allowed=fields)
    _enum(graph["schema_version"], (GRAPH_SCHEMA_VERSION,), f"{path}.schema_version")
    _string(graph["graph_id"], f"{path}.graph_id", identifier=True)
    entry_id = _string(graph["entry_node_id"], f"{path}.entry_node_id", identifier=True)
    raw_nodes = _list(graph["nodes"], f"{path}.nodes", minimum=1)
    nodes: dict[str, Mapping[str, Any]] = {}
    common_required = {"node_id", "kind", "label"}
    common_optional = {"description"}

    for index, raw in enumerate(raw_nodes):
        node_path = f"{path}.nodes[{index}]"
        node = _mapping(raw, node_path)
        if "kind" not in node:
            _fail(node_path, "missing required field(s): kind")
        kind = _enum(node["kind"], GRAPH_NODE_KINDS, f"{node_path}.kind")
        kind_required, kind_optional = _NODE_FIELDS[kind]
        required = common_required | kind_required
        allowed = required | common_optional | kind_optional
        _keys(node, node_path, required=required, allowed=allowed)
        node_id = _string(node["node_id"], f"{node_path}.node_id", identifier=True)
        if node_id in nodes:
            _fail(f"{node_path}.node_id", "must be unique")
        nodes[node_id] = node
        _string(node["label"], f"{node_path}.label")
        if "description" in node:
            _optional_string(node["description"], f"{node_path}.description")

        if kind == "action":
            _string(node["operation"], f"{node_path}.operation", identifier=True)
            _string(node["next_node_id"], f"{node_path}.next_node_id", identifier=True)
            _strings(node["authority_grant_ids"], f"{node_path}.authority_grant_ids", minimum=1, identifiers=True)
            _strings(node["artifact_access"], f"{node_path}.artifact_access")
            _strings(node["evidence_requirement_ids"], f"{node_path}.evidence_requirement_ids", identifiers=True)
            _boolean(node["external_effect"], f"{node_path}.external_effect")
        elif kind == "sequence":
            _strings(node["member_node_ids"], f"{node_path}.member_node_ids", minimum=2, identifiers=True)
            _string(node["next_node_id"], f"{node_path}.next_node_id", identifier=True)
        elif kind == "parallel_branch":
            branches = _strings(node["branch_node_ids"], f"{node_path}.branch_node_ids", minimum=2, identifiers=True)
            join_id = _string(node["join_node_id"], f"{node_path}.join_node_id", identifier=True)
            if join_id in branches:
                _fail(f"{node_path}.join_node_id", "must differ from branch nodes")
        elif kind == "join":
            _strings(
                node["expected_branch_node_ids"],
                f"{node_path}.expected_branch_node_ids",
                minimum=2,
                identifiers=True,
            )
            _string(node["next_node_id"], f"{node_path}.next_node_id", identifier=True)
        elif kind == "decision":
            routes = _list(node["routes"], f"{node_path}.routes", minimum=1)
            conditions: list[str] = []
            for route_index, raw_route in enumerate(routes):
                route_path = f"{node_path}.routes[{route_index}]"
                route = _mapping(raw_route, route_path)
                _keys(
                    route,
                    route_path,
                    required={"condition", "target_node_id"},
                    allowed={"condition", "target_node_id"},
                )
                conditions.append(_string(route["condition"], f"{route_path}.condition", identifier=True))
                _string(route["target_node_id"], f"{route_path}.target_node_id", identifier=True)
            if len(set(conditions)) != len(conditions):
                _fail(f"{node_path}.routes", "condition values must be unique")
            _string(node["default_node_id"], f"{node_path}.default_node_id", identifier=True)
        elif kind == "bounded_loop":
            body = _string(node["body_node_id"], f"{node_path}.body_node_id", identifier=True)
            exit_id = _string(node["exit_node_id"], f"{node_path}.exit_node_id", identifier=True)
            if body == exit_id:
                _fail(f"{node_path}.exit_node_id", "must differ from body_node_id")
            _integer(node["max_iterations"], f"{node_path}.max_iterations", minimum=1)
            _strings(
                node["progress_evidence_requirement_ids"],
                f"{node_path}.progress_evidence_requirement_ids",
                minimum=1,
                identifiers=True,
            )
        elif kind == "verification_boundary":
            _strings(
                node["evidence_requirement_ids"],
                f"{node_path}.evidence_requirement_ids",
                minimum=1,
                identifiers=True,
            )
            routes = _mapping(node["routes"], f"{node_path}.routes")
            if not routes:
                _fail(f"{node_path}.routes", "must contain at least one directive route")
            for directive, target in routes.items():
                _enum(directive, TRANSITION_DIRECTIVES, f"{node_path}.routes")
                _string(target, f"{node_path}.routes.{directive}", identifier=True)
        elif kind == "human_checkpoint":
            _string(node["authority_request_type"], f"{node_path}.authority_request_type", identifier=True)
            _string(node["on_approved_node_id"], f"{node_path}.on_approved_node_id", identifier=True)
            _string(node["on_denied_node_id"], f"{node_path}.on_denied_node_id", identifier=True)
            if "on_unavailable_node_id" in node:
                _string(node["on_unavailable_node_id"], f"{node_path}.on_unavailable_node_id", identifier=True)
        elif kind == "process_call":
            _validate_definition_ref(node["definition_ref"], f"{node_path}.definition_ref")
            _mapping(node["input_bindings"], f"{node_path}.input_bindings")
            _string(node["return_node_id"], f"{node_path}.return_node_id", identifier=True)
            if "on_error_node_id" in node:
                _string(node["on_error_node_id"], f"{node_path}.on_error_node_id", identifier=True)
        elif kind == "process_return":
            _mapping(node["output_bindings"], f"{node_path}.output_bindings")
            _string(node["next_node_id"], f"{node_path}.next_node_id", identifier=True)
        elif kind == "terminal_state":
            _enum(node["outcome"], ("accepted", "blocked", "cancelled", "returned"), f"{node_path}.outcome")

    if entry_id not in nodes:
        _fail(f"{path}.entry_node_id", "must reference an existing node")
    if not any(node["kind"] == "terminal_state" for node in nodes.values()):
        _fail(f"{path}.nodes", "must contain at least one terminal_state")

    for node_id, node in nodes.items():
        for reference in _node_references(node):
            if reference not in nodes:
                _fail(f"{path}.nodes[{node_id}]", f"references unknown node '{reference}'")
        if node["kind"] == "parallel_branch":
            join = nodes[str(node["join_node_id"])]
            if join["kind"] != "join":
                _fail(f"{path}.nodes[{node_id}].join_node_id", "must reference a join node")
            if set(join["expected_branch_node_ids"]) != set(node["branch_node_ids"]):
                _fail(f"{path}.nodes[{node_id}]", "parallel branch and join must name the same branches")

    reachable: set[str] = set()
    pending = [entry_id]
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(_node_references(nodes[current]))
    unreachable = sorted(set(nodes) - reachable)
    if unreachable:
        _fail(f"{path}.nodes", f"unreachable node(s): {', '.join(unreachable)}")

    return copy.deepcopy(dict(graph))


def validate_package_manifest(value: Any, path: str = "package_manifest") -> dict[str, Any]:
    """Validate a role-based multi-file package binding."""

    manifest = _mapping(value, path)
    fields = {
        "schema_version", "package_id", "package_version", "definition_ref",
        "entry_member_id", "members",
    }
    _keys(manifest, path, required=fields, allowed=fields)
    _enum(manifest["schema_version"], (PACKAGE_SCHEMA_VERSION,), f"{path}.schema_version")
    _string(manifest["package_id"], f"{path}.package_id", identifier=True)
    _string(manifest["package_version"], f"{path}.package_version", identifier=True)
    _validate_definition_ref(manifest["definition_ref"], f"{path}.definition_ref")
    entry_id = _string(manifest["entry_member_id"], f"{path}.entry_member_id", identifier=True)
    members = _list(manifest["members"], f"{path}.members", minimum=1)
    member_map: dict[str, Mapping[str, Any]] = {}
    locators: set[tuple[str, str]] = set()
    for index, raw in enumerate(members):
        member_path = f"{path}.members[{index}]"
        member = _mapping(raw, member_path)
        member_fields = {"member_id", "role", "required", "media_type", "locator", "identity"}
        _keys(member, member_path, required=member_fields, allowed=member_fields)
        member_id = _string(member["member_id"], f"{member_path}.member_id", identifier=True)
        if member_id in member_map:
            _fail(f"{member_path}.member_id", "must be unique")
        member_map[member_id] = member
        _enum(
            member["role"],
            ("process_definition", "instruction", "script", "template", "test", "schema", "resource"),
            f"{member_path}.role",
        )
        _boolean(member["required"], f"{member_path}.required")
        _string(member["media_type"], f"{member_path}.media_type")
        _validate_locator(member["locator"], f"{member_path}.locator")
        locator = member["locator"]
        locator_key = (str(locator["kind"]), str(locator["ref"]))
        if locator_key in locators:
            _fail(f"{member_path}.locator", "must identify a unique package member")
        locators.add(locator_key)
        _validate_identity(member["identity"], f"{member_path}.identity")
    if entry_id not in member_map:
        _fail(f"{path}.entry_member_id", "must reference an existing member")
    if member_map[entry_id]["role"] != "process_definition":
        _fail(f"{path}.entry_member_id", "must reference the process_definition member")
    if member_map[entry_id]["identity"]["digest"] != manifest["definition_ref"]["digest"]:
        _fail(
            f"{path}.members[{entry_id}].identity.digest",
            "must match the bound Process Definition digest",
        )
    return copy.deepcopy(dict(manifest))


def _validate_root(value: Any, path: str, family: str, *, required: set[str], optional: set[str]) -> Mapping[str, Any]:
    root = _mapping(value, path)
    common = {"schema_version", "object_family"}
    _keys(root, path, required=common | required, allowed=common | required | optional)
    _enum(root["schema_version"], (CONTRACT_SCHEMA_VERSION,), f"{path}.schema_version")
    _enum(root["object_family"], (family,), f"{path}.object_family")
    return root


def validate_process_definition(value: Any, path: str = "process_definition") -> dict[str, Any]:
    fields = {
        "definition_id", "version", "digest", "title", "purpose", "status", "scope",
        "input_schema", "output_schema", "graph", "package_manifest",
    }
    definition = _validate_root(value, path, "process_definition", required=fields, optional={"labels"})
    _string(definition["definition_id"], f"{path}.definition_id", identifier=True)
    _string(definition["version"], f"{path}.version", identifier=True)
    _digest(definition["digest"], f"{path}.digest")
    _string(definition["title"], f"{path}.title")
    _string(definition["purpose"], f"{path}.purpose")
    _enum(definition["status"], DEFINITION_STATUSES, f"{path}.status")
    scope = _mapping(definition["scope"], f"{path}.scope")
    _keys(scope, f"{path}.scope", required={"kind", "selector"}, allowed={"kind", "selector"})
    _enum(scope["kind"], ("universal", "project", "engagement"), f"{path}.scope.kind")
    _string(scope["selector"], f"{path}.scope.selector")
    _json_schema(definition["input_schema"], f"{path}.input_schema")
    _json_schema(definition["output_schema"], f"{path}.output_schema")
    validate_process_graph(definition["graph"], f"{path}.graph")
    validate_package_manifest(definition["package_manifest"], f"{path}.package_manifest")
    manifest_ref = definition["package_manifest"]["definition_ref"]
    expected_ref = {
        "definition_id": definition["definition_id"],
        "version": definition["version"],
        "digest": definition["digest"],
    }
    if manifest_ref != expected_ref:
        _fail(
            f"{path}.package_manifest.definition_ref",
            "must bind this exact Process Definition identity",
        )
    if "labels" in definition:
        _strings(definition["labels"], f"{path}.labels", identifiers=True)
    return copy.deepcopy(dict(definition))


def validate_process_run(value: Any, path: str = "process_run") -> dict[str, Any]:
    fields = {
        "run_id", "definition_ref", "state", "entrypoint", "current_node_id",
        "input_bindings", "contracts", "relationships", "artifact_ids",
        "last_sequence", "created_at", "updated_at",
    }
    run = _validate_root(value, path, "process_run", required=fields, optional={"labels"})
    _string(run["run_id"], f"{path}.run_id", identifier=True)
    _validate_definition_ref(run["definition_ref"], f"{path}.definition_ref")
    _enum(run["state"], RUN_STATES, f"{path}.state")
    _string(run["entrypoint"], f"{path}.entrypoint", identifier=True)
    _string(run["current_node_id"], f"{path}.current_node_id", identifier=True)
    _mapping(run["input_bindings"], f"{path}.input_bindings")
    _validate_contract_set(run["contracts"], f"{path}.contracts")
    relationships = _mapping(run["relationships"], f"{path}.relationships")
    relation_fields = {
        "parent_run_id", "invoked_by_run_id", "invoked_definition_refs",
        "constructed_definition_refs", "return_to_run_id",
    }
    _keys(relationships, f"{path}.relationships", required=relation_fields, allowed=relation_fields)
    _optional_string(relationships["parent_run_id"], f"{path}.relationships.parent_run_id", identifier=True)
    _optional_string(relationships["invoked_by_run_id"], f"{path}.relationships.invoked_by_run_id", identifier=True)
    _optional_string(relationships["return_to_run_id"], f"{path}.relationships.return_to_run_id", identifier=True)
    for field in ("invoked_definition_refs", "constructed_definition_refs"):
        refs = _list(relationships[field], f"{path}.relationships.{field}")
        for index, ref in enumerate(refs):
            _validate_definition_ref(ref, f"{path}.relationships.{field}[{index}]")
    _strings(run["artifact_ids"], f"{path}.artifact_ids", identifiers=True)
    _integer(run["last_sequence"], f"{path}.last_sequence", minimum=0)
    created = _timestamp(run["created_at"], f"{path}.created_at")
    updated = _timestamp(run["updated_at"], f"{path}.updated_at")
    if datetime.fromisoformat(updated.replace("Z", "+00:00")) < datetime.fromisoformat(created.replace("Z", "+00:00")):
        _fail(f"{path}.updated_at", "must not precede created_at")
    if "labels" in run:
        _strings(run["labels"], f"{path}.labels", identifiers=True)
    return copy.deepcopy(dict(run))


def validate_artifact(value: Any, path: str = "artifact") -> dict[str, Any]:
    fields = {
        "artifact_id", "role", "status", "media_type", "locator", "identity",
        "lineage", "created_at",
    }
    artifact = _validate_root(value, path, "artifact", required=fields, optional={"labels"})
    _string(artifact["artifact_id"], f"{path}.artifact_id", identifier=True)
    _enum(artifact["role"], ARTIFACT_ROLES, f"{path}.role")
    _enum(artifact["status"], ARTIFACT_STATUSES, f"{path}.status")
    _string(artifact["media_type"], f"{path}.media_type")
    _validate_locator(artifact["locator"], f"{path}.locator")
    _validate_identity(artifact["identity"], f"{path}.identity")
    lineage = _mapping(artifact["lineage"], f"{path}.lineage")
    lineage_fields = {"run_id", "definition_ref", "producing_node_id", "source_artifact_ids", "event_record_id"}
    _keys(lineage, f"{path}.lineage", required=lineage_fields, allowed=lineage_fields)
    _string(lineage["run_id"], f"{path}.lineage.run_id", identifier=True)
    _validate_definition_ref(lineage["definition_ref"], f"{path}.lineage.definition_ref")
    _string(lineage["producing_node_id"], f"{path}.lineage.producing_node_id", identifier=True)
    _strings(lineage["source_artifact_ids"], f"{path}.lineage.source_artifact_ids", identifiers=True)
    _string(lineage["event_record_id"], f"{path}.lineage.event_record_id", identifier=True)
    _timestamp(artifact["created_at"], f"{path}.created_at")
    if "labels" in artifact:
        _strings(artifact["labels"], f"{path}.labels", identifiers=True)
    return copy.deepcopy(dict(artifact))


def _validate_evidence_ref(value: Any, path: str) -> None:
    ref = _mapping(value, path)
    fields = {"evidence_id", "artifact_id", "identity_digest", "outcome"}
    _keys(ref, path, required=fields, allowed=fields)
    _string(ref["evidence_id"], f"{path}.evidence_id", identifier=True)
    _string(ref["artifact_id"], f"{path}.artifact_id", identifier=True)
    _digest(ref["identity_digest"], f"{path}.identity_digest")
    _enum(ref["outcome"], OBSERVATION_OUTCOMES, f"{path}.outcome")


def _validate_authority_request(value: Any, path: str) -> None:
    request = _mapping(value, path)
    fields = {"request_id", "request_type", "requested_authority", "options", "resume_node_id", "requested_from"}
    _keys(request, path, required=fields, allowed=fields)
    _string(request["request_id"], f"{path}.request_id", identifier=True)
    _string(request["request_type"], f"{path}.request_type", identifier=True)
    _strings(request["requested_authority"], f"{path}.requested_authority", minimum=1, identifiers=True)
    _strings(request["options"], f"{path}.options", minimum=1)
    _string(request["resume_node_id"], f"{path}.resume_node_id", identifier=True)
    _string(request["requested_from"], f"{path}.requested_from", identifier=True)


def validate_event_transition_record(
    value: Any,
    path: str = "event_transition_record",
) -> dict[str, Any]:
    required = {
        "record_id", "run_id", "definition_ref", "sequence", "recorded_at",
        "node_id", "record_type", "evidence_refs", "artifact_ids",
    }
    record = _validate_root(
        value,
        path,
        "event_transition_record",
        required=required,
        optional={"event", "transition"},
    )
    _string(record["record_id"], f"{path}.record_id", identifier=True)
    _string(record["run_id"], f"{path}.run_id", identifier=True)
    _validate_definition_ref(record["definition_ref"], f"{path}.definition_ref")
    _integer(record["sequence"], f"{path}.sequence", minimum=1)
    _timestamp(record["recorded_at"], f"{path}.recorded_at")
    _string(record["node_id"], f"{path}.node_id", identifier=True)
    record_type = _enum(record["record_type"], ("event", "transition"), f"{path}.record_type")
    refs = _list(record["evidence_refs"], f"{path}.evidence_refs")
    for index, ref in enumerate(refs):
        _validate_evidence_ref(ref, f"{path}.evidence_refs[{index}]")
    _strings(record["artifact_ids"], f"{path}.artifact_ids", identifiers=True)

    if record_type == "event":
        if "event" not in record or "transition" in record:
            _fail(path, "event records require event and forbid transition")
        event = _mapping(record["event"], f"{path}.event")
        event_fields = {"event_type", "details", "observation"}
        _keys(event, f"{path}.event", required={"event_type", "details"}, allowed=event_fields)
        _string(event["event_type"], f"{path}.event.event_type", identifier=True)
        _mapping(event["details"], f"{path}.event.details")
        if "observation" in event:
            observation = _mapping(event["observation"], f"{path}.event.observation")
            fields = {"outcome", "summary"}
            _keys(observation, f"{path}.event.observation", required=fields, allowed=fields)
            _enum(observation["outcome"], OBSERVATION_OUTCOMES, f"{path}.event.observation.outcome")
            _string(observation["summary"], f"{path}.event.observation.summary")
    else:
        if "transition" not in record or "event" in record:
            _fail(path, "transition records require transition and forbid event")
        transition = _mapping(record["transition"], f"{path}.transition")
        required_fields = {
            "directive", "from_state", "to_state", "reason", "evaluation_boundary",
            "target_node_id",
        }
        _keys(
            transition,
            f"{path}.transition",
            required=required_fields,
            allowed=required_fields | {"authority_request"},
        )
        directive = _enum(transition["directive"], TRANSITION_DIRECTIVES, f"{path}.transition.directive")
        _enum(transition["from_state"], RUN_STATES, f"{path}.transition.from_state")
        to_state = _enum(transition["to_state"], RUN_STATES, f"{path}.transition.to_state")
        required_target_state = DIRECTIVE_TARGET_STATES[directive]
        if to_state != required_target_state:
            _fail(
                f"{path}.transition.to_state",
                f"{directive} requires to_state '{required_target_state}', got '{to_state}'",
            )
        _string(transition["reason"], f"{path}.transition.reason")
        _string(transition["evaluation_boundary"], f"{path}.transition.evaluation_boundary", identifier=True)
        _string(transition["target_node_id"], f"{path}.transition.target_node_id", identifier=True)
        has_request = "authority_request" in transition
        if directive == "ESCALATE" and not has_request:
            _fail(f"{path}.transition.authority_request", "is required for ESCALATE")
        if directive != "ESCALATE" and has_request:
            _fail(f"{path}.transition.authority_request", "is permitted only for ESCALATE")
        if has_request:
            _validate_authority_request(transition["authority_request"], f"{path}.transition.authority_request")

    return copy.deepcopy(dict(record))


_ROOT_VALIDATORS = {
    "process_definition": validate_process_definition,
    "process_run": validate_process_run,
    "artifact": validate_artifact,
    "event_transition_record": validate_event_transition_record,
}


def validate_persisted_object(value: Any, path: str = "object") -> dict[str, Any]:
    """Dispatch strict validation for exactly one of the four persisted families."""

    root = _mapping(value, path)
    family = root.get("object_family")
    if family not in _ROOT_VALIDATORS:
        _fail(f"{path}.object_family", f"must be one of: {', '.join(ROOT_OBJECT_FAMILIES)}")
    return _ROOT_VALIDATORS[str(family)](root, path)


def contract_catalog() -> dict[str, Any]:
    """Return the versioned, JSON-serializable contract vocabulary.

    This compact catalog lets registries and tooling inspect the contract surface
    without importing runtime behavior.  The strict validators above are the
    executable machine-checking authority for Phase 1.3.
    """

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "root_object_families": list(ROOT_OBJECT_FAMILIES),
        "attached_contracts": list(ATTACHED_CONTRACTS),
        "transition_directives": list(TRANSITION_DIRECTIVES),
        "directive_target_states": dict(DIRECTIVE_TARGET_STATES),
        "observation_outcomes": list(OBSERVATION_OUTCOMES),
        "definition_statuses": list(DEFINITION_STATUSES),
        "run_states": list(RUN_STATES),
        "artifact_statuses": list(ARTIFACT_STATUSES),
        "artifact_roles": list(ARTIFACT_ROLES),
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "graph_node_kinds": list(GRAPH_NODE_KINDS),
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "construction_operation_model": "relationships_over_one_process_run",
    }


__all__ = [
    "ARTIFACT_ROLES",
    "ARTIFACT_STATUSES",
    "ATTACHED_CONTRACTS",
    "CONTRACT_SCHEMA_VERSION",
    "ContractValidationError",
    "DIRECTIVE_TARGET_STATES",
    "GRAPH_NODE_KINDS",
    "GRAPH_SCHEMA_VERSION",
    "OBSERVATION_OUTCOMES",
    "PACKAGE_SCHEMA_VERSION",
    "ROOT_OBJECT_FAMILIES",
    "RUN_STATES",
    "TRANSITION_DIRECTIVES",
    "contract_catalog",
    "validate_artifact",
    "validate_event_transition_record",
    "validate_package_manifest",
    "validate_persisted_object",
    "validate_process_definition",
    "validate_process_graph",
    "validate_process_run",
]
