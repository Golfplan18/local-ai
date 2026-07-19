"""G1.1 Phase 2.8 — Part 2 outcome and experience validation."""

from __future__ import annotations

import json
import os
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
import process_definition_registry as registry_module  # noqa: E402
import process_delegation_attention as delegation  # noqa: E402
import process_entry_routing as entry  # noqa: E402
import process_run_inspector as inspector  # noqa: E402
from server import server  # noqa: E402
from tests import test_phase_1_7_kernel_trials as phase17  # noqa: E402
from tests import test_phase_2_4_delegation_attention as phase24  # noqa: E402
from tests import test_phase_2_5_run_inspector as phase25  # noqa: E402
from tests import test_phase_2_6_process_library_lifecycle as phase26  # noqa: E402


class Phase28AuthorityFixture(phase17.TrialCase):
    request = {
        "request_id": "cash-authority-experience-001",
        "request_type": "calculation_exception",
        "requested_authority": ["expand_scope"],
        "options": ["authorize tax settlement", "leave it excluded"],
        "resume_node_id": "calculate",
        "requested_from": "principal-001",
    }

    def setUp(self):
        super().setUp()
        self.registry = registry_module.ProcessDefinitionRegistry(
            Path(self.temp.name) / "registry", now=lambda: phase17.NOW
        )
        self.attention = delegation.ProcessDelegationAttentionService(
            runtime=self.runtime,
            registry=self.registry,
            sessions_root=Path(self.temp.name) / "sessions",
            repository_root=ROOT,
            now=lambda: phase17.NOW,
        )
        self.inspector = inspector.ProcessRunInspectorService(
            runtime=self.runtime,
            plan_service=self.attention.plan_service,
            attention_service=self.attention,
            sessions_root=Path(self.temp.name) / "sessions",
            repository_root=ROOT,
            now=lambda: phase17.NOW,
        )

    def escalate(self, run_id="run-phase-2-8-authority"):
        definition = phase17._cash_review_definition()
        self.create(run_id, definition)
        self.observed_action(
            run_id,
            "calculate_permitted_cash_flow",
            "reserved settlement withheld",
            {"reserved_amount": -35000, "included": False},
        )
        escalation = self.runtime.apply_transition(
            run_id,
            "ESCALATE",
            target_node_id="authority",
            reason="Tax settlement is outside inferred authority.",
            evaluation_boundary="review-review",
            authority_request=self.request,
            evidence_refs=[self.evidence_ref(run_id, "reserved-settlement")],
        )
        return run_id, escalation


class Phase28AuthorityExperienceTests(Phase28AuthorityFixture):
    def test_user_answers_one_exact_request_and_retry_cannot_consume_another(self):
        run_id, escalation = self.escalate()
        before = self.attention.projection()
        required = before["pending"][0]["attention"]["required_decision"]
        self.assertEqual(required["request_id"], self.request["request_id"])
        self.assertEqual(required["options"], self.request["options"])

        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.record_event(
                run_id,
                "authority_request_resolved",
                {"request_id": self.request["request_id"], "outcome": "approved"},
            )
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.attention.resolve_authority_request(
                run_id,
                request_id=self.request["request_id"],
                outcome="approved",
                decision_by="principal:attacker",
            )
        with self.assertRaises(runtime.RunConflictError):
            self.runtime.resolve_human_checkpoint(
                run_id,
                "approved",
                decision_by="principal-001",
                reason="bypass persisted authority request",
            )

        first = self.attention.resolve_authority_request(
            run_id,
            request_id=self.request["request_id"],
            outcome="approved",
            decision_by="principal-001",
        )
        replay = self.attention.resolve_authority_request(
            run_id,
            request_id=self.request["request_id"],
            outcome="approved",
            decision_by="principal-001",
        )
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(first["resolution_record_id"], replay["resolution_record_id"])
        self.assertEqual(first["route_record_id"], replay["route_record_id"])
        self.assertEqual(self.runtime.load_run(run_id)["current_node_id"], "calculate")
        self.assertEqual(escalation["record_id"], next(
            record["event"]["details"]["escalation_record_id"]
            for record in self.runtime.load_records(run_id)
            if (record.get("event") or {}).get("event_type")
            == "authority_request_resolved"
        ))
        with self.assertRaises(delegation.ProcessDelegationConflict):
            self.attention.resolve_authority_request(
                run_id,
                request_id=self.request["request_id"],
                outcome="denied",
                decision_by="principal-001",
            )

    def test_denial_follows_declared_blocked_route_and_remains_a_visible_decision(self):
        run_id, _escalation = self.escalate("run-phase-2-8-denied")
        first = self.attention.resolve_authority_request(
            run_id,
            request_id=self.request["request_id"],
            outcome="denied",
            decision_by="principal-001",
        )
        replay = self.attention.resolve_authority_request(
            run_id,
            request_id=self.request["request_id"],
            outcome="denied",
            decision_by="principal-001",
        )
        stopped = self.runtime.load_run(run_id)
        self.assertEqual(stopped["state"], "blocked")
        self.assertEqual(stopped["current_node_id"], "blocked")
        self.assertEqual(first["route_record_id"], replay["route_record_id"])
        self.assertTrue(replay["idempotent_replay"])
        snapshot = self.inspector.inspect(run_id)
        authority_events = [
            record for record in snapshot["views"]["decisions"]["decision_events"]
            if (record.get("event") or {}).get("event_type")
            == "authority_request_resolved"
        ]
        self.assertEqual(len(authority_events), 1)
        self.assertEqual(
            authority_events[0]["event"]["details"]["outcome"], "denied"
        )

    def test_answer_commit_recovers_before_route_without_replaying_decision(self):
        run_id, _escalation = self.escalate("run-phase-2-8-restart")
        with mock.patch.object(
            self.runtime,
            "_advance_graph_locked",
            side_effect=OSError("injected interruption after authority persistence"),
        ):
            with self.assertRaises(OSError):
                self.runtime.resolve_authority_request(
                    run_id,
                    self.request["request_id"],
                    "approved",
                    decision_by="principal-001",
                )
        records = self.runtime.load_records(run_id)
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "authority_request_resolved"
            for record in records
        ), 1)

        restarted = runtime.GovernedProcessRuntime(
            Path(self.temp.name) / "runs", now=lambda: phase17.NOW
        )
        recovered = restarted.resolve_authority_request(
            run_id,
            self.request["request_id"],
            "approved",
            decision_by="principal-001",
        )
        self.assertFalse(recovered["idempotent_replay"])
        self.assertEqual(restarted.load_run(run_id)["current_node_id"], "calculate")
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "authority_request_resolved"
            for record in restarted.load_records(run_id)
        ), 1)

    def test_authority_decision_completion_and_evidence_are_understandable(self):
        run_id, _escalation = self.escalate("run-phase-2-8-complete")
        self.attention.resolve_authority_request(
            run_id,
            request_id=self.request["request_id"],
            outcome="approved",
            decision_by="principal-001",
        )
        result = self.runtime.record_inline_artifact(
            run_id,
            "cash-result-after-authority",
            "Authorized settlement included; closing cash is 105000.",
            role="result",
            node_id="calculate",
            action="produce_artifact",
            selector=phase17.OUTPUT,
            satisfied_conditions=phase17.CONDITIONS,
        )
        self.runtime.complete_action_node(
            run_id,
            "calculate_permitted_cash_flow",
            reason="authority-bounded result produced",
            artifact_ids=[result["artifact"]["artifact_id"]],
        )
        self.accept_existing_result(run_id, result["artifact"]["artifact_id"])

        completed = self.attention.projection()["unread"][0]
        self.assertEqual(completed["visible_status"], "Completed")
        self.assertEqual(
            completed["attention"]["result_artifacts"][0]["artifact_id"],
            "cash-result-after-authority",
        )
        snapshot = self.inspector.inspect(run_id)
        authority = next(
            item for item in snapshot["views"]["decisions"]["governed_decisions"]
            if item["source_node_id"] == "authority"
        )
        self.assertEqual(authority["outcome"], "approved")
        self.assertEqual(authority["decision_by"], "principal-001")
        self.assertTrue(snapshot["views"]["overview"]["evidence_current"])
        self.assertNotIn("records", snapshot["views"]["overview"])

    def test_http_authority_boundary_accepts_only_exact_focused_decision(self):
        run_id, _escalation = self.escalate("run/phase-2-8-http")
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_delegation_service", return_value=self.attention
        ):
            malformed = client.post(
                f"/api/process-runs/{run_id}/authority",
                json={"request_id": self.request["request_id"], "outcome": "approved"},
            )
            response = client.post(
                f"/api/process-runs/{run_id}/authority",
                json={
                    "request_id": self.request["request_id"],
                    "outcome": "approved",
                    "decision_by": "principal-001",
                },
            )
            missing = client.post(
                "/api/process-runs/run-missing/authority",
                json={
                    "request_id": self.request["request_id"],
                    "outcome": "approved",
                    "decision_by": "principal-001",
                },
            )
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(missing.status_code, 404)
        payload = response.get_json()["authority_resolution"]
        self.assertEqual(payload["current_node_id"], "calculate")
        self.assertRegex(payload["response_digest"], r"^sha256:[0-9a-f]{64}$")


class Phase28NontechnicalExperienceTests(phase24.Phase24Fixture):
    def test_outcome_to_quiet_execution_never_requires_code_from_principal(self):
        self.assertEqual(self.interview_state["status"], "ready_for_plan")
        self.assertIsNone(self.interview_state["current_question"])
        proposed = self.propose()
        plan = proposed["current_plan"]
        principal_packet = json.dumps(plan["principal_view"], sort_keys=True)
        technical_packet = json.dumps(plan["technical_view"], sort_keys=True)
        self.assertNotIn(str(self.target), principal_packet)
        self.assertNotIn("worktree_entries", principal_packet)
        self.assertNotIn("captured_at", principal_packet)
        self.assertIn("report.py", principal_packet)
        self.assertIn("report.py", technical_packet)
        self.assertEqual(proposed["status"], "awaiting_approval")

        approved = self.approve(proposed)
        before = (self.target / "report.py").read_text(encoding="utf-8")
        self.delegate(approved)
        restarted = self.restarted()
        pending = restarted.projection()["pending"][0]
        self.assertTrue(pending["quiet"])
        self.assertFalse(pending["needs_attention"])
        self.assertEqual(pending["visible_status"], "Operating")
        self.assertEqual((self.target / "report.py").read_text(encoding="utf-8"), before)


class Phase28TechnicalExperienceTests(phase25.Phase25Fixture):
    def test_technical_state_is_available_without_becoming_the_default_interface(self):
        state = self.approved()
        self.completed_effect(state)
        report = self.target / "report.py"
        report.write_text(
            report.read_text(encoding="utf-8") + "# expert editor change\n",
            encoding="utf-8",
        )
        snapshot = self.inspector.inspect(state["run_id"])
        self.assertNotIn("records", snapshot["views"]["overview"])
        self.assertNotIn("diff", snapshot["views"]["overview"])
        self.assertTrue(snapshot["views"]["technical"]["records"])
        self.assertTrue(snapshot["views"]["technical"]["files"])
        self.assertEqual(
            snapshot["views"]["changes"]["repository"]["state"],
            "external_change_detected",
        )
        self.assertFalse(snapshot["views"]["overview"]["evidence_current"])


class Phase28ResultingCapabilityTests(phase26.Phase26Fixture):
    def test_completed_construction_can_be_invoked_later_by_exact_identity(self):
        target, _artifact, _result, _lifecycle = self.promote(
            "run-phase-2-8-capability"
        )
        ref = phase17._definition_ref(target)
        item = self.service.list_entries(project_ref="project:trial")["entries"][0]
        routed = entry.route_process_entry(
            {
                "source": "process_library",
                "objective": "Use the approved cash-flow review now.",
                "project_ref": "project:trial",
                "project_confirmed": False,
                "selected_definition_ref": ref,
            },
            catalog=[item],
            project_visible=lambda _project: True,
        )
        self.assertEqual(routed["status"], "ready")
        self.assertEqual(routed["definition_ref"], ref)
        self.assertEqual(routed["next_action"], "begin_exact_definition_invocation")
        self.assertFalse(item["standing_automation"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
