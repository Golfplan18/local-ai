"""G1.20 — authenticated Run telemetry, liveness, controls, and opt-in review."""

from __future__ import annotations

import copy
import json
import sys
import threading
import time
from unittest import mock

import pytest

from orchestrator import process_automation as automation
from orchestrator import process_automation_worker as worker_module
from orchestrator import process_run_inspector as inspector
from orchestrator.tests.test_g1_18_process_automation import (
    ROOT,
    VAULT_ORA,
    ProcessAutomationFixture,
    _body,
)
from server import server


class TestG120ProcessRunTelemetry(ProcessAutomationFixture):
    def _accepted_ref(self):
        return self.author()["proposal"]["definition_ref"]

    def _handoff(self):
        begun = self.begin(self._accepted_ref())
        state = self.service.execute(begun["run_id"])
        assert state["status"] == "awaiting_human_checkpoint"
        return state

    def _inspector(self):
        return inspector.ProcessRunInspectorService(
            runtime=self.runtime,
            sessions_root=self.root / "sessions",
            repository_root=self.root,
        )

    def test_layer_one_is_always_on_and_uses_authenticated_run_records(self):
        state = self._handoff()
        snapshot = self._inspector().inspect(state["run_id"])
        telemetry = snapshot["views"]["current_state"]["telemetry"]

        assert telemetry["layer"] == "deterministic"
        assert telemetry["run_state"] == "pending"
        assert telemetry["current_node_id"] == "draft-approval"
        assert telemetry["elapsed_seconds"] >= 0
        assert "estimated_remaining_seconds" in telemetry
        assert telemetry["attempts"]["total"] == 2
        assert telemetry["attempts"]["retries"] == 0
        assert telemetry["usage"] == {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "measured": False,
            "status": "unavailable",
            "source": "no_authenticated_usage_receipt",
            "reason": (
                "No runtime-authenticated token/cost receipt is bound to this Run; "
                "worker tool isolation does not establish model usage."
            ),
        }
        assert telemetry["artifacts"]["by_role"]["working"] == 2
        assert telemetry["liveness"]["status"] == "idle"
        assert telemetry["health"]["status"] == "healthy"
        assert telemetry["controls"]["available_actions"] == ["stop"]
        assert telemetry["quality_evaluation"]["eligibility"]["reason"] == "human_handoff"
        assert snapshot["views"]["overview"]["telemetry"]["attempts"]["total"] == 2

    def test_canonical_guidance_and_gate_records_match_the_shipped_boundaries(self):
        technical = _body(VAULT_ORA / "Reference — Ora Technical Documentation.md")
        guide = _body(VAULT_ORA / "Guide — Using Ora.md")
        assert technical == _body(ROOT / "docs" / "technical-documentation.md")
        assert guide == _body(ROOT / "docs" / "user-guide.md")
        for token in (
            "## 20. G1.20 Process Run Telemetry, Liveness, and Controls",
            "Layer 1 is always assembled",
            "A retry returns the same control identity",
            "legacy execute/retry path and direct runtime resume fail closed",
            "forged, stale, or losing racing Pause",
            "runtime-authenticated usage receipt exists",
            "Caller-supplied source, subject, node, or model substitutions",
            "produces an authority-inert `INDETERMINATE` result without invoking the evaluator",
            "Model-based drift/quality/trace evaluation is never automatic on every step",
            "Every projection labels the result `authority_effect: none`",
            "G1.20 adds no Trigger record, schedule, standing activation, Persona/MindSpec binding",
        ):
            assert token in technical
        for token in (
            "### Watch Run telemetry",
            "**Pause run** stops the exact live isolated worker",
            "A stale or rejected Pause leaves the existing checkpoint and Run untouched",
            "Ordinary Execute/Retry cannot bypass it",
            "tool isolation is never shown as zero usage",
            "returns `INDETERMINATE` without calling the model",
            "**Stop run** stops the worker and ends the Run as blocked",
            "even `PASS` cannot approve, retry, authorize, complete, or accept the Run",
        ):
            assert token in guide
        tracker = (VAULT_ORA / "Working — Ora Setup and Refinement.md").read_text()
        program = (
            VAULT_ORA / "Working — Framework — Ora Project Integration Program.md"
        ).read_text()
        registry = (
            VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
        ).read_text()
        combined = "\n".join((tracker, program, registry))
        for token in (
            "G1.20 is implemented and submitted for independent judgment",
            "G1.19 remains unauthorized until G1.20 is accepted",
            "G1.17 is user-deferred",
        ):
            assert token in combined
        assert "Gate G1.20: PASS" not in combined
        assert "G1.20 — ✅" not in combined
        evidence = (ROOT / "outputs" / "g1-20" / "closeout-evidence.md").read_text()
        for token in (
            "python3 -m pytest -q \\",
            "# 141 passed, 85 subtests passed; exit 0",
            "# 28/28 + 15/15 + 26/26 + 19/19 + 8/8 = 96/96; exit 0",
            "python3 scripts/verify-implementation.py --check drift",
            "# 2/2 body-identical; exit 0",
            "git diff cb57d71a8893554370785f7b1b0eefcae4848dc8..HEAD --check",
            "git diff 87d29cc8562cf443d10215f662daa499bd14777d..HEAD --check",
        ):
            assert token in evidence
        assert "G1.19 is authorized" not in combined

    def test_opt_in_quality_review_is_handoff_only_authority_inert_and_idempotent(self):
        state = self._handoff()
        before = self.runtime.load_run(state["run_id"])
        calls = []

        def evaluate(package, binding):
            calls.append((copy.deepcopy(package), copy.deepcopy(binding)))
            return {
                "verdict": "WARN",
                "drift_verdict": "POSSIBLE",
                "quality_verdict": "WARN",
                "findings": ["The draft checkpoint still requires the Principal."],
                "rationale": "This is an observation at the declared human handoff.",
            }

        service = inspector.ProcessRunTelemetryService(
            runtime=self.runtime,
            evaluator=evaluate,
        )
        result = service.evaluate(
            state["run_id"], idempotency_key="quality:handoff:1",
        )
        retry = service.evaluate(
            state["run_id"], idempotency_key="quality:handoff:1",
        )
        after = self.runtime.load_run(state["run_id"])

        assert result["status"] == "completed"
        assert retry["status"] == "idempotent_retry"
        assert len(calls) == 1
        assert calls[0][0]["eligible_reason"] == "human_handoff"
        assert calls[0][0]["schema_version"] == (
            "ora.process-quality-evaluation-subject/2.0"
        )
        assert calls[0][0]["material_status"]["evaluable"] is True
        assert calls[0][0]["inputs"] == self.inputs()
        assert all(
            artifact["content_available"]
            and artifact["content_digest_verified"]
            and artifact["content"]
            for artifact in calls[0][0]["artifacts"]
        )
        contract = calls[0][0]["governing_contract"]
        assert contract["acceptance_criteria"]
        assert any(
            item["instruction"] == "Produce a faithful concise summary of the exact inbound email."
            for item in contract["operation_instructions"]
        )
        assert calls[0][0]["source_context"]["event_type"] == "run_paused"
        assert before["state"] == after["state"] == "pending"
        assert before["current_node_id"] == after["current_node_id"] == "draft-approval"
        assert before["artifact_ids"] == after["artifact_ids"]
        assert before["contracts"]["correction_loop"] == after["contracts"]["correction_loop"]
        history = self._inspector().inspect(state["run_id"])["views"][
            "current_state"
        ]["telemetry"]["quality_evaluation"]["history"]
        assert history[0]["verdict"]["verdict"] == "WARN"

        fresh = self.service.begin_run(
            definition_ref=self._accepted_ref(),
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:email:fresh-quality-boundary",
        )
        with pytest.raises(
            inspector.ProcessRunTelemetryConflict,
            match="human handoff or output failure",
        ):
            service.evaluate(
                fresh["run_id"], idempotency_key="quality:ordinary-step:1",
            )

    def test_partial_quality_output_fails_as_authority_inert_observation(self):
        state = self._handoff()
        before = self.runtime.load_run(state["run_id"])
        calls = []

        def partial(_package, _binding):
            calls.append(True)
            return {"verdict": "PASS", "findings": []}

        service = inspector.ProcessRunTelemetryService(
            runtime=self.runtime,
            evaluator=partial,
        )
        failed = service.evaluate(
            state["run_id"], idempotency_key="quality:partial:1",
        )
        retry = service.evaluate(
            state["run_id"], idempotency_key="quality:partial:1",
        )
        after = self.runtime.load_run(state["run_id"])
        assert failed["status"] == "failed"
        assert retry["status"] == "idempotent_retry"
        assert len(calls) == 1
        assert before["state"] == after["state"] == "pending"
        assert before["current_node_id"] == after["current_node_id"]
        assert before["artifact_ids"] == after["artifact_ids"]
        assert before["contracts"]["correction_loop"] == after["contracts"]["correction_loop"]
        history = self._inspector().inspect(state["run_id"])["views"][
            "overview"
        ]["telemetry"]["quality_evaluation"]["history"]
        assert history[0]["status"] == "failed"
        assert history[0]["verdict"] is None

    def test_output_failure_surfaces_error_and_is_the_only_other_review_seam(self):
        ref = self._accepted_ref()
        failing = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=automation.IsolatedProcessWorker(
                runner=lambda _request: (_ for _ in ()).throw(RuntimeError("offline"))
            ),
        )
        begun = failing.begin_run(
            definition_ref=ref,
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:email:failure",
        )
        with pytest.raises(automation.ProcessAutomationWorkerError):
            failing.execute(begun["run_id"])

        telemetry = self._inspector().inspect(begun["run_id"])["views"][
            "current_state"
        ]["telemetry"]
        assert telemetry["last_error"]["codes"] == ["isolated_worker_failure"]
        assert telemetry["health"]["status"] == "action_required"
        assert telemetry["quality_evaluation"]["eligibility"]["reason"] == "output_failure"

    def _slow_service(self):
        command = [
            sys.executable,
            "-c",
            (
                "import json,sys,time; "
                "from orchestrator.process_automation_worker import execute; "
                "request=json.load(sys.stdin); time.sleep(10); "
                "print(json.dumps(execute(request)))"
            ),
        ]
        return automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=automation.IsolatedProcessWorker(
                command=command, timeout_seconds=20,
            ),
        )

    @staticmethod
    def _wait_for_worker(run_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            worker = automation.active_automation_worker(run_id)
            if worker and worker["alive"]:
                return worker
            time.sleep(0.01)
        raise AssertionError("isolated worker never became observable")

    def _drive_in_thread(self, service, run_id):
        result = {}

        def drive():
            try:
                result["state"] = service.execute(run_id)
            except Exception as exc:  # pragma: no cover - asserted below
                result["error"] = exc

        thread = threading.Thread(target=drive)
        thread.start()
        self._wait_for_worker(run_id)
        return thread, result

    def test_pause_stops_exact_live_worker_and_resume_continues_from_checkpoint(self):
        ref = self._accepted_ref()
        service = self._slow_service()
        begun = service.begin_run(
            definition_ref=ref,
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:email:pause-control",
        )
        thread, result = self._drive_in_thread(service, begun["run_id"])
        controls = service.run_controls(begun["run_id"])
        assert controls["active_worker"]["alive"] is True

        applied = service.control_run(
            begun["run_id"],
            action="pause",
            control_state_digest=controls["control_state_digest"],
            idempotency_key="control:pause:1",
        )
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert "error" not in result
        assert applied["run"]["status"] == "paused_by_user"
        assert automation.active_automation_worker(begun["run_id"]) is None
        event_types = [
            (record.get("event") or {}).get("event_type")
            for record in self.runtime.load_records(begun["run_id"])
        ]
        for event_type in (
            "process_worker_started", "process_worker_finished",
            "process_run_control_requested", "process_run_control_applied",
            "run_paused",
        ):
            assert event_type in event_types

        with pytest.raises(
            automation.ProcessAutomationConflict,
            match="authenticated Resume control",
        ):
            service.execute(begun["run_id"])

        service.worker = self.worker
        paused_controls = service.run_controls(begun["run_id"])
        resumed = service.control_run(
            begun["run_id"],
            action="resume",
            control_state_digest=paused_controls["control_state_digest"],
            idempotency_key="control:resume:1",
        )
        assert resumed["run"]["status"] == "awaiting_human_checkpoint"
        assert resumed["run"]["current_node"]["node_id"] == "draft-approval"

    def test_user_pause_survives_direct_api_and_restart_retry_until_exact_resume(self):
        begun = self.begin(self._accepted_ref())
        controls = self.service.run_controls(begun["run_id"])
        paused = self.service.control_run(
            begun["run_id"],
            action="pause",
            control_state_digest=controls["control_state_digest"],
            idempotency_key="control:pause:no-worker",
        )
        assert paused["run"]["status"] == "paused_by_user"
        assert paused["run"]["pause_kind"] == "user_control"
        before_run = self.runtime.load_run(begun["run_id"])
        before_records = self.runtime.load_records(begun["run_id"])

        with pytest.raises(
            automation.ProcessAutomationConflict,
            match="authenticated Resume control",
        ):
            self.service.execute(begun["run_id"])
        with pytest.raises(Exception, match="authenticated Resume control"):
            self.runtime.resume_run(begun["run_id"])

        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_automation_service", return_value=self.service,
        ):
            response = client.post(
                f"/api/process-automation/runs/{begun['run_id']}",
                json={"action": "retry"},
            )
        assert response.status_code == 409

        restarted = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=self.worker,
        )
        with pytest.raises(
            automation.ProcessAutomationConflict,
            match="authenticated Resume control",
        ):
            restarted.execute(begun["run_id"])
        assert self.runtime.load_run(begun["run_id"]) == before_run
        assert self.runtime.load_records(begun["run_id"]) == before_records

        resume = restarted.run_controls(begun["run_id"])
        continued = restarted.control_run(
            begun["run_id"],
            action="resume",
            control_state_digest=resume["control_state_digest"],
            idempotency_key="control:resume:no-worker",
        )
        assert continued["run"]["status"] == "awaiting_human_checkpoint"
        resumed = [
            record for record in self.runtime.load_records(begun["run_id"])
            if (record.get("event") or {}).get("event_type") == "run_resumed"
            and (record.get("event") or {}).get("details", {}).get(
                "resume_authority"
            ) == "authenticated_process_run_control"
        ]
        assert len(resumed) == 1
        assert resumed[0]["event"]["details"]["control_request_record_id"]

    def _persist_pause_control_pair(self, run_id, idempotency_key):
        run = self.runtime.load_run(run_id)
        request = self.runtime._record_runtime_event(
            run_id,
            "process_run_control_requested",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "idempotency_key": idempotency_key,
                "control_state_digest": "sha256:" + "a" * 64,
                "action": "pause",
                "execution_id": None,
                "run_state": run["state"],
                "node_id": run["current_node_id"],
                "attempt": run["contracts"]["correction_loop"]["attempt"],
                "decision_by": run["contracts"]["authority"]["principal_id"],
            },
            node_id=run["current_node_id"],
        )
        self.service._record_control_applied(
            run_id,
            request_record=request,
            action="pause",
            execution_id=None,
        )
        return request

    def test_rejected_stale_and_racing_pause_requests_never_mutate_a_checkpoint(self):
        begun = self.begin(self._accepted_ref())
        run_id = begun["run_id"]
        before_run = self.runtime.load_run(run_id)
        before_records = self.runtime.load_records(run_id)
        with pytest.raises(Exception, match="authenticated request/application pair"):
            self.runtime.pause_run(
                run_id,
                "forged-pause-checkpoint",
                segment_id="classify",
                resume_node_id="draft-approval",
                reason="forged",
                pause_kind="user_control",
                control_request_record_id="event-does-not-exist",
            )
        assert self.runtime.load_run(run_id) == before_run
        assert self.runtime.load_records(run_id) == before_records
        with pytest.raises(Exception, match="no checkpoint exists|only a pending Process Run"):
            self.runtime.resume_run(run_id)
        assert self.runtime.load_run(run_id)["current_node_id"] == "classify"

        run = self.runtime.load_run(run_id)
        stale_request = self.runtime._record_runtime_event(
            run_id,
            "process_run_control_requested",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "idempotency_key": "control:pause:stale-direct",
                "control_state_digest": "sha256:" + "b" * 64,
                "action": "pause",
                "execution_id": None,
                "run_state": "running",
                "node_id": "summarize",
                "attempt": run["contracts"]["correction_loop"]["attempt"],
                "decision_by": run["contracts"]["authority"]["principal_id"],
            },
            node_id=run["current_node_id"],
        )
        self.runtime._record_runtime_event(
            run_id,
            "process_run_control_applied",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "control_request_record_id": stale_request["record_id"],
                "idempotency_key": "control:pause:stale-direct",
                "action": "pause",
                "execution_id": None,
                "source_run_state": "running",
                "node_id": "summarize",
                "attempt": run["contracts"]["correction_loop"]["attempt"],
            },
            node_id=run["current_node_id"],
        )
        stale_run = self.runtime.load_run(run_id)
        stale_records = self.runtime.load_records(run_id)
        with pytest.raises(Exception, match="does not bind the current Run"):
            self.runtime.pause_run(
                run_id,
                "stale-pause-checkpoint",
                segment_id="classify",
                resume_node_id="draft-approval",
                reason="stale",
                pause_kind="user_control",
                control_request_record_id=stale_request["record_id"],
            )
        assert self.runtime.load_run(run_id) == stale_run
        assert self.runtime.load_records(run_id) == stale_records

        requests = [
            self._persist_pause_control_pair(
                run_id, f"control:pause:race:{number}",
            )
            for number in (1, 2)
        ]
        race_records = self.runtime.load_records(run_id)
        barrier = threading.Barrier(2)
        outcomes = []

        def race(number):
            barrier.wait()
            try:
                result = self.runtime.pause_run(
                    run_id,
                    f"race-pause-checkpoint-{number}",
                    segment_id="classify",
                    resume_node_id="classify",
                    reason="racing authenticated pause",
                    pause_kind="user_control",
                    control_request_record_id=requests[number - 1]["record_id"],
                )
                outcomes.append(("applied", result))
            except Exception as exc:
                outcomes.append(("rejected", exc))

        threads = [threading.Thread(target=race, args=(number,)) for number in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert all(not thread.is_alive() for thread in threads)
        assert sorted(kind for kind, _value in outcomes) == ["applied", "rejected"]
        after_records = self.runtime.load_records(run_id)
        assert len(after_records) == len(race_records) + 2
        assert [
            (record.get("event") or {}).get("event_type")
            for record in after_records[-2:]
        ] == ["checkpoint_created", "run_paused"]
        assert self.runtime.load_run(run_id)["state"] == "pending"

    def test_quality_failure_packet_binds_content_contract_and_exact_error_trace(self):
        ref = self._accepted_ref()

        def fail_draft(request):
            if request["operation"] == "email.draft":
                raise RuntimeError("draft evaluator offline at exact boundary")
            return worker_module.execute(request)

        failing = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=automation.IsolatedProcessWorker(runner=fail_draft),
        )
        begun = failing.begin_run(
            definition_ref=ref,
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:quality:failure-material",
        )
        handoff = failing.execute(begun["run_id"])
        assert handoff["status"] == "awaiting_human_checkpoint"
        with pytest.raises(automation.ProcessAutomationWorkerError):
            failing.resolve_checkpoint(
                begun["run_id"], outcome="approved", decision_by="principal:user",
            )

        captured = []

        def evaluate(package, _binding):
            captured.append(copy.deepcopy(package))
            return {
                "verdict": "FAIL",
                "drift_verdict": "NONE",
                "quality_verdict": "FAIL",
                "findings": ["The declared draft output was not produced."],
                "rationale": "The exact failure trace records worker unavailability.",
            }

        result = inspector.ProcessRunTelemetryService(
            runtime=self.runtime, evaluator=evaluate,
        ).evaluate(
            begun["run_id"], idempotency_key="quality:failure:material",
        )
        assert result["evaluation"]["verdict"]["quality_verdict"] == "FAIL"
        assert len(captured) == 1
        packet = captured[0]
        assert packet["material_status"]["evaluable"] is True
        assert packet["governing_contract"]["acceptance_criteria"]
        assert all(item["content_available"] for item in packet["artifacts"])
        failure = next(
            row for row in packet["failure_trace"]
            if row["event_type"] == "isolated_process_action_failed"
        )
        assert failure["details"]["error"] == (
            "draft evaluator offline at exact boundary"
        )
        assert failure["record_id"] == packet["source_record_id"]

    def test_quality_review_is_indeterminate_without_authenticated_content(self):
        state = self._handoff()
        run = self.runtime.load_run(state["run_id"])
        artifact = self.runtime.load_artifact(state["run_id"], run["artifact_ids"][0])
        path = artifact["locator"]["ref"]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("unbound drift")
        calls = []
        result = inspector.ProcessRunTelemetryService(
            runtime=self.runtime,
            evaluator=lambda package, binding: calls.append((package, binding)),
        ).evaluate(
            state["run_id"], idempotency_key="quality:unavailable:content",
        )
        assert calls == []
        assert result["status"] == "completed"
        assert result["evaluation"]["model_invoked"] is False
        verdict = result["evaluation"]["verdict"]
        assert verdict["verdict"] == "INDETERMINATE"
        assert verdict["quality_verdict"] == "INDETERMINATE"
        assert any("does not match its identity" in item for item in verdict["findings"])

    def test_stop_terminates_live_worker_and_retry_is_one_terminal_identity(self):
        ref = self._accepted_ref()
        service = self._slow_service()
        begun = service.begin_run(
            definition_ref=ref,
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:email:stop-control",
        )
        thread, result = self._drive_in_thread(service, begun["run_id"])
        controls = service.run_controls(begun["run_id"])
        first = service.control_run(
            begun["run_id"],
            action="stop",
            control_state_digest=controls["control_state_digest"],
            idempotency_key="control:stop:1",
        )
        thread.join(timeout=5)
        retry = service.control_run(
            begun["run_id"],
            action="stop",
            control_state_digest=controls["control_state_digest"],
            idempotency_key="control:stop:1",
        )
        assert "error" not in result
        assert first["run"]["run_state"] == "blocked"
        assert retry["status"] == "idempotent_retry"
        assert retry["run"]["run_state"] == "blocked"
        assert len([
            record for record in self.runtime.load_records(begun["run_id"])
            if (record.get("event") or {}).get("event_type")
            == "process_run_control_requested"
        ]) == 1

    def test_stop_from_human_handoff_uses_the_same_authenticated_blocked_route(self):
        state = self._handoff()
        controls = self.service.run_controls(state["run_id"])
        assert controls["available_actions"] == ["stop"]
        with mock.patch.object(
            self.service,
            "_record_control_applied",
            side_effect=RuntimeError("interrupted pending stop"),
        ):
            with pytest.raises(RuntimeError, match="interrupted pending stop"):
                self.service.control_run(
                    state["run_id"],
                    action="stop",
                    control_state_digest=controls["control_state_digest"],
                    idempotency_key="control:stop:human-handoff",
                )
        restarted = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=self.worker,
        )
        stopped = restarted.control_run(
            state["run_id"],
            action="stop",
            control_state_digest=controls["control_state_digest"],
            idempotency_key="control:stop:human-handoff",
        )
        assert stopped["run"]["run_state"] == "blocked"
        assert stopped["run"]["current_node"]["node_id"] == "blocked"
        transitions = [
            record for record in self.runtime.load_records(state["run_id"])
            if record.get("record_type") == "transition"
        ]
        assert transitions[-1]["transition"]["directive"] == "BLOCKED"
        assert transitions[-1]["transition"]["evaluation_boundary"] == "mechanical_graph_route"

    def test_control_retry_recovers_request_persisted_before_application(self):
        ref = self._accepted_ref()
        begun = self.begin(ref)
        controls = self.service.run_controls(begun["run_id"])
        with mock.patch.object(
            self.service,
            "_record_control_applied",
            side_effect=RuntimeError("injected interruption after request persistence"),
        ):
            with pytest.raises(RuntimeError, match="injected interruption"):
                self.service.control_run(
                    begun["run_id"],
                    action="pause",
                    control_state_digest=controls["control_state_digest"],
                    idempotency_key="control:pause:interrupted",
                )

        assert self.runtime.load_run(begun["run_id"])["state"] == "running"
        restarted = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=self.worker,
        )
        recovered = restarted.control_run(
            begun["run_id"],
            action="pause",
            control_state_digest=controls["control_state_digest"],
            idempotency_key="control:pause:interrupted",
        )
        assert recovered["status"] == "idempotent_retry"
        assert recovered["run"]["run_state"] == "pending"
        records = self.runtime.load_records(begun["run_id"])
        assert sum(
            (record.get("event") or {}).get("event_type")
            == "process_run_control_requested"
            for record in records
        ) == 1
        assert sum(
            (record.get("event") or {}).get("event_type")
            == "process_run_control_applied"
            for record in records
        ) == 1

    def test_lost_worker_is_visible_then_recovered_without_replay(self):
        ref = self._accepted_ref()
        begun = self.begin(ref)
        run_id = begun["run_id"]
        self.runtime.create_checkpoint(
            run_id, "pre-classify-orphan",
            segment_id="classify", resume_node_id="classify",
        )
        attempt = self.runtime.begin_automation_attempt(run_id, "classify")
        number = attempt["event"]["details"]["attempt"]
        run = self.runtime.load_run(run_id)
        self.runtime._record_runtime_event(
            run_id,
            "process_worker_started",
            {
                "run_id": run_id,
                "definition_ref": copy.deepcopy(run["definition_ref"]),
                "execution_id": "worker-orphaned-restart",
                "node_id": "classify",
                "attempt": number,
                "pid": 999999,
                "worker_boundary": "separate_no_tools_process",
                "worker_request_digest": "sha256:" + "9" * 64,
            },
            node_id="classify",
        )
        before = self._inspector().inspect(run_id)["views"]["current_state"][
            "telemetry"
        ]
        assert before["liveness"]["status"] == "orphaned_after_restart"
        assert before["liveness"]["action_required"] is True

        restarted = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=self.worker,
        )
        recovered = restarted.execute(run_id)
        assert recovered["status"] == "paused_after_failure"
        records = self.runtime.load_records(run_id)
        completed = [
            record for record in records
            if (record.get("event") or {}).get("event_type") == "attempt_completed"
        ]
        assert completed[-1]["event"]["details"]["defect_codes"] == [
            "worker_orphaned_after_restart"
        ]
        after = self._inspector().inspect(run_id)["views"]["current_state"][
            "telemetry"
        ]
        assert after["liveness"]["status"] == "recovered_after_restart"

    def test_public_endpoints_reject_stale_controls_and_noneligible_evaluation(self):
        ref = self._accepted_ref()
        begun = self.begin(ref)
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_automation_service", return_value=self.service,
        ):
            response = client.post(
                f"/api/process-runs/{begun['run_id']}/control",
                json={
                    "action": "pause",
                    "control_state_digest": "sha256:" + "0" * 64,
                    "idempotency_key": "control:stale:1",
                },
            )
        assert response.status_code == 409

        telemetry_service = inspector.ProcessRunTelemetryService(
            runtime=self.runtime,
            evaluator=lambda _package, _binding: {},
        )
        with mock.patch.object(
            server, "_process_run_telemetry_service", return_value=telemetry_service,
        ):
            response = client.post(
                f"/api/process-runs/{begun['run_id']}/quality-evaluation",
                json={"idempotency_key": "quality:not-eligible:1"},
            )
        assert response.status_code == 409

    def test_authoritative_telemetry_events_cannot_be_forged_publicly(self):
        state = self._handoff()
        before = self.runtime.load_records(state["run_id"])
        for event_type in (
            "process_worker_started",
            "isolated_process_action_failed",
            "process_run_control_requested",
            "process_quality_evaluation_completed",
        ):
            with pytest.raises(Exception):
                self.runtime.record_event(
                    state["run_id"], event_type, {"forged": True},
                )
        run = self.runtime.load_run(state["run_id"])
        source = next(
            record for record in reversed(before)
            if (record.get("event") or {}).get("event_type")
            not in {
                "process_quality_evaluation_started",
                "process_quality_evaluation_completed",
                "process_quality_evaluation_failed",
            }
        )
        verdict = {
            "verdict": "PASS",
            "drift_verdict": "NONE",
            "quality_verdict": "PASS",
            "findings": [],
            "rationale": "forged",
        }
        with pytest.raises(Exception, match="runtime-derived evaluation path"):
            self.runtime.record_process_quality_evaluation(
                state["run_id"],
                "process_quality_evaluation_completed",
                {
                    "run_id": state["run_id"],
                    "definition_ref": copy.deepcopy(run["definition_ref"]),
                    "evaluation_id": "quality-forged",
                    "idempotency_key": "quality:forged",
                    "subject_digest": "sha256:" + "1" * 64,
                    "eligible_reason": "human_handoff",
                    "source_record_id": source["record_id"],
                    "source_sequence": source["sequence"],
                    "evaluator_binding": {"kind": "forged"},
                    "evaluation_start_record_id": "event-does-not-exist",
                    "response_digest": automation._digest_json(verdict),
                    "verdict": verdict,
                },
                node_id=run["current_node_id"],
            )
        fresh = self.service.begin_run(
            definition_ref=self._accepted_ref(),
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:forged-control-route",
        )
        fresh_before = self.runtime.load_records(fresh["run_id"])
        with pytest.raises(Exception, match="authenticated request/application pair"):
            self.runtime.block_by_process_run_control(
                fresh["run_id"],
                control_request_record_id="event-does-not-exist",
                target_node_id="blocked",
                reason="forged",
            )
        assert self.runtime.load_records(state["run_id"]) == before
        assert self.runtime.load_records(fresh["run_id"]) == fresh_before

    def test_forged_quality_start_and_matching_pass_leave_no_records(self):
        state = self._handoff()
        run_id = state["run_id"]
        run = self.runtime.load_run(run_id)
        records = self.runtime.load_records(run_id)
        old_source = next(
            record for record in records
            if (record.get("event") or {}).get("event_type") == "run_created"
        )
        common = {
            "run_id": run_id,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "evaluation_id": "quality-fabricated-complete-pass",
            "idempotency_key": "quality:fabricated:complete-pass",
            "subject_digest": "sha256:" + "1" * 64,
            "eligible_reason": "human_handoff",
            "source_record_id": old_source["record_id"],
            "source_sequence": old_source["sequence"],
            "evaluator_binding": {
                "kind": "exact_run_model_profile",
                "runtime_name": "substituted-model",
            },
        }
        with pytest.raises(Exception, match="runtime-derived evaluation path"):
            self.runtime.record_process_quality_evaluation(
                run_id,
                "process_quality_evaluation_started",
                common,
                node_id=run["current_node_id"],
            )
        verdict = {
            "verdict": "PASS",
            "drift_verdict": "NONE",
            "quality_verdict": "PASS",
            "findings": [],
            "rationale": "fabricated",
        }
        with pytest.raises(Exception, match="runtime-derived evaluation path"):
            self.runtime.record_process_quality_evaluation(
                run_id,
                "process_quality_evaluation_completed",
                {
                    **common,
                    "evaluation_start_record_id": "event-fabricated-start",
                    "response_digest": automation._digest_json(verdict),
                    "verdict": verdict,
                },
                node_id=run["current_node_id"],
            )
        assert self.runtime.load_run(run_id) == run
        assert self.runtime.load_records(run_id) == records
