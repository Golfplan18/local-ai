"""Phase 1.7 proof: generic kernel trials across programming and business work."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import governed_process_runtime as gpr  # noqa: E402
import process_contracts as pc  # noqa: E402
import process_definition_registry as registry_module  # noqa: E402
from tests import test_governed_process_runtime as runtime_fixtures  # noqa: E402
from tests import test_process_contracts as fixtures  # noqa: E402


NOW = fixtures.NOW
CONDITIONS = ["approved_plan_digest_matches"]
OUTPUT = "scope:declared_outputs"
INPUT = "scope:declared_inputs"
EXTERNAL = "scope:declared_external_effects"
DEFINITION_SCOPE = "scope:process_definition"
WORKBOOK = ROOT / "outputs" / "g1-1-phase-1-7" / "cash-flow-exception-trial.xlsx"


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_json(value: object) -> str:
    return _digest_text(_canonical_json(value))


def _repository_composite(repository: Path) -> tuple[dict, str]:
    """Capture exact Git HEAD plus every non-ignored worktree file identity."""

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repository, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    entries = []
    for raw_name in sorted(item for item in listed.split(b"\0") if item):
        relative = os.fsdecode(raw_name)
        path = repository / relative
        if path.is_symlink():
            kind = "symlink"
            digest = _digest_text(os.readlink(path))
            mode = None
        else:
            kind = "file"
            digest = _digest_bytes(path.read_bytes())
            mode = oct(path.stat().st_mode & 0o777)
        entries.append(
            {"path": relative, "kind": kind, "mode": mode, "digest": digest}
        )
    payload = {
        "schema_version": "ora.repository-composite/1.0",
        "repository": str(repository.resolve()),
        "git_head": head,
        "git_status_digest": _digest_bytes(status),
        "worktree_entries": entries,
    }
    return payload, _digest_json(payload)


def _definition_ref(definition: dict) -> dict:
    return {
        "definition_id": definition["definition_id"],
        "version": definition["version"],
        "digest": definition["digest"],
    }


def _seal_definition(definition: dict) -> dict:
    """Bind every self-reference to the definition's normalized content."""

    placeholder = "sha256:" + ("0" * 64)
    manifest = definition["package_manifest"]
    manifest["definition_ref"] = {
        "definition_id": definition["definition_id"],
        "version": definition["version"],
        "digest": placeholder,
    }
    entry_member = next(
        member
        for member in manifest["members"]
        if member["member_id"] == manifest["entry_member_id"]
    )
    definition["digest"] = placeholder
    entry_member["identity"]["digest"] = placeholder
    digest = registry_module.process_definition_content_digest(definition)
    definition["digest"] = digest
    manifest["definition_ref"]["digest"] = digest
    entry_member["identity"]["digest"] = digest
    return definition


def _programming_definition() -> dict:
    text = (ROOT / "frameworks" / "book" / "programming.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"<!-- PROGRAMMING_PROCESS_DEFINITION_BEGIN -->\n"
        r"```json\n(.*?)\n```\n"
        r"<!-- PROGRAMMING_PROCESS_DEFINITION_END -->",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("Programming definition projection is missing")
    return json.loads(match.group(1))


def _definition(
    definition_id: str,
    *,
    version: str = "1.0.0",
    graph: dict | None = None,
) -> dict:
    definition = fixtures.process_definition(definition_id, definition_id)
    definition["version"] = version
    definition["graph"] = graph or copy.deepcopy(definition["graph"])
    manifest = definition["package_manifest"]
    manifest["package_id"] = definition_id
    manifest["package_version"] = version
    manifest["members"][0]["locator"]["ref"] = (
        f"processes/{definition_id}@{version}"
    )
    return _seal_definition(definition)


def _cash_review_definition() -> dict:
    graph = {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": "business/cash-flow-review/1.0.0",
        "entry_node_id": "calculate",
        "nodes": [
            {
                "node_id": "calculate", "kind": "action",
                "label": "Calculate only authority-permitted cash flows",
                "operation": "calculate_permitted_cash_flow", "next_node_id": "review",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [INPUT, OUTPUT],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "review", "kind": "verification_boundary",
                "label": "Independently verify the exact workbook result",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {"ACCEPT": "accepted", "ESCALATE": "authority", "BLOCKED": "blocked"},
            },
            {
                "node_id": "authority", "kind": "human_checkpoint",
                "label": "Return a reserved calculation exception to the Principal",
                "authority_request_type": "calculation_exception",
                "on_approved_node_id": "calculate", "on_denied_node_id": "blocked",
                "on_unavailable_node_id": "blocked",
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }
    return _definition("business/cash-flow-review", graph=graph)


def _construction_definition(target: dict) -> dict:
    graph = {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": "ora/reusable-definition-construction/1.0.0",
        "entry_node_id": "construct-definition",
        "nodes": [
            {
                "node_id": "construct-definition", "kind": "action",
                "label": "Construct and verify an exact reusable Process Definition",
                "operation": "construct_reusable_process_definition",
                "next_node_id": "register-definition",
                "authority_grant_ids": ["trial-grant"],
                "artifact_access": [DEFINITION_SCOPE],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "register-definition", "kind": "action",
                "label": "Register the approved exact version without activation",
                "operation": "register_reusable_process_definition",
                "next_node_id": "review",
                "authority_grant_ids": ["trial-grant"],
                "artifact_access": [DEFINITION_SCOPE, OUTPUT],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "review", "kind": "verification_boundary",
                "label": "Independently verify construction and registration",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"},
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }
    definition = _definition("ora/reusable-definition-construction", graph=graph)
    definition["input_schema"]["properties"]["target_definition_ref"] = {
        "const": _definition_ref(target)
    }
    return _seal_definition(definition)


def _calling_definition(
    definition_id: str,
    child: dict,
    *,
    return_operation: str = "summarize_child_result",
) -> dict:
    graph = {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": f"{definition_id}/1.0.0",
        "entry_node_id": "call-child",
        "nodes": [
            {
                "node_id": "call-child", "kind": "process_call", "label": "Invoke exact child",
                "definition_ref": _definition_ref(child), "input_bindings": {},
                "return_node_id": "receive-child", "on_error_node_id": "blocked",
            },
            {
                "node_id": "receive-child", "kind": "process_return", "label": "Receive exact child result",
                "output_bindings": {"result": "child.result"}, "next_node_id": "summarize",
            },
            {
                "node_id": "summarize", "kind": "action", "label": "Bind returned result",
                "operation": return_operation, "next_node_id": "final-review",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "final-review", "kind": "verification_boundary", "label": "Review parent result",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"},
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }
    return _definition(definition_id, graph=graph)


def _leaf_definition(definition_id: str, operation: str) -> dict:
    graph = {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": f"{definition_id}/1.0.0",
        "entry_node_id": "work",
        "nodes": [
            {
                "node_id": "work", "kind": "action", "label": "Produce bounded result",
                "operation": operation, "next_node_id": "review",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [INPUT, OUTPUT],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "review", "kind": "verification_boundary", "label": "Review bounded result",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"},
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }
    return _definition(definition_id, graph=graph)


def _pef_parent_definition(pif: dict, pff: dict, execution: dict) -> dict:
    graph = {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": "ora/problem-evolution-trial/1.0.0",
        "entry_node_id": "establish-interim-contract",
        "nodes": [
            {
                "node_id": "establish-interim-contract", "kind": "action",
                "label": "Persist one bounded interim-goal contract",
                "operation": "establish_interim_goal_contract", "next_node_id": "call-pif",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT],
                "evidence_requirement_ids": [], "external_effect": False,
            },
            {
                "node_id": "call-pif", "kind": "process_call", "label": "Invoke PIF",
                "definition_ref": _definition_ref(pif), "input_bindings": {},
                "return_node_id": "receive-pif", "on_error_node_id": "blocked",
            },
            {
                "node_id": "receive-pif", "kind": "process_return", "label": "Receive PIF evidence",
                "output_bindings": {"evidence": "child.result"}, "next_node_id": "derive-dependent-goal",
            },
            {
                "node_id": "derive-dependent-goal", "kind": "action",
                "label": "Select the next goal only from returned evidence",
                "operation": "derive_evidence_dependent_goal", "next_node_id": "call-pff",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "call-pff", "kind": "process_call", "label": "Invoke PFF",
                "definition_ref": _definition_ref(pff), "input_bindings": {},
                "return_node_id": "receive-pff", "on_error_node_id": "blocked",
            },
            {
                "node_id": "receive-pff", "kind": "process_return", "label": "Receive formalized definition",
                "output_bindings": {"definition": "child.result"}, "next_node_id": "register-definition",
            },
            {
                "node_id": "register-definition", "kind": "action",
                "label": "Register and bind the exact approved definition",
                "operation": "register_exact_process_definition", "next_node_id": "call-execution",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT, DEFINITION_SCOPE],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "call-execution", "kind": "process_call", "label": "Invoke exact execution",
                "definition_ref": _definition_ref(execution), "input_bindings": {},
                "return_node_id": "receive-execution", "on_error_node_id": "blocked",
            },
            {
                "node_id": "receive-execution", "kind": "process_return", "label": "Receive execution evidence",
                "output_bindings": {"result": "child.result"}, "next_node_id": "update-problem-state",
            },
            {
                "node_id": "update-problem-state", "kind": "action",
                "label": "Update persisted problem state and next goal",
                "operation": "update_problem_state_from_evidence", "next_node_id": "final-review",
                "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT],
                "evidence_requirement_ids": ["result_verified"], "external_effect": False,
            },
            {
                "node_id": "final-review", "kind": "verification_boundary", "label": "Review evolved state",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"},
            },
            {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted", "outcome": "accepted"},
            {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked", "outcome": "blocked"},
        ],
    }
    return _definition("ora/problem-evolution-trial", graph=graph)


def _trial_run(
    run_id: str,
    definition: dict,
    *,
    entrypoint: str = "run",
    child_definitions: tuple[dict, ...] = (),
) -> dict:
    run = fixtures.process_run(entrypoint)
    run["run_id"] = run_id
    run["definition_ref"] = _definition_ref(definition)
    run["state"] = "ready"
    run["entrypoint"] = entrypoint
    run["current_node_id"] = definition["graph"]["entry_node_id"]
    run["input_bindings"] = {
        "entrypoint": entrypoint,
        "objective": "Produce the exact governed trial result.",
        "project_ref": "project:ora-g1.1",
        "target_artifact_selectors": [OUTPUT],
    }
    run["artifact_ids"] = []
    run["last_sequence"] = 0
    run["contracts"]["approved_plan"]["approved_node_ids"] = [
        node["node_id"] for node in definition["graph"]["nodes"]
    ]
    run["contracts"]["correction_loop"].update(
        {"max_attempts": 12, "attempt": 0, "repeated_defect_limit": 3}
    )
    run["contracts"]["continuation"].update(
        {"checkpoint_id": "initial", "resume_node_id": run["current_node_id"]}
    )

    selectors = {INPUT, OUTPUT, EXTERNAL, DEFINITION_SCOPE, "scope:dialogue", "scope:plan_outputs"}
    selectors.update(
        f"definition:{item['definition_id']}@{item['version']}"
        for item in child_definitions
    )
    actions = {
        "construct_definition",
        "evaluate_evidence",
        "inspect",
        "invoke_process",
        "mutate",
        "mutate_repository",
        "produce_artifact",
        "record_evidence",
        "register_definition",
        "test",
    }
    run["contracts"]["authority"] = {
        "principal_id": "principal-001",
        "grants": [{
            "grant_id": "trial-grant",
            "actions": sorted(actions),
            "resource_selectors": sorted(selectors),
            "effect_types": ["external_irreversible", "local_reversible"],
            "conditions": CONDITIONS,
        }],
        "reserved_actions": ["activate", "expand_scope", "publish"],
    }
    run["contracts"]["artifact_scope"] = {
        "read_selectors": sorted(selectors),
        "write_selectors": sorted(selectors),
        "external_effect_selectors": sorted(selectors),
    }
    verification_nodes = [
        node for node in definition["graph"]["nodes"]
        if node["kind"] == "verification_boundary"
    ]
    run["contracts"]["bounded_judgment"] = [
        {
            "judgment_id": f"judgment-{node['node_id']}",
            "node_id": node["node_id"],
            "verified_circumstances": ["Exact Run and artifact identities are bound."],
            "question": "Which declared route does the supplied evidence support?",
            "permitted_conclusions": [
                "criteria_met", "execution_defect", "plan_defect",
                "definition_defect", "authority_exception",
            ],
            "permitted_directives": sorted(node["routes"]),
            "permitted_actions": ["evaluate_evidence"],
            "authority_grant_ids": ["trial-grant"],
            "artifact_selectors": [OUTPUT],
            "required_evidence_ids": ["result_verified"],
            "evaluator_boundary": f"review-{node['node_id']}",
            "stop_conditions": ["unsupported_transition", "stale_evidence"],
            "return_node_id": node["node_id"],
            "escalation_request_types": [
                "calculation_exception", "definition_replacement", "scope_expansion"
            ],
        }
        for node in verification_nodes
    ] or [{
        **copy.deepcopy(fixtures.contract_set()["bounded_judgment"][0]),
        "node_id": definition["graph"]["entry_node_id"],
        "return_node_id": definition["graph"]["entry_node_id"],
        "authority_grant_ids": ["trial-grant"],
        "escalation_request_types": ["scope_expansion"],
    }]
    run["contracts"]["evidence"] = {
        "requirements": [{
            "evidence_id": "result_verified",
            "claim": "The exact result satisfies its approved acceptance criteria.",
            "method": "independent_verification",
            "producer_independence": "independent_step",
            "artifact_selectors": [OUTPUT],
            "freshness_seconds": 3600,
            "required": True,
        }],
        "acceptance_rule": "all_required",
        "stale_evidence_policy": "recapture",
    }
    run["contracts"]["recovery"]["revalidation_evidence_ids"] = [
        "result_verified"
    ]
    run["contracts"]["stop_escalation"]["authority_request_types"] = [
        "calculation_exception", "definition_replacement", "scope_expansion"
    ]
    run["contracts"]["stop_escalation"]["authority_return_target"] = "principal-001"
    return run


class TrialCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = gpr.GovernedProcessRuntime(
            Path(self.temp.name) / "runs", now=lambda: NOW
        )

    def create(self, run_id: str, definition: dict, **kwargs) -> dict:
        run = _trial_run(run_id, definition, **kwargs)
        self.runtime.create_run(definition, run)
        self.runtime.start_run(run_id, reason="Approved Phase 1.7 trial")
        return run

    def evidence_ref(self, run_id: str, label: str) -> dict:
        safe_label = re.sub(r"[^A-Za-z0-9._:/-]", "-", label)
        artifact_id = f"evidence-{safe_label}"
        recorded = self.runtime.record_inline_artifact(
            run_id,
            artifact_id,
            f"Independent trial observation: {label}",
            role="evidence",
            node_id=self.runtime.load_run(run_id)["current_node_id"],
            action="record_evidence",
            selector=OUTPUT,
            satisfied_conditions=CONDITIONS,
        )
        artifact = recorded["artifact"]
        return {
            "evidence_id": "result_verified",
            "artifact_id": artifact_id,
            "identity_digest": artifact["identity"]["digest"],
            "outcome": "PASS",
        }

    def transition(self, run_id: str, directive: str, target: str, label: str) -> dict:
        return self.runtime.apply_transition(
            run_id,
            directive,
            target_node_id=target,
            reason=label,
            evaluation_boundary=(
                f"review-{self.runtime.load_run(run_id)['current_node_id']}"
            ),
            evidence_refs=[self.evidence_ref(run_id, label)],
        )

    def repository_artifact(
        self,
        run_id: str,
        repository: Path,
        artifact_id: str,
        *,
        role: str,
        node_id: str | None = None,
        source_artifact_ids: tuple[str, ...] = (),
    ) -> dict:
        payload, digest = _repository_composite(repository)
        run = self.runtime.load_run(run_id)
        artifact = {
            "schema_version": pc.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": artifact_id,
            "role": role,
            "status": "candidate",
            "media_type": "application/vnd.ora.repository-state+json",
            "locator": {"kind": "git_ref", "ref": str(repository.resolve())},
            "identity": {
                "kind": "composite",
                "digest": digest,
                "coverage": ["git_head", "git_status", "nonignored_worktree_files"],
                "captured_at": NOW,
                "fresh_until": fixtures.LATER,
                "external_version": payload["git_head"],
            },
            "lineage": {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "producing_node_id": node_id or run["current_node_id"],
                "source_artifact_ids": list(source_artifact_ids),
                "event_record_id": f"event-{run_id}-{artifact_id}-{digest[7:19]}",
            },
            "created_at": NOW,
        }
        recorded = self.runtime.record_artifact(
            artifact,
            action="produce_artifact",
            selectors=[OUTPUT],
            satisfied_conditions=CONDITIONS,
        )
        return {**recorded, "composite": payload}

    def repository_mutation(
        self,
        run_id: str,
        repository: Path,
        operation: str,
        label: str,
        pre_state: dict,
        post_state: dict,
    ) -> dict:
        node_id = self.runtime.load_run(run_id)["current_node_id"]
        receipt_id = f"receipt-{label}"
        receipt_payload = {
            "schema_version": "ora.repository-mutation-receipt/1.0",
            "operation": operation,
            "repository": str(repository.resolve()),
            "pre_state": {
                "artifact_id": pre_state["artifact"]["artifact_id"],
                "identity_digest": pre_state["artifact"]["identity"]["digest"],
            },
            "post_state": {
                "artifact_id": post_state["artifact"]["artifact_id"],
                "identity_digest": post_state["artifact"]["identity"]["digest"],
            },
        }
        receipt = self.runtime.record_inline_artifact(
            run_id, receipt_id, _canonical_json(receipt_payload),
            role="external_effect_receipt", node_id=node_id,
            action="produce_artifact", selector=OUTPUT,
            source_artifact_ids=[
                pre_state["artifact"]["artifact_id"],
                post_state["artifact"]["artifact_id"],
            ],
            satisfied_conditions=CONDITIONS,
            media_type="application/json",
        )
        self.runtime.record_action(
            run_id,
            action="mutate_repository",
            selectors=[OUTPUT],
            satisfied_conditions=CONDITIONS,
            effect_type="external_irreversible",
            external_effect=True,
            receipt_artifact_id=receipt["artifact"]["artifact_id"],
            details={
                "operation": operation,
                "repository": str(repository.resolve()),
                "pre_state_identity": receipt_payload["pre_state"],
                "post_state_identity": receipt_payload["post_state"],
            },
        )
        self.runtime.complete_action_node(
            run_id, operation, reason=label, artifact_ids=[receipt_id]
        )
        return {"receipt": receipt, "payload": receipt_payload}

    def repository_test_evidence(
        self,
        run_id: str,
        repository: Path,
        subject_artifact_id: str,
        evidence_artifact_id: str,
    ) -> tuple[dict, dict, dict]:
        subject = self.runtime.load_artifact(run_id, subject_artifact_id)
        current_composite, current_digest = _repository_composite(repository)
        self.assertEqual(current_digest, subject["identity"]["digest"])
        command = [
            sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"
        ]
        completed = subprocess.run(
            command, cwd=repository, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, check=False,
        )
        after_composite, after_digest = _repository_composite(repository)
        self.assertEqual(after_digest, current_digest)
        payload = {
            "schema_version": "ora.repository-test-evidence/1.0",
            "command": command,
            "cwd": str(repository.resolve()),
            "repository_identity_digest": current_digest,
            "repository_composite": current_composite,
            "post_test_repository_composite": after_composite,
            "returncode": completed.returncode,
            "output": completed.stdout,
        }
        evidence_dir = Path(self.temp.name) / "programming-evidence"
        evidence_dir.mkdir(exist_ok=True)
        evidence_path = evidence_dir / f"{evidence_artifact_id}.json"
        evidence_path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        run = self.runtime.load_run(run_id)
        artifact = {
            "schema_version": pc.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": evidence_artifact_id,
            "role": "evidence",
            "status": "verified",
            "media_type": "application/json",
            "locator": {"kind": "file", "ref": str(evidence_path.resolve())},
            "identity": {
                "kind": "content_digest",
                "digest": _digest_bytes(evidence_path.read_bytes()),
                "coverage": ["command", "repository_composite", "exit_status", "output"],
                "captured_at": NOW,
                "fresh_until": fixtures.LATER,
            },
            "lineage": {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "producing_node_id": run["current_node_id"],
                "source_artifact_ids": [subject_artifact_id],
                "event_record_id": f"event-{run_id}-{evidence_artifact_id}",
            },
            "created_at": NOW,
        }
        recorded = self.runtime.record_artifact(
            artifact, action="record_evidence", selectors=[OUTPUT],
            satisfied_conditions=CONDITIONS,
        )
        evidence_ref = {
            "evidence_id": "result_verified",
            "artifact_id": evidence_artifact_id,
            "identity_digest": artifact["identity"]["digest"],
            "outcome": "PASS" if completed.returncode == 0 else "FAIL",
        }
        return recorded, evidence_ref, payload

    def observed_action(
        self,
        run_id: str,
        operation: str,
        label: str,
        details: dict,
    ) -> None:
        node_id = self.runtime.load_run(run_id)["current_node_id"]
        node = next(
            item for item in self.runtime.load_definition(run_id)["graph"]["nodes"]
            if item["node_id"] == node_id
        )
        selector = node["artifact_access"][0]
        self.runtime.record_action(
            run_id,
            action="inspect",
            selectors=[selector],
            satisfied_conditions=CONDITIONS,
            effect_type="local_reversible",
            external_effect=False,
            details={"operation": operation, **details},
        )
        self.runtime.complete_action_node(
            run_id, operation, reason=label, completion_details=details
        )

    def final_result(
        self, run_id: str, text: str, *, result_id: str = "trial-result"
    ) -> tuple[dict, dict, dict]:
        definition = self.runtime.load_definition(run_id)
        current_node_id = self.runtime.load_run(run_id)["current_node_id"]
        producing_node_id = next(
            node["node_id"]
            for node in definition["graph"]["nodes"]
            if node["kind"] == "action" and node["node_id"] != current_node_id
        )
        result = self.runtime.record_inline_artifact(
            run_id,
            result_id,
            text,
            role="result",
            node_id=producing_node_id,
            action="produce_artifact",
            selector=OUTPUT,
            satisfied_conditions=CONDITIONS,
        )
        evidence = self.runtime.record_inline_artifact(
            run_id,
            f"{result_id}-proof",
            f"Independent verification of {text}",
            role="evidence",
            node_id=current_node_id,
            action="record_evidence",
            selector=OUTPUT,
            source_artifact_ids=[result_id],
            satisfied_conditions=CONDITIONS,
        )
        review = self.runtime.record_final_review(
            run_id,
            artifact_id=result_id,
            evidence_id="result_verified",
            evidence_artifact_id=evidence["artifact"]["artifact_id"],
            outcome="PASS",
            reviewer_id="independent-reviewer",
            independent=True,
            satisfied_conditions=CONDITIONS,
        )
        return result, evidence, review["evidence_refs"][0]

    def file_result(
        self,
        run_id: str,
        artifact_id: str,
        path: Path,
        *,
        node_id: str,
        source_artifact_ids: tuple[str, ...] = (),
    ) -> dict:
        run = self.runtime.load_run(run_id)
        artifact = {
            "schema_version": pc.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": artifact_id,
            "role": "result",
            "status": "candidate",
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "locator": {"kind": "file", "ref": str(path.resolve())},
            "identity": {
                "kind": "content_digest",
                "digest": _digest_bytes(path.read_bytes()),
                "coverage": ["complete_content"],
                "captured_at": NOW,
                "fresh_until": fixtures.LATER,
            },
            "lineage": {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "producing_node_id": node_id,
                "source_artifact_ids": list(source_artifact_ids),
                "event_record_id": f"event-{run_id}-{artifact_id}",
            },
            "created_at": NOW,
        }
        return self.runtime.record_artifact(
            artifact,
            action="produce_artifact",
            selectors=[OUTPUT],
            satisfied_conditions=CONDITIONS,
        )

    def accept_existing_result(
        self, run_id: str, artifact_id: str, *, accepted_node: str = "accepted"
    ) -> dict:
        current = self.runtime.load_run(run_id)["current_node_id"]
        evidence = self.runtime.record_inline_artifact(
            run_id,
            f"{artifact_id}-proof",
            f"Independent proof for {artifact_id}",
            role="evidence",
            node_id=current,
            action="record_evidence",
            selector=OUTPUT,
            source_artifact_ids=[artifact_id],
            satisfied_conditions=CONDITIONS,
        )
        review = self.runtime.record_final_review(
            run_id,
            artifact_id=artifact_id,
            evidence_id="result_verified",
            evidence_artifact_id=evidence["artifact"]["artifact_id"],
            outcome="PASS",
            reviewer_id="independent-reviewer",
            independent=True,
            satisfied_conditions=CONDITIONS,
        )
        return self.runtime.apply_transition(
            run_id,
            "ACCEPT",
            target_node_id=accepted_node,
            reason="Exact result independently verified",
            evaluation_boundary=f"review-{current}",
            evidence_refs=review["evidence_refs"],
        )


class TestMechanicalTraversalAndRegistry(TrialCase):
    def test_reserved_graph_events_and_cross_path_routes_are_rejected(self):
        definition = _programming_definition()
        self.create("run-guard", definition, entrypoint="prg_run")
        before = self.runtime.load_run("run-guard")
        with self.assertRaises(gpr.AuthorityDeniedError):
            self.runtime.record_event(
                "run-guard", "node_advanced", {"to_node_id": "execute-step"}
            )
        with self.assertRaises(gpr.AuthorityDeniedError):
            self.runtime.advance_decision(
                "run-guard", "prg_verify", reason="cross-path attempt"
            )
        self.assertEqual(self.runtime.load_run("run-guard"), before)

    def test_action_checkpoint_and_return_boundaries_fail_closed(self):
        definition = _programming_definition()
        self.create("run-guard", definition, entrypoint="prg_run")
        self.runtime.advance_decision("run-guard", "prg_run", reason="enter path")
        self.observed_action(
            "run-guard", "elicit_programming_intent", "intent bound",
            {"objective": "trial"},
        )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "current validated"):
            self.runtime.complete_action_node(
                "run-guard", "inspect_programming_scope", reason="skip inspection",
                completion_details={"claimed": "inspected"},
            )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "operation mismatch"):
            self.runtime.complete_action_node(
                "run-guard", "execute_approved_programming_step", reason="wrong node",
                completion_details={"attempt": 1},
            )
        self.observed_action(
            "run-guard", "inspect_programming_scope", "scope inspected",
            {"scope": "exact"},
        )
        self.transition("run-guard", "PROCEED", "mode-after-scope", "scope valid")
        self.runtime.advance_decision("run-guard", "prg_run", reason="enter planning")
        plan = self.runtime.record_inline_artifact(
            "run-guard", "guard-plan", "exact plan", role="working", node_id="plan",
            action="produce_artifact", selector="scope:plan_outputs",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-guard", "produce_programming_plan", reason="plan produced",
            artifact_ids=[plan["artifact"]["artifact_id"]],
        )
        self.transition("run-guard", "REVISE", "plan", "plan needs revision")
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "current validated"):
            self.runtime.complete_action_node(
                "run-guard", "produce_programming_plan", reason="reuse old proof",
                artifact_ids=[plan["artifact"]["artifact_id"]],
            )

        checkpoint_graph = {
            "schema_version": pc.GRAPH_SCHEMA_VERSION,
            "graph_id": "trial/checkpoint",
            "entry_node_id": "approval",
            "nodes": [
                {"node_id": "approval", "kind": "human_checkpoint", "label": "Approve",
                 "authority_request_type": "plan_approval",
                 "on_approved_node_id": "work", "on_denied_node_id": "blocked"},
                {"node_id": "work", "kind": "action", "label": "Work",
                 "operation": "work", "next_node_id": "blocked",
                 "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT],
                 "evidence_requirement_ids": [], "external_effect": False},
                {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked",
                 "outcome": "blocked"},
            ],
        }
        checkpoint_definition = _definition("trial/checkpoint", graph=checkpoint_graph)
        self.create("run-checkpoint", checkpoint_definition)
        with self.assertRaises(gpr.AuthorityDeniedError):
            self.runtime.resolve_human_checkpoint(
                "run-checkpoint", "approved", decision_by="not-principal", reason="forged"
            )

        repository_graph = {
            "schema_version": pc.GRAPH_SCHEMA_VERSION,
            "graph_id": "trial/repository-zero-attempt",
            "entry_node_id": "produce",
            "nodes": [
                {"node_id": "produce", "kind": "action", "label": "Produce repository",
                 "operation": "produce_repository_result", "next_node_id": "review",
                 "authority_grant_ids": ["trial-grant"], "artifact_access": [OUTPUT],
                 "evidence_requirement_ids": ["result_verified"], "external_effect": False},
                {"node_id": "review", "kind": "verification_boundary", "label": "Review",
                 "evidence_requirement_ids": ["result_verified"],
                 "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"}},
                {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted",
                 "outcome": "accepted"},
                {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked",
                 "outcome": "blocked"},
            ],
        }
        repository_definition = _definition(
            "trial/repository-zero-attempt", graph=repository_graph
        )
        repository = Path(self.temp.name) / "zero-attempt-repository"
        repository.mkdir()
        (repository / "result.txt").write_text("current repository result\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(
            ["git", "config", "user.email", "trial@example.test"],
            cwd=repository, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Phase Trial"],
            cwd=repository, check=True,
        )
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-qm", "result"], cwd=repository, check=True)
        self.create("run-zero-attempt", repository_definition)
        repository_result = self.repository_artifact(
            "run-zero-attempt", repository, "repository-result", role="result"
        )
        self.runtime.complete_action_node(
            "run-zero-attempt", "produce_repository_result", reason="result captured",
            artifact_ids=[repository_result["artifact"]["artifact_id"]],
        )
        repository_evidence = self.runtime.record_inline_artifact(
            "run-zero-attempt", "repository-result-proof", "synthetic pass",
            role="evidence", node_id="review", action="record_evidence",
            selector=OUTPUT, source_artifact_ids=["repository-result"],
            satisfied_conditions=CONDITIONS,
        )
        repository_review = self.runtime.record_final_review(
            "run-zero-attempt", artifact_id="repository-result",
            evidence_id="result_verified",
            evidence_artifact_id=repository_evidence["artifact"]["artifact_id"],
            outcome="PASS", reviewer_id="independent-reviewer", independent=True,
            satisfied_conditions=CONDITIONS,
        )
        with self.assertRaisesRegex(
            gpr.FinalReviewRequired, "successful completed attempt"
        ):
            self.runtime.apply_transition(
                "run-zero-attempt", "ACCEPT", target_node_id="accepted",
                reason="zero-attempt bypass", evaluation_boundary="review-review",
                evidence_refs=repository_review["evidence_refs"],
            )
        self.assertEqual(self.runtime.load_run("run-zero-attempt")["state"], "running")
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type") == "attempt_completed"
            for record in self.runtime.load_records("run-zero-attempt")
        ))
        repository_digest = repository_result["artifact"]["identity"]["digest"]
        self.runtime.begin_attempt("run-zero-attempt", "repository-check")
        self.runtime.complete_attempt(
            "run-zero-attempt", "repository-check", defect_codes=[],
            evidence_refs=[], artifact_digests=[repository_digest],
        )
        with self.assertRaisesRegex(
            gpr.FinalReviewRequired, "PASS attempt evidence"
        ):
            self.runtime.apply_transition(
                "run-zero-attempt", "ACCEPT", target_node_id="accepted",
                reason="evidence-free attempt bypass",
                evaluation_boundary="review-review",
                evidence_refs=repository_review["evidence_refs"],
            )
        attempt_evidence_ref = {
            "evidence_id": "result_verified",
            "artifact_id": repository_evidence["artifact"]["artifact_id"],
            "identity_digest": repository_evidence["artifact"]["identity"]["digest"],
            "outcome": "PASS",
        }
        self.runtime.begin_attempt("run-zero-attempt", "repository-check")
        self.runtime.complete_attempt(
            "run-zero-attempt", "repository-check", defect_codes=[],
            evidence_refs=[attempt_evidence_ref], artifact_digests=[repository_digest],
        )
        self.runtime.apply_transition(
            "run-zero-attempt", "ACCEPT", target_node_id="accepted",
            reason="successful identity-bound repository attempt",
            evaluation_boundary="review-review",
            evidence_refs=repository_review["evidence_refs"],
        )
        self.assertEqual(self.runtime.load_run("run-zero-attempt")["state"], "completed")

    def test_exact_version_registry_is_immutable_and_never_selects_latest(self):
        root = Path(self.temp.name) / "registry"
        registry = registry_module.ProcessDefinitionRegistry(root, now=lambda: NOW)
        programming = _programming_definition()
        self.assertEqual(
            programming["digest"],
            "sha256:b79d06b401ca54ec62588ab9cd64393fc049d4cf599298a5b057d93aa4e2a927",
        )
        programming_receipt = registry.register(programming)
        self.assertEqual(programming_receipt["definition_ref"], _definition_ref(programming))
        self.assertEqual(
            registry.resolve(
                programming["definition_id"], programming["version"], programming["digest"]
            ),
            programming,
        )
        programming_path = registry._definition_path(
            programming["definition_id"], programming["version"]
        )
        stored_programming = json.loads(programming_path.read_text(encoding="utf-8"))
        stored_programming["definition"]["graph"]["nodes"][0]["label"] = (
            "Tampered Programming graph"
        )
        stored_programming["storage_content_digest"] = _digest_json(
            stored_programming["definition"]
        )
        programming_path.write_text(
            json.dumps(stored_programming, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(registry_module.DefinitionIntegrityError):
            registry.resolve(
                programming["definition_id"], programming["version"], programming["digest"]
            )
        with self.assertRaises(registry_module.DefinitionIntegrityError):
            registry.list_definition_refs()

        programming_anchor_path = registry._anchor_path(
            programming["definition_id"], programming["version"]
        )
        stored_anchor = json.loads(
            programming_anchor_path.read_text(encoding="utf-8")
        )
        stored_anchor["storage_content_digest"] = stored_programming[
            "storage_content_digest"
        ]
        os.chmod(programming_anchor_path, 0o600)
        programming_anchor_path.write_text(
            json.dumps(stored_anchor, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            registry_module.DefinitionIntegrityError, "canonical projection"
        ):
            registry.resolve(
                programming["definition_id"], programming["version"], programming["digest"]
            )
        with self.assertRaisesRegex(
            registry_module.DefinitionIntegrityError, "canonical projection"
        ):
            registry.list_definition_refs()

        root = Path(self.temp.name) / "synthetic-registry"
        registry = registry_module.ProcessDefinitionRegistry(root, now=lambda: NOW)
        first = _definition("business/cash-review", version="1.0.0")
        second = _definition("business/cash-review", version="1.1.0")
        receipt = registry.register(first)
        self.assertFalse(receipt["activated"])
        self.assertFalse(receipt["idempotent"])
        self.assertTrue(registry.register(first)["idempotent"])
        registry.register(second)
        self.assertEqual(
            registry.resolve(first["definition_id"], first["version"], first["digest"]),
            first,
        )
        with self.assertRaises(registry_module.DefinitionNotFoundError):
            registry.resolve(first["definition_id"], first["version"], second["digest"])
        attacked = copy.deepcopy(first)
        attacked["title"] = "Conflicting body"
        with self.assertRaisesRegex(
            registry_module.DefinitionIntegrityError, "normalized content digest"
        ):
            registry.register(attacked)
        _seal_definition(attacked)
        self.assertNotEqual(attacked["digest"], first["digest"])
        with self.assertRaises(registry_module.DefinitionVersionConflict):
            registry.register(attacked)

        stored_path = registry._definition_path(first["definition_id"], first["version"])
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
        stored["definition"]["graph"]["nodes"][0]["label"] = (
            "Tampered after registration"
        )
        stored["storage_content_digest"] = _digest_json(stored["definition"])
        stored_path.write_text(
            json.dumps(stored, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        anchor_path = registry._anchor_path(first["definition_id"], first["version"])
        stored_anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        stored_anchor["storage_content_digest"] = stored["storage_content_digest"]
        os.chmod(anchor_path, 0o600)
        anchor_path.write_text(
            json.dumps(stored_anchor, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            registry_module.DefinitionIntegrityError, "normalized content digest"
        ):
            registry.resolve(first["definition_id"], first["version"], first["digest"])
        with self.assertRaisesRegex(
            registry_module.DefinitionIntegrityError, "normalized content digest"
        ):
            registry.list_definition_refs()


class TestProgrammingTrial(TrialCase):
    def _write_attempt(self, repository: Path, attempt: int) -> None:
        implementations = {
            1: """def allocate(stock, requests):\n    result = {}\n    for sku, qty in requests:\n        if qty > stock[sku]:\n            raise ValueError('capacity')\n        result[sku] = qty\n        stock[sku] -= qty\n    return result\n""",
            2: """def allocate(stock, requests):\n    result = {}\n    for sku, qty in requests:\n        if qty < 0 or qty > stock[sku]:\n            raise ValueError('quantity')\n        result[sku] = qty\n        stock[sku] -= qty\n    return result\n""",
            3: """def allocate(stock, requests):\n    result = {}\n    for sku, qty in requests:\n        if qty < 0 or qty > stock[sku]:\n            raise ValueError('quantity')\n        result[sku] = result.get(sku, 0) + qty\n        stock[sku] -= qty\n    return result\n""",
        }
        (repository / "inventory.py").write_text(implementations[attempt], encoding="utf-8")

    def test_nontrivial_repository_change_exercises_full_correction_and_recovery(self):
        definition = _programming_definition()
        self.assertEqual(definition["version"], "2.0.1")
        repository = Path(self.temp.name) / "repository"
        (repository / "tests").mkdir(parents=True)
        (repository / "inventory.py").write_text(
            "def allocate(stock, requests):\n    raise NotImplementedError\n", encoding="utf-8"
        )
        (repository / "tests" / "test_inventory.py").write_text(
            """import unittest\nfrom inventory import allocate\n\nclass InventoryTest(unittest.TestCase):\n    def test_capacity(self):\n        with self.assertRaises(ValueError):\n            allocate({'A': 2}, [('A', 3)])\n\n    def test_negative(self):\n        with self.assertRaises(ValueError):\n            allocate({'A': 2}, [('A', -1)])\n""",
            encoding="utf-8",
        )
        (repository / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.email", "trial@example.test"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.name", "Phase Trial"], cwd=repository, check=True)
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)

        run_id = "run-programming-trial"
        self.create(run_id, definition, entrypoint="prg_run")
        self.runtime.advance_decision(run_id, "prg_run", reason="confirmed PRG-Run")
        self.observed_action(
            run_id, "elicit_programming_intent", "objective confirmed",
            {"objective": "aggregate inventory allocations safely"},
        )
        self.observed_action(
            run_id, "inspect_programming_scope", "repository inspected",
            {"repository": str(repository)},
        )
        self.transition(run_id, "PROCEED", "mode-after-scope", "scope accepted")
        self.runtime.advance_decision(run_id, "prg_run", reason="plan required")
        plan = self.runtime.record_inline_artifact(
            run_id, "approved-plan", "Validate quantities and allocate each request.",
            role="working", node_id="plan", action="produce_artifact", selector="scope:plan_outputs",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            run_id, "produce_programming_plan", reason="plan produced",
            artifact_ids=[plan["artifact"]["artifact_id"]],
        )
        self.transition(run_id, "PROCEED", "plan-approval", "plan independently reviewed")
        self.runtime.resolve_human_checkpoint(
            run_id, "approved", decision_by="principal-001", reason="exact plan approved"
        )
        self.runtime.advance_decision(run_id, "prg_run", reason="approved execution")
        self.observed_action(
            run_id, "programming_preflight", "identities current",
            {"plan_digest": plan["artifact"]["identity"]["digest"]},
        )

        self.runtime.begin_attempt(run_id, "inventory-change")
        attempt_one_pre = self.repository_artifact(
            run_id, repository, "repository-pre-attempt-1", role="working"
        )
        self._write_attempt(repository, 1)
        attempt_one_state = self.repository_artifact(
            run_id, repository, "repository-state-attempt-1", role="working"
        )
        receipt_one = self.repository_mutation(
            run_id, repository, "execute_approved_programming_step", "attempt-1",
            attempt_one_pre, attempt_one_state,
        )
        _attempt_one_evidence, attempt_one_ref, attempt_one_test = (
            self.repository_test_evidence(
                run_id, repository, "repository-state-attempt-1",
                "repository-tests-attempt-1",
            )
        )
        self.assertNotEqual(attempt_one_test["returncode"], 0)
        self.runtime.complete_attempt(
            run_id, "inventory-change", defect_codes=["negative_quantity_unchecked"],
            evidence_refs=[attempt_one_ref],
            artifact_digests=[attempt_one_state["artifact"]["identity"]["digest"]],
        )
        self.transition(run_id, "REVISE", "revision-route", "execution defect")
        self.runtime.advance_decision(run_id, "prg_run", reason="PRG-Run correction")
        self.runtime.advance_bounded_loop(run_id, continue_loop=True, reason="one bounded correction")

        self.runtime.begin_attempt(run_id, "inventory-change")
        attempt_two_pre = self.repository_artifact(
            run_id, repository, "repository-pre-attempt-2", role="working"
        )
        self._write_attempt(repository, 2)
        attempt_two_state = self.repository_artifact(
            run_id, repository, "repository-state-attempt-2", role="working"
        )
        receipt_two = self.repository_mutation(
            run_id, repository, "correct_programming_defect", "attempt-2",
            attempt_two_pre, attempt_two_state,
        )
        _initial_two_evidence, initial_two_ref, initial_two_test = (
            self.repository_test_evidence(
                run_id, repository, "repository-state-attempt-2",
                "repository-tests-attempt-2-initial",
            )
        )
        self.assertEqual(initial_two_test["returncode"], 0)
        before_editor, before_editor_digest = _repository_composite(repository)
        (repository / "tests" / "test_inventory.py").write_text(
            (repository / "tests" / "test_inventory.py").read_text(encoding="utf-8")
            + """\n    def test_duplicate_sku_is_aggregated(self):\n        self.assertEqual(allocate({'A': 10}, [('A', 3), ('A', 2)]), {'A': 5})\n""",
            encoding="utf-8",
        )
        editor_state = self.repository_artifact(
            run_id, repository, "repository-state-attempt-2-editor", role="working"
        )
        self.runtime.record_event(
            run_id,
            "external_editor_change_observed",
            {
                "path": "tests/test_inventory.py",
                "identity_digest": _digest_bytes(
                    (repository / "tests" / "test_inventory.py").read_bytes()
                ),
                "effect": "independent test added",
                "repository_pre_identity_digest": before_editor_digest,
                "repository_post_identity_digest": editor_state["artifact"]["identity"]["digest"],
                "repository_pre_composite": before_editor,
            },
        )
        _attempt_two_evidence, attempt_two_ref, attempt_two_test = (
            self.repository_test_evidence(
                run_id, repository, "repository-state-attempt-2-editor",
                "repository-tests-attempt-2-editor",
            )
        )
        self.assertNotEqual(attempt_two_test["returncode"], 0)
        self.runtime.complete_attempt(
            run_id, "inventory-change", defect_codes=["plan_omitted_duplicate_semantics"],
            evidence_refs=[initial_two_ref, attempt_two_ref],
            artifact_digests=[editor_state["artifact"]["identity"]["digest"]],
        )
        self.runtime.create_checkpoint(
            run_id, "before-replan", segment_id="inventory-change", resume_node_id="replan-route"
        )
        self.transition(run_id, "REPLAN", "replan-route", "plan defect")
        self.runtime.resume_run(run_id)
        self.runtime.advance_decision(run_id, "prg_run", reason="PRG-Run may replan")
        revised_plan = self.runtime.record_inline_artifact(
            run_id, "approved-plan", "Validate quantities and aggregate duplicate SKU allocations.",
            role="working", node_id="plan", action="produce_artifact", selector="scope:plan_outputs",
            satisfied_conditions=CONDITIONS,
        )
        self.assertTrue(revised_plan["record"]["event"]["details"]["stale_review_invalidated"])
        self.runtime.complete_action_node(
            run_id, "produce_programming_plan", reason="replacement plan produced",
            artifact_ids=["approved-plan"],
        )
        self.transition(run_id, "PROCEED", "plan-approval", "replacement plan reviewed")
        self.runtime.resolve_human_checkpoint(
            run_id, "approved", decision_by="principal-001", reason="replacement plan approved"
        )
        self.runtime.advance_decision(run_id, "prg_run", reason="resume approved execution")
        self.observed_action(
            run_id, "programming_preflight", "replacement identities current",
            {"plan_digest": revised_plan["artifact"]["identity"]["digest"]},
        )

        self.runtime.begin_attempt(run_id, "inventory-change")
        attempt_three_pre = self.repository_artifact(
            run_id, repository, "repository-pre-attempt-3", role="working"
        )
        self._write_attempt(repository, 3)
        attempt_three_state = self.repository_artifact(
            run_id, repository, "repository-state-attempt-3", role="working"
        )
        receipt_three = self.repository_mutation(
            run_id, repository, "execute_approved_programming_step", "attempt-3",
            attempt_three_pre, attempt_three_state,
        )
        _attempt_three_evidence, attempt_three_ref, attempt_three_test = (
            self.repository_test_evidence(
                run_id, repository, "repository-state-attempt-3",
                "repository-tests-attempt-3",
            )
        )
        self.assertEqual(attempt_three_test["returncode"], 0)
        self.runtime.complete_attempt(
            run_id, "inventory-change", defect_codes=[], evidence_refs=[attempt_three_ref],
            artifact_digests=[attempt_three_state["artifact"]["identity"]["digest"]],
        )
        self.transition(run_id, "PROCEED", "work-remaining", "attempt independently passed")
        self.runtime.advance_decision(run_id, "prg_run", reason="apply PRG-Run path")
        self.runtime.advance_decision(run_id, "no_authorized_work_remains", reason="work complete")

        result = self.repository_artifact(
            run_id, repository, "repository-result", role="result",
            node_id="execute-step",
        )
        final_evidence_before_restart, _final_ref_before_restart, final_test_before_restart = (
            self.repository_test_evidence(
                run_id, repository, "repository-result",
                "repository-tests-final-before-restart",
            )
        )
        self.assertEqual(final_test_before_restart["returncode"], 0)
        self.runtime.record_final_review(
            run_id, artifact_id="repository-result", evidence_id="result_verified",
            evidence_artifact_id=final_evidence_before_restart["artifact"]["artifact_id"],
            outcome="PASS", reviewer_id="independent-reviewer", independent=True,
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.pause_run(
            run_id, "restart-before-accept", segment_id="final-review",
            resume_node_id="final-review", reason="restart trial",
        )
        repository_before_restart_drift = result["composite"]
        (repository / "inventory.py").write_text(
            (repository / "inventory.py").read_text(encoding="utf-8")
            + "\n# restart drift recaptured before acceptance\n",
            encoding="utf-8",
        )
        changed = self.repository_artifact(
            run_id, repository, "repository-result", role="result",
            node_id="execute-step",
        )
        self.runtime.record_event(
            run_id, "restart_repository_drift_observed",
            {
                "repository": str(repository.resolve()),
                "pre_identity_digest": result["artifact"]["identity"]["digest"],
                "post_identity_digest": changed["artifact"]["identity"]["digest"],
                "pre_composite": repository_before_restart_drift,
                "post_composite": changed["composite"],
            },
        )
        decision = self.runtime.recovery_decision(run_id)
        self.assertEqual(decision["changed_artifact_ids"], ["repository-result"])
        self.assertEqual(decision["revalidate_evidence_ids"], ["result_verified"])
        self.runtime.resume_run(run_id)

        self.runtime.begin_attempt(run_id, "restart-revalidation")
        final_evidence, final_test_ref, final_test = self.repository_test_evidence(
            run_id, repository, "repository-result", "repository-tests-final"
        )
        self.assertEqual(final_test["returncode"], 0)
        self.assertEqual(
            final_test["repository_identity_digest"],
            changed["artifact"]["identity"]["digest"],
        )
        self.runtime.complete_attempt(
            run_id, "restart-revalidation", defect_codes=[],
            evidence_refs=[final_test_ref],
            artifact_digests=[changed["artifact"]["identity"]["digest"]],
        )

        with self.assertRaisesRegex(
            gpr.GovernedRuntimeError, "semantic identity binding"
        ):
            self.runtime.record_inline_artifact(
                run_id, "repository-result", "synthetic hash-chain substitute",
                role="result", node_id="execute-step", action="produce_artifact",
                selector=OUTPUT, satisfied_conditions=CONDITIONS,
            )
        unrelated = self.runtime.record_inline_artifact(
            run_id, "unrelated-hash-chain", "synthetic unrelated result hash",
            role="working", node_id="execute-step", action="produce_artifact",
            selector=OUTPUT, satisfied_conditions=CONDITIONS,
        )
        unrelated_evidence = self.runtime.record_inline_artifact(
            run_id, "unrelated-hash-chain-proof", "independent synthetic proof",
            role="evidence", node_id="final-review", action="record_evidence",
            selector=OUTPUT, source_artifact_ids=["unrelated-hash-chain"],
            satisfied_conditions=CONDITIONS,
        )
        unrelated_review = self.runtime.record_final_review(
            run_id, artifact_id=unrelated["artifact"]["artifact_id"],
            evidence_id="result_verified",
            evidence_artifact_id=unrelated_evidence["artifact"]["artifact_id"],
            outcome="PASS", reviewer_id="independent-reviewer", independent=True,
            satisfied_conditions=CONDITIONS,
        )
        with self.assertRaises(gpr.FinalReviewRequired):
            self.runtime.apply_transition(
                run_id, "ACCEPT", target_node_id="accepted",
                reason="unrelated hash cannot authorize repository completion",
                evaluation_boundary="review-final-review",
                evidence_refs=unrelated_review["evidence_refs"],
            )

        final_review = self.runtime.record_final_review(
            run_id, artifact_id="repository-result", evidence_id="result_verified",
            evidence_artifact_id=final_evidence["artifact"]["artifact_id"],
            outcome="PASS", reviewer_id="independent-reviewer", independent=True,
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.apply_transition(
            run_id, "ACCEPT", target_node_id="accepted", reason="verified completion",
            evaluation_boundary="review-final-review",
            evidence_refs=final_review["evidence_refs"],
        )
        self.assertEqual(self.runtime.load_run(run_id)["state"], "completed")
        persisted_result = self.runtime.load_artifact(run_id, "repository-result")
        self.assertEqual(persisted_result["identity"]["kind"], "composite")
        self.assertEqual(persisted_result["locator"], {
            "kind": "git_ref", "ref": str(repository.resolve())
        })
        self.assertEqual(
            persisted_result["identity"]["digest"],
            changed["artifact"]["identity"]["digest"],
        )
        self.assertEqual(
            final_review["event"]["details"]["subject_digest"],
            persisted_result["identity"]["digest"],
        )
        self.assertEqual(
            final_evidence["artifact"]["lineage"]["source_artifact_ids"],
            ["repository-result"],
        )
        for receipt, state in (
            (receipt_one, attempt_one_state),
            (receipt_two, attempt_two_state),
            (receipt_three, attempt_three_state),
        ):
            self.assertEqual(
                receipt["payload"]["post_state"]["identity_digest"],
                state["artifact"]["identity"]["digest"],
            )
            source_identities = receipt["receipt"]["record"]["event"]["details"][
                "source_artifact_identities"
            ]
            self.assertIn(
                state["artifact"]["identity"]["digest"],
                {item["identity_digest"] for item in source_identities},
            )
        self.assertEqual(
            _digest_bytes(Path(final_evidence["artifact"]["locator"]["ref"]).read_bytes()),
            final_evidence["artifact"]["identity"]["digest"],
        )
        directives = [
            record["transition"]["directive"] for record in self.runtime.load_records(run_id)
            if record["record_type"] == "transition"
        ]
        self.assertIn("REVISE", directives)
        self.assertIn("REPLAN", directives)
        self.assertEqual(directives[-1], "ACCEPT")

    def test_programming_kernel_persists_twelve_attempts_without_state_loss(self):
        definition = _programming_definition()
        self.create("run-attempt-ceiling", definition, entrypoint="prg_run")
        for attempt in range(1, 13):
            self.runtime.begin_attempt("run-attempt-ceiling", "long-change")
            self.runtime.complete_attempt(
                "run-attempt-ceiling", "long-change", defect_codes=[f"defect-{attempt}"],
                evidence_refs=[], artifact_digests=[_digest_text(str(attempt))],
            )
            reloaded = gpr.GovernedProcessRuntime(
                Path(self.temp.name) / "runs", now=lambda: NOW
            ).load_run("run-attempt-ceiling")
            self.assertEqual(reloaded["contracts"]["correction_loop"]["attempt"], attempt)
        with self.assertRaises(gpr.CorrectionDecisionRequired):
            self.runtime.begin_attempt("run-attempt-ceiling", "long-change")


class TestCrossDomainReusableDefinitionTrial(TrialCase):
    def test_spreadsheet_process_is_registered_invoked_verified_and_authority_bounded(self):
        self.assertTrue(WORKBOOK.is_file())
        with zipfile.ZipFile(WORKBOOK) as archive:
            calculation = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
            verification = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
        self.assertIn("SUMIF", calculation)
        self.assertIn("AUTHORITY REQUIRED", calculation)
        self.assertEqual(verification.count(">PASS<"), 3)

        child_definition = _cash_review_definition()
        construction_definition = _construction_definition(child_definition)
        registry = registry_module.ProcessDefinitionRegistry(
            Path(self.temp.name) / "definitions", now=lambda: NOW
        )
        self.create("run-definition-construction", construction_definition)
        definition_artifact = self.runtime.record_inline_artifact(
            "run-definition-construction",
            "cash-review-definition",
            json.dumps(child_definition, sort_keys=True),
            role="process_definition",
            node_id="construct-definition",
            action="construct_definition",
            selector=DEFINITION_SCOPE,
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-definition-construction",
            "construct_reusable_process_definition",
            reason="Exact reusable spreadsheet definition constructed",
            artifact_ids=[definition_artifact["artifact"]["artifact_id"]],
        )
        registration = registry.register(child_definition)
        registration_result = self.runtime.record_inline_artifact(
            "run-definition-construction",
            "cash-review-registration",
            json.dumps(registration, sort_keys=True),
            role="result",
            node_id="register-definition",
            action="register_definition",
            selector=DEFINITION_SCOPE,
            source_artifact_ids=["cash-review-definition"],
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-definition-construction",
            "register_reusable_process_definition",
            reason="Exact approved definition registered without activation",
            artifact_ids=[registration_result["artifact"]["artifact_id"]],
        )
        self.accept_existing_result(
            "run-definition-construction", "cash-review-registration"
        )
        exact = registry.resolve(
            child_definition["definition_id"],
            child_definition["version"],
            child_definition["digest"],
        )
        self.assertEqual(registration["definition_ref"], _definition_ref(exact))
        self.assertFalse(registration["activated"])
        self.assertEqual(
            self.runtime.load_run("run-definition-construction")["state"],
            "completed",
        )

        parent_definition = _calling_definition("business/monthly-cash-close", exact)
        self.create(
            "run-cash-parent",
            parent_definition,
            child_definitions=(exact,),
        )
        child_run = _trial_run("run-cash-child", exact)
        self.runtime.invoke_child(
            "run-cash-parent",
            exact,
            child_run,
            call_node_id="call-child",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.start_run("run-cash-child", reason="Exact registered version invoked")
        workbook = self.file_result(
            "run-cash-child",
            "cash-flow-workbook",
            WORKBOOK,
            node_id="calculate",
        )
        self.runtime.complete_action_node(
            "run-cash-child",
            "calculate_permitted_cash_flow",
            reason="Formula-driven workbook produced",
            artifact_ids=["cash-flow-workbook"],
        )
        self.accept_existing_result("run-cash-child", "cash-flow-workbook")
        returned = self.runtime.return_child(
            "run-cash-child", output_artifact_ids=["cash-flow-workbook"]
        )
        binding = returned["parent_record"]["event"]["details"]["output_bindings"][0]
        self.assertEqual(binding["definition_ref"], _definition_ref(exact))
        self.assertEqual(
            binding["identity_digest"], workbook["artifact"]["identity"]["digest"]
        )
        self.assertEqual(binding["acceptance_evidence"][0]["outcome"], "PASS")
        self.runtime.complete_process_return_node(
            "run-cash-parent",
            child_run_id="run-cash-child",
            reason="Exact accepted workbook returned",
        )
        parent_result = self.runtime.record_inline_artifact(
            "run-cash-parent",
            "cash-close-result",
            json.dumps({
                "workbook_digest": binding["identity_digest"],
                "permitted_closing_cash": 140000,
                "reserved_amount": -35000,
            }, sort_keys=True),
            role="result",
            node_id="summarize",
            action="produce_artifact",
            selector=OUTPUT,
            source_artifact_ids=["cash-flow-workbook"],
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-cash-parent",
            "summarize_child_result",
            reason="Returned identity bound to close result",
            artifact_ids=[parent_result["artifact"]["artifact_id"]],
        )
        self.accept_existing_result("run-cash-parent", "cash-close-result")
        self.assertEqual(self.runtime.load_run("run-cash-parent")["state"], "completed")

        exception_parent_definition = _calling_definition(
            "business/monthly-cash-close-exception", exact
        )
        self.create(
            "run-exception-parent",
            exception_parent_definition,
            child_definitions=(exact,),
        )
        exception_child = _trial_run("run-exception-child", exact)
        self.runtime.invoke_child(
            "run-exception-parent",
            exact,
            exception_child,
            call_node_id="call-child",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.start_run("run-exception-child", reason="Exception trial")
        self.observed_action(
            "run-exception-child",
            "calculate_permitted_cash_flow",
            "Reserved tax settlement withheld",
            {"reserved_amount": -35000, "included": False},
        )
        request = {
            "request_id": "cash-authority-001",
            "request_type": "calculation_exception",
            "requested_authority": ["expand_scope"],
            "options": ["authorize tax settlement", "leave it excluded"],
            "resume_node_id": "calculate",
            "requested_from": "principal-001",
        }
        self.runtime.apply_transition(
            "run-exception-child",
            "ESCALATE",
            target_node_id="authority",
            reason="Tax settlement is reserved from inferred authority",
            evaluation_boundary="review-review",
            authority_request=request,
            evidence_refs=[self.evidence_ref("run-exception-child", "reserved-tax-withheld")],
        )
        stopped = self.runtime.load_run("run-exception-child")
        self.assertEqual(stopped["state"], "waiting_for_authority")
        self.assertEqual(stopped["current_node_id"], "authority")
        actions = [
            (record.get("event") or {}).get("details", {}).get("action")
            for record in self.runtime.load_records("run-exception-child")
        ]
        self.assertNotIn("expand_scope", actions)

    def test_process_return_rejects_wrong_child_and_reuse(self):
        child = _cash_review_definition()
        parent = _calling_definition("business/return-guard", child)
        self.create("run-return-parent", parent, child_definitions=(child,))
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "requires a process_return"):
            self.runtime.complete_process_return_node(
                "run-return-parent", child_run_id="missing-child", reason="forged return"
            )


class TestProblemEvolutionContingentTrial(TrialCase):
    def _complete_leaf(
        self,
        run_id: str,
        operation: str,
        result_id: str,
        result_text: str,
    ) -> dict:
        result = self.runtime.record_inline_artifact(
            run_id,
            result_id,
            result_text,
            role="result",
            node_id="work",
            action="produce_artifact",
            selector=OUTPUT,
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            run_id,
            operation,
            reason=f"{operation} produced exact result",
            artifact_ids=[result_id],
        )
        self.accept_existing_result(run_id, result_id)
        return result

    def test_second_goal_is_causally_bound_to_first_evidence_through_pif_pff_and_execution(self):
        pif = _leaf_definition("ora/process-inference-trial", "infer_inventory_process")
        pff = _leaf_definition("ora/process-formalization-trial", "formalize_inventory_process")
        execution = _leaf_definition("business/inventory-replenishment", "execute_replenishment")
        pef = _pef_parent_definition(pif, pff, execution)
        registry = registry_module.ProcessDefinitionRegistry(
            Path(self.temp.name) / "pef-definitions", now=lambda: NOW
        )
        self.create(
            "run-pef",
            pef,
            child_definitions=(pif, pff, execution),
        )
        interim = self.runtime.record_inline_artifact(
            "run-pef",
            "interim-goal-contract",
            json.dumps({
                "first_goal": "Measure the actual stock/demand gap for SKU A",
                "next_goal_rule": "Select only after accepted measurement evidence",
                "locked_end_state": "Replenishment decision with no stockout",
            }, sort_keys=True),
            role="working",
            node_id="establish-interim-contract",
            action="produce_artifact",
            selector=OUTPUT,
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-pef",
            "establish_interim_goal_contract",
            reason="Interim contract persisted before discovery",
            artifact_ids=[interim["artifact"]["artifact_id"]],
        )

        pif_run = _trial_run("run-pef-pif", pif)
        self.runtime.invoke_child(
            "run-pef", pif, pif_run, call_node_id="call-pif",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.start_run("run-pef-pif", reason="Infer from bounded first goal")
        pif_result = self._complete_leaf(
            "run-pef-pif",
            "infer_inventory_process",
            "inventory-gap-evidence",
            json.dumps({"sku": "A", "available": 5, "committed_demand": 8}, sort_keys=True),
        )
        pif_return = self.runtime.return_child(
            "run-pef-pif", output_artifact_ids=["inventory-gap-evidence"]
        )
        self.runtime.complete_process_return_node(
            "run-pef", child_run_id="run-pef-pif", reason="Accepted PIF evidence returned"
        )

        dependent_goal = self.runtime.record_inline_artifact(
            "run-pef",
            "evidence-dependent-goal",
            json.dumps({
                "evidence_digest": pif_result["artifact"]["identity"]["digest"],
                "second_goal": "Replenish exactly 3 units of SKU A",
            }, sort_keys=True),
            role="working",
            node_id="derive-dependent-goal",
            action="produce_artifact",
            selector=OUTPUT,
            source_artifact_ids=["inventory-gap-evidence"],
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-pef",
            "derive_evidence_dependent_goal",
            reason="Second goal derived from exact accepted measurement",
            artifact_ids=[dependent_goal["artifact"]["artifact_id"]],
        )

        pff_run = _trial_run("run-pef-pff", pff)
        self.runtime.invoke_child(
            "run-pef", pff, pff_run, call_node_id="call-pff",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.start_run("run-pef-pff", reason="Formalize inferred replenishment")
        pff_result = self._complete_leaf(
            "run-pef-pff",
            "formalize_inventory_process",
            "formalized-definition",
            json.dumps(_definition_ref(execution), sort_keys=True),
        )
        self.runtime.return_child(
            "run-pef-pff", output_artifact_ids=["formalized-definition"]
        )
        self.runtime.complete_process_return_node(
            "run-pef", child_run_id="run-pef-pff", reason="Exact formalization returned"
        )
        registration = registry.register(execution)
        registration_artifact = self.runtime.record_inline_artifact(
            "run-pef",
            "definition-registration",
            json.dumps(registration, sort_keys=True),
            role="working",
            node_id="register-definition",
            action="register_definition",
            selector=DEFINITION_SCOPE,
            source_artifact_ids=[pff_result["artifact"]["artifact_id"]],
            satisfied_conditions=CONDITIONS,
        )
        exact_execution = registry.resolve(
            execution["definition_id"], execution["version"], execution["digest"]
        )
        self.runtime.complete_action_node(
            "run-pef",
            "register_exact_process_definition",
            reason="Approved exact version registered without activation",
            artifact_ids=[registration_artifact["artifact"]["artifact_id"]],
        )

        execution_run = _trial_run("run-pef-execution", exact_execution)
        self.runtime.invoke_child(
            "run-pef", exact_execution, execution_run, call_node_id="call-execution",
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.start_run("run-pef-execution", reason="Invoke exact registered version")
        execution_result = self._complete_leaf(
            "run-pef-execution",
            "execute_replenishment",
            "replenishment-result",
            json.dumps({"sku": "A", "ordered": 3, "remaining_gap": 0}, sort_keys=True),
        )
        execution_return = self.runtime.return_child(
            "run-pef-execution", output_artifact_ids=["replenishment-result"]
        )
        self.runtime.complete_process_return_node(
            "run-pef", child_run_id="run-pef-execution", reason="Verified execution returned"
        )
        evolved = self.runtime.record_inline_artifact(
            "run-pef",
            "updated-problem-state",
            json.dumps({
                "first_evidence": pif_result["artifact"]["identity"]["digest"],
                "completed_goal": "Replenish exactly 3 units of SKU A",
                "execution_evidence": execution_result["artifact"]["identity"]["digest"],
                "new_goal": "Monitor demand until the next stock threshold",
            }, sort_keys=True),
            role="result",
            node_id="update-problem-state",
            action="produce_artifact",
            selector=OUTPUT,
            source_artifact_ids=["inventory-gap-evidence", "replenishment-result"],
            satisfied_conditions=CONDITIONS,
        )
        self.runtime.complete_action_node(
            "run-pef",
            "update_problem_state_from_evidence",
            reason="Problem state and next goal updated from returned evidence",
            artifact_ids=[evolved["artifact"]["artifact_id"]],
        )
        self.accept_existing_result("run-pef", "updated-problem-state")
        self.assertEqual(self.runtime.load_run("run-pef")["state"], "completed")

        records = self.runtime.load_records("run-pef")
        sequences = {
            (record.get("event") or {}).get("details", {}).get("artifact_id"): record["sequence"]
            for record in records
            if (record.get("event") or {}).get("event_type") == "artifact_recorded"
        }
        pif_return_sequence = pif_return["parent_record"]["sequence"]
        self.assertGreater(sequences["evidence-dependent-goal"], pif_return_sequence)
        source_bindings = dependent_goal["record"]["event"]["details"]["source_artifact_identities"]
        self.assertEqual(source_bindings[0]["identity_digest"], pif_result["artifact"]["identity"]["digest"])
        invoked = [
            record["event"]["details"]["child_definition_ref"]["definition_id"]
            for record in records
            if (record.get("event") or {}).get("event_type") == "process_invoked"
        ]
        self.assertEqual(invoked, [pif["definition_id"], pff["definition_id"], execution["definition_id"]])
        self.assertEqual(
            execution_return["parent_record"]["event"]["details"]["output_bindings"][0]["acceptance_evidence"][0]["outcome"],
            "PASS",
        )
        self.assertFalse(registration["activated"])

    def test_known_procedure_routes_directly_without_problem_evolution(self):
        known = _cash_review_definition()
        parent = _calling_definition("business/known-procedure", known)
        run = _trial_run(
            "run-known-procedure", parent, child_definitions=(known,)
        )
        self.runtime.create_run(parent, run)
        self.runtime.start_run("run-known-procedure", reason="Known exact procedure")
        child = _trial_run("run-known-child", known)
        self.runtime.invoke_child(
            "run-known-procedure", known, child, call_node_id="call-child",
            satisfied_conditions=CONDITIONS,
        )
        refs = self.runtime.load_run("run-known-procedure")["relationships"][
            "invoked_definition_refs"
        ]
        self.assertEqual(refs, [_definition_ref(known)])
        self.assertFalse(any(ref["definition_id"].startswith("ora/problem-evolution") for ref in refs))
