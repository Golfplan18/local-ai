"""Phase 1.4 proof for the generic governed Process Run runtime."""

from __future__ import annotations

import copy
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


_ORCHESTRATOR = Path(__file__).resolve().parent.parent
if str(_ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(_ORCHESTRATOR))

import governed_process_runtime as gpr  # noqa: E402
import process_contracts as pc  # noqa: E402
from tests import test_process_contracts as fixtures  # noqa: E402


NOW = fixtures.NOW
CONDITION = ["approved_plan_digest_matches"]
OUTPUT = "scope:declared_outputs"
EXTERNAL = "scope:declared_external"


def _broaden_contracts(run: dict, *, child_selector: str | None = None) -> None:
    grant = run["contracts"]["authority"]["grants"][0]
    grant["actions"] = sorted(
        {
            *grant["actions"],
            "external_write",
            "invoke_process",
            "produce_artifact",
            "record_evidence",
        }
    )
    grant["resource_selectors"] = sorted(
        {*grant["resource_selectors"], EXTERNAL, *(child_selector and [child_selector] or [])}
    )
    grant["effect_types"] = ["external_irreversible", "local_reversible"]
    run["contracts"]["artifact_scope"]["external_effect_selectors"] = [EXTERNAL]
    if child_selector:
        run["contracts"]["artifact_scope"]["read_selectors"].append(child_selector)
    judgment = run["contracts"]["bounded_judgment"][0]
    judgment["permitted_directives"] = list(pc.TRANSITION_DIRECTIVES)


def make_definition(definition_id: str = "generic/work") -> dict:
    definition = fixtures.process_definition(definition_id, "Generic governed work")
    definition["graph"] = {
        "schema_version": pc.GRAPH_SCHEMA_VERSION,
        "graph_id": "governed/verification-entry",
        "entry_node_id": "verify",
        "nodes": [
            {
                "node_id": "verify",
                "kind": "verification_boundary",
                "label": "Inspect independent evidence",
                "evidence_requirement_ids": ["result_verified"],
                "routes": {
                    "PROCEED": "act",
                    "ACCEPT": "accepted",
                    "REVISE": "act",
                    "REPLAN": "verify",
                    "REDEFINE": "verify",
                    "ESCALATE": "verify",
                    "BLOCKED": "blocked",
                },
            },
            {
                "node_id": "act",
                "kind": "action",
                "label": "Perform the approved change",
                "operation": "apply_approved_change",
                "next_node_id": "verify",
                "authority_grant_ids": ["mutation"],
                "artifact_access": [OUTPUT],
                "evidence_requirement_ids": ["result_verified"],
                "external_effect": False,
            },
            {
                "node_id": "accepted",
                "kind": "terminal_state",
                "label": "Accepted",
                "outcome": "accepted",
            },
            {
                "node_id": "blocked",
                "kind": "terminal_state",
                "label": "Blocked",
                "outcome": "blocked",
            },
        ],
    }
    return definition


def make_run(
    run_id: str,
    definition: dict,
    *,
    state: str = "ready",
    current_node_id: str = "verify",
    child_selector: str | None = None,
) -> dict:
    run = fixtures.process_run(run_id)
    run["run_id"] = run_id
    run["definition_ref"] = {
        "definition_id": definition["definition_id"],
        "version": definition["version"],
        "digest": definition["digest"],
    }
    run["state"] = state
    run["current_node_id"] = current_node_id
    run["artifact_ids"] = []
    run["contracts"]["continuation"]["resume_node_id"] = current_node_id
    run["contracts"]["approved_plan"]["approved_node_ids"] = [
        node["node_id"] for node in definition["graph"]["nodes"]
    ]
    _broaden_contracts(run, child_selector=child_selector)
    return run


def evidence_ref(result: dict, outcome: str = "PASS") -> dict:
    return {
        "evidence_id": "result_verified",
        "artifact_id": result["artifact"]["artifact_id"],
        "identity_digest": result["artifact"]["identity"]["digest"],
        "outcome": outcome,
    }


class RuntimeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = gpr.GovernedProcessRuntime(self.temp.name, now=lambda: NOW)

    def create(self, run_id: str = "run-main") -> tuple[dict, dict]:
        definition = make_definition()
        run = make_run(run_id, definition)
        self.runtime.create_run(definition, run)
        self.runtime.start_run(run_id, reason="approved test plan is ready")
        return definition, run

    def result_and_evidence(
        self,
        run_id: str,
        *,
        result_text: str = "candidate result",
        evidence_text: str = "independent proof",
        result_id: str = "result",
        evidence_id: str = "evidence",
    ) -> tuple[dict, dict]:
        result = self.runtime.record_inline_artifact(
            run_id,
            result_id,
            result_text,
            role="result",
            node_id="act",
            action="produce_artifact",
            selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        evidence = self.runtime.record_inline_artifact(
            run_id,
            evidence_id,
            evidence_text,
            role="evidence",
            node_id="verify",
            action="record_evidence",
            selector=OUTPUT,
            source_artifact_ids=[result_id],
            satisfied_conditions=CONDITION,
        )
        return result, evidence

    def pass_review(self, run_id: str, result: dict, evidence: dict) -> dict:
        return self.runtime.record_final_review(
            run_id,
            artifact_id=result["artifact"]["artifact_id"],
            evidence_id="result_verified",
            evidence_artifact_id=evidence["artifact"]["artifact_id"],
            outcome="PASS",
            reviewer_id="independent-reviewer",
            independent=True,
            satisfied_conditions=CONDITION,
        )


class TestPersistentKernel(RuntimeCase):
    def test_runtime_exposes_no_agent_programming_or_controller_type(self):
        declared = {
            name for name, item in inspect.getmembers(gpr, inspect.isclass)
            if item.__module__ == gpr.__name__
        }
        lowered = {name.lower() for name in declared}
        self.assertFalse(any("agent" in name for name in lowered))
        self.assertFalse(any("programming" in name for name in lowered))
        self.assertFalse(any("controller" in name for name in lowered))

    def test_correction_defaults_are_explicit_configurable_and_strict(self):
        defaults = gpr.correction_policy_defaults()
        self.assertEqual(defaults["max_attempts"], 3)
        configured = gpr.correction_policy_defaults({"max_attempts": 12})
        self.assertEqual(configured["max_attempts"], 12)
        self.assertEqual(defaults["max_attempts"], 3)
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "unknown"):
            gpr.correction_policy_defaults({"force_churn": True})

    def test_ready_run_starts_only_at_approved_graph_entry(self):
        definition = make_definition()
        run = make_run(
            "run-ready", definition, state="ready", current_node_id="verify"
        )
        self.runtime.create_run(definition, run)
        started = self.runtime.start_run("run-ready", reason="approved plan is ready")
        self.assertEqual(started["event"]["event_type"], "run_started")
        self.assertEqual(self.runtime.load_run("run-ready")["state"], "running")
        with self.assertRaisesRegex(gpr.RunConflictError, "only a ready"):
            self.runtime.start_run("run-ready", reason="duplicate start")

    def test_creation_rejects_advanced_or_inconsistent_lifecycle_state(self):
        definition = make_definition()
        for index, state in enumerate(("running", "pending", "completed", "blocked")):
            with self.subTest(state=state):
                run = make_run(f"run-invalid-{index}", definition, state=state)
                with self.assertRaisesRegex(
                    gpr.GovernedRuntimeError, "lifecycle advancement requires persisted events"
                ):
                    self.runtime.create_run(definition, run)

        wrong_node = make_run("run-wrong-node", definition, current_node_id="act")
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "graph entry"):
            self.runtime.create_run(definition, wrong_node)
        sequenced = make_run("run-sequenced", definition)
        sequenced["last_sequence"] = 9
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "sequence zero"):
            self.runtime.create_run(definition, sequenced)

    def test_created_run_becomes_ready_and_running_only_through_events(self):
        definition = make_definition()
        run = make_run("run-lifecycle", definition, state="created")
        self.runtime.create_run(definition, run)
        ready = self.runtime.mark_run_ready(
            "run-lifecycle", reason="approved plan and bindings are complete"
        )
        started = self.runtime.start_run(
            "run-lifecycle", reason="start approved work"
        )
        self.assertEqual(ready["event"]["event_type"], "run_ready")
        self.assertEqual(started["event"]["event_type"], "run_started")
        self.assertEqual(self.runtime.load_run("run-lifecycle")["state"], "running")
        self.assertEqual(
            [
                record["event"]["event_type"]
                for record in self.runtime.load_records("run-lifecycle")
            ],
            ["run_created", "run_ready", "run_started"],
        )

    def test_persists_exactly_the_four_contract_families(self):
        self.create()
        self.result_and_evidence("run-main")

        families = set()
        for path in Path(self.temp.name).rglob("*.json"):
            families.add(json.loads(path.read_text(encoding="utf-8"))["object_family"])
        for path in Path(self.temp.name).rglob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                families.add(json.loads(line)["object_family"])

        self.assertEqual(families, set(pc.ROOT_OBJECT_FAMILIES))
        self.assertFalse(any(Path(self.temp.name).rglob("*controller*.json")))
        self.assertFalse(any(Path(self.temp.name).rglob("*attempt*.json")))
        self.assertFalse(any(Path(self.temp.name).rglob("*checkpoint*.json")))

    def test_segment_attempt_and_checkpoint_are_event_records(self):
        self.create()
        self.runtime.start_segment("run-main", "segment-a")
        self.runtime.begin_attempt("run-main", "segment-a")
        self.runtime.complete_attempt(
            "run-main",
            "segment-a",
            defect_codes=["missing-proof"],
            evidence_refs=[],
            artifact_digests=["sha256:" + "1" * 64],
        )
        self.runtime.pause_run(
            "run-main",
            "checkpoint-a",
            segment_id="segment-a",
            resume_node_id="verify",
            reason="safe handoff",
        )
        resumed = self.runtime.resume_run("run-main")

        event_types = [
            record["event"]["event_type"]
            for record in self.runtime.load_records("run-main")
            if record["record_type"] == "event"
        ]
        self.assertTrue(
            {"segment_started", "attempt_started", "attempt_completed", "checkpoint_created"}
            <= set(event_types)
        )
        self.assertFalse(resumed["decision"]["replay_mutations"])
        self.assertEqual(self.runtime.load_run("run-main")["state"], "running")

    def test_interrupted_materialization_folds_records_without_replaying_work(self):
        self.create()
        committed_before_attempt = self.runtime.load_run("run-main")
        self.runtime.begin_attempt("run-main", "segment-a")
        self.runtime.complete_attempt(
            "run-main", "segment-a", defect_codes=["proof-gap"],
            evidence_refs=[], artifact_digests=["sha256:" + "7" * 64],
        )
        self.runtime._run_path("run-main").write_text(  # simulate crash window
            json.dumps(committed_before_attempt), encoding="utf-8"
        )

        recovered = self.runtime.load_run("run-main")
        self.assertEqual(recovered["contracts"]["correction_loop"]["attempt"], 1)
        self.assertEqual(
            recovered["last_sequence"],
            self.runtime.load_records("run-main")[-1]["sequence"],
        )
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type") == "action_completed"
            for record in self.runtime.load_records("run-main")
        ))

    def test_artifact_store_refuses_symlink_redirection(self):
        self.create()
        outside = Path(self.temp.name) / "outside-artifacts"
        outside.mkdir()
        os.symlink(outside, self.runtime._run_dir("run-main") / "artifacts")
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "must not be a symlink"):
            self.runtime.record_inline_artifact(
                "run-main", "result", "candidate", role="result", node_id="act",
                action="produce_artifact", selector=OUTPUT,
                satisfied_conditions=CONDITION,
            )


class TestCorrectionAndInfrastructurePolicy(RuntimeCase):
    def test_attempts_must_start_and_complete_in_sequence(self):
        self.create()
        with self.assertRaisesRegex(gpr.RunConflictError, "active attempt"):
            self.runtime.complete_attempt(
                "run-main", "segment-a", defect_codes=[], evidence_refs=[],
                artifact_digests=[],
            )
        self.runtime.begin_attempt("run-main", "segment-a")
        with self.assertRaisesRegex(gpr.RunConflictError, "must complete"):
            self.runtime.begin_attempt("run-main", "segment-a")
        with self.assertRaisesRegex(gpr.RunConflictError, "segment"):
            self.runtime.complete_attempt(
                "run-main", "segment-b", defect_codes=[], evidence_refs=[],
                artifact_digests=[],
            )

    def test_high_attempt_ceiling_permits_but_does_not_force_attempts(self):
        self.create()
        for number in range(1, 13):
            record = self.runtime.begin_attempt("run-main", "segment-a")
            self.assertEqual(record["event"]["details"]["attempt"], number)
            self.runtime.complete_attempt(
                "run-main", "segment-a", defect_codes=[f"defect-{number}"],
                evidence_refs=[], artifact_digests=["sha256:" + f"{number:064x}"],
            )
        with self.assertRaisesRegex(gpr.CorrectionDecisionRequired, "ceiling"):
            self.runtime.begin_attempt("run-main", "segment-a")
        transitions = [
            record for record in self.runtime.load_records("run-main")
            if record["record_type"] == "transition"
        ]
        self.assertEqual(transitions, [])

    def test_no_progress_rejects_revise_and_allows_replan(self):
        self.create()
        result, _ = self.result_and_evidence("run-main")
        ref = evidence_ref(result, "FAIL")
        digest = result["artifact"]["identity"]["digest"]
        self.runtime.begin_attempt("run-main", "segment-a")
        first = self.runtime.complete_attempt(
            "run-main", "segment-a", defect_codes=["wrong-output"],
            evidence_refs=[ref], artifact_digests=[digest],
        )
        self.runtime.begin_attempt("run-main", "segment-a")
        second = self.runtime.complete_attempt(
            "run-main", "segment-a", defect_codes=["wrong-output"],
            evidence_refs=[ref], artifact_digests=[digest],
        )
        self.assertTrue(first["progress_evidence"])
        self.assertFalse(second["progress_evidence"])
        with self.assertRaisesRegex(gpr.CorrectionDecisionRequired, "no new progress"):
            self.runtime.apply_transition(
                "run-main", "REVISE", target_node_id="act", reason="try again",
                evaluation_boundary="independent_quality_review", evidence_refs=[ref],
            )
        transition = self.runtime.apply_transition(
            "run-main", "REPLAN", target_node_id="verify", reason="plan is inadequate",
            evaluation_boundary="independent_quality_review", evidence_refs=[ref],
        )
        self.assertEqual(transition["transition"]["to_state"], "pending")

    def test_repeated_defect_rule_stops_revision_even_with_new_artifacts(self):
        self.create()
        result, _ = self.result_and_evidence("run-main")
        ref = evidence_ref(result, "FAIL")
        for number in range(3):
            self.runtime.begin_attempt("run-main", "segment-a")
            completed = self.runtime.complete_attempt(
                "run-main", "segment-a", defect_codes=["same-defect"],
                evidence_refs=[ref], artifact_digests=["sha256:" + str(number + 1) * 64],
            )
        self.assertEqual(completed["repeated_defect_count"], 3)
        self.assertTrue(completed["progress_evidence"])
        with self.assertRaisesRegex(gpr.CorrectionDecisionRequired, "repeated defect"):
            self.runtime.apply_transition(
                "run-main", "REVISE", target_node_id="act", reason="same correction",
                evaluation_boundary="independent_quality_review", evidence_refs=[ref],
            )

    def test_infrastructure_retry_never_creates_a_quality_directive(self):
        self.create()
        retry = self.runtime.record_infrastructure_attempt(
            "run-main", "model-call", attempt=1, max_retries=1,
            outcome="retryable_failure", reason="temporary timeout",
        )
        exhausted = self.runtime.record_infrastructure_attempt(
            "run-main", "model-call", attempt=2, max_retries=1,
            outcome="retryable_failure", reason="temporary timeout",
        )
        self.assertTrue(retry["can_retry"])
        self.assertFalse(retry["requires_transition_evaluation"])
        self.assertFalse(exhausted["can_retry"])
        self.assertTrue(exhausted["requires_transition_evaluation"])
        self.assertIsNone(retry["directive"])
        self.assertIsNone(exhausted["directive"])
        self.assertEqual(
            [r for r in self.runtime.load_records("run-main") if r["record_type"] == "transition"],
            [],
        )
        with self.assertRaisesRegex(gpr.RunConflictError, "terminal outcome"):
            self.runtime.record_infrastructure_attempt(
                "run-main", "model-call", attempt=3, max_retries=1,
                outcome="success", reason="late replay",
            )


class TestTransitionRouting(RuntimeCase):
    TARGETS = {
        "PROCEED": "act",
        "ACCEPT": "accepted",
        "REVISE": "act",
        "REPLAN": "verify",
        "REDEFINE": "verify",
        "ESCALATE": "verify",
        "BLOCKED": "blocked",
    }

    def test_all_seven_directives_follow_state_graph_and_judgment_contracts(self):
        for directive in pc.TRANSITION_DIRECTIVES:
            with self.subTest(directive=directive):
                runtime_dir = tempfile.TemporaryDirectory()
                self.addCleanup(runtime_dir.cleanup)
                runtime = gpr.GovernedProcessRuntime(runtime_dir.name, now=lambda: NOW)
                definition = make_definition()
                run_id = f"run-{directive.lower()}"
                runtime.create_run(definition, make_run(run_id, definition))
                runtime.start_run(run_id, reason="approved test plan is ready")
                result = runtime.record_inline_artifact(
                    run_id, "result", "candidate", role="result", node_id="act",
                    action="produce_artifact", selector=OUTPUT,
                    satisfied_conditions=CONDITION,
                )
                evidence = runtime.record_inline_artifact(
                    run_id, "evidence", "proof", role="evidence", node_id="verify",
                    action="record_evidence", selector=OUTPUT,
                    source_artifact_ids=["result"], satisfied_conditions=CONDITION,
                )
                if directive == "ACCEPT":
                    runtime.record_final_review(
                        run_id, artifact_id="result", evidence_id="result_verified",
                        evidence_artifact_id="evidence", outcome="PASS",
                        reviewer_id="independent", independent=True,
                        satisfied_conditions=CONDITION,
                    )
                request = None
                if directive == "ESCALATE":
                    request = {
                        "request_id": "authority-001",
                        "request_type": "scope_expansion",
                        "requested_authority": ["expand_scope"],
                        "options": ["approve", "deny"],
                        "resume_node_id": "verify",
                        "requested_from": "principal-001",
                    }
                transition = runtime.apply_transition(
                    run_id,
                    directive,
                    target_node_id=self.TARGETS[directive],
                    reason="bounded Process Coherence conclusion",
                    evaluation_boundary="independent_quality_review",
                    authority_request=request,
                    evidence_refs=[evidence_ref(result, "PASS" if directive == "ACCEPT" else "FAIL")],
                )
                self.assertEqual(
                    transition["transition"]["to_state"],
                    pc.DIRECTIVE_TARGET_STATES[directive],
                )

    def test_failure_class_dispatch_is_fixed_and_unknown_classes_are_refused(self):
        self.assertEqual(
            {name: gpr.directive_for_failure_class(name) for name in gpr.FAILURE_CLASS_DIRECTIVES},
            gpr.FAILURE_CLASS_DIRECTIVES,
        )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "failure_class"):
            gpr.directive_for_failure_class("programming")

    def test_transition_rejects_wrong_route_missing_or_stale_evidence_and_terminal_restart(self):
        self.create()
        result, evidence = self.result_and_evidence("run-main")
        ref = evidence_ref(result, "FAIL")
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "missing required evidence"):
            self.runtime.apply_transition(
                "run-main", "REVISE", target_node_id="act", reason="missing proof",
                evaluation_boundary="independent_quality_review",
            )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "declared graph route"):
            self.runtime.apply_transition(
                "run-main", "REVISE", target_node_id="verify", reason="wrong route",
                evaluation_boundary="independent_quality_review", evidence_refs=[ref],
            )
        stale = copy.deepcopy(ref)
        stale["identity_digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "identity is stale"):
            self.runtime.apply_transition(
                "run-main", "REVISE", target_node_id="act", reason="stale proof",
                evaluation_boundary="independent_quality_review", evidence_refs=[stale],
            )
        self.pass_review("run-main", result, evidence)
        self.runtime.apply_transition(
            "run-main", "ACCEPT", target_node_id="accepted", reason="accepted",
            evaluation_boundary="independent_quality_review",
            evidence_refs=[evidence_ref(result)],
        )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "not valid"):
            self.runtime.apply_transition(
                "run-main", "PROCEED", target_node_id="act", reason="restart",
                evaluation_boundary="independent_quality_review",
                evidence_refs=[evidence_ref(result)],
            )


class TestAuthorityLineageAndReview(RuntimeCase):
    def test_runtime_enforces_conditions_scope_effects_and_reserved_actions(self):
        self.create()
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "not authorized"):
            self.runtime.authorize_action(
                "run-main", "mutate", [OUTPUT], effect_type="local_reversible",
                scope_kind="write",
            )
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "outside"):
            self.runtime.authorize_action(
                "run-main", "mutate", ["scope:not-approved"],
                satisfied_conditions=CONDITION, effect_type="local_reversible",
                scope_kind="write",
            )
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "reserved"):
            self.runtime.authorize_action(
                "run-main", "activate", [OUTPUT], satisfied_conditions=CONDITION,
                effect_type="local_reversible", scope_kind="write",
            )
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "not authorized"):
            self.runtime.authorize_action(
                "run-main", "mutate", [OUTPUT], satisfied_conditions=CONDITION,
                effect_type="undeclared_effect", scope_kind="write",
            )

    def test_expired_authority_and_principal_self_review_are_rejected(self):
        definition = make_definition()
        run = make_run("run-expired", definition)
        run["contracts"]["authority"]["expires_at"] = "2026-07-16T17:00:00-07:00"
        self.runtime.create_run(definition, run)
        self.runtime.start_run("run-expired", reason="approved test plan is ready")
        with self.assertRaisesRegex(gpr.AuthorityDeniedError, "expired"):
            self.runtime.authorize_action(
                "run-expired", "mutate", [OUTPUT], satisfied_conditions=CONDITION,
                effect_type="local_reversible", scope_kind="write",
            )

        self.create("run-review")
        result, evidence = self.result_and_evidence("run-review")
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "differ"):
            self.runtime.record_final_review(
                "run-review", artifact_id=result["artifact"]["artifact_id"],
                evidence_id="result_verified",
                evidence_artifact_id=evidence["artifact"]["artifact_id"],
                outcome="PASS", reviewer_id="principal-001", independent=True,
                satisfied_conditions=CONDITION,
            )

    def test_accept_requires_independent_current_reinspection_after_correction(self):
        self.create()
        result, evidence = self.result_and_evidence("run-main")
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "review missing"):
            self.runtime.apply_transition(
                "run-main", "ACCEPT", target_node_id="accepted", reason="premature",
                evaluation_boundary="independent_quality_review",
                evidence_refs=[evidence_ref(result)],
            )
        self.runtime.record_final_review(
            "run-main", artifact_id="result", evidence_id="result_verified",
            evidence_artifact_id="evidence", outcome="FAIL", reviewer_id="independent",
            independent=True, satisfied_conditions=CONDITION,
        )
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "did not pass"):
            self.runtime.apply_transition(
                "run-main", "ACCEPT", target_node_id="accepted", reason="failed review",
                evaluation_boundary="independent_quality_review",
                evidence_refs=[evidence_ref(result, "FAIL")],
            )
        corrected, _ = self.result_and_evidence(
            "run-main", result_text="corrected result", result_id="result",
            evidence_id="correction-evidence",
        )
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "stale"):
            self.runtime.apply_transition(
                "run-main", "ACCEPT", target_node_id="accepted", reason="unreviewed correction",
                evaluation_boundary="independent_quality_review",
                evidence_refs=[evidence_ref(corrected)],
            )
        new_evidence = self.runtime.load_artifact("run-main", "correction-evidence")
        self.runtime.record_final_review(
            "run-main", artifact_id="result", evidence_id="result_verified",
            evidence_artifact_id="correction-evidence", outcome="PASS",
            reviewer_id="independent-reviewer-2", independent=True,
            satisfied_conditions=CONDITION,
        )
        accepted = self.runtime.apply_transition(
            "run-main", "ACCEPT", target_node_id="accepted", reason="reinspection passed",
            evaluation_boundary="independent_quality_review",
            evidence_refs=[evidence_ref(corrected)],
        )
        self.assertEqual(accepted["transition"]["to_state"], "completed")
        self.assertEqual(new_evidence["lineage"]["source_artifact_ids"], ["result"])

    def test_final_review_requires_exact_subject_lineage_and_digest(self):
        self.create()
        result = self.runtime.record_inline_artifact(
            "run-main", "result", "candidate-v1", role="result", node_id="act",
            action="produce_artifact", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        unrelated = self.runtime.record_inline_artifact(
            "run-main", "unrelated-evidence", "looks persuasive", role="evidence",
            node_id="verify", action="record_evidence", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "no lineage"):
            self.runtime.record_final_review(
                "run-main", artifact_id="result", evidence_id="result_verified",
                evidence_artifact_id="unrelated-evidence", outcome="PASS",
                reviewer_id="independent", independent=True,
                satisfied_conditions=CONDITION,
            )

        evidence = self.runtime.record_inline_artifact(
            "run-main", "evidence", "proof of v1", role="evidence", node_id="verify",
            action="record_evidence", selector=OUTPUT,
            source_artifact_ids=["result"], satisfied_conditions=CONDITION,
        )
        self.runtime.record_inline_artifact(
            "run-main", "result", "candidate-v2", role="result", node_id="act",
            action="produce_artifact", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "current result identity"):
            self.runtime.record_final_review(
                "run-main", artifact_id="result", evidence_id="result_verified",
                evidence_artifact_id=evidence["artifact"]["artifact_id"], outcome="PASS",
                reviewer_id="independent", independent=True,
                satisfied_conditions=CONDITION,
            )
        self.assertEqual(result["artifact"]["artifact_id"], "result")

    def test_accept_ref_must_match_the_current_persisted_pass_review(self):
        self.create()
        result, evidence = self.result_and_evidence("run-main")
        self.pass_review("run-main", result, evidence)
        contradictory = evidence_ref(result, "FAIL")
        with self.assertRaisesRegex(gpr.FinalReviewRequired, "must report PASS"):
            self.runtime.apply_transition(
                "run-main", "ACCEPT", target_node_id="accepted",
                reason="contradictory transition evidence",
                evaluation_boundary="independent_quality_review",
                evidence_refs=[contradictory],
            )

    def test_terminal_run_rejects_actions_attempts_events_and_artifact_mutation(self):
        self.create()
        result, evidence = self.result_and_evidence("run-main")
        self.pass_review("run-main", result, evidence)
        self.runtime.apply_transition(
            "run-main", "ACCEPT", target_node_id="accepted", reason="accepted",
            evaluation_boundary="independent_quality_review",
            evidence_refs=[evidence_ref(result)],
        )
        accepted_digest = self.runtime.load_artifact(
            "run-main", "result"
        )["identity"]["digest"]
        with self.assertRaisesRegex(gpr.RunConflictError, "terminal Process Run"):
            self.runtime.authorize_action(
                "run-main", "mutate", [OUTPUT], satisfied_conditions=CONDITION,
                effect_type="local_reversible", scope_kind="write",
            )
        with self.assertRaisesRegex(gpr.RunConflictError, "terminal Process Run"):
            self.runtime.begin_attempt("run-main", "late-attempt")
        with self.assertRaisesRegex(gpr.RunConflictError, "terminal Process Run"):
            self.runtime.record_event("run-main", "late_event", {})
        with self.assertRaisesRegex(gpr.RunConflictError, "terminal Process Run"):
            self.runtime.record_inline_artifact(
                "run-main", "result", "replacement", role="result", node_id="act",
                action="produce_artifact", selector=OUTPUT,
                satisfied_conditions=CONDITION,
            )
        self.assertEqual(
            self.runtime.load_artifact("run-main", "result")["identity"]["digest"],
            accepted_digest,
        )

    def test_artifact_drift_from_committed_lineage_is_rejected(self):
        self.create()
        result, _ = self.result_and_evidence("run-main")
        path = self.runtime._artifact_path("run-main", result["artifact"]["artifact_id"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["identity"]["digest"] = "sha256:" + "e" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "latest committed record"):
            self.runtime.load_artifact("run-main", "result")


class TestRecoveryAndInvocation(RuntimeCase):
    def test_unreceipted_external_effect_blocks_recovery(self):
        self.create()
        self.runtime.create_checkpoint(
            "run-main", "before-effect", segment_id="segment-a", resume_node_id="verify"
        )
        self.runtime.record_action(
            "run-main", action="external_write", selectors=[EXTERNAL],
            satisfied_conditions=CONDITION, effect_type="external_irreversible",
            external_effect=True,
        )
        decision = self.runtime.recovery_decision("run-main")
        self.assertFalse(decision["safe_to_resume"])
        self.assertFalse(decision["replay_mutations"])
        with self.assertRaisesRegex(gpr.RecoveryBlockedError, "lacks a receipt"):
            self.runtime.resume_run("run-main")
        with self.assertRaisesRegex(gpr.RecoveryBlockedError, "without its receipt"):
            self.runtime.create_checkpoint(
                "run-main", "after-effect", segment_id="segment-a", resume_node_id="verify"
            )

    def test_receipted_effect_pauses_and_resumes_without_replay(self):
        self.create()
        receipt = self.runtime.record_inline_artifact(
            "run-main", "receipt", "external operation receipt",
            role="external_effect_receipt", node_id="act", action="produce_artifact",
            selector=OUTPUT, satisfied_conditions=CONDITION,
        )
        self.runtime.record_action(
            "run-main", action="external_write", selectors=[EXTERNAL],
            satisfied_conditions=CONDITION, effect_type="external_irreversible",
            external_effect=True, receipt_artifact_id=receipt["artifact"]["artifact_id"],
        )
        self.runtime.pause_run(
            "run-main", "after-effect", segment_id="segment-a",
            resume_node_id="verify", reason="restart test",
        )
        resumed = self.runtime.resume_run("run-main")
        actions = [
            record for record in self.runtime.load_records("run-main")
            if (record.get("event") or {}).get("event_type") == "action_completed"
        ]
        self.assertEqual(len(actions), 1)
        self.assertFalse(resumed["decision"]["replay_mutations"])

    def test_changed_receipt_identity_blocks_restart(self):
        self.create()
        receipt = self.runtime.record_inline_artifact(
            "run-main", "receipt", "receipt-v1", role="external_effect_receipt",
            node_id="act", action="produce_artifact", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        self.runtime.record_action(
            "run-main", action="external_write", selectors=[EXTERNAL],
            satisfied_conditions=CONDITION, effect_type="external_irreversible",
            external_effect=True, receipt_artifact_id=receipt["artifact"]["artifact_id"],
        )
        self.runtime.pause_run(
            "run-main", "receipt-checkpoint", segment_id="segment-a",
            resume_node_id="verify", reason="restart test",
        )
        self.runtime.record_inline_artifact(
            "run-main", "receipt", "receipt-v2", role="external_effect_receipt",
            node_id="act", action="produce_artifact", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        decision = self.runtime.recovery_decision("run-main")
        self.assertFalse(decision["safe_to_resume"])
        self.assertIn("receipt identity changed", decision["reason"])

    def test_post_checkpoint_receipt_is_checked_against_effect_digest(self):
        self.create()
        self.runtime.create_checkpoint(
            "run-main", "before-effect", segment_id="segment-a",
            resume_node_id="verify",
        )
        receipt = self.runtime.record_inline_artifact(
            "run-main", "late-receipt", "receipt-v1", role="external_effect_receipt",
            node_id="act", action="produce_artifact", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        self.runtime.record_action(
            "run-main", action="external_write", selectors=[EXTERNAL],
            satisfied_conditions=CONDITION, effect_type="external_irreversible",
            external_effect=True,
            receipt_artifact_id=receipt["artifact"]["artifact_id"],
        )
        self.runtime.record_inline_artifact(
            "run-main", "late-receipt", "receipt-v2", role="external_effect_receipt",
            node_id="act", action="produce_artifact", selector=OUTPUT,
            satisfied_conditions=CONDITION,
        )
        decision = self.runtime.recovery_decision("run-main")
        self.assertFalse(decision["safe_to_resume"])
        self.assertFalse(decision["replay_mutations"])
        self.assertIn("post-checkpoint", decision["reason"])
        self.assertEqual(decision["changed_artifact_ids"], ["late-receipt"])

    def test_child_invocation_returns_to_declared_node_once(self):
        child_definition = make_definition("generic/child")
        child_selector = "definition:generic/child@1.0.0"
        parent_definition = fixtures.process_definition("generic/parent", "Generic parent")
        parent_definition["graph"] = {
            "schema_version": pc.GRAPH_SCHEMA_VERSION,
            "graph_id": "governed/parent-call",
            "entry_node_id": "call",
            "nodes": [
                {
                    "node_id": "call",
                    "kind": "process_call",
                    "label": "Invoke governed child",
                    "definition_ref": {
                        "definition_id": child_definition["definition_id"],
                        "version": child_definition["version"],
                        "digest": child_definition["digest"],
                    },
                    "input_bindings": {},
                    "return_node_id": "return",
                    "on_error_node_id": "blocked",
                },
                {
                    "node_id": "return",
                    "kind": "process_return",
                    "label": "Receive governed child",
                    "output_bindings": {"result": "child.result"},
                    "next_node_id": "accepted",
                },
                {
                    "node_id": "accepted",
                    "kind": "terminal_state",
                    "label": "Accepted",
                    "outcome": "accepted",
                },
                {
                    "node_id": "blocked",
                    "kind": "terminal_state",
                    "label": "Blocked",
                    "outcome": "blocked",
                },
            ],
        }
        parent_run = make_run(
            "run-parent", parent_definition, current_node_id="call",
            child_selector=child_selector,
        )
        parent_run["contracts"]["approved_plan"]["approved_node_ids"] = [
            node["node_id"] for node in parent_definition["graph"]["nodes"]
        ]
        parent_run["contracts"]["continuation"]["resume_node_id"] = "call"
        parent_run["contracts"]["bounded_judgment"][0]["node_id"] = "return"
        parent_run["contracts"]["bounded_judgment"][0]["return_node_id"] = "return"
        self.runtime.create_run(parent_definition, parent_run)
        self.runtime.start_run("run-parent", reason="approved parent plan is ready")

        child_run = make_run("run-child", child_definition)
        invoked = self.runtime.invoke_child(
            "run-parent", child_definition, child_run, call_node_id="call",
            satisfied_conditions=CONDITION,
        )
        self.runtime.start_run("run-child", reason="approved child plan is ready")
        self.assertEqual(invoked["child_run"]["relationships"]["parent_run_id"], "run-parent")
        self.assertEqual(
            invoked["child_run"]["contracts"]["continuation"]["parent_run_id"],
            "run-parent",
        )
        result = self.runtime.record_inline_artifact(
            "run-child", "child-result", "child output", role="result", node_id="act",
            action="produce_artifact", selector=OUTPUT, satisfied_conditions=CONDITION,
        )
        evidence = self.runtime.record_inline_artifact(
            "run-child", "child-evidence", "child proof", role="evidence", node_id="verify",
            action="record_evidence", selector=OUTPUT, source_artifact_ids=["child-result"],
            satisfied_conditions=CONDITION,
        )
        self.runtime.record_final_review(
            "run-child", artifact_id="child-result", evidence_id="result_verified",
            evidence_artifact_id="child-evidence", outcome="PASS",
            reviewer_id="independent-child-reviewer", independent=True,
            satisfied_conditions=CONDITION,
        )
        self.runtime.apply_transition(
            "run-child", "ACCEPT", target_node_id="accepted", reason="child accepted",
            evaluation_boundary="independent_quality_review",
            evidence_refs=[evidence_ref(result)],
        )
        with self.assertRaisesRegex(gpr.RunConflictError, "terminal Process Run"):
            self.runtime.record_inline_artifact(
                "run-child", "child-result", "replacement child output", role="result",
                node_id="act", action="produce_artifact", selector=OUTPUT,
                satisfied_conditions=CONDITION,
            )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "at least one"):
            self.runtime.return_child("run-child", output_artifact_ids=[])
        returned = self.runtime.return_child(
            "run-child", output_artifact_ids=["child-result"]
        )
        parent = self.runtime.load_run("run-parent")
        self.assertEqual(parent["current_node_id"], "return")
        self.assertEqual(parent["state"], "running")
        self.assertNotIn("child-result", parent["artifact_ids"])
        self.assertEqual(
            returned["parent_record"]["event"]["details"]["output_artifact_ids"],
            ["child-result"],
        )
        binding = returned["parent_record"]["event"]["details"]["output_bindings"][0]
        self.assertEqual(binding["artifact_id"], "child-result")
        self.assertEqual(binding["producing_run_id"], "run-child")
        self.assertEqual(binding["definition_ref"], child_run["definition_ref"])
        self.assertEqual(
            binding["identity_digest"], result["artifact"]["identity"]["digest"]
        )
        self.assertEqual(
            [item["evidence_id"] for item in binding["acceptance_evidence"]],
            ["result_verified"],
        )
        self.assertEqual(binding["acceptance_evidence"][0]["outcome"], "PASS")
        self.assertEqual(binding["acceptance_transition"]["directive"], "ACCEPT")
        self.assertEqual(
            binding["acceptance_transition"]["evidence_refs"],
            [evidence_ref(result)],
        )
        derived = self.runtime.record_inline_artifact(
            "run-parent", "parent-result", "derived parent output", role="result",
            node_id="return", action="produce_artifact", selector=OUTPUT,
            source_artifact_ids=["child-result"], satisfied_conditions=CONDITION,
        )
        self.assertEqual(
            derived["artifact"]["lineage"]["source_artifact_ids"],
            ["child-result"],
        )
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "collides"):
            self.runtime.record_inline_artifact(
                "run-parent", "child-result", "colliding local output", role="result",
                node_id="return", action="produce_artifact", selector=OUTPUT,
                satisfied_conditions=CONDITION,
            )
        with self.assertRaisesRegex(gpr.RunConflictError, "already returned"):
            self.runtime.return_child("run-child", output_artifact_ids=["child-result"])

        child_path = self.runtime._artifact_path("run-child", "child-result")
        tampered = json.loads(child_path.read_text(encoding="utf-8"))
        tampered["identity"]["digest"] = "sha256:" + "d" * 64
        child_path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(gpr.GovernedRuntimeError, "latest committed record"):
            self.runtime.record_inline_artifact(
                "run-parent", "parent-result-2", "drifted derivation", role="result",
                node_id="return", action="produce_artifact", selector=OUTPUT,
                source_artifact_ids=["child-result"], satisfied_conditions=CONDITION,
            )


if __name__ == "__main__":
    unittest.main()
