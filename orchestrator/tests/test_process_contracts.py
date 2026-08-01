"""Contract-level proof for the Phase 1.3 governed-process kernel."""

from __future__ import annotations

import copy
import inspect
import json
import sys
import unittest
from pathlib import Path


_ORCHESTRATOR = Path(__file__).resolve().parent.parent
if str(_ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(_ORCHESTRATOR))

import process_contracts as pc  # noqa: E402


NOW = "2026-07-16T18:00:00-07:00"
LATER = "2026-07-16T19:00:00-07:00"
DIGEST = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def definition_ref(definition_id: str = "programming/change", version: str = "1.0.0") -> dict:
    return {"definition_id": definition_id, "version": version, "digest": DIGEST}


def identity(digest: str = DIGEST) -> dict:
    return {
        "kind": "content_digest",
        "digest": digest,
        "coverage": ["complete_content"],
        "captured_at": NOW,
        "fresh_until": LATER,
    }


def package_manifest(package_id: str = "programming/change") -> dict:
    return {
        "schema_version": pc.PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "package_version": "1.0.0",
        "definition_ref": definition_ref(package_id),
        "entry_member_id": "definition",
        "members": [
            {
                "member_id": "definition",
                "role": "process_definition",
                "required": True,
                "media_type": "application/json",
                "locator": {"kind": "registry", "ref": f"processes/{package_id}@1.0.0"},
                "identity": identity(),
            },
            {
                "member_id": "instructions",
                "role": "instruction",
                "required": True,
                "media_type": "text/markdown",
                "locator": {"kind": "file", "ref": "capability/instructions.md"},
                "identity": identity(DIGEST_B),
            },
            {
                "member_id": "verification",
                "role": "test",
                "required": True,
                "media_type": "text/x-python",
                "locator": {"kind": "file", "ref": "proof/test_capability.py"},
                "identity": identity("sha256:" + "c" * 64),
            },
        ],
    }


def compact_graph() -> dict:
    return {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": "governed/change",
        "entry_node_id": "approve",
        "nodes": [
            {
                "node_id": "approve",
                "kind": "human_checkpoint",
                "label": "Approve the plan",
                "authority_request_type": "plan_approval",
                "on_approved_node_id": "act",
                "on_denied_node_id": "blocked",
            },
            {
                "node_id": "act",
                "kind": "action",
                "label": "Perform the approved change",
                "operation": "apply_approved_change",
                "next_node_id": "verify",
                "authority_grant_ids": ["mutation"],
                "artifact_access": ["scope:declared_inputs", "scope:declared_outputs"],
                "evidence_requirement_ids": ["result_verified"],
                "external_effect": True,
            },
            {
                "node_id": "verify",
                "kind": "verification_boundary",
                "label": "Inspect independent evidence",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {"ACCEPT": "accepted", "REVISE": "act", "BLOCKED": "blocked"},
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }


def complete_grammar_graph() -> dict:
    """One connected graph exercising every required grammar production."""

    return {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": "grammar/all-productions",
        "entry_node_id": "sequence",
        "nodes": [
            {
                "node_id": "sequence",
                "kind": "sequence",
                "label": "Ordered work",
                "member_node_ids": ["prepare", "parallel"],
                "next_node_id": "prepare",
            },
            {
                "node_id": "prepare",
                "kind": "action",
                "label": "Prepare",
                "operation": "prepare_inputs",
                "next_node_id": "parallel",
                "authority_grant_ids": ["read"],
                "artifact_access": ["scope:inputs"],
                "evidence_requirement_ids": [],
                "external_effect": False,
            },
            {
                "node_id": "parallel",
                "kind": "parallel_branch",
                "label": "Independent checks",
                "branch_node_ids": ["branch_a", "branch_b"],
                "join_node_id": "join",
            },
            {
                "node_id": "branch_a",
                "kind": "action",
                "label": "Check A",
                "operation": "check_a",
                "next_node_id": "join",
                "authority_grant_ids": ["read"],
                "artifact_access": ["scope:inputs"],
                "evidence_requirement_ids": ["proof"],
                "external_effect": False,
            },
            {
                "node_id": "branch_b",
                "kind": "action",
                "label": "Check B",
                "operation": "check_b",
                "next_node_id": "join",
                "authority_grant_ids": ["read"],
                "artifact_access": ["scope:inputs"],
                "evidence_requirement_ids": ["proof"],
                "external_effect": False,
            },
            {
                "node_id": "join",
                "kind": "join",
                "label": "Join checks",
                "expected_branch_node_ids": ["branch_a", "branch_b"],
                "next_node_id": "decision",
            },
            {
                "node_id": "decision",
                "kind": "decision",
                "label": "Select route",
                "routes": [{"condition": "work_required", "target_node_id": "loop"}],
                "default_node_id": "checkpoint",
            },
            {
                "node_id": "loop",
                "kind": "bounded_loop",
                "label": "Bounded correction",
                "body_node_id": "verify",
                "exit_node_id": "checkpoint",
                "max_iterations": 12,
                "progress_evidence_requirement_ids": ["proof"],
            },
            {
                "node_id": "verify",
                "kind": "verification_boundary",
                "label": "Verify progress",
                "evidence_requirement_ids": ["proof"],
                "routes": {"PROCEED": "loop", "REPLAN": "checkpoint"},
            },
            {
                "node_id": "checkpoint",
                "kind": "human_checkpoint",
                "label": "Reserved decision",
                "authority_request_type": "scope_expansion",
                "on_approved_node_id": "call",
                "on_denied_node_id": "blocked",
                "on_unavailable_node_id": "blocked",
            },
            {
                "node_id": "call",
                "kind": "process_call",
                "label": "Invoke governed child",
                "definition_ref": definition_ref("generic/child"),
                "input_bindings": {"source": "artifact:prepared"},
                "return_node_id": "return",
                "on_error_node_id": "blocked",
            },
            {
                "node_id": "return",
                "kind": "process_return",
                "label": "Return child evidence",
                "output_bindings": {"proof": "child.result"},
                "next_node_id": "accepted",
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }


def process_definition(
    definition_id: str = "programming/change",
    title: str = "Governed repository change",
    input_properties: dict | None = None,
    output_properties: dict | None = None,
) -> dict:
    return {
        "schema_version": pc.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_definition",
        "definition_id": definition_id,
        "version": "1.0.0",
        "digest": DIGEST,
        "title": title,
        "purpose": "Produce a verified result under an approved plan and bounded authority.",
        "status": "approved",
        "scope": {"kind": "project", "selector": "project:trial"},
        "input_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": input_properties or {"repository_ref": {"type": "string"}},
            "additionalProperties": False,
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": output_properties or {"change_artifact_id": {"type": "string"}},
            "additionalProperties": False,
        },
        "graph": compact_graph(),
        "package_manifest": package_manifest(definition_id),
        "labels": ["governed", "reusable"],
    }


def contract_set(node_id: str = "verify") -> dict:
    return {
        "approved_plan": {
            "plan_id": "plan-001",
            "version": "1.0",
            "digest": DIGEST_B,
            "objective": "Produce the declared result and prove it meets the acceptance criteria.",
            "approved_by": "principal-001",
            "approved_at": NOW,
            "approved_node_ids": ["approve", "act", "verify", "accepted", "blocked"],
            "constraints": ["Stay within declared artifact scope"],
            "non_goals": ["Do not activate or publish the capability"],
        },
        "authority": {
            "principal_id": "principal-001",
            "grants": [
                {
                    "grant_id": "mutation",
                    "actions": ["inspect", "mutate", "test", "evaluate_evidence"],
                    "resource_selectors": ["scope:declared_inputs", "scope:declared_outputs"],
                    "effect_types": ["local_reversible"],
                    "conditions": ["approved_plan_digest_matches"],
                }
            ],
            "reserved_actions": ["activate", "publish", "expand_scope"],
        },
        "artifact_scope": {
            "read_selectors": ["scope:declared_inputs"],
            "write_selectors": ["scope:declared_outputs"],
            "external_effect_selectors": [],
        },
        "bounded_judgment": [
            {
                "judgment_id": "quality-boundary",
                "node_id": node_id,
                "verified_circumstances": ["approved plan and current artifact identities are bound"],
                "question": "Does the current evidence support an allowed transition?",
                "permitted_conclusions": ["criteria_met", "execution_defect", "plan_defect", "definition_defect"],
                "permitted_directives": ["ACCEPT", "REVISE", "REPLAN", "REDEFINE", "BLOCKED"],
                "permitted_actions": ["evaluate_evidence"],
                "authority_grant_ids": ["mutation"],
                "artifact_selectors": ["scope:declared_outputs"],
                "required_evidence_ids": ["result_verified"],
                "evaluator_boundary": "independent_quality_review",
                "stop_conditions": ["unsupported_transition", "stale_evidence"],
                "return_node_id": node_id,
                "escalation_request_types": ["scope_expansion", "activation_approval"],
            }
        ],
        "evidence": {
            "requirements": [
                {
                    "evidence_id": "result_verified",
                    "claim": "The result satisfies the approved acceptance criteria.",
                    "method": "independent_verification",
                    "producer_independence": "independent_step",
                    "artifact_selectors": ["scope:declared_outputs"],
                    "freshness_seconds": 3600,
                    "required": True,
                }
            ],
            "acceptance_rule": "all_required",
            "stale_evidence_policy": "recapture",
        },
        "correction_loop": {
            "max_attempts": 12,
            "attempt": 0,
            "progress_evidence_required": True,
            "repeated_defect_limit": 3,
            "allowed_directives": ["REVISE", "REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
            "no_progress_directives": ["REPLAN", "REDEFINE", "ESCALATE", "BLOCKED"],
        },
        "continuation": {
            "checkpoint_id": "checkpoint-001",
            "resume_node_id": "approve",
            "required_state_fields": ["current_node_id", "last_sequence", "artifact_ids"],
            "child_return_fields": ["artifact_ids", "evidence_refs", "directive"],
            "parent_run_id": None,
            "child_run_ids": [],
        },
        "recovery": {
            "replay_policy": "receipt_guarded",
            "checkpoint_ref": "checkpoint:checkpoint-001",
            "external_effect_receipts_required": True,
            "revalidation_evidence_ids": ["result_verified"],
            "on_recovery_failure": "BLOCKED",
        },
        "stop_escalation": {
            "stop_conditions": ["accepted", "authority_exhausted", "safe_continuation_unavailable"],
            "blocked_conditions": ["required_input_unavailable", "evidence_cannot_be_produced"],
            "authority_request_types": ["scope_expansion", "activation_approval"],
            "authority_return_target": "principal-001",
        },
    }


def process_run(entrypoint: str = "run") -> dict:
    return {
        "schema_version": pc.CONTRACT_SCHEMA_VERSION,
        "object_family": "process_run",
        "run_id": f"run-{entrypoint}",
        "definition_ref": definition_ref(),
        "state": "ready",
        "entrypoint": entrypoint,
        "current_node_id": "approve",
        "input_bindings": {"repository_ref": "artifact:repo-input"},
        "contracts": contract_set(),
        "relationships": {
            "parent_run_id": None,
            "invoked_by_run_id": None,
            "invoked_definition_refs": [],
            "constructed_definition_refs": [],
            "return_to_run_id": None,
        },
        "artifact_ids": ["repo-input"],
        "last_sequence": 0,
        "created_at": NOW,
        "updated_at": NOW,
        "labels": ["trial"],
    }


def artifact() -> dict:
    return {
        "schema_version": pc.CONTRACT_SCHEMA_VERSION,
        "object_family": "artifact",
        "artifact_id": "change-result",
        "role": "result",
        "status": "verified",
        "media_type": "application/x-git-tree",
        "locator": {"kind": "git_ref", "ref": "refs/heads/trial"},
        "identity": identity(),
        "lineage": {
            "run_id": "run-run",
            "definition_ref": definition_ref(),
            "producing_node_id": "act",
            "source_artifact_ids": ["repo-input"],
            "event_record_id": "event-001",
        },
        "created_at": NOW,
    }


def observation_event() -> dict:
    return {
        "schema_version": pc.CONTRACT_SCHEMA_VERSION,
        "object_family": "event_transition_record",
        "record_id": "event-001",
        "run_id": "run-run",
        "definition_ref": definition_ref(),
        "sequence": 1,
        "recorded_at": NOW,
        "node_id": "verify",
        "record_type": "event",
        "event": {
            "event_type": "verification_completed",
            "details": {"checker": "independent_verification"},
            "observation": {"outcome": "PASS", "summary": "All required checks passed."},
        },
        "evidence_refs": [
            {
                "evidence_id": "result_verified",
                "artifact_id": "change-result",
                "identity_digest": DIGEST,
                "outcome": "PASS",
            }
        ],
        "artifact_ids": ["change-result"],
    }


def transition_record(directive: str = "REDEFINE") -> dict:
    record = {
        "schema_version": pc.CONTRACT_SCHEMA_VERSION,
        "object_family": "event_transition_record",
        "record_id": f"transition-{directive.lower()}",
        "run_id": "run-run",
        "definition_ref": definition_ref(),
        "sequence": 2,
        "recorded_at": LATER,
        "node_id": "verify",
        "record_type": "transition",
        "transition": {
            "directive": directive,
            "from_state": "running",
            "to_state": "redefining" if directive == "REDEFINE" else "waiting_for_authority",
            "reason": "Evidence identifies the responsible correction route.",
            "evaluation_boundary": "process_coherence",
            "target_node_id": "verify",
        },
        "evidence_refs": [],
        "artifact_ids": ["change-result"],
    }
    if directive == "ESCALATE":
        record["transition"]["authority_request"] = {
            "request_id": "authority-001",
            "request_type": "scope_expansion",
            "requested_authority": ["expand_scope"],
            "options": ["approve expansion", "deny and stop"],
            "resume_node_id": "verify",
            "requested_from": "principal-001",
        }
    return record


class TestContractVocabulary(unittest.TestCase):
    def test_exactly_four_persisted_families(self):
        self.assertEqual(
            pc.ROOT_OBJECT_FAMILIES,
            ("process_definition", "process_run", "artifact", "event_transition_record"),
        )
        self.assertEqual(set(pc._ROOT_VALIDATORS), set(pc.ROOT_OBJECT_FAMILIES))

    def test_attached_concepts_are_not_root_families(self):
        self.assertEqual(len(pc.ATTACHED_CONTRACTS), 9)
        self.assertTrue(set(pc.ATTACHED_CONTRACTS).isdisjoint(pc.ROOT_OBJECT_FAMILIES))

    def test_versioned_catalog_is_json_serializable(self):
        catalog = pc.contract_catalog()
        self.assertEqual(catalog["schema_version"], pc.CONTRACT_SCHEMA_VERSION)
        self.assertEqual(catalog["directive_target_states"], pc.DIRECTIVE_TARGET_STATES)
        self.assertEqual(catalog["construction_operation_model"], "relationships_over_one_process_run")
        json.dumps(catalog)

    def test_no_controller_or_agent_object(self):
        classes = {name for name, item in inspect.getmembers(pc, inspect.isclass) if item.__module__ == pc.__name__}
        self.assertEqual(classes, {"ContractValidationError"})
        self.assertNotIn("agent", {family.lower() for family in pc.ROOT_OBJECT_FAMILIES})


class TestGraphAndPackageGrammar(unittest.TestCase):
    def test_every_required_graph_production_validates(self):
        graph = complete_grammar_graph()
        validated = pc.validate_process_graph(graph)
        self.assertEqual({node["kind"] for node in validated["nodes"]}, set(pc.GRAPH_NODE_KINDS))

    def test_unbounded_loop_is_impossible(self):
        graph = complete_grammar_graph()
        loop = next(node for node in graph["nodes"] if node["kind"] == "bounded_loop")
        del loop["max_iterations"]
        with self.assertRaisesRegex(pc.ContractValidationError, "max_iterations"):
            pc.validate_process_graph(graph)

    def test_loop_requires_progress_evidence(self):
        graph = complete_grammar_graph()
        loop = next(node for node in graph["nodes"] if node["kind"] == "bounded_loop")
        loop["progress_evidence_requirement_ids"] = []
        with self.assertRaisesRegex(pc.ContractValidationError, "at least 1"):
            pc.validate_process_graph(graph)

    def test_graph_rejects_dangling_and_unreachable_nodes(self):
        graph = compact_graph()
        next(node for node in graph["nodes"] if node["node_id"] == "act")["next_node_id"] = "missing"
        with self.assertRaisesRegex(pc.ContractValidationError, "unknown node"):
            pc.validate_process_graph(graph)

        graph = compact_graph()
        graph["nodes"].append({
            "node_id": "orphan",
            "kind": "terminal_state",
            "label": "Orphan",
            "outcome": "cancelled",
        })
        with self.assertRaisesRegex(pc.ContractValidationError, "unreachable"):
            pc.validate_process_graph(graph)

    def test_package_roles_not_directories_define_membership(self):
        manifest = package_manifest()
        validated = pc.validate_package_manifest(manifest)
        self.assertEqual(
            [member["role"] for member in validated["members"]],
            ["process_definition", "instruction", "test"],
        )
        self.assertNotEqual(
            Path(validated["members"][1]["locator"]["ref"]).parent,
            Path(validated["members"][2]["locator"]["ref"]).parent,
        )

    def test_package_rejects_duplicate_locator(self):
        manifest = package_manifest()
        manifest["members"][2]["locator"] = copy.deepcopy(manifest["members"][1]["locator"])
        with self.assertRaisesRegex(pc.ContractValidationError, "unique package member"):
            pc.validate_package_manifest(manifest)

    def test_definition_rejects_manifest_for_another_identity(self):
        definition = process_definition()
        definition["package_manifest"]["definition_ref"] = definition_ref("unrelated/process")
        with self.assertRaisesRegex(pc.ContractValidationError, "exact Process Definition identity"):
            pc.validate_process_definition(definition)

    def test_package_entry_member_must_match_definition_digest(self):
        manifest = package_manifest()
        manifest["members"][0]["identity"]["digest"] = DIGEST_B
        with self.assertRaisesRegex(pc.ContractValidationError, "must match"):
            pc.validate_package_manifest(manifest)


class TestFourPersistedFamilies(unittest.TestCase):
    def test_each_family_validates_and_dispatches(self):
        objects = [process_definition(), process_run(), artifact(), observation_event()]
        for payload in objects:
            with self.subTest(family=payload["object_family"]):
                self.assertEqual(pc.validate_persisted_object(payload), payload)

    def test_validation_returns_detached_copy(self):
        original = artifact()
        validated = pc.validate_artifact(original)
        validated["lineage"]["source_artifact_ids"].append("new-source")
        self.assertEqual(original["lineage"]["source_artifact_ids"], ["repo-input"])

    def test_unknown_root_field_is_rejected(self):
        run = process_run()
        run["programming_controller"] = "private path"
        with self.assertRaisesRegex(pc.ContractValidationError, "unknown field"):
            pc.validate_process_run(run)

    def test_unknown_family_is_rejected(self):
        payload = process_run()
        payload["object_family"] = "agent"
        with self.assertRaisesRegex(pc.ContractValidationError, "object_family"):
            pc.validate_persisted_object(payload)

    def test_run_rejects_unknown_nested_authority_or_evidence_references(self):
        run = process_run()
        run["contracts"]["bounded_judgment"][0]["authority_grant_ids"] = ["missing-grant"]
        with self.assertRaisesRegex(pc.ContractValidationError, "unknown authority grant"):
            pc.validate_process_run(run)

        run = process_run()
        run["contracts"]["recovery"]["revalidation_evidence_ids"] = ["missing-evidence"]
        with self.assertRaisesRegex(pc.ContractValidationError, "unknown evidence requirement"):
            pc.validate_process_run(run)

    def test_stale_or_incomplete_artifact_identity_is_rejected(self):
        payload = artifact()
        payload["identity"]["fresh_until"] = "2026-07-16T17:00:00-07:00"
        with self.assertRaisesRegex(pc.ContractValidationError, "must not precede"):
            pc.validate_artifact(payload)


class TestBoundedAuthoritySemantics(unittest.TestCase):
    def test_judgment_rejects_action_absent_from_referenced_grants(self):
        run = process_run()
        run["contracts"]["bounded_judgment"][0]["permitted_actions"] = [
            "delete_everything"
        ]
        with self.assertRaisesRegex(pc.ContractValidationError, "not authorized"):
            pc.validate_process_run(run)

    def test_judgment_rejects_selector_outside_grant_and_artifact_scope(self):
        run = process_run()
        run["contracts"]["bounded_judgment"][0]["artifact_selectors"] = [
            "scope:undeclared"
        ]
        with self.assertRaisesRegex(pc.ContractValidationError, "outside the referenced"):
            pc.validate_process_run(run)

    def test_judgment_rejects_granted_selector_outside_artifact_scope(self):
        run = process_run()
        run["contracts"]["authority"]["grants"][0]["resource_selectors"].append(
            "scope:grant_only"
        )
        run["contracts"]["bounded_judgment"][0]["artifact_selectors"] = [
            "scope:grant_only"
        ]
        with self.assertRaisesRegex(pc.ContractValidationError, "outside artifact scope"):
            pc.validate_process_run(run)

    def test_authority_rejects_action_that_is_granted_permitted_and_reserved(self):
        run = process_run()
        run["contracts"]["authority"]["reserved_actions"].append("mutate")
        run["contracts"]["bounded_judgment"][0]["permitted_actions"].append("mutate")
        with self.assertRaisesRegex(pc.ContractValidationError, "must not also be granted"):
            pc.validate_process_run(run)

    def test_judgment_rejects_reserved_action_even_when_not_granted(self):
        run = process_run()
        run["contracts"]["bounded_judgment"][0]["permitted_actions"] = ["activate"]
        with self.assertRaisesRegex(pc.ContractValidationError, "must not be permitted"):
            pc.validate_process_run(run)

    def test_judgment_rejects_undeclared_escalation_request_type(self):
        run = process_run()
        run["contracts"]["bounded_judgment"][0]["escalation_request_types"].append(
            "undeclared_authority"
        )
        with self.assertRaisesRegex(pc.ContractValidationError, "not declared"):
            pc.validate_process_run(run)


class TestTransitionSemantics(unittest.TestCase):
    def test_all_seven_directives_are_machine_valid(self):
        for directive in pc.TRANSITION_DIRECTIVES:
            payload = transition_record("ESCALATE" if directive == "ESCALATE" else "REDEFINE")
            payload["transition"]["directive"] = directive
            payload["transition"]["to_state"] = {
                "PROCEED": "running",
                "ACCEPT": "completed",
                "REVISE": "running",
                "REPLAN": "pending",
                "REDEFINE": "redefining",
                "ESCALATE": "waiting_for_authority",
                "BLOCKED": "blocked",
            }[directive]
            if directive != "ESCALATE":
                payload["transition"].pop("authority_request", None)
            with self.subTest(directive=directive):
                pc.validate_event_transition_record(payload)

    def test_every_directive_rejects_a_contradictory_target_state(self):
        contradictory_states = {
            "PROCEED": "completed",
            "ACCEPT": "running",
            "REVISE": "completed",
            "REPLAN": "running",
            "REDEFINE": "completed",
            "ESCALATE": "completed",
            "BLOCKED": "running",
        }
        for directive, contradictory_state in contradictory_states.items():
            payload = transition_record("ESCALATE" if directive == "ESCALATE" else "REDEFINE")
            payload["transition"]["directive"] = directive
            payload["transition"]["to_state"] = contradictory_state
            if directive != "ESCALATE":
                payload["transition"].pop("authority_request", None)
            with self.subTest(directive=directive):
                with self.assertRaisesRegex(pc.ContractValidationError, "requires to_state"):
                    pc.validate_event_transition_record(payload)

    def test_observation_words_are_not_directives(self):
        payload = transition_record()
        payload["transition"]["directive"] = "PASS"
        with self.assertRaisesRegex(pc.ContractValidationError, "must be one of"):
            pc.validate_event_transition_record(payload)

    def test_redefine_is_nonqueued_and_escalate_requires_typed_authority(self):
        redefine = transition_record("REDEFINE")
        pc.validate_event_transition_record(redefine)
        self.assertNotIn("authority_request", redefine["transition"])

        escalate = transition_record("ESCALATE")
        pc.validate_event_transition_record(escalate)
        self.assertEqual(escalate["transition"]["authority_request"]["request_type"], "scope_expansion")

        del escalate["transition"]["authority_request"]
        with self.assertRaisesRegex(pc.ContractValidationError, "required for ESCALATE"):
            pc.validate_event_transition_record(escalate)

    def test_authority_request_is_forbidden_on_redefine(self):
        payload = transition_record("REDEFINE")
        payload["transition"]["authority_request"] = transition_record("ESCALATE")["transition"]["authority_request"]
        with self.assertRaisesRegex(pc.ContractValidationError, "only for ESCALATE"):
            pc.validate_event_transition_record(payload)

    def test_event_and_transition_payloads_are_mutually_exclusive(self):
        payload = observation_event()
        payload["transition"] = transition_record()["transition"]
        with self.assertRaisesRegex(pc.ContractValidationError, "forbid transition"):
            pc.validate_event_transition_record(payload)


class TestProgrammingAndCrossDomainExpression(unittest.TestCase):
    def test_four_programming_entry_paths_share_one_definition_and_run_shape(self):
        definition = process_definition()
        pc.validate_process_definition(definition)
        key_sets = []
        definition_refs = []
        for entrypoint in ("prg_run", "prg_plan", "prg_execute", "prg_verify"):
            run = process_run(entrypoint)
            run["input_bindings"]["selected_entrypoint"] = entrypoint
            pc.validate_process_run(run)
            key_sets.append(set(run))
            definition_refs.append(run["definition_ref"])
            self.assertNotIn("run_kind", run)
        self.assertTrue(all(keys == key_sets[0] for keys in key_sets))
        self.assertTrue(all(ref == definition_refs[0] for ref in definition_refs))

    def test_cross_domain_spreadsheet_uses_identical_contract_surface(self):
        programming = process_definition()
        spreadsheet = process_definition(
            definition_id="finance/monthly-workbook",
            title="Produce and verify a monthly workbook",
            input_properties={
                "workbook_ref": {"type": "string"},
                "source_dataset_ref": {"type": "string"},
                "expected_validation_rule": {"type": "string"},
            },
            output_properties={
                "verified_workbook_artifact_id": {"type": "string"},
                "evidence_artifact_id": {"type": "string"},
            },
        )
        spreadsheet["package_manifest"] = package_manifest("finance/monthly-workbook")
        pc.validate_process_definition(spreadsheet)
        self.assertEqual(set(programming), set(spreadsheet))
        root_keys = {key.lower() for key in spreadsheet}
        self.assertFalse(any("spreadsheet" in key or "programming" in key or "controller" in key for key in root_keys))

    def test_cross_domain_exception_returns_typed_authority_without_private_schema(self):
        run = process_run("invoke")
        run["run_id"] = "run-monthly-workbook"
        run["definition_ref"] = definition_ref("finance/monthly-workbook")
        run["input_bindings"] = {
            "workbook_ref": "artifact:workbook-template",
            "source_dataset_ref": "artifact:monthly-source",
        }
        pc.validate_process_run(run)

        result = artifact()
        result["artifact_id"] = "monthly-workbook-result"
        result["media_type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        result["locator"] = {"kind": "file", "ref": "outputs/monthly-result.xlsx"}
        result["lineage"]["run_id"] = run["run_id"]
        result["lineage"]["definition_ref"] = run["definition_ref"]
        result["lineage"]["source_artifact_ids"] = ["workbook-template", "monthly-source"]
        pc.validate_artifact(result)

        exception = transition_record("ESCALATE")
        exception["run_id"] = run["run_id"]
        exception["definition_ref"] = run["definition_ref"]
        request = exception["transition"]["authority_request"]
        request["request_type"] = "source_input_exception"
        request["requested_authority"] = ["correct_source_input", "accept_documented_exception"]
        request["options"] = ["supply corrected input", "accept the documented exception", "stop"]
        pc.validate_event_transition_record(exception)

        self.assertNotIn("spreadsheet_controller", run)
        self.assertNotIn("spreadsheet_exception", exception)
        self.assertEqual(exception["transition"]["directive"], "ESCALATE")

    def test_pif_direct_operation_remains_one_governed_run(self):
        run = process_run("infer_and_operate")
        pif_ref = definition_ref("process-inference/direct-operation")
        run["definition_ref"] = pif_ref
        run["input_bindings"] = {
            "requested_outcome": "Transform the supplied data into the verified result",
            "procedure_inferable_now": True,
        }
        run["contracts"]["approved_plan"]["objective"] = "Infer and execute the complete procedure inside this Run."
        run["contracts"]["authority"]["reserved_actions"].extend([
            "register", "invoke_from_another_run", "replace_definition",
        ])
        pc.validate_process_run(run)
        self.assertEqual(run["run_id"], "run-infer_and_operate")
        self.assertEqual(run["definition_ref"], pif_ref)
        self.assertNotIn("run_kind", run)
        self.assertEqual(run["relationships"]["invoked_definition_refs"], [])
        self.assertIn("register", run["contracts"]["authority"]["reserved_actions"])

    def test_construction_and_invocation_are_relationships_not_engines(self):
        run = process_run("construct_and_invoke")
        child = definition_ref("finance/monthly-workbook")
        run["relationships"]["constructed_definition_refs"] = [child]
        run["relationships"]["invoked_definition_refs"] = [child]
        pc.validate_process_run(run)
        self.assertEqual(
            run["relationships"]["constructed_definition_refs"],
            run["relationships"]["invoked_definition_refs"],
        )
        self.assertNotIn("construction_engine", run)
        self.assertNotIn("operation_engine", run)


if __name__ == "__main__":
    unittest.main()
