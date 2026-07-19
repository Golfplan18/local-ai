"""G1.1 Phase 2.8 — Part 2 outcome and experience validation."""

from __future__ import annotations

import copy
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
import boot as boot_runtime  # noqa: E402
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
        objective = "Use the approved cash-flow review now."
        request = {
            "source": "process_library",
            "objective": objective,
            "project_ref": "project:trial",
            "project_confirmed": False,
            "selected_definition_ref": ref,
        }
        response_text = "Closing cash is 105000 after the approved review."
        definition_inputs = {"repository_ref": "repo:cash-flow-trial"}
        captured = {}

        def fake_stream(clean_input, history, **kwargs):
            captured["clean_input"] = clean_input
            captured["extra_context"] = kwargs.get("extra_context")
            yield server._sse("pipeline_stage", stage="complete", gear=3)
            yield server._sse("response", text=response_text)

        class NoopThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_library_service", return_value=self.service
        ), mock.patch.object(
            server, "_process_entry_project_visible", return_value=True
        ), mock.patch.object(
            server, "_log_pending_submission", return_value="submission-invocation"
        ), mock.patch.object(
            server, "_finalize_pending_submission"
        ), mock.patch.object(
            server, "_save_conversation", return_value="chunk-invocation"
        ), mock.patch.object(
            server, "agentic_loop_stream", side_effect=fake_stream
        ) as stream, mock.patch.object(
            server.threading, "Thread", NoopThread
        ):
            response = client.post("/chat", json={
                "message": objective,
                "conversation_id": "dialogue-phase-2-8-invocation",
                "history": [],
                "process_entry_request": request,
                "process_invocation_inputs": definition_inputs,
            })
            retry = client.post("/chat", json={
                "message": objective,
                "conversation_id": "dialogue-phase-2-8-invocation",
                "history": [],
                "process_entry_request": request,
                "process_invocation_inputs": definition_inputs,
            })
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.get_data(as_text=True))
        invocation = payload["process_invocation"]
        self.assertEqual(invocation["status"], "result_recorded")
        self.assertEqual(invocation["definition_ref"], ref)
        self.assertEqual(invocation["dialogue_ref"], "dialogue-phase-2-8-invocation")
        self.assertEqual(invocation["project_ref"], "project:trial")
        self.assertEqual(invocation["definition_inputs"], definition_inputs)
        self.assertEqual(
            invocation["result"]["acceptance_status"],
            "pending_independent_review",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.get_json()["idempotent_replay"])
        self.assertEqual(
            retry.get_json()["process_invocation"]["run_id"],
            invocation["run_id"],
        )
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(captured["clean_input"], objective)
        self.assertEqual(
            captured["extra_context"]["governed_process_invocation"][
                "definition_ref"
            ],
            ref,
        )
        execution = captured["extra_context"]["governed_process_invocation"][
            "execution_contract"
        ]
        self.assertEqual(
            execution["entry_node"]["operation"],
            "calculate_permitted_cash_flow",
        )
        self.assertFalse(execution["entry_node"]["external_effect"])
        self.assertEqual(execution["definition_ref"], ref)
        self.assertEqual(execution["definition_inputs"], definition_inputs)
        prompt = boot_runtime.build_system_prompt_for_gear({
            "mode_text": (
                ROOT / "modes" / "root-cause-analysis.md"
            ).read_text(encoding="utf-8"),
            "mode_name": "root-cause-analysis",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "process_entry": captured["extra_context"]["process_entry"],
            "governed_process_invocation": captured["extra_context"][
                "governed_process_invocation"
            ],
        })
        self.assertIn("GOVERNED PROCESS INVOCATION (RUNTIME-AUTHORITATIVE)", prompt)
        self.assertIn("calculate_permitted_cash_flow", prompt)
        self.assertIn(ref["digest"], prompt)
        self.assertIn("Do not activate, publish", prompt)

        run = self.runtime.load_run(invocation["run_id"])
        self.assertEqual(run["definition_ref"], ref)
        self.assertEqual(run["input_bindings"]["dialogue_ref"], invocation["dialogue_ref"])
        self.assertEqual(run["input_bindings"]["project_ref"], "project:trial")
        self.assertEqual(
            run["input_bindings"]["definition_inputs"], definition_inputs
        )
        records = self.runtime.load_records(invocation["run_id"])
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "manual_process_invoked"
            for record in records
        ), 1)
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "manual_process_result_recorded"
            for record in records
        ), 1)
        result = self.runtime.load_artifact(
            invocation["run_id"], invocation["result"]["result_artifact_id"]
        )
        evidence = self.runtime.load_artifact(
            invocation["run_id"], invocation["result"]["evidence_artifact_id"]
        )
        self.assertEqual(result["identity"]["digest"], phase17._digest_text(response_text))
        self.assertIn(result["artifact_id"], evidence["lineage"]["source_artifact_ids"])

        restarted = phase26.library.ProcessLibraryLifecycleService(
            runtime=runtime.GovernedProcessRuntime(
                self.runtime.root, now=lambda: phase17.NOW
            ),
            registry=registry_module.ProcessDefinitionRegistry(
                self.registry_root, now=lambda: phase17.NOW
            ),
            now=lambda: phase17.NOW,
        )
        routed = entry.route_process_entry(
            request,
            catalog=restarted.list_entries(project_ref="project:trial")["entries"],
            project_visible=lambda _project: True,
        )
        recovered = restarted.begin_manual_invocation(
            dialogue_ref="dialogue-phase-2-8-invocation",
            project_ref="project:trial",
            objective=objective,
            definition_ref=ref,
            definition_inputs=definition_inputs,
            entry_contract=routed,
            request_context=server._process_invocation_request_context(
                surface="chat", history=[], attachments=[]
            ),
        )
        self.assertEqual(recovered["status"], "result_recorded")
        self.assertEqual(recovered["run_id"], invocation["run_id"])
        self.assertEqual(recovered["response_text"], response_text)

    def test_manual_invocation_reauthenticates_availability_scope_and_entry(self):
        target, _artifact, _result, _lifecycle = self.promote(
            "run-phase-2-8-invocation-guards"
        )
        ref = phase17._definition_ref(target)
        item = self.service.list_entries(project_ref="project:trial")["entries"][0]
        contract = entry.route_process_entry(
            {
                "source": "process_library",
                "objective": "Run the exact review.",
                "project_ref": "project:trial",
                "project_confirmed": False,
                "selected_definition_ref": ref,
            },
            catalog=[item],
            project_visible=lambda _project: True,
        )
        forged = copy.deepcopy(contract)
        forged["objective"] = "Substituted objective."
        before = list(self.runtime.root.iterdir())
        with self.assertRaises(phase26.library.ProcessLibraryConflict):
            self.service.begin_manual_invocation(
                dialogue_ref="dialogue-forged",
                project_ref="project:trial",
                objective="Substituted objective.",
                definition_ref=ref,
                definition_inputs={},
                entry_contract=forged,
                request_context={},
            )
        self.assertEqual(list(self.runtime.root.iterdir()), before)

        out_of_scope = copy.deepcopy(contract)
        out_of_scope["project_ref"] = "project:other"
        out_of_scope["contract_digest"] = phase26.library._digest_json({
            key: value for key, value in out_of_scope.items()
            if key != "contract_digest"
        })
        with self.assertRaises(phase26.library.ProcessLibraryConflict):
            self.service.begin_manual_invocation(
                dialogue_ref="dialogue-out-of-scope",
                project_ref="project:other",
                objective=contract["objective"],
                definition_ref=ref,
                definition_inputs={},
                entry_contract=out_of_scope,
                request_context={},
            )

        stale = copy.deepcopy(contract)
        stale["definition_ref"]["digest"] = "sha256:" + "0" * 64
        stale["contract_digest"] = phase26.library._digest_json({
            key: value for key, value in stale.items()
            if key != "contract_digest"
        })
        with self.assertRaises(phase26.library.ProcessLibraryConflict):
            self.service.begin_manual_invocation(
                dialogue_ref="dialogue-stale",
                project_ref="project:trial",
                objective=contract["objective"],
                definition_ref=stale["definition_ref"],
                definition_inputs={},
                entry_contract=stale,
                request_context={},
            )

        unavailable = phase17._definition("business/unavailable-review")
        unavailable = phase17._seal_definition(unavailable)
        self.registry.register(unavailable)
        unavailable_contract = copy.deepcopy(contract)
        unavailable_contract["definition_ref"] = phase17._definition_ref(
            unavailable
        )
        unavailable_contract["contract_digest"] = phase26.library._digest_json({
            key: value for key, value in unavailable_contract.items()
            if key != "contract_digest"
        })
        with self.assertRaises(phase26.library.ProcessLibraryConflict):
            self.service.begin_manual_invocation(
                dialogue_ref="dialogue-unavailable",
                project_ref="project:trial",
                objective=contract["objective"],
                definition_ref=unavailable_contract["definition_ref"],
                definition_inputs={},
                entry_contract=unavailable_contract,
                request_context={},
            )

        inactive = phase17._definition("business/inactive-review")
        inactive["status"] = "draft"
        inactive = phase17._seal_definition(inactive)
        inactive_contract = copy.deepcopy(contract)
        inactive_contract["definition_ref"] = phase17._definition_ref(inactive)
        inactive_contract["contract_digest"] = phase26.library._digest_json({
            key: value for key, value in inactive_contract.items()
            if key != "contract_digest"
        })
        with mock.patch.object(
            self.service,
            "list_entries",
            return_value={
                "entries": [{
                    "definition_ref": inactive_contract["definition_ref"],
                    "manual_invocation_available": True,
                }]
            },
        ), mock.patch.object(self.registry, "resolve", return_value=inactive):
            with self.assertRaises(phase26.library.ProcessLibraryConflict):
                self.service.begin_manual_invocation(
                    dialogue_ref="dialogue-inactive",
                    project_ref="project:trial",
                    objective=contract["objective"],
                    definition_ref=inactive_contract["definition_ref"],
                    definition_inputs={},
                    entry_contract=inactive_contract,
                    request_context={},
                )
        self.assertFalse(any(
            path.name.startswith("run-invocation-")
            for path in self.runtime.root.iterdir()
        ))

    def test_public_entry_rejects_invalid_definition_inputs_before_execution(self):
        target, _artifact, _result, _lifecycle = self.promote(
            "run-phase-2-8-invalid-input"
        )
        objective = "Use the approved cash-flow review now."
        request = {
            "source": "process_library",
            "objective": objective,
            "project_ref": "project:trial",
            "project_confirmed": False,
            "selected_definition_ref": phase17._definition_ref(target),
        }
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_library_service", return_value=self.service
        ), mock.patch.object(
            server, "_process_entry_project_visible", return_value=True
        ), mock.patch.object(
            server, "_log_pending_submission", return_value="invalid-input"
        ), mock.patch.object(
            server, "_delete_pending_submission"
        ), mock.patch.object(server, "agentic_loop_stream") as stream:
            response = client.post("/chat", json={
                "message": objective,
                "conversation_id": "dialogue-invalid-definition-input",
                "history": [],
                "process_entry_request": request,
                "process_invocation_inputs": {"unexpected": True},
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn("do not satisfy", response.get_json()["error"])
        stream.assert_not_called()
        self.assertFalse(any(
            path.name.startswith("run-invocation-")
            for path in self.runtime.root.iterdir()
        ))

    def test_result_requires_runtime_traversal_and_reserved_events_cannot_be_forged(self):
        target, _artifact, _result, _lifecycle = self.promote(
            "run-phase-2-8-runtime-guards"
        )
        ref = phase17._definition_ref(target)
        objective = "Use the exact review."
        request = {
            "source": "process_library",
            "objective": objective,
            "project_ref": "project:trial",
            "project_confirmed": False,
            "selected_definition_ref": ref,
        }
        contract = entry.route_process_entry(
            request,
            catalog=self.service.list_entries(project_ref="project:trial")["entries"],
            project_visible=lambda _project: True,
        )
        state = self.service.begin_manual_invocation(
            dialogue_ref="dialogue-runtime-guards",
            project_ref="project:trial",
            objective=objective,
            definition_ref=ref,
            definition_inputs={},
            entry_contract=contract,
            request_context={},
        )
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.record_event(
                state["run_id"], "manual_process_invoked", {"forged": True}
            )
        result = self.runtime.record_inline_artifact(
            state["run_id"],
            "premature-result",
            "not executed",
            role="result",
            node_id="calculate",
            action="produce_artifact",
            selector=phase17.OUTPUT,
            satisfied_conditions=["exact_manual_invocation_binding"],
        )
        evidence = self.runtime.record_inline_artifact(
            state["run_id"],
            "premature-evidence",
            "not executed",
            role="evidence",
            node_id="calculate",
            action="record_evidence",
            selector=phase17.OUTPUT,
            source_artifact_ids=[result["artifact"]["artifact_id"]],
            satisfied_conditions=["exact_manual_invocation_binding"],
        )
        with self.assertRaises(runtime.GovernedRuntimeError):
            self.runtime.record_manual_process_result(
                state["run_id"],
                invocation_record_id=state["invocation_record_id"],
                result_artifact_id=result["artifact"]["artifact_id"],
                evidence_artifact_id=evidence["artifact"]["artifact_id"],
                response_text="not executed",
            )

    def test_dialogue_save_failure_replays_authenticated_result_without_reexecution(self):
        target, _artifact, _result, _lifecycle = self.promote(
            "run-phase-2-8-save-recovery"
        )
        objective = "Use the approved cash-flow review after restart."
        request = {
            "source": "process_library",
            "objective": objective,
            "project_ref": "project:trial",
            "project_confirmed": False,
            "selected_definition_ref": phase17._definition_ref(target),
        }
        response_text = "Authenticated result survives the Dialogue-save fault."

        def fake_stream(*_args, **_kwargs):
            yield server._sse("response", text=response_text)

        class NoopThread:
            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_library_service", return_value=self.service
        ), mock.patch.object(
            server, "_process_entry_project_visible", return_value=True
        ), mock.patch.object(
            server, "_log_pending_submission", return_value="save-recovery"
        ), mock.patch.object(
            server, "_finalize_pending_submission"
        ), mock.patch.object(
            server, "_save_conversation",
            side_effect=[RuntimeError("injected save fault"), "replayed-chunk"],
        ) as save, mock.patch.object(
            server, "agentic_loop_stream", side_effect=fake_stream
        ) as stream, mock.patch.object(
            server.threading, "Thread", NoopThread
        ):
            first = client.post("/chat", json={
                "message": objective,
                "conversation_id": "dialogue-save-recovery",
                "history": [],
                "process_entry_request": request,
            })
            retry = client.post("/chat", json={
                "message": objective,
                "conversation_id": "dialogue-save-recovery",
                "history": [],
                "process_entry_request": request,
            })
        self.assertEqual(
            json.loads(first.get_data(as_text=True))["status"], "errored"
        )
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.get_json()["idempotent_replay"])
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(save.call_count, 2)

    def test_restart_finishes_captured_output_after_mid_completion_failure(self):
        target, _artifact, _result, _lifecycle = self.promote(
            "run-phase-2-8-mid-completion"
        )
        ref = phase17._definition_ref(target)
        objective = "Use the exact review with restart recovery."
        request = {
            "source": "process_library",
            "objective": objective,
            "project_ref": "project:trial",
            "project_confirmed": False,
            "selected_definition_ref": ref,
        }
        contract = entry.route_process_entry(
            request,
            catalog=self.service.list_entries(project_ref="project:trial")["entries"],
            project_visible=lambda _project: True,
        )
        context = {"surface": "chat", "delivery": "mid-completion"}
        state = self.service.begin_manual_invocation(
            dialogue_ref="dialogue-mid-completion",
            project_ref="project:trial",
            objective=objective,
            definition_ref=ref,
            definition_inputs={},
            entry_contract=contract,
            request_context=context,
        )
        response_text = "The exact output was captured before the injected fault."
        original = self.runtime.record_inline_artifact
        failed = False

        def fail_evidence_once(*args, **kwargs):
            nonlocal failed
            artifact_id = args[1] if len(args) > 1 else kwargs.get("artifact_id")
            if str(artifact_id).startswith("manual-execution-evidence-") and not failed:
                failed = True
                raise RuntimeError("injected failure after graph advancement")
            return original(*args, **kwargs)

        with mock.patch.object(
            self.runtime,
            "record_inline_artifact",
            side_effect=fail_evidence_once,
        ):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                self.service.complete_manual_invocation(
                    state["run_id"], response_text
                )
        partial = self.service._manual_invocation_state(state["run_id"])
        self.assertEqual(partial["status"], "output_captured")
        self.assertEqual(partial["response_text"], response_text)
        self.assertEqual(partial["current_node_id"], "review")

        restarted = phase26.library.ProcessLibraryLifecycleService(
            runtime=runtime.GovernedProcessRuntime(
                self.runtime.root, now=lambda: phase17.NOW
            ),
            registry=registry_module.ProcessDefinitionRegistry(
                self.registry_root, now=lambda: phase17.NOW
            ),
            now=lambda: phase17.NOW,
        )
        recovered = restarted.begin_manual_invocation(
            dialogue_ref="dialogue-mid-completion",
            project_ref="project:trial",
            objective=objective,
            definition_ref=ref,
            definition_inputs={},
            entry_contract=contract,
            request_context=context,
        )
        self.assertEqual(recovered["status"], "result_recorded")
        self.assertEqual(recovered["response_text"], response_text)
        records = restarted.runtime.load_records(recovered["run_id"])
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "manual_process_output_captured"
            for record in records
        ), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
