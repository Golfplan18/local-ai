"""G1.1 Phase 2.5 — authenticated generic Run Inspector proofs."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
os.environ.setdefault("ORA_HOME", str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import governed_process_runtime as runtime  # noqa: E402
import process_plan_approval as planning  # noqa: E402
import process_run_inspector as inspector  # noqa: E402
from server import server  # noqa: E402
from tests import test_governed_process_runtime as runtime_fixtures  # noqa: E402
from tests import test_phase_1_7_kernel_trials as phase17  # noqa: E402
from tests import test_phase_2_4_delegation_attention as phase24  # noqa: E402


NOW = phase24.NOW


class Phase25Fixture(phase24.Phase24Fixture):
    def setUp(self):
        super().setUp()
        self.inspector = inspector.ProcessRunInspectorService(
            runtime=self.runtime,
            plan_service=self.service,
            attention_service=self.delegation,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            now=lambda: NOW,
        )

    def restarted_inspector(self):
        restarted_attention = self.restarted()
        return inspector.ProcessRunInspectorService(
            runtime=restarted_attention.runtime,
            plan_service=restarted_attention.plan_service,
            attention_service=restarted_attention,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            now=lambda: NOW,
        )

    @staticmethod
    def _grant_conditions(run, action):
        return next(
            grant["conditions"]
            for grant in run["contracts"]["authority"]["grants"]
            if action in grant["actions"]
        )

    def _enter_external_execute_step(self, state):
        self.delegate(state)
        run_id = state["run_id"]
        run = self.runtime.load_run(run_id)
        conditions = self._grant_conditions(run, "programming_preflight")
        preflight = self.runtime.record_inline_artifact(
            run_id, "preflight-evidence",
            "exact approved baseline and authority are current",
            role="evidence", node_id="execute-preflight",
            action="programming_preflight", selector="scope:declared_outputs",
            satisfied_conditions=conditions,
        )
        self.runtime.complete_action_node(
            run_id, "programming_preflight", reason="preflight is current",
            artifact_ids=[preflight["artifact"]["artifact_id"]],
        )
        pre_state = self.delegation.capture_repository_state(
            "dialogue-plan", artifact_id="repository-pre-state",
            phase="pre_action",
        )
        self.runtime.create_checkpoint(
            run_id, "before-approved-report-mutation",
            segment_id="approved-report-mutation", resume_node_id="execute-step",
        )
        return pre_state

    def _post_state_and_receipt(self, state, pre_state):
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        self.runtime.authorize_action(
            state["run_id"], "execute_approved_programming_step",
            ["artifact:report.py"], satisfied_conditions=conditions,
            effect_type="local_reversible", scope_kind="external",
        )
        report = self.target / "report.py"
        report.write_text(
            report.read_text(encoding="utf-8") + "# approved mutation\n",
            encoding="utf-8",
        )
        post_state = self.delegation.capture_repository_state(
            "dialogue-plan", artifact_id="repository-post-state",
            phase="post_action",
        )
        receipt = self.delegation.issue_repository_mutation_receipt(
            "dialogue-plan", artifact_id="repository-mutation-receipt",
            pre_state_artifact_id=pre_state["artifact"]["artifact_id"],
            post_state_artifact_id=post_state["artifact"]["artifact_id"],
        )
        return post_state, receipt

    @staticmethod
    def _mutation_details(pre_state, post_state):
        return {
            "operation": "execute_approved_programming_step",
            "pre_state_identity": {
                "artifact_id": pre_state["artifact"]["artifact_id"],
                "identity_digest": pre_state["artifact"]["identity"]["digest"],
            },
            "post_state_identity": {
                "artifact_id": post_state["artifact"]["artifact_id"],
                "identity_digest": post_state["artifact"]["identity"]["digest"],
            },
        }

    def completed_effect(self, state):
        pre_state = self._enter_external_execute_step(state)
        post_state, receipt = self._post_state_and_receipt(state, pre_state)
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        action = self.runtime.record_action(
            state["run_id"],
            action="execute_approved_programming_step",
            selectors=["artifact:report.py"],
            satisfied_conditions=conditions,
            effect_type="local_reversible",
            external_effect=True,
            receipt_artifact_id=receipt["artifact"]["artifact_id"],
            details=self._mutation_details(pre_state, post_state),
        )
        self.runtime.complete_action_node(
            state["run_id"],
            "execute_approved_programming_step",
            reason="approved target mutation completed",
            artifact_ids=[receipt["artifact"]["artifact_id"]],
        )
        return pre_state, post_state, receipt, action

    def record_repository_artifact(
        self,
        run_id,
        target,
        artifact_id,
        *,
        role,
        action,
        selector,
        conditions,
    ):
        capture = planning.capture_target_identity(
            str(target.resolve()), captured_at=NOW
        )
        run = self.runtime.load_run(run_id)
        artifact = {
            "schema_version": phase17.pc.CONTRACT_SCHEMA_VERSION,
            "object_family": "artifact",
            "artifact_id": artifact_id,
            "role": role,
            "status": "candidate",
            "media_type": "application/vnd.ora.repository-state+json",
            "locator": copy.deepcopy(capture["locator"]),
            "identity": {
                **copy.deepcopy(capture["identity"]),
                "fresh_until": "2027-07-18T12:00:00Z",
            },
            "lineage": {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "producing_node_id": run["current_node_id"],
                "source_artifact_ids": [],
                "event_record_id": (
                    f"event-{run_id}-{artifact_id}-"
                    f"{capture['identity']['digest'][7:19]}"
                ),
            },
            "created_at": NOW,
        }
        return self.runtime.record_artifact(
            artifact,
            action=action,
            selectors=[selector],
            satisfied_conditions=conditions,
        )


class Phase25RunInspectorTests(Phase25Fixture):
    def test_decisions_include_authenticated_human_and_graph_routes(self):
        state = self.approved()
        self.delegate(state)

        decisions = self.inspector.inspect(state["run_id"])["views"]["decisions"]
        governed = decisions["governed_decisions"]
        human = next(
            item for item in governed
            if item["source_node_id"] == "plan-approval"
        )
        route = next(
            item for item in governed
            if item["source_node_id"] == "post-plan-mode"
        )

        self.assertEqual(human["decision_kind"], "human_checkpoint")
        self.assertEqual(human["outcome"], "approved")
        self.assertEqual(human["decision_by"], "principal:user")
        self.assertEqual(human["authority_request_type"], "plan_approval")
        self.assertEqual(human["target_node_id"], "post-plan-mode")
        self.assertEqual(route["decision_kind"], "decision_node")
        self.assertEqual(route["condition"], "prg_run")
        self.assertTrue(route["matched"])
        self.assertFalse(route["default_used"])
        self.assertEqual(route["target_node_id"], "execute-preflight")
        self.assertTrue({human["record_id"], route["record_id"]}.issubset({
            record["record_id"] for record in decisions["decision_events"]
        }))

    def test_decision_projection_rejects_a_route_that_disagrees_with_the_graph(self):
        state = self.approved()
        records = self.runtime.load_records(state["run_id"])
        definition = self.runtime.load_definition(state["run_id"])
        forged = copy.deepcopy(records)
        checkpoint = next(
            record for record in forged
            if (record.get("event") or {}).get("event_type") == "node_advanced"
            and record["node_id"] == "plan-approval"
        )
        checkpoint["event"]["details"]["route"]["outcome"] = "denied"

        with self.assertRaisesRegex(
            inspector.ProcessRunInspectorIntegrityError,
            "declared graph route",
        ):
            inspector.ProcessRunInspectorService._governed_decisions(
                self.runtime.load_run(state["run_id"]), definition, forged
            )

    def test_all_nine_views_are_exact_restart_derived_and_read_only(self):
        state = self.approved()
        self.delegate(state)
        before_run = self.runtime._run_path(state["run_id"]).read_bytes()
        before_records = self.runtime._events_path(state["run_id"]).read_bytes()

        snapshot = self.inspector.inspect(state["run_id"])

        self.assertEqual(snapshot["view_order"], list(inspector.INSPECTOR_VIEWS))
        self.assertEqual(tuple(snapshot["views"]), inspector.INSPECTOR_VIEWS)
        self.assertEqual(
            snapshot["views"]["overview"]["definition_ref"],
            state["definition_ref"],
        )
        self.assertEqual(
            snapshot["views"]["plan"]["approval"], state["approval"]
        )
        self.assertEqual(
            snapshot["views"]["overview"]["trigger"]["entrypoint"], "prg_run"
        )
        self.assertEqual(
            snapshot["snapshot_digest"],
            inspector._digest_json({
                key: value for key, value in snapshot.items()
                if key != "snapshot_digest"
            }),
        )
        self.assertEqual(self.runtime._run_path(state["run_id"]).read_bytes(), before_run)
        self.assertEqual(
            self.runtime._events_path(state["run_id"]).read_bytes(), before_records
        )
        self.assertEqual(self.restarted_inspector().inspect(state["run_id"]), snapshot)

    def test_capability_relationships_results_and_trigger_are_not_inferred_from_ui(self):
        definition = runtime_fixtures.make_definition("generic/inspection-proof")
        run = runtime_fixtures.make_run("run-inspection-proof", definition)
        invoked = {
            "definition_id": "generic/invoked",
            "version": "2.0",
            "digest": "sha256:" + "1" * 64,
        }
        constructed = {
            "definition_id": "generic/constructed",
            "version": "1.0",
            "digest": "sha256:" + "2" * 64,
        }
        run["relationships"]["invoked_definition_refs"] = [invoked]
        run["relationships"]["constructed_definition_refs"] = [constructed]
        run["input_bindings"]["trigger_binding"] = "manual:inquiry"
        self.runtime.create_run(definition, run)
        self.runtime.start_run("run-inspection-proof", reason="inspect exact relationships")
        result = self.runtime.record_inline_artifact(
            "run-inspection-proof", "result", "exact output", role="result",
            node_id="act", action="produce_artifact",
            selector=runtime_fixtures.OUTPUT,
            satisfied_conditions=runtime_fixtures.CONDITION,
        )

        snapshot = self.inspector.inspect("run-inspection-proof")
        overview = snapshot["views"]["overview"]
        self.assertEqual(overview["invoked_capabilities"], [invoked])
        self.assertEqual(overview["capabilities_created_or_modified"], [constructed])
        self.assertEqual(
            overview["result_artifacts"][0]["identity_digest"],
            result["artifact"]["identity"]["digest"],
        )
        self.assertEqual(
            overview["trigger"]["bindings"], {"trigger_binding": "manual:inquiry"}
        )

    def test_external_effect_exposes_exact_selector_checkpoint_receipt_and_target(self):
        state = self.approved()
        _pre, post, receipt, action = self.completed_effect(state)

        snapshot = self.inspector.inspect(state["run_id"])
        changes = snapshot["views"]["changes"]
        self.assertEqual(changes["repository"]["state"], "current")
        self.assertEqual(
            changes["repository"]["expected"]["identity_digest"],
            post["artifact"]["identity"]["digest"],
        )
        self.assertEqual(changes["external_effects"], [{
            "record_id": action["record_id"],
            "sequence": action["sequence"],
            "recorded_at": action["recorded_at"],
            "node_id": "execute-step",
            "action": "execute_approved_programming_step",
            "operation": "execute_approved_programming_step",
            "selectors": ["artifact:report.py"],
            "effect_type": "local_reversible",
            "receipt_artifact_id": receipt["artifact"]["artifact_id"],
            "receipt_identity_digest": receipt["artifact"]["identity"]["digest"],
        }])
        self.assertEqual(changes["receipts"][0]["role"], "external_effect_receipt")
        self.assertTrue(changes["state_captures"])

    def test_later_unrelated_working_artifact_cannot_replace_approved_target(self):
        state = self.approved()
        _pre, post, _receipt, _action = self.completed_effect(state)
        unrelated = self.root / "unrelated-target"
        unrelated.mkdir()
        (unrelated / "other.txt").write_text("not approved\n", encoding="utf-8")
        run = self.runtime.load_run(state["run_id"])
        self.record_repository_artifact(
            state["run_id"], unrelated, "unrelated-later-working",
            role="working",
            action="record_programming_mutation_receipt",
            selector="scope:declared_outputs",
            conditions=self._grant_conditions(
                run, "record_programming_mutation_receipt"
            ),
        )

        repository = self.inspector.inspect(state["run_id"])["views"]["changes"][
            "repository"
        ]
        self.assertEqual(repository["locator"]["ref"], str(self.target.resolve()))
        self.assertEqual(
            repository["expected"]["artifact_id"],
            post["artifact"]["artifact_id"],
        )
        self.assertEqual(
            repository["expected"]["identity_digest"],
            post["artifact"]["identity"]["digest"],
        )
        self.assertEqual(
            [item["locator"]["ref"] for item in repository["other_targets"]],
            [str(unrelated.resolve())],
        )

    def test_multiple_unapproved_repository_targets_fail_closed_explicitly(self):
        definition = runtime_fixtures.make_definition(
            "generic/multiple-repository-targets"
        )
        run_id = "run-multiple-repository-targets"
        self.runtime.create_run(
            definition, runtime_fixtures.make_run(run_id, definition)
        )
        self.runtime.start_run(run_id, reason="inspect ambiguous targets")
        targets = [self.root / "candidate-one", self.root / "candidate-two"]
        for index, target in enumerate(targets, start=1):
            target.mkdir()
            (target / "result.txt").write_text(
                f"candidate {index}\n", encoding="utf-8"
            )
            self.record_repository_artifact(
                run_id, target, f"repository-candidate-{index}",
                role="result",
                action="produce_artifact",
                selector=runtime_fixtures.OUTPUT,
                conditions=runtime_fixtures.CONDITION,
            )

        repository = self.inspector.inspect(run_id)["views"]["changes"]["repository"]
        self.assertEqual(repository["state"], "ambiguous_unbound_targets")
        self.assertIsNone(repository["locator"])
        self.assertIsNone(repository["expected"])
        self.assertFalse(repository["evidence_current"])
        self.assertEqual(
            {item["locator"]["ref"] for item in repository["candidate_targets"]},
            {str(target.resolve()) for target in targets},
        )

    def test_external_editor_change_invalidates_current_evidence_and_shows_diff(self):
        state = self.approved()
        self.completed_effect(state)
        report = self.target / "report.py"
        report.write_text(
            report.read_text(encoding="utf-8") + "# external editor drift\n",
            encoding="utf-8",
        )

        snapshot = self.inspector.inspect(state["run_id"])
        repository = snapshot["views"]["changes"]["repository"]
        self.assertEqual(repository["state"], "external_change_detected")
        self.assertFalse(repository["evidence_current"])
        self.assertGreaterEqual(
            repository["file_changes_from_approved_baseline"]["counts"]["modified"], 1
        )
        self.assertFalse(snapshot["views"]["evidence"]["acceptance_supported_now"])
        self.assertFalse(snapshot["views"]["overview"]["evidence_current"])

    def test_unavailable_target_fails_closed_without_rewriting_history(self):
        state = self.approved()
        self.delegate(state)
        moved = self.target.with_name(self.target.name + "-moved")
        self.target.rename(moved)
        snapshot = self.inspector.inspect(state["run_id"])
        repository = snapshot["views"]["changes"]["repository"]
        self.assertEqual(repository["state"], "target_unavailable")
        self.assertFalse(repository["evidence_current"])

    def test_waiting_authority_request_is_the_exact_required_human_decision(self):
        definition = runtime_fixtures.make_definition("generic/authority-inspection")
        run = runtime_fixtures.make_run("run-authority-inspection", definition)
        self.runtime.create_run(definition, run)
        self.runtime.start_run("run-authority-inspection", reason="start")
        result = self.runtime.record_inline_artifact(
            "run-authority-inspection", "result", "candidate", role="result",
            node_id="act", action="produce_artifact",
            selector=runtime_fixtures.OUTPUT,
            satisfied_conditions=runtime_fixtures.CONDITION,
        )
        request = {
            "request_id": "authority-inspector-001",
            "request_type": "scope_expansion",
            "requested_authority": ["expand_scope"],
            "options": ["approve", "deny"],
            "resume_node_id": "verify",
            "requested_from": "principal-001",
        }
        self.runtime.apply_transition(
            "run-authority-inspection", "ESCALATE", target_node_id="verify",
            reason="Exact additional authority is required.",
            evaluation_boundary="independent_quality_review",
            authority_request=request,
            evidence_refs=[runtime_fixtures.evidence_ref(result, "FAIL")],
        )
        snapshot = self.inspector.inspect("run-authority-inspection")
        self.assertEqual(
            snapshot["views"]["overview"]["required_human_decision"],
            {
                "request_id": request["request_id"],
                "request_type": request["request_type"],
                "requested_authority": request["requested_authority"],
                "options": request["options"],
                "resume_node_id": request["resume_node_id"],
            },
        )

    def test_artifact_or_record_tampering_blocks_the_inspector(self):
        state = self.approved()
        self.delegate(state)
        artifact_id = state["current_plan"]["principal_view"]["plan_ref"]["plan_id"]
        self.assertTrue(artifact_id)
        artifact_path = self.runtime._artifact_path(state["run_id"], "art-plan-v1-0")
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["identity"]["digest"] = "sha256:" + "f" * 64
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        with self.assertRaises(inspector.ProcessRunInspectorIntegrityError):
            self.inspector.inspect(state["run_id"])

    def test_api_returns_snapshot_and_404_without_mutation(self):
        state = self.approved()
        self.delegate(state)
        client = server.app.test_client()
        before = self.runtime._events_path(state["run_id"]).read_bytes()
        with mock.patch.object(
            server, "_process_run_inspector_service", return_value=self.inspector
        ):
            response = client.get(
                f"/api/process-runs/{state['run_id']}/inspector"
            )
            missing = client.get("/api/process-runs/run-missing/inspector")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(
            response.get_json()["inspector"]["view_order"],
            list(inspector.INSPECTOR_VIEWS),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self.runtime._events_path(state["run_id"]).read_bytes(), before)

    def test_phase_2_6_lifecycle_actions_are_absent(self):
        state = self.approved()
        self.delegate(state)
        snapshot = self.inspector.inspect(state["run_id"])
        encoded = json.dumps(snapshot, sort_keys=True)
        for unauthorized in ("Promote", "Preserve", "Archive", "Discard"):
            self.assertNotIn(unauthorized, encoded)


class Phase25LiveAcceptanceTests(phase17.TrialCase):
    def _repository_definition(self):
        graph = {
            "schema_version": phase17.pc.GRAPH_SCHEMA_VERSION,
            "graph_id": "phase-2.5/live-acceptance",
            "entry_node_id": "produce",
            "nodes": [
                {"node_id": "produce", "kind": "action", "label": "Produce repository",
                 "operation": "produce_repository_result", "next_node_id": "review",
                 "authority_grant_ids": ["trial-grant"],
                 "artifact_access": [phase17.OUTPUT],
                 "evidence_requirement_ids": ["result_verified"],
                 "external_effect": False},
                {"node_id": "review", "kind": "verification_boundary", "label": "Review",
                 "evidence_requirement_ids": ["result_verified"],
                 "routes": {"ACCEPT": "accepted", "BLOCKED": "blocked"}},
                {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted",
                 "outcome": "accepted"},
                {"node_id": "blocked", "kind": "terminal_state", "label": "Blocked",
                 "outcome": "blocked"},
            ],
        }
        return phase17._definition("phase-2.5/live-acceptance", graph=graph)

    def _reviewed_repository(self):
        repository = Path(self.temp.name) / "live-acceptance-repository"
        repository.mkdir()
        (repository / "result.txt").write_text("current result\n", encoding="utf-8")
        (repository / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        (repository / "tests").mkdir()
        (repository / "tests" / "test_result.py").write_text(
            "import unittest\n\n"
            "class ResultTest(unittest.TestCase):\n"
            "    def test_result(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(
            ["git", "config", "user.email", "phase25@example.test"],
            cwd=repository, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Phase 2.5"],
            cwd=repository, check=True,
        )
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-qm", "result"], cwd=repository, check=True)
        self.create("run-live-acceptance", self._repository_definition())
        result = self.repository_artifact(
            "run-live-acceptance", repository, "repository-result", role="result"
        )
        self.runtime.complete_action_node(
            "run-live-acceptance", "produce_repository_result",
            reason="repository result captured",
            artifact_ids=[result["artifact"]["artifact_id"]],
        )
        evidence, evidence_ref, _evidence_payload = self.repository_test_evidence(
            "run-live-acceptance", repository, "repository-result",
            "repository-proof",
        )
        review = self.runtime.record_final_review(
            "run-live-acceptance", artifact_id="repository-result",
            evidence_id="result_verified",
            evidence_artifact_id="repository-proof", outcome="PASS",
            reviewer_id="independent-reviewer", independent=True,
            satisfied_conditions=phase17.CONDITIONS,
        )
        self.assertEqual(evidence_ref["outcome"], "PASS")
        self.runtime.begin_attempt("run-live-acceptance", "repository-check")
        self.runtime.complete_attempt(
            "run-live-acceptance", "repository-check", defect_codes=[],
            evidence_refs=[evidence_ref],
            artifact_digests=[result["artifact"]["identity"]["digest"]],
        )
        return repository, review, Path(evidence["artifact"]["locator"]["ref"])

    def test_external_edit_after_passing_review_cannot_authorize_accept(self):
        repository, review, _evidence_path = self._reviewed_repository()
        (repository / "result.txt").write_text("externally changed\n", encoding="utf-8")
        with self.assertRaisesRegex(runtime.FinalReviewRequired, "live identity is stale"):
            self.runtime.apply_transition(
                "run-live-acceptance", "ACCEPT", target_node_id="accepted",
                reason="stale external state must not pass",
                evaluation_boundary="review-review",
                evidence_refs=review["evidence_refs"],
            )
        self.assertEqual(self.runtime.load_run("run-live-acceptance")["state"], "running")

    def test_unchanged_live_repository_remains_acceptable(self):
        _repository, review, _evidence_path = self._reviewed_repository()
        self.runtime.apply_transition(
            "run-live-acceptance", "ACCEPT", target_node_id="accepted",
            reason="current exact repository passes",
            evaluation_boundary="review-review",
            evidence_refs=review["evidence_refs"],
        )
        self.assertEqual(self.runtime.load_run("run-live-acceptance")["state"], "completed")

    def test_external_edit_to_file_backed_evidence_cannot_authorize_accept(self):
        _repository, review, evidence_path = self._reviewed_repository()
        evidence_path.write_text('{"substituted":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(
            runtime.FinalReviewRequired, "evidence live identity is stale"
        ):
            self.runtime.apply_transition(
                "run-live-acceptance", "ACCEPT", target_node_id="accepted",
                reason="substituted test evidence must not pass",
                evaluation_boundary="review-review",
                evidence_refs=review["evidence_refs"],
            )
        self.assertEqual(self.runtime.load_run("run-live-acceptance")["state"], "running")


if __name__ == "__main__":
    unittest.main()
