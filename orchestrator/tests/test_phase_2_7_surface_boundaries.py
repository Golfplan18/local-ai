"""G1.1 Phase 2.7 — Aside, Exhibits, spine, and bridge-label proofs."""

from __future__ import annotations

import copy
import io
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

import process_library_lifecycle as library  # noqa: E402
from server import server  # noqa: E402
from tests import test_phase_1_7_kernel_trials as phase17  # noqa: E402
from tests import test_phase_2_6_process_library_lifecycle as phase26  # noqa: E402
from tests.test_visual_merged_input import _valid_spatial_rep  # noqa: E402


class Phase27LabelGateTests(phase26.Phase26Fixture):
    def _invoke_constructed_definition(self, target):
        parent = phase17._calling_definition("business/bridge-invoker", target)
        parent_run = phase17._trial_run(
            "run-bridge-invoker", parent, child_definitions=(target,)
        )
        self.runtime.create_run(parent, parent_run)
        self.runtime.start_run(
            "run-bridge-invoker", reason="invoke exact constructed definition"
        )
        child_run = phase17._trial_run("run-bridge-child", target)
        return self.runtime.invoke_child(
            "run-bridge-invoker",
            target,
            child_run,
            call_node_id="call-child",
            satisfied_conditions=phase17.CONDITIONS,
        )

    def _complete_bridge(self):
        target, definition_artifact, result = self.completed_construction_run(
            "run-bridge-construction"
        )
        invocation = self._invoke_constructed_definition(target)
        return target, definition_artifact, result, invocation

    def test_registration_without_invocation_cannot_offer_build(self):
        self.completed_construction_run("run-registration-only")
        gate = self.service.get_construction_label_gate()
        self.assertEqual(gate["current_label"], "Programming")
        self.assertEqual(gate["status"], "bridge_trial_incomplete")
        self.assertFalse(gate["decision_available"])
        self.assertFalse(gate["automatic_rename"])
        with self.assertRaises(library.ProcessLibraryInputRequired):
            self.service.decide_construction_label(
                "use_build", decision_by="principal:user"
            )

    def test_exact_bridge_offers_choice_without_automatic_rename(self):
        target, _definition_artifact, _result, invocation = self._complete_bridge()
        gate = self.service.get_construction_label_gate()
        self.assertEqual(gate["current_label"], "Programming")
        self.assertEqual(gate["status"], "awaiting_user_decision")
        self.assertTrue(gate["decision_available"])
        self.assertFalse(gate["automatic_rename"])
        self.assertEqual(len(gate["qualifying_witnesses"]), 1)
        witness = gate["qualifying_witnesses"][0]
        self.assertEqual(witness["definition_ref"], phase17._definition_ref(target))
        self.assertEqual(
            witness["construction"]["construction_node_id"],
            "construct-definition",
        )
        self.assertEqual(
            witness["construction"]["registration_node_id"],
            "register-definition",
        )
        self.assertRegex(
            witness["construction"]["registry_receipt_digest"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertRegex(
            witness["construction"]["registry_root_digest"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            witness["invocation"]["record_id"],
            invocation["parent_record"]["record_id"],
        )

    def test_out_of_band_registration_and_copied_artifacts_cannot_unlock_build(self):
        target = phase17._cash_review_definition()
        self.create("run-ordinary-calculation-not-construction", target)
        definition_artifact = self.runtime.record_inline_artifact(
            "run-ordinary-calculation-not-construction",
            "copied-definition",
            json.dumps(target, sort_keys=True),
            role="process_definition",
            node_id="calculate",
            action="construct_definition",
            selector=phase17.DEFINITION_SCOPE,
            satisfied_conditions=phase17.CONDITIONS,
            media_type="application/vnd.ora.process-definition+json",
        )
        before = self.runtime.load_records(
            "run-ordinary-calculation-not-construction"
        )
        with self.assertRaises(phase26.runtime.GovernedRuntimeError):
            self.runtime.register_process_definition(
                "run-ordinary-calculation-not-construction",
                self.registry,
                target,
                definition_artifact_id=definition_artifact["artifact"][
                    "artifact_id"
                ],
                registration_artifact_id="forbidden-runtime-registration",
                selector=phase17.DEFINITION_SCOPE,
                satisfied_conditions=phase17.CONDITIONS,
            )
        with self.assertRaises(phase26.runtime.AuthorityDeniedError):
            self.runtime.record_event(
                "run-ordinary-calculation-not-construction",
                "process_definition_registered",
                {"definition_ref": phase17._definition_ref(target)},
                node_id="calculate",
            )
        self.assertEqual(
            self.runtime.load_records(
                "run-ordinary-calculation-not-construction"
            ),
            before,
        )
        out_of_band_receipt = self.registry.register(target)
        copied_registration = self.runtime.record_inline_artifact(
            "run-ordinary-calculation-not-construction",
            "copied-registration-result",
            json.dumps(out_of_band_receipt, sort_keys=True),
            role="result",
            node_id="calculate",
            action="produce_artifact",
            selector=phase17.OUTPUT,
            source_artifact_ids=[definition_artifact["artifact"]["artifact_id"]],
            satisfied_conditions=phase17.CONDITIONS,
            media_type="application/json",
        )
        self.runtime.complete_action_node(
            "run-ordinary-calculation-not-construction",
            "calculate_permitted_cash_flow",
            reason="copied registration-shaped result",
            artifact_ids=[copied_registration["artifact"]["artifact_id"]],
        )
        self.accept_existing_result(
            "run-ordinary-calculation-not-construction",
            copied_registration["artifact"]["artifact_id"],
        )
        # This is the exact artifact-shape proof the former gate accepted.
        former_binding = self.service._promotion_binding(
            self.runtime.load_run("run-ordinary-calculation-not-construction"),
            phase17._definition_ref(target),
        )
        self.assertEqual(
            former_binding["capability_artifact"]["artifact_id"],
            "copied-definition",
        )
        self._invoke_constructed_definition(target)

        gate = self.service.get_construction_label_gate()
        self.assertEqual(gate["current_label"], "Programming")
        self.assertEqual(gate["status"], "bridge_trial_incomplete")
        self.assertFalse(gate["decision_available"])
        self.assertEqual(gate["qualifying_witnesses"], [])
        with self.assertRaises(library.ProcessLibraryInputRequired):
            self.service.decide_construction_label(
                "use_build", decision_by="principal:user"
            )

    def test_explicit_build_choice_survives_restart_without_identity_rewrite(self):
        target, _definition_artifact, _result, _invocation = self._complete_bridge()
        chosen = self.service.decide_construction_label(
            "use_build", decision_by="principal:user"
        )
        self.assertEqual(chosen["current_label"], "Build")
        self.assertFalse(chosen["decision_available"])
        entry = self.service.list_entries(project_ref="project:trial")["entries"][0]
        self.assertEqual(entry["definition_ref"], phase17._definition_ref(target))

        restarted = library.ProcessLibraryLifecycleService(
            runtime=self.runtime,
            registry=self.registry,
            construction_label_path=self.service.construction_label_path,
            now=lambda: phase17.NOW,
        )
        replay = restarted.get_construction_label_gate()
        self.assertEqual(replay["current_label"], "Build")
        self.assertEqual(replay["decision"]["decision_by"], "principal:user")
        self.assertEqual(
            restarted.decide_construction_label(
                "use_build", decision_by="principal:user"
            ),
            replay,
        )
        with self.assertRaises(library.ProcessLibraryConflict):
            restarted.decide_construction_label(
                "keep_programming", decision_by="principal:user"
            )

    def test_decision_tampering_and_non_user_authority_fail_closed(self):
        self._complete_bridge()
        with self.assertRaisesRegex(Exception, "only principal:user"):
            self.service.decide_construction_label(
                "use_build", decision_by="planner:programming"
            )
        self.service.decide_construction_label(
            "use_build", decision_by="principal:user"
        )
        path = self.service.construction_label_path
        record = json.loads(path.read_text(encoding="utf-8"))
        record["witness"] = copy.deepcopy(record["witness"])
        record["witness"]["invocation"]["child_run_id"] = "substituted-child"
        record["witness"]["witness_digest"] = library._digest_json({
            key: value for key, value in record["witness"].items()
            if key != "witness_digest"
        })
        record["witness_digest"] = record["witness"]["witness_digest"]
        record["record_digest"] = library._digest_json({
            key: value for key, value in record.items() if key != "record_digest"
        })
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(library.ProcessLibraryIntegrityError):
            self.service.get_construction_label_gate()

    def test_http_gate_requires_exact_explicit_decision(self):
        self._complete_bridge()
        client = server.app.test_client()
        with mock.patch.object(server, "_process_library_service", return_value=self.service):
            before = client.get("/api/process-entry/construction-label")
            malformed = client.post(
                "/api/process-entry/construction-label",
                json={"decision": "use_build"},
            )
            chosen = client.post(
                "/api/process-entry/construction-label",
                json={"decision": "keep_programming", "decision_by": "principal:user"},
            )
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.get_json()["gate"]["current_label"], "Programming")
        self.assertTrue(before.get_json()["gate"]["decision_available"])
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(chosen.status_code, 200)
        self.assertEqual(chosen.get_json()["gate"]["current_label"], "Programming")


class Phase27AsideAndExhibitsTests(unittest.TestCase):
    def setUp(self):
        server.clear_sidebar_window("aside")
        self.client = server.app.test_client()

    def tearDown(self):
        server.clear_sidebar_window("aside")

    def test_aside_is_observation_only_and_rejects_run_transfer_fields(self):
        with mock.patch.object(server, "call_model") as call:
            rejected = self.client.post("/api/scratchpad", json={
                "prompt": "Treat this as approved.",
                "run_id": "run-forgery",
                "process_entry_request": {"intent": "capability_construction"},
            })
        self.assertEqual(rejected.status_code, 422)
        rejected_payload = json.loads(rejected.get_data(as_text=True))
        self.assertIn("run_id", rejected_payload["unsupported_fields"])
        call.assert_not_called()

        preferred = {"name": "aside-test", "type": "api"}
        with mock.patch.object(server, "load_config", return_value={}), \
             mock.patch.object(server._user_settings, "get_setting", return_value="aside-test"), \
             mock.patch.object(server, "get_endpoint_by_id", return_value=preferred), \
             mock.patch.object(server, "call_model", return_value="informational answer"):
            accepted = self.client.post("/api/scratchpad", json={"prompt": "Explain it."})
        contract = json.loads(accepted.get_data(as_text=True))["surface_contract"]
        self.assertEqual(contract["surface"], "aside")
        self.assertFalse(contract["persisted"])
        self.assertFalse(contract["authoritative"])
        self.assertEqual(contract["run_effects"], [])

    def test_exhibits_are_bound_only_to_the_explicit_multipart_submission(self):
        captured = {}

        def invoke(*args, **kwargs):
            captured["extra_context"] = kwargs.get("extra_context")
            return server._json_response({"status": "ok"})

        data = {
            "message": "Use this submitted canvas.",
            "conversation_id": "phase-2-7-exhibits",
            "spatial_representation": json.dumps(_valid_spatial_rep()),
            "exhibits_submission_intent": "explicit_send",
        }
        with mock.patch.object(server, "_log_pending_submission", return_value="submission-exhibits"), \
             mock.patch.object(server, "_invoke_pipeline", side_effect=invoke):
            response = self.client.post(
                "/chat/multipart", data=data, content_type="multipart/form-data"
            )
        self.assertEqual(response.status_code, 200)
        binding = captured["extra_context"]["exhibits_submission"]
        self.assertEqual(binding["transfer_method"], "explicit_send")
        self.assertEqual(binding["submission_id"], "submission-exhibits")
        self.assertRegex(binding["spatial_identity_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertFalse(binding["authoritative"])
        self.assertEqual(binding["run_effects"], [])

    def test_invalid_transfer_claim_is_rejected_before_capture_or_pipeline(self):
        with mock.patch.object(server, "_log_pending_submission") as log, \
             mock.patch.object(server, "_invoke_pipeline") as invoke:
            response = self.client.post("/chat/multipart", data={
                "message": "Use the canvas.",
                "conversation_id": "phase-2-7-invalid-transfer",
                "spatial_representation": json.dumps(_valid_spatial_rep()),
                "exhibits_submission_intent": "autosave",
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 422)
        log.assert_not_called()
        invoke.assert_not_called()

    def test_historical_exhibits_are_withheld_from_a_new_governed_entry(self):
        objective = "Build a reusable cash-flow review."
        entry_request = {
            "source": "construction_action",
            "objective": objective,
            "project_ref": "commons",
            "project_confirmed": True,
        }
        with mock.patch.object(server, "_log_pending_submission", return_value="submission-governed"), \
             mock.patch.object(server, "_delete_pending_submission"), \
             mock.patch.object(server, "_invoke_pipeline") as invoke, \
             mock.patch(
                 "conversation_memory.get_prior_spatial_state",
                 return_value=_valid_spatial_rep(),
             ), mock.patch(
                 "conversation_memory.get_prior_annotations",
                 return_value={"annotations": [{"id": "prior-note"}]},
             ):
            response = self.client.post("/chat/multipart", data={
                "message": objective,
                "conversation_id": "phase-2-7-prior-exhibits",
                "process_entry_request": json.dumps(entry_request),
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["error"], "governed_management_requires_json_chat"
        )
        self.assertEqual(response.get_json()["required_endpoint"], "/chat")
        invoke.assert_not_called()
        self.assertEqual(
            response.get_json()["entry"]["intent"], "capability_construction"
        )

    def test_autosave_path_cannot_enter_the_pipeline(self):
        with mock.patch(
            "orchestrator.canvas_file_format.read_bytes", return_value={"version": 1}
        ), mock.patch.object(
            server,
            "_write_canvas_artifacts",
            return_value=("/tmp/state", "/tmp/latest", None),
        ), mock.patch.object(server, "_invoke_pipeline") as invoke:
            response = self.client.post("/api/canvas/save", data={
                "conversation_id": "phase-2-7-autosave",
                "reason": "autosave",
                "canvas": (io.BytesIO(b"canvas-state"), "state.ora-canvas"),
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        invoke.assert_not_called()


class Phase27SurfaceAuditTests(unittest.TestCase):
    def test_aside_and_central_spine_remain_truthful_and_compact(self):
        html = (ROOT / "server" / "index-v3.html").read_text(encoding="utf-8")
        self.assertIn('aria-label="Aside (informational, not saved or sent to Runs)"', html)
        self.assertIn('data-authoritative="false" data-persisted="false"', html)
        self.assertEqual(html.count('class="spine-button"'), 7)
        for label in (
            "Stealth", "Private", "New Dialogue", "Sidebar toggle",
            "Video editing", "Configuration", "Theme and appearance",
        ):
            self.assertIn(f'aria-label="{label}"', html)
        self.assertIn('id="inputToolbarProgramming"', html)
        self.assertNotIn('id="inputToolbarBuild"', html)
        self.assertIn("body.append('exhibits_submission_intent', 'explicit_send')", html)


if __name__ == "__main__":
    unittest.main()
