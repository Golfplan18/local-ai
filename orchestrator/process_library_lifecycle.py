"""G1.1 Phase 2.6–2.8 — Library lifecycle and governed invocation.

The Process Definition registry remains immutable exact-version storage. This
service adds no marketplace and no standing automation. It projects registry
entries for discovery, enforces project/universal scope for manual invocation,
and treats one authenticated terminal Run disposition as the only source of
promotion authority. Promotion makes an accepted registered definition
available for manual invocation; it never creates triggers or deployment.
Phase 2.7 derives the Programming/Build label decision from authenticated
construct/register/invoke evidence and never renames the surface automatically.
Phase 2.8 binds a ready Library selection to one exact, restart-safe governed
Run and its authenticated result without fabricating independent acceptance.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from active_project import canonicalize_project_nexus
    import process_contracts as _contracts
    from governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
        TERMINAL_RUN_STATES,
        lifecycle_disposition_idempotency_key,
    )
    from process_definition_registry import (
        DEFAULT_PROCESS_DEFINITIONS_DIR,
        PROCESS_DEFINITIONS_ENV,
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
    )
    import runtime_paths as _runtime_paths
except ImportError:  # pragma: no cover
    from orchestrator.active_project import canonicalize_project_nexus
    from orchestrator import process_contracts as _contracts
    from orchestrator.governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
        TERMINAL_RUN_STATES,
        lifecycle_disposition_idempotency_key,
    )
    from orchestrator.process_definition_registry import (
        DEFAULT_PROCESS_DEFINITIONS_DIR,
        PROCESS_DEFINITIONS_ENV,
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
    )
    from orchestrator import runtime_paths as _runtime_paths


LIBRARY_SCHEMA_VERSION = "ora.process-library/1.0"
LIFECYCLE_SCHEMA_VERSION = "ora.process-lifecycle-disposition/1.0"
CONSTRUCTION_LABEL_SCHEMA_VERSION = "ora.construction-label-decision/1.0"
MANUAL_INVOCATION_SCHEMA_VERSION = "ora.manual-process-invocation/1.0"
LIFECYCLE_DISPOSITIONS = ("promote", "preserve", "archive", "discard")
_OUTPUT_ROLES = frozenset({"working", "result", "process_definition"})
_PROGRAMMING_DEFINITION_ID = "ora/programming"
_CONSTRUCTION_LABEL_DECISIONS = {
    "keep_programming": "Programming",
    "use_build": "Build",
}
_construction_label_lock = threading.RLock()


class ProcessLibraryError(RuntimeError):
    """The Process Library request cannot be completed."""


class ProcessLibraryInputRequired(ProcessLibraryError):
    """An exact user choice or identity is required."""


class ProcessLibraryConflict(ProcessLibraryError):
    """The requested lifecycle action conflicts with persisted state."""


class ProcessLibraryIntegrityError(ProcessLibraryError):
    """A registry, Run, Artifact, or lifecycle identity does not authenticate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    return _digest_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def _normalize_ref(value: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "definition_id", "version", "digest",
    }:
        raise ProcessLibraryInputRequired(
            "definition_ref must contain exact definition_id, version, and digest"
        )
    ref = {field: str(value[field] or "").strip() for field in value}
    if not ref["definition_id"] or not ref["version"]:
        raise ProcessLibraryInputRequired("definition_ref values must be non-empty")
    if (
        len(ref["digest"]) != 71
        or not ref["digest"].startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in ref["digest"][7:])
    ):
        raise ProcessLibraryInputRequired(
            "definition_ref digest must be an exact lowercase sha256 identity"
        )
    return ref


def _canonical_definition_artifact_digest(definition: Mapping[str, Any]) -> str:
    """Identity required for a complete inline Process Definition Artifact."""

    return _digest_text(
        json.dumps(definition, sort_keys=True, ensure_ascii=False)
    )


def _validate_definition_inputs(
    definition: Mapping[str, Any], value: Mapping[str, Any] | None
) -> dict[str, Any]:
    if value is None:
        inputs: dict[str, Any] = {}
    elif isinstance(value, Mapping):
        inputs = copy.deepcopy(dict(value))
    else:
        raise ProcessLibraryInputRequired(
            "manual invocation inputs must be an object"
        )
    try:
        from jsonschema import Draft202012Validator

        errors = sorted(
            Draft202012Validator(definition["input_schema"]).iter_errors(inputs),
            key=lambda item: list(item.absolute_path),
        )
    except Exception as exc:
        if exc.__class__.__module__.startswith("jsonschema"):
            raise ProcessLibraryIntegrityError(
                "registered Process Definition has an invalid input schema"
            ) from exc
        raise ProcessLibraryIntegrityError(
            "manual invocation input validation is unavailable"
        ) from exc
    if errors:
        locations = []
        for error in errors[:5]:
            path = ".".join(str(item) for item in error.absolute_path) or "$"
            locations.append(f"{path}: {error.message}")
        raise ProcessLibraryInputRequired(
            "manual invocation inputs do not satisfy the exact definition: "
            + "; ".join(locations)
        )
    return inputs


def _manual_execution_contract(
    definition: Mapping[str, Any], inputs: Mapping[str, Any]
) -> dict[str, Any]:
    """Project the exact graph operation supported by the Dialogue executor."""

    nodes = {
        str(node["node_id"]): node
        for node in definition["graph"]["nodes"]
    }
    entry_node_id = str(definition["graph"]["entry_node_id"])
    entry_node = nodes[entry_node_id]
    next_node = nodes.get(str(entry_node.get("next_node_id") or ""))
    if (
        entry_node.get("kind") != "action"
        or entry_node.get("external_effect") is not False
        or not entry_node.get("operation")
        or not entry_node.get("artifact_access")
        or next_node is None
        or next_node.get("kind") != "verification_boundary"
    ):
        raise ProcessLibraryConflict(
            "manual Dialogue invocation requires a non-external action entry "
            "followed by an exact verification boundary"
        )
    body = {
        "definition_ref": _definition_ref(definition),
        "title": str(definition["title"]),
        "purpose": str(definition["purpose"]),
        "definition_inputs": copy.deepcopy(dict(inputs)),
        "entry_node": {
            "node_id": entry_node_id,
            "label": str(entry_node["label"]),
            "operation": str(entry_node["operation"]),
            "external_effect": False,
            "artifact_access": copy.deepcopy(entry_node["artifact_access"]),
            "next_node_id": str(entry_node["next_node_id"]),
        },
        "verification_boundary": {
            "node_id": str(next_node["node_id"]),
            "label": str(next_node["label"]),
            "required_evidence_ids": copy.deepcopy(
                next_node["evidence_requirement_ids"]
            ),
            "routes": copy.deepcopy(next_node["routes"]),
        },
        "output_schema": copy.deepcopy(definition["output_schema"]),
    }
    return {**body, "execution_contract_digest": _digest_json(body)}


def _manual_invocation_contracts(
    definition: Mapping[str, Any],
    *,
    invocation_id: str,
    objective: str,
    principal_id: str,
    now: str,
) -> dict[str, Any]:
    """Derive a no-external-effect execution envelope from the exact graph."""

    nodes = list(definition["graph"]["nodes"])
    node_ids = [str(node["node_id"]) for node in nodes]
    action_nodes = [node for node in nodes if node["kind"] == "action"]
    selectors = sorted({
        str(selector)
        for node in action_nodes
        for selector in node.get("artifact_access", [])
    })
    if not selectors:
        selectors = ["scope:declared_outputs"]
    output_selector = (
        "scope:declared_outputs"
        if "scope:declared_outputs" in selectors else selectors[0]
    )
    grant_ids = sorted({
        str(grant_id)
        for node in action_nodes
        for grant_id in node.get("authority_grant_ids", [])
    }) or ["manual-invocation-grant"]
    conditions = ["exact_manual_invocation_binding"]
    safe_actions = ["evaluate_evidence", "produce_artifact", "record_evidence"]
    grants = [
        {
            "grant_id": grant_id,
            "actions": safe_actions,
            "resource_selectors": selectors,
            "effect_types": ["local_reversible"],
            "conditions": conditions,
        }
        for grant_id in grant_ids
    ]
    verification_nodes = [
        node for node in nodes if node["kind"] == "verification_boundary"
    ]
    declared_evidence_ids = sorted({
        str(evidence_id)
        for node in nodes
        for evidence_id in node.get("evidence_requirement_ids", [])
    })
    requirements = [
        {
            "evidence_id": evidence_id,
            "claim": "The exact manual invocation result satisfies the declared criterion.",
            "method": "independent_manual_invocation_review",
            "producer_independence": "independent_step",
            "artifact_selectors": [output_selector],
            "freshness_seconds": 86400,
            "required": True,
        }
        for evidence_id in declared_evidence_ids
    ]
    if not requirements:
        requirements = [{
            "evidence_id": "manual_invocation_result_authenticated",
            "claim": "The exact pipeline result is bound to this invocation.",
            "method": "runtime_result_identity_binding",
            "producer_independence": "same_step",
            "artifact_selectors": [output_selector],
            "freshness_seconds": 86400,
            "required": False,
        }]
    escalation_types = sorted({
        str(node["authority_request_type"])
        for node in nodes if node["kind"] == "human_checkpoint"
    })
    if any("ESCALATE" in (node.get("routes") or {}) for node in verification_nodes):
        escalation_types = sorted({*escalation_types, "manual_authority_request"})
    judgments = []
    for node in verification_nodes:
        directives = sorted(str(item) for item in node["routes"])
        judgments.append({
            "judgment_id": f"manual-judgment-{node['node_id']}",
            "node_id": node["node_id"],
            "verified_circumstances": [
                "The exact invocation, result Artifact, and current evidence are bound."
            ],
            "question": "Which declared graph route is supported by current evidence?",
            "permitted_conclusions": [
                "criteria_met", "correction_required", "authority_required", "blocked",
            ],
            "permitted_directives": directives,
            "permitted_actions": ["evaluate_evidence"],
            "authority_grant_ids": [grant_ids[0]],
            "artifact_selectors": [output_selector],
            "required_evidence_ids": list(node["evidence_requirement_ids"]),
            "evaluator_boundary": f"manual-review-{node['node_id']}",
            "stop_conditions": ["missing_evidence", "unsupported_route"],
            "return_node_id": node["node_id"],
            "escalation_request_types": escalation_types,
        })
    if not judgments:
        judgments = [{
            "judgment_id": "manual-invocation-boundary",
            "node_id": definition["graph"]["entry_node_id"],
            "verified_circumstances": ["The exact invocation identity is bound."],
            "question": "Must this unsupported invocation stop?",
            "permitted_conclusions": ["blocked"],
            "permitted_directives": ["BLOCKED"],
            "permitted_actions": [],
            "authority_grant_ids": [],
            "artifact_selectors": [],
            "required_evidence_ids": [],
            "evaluator_boundary": "manual-invocation-boundary",
            "stop_conditions": ["unsupported_graph"],
            "return_node_id": definition["graph"]["entry_node_id"],
            "escalation_request_types": [],
        }]
    correction_directives = [
        "REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED",
    ]
    return {
        "approved_plan": {
            "plan_id": f"plan-{invocation_id}",
            "version": "1.0",
            "digest": _digest_json({
                "invocation_id": invocation_id,
                "definition_ref": _definition_ref(definition),
                "objective": objective,
                "approved_node_ids": node_ids,
            }),
            "objective": objective,
            "approved_by": principal_id,
            "approved_at": now,
            "approved_node_ids": node_ids,
            "constraints": [
                "Bind the exact registered Process Definition and manual invocation inputs.",
                "No external effect, activation, publication, or scope expansion is granted.",
            ],
            "non_goals": ["Standing automation and undeclared external effects."],
        },
        "authority": {
            "principal_id": principal_id,
            "grants": grants,
            "reserved_actions": [
                "activate", "expand_scope", "external_effect", "mutate",
                "publish", "register_definition", "remote_git", "send_external",
            ],
        },
        "artifact_scope": {
            "read_selectors": selectors,
            "write_selectors": selectors,
            "external_effect_selectors": [],
        },
        "bounded_judgment": judgments,
        "evidence": {
            "requirements": requirements,
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "invalidate",
        },
        "correction_loop": {
            "max_attempts": 3,
            "attempt": 0,
            "progress_evidence_required": True,
            "repeated_defect_limit": 2,
            "allowed_directives": correction_directives,
            "no_progress_directives": [
                "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED",
            ],
        },
        "continuation": {
            "checkpoint_id": f"checkpoint-{invocation_id}",
            "resume_node_id": definition["graph"]["entry_node_id"],
            "required_state_fields": [
                "current_node_id", "last_sequence", "artifact_ids", "input_bindings",
            ],
            "child_return_fields": [],
            "parent_run_id": None,
            "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "never_replay_effects",
            "checkpoint_ref": f"checkpoint:{invocation_id}",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": declared_evidence_ids,
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": [
                "missing_input", "missing_evidence", "external_effect_requested",
            ],
            "blocked_conditions": [
                "definition_unavailable", "identity_drift", "unsupported_graph",
            ],
            "authority_request_types": escalation_types,
            "authority_return_target": principal_id,
        },
    }


class ProcessLibraryLifecycleService:
    """Restart-derived library discovery and one-time Run closure service."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        registry: ProcessDefinitionRegistry | None = None,
        registry_root: str | Path | None = None,
        seed_definitions: Sequence[Mapping[str, Any]] = (),
        construction_label_path: str | Path | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.runtime = runtime or GovernedProcessRuntime()
        self.registry = registry
        self.registry_root = Path(
            registry_root
            or os.environ.get(PROCESS_DEFINITIONS_ENV)
            or DEFAULT_PROCESS_DEFINITIONS_DIR
        ).expanduser().resolve()
        self.seed_definitions = [copy.deepcopy(dict(item)) for item in seed_definitions]
        raw_label_path = (
            Path(construction_label_path)
            if construction_label_path is not None
            else self.runtime.root.parent / "process-construction-label.json"
        )
        self.construction_label_path = Path(
            os.path.abspath(os.path.expanduser(str(raw_label_path)))
        )
        self._now = now or _utc_now

    def _registry_for_read(self) -> ProcessDefinitionRegistry | None:
        if self.registry is not None:
            return self.registry
        if not self.registry_root.exists():
            return None
        if self.registry_root.is_symlink() or not self.registry_root.is_dir():
            raise ProcessLibraryIntegrityError(
                "Process Definition registry root is not a real directory"
            )
        if not any(self.registry_root.iterdir()):
            return None
        anchor_root = self.registry_root / ".registration-anchors"
        if not anchor_root.is_dir() or anchor_root.is_symlink():
            raise ProcessLibraryIntegrityError(
                "Process Definition registry lacks its independent anchor root"
            )
        self.registry = ProcessDefinitionRegistry(self.registry_root)
        return self.registry

    def _registry_required(self) -> ProcessDefinitionRegistry:
        if self.registry is None:
            self.registry = ProcessDefinitionRegistry(self.registry_root)
        return self.registry

    def _validated_seed_definitions(self) -> list[dict[str, Any]]:
        validated = []
        for definition in self.seed_definitions:
            try:
                ProcessDefinitionRegistry._verify_issued_content_identity(definition)
            except (KeyError, ProcessDefinitionRegistryError) as exc:
                raise ProcessLibraryIntegrityError(
                    "Process Library seed definition could not be authenticated"
                ) from exc
            validated.append(copy.deepcopy(definition))
        return validated

    def _iter_runs(self) -> list[dict[str, Any]]:
        if not self.runtime.root.exists():
            return []
        runs: list[dict[str, Any]] = []
        for entry in sorted(self.runtime.root.iterdir()):
            if entry.is_symlink() or not entry.is_dir():
                raise ProcessLibraryIntegrityError(
                    f"invalid Process Run storage entry: {entry}"
                )
            run_path = entry / "run.json"
            if not run_path.is_file() or run_path.is_symlink():
                raise ProcessLibraryIntegrityError(
                    f"Process Run storage entry lacks a real run.json: {entry}"
                )
            try:
                raw = json.loads(run_path.read_text(encoding="utf-8"))
                run = self.runtime.load_run(str(raw["run_id"]))
            except (OSError, KeyError, ValueError, json.JSONDecodeError,
                    GovernedRuntimeError) as exc:
                raise ProcessLibraryIntegrityError(
                    f"Process Run storage integrity failed at {entry}"
                ) from exc
            if entry != self.runtime._run_dir(run["run_id"]):
                raise ProcessLibraryIntegrityError(
                    "Process Run storage path differs from its declared identity"
                )
            runs.append(run)
        return runs

    def _output_bindings(self, run: Mapping[str, Any]) -> list[dict[str, Any]]:
        bindings = []
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            if artifact["role"] not in _OUTPUT_ROLES:
                continue
            bindings.append({
                "artifact_id": artifact["artifact_id"],
                "role": artifact["role"],
                "identity_digest": artifact["identity"]["digest"],
                "recorded_status": artifact["status"],
            })
        return sorted(bindings, key=lambda item: item["artifact_id"])

    def _accepted_linked_result(
        self,
        run: Mapping[str, Any],
        capability_artifact_id: str,
    ) -> dict[str, Any] | None:
        requirements = [
            item for item in run["contracts"]["evidence"]["requirements"]
            if item["required"]
        ]
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            if (
                artifact["role"] != "result"
                or capability_artifact_id
                not in artifact["lineage"]["source_artifact_ids"]
            ):
                continue
            try:
                for requirement in requirements:
                    self.runtime._current_passing_review(
                        run["run_id"], artifact["artifact_id"],
                        requirement["evidence_id"],
                    )
            except GovernedRuntimeError:
                continue
            return artifact
        return None

    def _promotion_binding(
        self,
        run: Mapping[str, Any],
        definition_ref: Mapping[str, Any],
        capability_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        ref = _normalize_ref(definition_ref)
        registry = self._registry_required()
        try:
            definition = registry.resolve(
                ref["definition_id"], ref["version"], ref["digest"]
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryInputRequired(
                "promotion requires an exact registered Process Definition"
            ) from exc
        expected_digest = _canonical_definition_artifact_digest(definition)
        matches = []
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            if artifact["role"] != "process_definition":
                continue
            if capability_artifact_id and artifact_id != capability_artifact_id:
                continue
            if (
                artifact["identity"]["kind"] == "content_digest"
                and artifact["identity"]["digest"] == expected_digest
                and "complete_content" in artifact["identity"]["coverage"]
            ):
                matches.append(artifact)
        if len(matches) != 1:
            raise ProcessLibraryInputRequired(
                "promotion requires one exact content-bound Process Definition Artifact"
            )
        capability = matches[0]
        accepted_result = self._accepted_linked_result(
            run, capability["artifact_id"]
        )
        if accepted_result is None:
            raise ProcessLibraryInputRequired(
                "promotion requires a currently accepted result derived from the "
                "exact Process Definition Artifact"
            )
        return {
            "definition": definition,
            "definition_ref": ref,
            "capability_artifact": capability,
            "accepted_result": accepted_result,
        }

    def _validate_lifecycle_record(
        self,
        run: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        event = record.get("event") or {}
        details = event.get("details") or {}
        required = {
            "schema_version", "disposition", "decision_by", "idempotency_key",
            "terminal_state", "terminal_record_id", "terminal_sequence",
            "output_bindings", "output_bindings_digest",
            "promoted_definition_ref", "capability_artifact_id",
        }
        if (
            record.get("record_type") != "event"
            or event.get("event_type") != "lifecycle_disposition_recorded"
            or set(details) != required
            or details.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
            or details.get("disposition") not in LIFECYCLE_DISPOSITIONS
            or details.get("decision_by")
            != run["contracts"]["authority"]["principal_id"]
            or details.get("terminal_state") != run["state"]
            or run["state"] not in TERMINAL_RUN_STATES
        ):
            raise ProcessLibraryIntegrityError(
                "Run lifecycle disposition has an invalid authority or terminal binding"
            )
        try:
            expected_idempotency_key = lifecycle_disposition_idempotency_key(
                run["run_id"],
                details["disposition"],
                details["promoted_definition_ref"],
                details["capability_artifact_id"],
            )
        except (TypeError, ValueError) as exc:
            raise ProcessLibraryIntegrityError(
                "Run lifecycle disposition has an invalid idempotency identity"
            ) from exc
        if details["idempotency_key"] != expected_idempotency_key:
            raise ProcessLibraryIntegrityError(
                "Run lifecycle disposition idempotency identity does not authenticate"
            )
        records = self.runtime.load_records(run["run_id"])
        terminal = next(
            (
                item for item in records
                if item["record_id"] == details["terminal_record_id"]
            ),
            None,
        )
        bindings = self._output_bindings(run)
        if (
            terminal is None
            or terminal.get("record_type") != "transition"
            or (terminal.get("transition") or {}).get("to_state") != run["state"]
            or terminal["sequence"] != details.get("terminal_sequence")
            or details.get("output_bindings") != bindings
            or details.get("output_bindings_digest") != _digest_json(bindings)
            or record.get("artifact_ids")
            != [item["artifact_id"] for item in bindings]
            or record.get("evidence_refs") != terminal.get("evidence_refs")
        ):
            raise ProcessLibraryIntegrityError(
                "Run lifecycle disposition differs from its terminal or Artifact identity"
            )
        promotion = None
        if details["disposition"] == "promote":
            if run["state"] != "completed":
                raise ProcessLibraryIntegrityError(
                    "non-completed Run contains a promotion disposition"
                )
            try:
                promotion = self._promotion_binding(
                    run,
                    details.get("promoted_definition_ref"),
                    str(details.get("capability_artifact_id") or ""),
                )
            except ProcessLibraryError as exc:
                raise ProcessLibraryIntegrityError(
                    "persisted promotion no longer authenticates its exact capability"
                ) from exc
        elif (
            details.get("promoted_definition_ref") is not None
            or details.get("capability_artifact_id") is not None
        ):
            raise ProcessLibraryIntegrityError(
                "non-promotion lifecycle disposition carries promotion authority"
            )
        closure = {
            "record_id": record["record_id"],
            "sequence": record["sequence"],
            "recorded_at": record["recorded_at"],
            **copy.deepcopy(dict(details)),
            "effective_artifacts": [
                {
                    **binding,
                    "lifecycle_status": (
                        "promoted"
                        if details["disposition"] == "promote"
                        and binding["artifact_id"]
                        == details["capability_artifact_id"]
                        else {
                            "promote": "preserved",
                            "preserve": "preserved",
                            "archive": "archived",
                            "discard": "discarded",
                        }[details["disposition"]]
                    ),
                }
                for binding in bindings
            ],
        }
        if promotion is not None:
            closure["accepted_result_artifact_id"] = promotion[
                "accepted_result"
            ]["artifact_id"]
        return closure

    def _run_closure(self, run: Mapping[str, Any]) -> dict[str, Any] | None:
        lifecycle_records = [
            record for record in self.runtime.load_records(run["run_id"])
            if (record.get("event") or {}).get("event_type")
            == "lifecycle_disposition_recorded"
        ]
        if not lifecycle_records:
            return None
        if len(lifecycle_records) != 1:
            raise ProcessLibraryIntegrityError(
                "Process Run has multiple lifecycle dispositions"
            )
        return self._validate_lifecycle_record(run, lifecycle_records[0])

    def _promotions(self) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        promoted: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for run in self._iter_runs():
            closure = self._run_closure(run)
            if closure is None or closure["disposition"] != "promote":
                continue
            ref = closure["promoted_definition_ref"]
            key = (ref["definition_id"], ref["version"], ref["digest"])
            promoted.setdefault(key, []).append({
                "run_id": run["run_id"],
                "record_id": closure["record_id"],
                "recorded_at": closure["recorded_at"],
                "capability_artifact_id": closure["capability_artifact_id"],
                "accepted_result_artifact_id": closure[
                    "accepted_result_artifact_id"
                ],
            })
        return promoted

    def _authenticated_construction_registration(
        self,
        run: Mapping[str, Any],
        definition_ref: Mapping[str, Any],
        registration_record: Mapping[str, Any],
        registry: ProcessDefinitionRegistry,
    ) -> dict[str, Any]:
        """Reauthenticate one exact construction and registration chain."""

        ref = _normalize_ref(definition_ref)
        details = (registration_record.get("event") or {}).get("details") or {}
        required_details = {
            "operation", "authority_grant_ids", "construction_node_id",
            "construction_completion_record_id", "registration_node_id",
            "definition_ref", "definition_artifact_id",
            "definition_artifact_digest", "registration_artifact_id",
            "registration_artifact_digest", "registration_artifact_record_id",
            "registration_receipt", "registration_selector",
            "registry_locator", "registry_root_digest",
            "registry_storage_content_digest", "registry_receipt_digest",
        }
        if (
            registration_record.get("record_type") != "event"
            or (registration_record.get("event") or {}).get("event_type")
            != "process_definition_registered"
            or set(details) != required_details
            or details.get("operation")
            != "register_reusable_process_definition"
            or details.get("definition_ref") != ref
        ):
            raise ProcessLibraryIntegrityError(
                "runtime registration record has an invalid authoritative envelope"
            )
        try:
            registered_definition = registry.resolve(
                ref["definition_id"], ref["version"], ref["digest"]
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryIntegrityError(
                "runtime registration no longer resolves its exact stored definition"
            ) from exc

        construction_definition = self.runtime.load_definition(run["run_id"])
        nodes = {
            node["node_id"]: node
            for node in construction_definition["graph"]["nodes"]
        }
        construction_node_id = str(details.get("construction_node_id") or "")
        registration_node_id = str(details.get("registration_node_id") or "")
        construction_node = nodes.get(construction_node_id)
        registration_node = nodes.get(registration_node_id)
        target_contract = (
            (((construction_definition.get("input_schema") or {}).get(
                "properties"
            ) or {}).get("target_definition_ref") or {}).get("const")
        )
        if (
            construction_node is None
            or construction_node.get("kind") != "action"
            or construction_node.get("operation")
            != "construct_reusable_process_definition"
            or construction_node.get("external_effect") is not False
            or construction_node.get("next_node_id") != registration_node_id
            or registration_node is None
            or registration_node.get("kind") != "action"
            or registration_node.get("operation")
            != "register_reusable_process_definition"
            or registration_node.get("external_effect") is not False
            or target_contract != ref
            or registration_record.get("node_id") != registration_node_id
        ):
            raise ProcessLibraryIntegrityError(
                "runtime registration is not bound to the exact construction graph nodes"
            )

        records = self.runtime.load_records(run["run_id"])
        construction_completion = next(
            (
                record for record in records
                if record["record_id"]
                == details.get("construction_completion_record_id")
            ),
            None,
        )
        construction_route = (
            (((construction_completion or {}).get("event") or {}).get(
                "details"
            ) or {}).get("route") or {}
        )
        definition_artifact_id = str(
            details.get("definition_artifact_id") or ""
        )
        if (
            construction_completion is None
            or (construction_completion.get("event") or {}).get("event_type")
            != "node_advanced"
            or construction_completion.get("node_id") != construction_node_id
            or construction_completion["event"]["details"].get("from_node_id")
            != construction_node_id
            or construction_completion["event"]["details"].get("to_node_id")
            != registration_node_id
            or construction_completion["event"]["details"].get("advance_kind")
            != "action"
            or construction_route.get("operation")
            != "construct_reusable_process_definition"
            or definition_artifact_id
            not in construction_completion.get("artifact_ids", [])
            or int(construction_completion["sequence"])
            >= int(registration_record["sequence"])
        ):
            raise ProcessLibraryIntegrityError(
                "runtime registration lacks exact construction-node completion"
            )

        registration_completions = [
            record for record in records
            if int(record["sequence"]) > int(registration_record["sequence"])
            and (record.get("event") or {}).get("event_type")
            == "node_advanced"
            and record.get("node_id") == registration_node_id
            and ((record.get("event") or {}).get("details") or {}).get(
                "from_node_id"
            ) == registration_node_id
            and ((record.get("event") or {}).get("details") or {}).get(
                "to_node_id"
            ) == registration_node.get("next_node_id")
            and ((record.get("event") or {}).get("details") or {}).get(
                "advance_kind"
            ) == "action"
            and ((((record.get("event") or {}).get("details") or {}).get(
                "route"
            ) or {}).get("operation"))
            == "register_reusable_process_definition"
        ]
        if len(registration_completions) != 1:
            raise ProcessLibraryIntegrityError(
                "runtime registration lacks exact registration-node completion"
            )
        registration_completion = registration_completions[0]
        registration_artifact_id = str(
            details.get("registration_artifact_id") or ""
        )
        if registration_artifact_id not in registration_completion.get(
            "artifact_ids", []
        ):
            raise ProcessLibraryIntegrityError(
                "registration-node completion omits its exact receipt Artifact"
            )

        definition_artifact = self.runtime.load_artifact(
            run["run_id"], definition_artifact_id
        )
        registration_artifact = self.runtime.load_artifact(
            run["run_id"], registration_artifact_id
        )
        registration_artifact_record = next(
            (
                record for record in records
                if record["record_id"]
                == details.get("registration_artifact_record_id")
            ),
            None,
        )
        registration_record_details = (
            ((registration_artifact_record or {}).get("event") or {}).get(
                "details"
            ) or {}
        )
        expected_definition_digest = _canonical_definition_artifact_digest(
            registered_definition
        )
        receipt = details.get("registration_receipt")
        receipt_fields = {
            "definition_ref", "registered_at", "registry_locator",
            "idempotent", "activated", "storage_content_digest",
            "receipt_digest",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != receipt_fields:
            raise ProcessLibraryIntegrityError(
                "runtime registration receipt has an invalid shape"
            )
        receipt_body = {
            key: copy.deepcopy(value)
            for key, value in receipt.items()
            if key != "receipt_digest"
        }
        expected_locator = (
            "registry:process-definitions/"
            f"{ref['definition_id']}@{ref['version']}"
        )
        expected_registration_digest = _digest_text(json.dumps(
            dict(receipt), sort_keys=True, ensure_ascii=False
        ))
        accepted_result = self._accepted_linked_result(
            run, definition_artifact_id
        )
        if (
            definition_artifact["role"] != "process_definition"
            or definition_artifact["lineage"]["producing_node_id"]
            != construction_node_id
            or definition_artifact["identity"]["kind"] != "content_digest"
            or "complete_content"
            not in definition_artifact["identity"]["coverage"]
            or definition_artifact["identity"]["digest"]
            != expected_definition_digest
            or details.get("definition_artifact_digest")
            != expected_definition_digest
            or registration_artifact["role"] != "result"
            or registration_artifact["lineage"]["producing_node_id"]
            != registration_node_id
            or registration_artifact["lineage"]["source_artifact_ids"]
            != [definition_artifact_id]
            or registration_artifact_record is None
            or (registration_artifact_record.get("event") or {}).get(
                "event_type"
            ) != "artifact_recorded"
            or registration_artifact_record.get("node_id")
            != registration_node_id
            or registration_record_details.get("artifact_id")
            != registration_artifact_id
            or registration_artifact["lineage"]["event_record_id"]
            != registration_artifact_record["record_id"]
            or registration_record_details.get("identity_digest")
            != registration_artifact["identity"]["digest"]
            or registration_record_details.get("action")
            != "register_definition"
            or registration_record_details.get("selectors")
            != [details.get("registration_selector")]
            or registration_record_details.get("grant_ids")
            != details.get("authority_grant_ids")
            or not details.get("authority_grant_ids")
            or not set(details.get("authority_grant_ids") or []).issubset(
                set(registration_node["authority_grant_ids"])
            )
            or details.get("registration_selector")
            not in registration_node["artifact_access"]
            or int(registration_artifact_record["sequence"])
            >= int(registration_record["sequence"])
            or registration_artifact["identity"]["digest"]
            != expected_registration_digest
            or details.get("registration_artifact_digest")
            != expected_registration_digest
            or registration_record.get("artifact_ids")
            != [definition_artifact_id, registration_artifact_id]
            or receipt.get("definition_ref") != ref
            or receipt.get("registry_locator") != expected_locator
            or receipt.get("activated") is not False
            or not isinstance(receipt.get("idempotent"), bool)
            or receipt.get("storage_content_digest")
            != _digest_json(registered_definition)
            or receipt.get("receipt_digest") != _digest_json(receipt_body)
            or details.get("registry_locator") != expected_locator
            or details.get("registry_root_digest")
            != _digest_text(str(registry.root.resolve()))
            or details.get("registry_storage_content_digest")
            != receipt.get("storage_content_digest")
            or details.get("registry_receipt_digest")
            != receipt.get("receipt_digest")
            or accepted_result is None
            or accepted_result["artifact_id"] != registration_artifact_id
        ):
            raise ProcessLibraryIntegrityError(
                "construction, registration, registry, and acceptance identities differ"
            )
        return {
            "run_id": run["run_id"],
            "construction_node_id": construction_node_id,
            "construction_completion_record_id": construction_completion[
                "record_id"
            ],
            "registration_node_id": registration_node_id,
            "registration_record_id": registration_record["record_id"],
            "registration_completion_record_id": registration_completion[
                "record_id"
            ],
            "definition_artifact_id": definition_artifact_id,
            "definition_artifact_digest": expected_definition_digest,
            "accepted_result_artifact_id": registration_artifact_id,
            "accepted_result_digest": expected_registration_digest,
            "registry_locator": expected_locator,
            "registry_root_digest": details["registry_root_digest"],
            "registry_storage_content_digest": receipt[
                "storage_content_digest"
            ],
            "registry_receipt_digest": receipt["receipt_digest"],
        }

    def _construction_label_witnesses(self) -> list[dict[str, Any]]:
        """Return exact construct/register/invoke bridge evidence.

        Registration alone is insufficient. A witness requires one completed
        Run whose exact construction node, runtime-issued registration record,
        exact registry identity, registration-node completion, and accepted
        receipt all authenticate, plus a separate runtime-issued
        ``process_invoked`` record for that exact registered identity.
        Programming itself is deliberately excluded.
        """

        registry = self._registry_for_read()
        if registry is None:
            return []
        try:
            refs = [
                _normalize_ref(ref)
                for ref in registry.list_definition_refs()
                if ref.get("definition_id") != _PROGRAMMING_DEFINITION_ID
            ]
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryIntegrityError(
                "construction-label registry integrity failed"
            ) from exc
        if not refs:
            return []

        runs = self._iter_runs()
        registered_refs = {
            (ref["definition_id"], ref["version"], ref["digest"]): ref
            for ref in refs
        }
        constructions: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for run in runs:
            registration_records = [
                record for record in self.runtime.load_records(run["run_id"])
                if (record.get("event") or {}).get("event_type")
                == "process_definition_registered"
            ]
            if not registration_records:
                continue
            if run["state"] != "completed" or len(registration_records) != 1:
                raise ProcessLibraryIntegrityError(
                    "construction-label registration evidence is ambiguous or nonterminal"
                )
            details = registration_records[0]["event"]["details"]
            try:
                ref = _normalize_ref(details.get("definition_ref"))
            except ProcessLibraryInputRequired as exc:
                raise ProcessLibraryIntegrityError(
                    "construction-label registration has an invalid definition identity"
                ) from exc
            key = (ref["definition_id"], ref["version"], ref["digest"])
            if key not in registered_refs:
                raise ProcessLibraryIntegrityError(
                    "runtime registration no longer resolves its exact registry identity"
                )
            construction = self._authenticated_construction_registration(
                run,
                ref,
                registration_records[0],
                registry,
            )
            constructions.setdefault(key, []).append(construction)

        witnesses: list[dict[str, Any]] = []
        for parent in runs:
            for record in self.runtime.load_records(parent["run_id"]):
                event = record.get("event") or {}
                details = event.get("details") or {}
                if event.get("event_type") != "process_invoked":
                    continue
                try:
                    ref = _normalize_ref(details.get("child_definition_ref"))
                except ProcessLibraryInputRequired as exc:
                    raise ProcessLibraryIntegrityError(
                        "persisted invocation has an invalid definition identity"
                    ) from exc
                key = (ref["definition_id"], ref["version"], ref["digest"])
                if key not in constructions:
                    continue
                try:
                    child = self.runtime.load_run(str(details["child_run_id"]))
                except (KeyError, GovernedRuntimeError) as exc:
                    raise ProcessLibraryIntegrityError(
                        "persisted invocation no longer resolves its exact child Run"
                    ) from exc
                if (
                    child["definition_ref"] != ref
                    or child["relationships"]["invoked_by_run_id"] != parent["run_id"]
                ):
                    raise ProcessLibraryIntegrityError(
                        "persisted invocation differs from its child definition binding"
                    )
                for construction in constructions[key]:
                    witness = {
                        "definition_ref": copy.deepcopy(ref),
                        "construction": copy.deepcopy(construction),
                        "invocation": {
                            "parent_run_id": parent["run_id"],
                            "record_id": record["record_id"],
                            "sequence": record["sequence"],
                            "child_run_id": child["run_id"],
                        },
                    }
                    witnesses.append({
                        **witness,
                        "witness_digest": _digest_json(witness),
                    })
        witnesses.sort(key=lambda item: (
            item["definition_ref"]["definition_id"],
            item["definition_ref"]["version"],
            item["construction"]["run_id"],
            item["invocation"]["parent_run_id"],
            item["invocation"]["sequence"],
        ))
        return witnesses

    def _read_construction_label_decision(
        self,
        witnesses: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any] | None:
        path = self.construction_label_path
        if not path.exists():
            return None
        if not path.is_file() or path.is_symlink():
            raise ProcessLibraryIntegrityError(
                "construction-label decision path is not a real file"
            )
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProcessLibraryIntegrityError(
                "construction-label decision cannot be read"
            ) from exc
        required = {
            "schema_version", "decision", "label", "decision_by",
            "recorded_at", "witness", "witness_digest", "record_digest",
        }
        if not isinstance(record, dict) or set(record) != required:
            raise ProcessLibraryIntegrityError(
                "construction-label decision has an invalid envelope"
            )
        decision = record.get("decision")
        witness = record.get("witness")
        body = {key: copy.deepcopy(value) for key, value in record.items()
                if key != "record_digest"}
        if (
            record.get("schema_version") != CONSTRUCTION_LABEL_SCHEMA_VERSION
            or decision not in _CONSTRUCTION_LABEL_DECISIONS
            or record.get("label") != _CONSTRUCTION_LABEL_DECISIONS[decision]
            or record.get("decision_by") != "principal:user"
            or not isinstance(witness, Mapping)
            or record.get("witness_digest")
            != (witness.get("witness_digest") if isinstance(witness, Mapping) else None)
            or record.get("record_digest") != _digest_json(body)
            or witness not in witnesses
        ):
            raise ProcessLibraryIntegrityError(
                "construction-label decision no longer authenticates its bridge evidence"
            )
        return copy.deepcopy(record)

    def get_construction_label_gate(self) -> dict[str, Any]:
        """Project the bridge-trial label without ever renaming automatically."""

        with _construction_label_lock:
            witnesses = self._construction_label_witnesses()
            decision = self._read_construction_label_decision(witnesses)
        body = {
            "schema_version": CONSTRUCTION_LABEL_SCHEMA_VERSION,
            "current_label": decision["label"] if decision else "Programming",
            "automatic_rename": False,
            "decision_available": bool(witnesses) and decision is None,
            "status": (
                "decided" if decision is not None
                else "awaiting_user_decision" if witnesses
                else "bridge_trial_incomplete"
            ),
            "decision": copy.deepcopy(decision),
            "qualifying_witnesses": copy.deepcopy(witnesses),
        }
        return {**body, "gate_digest": _digest_json(body)}

    def decide_construction_label(
        self,
        decision: str,
        *,
        decision_by: str,
    ) -> dict[str, Any]:
        exact_decision = str(decision or "").strip()
        if exact_decision not in _CONSTRUCTION_LABEL_DECISIONS:
            raise ProcessLibraryInputRequired(
                "decision must be keep_programming or use_build"
            )
        if str(decision_by or "").strip() != "principal:user":
            raise AuthorityDeniedError(
                "only principal:user may decide the construction entry label"
            )
        with _construction_label_lock:
            witnesses = self._construction_label_witnesses()
            existing = self._read_construction_label_decision(witnesses)
            if existing is not None:
                if existing["decision"] != exact_decision:
                    raise ProcessLibraryConflict(
                        "construction entry label was already decided"
                    )
                return self.get_construction_label_gate()
            if not witnesses:
                raise ProcessLibraryInputRequired(
                    "Build is unavailable until a non-Programming Process Definition "
                    "has been constructed, registered, and invoked"
                )
            witness = copy.deepcopy(witnesses[0])
            record = {
                "schema_version": CONSTRUCTION_LABEL_SCHEMA_VERSION,
                "decision": exact_decision,
                "label": _CONSTRUCTION_LABEL_DECISIONS[exact_decision],
                "decision_by": "principal:user",
                "recorded_at": self._now(),
                "witness": witness,
                "witness_digest": witness["witness_digest"],
            }
            record["record_digest"] = _digest_json(record)
            path = self.construction_label_path
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.parent.is_symlink() or path.is_symlink():
                raise ProcessLibraryIntegrityError(
                    "construction-label decision path may not use symlinks"
                )
            _runtime_paths.atomic_write_text(
                path,
                json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            )
        return self.get_construction_label_gate()

    @staticmethod
    def _scope_visible(scope: Mapping[str, Any], project_ref: str | None) -> bool:
        if project_ref is None:
            return True
        if scope["kind"] == "universal":
            return True
        return scope["selector"] == project_ref

    def list_entries(
        self,
        *,
        project_ref: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """Return authenticated exact versions; never select a latest version."""

        canonical_project = (
            canonicalize_project_nexus(project_ref) if project_ref else None
        )
        promotions = self._promotions()
        entries = []
        try:
            definitions: dict[tuple[str, str, str], dict[str, Any]] = {}
            registry = self._registry_for_read()
            refs = registry.list_definition_refs() if registry is not None else []
            for ref in refs:
                definition = registry.resolve(
                    ref["definition_id"], ref["version"], ref["digest"]
                )
                definitions[(
                    ref["definition_id"], ref["version"], ref["digest"],
                )] = definition
            for definition in self._validated_seed_definitions():
                ref = _definition_ref(definition)
                key = (ref["definition_id"], ref["version"], ref["digest"])
                existing = definitions.get(key)
                if existing is not None and existing != definition:
                    raise ProcessLibraryIntegrityError(
                        "registered definition conflicts with its canonical seed"
                    )
                definitions[key] = definition
            for key, definition in definitions.items():
                ref = _definition_ref(definition)
                if (
                    not include_archived
                    and definition["status"] in {"archived", "retired"}
                ):
                    continue
                if not self._scope_visible(definition["scope"], canonical_project):
                    continue
                promotion_records = promotions.get(key, [])
                available = bool(promotion_records)
                manifest = definition["package_manifest"]
                aliases = sorted({
                    definition["title"].casefold(),
                    definition["definition_id"].rsplit("/", 1)[-1].replace("-", " "),
                    *[str(label).replace("-", " ") for label in definition.get("labels", [])],
                })
                automation_contract = (
                    (definition.get("output_schema") or {}).get("x-ora-process")
                )
                automated_execution = bool(
                    isinstance(automation_contract, Mapping)
                    and automation_contract.get("schema_version")
                    == "ora.process-automation/1.0"
                    and automation_contract.get("external_effects") is False
                    and automation_contract.get("triggers") is False
                )
                entries.append({
                    "kind": "process_definition",
                    "id": definition["definition_id"].rsplit("/", 1)[-1],
                    "display_name": definition["title"],
                    "display_description": definition["purpose"],
                    "category": "process-definition",
                    "definition_ref": copy.deepcopy(ref),
                    "scope": copy.deepcopy(definition["scope"]),
                    "status": definition["status"],
                    "lifecycle_status": (
                        "available" if available else "registered"
                    ),
                    "promoted": available,
                    "activated": False,
                    "manual_invocation_available": available and not automated_execution,
                    "automated_execution_available": available and automated_execution,
                    "input_schema": (
                        copy.deepcopy(definition["input_schema"])
                        if automated_execution else None
                    ),
                    "standing_automation": False,
                    "entrypoints": copy.deepcopy(
                        definition["input_schema"].get("properties", {})
                        .get("entrypoint", {}).get("enum", [])
                    ),
                    "package": {
                        "package_id": manifest["package_id"],
                        "package_version": manifest["package_version"],
                        "entry_member_id": manifest["entry_member_id"],
                        "members": copy.deepcopy(manifest["members"]),
                    },
                    "promotion_records": copy.deepcopy(promotion_records),
                    "aliases": aliases,
                })
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryIntegrityError(
                "Process Library registry integrity failed"
            ) from exc
        entries.sort(key=lambda item: (
            item["display_name"].casefold(),
            item["definition_ref"]["definition_id"],
            item["definition_ref"]["version"],
        ))
        body = {
            "schema_version": LIBRARY_SCHEMA_VERSION,
            "generated_at": self._now(),
            "project_ref": canonical_project,
            "entries": entries,
            "standing_automation_included": False,
        }
        return {**body, "catalog_digest": _digest_json(body)}

    @staticmethod
    def _validate_ready_invocation_entry(
        entry_contract: Mapping[str, Any],
        *,
        definition_ref: Mapping[str, Any],
        objective: str,
        project_ref: str,
    ) -> dict[str, Any]:
        fields = {
            "schema_version", "source", "objective", "project_ref",
            "project_confirmed", "intent", "classification_basis", "status",
            "next_action", "definition_ref", "framework_id", "authority_effects",
            "creates_process_run", "contract_digest",
        }
        if not isinstance(entry_contract, Mapping) or set(entry_contract) != fields:
            raise ProcessLibraryInputRequired(
                "manual invocation requires an exact ready entry contract"
            )
        contract = copy.deepcopy(dict(entry_contract))
        digest_body = {
            key: copy.deepcopy(value)
            for key, value in contract.items() if key != "contract_digest"
        }
        canonical_project = canonicalize_project_nexus(project_ref)
        if (
            contract["contract_digest"] != _digest_json(digest_body)
            or contract["source"] != "process_library"
            or contract["objective"] != objective
            or contract["project_ref"] != canonical_project
            or contract["intent"] != "capability_invocation"
            or contract["status"] != "ready"
            or contract["next_action"] != "begin_exact_definition_invocation"
            or contract["definition_ref"] != dict(definition_ref)
            or contract["framework_id"] is not None
            or contract["authority_effects"] != []
            or contract["creates_process_run"] is not False
        ):
            raise ProcessLibraryConflict(
                "entry contract does not authorize this exact manual invocation"
            )
        return contract

    def _manual_invocation_state(self, run_id: str) -> dict[str, Any]:
        try:
            run = self.runtime.load_run(run_id)
            records = self.runtime.load_records(run_id)
            definition = self.runtime.load_definition(run_id)
        except GovernedRuntimeError as exc:
            raise ProcessLibraryIntegrityError(
                "manual invocation Run integrity failed"
            ) from exc
        invocation_records = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "manual_process_invoked"
        ]
        result_records = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "manual_process_result_recorded"
        ]
        capture_records = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "manual_process_output_captured"
        ]
        if (
            len(invocation_records) != 1
            or len(capture_records) > 1
            or len(result_records) > 1
            or (result_records and not capture_records)
        ):
            raise ProcessLibraryIntegrityError(
                "manual invocation records are missing or ambiguous"
            )
        invocation = invocation_records[0]
        details = invocation["event"]["details"]
        execution_contract = _manual_execution_contract(
            definition, details.get("definition_inputs") or {}
        )
        details_body = {
            key: copy.deepcopy(value)
            for key, value in details.items() if key != "invocation_digest"
        }
        if (
            details.get("definition_ref") != run["definition_ref"]
            or details.get("entry_node_id")
            != definition["graph"]["entry_node_id"]
            or details.get("invocation_digest") != _digest_json(details_body)
            or run["input_bindings"] != {
                key: copy.deepcopy(details[key])
                for key in (
                    "invocation_id", "dialogue_ref", "project_ref", "objective",
                    "definition_inputs", "definition_input_digest",
                    "entry_contract_digest", "request_context_digest",
                )
            }
        ):
            raise ProcessLibraryIntegrityError(
                "manual invocation record differs from its exact Run binding"
            )
        result_view = None
        response_text = None
        if capture_records:
            capture = capture_records[0]
            capture_details = capture["event"]["details"]
            capture_body = {
                key: copy.deepcopy(value)
                for key, value in capture_details.items()
                if key != "output_capture_digest"
            }
            if (
                capture_details.get("invocation_record_id")
                != invocation["record_id"]
                or capture_details.get("invocation_id")
                != details["invocation_id"]
                or capture_details.get("invocation_digest")
                != details["invocation_digest"]
                or capture_details.get("definition_ref") != run["definition_ref"]
                or capture_details.get("entry_node_id")
                != definition["graph"]["entry_node_id"]
                or capture_details.get("response_digest")
                != _digest_text(str(capture_details.get("response_text") or ""))
                or capture_details.get("output_capture_digest")
                != _digest_json(capture_body)
            ):
                raise ProcessLibraryIntegrityError(
                    "manual invocation output capture is invalid"
                )
            response_text = str(capture_details["response_text"])
        if result_records:
            result_record = result_records[0]
            result_details = result_record["event"]["details"]
            result_body = {
                key: copy.deepcopy(value)
                for key, value in result_details.items()
                if key != "result_binding_digest"
            }
            try:
                result = self.runtime.load_artifact(
                    run_id, result_details["result_artifact_id"]
                )
                evidence = self.runtime.load_artifact(
                    run_id, result_details["evidence_artifact_id"]
                )
            except (KeyError, GovernedRuntimeError) as exc:
                raise ProcessLibraryIntegrityError(
                    "manual invocation result Artifacts are unavailable"
                ) from exc
            if (
                result_record["node_id"]
                != result_details.get("current_node_id")
                or result_record["node_id"] not in {
                    node["node_id"]
                    for node in self.runtime.load_definition(run_id)["graph"]["nodes"]
                }
                or result_details.get("invocation_record_id")
                != invocation["record_id"]
                or result_details.get("invocation_digest")
                != details["invocation_digest"]
                or result_details.get("definition_ref") != run["definition_ref"]
                or result_details.get("result_binding_digest")
                != _digest_json(result_body)
                or result_details.get("response_digest")
                != _digest_text(response_text or "")
                or result_details.get("response_text") != response_text
                or result_details.get("result_identity_digest")
                != result["identity"]["digest"]
                or result_details.get("evidence_identity_digest")
                != evidence["identity"]["digest"]
                or result["role"] != "result"
                or evidence["role"] != "evidence"
                or result["artifact_id"]
                not in evidence["lineage"]["source_artifact_ids"]
            ):
                raise ProcessLibraryIntegrityError(
                    "manual invocation result binding is invalid"
                )
            result_view = {
                "record_id": result_record["record_id"],
                "result_artifact_id": result["artifact_id"],
                "result_identity_digest": result["identity"]["digest"],
                "evidence_artifact_id": evidence["artifact_id"],
                "evidence_identity_digest": evidence["identity"]["digest"],
                "acceptance_status": "pending_independent_review",
            }
        body = {
            "schema_version": MANUAL_INVOCATION_SCHEMA_VERSION,
            "status": (
                "result_recorded" if result_view
                else "output_captured" if capture_records
                else "running"
            ),
            "run_id": run_id,
            "run_state": run["state"],
            "current_node_id": run["current_node_id"],
            "invocation_id": details["invocation_id"],
            "invocation_record_id": invocation["record_id"],
            "invocation_digest": details["invocation_digest"],
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "dialogue_ref": details["dialogue_ref"],
            "project_ref": details["project_ref"],
            "objective": details["objective"],
            "definition_inputs": copy.deepcopy(details["definition_inputs"]),
            "definition_input_digest": details["definition_input_digest"],
            "entry_contract_digest": details["entry_contract_digest"],
            "request_context_digest": details["request_context_digest"],
            "execution_contract": execution_contract,
            "result": result_view,
            "response_text": response_text,
        }
        return {**body, "state_digest": _digest_json(body)}

    def begin_manual_invocation(
        self,
        *,
        dialogue_ref: str,
        project_ref: str,
        objective: str,
        definition_ref: Mapping[str, Any],
        definition_inputs: Mapping[str, Any] | None,
        entry_contract: Mapping[str, Any],
        request_context: Mapping[str, Any],
        principal_id: str = "principal:user",
    ) -> dict[str, Any]:
        """Create or resume one exact, restart-safe Process Library Run."""

        ref = _normalize_ref(definition_ref)
        canonical_project = canonicalize_project_nexus(project_ref)
        if not dialogue_ref or not objective or not principal_id:
            raise ProcessLibraryInputRequired(
                "manual invocation requires Dialogue, project, objective, and principal"
            )
        contract = self._validate_ready_invocation_entry(
            entry_contract,
            definition_ref=ref,
            objective=objective,
            project_ref=canonical_project,
        )
        catalog = self.list_entries(project_ref=canonical_project)
        matches = [
            item for item in catalog["entries"]
            if item["definition_ref"] == ref
        ]
        if len(matches) != 1 or not matches[0]["manual_invocation_available"]:
            raise ProcessLibraryConflict(
                "exact Process Definition is unavailable for manual invocation"
            )
        registry = self._registry_for_read()
        if registry is None:
            raise ProcessLibraryIntegrityError(
                "manual invocation requires the authenticated definition registry"
            )
        try:
            definition = registry.resolve(
                ref["definition_id"], ref["version"], ref["digest"]
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryIntegrityError(
                "exact Process Definition could not be resolved"
            ) from exc
        if definition["status"] not in {"approved", "active"}:
            raise ProcessLibraryConflict(
                "inactive Process Definition cannot be manually invoked"
            )
        inputs = _validate_definition_inputs(definition, definition_inputs)
        _manual_execution_contract(definition, inputs)
        if not isinstance(request_context, Mapping):
            raise ProcessLibraryInputRequired(
                "manual invocation request context must be an object"
            )
        context = copy.deepcopy(dict(request_context))
        try:
            json.dumps(context, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ProcessLibraryInputRequired(
                "manual invocation request context must be JSON-serializable"
            ) from exc
        definition_input_digest = _digest_json(inputs)
        request_context_digest = _digest_json(context)
        invocation_basis = {
            "dialogue_ref": dialogue_ref,
            "project_ref": canonical_project,
            "objective": objective,
            "definition_ref": ref,
            "definition_input_digest": definition_input_digest,
            "entry_contract_digest": contract["contract_digest"],
            "request_context_digest": request_context_digest,
        }
        identity = _digest_json(invocation_basis).split(":", 1)[1]
        invocation_id = "invocation-" + identity[:32]
        run_id = "run-invocation-" + identity[:40]
        input_bindings = {
            "invocation_id": invocation_id,
            "dialogue_ref": dialogue_ref,
            "project_ref": canonical_project,
            "objective": objective,
            "definition_inputs": inputs,
            "definition_input_digest": definition_input_digest,
            "entry_contract_digest": contract["contract_digest"],
            "request_context_digest": request_context_digest,
        }
        try:
            run = self.runtime.load_run(run_id)
            if (
                run["definition_ref"] != ref
                or run["input_bindings"] != input_bindings
            ):
                raise ProcessLibraryConflict(
                    "manual invocation identity resolves to a different Run"
                )
        except RunNotFoundError:
            now = self._now()
            entrypoint = str(inputs.get("entrypoint") or "manual")
            run = {
                "schema_version": _contracts.CONTRACT_SCHEMA_VERSION,
                "object_family": "process_run",
                "run_id": run_id,
                "definition_ref": copy.deepcopy(ref),
                "state": "ready",
                "entrypoint": entrypoint,
                "current_node_id": definition["graph"]["entry_node_id"],
                "input_bindings": copy.deepcopy(input_bindings),
                "contracts": _manual_invocation_contracts(
                    definition,
                    invocation_id=invocation_id,
                    objective=objective,
                    principal_id=principal_id,
                    now=now,
                ),
                "relationships": {
                    "parent_run_id": None,
                    "invoked_by_run_id": None,
                    "invoked_definition_refs": [],
                    "constructed_definition_refs": [],
                    "return_to_run_id": None,
                },
                "artifact_ids": [],
                "last_sequence": 0,
                "created_at": now,
                "updated_at": now,
                "labels": ["governed", "manual-invocation"],
            }
            self.runtime.create_run(definition, run)
        invocation = self.runtime.bind_manual_process_invocation(
            run_id,
            invocation_id=invocation_id,
            dialogue_ref=dialogue_ref,
            project_ref=canonical_project,
            objective=objective,
            definition_inputs=inputs,
            definition_input_digest=definition_input_digest,
            entry_contract_digest=contract["contract_digest"],
            request_context_digest=request_context_digest,
        )
        run = self.runtime.load_run(run_id)
        if run["state"] == "ready":
            self.runtime.start_run(
                run_id, reason="Exact Process Library invocation started"
            )
        state = self._manual_invocation_state(run_id)
        if state["invocation_record_id"] != invocation["record_id"]:
            raise ProcessLibraryIntegrityError(
                "manual invocation response differs from its runtime record"
            )
        if state["status"] == "output_captured":
            state = self.complete_manual_invocation(
                run_id, str(state["response_text"])
            )
        return state

    def complete_manual_invocation(
        self,
        run_id: str,
        response_text: str,
    ) -> dict[str, Any]:
        """Persist a model-produced result without fabricating acceptance."""

        state = self._manual_invocation_state(run_id)
        matches = [
            item
            for item in self.list_entries(project_ref=state["project_ref"])[
                "entries"
            ]
            if item["definition_ref"] == state["definition_ref"]
        ]
        if len(matches) != 1 or not matches[0]["manual_invocation_available"]:
            raise ProcessLibraryConflict(
                "manual invocation definition became unavailable before result binding"
            )
        registry = self._registry_for_read()
        if registry is None:
            raise ProcessLibraryIntegrityError(
                "manual invocation result requires the authenticated registry"
            )
        try:
            registered_definition = registry.resolve(
                state["definition_ref"]["definition_id"],
                state["definition_ref"]["version"],
                state["definition_ref"]["digest"],
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryIntegrityError(
                "manual invocation definition failed result-time authentication"
            ) from exc
        if registered_definition != self.runtime.load_definition(run_id):
            raise ProcessLibraryIntegrityError(
                "manual invocation Run definition differs from the exact registry body"
            )
        if state["status"] == "result_recorded":
            if state["response_text"] != response_text:
                raise ProcessLibraryConflict(
                    "manual invocation already returned a different result"
                )
            return state
        capture = self.runtime.capture_manual_process_output(
            run_id,
            invocation_record_id=state["invocation_record_id"],
            response_text=response_text,
        )
        if capture["event"]["details"]["response_digest"] != _digest_text(
            response_text
        ):
            raise ProcessLibraryIntegrityError(
                "manual invocation output capture differs from its response"
            )
        run = self.runtime.load_run(run_id)
        definition = self.runtime.load_definition(run_id)
        nodes = {
            node["node_id"]: node for node in definition["graph"]["nodes"]
        }
        invocation = next(
            record for record in self.runtime.load_records(run_id)
            if (record.get("event") or {}).get("event_type")
            == "manual_process_invoked"
        )
        entry_node_id = invocation["event"]["details"]["entry_node_id"]
        entry_node = nodes[entry_node_id]
        if (
            entry_node["kind"] != "action"
            or entry_node.get("external_effect") is not False
        ):
            raise ProcessLibraryConflict(
                "manual Dialogue execution supports only a non-external action entry"
            )
        verification_node_id = str(entry_node["next_node_id"])
        verification_node = nodes.get(verification_node_id)
        if verification_node is None or verification_node["kind"] != "verification_boundary":
            raise ProcessLibraryConflict(
                "manual Dialogue result requires a declared verification boundary"
            )
        selector = (
            "scope:declared_outputs"
            if "scope:declared_outputs" in entry_node["artifact_access"]
            else str(entry_node["artifact_access"][0])
        )
        conditions = ["exact_manual_invocation_binding"]
        suffix = state["invocation_id"].rsplit("-", 1)[-1]
        result_id = "manual-result-" + suffix
        evidence_id = "manual-execution-evidence-" + suffix
        try:
            result = self.runtime.load_artifact(run_id, result_id)
            if result["identity"]["digest"] != _digest_text(response_text):
                raise ProcessLibraryConflict(
                    "persisted manual result differs from the current response"
                )
        except RunNotFoundError:
            result = self.runtime.record_inline_artifact(
                run_id,
                result_id,
                response_text,
                role="result",
                node_id=entry_node_id,
                action="produce_artifact",
                selector=selector,
                satisfied_conditions=conditions,
            )["artifact"]
        run = self.runtime.load_run(run_id)
        if run["current_node_id"] == entry_node_id:
            self.runtime.complete_action_node(
                run_id,
                entry_node["operation"],
                reason="Exact manual invocation result produced",
                artifact_ids=[result_id],
            )
        elif run["current_node_id"] != verification_node_id:
            raise ProcessLibraryConflict(
                "manual invocation moved outside its result verification boundary"
            )
        evidence_text = json.dumps({
            "schema_version": "ora.manual-invocation-evidence/1.0",
            "invocation_record_id": state["invocation_record_id"],
            "invocation_digest": state["invocation_digest"],
            "result_artifact_id": result_id,
            "result_identity_digest": result["identity"]["digest"],
            "observation": "Pipeline returned this exact response; acceptance is pending independent review.",
        }, sort_keys=True, ensure_ascii=False)
        try:
            evidence = self.runtime.load_artifact(run_id, evidence_id)
            if evidence["identity"]["digest"] != _digest_text(evidence_text):
                raise ProcessLibraryConflict(
                    "persisted manual execution evidence has drifted"
                )
        except RunNotFoundError:
            evidence = self.runtime.record_inline_artifact(
                run_id,
                evidence_id,
                evidence_text,
                role="evidence",
                node_id=verification_node_id,
                action="record_evidence",
                selector=selector,
                source_artifact_ids=[result_id],
                satisfied_conditions=conditions,
                media_type="application/json",
            )["artifact"]
        self.runtime.record_manual_process_result(
            run_id,
            invocation_record_id=state["invocation_record_id"],
            result_artifact_id=result_id,
            evidence_artifact_id=evidence_id,
            response_text=response_text,
        )
        return self._manual_invocation_state(run_id)

    def get_run_lifecycle(self, run_id: str) -> dict[str, Any]:
        try:
            run = self.runtime.load_run(run_id)
        except RunNotFoundError:
            raise
        except GovernedRuntimeError as exc:
            raise ProcessLibraryIntegrityError(
                "Process Run lifecycle source integrity failed"
            ) from exc
        closure = self._run_closure(run)
        promotable = []
        if run["state"] == "completed" and closure is None:
            try:
                registry = self._registry_for_read()
                refs = registry.list_definition_refs() if registry is not None else []
                for ref in refs:
                    try:
                        binding = self._promotion_binding(run, ref)
                    except ProcessLibraryInputRequired:
                        continue
                    promotable.append({
                        "definition_ref": copy.deepcopy(ref),
                        "display_name": binding["definition"]["title"],
                        "capability_artifact_id": binding[
                            "capability_artifact"
                        ]["artifact_id"],
                        "accepted_result_artifact_id": binding[
                            "accepted_result"
                        ]["artifact_id"],
                    })
            except ProcessDefinitionRegistryError as exc:
                raise ProcessLibraryIntegrityError(
                    "Process Library registry integrity failed"
                ) from exc
        actions = []
        if run["state"] in TERMINAL_RUN_STATES and closure is None:
            actions = ["preserve", "archive", "discard"]
            if promotable:
                actions.insert(0, "promote")
        body = {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "run_id": run_id,
            "run_state": run["state"],
            "principal_id": run["contracts"]["authority"]["principal_id"],
            "status": (
                "closed" if closure is not None
                else "awaiting_disposition"
                if run["state"] in TERMINAL_RUN_STATES
                else "not_terminal"
            ),
            "available_actions": actions,
            "promote_options": promotable,
            "closure": closure,
        }
        return {**body, "lifecycle_digest": _digest_json(body)}

    def close_run(
        self,
        run_id: str,
        *,
        disposition: str,
        decision_by: str,
        promoted_definition_ref: Mapping[str, Any] | None = None,
        capability_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        exact_disposition = str(disposition or "").strip().lower()
        if exact_disposition not in LIFECYCLE_DISPOSITIONS:
            raise ProcessLibraryInputRequired(
                "disposition must be promote, preserve, archive, or discard"
            )
        try:
            run = self.runtime.load_run(run_id)
            if exact_disposition == "promote":
                binding = self._promotion_binding(
                    run, promoted_definition_ref, capability_artifact_id
                )
                promoted_definition_ref = binding["definition_ref"]
                capability_artifact_id = binding[
                    "capability_artifact"
                ]["artifact_id"]
            record = self.runtime.record_lifecycle_disposition(
                run_id,
                exact_disposition,
                decision_by=decision_by,
                promoted_definition_ref=promoted_definition_ref,
                capability_artifact_id=capability_artifact_id,
            )
        except RunConflictError as exc:
            raise ProcessLibraryConflict(str(exc)) from exc
        except AuthorityDeniedError:
            raise
        except GovernedRuntimeError as exc:
            raise ProcessLibraryInputRequired(str(exc)) from exc
        lifecycle = self.get_run_lifecycle(run_id)
        if (
            lifecycle["status"] != "closed"
            or lifecycle["closure"]["record_id"] != record["record_id"]
        ):
            raise ProcessLibraryIntegrityError(
                "persisted Run lifecycle disposition did not reauthenticate"
            )
        return lifecycle


__all__ = [
    "CONSTRUCTION_LABEL_SCHEMA_VERSION",
    "LIBRARY_SCHEMA_VERSION",
    "LIFECYCLE_DISPOSITIONS",
    "LIFECYCLE_SCHEMA_VERSION",
    "ProcessLibraryConflict",
    "ProcessLibraryError",
    "ProcessLibraryInputRequired",
    "ProcessLibraryIntegrityError",
    "ProcessLibraryLifecycleService",
]
