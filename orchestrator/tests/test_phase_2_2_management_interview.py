"""G1.1 Phase 2.2 — persistent management-interview proofs."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
os.environ.setdefault("ORA_HOME", str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import conversation_memory as memory  # noqa: E402
import governed_process_runtime as runtime  # noqa: E402
import process_entry_routing as entry  # noqa: E402
import process_management_interview as interview  # noqa: E402
from server import server  # noqa: E402


NOW = "2026-07-18T12:00:00Z"


def construction_route(objective: str = "Automate my weekly cash-flow report."):
    return entry.route_process_entry({
        "source": "natural_language",
        "objective": objective,
        "project_ref": "ora",
        "project_confirmed": True,
    })


class Phase22ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.sessions = self.root / "sessions"
        self.runtime = runtime.GovernedProcessRuntime(
            self.runs, now=lambda: NOW,
        )
        self.service = interview.ManagementInterviewService(
            runtime=self.runtime,
            sessions_root=self.sessions,
            repository_root=ROOT,
            now=lambda: NOW,
        )

    def start(self, objective: str = "Automate my weekly cash-flow report."):
        return self.service.start_or_resume(
            "dialogue-phase-2-2", construction_route(objective),
        )

    def complete(self, state):
        index = 0
        while state["status"] == "interviewing":
            state = self.service.answer(
                state["dialogue_ref"], f"principal answer {index}",
            )
            index += 1
        return state

    def test_exact_programming_definition_is_loaded_for_the_governing_run(self):
        definition = entry.load_programming_definition(ROOT)
        state = self.start()
        self.assertEqual(state["definition_ref"], {
            "definition_id": definition["definition_id"],
            "version": definition["version"],
            "digest": definition["digest"],
        })
        self.assertEqual(self.runtime.load_definition(state["run_id"]), definition)

    def test_run_is_bound_bidirectionally_to_dialogue_and_interview_node(self):
        state = self.start()
        binding = memory.load_governing_process_binding(
            "dialogue-phase-2-2", sessions_root=self.sessions,
        )
        run = self.runtime.load_run(state["run_id"])
        self.assertEqual(binding["run_id"], run["run_id"])
        self.assertEqual(binding["binding_digest"], state["binding_digest"])
        self.assertNotIn("dialogue_binding_digest", run["input_bindings"])
        self.assertNotIn("entry_contract_digest", run["input_bindings"])
        self.assertEqual(run["input_bindings"]["dialogue_ref"],
                         "dialogue-phase-2-2")
        self.assertEqual(run["state"], "running")
        self.assertEqual(run["current_node_id"], "intent-interview")

    def test_run_inputs_conform_to_issued_programming_input_schema(self):
        state = self.start()
        run = self.runtime.load_run(state["run_id"])
        definition = self.runtime.load_definition(state["run_id"])
        jsonschema.Draft202012Validator(
            definition["input_schema"]
        ).validate(run["input_bindings"])

    def test_only_unresolved_dimensions_are_asked(self):
        state = self.start()
        self.assertEqual(set(state["answers"]), {
            "intended_result", "reuse", "initiation",
        })
        self.assertNotIn("intended_result", state["unresolved_dimensions"])
        self.assertNotIn("reuse", state["unresolved_dimensions"])
        self.assertNotIn("initiation", state["unresolved_dimensions"])
        self.assertEqual(state["current_question"]["dimension"], "affected_parties")
        self.assertTrue(state["current_question"]["evidence"])
        self.assertTrue(state["current_question"]["consequence"])

    def test_nonrecurring_construction_does_not_invent_reuse_or_initiation(self):
        state = self.start("Implement a new API endpoint in the repository.")
        self.assertEqual(set(state["answers"]), {"intended_result"})
        self.assertIn("reuse", state["unresolved_dimensions"])
        self.assertIn("initiation", state["unresolved_dimensions"])

    def test_explicit_management_facts_in_initial_request_are_not_reasked(self):
        objective = (
            "Automate a monthly report for the finance team using invoice CSVs "
            "and generate a PDF. Ora may read the finance folder without asking, "
            "but if an invoice is missing, stop and ask me. Accept it when totals "
            "are verified by the reconciliation test."
        )
        state = self.start(objective)
        self.assertEqual(state["status"], "ready_for_plan")
        self.assertEqual(state["unresolved_dimensions"], [])
        self.assertEqual(tuple(state["answers"]), interview.INTERVIEW_DIMENSIONS)

    def test_one_answer_can_resolve_other_explicitly_supplied_facts(self):
        state = self.start("Implement a new API endpoint in the repository.")
        state = self.service.answer(
            "dialogue-phase-2-2",
            "The finance team uses it. It reads invoice CSVs and generates a PDF "
            "monthly. Ora may read the finance folder without asking, but if an "
            "invoice is missing, stop and ask me. Accept it when totals are verified "
            "by the reconciliation test.",
        )
        self.assertEqual(state["status"], "ready_for_plan")
        self.assertEqual(state["unresolved_dimensions"], [])

    def test_answer_and_pending_question_survive_service_restart(self):
        state = self.start()
        first_question = state["current_question"]
        state = self.service.answer(
            "dialogue-phase-2-2", "The finance team and the principal.",
        )
        restarted = interview.ManagementInterviewService(
            runtime=runtime.GovernedProcessRuntime(self.runs, now=lambda: NOW),
            sessions_root=self.sessions,
            repository_root=ROOT,
            now=lambda: NOW,
        ).get_state("dialogue-phase-2-2")
        self.assertEqual(restarted["run_id"], state["run_id"])
        self.assertEqual(
            restarted["answers"][first_question["dimension"]]["answer"],
            "The finance team and the principal.",
        )
        self.assertEqual(restarted["current_question"], state["current_question"])

    def test_retry_is_idempotent_but_different_route_cannot_displace_run(self):
        state = self.start()
        again = self.start()
        self.assertEqual(again["run_id"], state["run_id"])
        run_dirs = [item for item in self.runs.iterdir() if item.is_dir()]
        self.assertEqual(len(run_dirs), 1)
        with self.assertRaises(interview.ManagementInterviewConflict):
            self.service.start_or_resume(
                "dialogue-phase-2-2",
                construction_route("Build a different reusable capability."),
            )

    def test_route_digest_change_cannot_rebind_same_deterministic_run(self):
        route = construction_route()
        self.service.start_or_resume("dialogue-phase-2-2", route)
        changed = copy.deepcopy(route)
        changed["classification_basis"] = ["different basis"]
        body = {key: value for key, value in changed.items()
                if key != "contract_digest"}
        changed["contract_digest"] = interview._digest_json(body)
        with self.assertRaises(interview.ManagementInterviewConflict):
            self.service.start_or_resume("dialogue-phase-2-2", changed)

    def test_all_ten_dimensions_complete_without_creating_phase_2_3_plan(self):
        state = self.complete(self.start())
        self.assertEqual(tuple(state["answers"]), interview.INTERVIEW_DIMENSIONS)
        self.assertEqual(state["status"], "ready_for_plan")
        self.assertEqual(state["next_action"], "await_phase_2_3_plan")
        self.assertFalse(state["creates_plan"])
        self.assertEqual(state["authority_effects"], [])
        run = self.runtime.load_run(state["run_id"])
        self.assertEqual(run["current_node_id"], "intent-interview")
        self.assertEqual(
            run["contracts"]["approved_plan"]["approved_node_ids"],
            ["entry-route", "intent-interview"],
        )
        grant = run["contracts"]["authority"]["grants"][0]
        self.assertEqual(grant["actions"], ["elicit_programming_intent"])
        self.assertIn("mutate", run["contracts"]["authority"]["reserved_actions"])

    def test_temporary_framework_call_returns_to_same_pending_question(self):
        state = self.start()
        pending = copy.deepcopy(state["current_question"])
        call = self.service.begin_temporary_framework_call(
            "dialogue-phase-2-2", "terrain-mapping", "Map this uncertainty.",
        )
        during = self.service.get_state("dialogue-phase-2-2")
        self.assertEqual(during["run_id"], state["run_id"])
        self.assertEqual(during["current_question"], pending)
        resumed = self.service.complete_temporary_framework_call(
            "dialogue-phase-2-2",
            call["call_id"],
            status="ok",
            result_ref={"conversation_id": "dialogue-phase-2-2", "chunk_id": "chunk-1"},
        )
        self.assertEqual(resumed["current_question"], pending)
        self.assertEqual(resumed["temporary_framework_calls"][0]["status"], "ok")

    def test_programming_cannot_displace_its_own_interview(self):
        self.start()
        with self.assertRaises(interview.ManagementInterviewConflict):
            self.service.begin_temporary_framework_call(
                "dialogue-phase-2-2", "programming", "Do something else.",
            )

    def test_generic_event_api_cannot_forge_interview_observations(self):
        state = self.start()
        for event_type in ("dialogue_observation_recorded", "dialogue_forged"):
            with self.subTest(event_type=event_type), self.assertRaises(
                runtime.AuthorityDeniedError
            ):
                self.runtime.record_event(state["run_id"], event_type, {})

    def test_no_public_direct_observation_api_bypasses_interview_validation(self):
        state = self.start()
        self.assertFalse(hasattr(self.runtime, "record_dialogue_observation"))
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.record_event(
                state["run_id"], "dialogue_observation_recorded", {
                    "observation_type": "management_interview_answered",
                    "payload": {"answer": "forged"},
                },
            )

    def test_event_payload_tampering_is_detected_on_restart(self):
        state = self.start()
        path = self.runtime._events_path(state["run_id"])
        lines = path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        target = next(
            record for record in records
            if (record.get("event") or {}).get("event_type")
               == "dialogue_observation_recorded"
        )
        target["event"]["details"]["payload"]["project_ref"] = "substituted"
        path.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(interview.ManagementInterviewIntegrityError):
            self.service.get_state("dialogue-phase-2-2")

    def test_dialogue_binding_tampering_is_detected(self):
        self.start()
        envelope_path = self.sessions / "dialogue-phase-2-2" / "conversation.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["governing_process"]["run_id"] = "run-substituted"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaises(interview.ManagementInterviewIntegrityError):
            self.service.get_state("dialogue-phase-2-2")

    def test_stealth_dialogue_cannot_start_persistent_interview(self):
        memory.ensure_conversation_envelope(
            "stealth-dialogue", tag="stealth", sessions_root=self.sessions,
        )
        with self.assertRaises(interview.ManagementInterviewConflict):
            self.service.start_or_resume(
                "stealth-dialogue", construction_route(), dialogue_tag="stealth",
            )

    def test_fork_does_not_inherit_governing_process_binding(self):
        self.start()
        child = memory.fork_conversation(
            "dialogue-phase-2-2", "dialogue-child", sessions_root=self.sessions,
        )
        self.assertIsNotNone(child)
        self.assertNotIn("governing_process", child)
        self.assertIsNone(memory.load_governing_process_binding(
            "dialogue-child", sessions_root=self.sessions,
        ))


class Phase22ServerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sessions = self.root / "sessions"
        self.service = interview.ManagementInterviewService(
            runtime=runtime.GovernedProcessRuntime(
                self.root / "runs", now=lambda: NOW,
            ),
            sessions_root=self.sessions,
            repository_root=ROOT,
            now=lambda: NOW,
        )
        server.app.config["TESTING"] = True
        self.client = server.app.test_client()
        self.binding_root = mock.patch.object(
            memory, "_DEFAULT_SESSIONS_ROOT", self.sessions,
        )
        self.binding_root.start()
        self.addCleanup(self.binding_root.stop)
        self.service_factory = mock.patch.object(
            server, "_management_interview_service", return_value=self.service,
        )
        self.service_factory.start()
        self.addCleanup(self.service_factory.stop)

    def post(self, message, **extra):
        payload = {
            "message": message,
            "conversation_id": "server-dialogue-phase-2-2",
        }
        payload.update(extra)
        return self.client.post("/chat", json=payload)

    def test_confirmed_construction_starts_interview_instead_of_pipeline(self):
        route = construction_route()
        saved = server._json_response({
            "status": "ok", "conversation_id": "server-dialogue-phase-2-2",
            "chunk_id": "chunk-interview",
        })
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-1",
        ), mock.patch.object(
            server, "_process_entry_project_visible", return_value=True,
        ), mock.patch.object(
            server, "_persist_management_interview_exchange", return_value=saved,
        ) as persist, mock.patch.object(server, "_invoke_pipeline") as invoke:
            response = self.post(
                route["objective"],
                process_entry_request={
                    "source": "natural_language",
                    "objective": route["objective"],
                    "project_ref": "ora",
                    "project_confirmed": True,
                },
            )
        self.assertEqual(response.status_code, 200)
        persist.assert_called_once()
        invoke.assert_not_called()
        state = self.service.get_state("server-dialogue-phase-2-2")
        self.assertEqual(state["status"], "interviewing")

    def test_chat_answer_advances_exact_pending_question_without_pipeline(self):
        state = self.service.start_or_resume(
            "server-dialogue-phase-2-2", construction_route(),
        )
        pending_dimension = state["current_question"]["dimension"]
        saved = server._json_response({"status": "ok", "chunk_id": "chunk-answer"})
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-2",
        ), mock.patch.object(
            server, "_persist_management_interview_exchange", return_value=saved,
        ), mock.patch.object(server, "_invoke_pipeline") as invoke:
            response = self.post("The finance team uses it.")
        self.assertEqual(response.status_code, 200)
        invoke.assert_not_called()
        resumed = self.service.get_state("server-dialogue-phase-2-2")
        self.assertEqual(
            resumed["answers"][pending_dimension]["answer"],
            "The finance team uses it.",
        )

    def test_chat_temporary_framework_call_does_not_displace_interview(self):
        state = self.service.start_or_resume(
            "server-dialogue-phase-2-2", construction_route(),
        )
        pending = copy.deepcopy(state["current_question"])
        pipeline_result = json.dumps({
            "status": "ok",
            "conversation_id": "server-dialogue-phase-2-2",
            "chunk_id": "framework-chunk",
        })
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-3",
        ), mock.patch.object(
            server, "_invoke_pipeline", return_value=pipeline_result,
        ) as invoke:
            response = self.post("Run Terrain Mapping on this uncertainty.")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(invoke.call_args.kwargs["framework_selected"],
                         "terrain-mapping")
        governing = invoke.call_args.kwargs["extra_context"]["governing_process"]
        self.assertEqual(governing["run_id"], state["run_id"])
        resumed = self.service.get_state("server-dialogue-phase-2-2")
        self.assertEqual(resumed["current_question"], pending)
        self.assertEqual(resumed["temporary_framework_calls"][0]["status"], "ok")

    def test_hydration_endpoint_returns_restart_safe_state(self):
        state = self.service.start_or_resume(
            "server-dialogue-phase-2-2", construction_route(),
        )
        response = self.client.get(
            "/api/process-interview/server-dialogue-phase-2-2"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["interview"]["run_id"], state["run_id"])

    def test_interview_question_is_saved_through_normal_dialogue_surfaces(self):
        state = self.service.start_or_resume(
            "server-dialogue-phase-2-2", construction_route(),
        )
        with server.app.app_context(), mock.patch.object(
            server, "_save_conversation", return_value="chunk-question",
        ) as save, mock.patch.object(
            memory, "save_turn_spatial_state", return_value=self.sessions,
        ) as save_envelope, mock.patch.object(
            server, "_finalize_pending_submission",
        ) as finalize:
            response = server._persist_management_interview_exchange(
                user_input=construction_route()["objective"],
                state=state,
                history=[],
                panel_id="server-dialogue-phase-2-2",
                tag="",
                submission_id="submission-question",
            )
        self.assertEqual(response.status_code, 200)
        assistant_text = save.call_args.args[1]
        self.assertIn(state["current_question"]["prompt"], assistant_text)
        self.assertIn("Why I’m asking:", assistant_text)
        save_envelope.assert_called_once()
        finalize.assert_called_once_with("submission-question")

    def test_completed_interview_cannot_fall_through_to_ordinary_pipeline(self):
        state = self.service.start_or_resume(
            "server-dialogue-phase-2-2", construction_route(),
        )
        while state["status"] == "interviewing":
            state = self.service.answer(
                "server-dialogue-phase-2-2", "A bounded principal answer.",
            )
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-4",
        ), mock.patch.object(
            server, "_delete_pending_submission",
        ) as delete, mock.patch.object(server, "_invoke_pipeline") as invoke:
            response = self.post("Continue.")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "awaiting_phase_2_3_plan")
        delete.assert_called_once_with("submission-4")
        invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
