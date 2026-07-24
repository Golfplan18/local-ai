"""G1.18 proofs for G1.1-native Process authoring and execution."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
os.environ.setdefault("ORA_HOME", str(ROOT))
VAULT = Path(os.environ.get("ORA_VAULT") or (Path.home() / "Documents" / "vault"))
VAULT_ORA = VAULT / "Projects" / "Ora"

from orchestrator import process_automation as automation  # noqa: E402
from orchestrator import process_automation_worker as worker_module  # noqa: E402
from orchestrator.governed_process_runtime import (  # noqa: E402
    AuthorityDeniedError,
    FinalReviewRequired,
    GovernedProcessRuntime,
    GovernedRuntimeError,
)
from orchestrator.process_definition_registry import ProcessDefinitionRegistry  # noqa: E402
from orchestrator.process_entry_routing import route_process_entry  # noqa: E402
from orchestrator.process_library_lifecycle import ProcessLibraryLifecycleService  # noqa: E402
from orchestrator.process_management_interview import ManagementInterviewService  # noqa: E402
from server import server  # noqa: E402


ANSWERS = {
    "intended_result": "A classified email summary and unsent reply draft should exist.",
    "affected_parties": "The principal uses it and the email sender is affected.",
    "inputs_outputs": "It reads one email and produces a classification, summary, and unsent draft.",
    "reuse": "This is a repeatable capability for future Runs.",
    "initiation": "A person starts it manually on demand.",
    "authority": "Ora may classify and summarize but must ask before preparing the draft.",
    "exceptions": "If input is missing, stop and return to me.",
    "permissions": "Ora may read the supplied email but may not send or change external systems.",
    "evidence": "Accept when every output is present and the draft is marked unsent.",
    "stopping": "Stop before drafting and ask me; stop on missing evidence.",
}


def _profile_resolution(**_kwargs):
    selected = {
        "source": "global",
        "name": "test-profile",
        "runtime_name": "test-profile",
        "digest": "sha256:" + "a" * 64,
        "health": {"status": "available", "reason": "test"},
    }
    return {"selected": selected, "chain": [copy.deepcopy(selected)]}


def _injected_worker(request):
    return worker_module.execute(request)


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise AssertionError(f"unterminated frontmatter: {path}")
        text = text[end + 5:]
    return text.lstrip("\n").rstrip()


class ProcessAutomationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = GovernedProcessRuntime(self.root / "runs")
        self.interview = ManagementInterviewService(
            runtime=self.runtime,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
        )
        route = route_process_entry({
            "source": "natural_language",
            "objective": "Build a reusable email processing capability.",
            "project_ref": "ora",
            "project_confirmed": True,
        })
        state = self.interview.start_or_resume("dialogue-g1-18", route)
        while state["status"] == "interviewing":
            question = state["current_question"]
            state = self.interview.answer(
                state["dialogue_ref"],
                ANSWERS[question["dimension"]],
                question_id=question["question_id"],
                idempotency_key=f"answer:{question['dimension']}",
            )
        self.interview_state = state
        self.registry = ProcessDefinitionRegistry(self.root / "registry")
        self.library = ProcessLibraryLifecycleService(
            runtime=self.runtime,
            registry_root=self.root / "registry",
            seed_definitions=[],
        )
        self.worker = automation.IsolatedProcessWorker(runner=_injected_worker)
        self.profile_patch = mock.patch.object(
            automation, "resolve_effective_profile", side_effect=_profile_resolution,
        )
        self.project_patch = mock.patch.object(
            automation.project_meta, "read_project_meta", return_value={},
        )
        self.profile_patch.start()
        self.project_patch.start()
        self.addCleanup(self.profile_patch.stop)
        self.addCleanup(self.project_patch.stop)
        self.service = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=self.worker,
        )

    def author(self):
        proposed = self.service.propose(
            "dialogue-g1-18",
            idempotency_key="proposal:email:1",
            blueprint=automation.email_processing_blueprint("ora"),
        )
        approved = self.service.approve_and_register(
            "dialogue-g1-18",
            proposal_id=proposed["proposal"]["proposal_id"],
            proposal_digest=proposed["proposal"]["proposal_digest"],
            decision_by="principal:user",
        )
        return approved

    @staticmethod
    def inputs():
        return {
            "message_id": "message-001",
            "sender": "Alex",
            "subject": "Urgent invoice",
            "body": "Please review the overdue invoice today.",
        }

    def begin(self, definition_ref):
        return self.service.begin_run(
            definition_ref=definition_ref,
            project_ref="ora",
            inputs=self.inputs(),
            idempotency_key="run:email:1",
        )


class ProcessAutomationContractTests(unittest.TestCase):
    def test_compiled_definition_uses_g1_1_schema_and_keeps_profiles_out_of_definition(self):
        definition = automation.compile_blueprint(
            automation.email_processing_blueprint("ora")
        )
        self.assertEqual(definition["definition_id"], "user/email-processing")
        self.assertEqual(definition["scope"], {"kind": "project", "selector": "ora"})
        for forbidden in ("trigger", "model_profile", "style", "persona", "mindspec"):
            self.assertNotIn(forbidden, definition)
        metadata = definition["output_schema"]["x-ora-process"]
        self.assertFalse(metadata["external_effects"])
        self.assertFalse(metadata["triggers"])
        self.assertNotIn("persona", metadata)
        self.assertTrue(all(
            node.get("external_effect") is False
            for node in definition["graph"]["nodes"] if node["kind"] == "action"
        ))

    def test_blueprint_rejects_external_operations_and_parallel_engine_fields(self):
        for mutation in (
            lambda value: value["stages"][0].update(operation="send_email"),
            lambda value: value.update(trigger={"kind": "schedule"}),
            lambda value: value.update(persona="assistant"),
            lambda value: value.update(runtime="milestone_executor"),
        ):
            blueprint = automation.email_processing_blueprint("ora")
            mutation(blueprint)
            with self.subTest(keys=set(blueprint)), self.assertRaises(
                automation.ProcessAutomationInputRequired
            ):
                automation.validate_blueprint(blueprint)

    def test_blueprint_rejects_ambiguous_or_unproduced_output_contracts(self):
        duplicate = automation.email_processing_blueprint("ora")
        duplicate["stages"][1]["operation"] = duplicate["stages"][0]["operation"]
        with self.assertRaisesRegex(
            automation.ProcessAutomationInputRequired, "operation .* duplicated"
        ):
            automation.validate_blueprint(duplicate)
        missing = automation.email_processing_blueprint("ora")
        missing["output_schema"]["properties"]["audit"] = {"type": "string"}
        missing["output_schema"]["required"].append("audit")
        with self.assertRaisesRegex(
            automation.ProcessAutomationInputRequired, "no producing action"
        ):
            automation.validate_blueprint(missing)

    def test_schema_constraints_are_enforced_and_unknown_keywords_fail_closed(self):
        blueprint = automation.email_processing_blueprint("ora")
        blueprint["input_schema"]["properties"]["sender"].update({
            "enum": ["Alex", "Morgan"],
        })
        blueprint["input_schema"]["properties"]["body"].update({
            "minLength": 10,
        })
        normalized = automation.validate_blueprint(blueprint)
        with self.assertRaisesRegex(
            automation.ProcessAutomationInputRequired, "inputs.sender.*enum"
        ):
            automation._validate_instance(
                {
                    "message_id": "m", "sender": "Wrong", "subject": "Invoice",
                    "body": "Payment is overdue.",
                },
                normalized["input_schema"],
                "inputs",
            )
        with self.assertRaisesRegex(
            automation.ProcessAutomationInputRequired, "inputs.body.*minLength"
        ):
            automation._validate_instance(
                {
                    "message_id": "m", "sender": "Alex", "subject": "Invoice",
                    "body": "short",
                },
                normalized["input_schema"],
                "inputs",
            )
        invalid = automation.email_processing_blueprint("ora")
        invalid["input_schema"]["properties"]["sender"]["format"] = "email"
        with self.assertRaisesRegex(
            automation.ProcessAutomationInputRequired, "unsupported.*format"
        ):
            automation.validate_blueprint(invalid)
        unassessable = automation.email_processing_blueprint("ora")
        unassessable["acceptance_criteria"] = ["must exactly equal EXPECTED"]
        with self.assertRaisesRegex(
            automation.ProcessAutomationInputRequired, "unassessable"
        ):
            automation.validate_blueprint(unassessable)

    def test_verifier_fails_wrong_partial_and_unassessable_criteria(self):
        base = {
            "schema_version": automation.WORKER_SCHEMA_VERSION,
            "kind": "verify",
            "operation": "verify.process_result",
            "instruction": "Verify every exact criterion.",
            "inputs": {},
            "prior_outputs": {"result": "WRONG", "prefix": "EXPECTED prefix"},
            "expected_output_key": "verification",
            "acceptance_criteria": [
                {
                    "criterion_id": "prefix-present",
                    "description": "The prefix field starts with EXPECTED.",
                    "kind": "field_prefix",
                    "field": "prefix",
                    "expected": "EXPECTED",
                },
                {
                    "criterion_id": "exact-result",
                    "description": "The result field must exactly equal EXPECTED.",
                    "kind": "field_equals",
                    "field": "result",
                    "expected": "EXPECTED",
                },
            ],
            "execution_context": {},
        }
        partial = worker_module.execute(base)
        self.assertEqual(partial["status"], "FAIL")
        self.assertFalse(partial["output"]["verification"])
        self.assertEqual(
            [item["satisfied"] for item in partial["output"]["criteria"]],
            [True, False],
        )
        forged = copy.deepcopy(partial)
        forged["status"] = "PASS"
        forged["output"]["verification"] = True
        for assessment in forged["output"]["criteria"]:
            assessment["satisfied"] = True
        with self.assertRaisesRegex(
            automation.ProcessAutomationIntegrityError,
            "mechanical reevaluation",
        ):
            automation.ProcessAutomationService._validated_criterion_assessments(
                forged, base["acceptance_criteria"], base,
            )
        unsupported = copy.deepcopy(base)
        unsupported["acceptance_criteria"] = ["must exactly equal EXPECTED"]
        refused = worker_module.execute(unsupported)
        self.assertEqual(refused["status"], "FAIL")
        self.assertFalse(refused["output"]["verification"])

    def test_email_proof_contains_exact_human_checkpoint_before_unsent_draft(self):
        definition = automation.compile_blueprint(
            automation.email_processing_blueprint("ora")
        )
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        self.assertEqual(nodes["summarize"]["next_node_id"], "draft-approval")
        self.assertEqual(nodes["draft-approval"]["on_approved_node_id"], "draft")
        self.assertEqual(nodes["draft"]["operation"], "email.draft")
        operations = {
            node["operation"] for node in definition["graph"]["nodes"]
            if node["kind"] == "action"
        }
        self.assertFalse(any("send" in operation for operation in operations))

    def test_real_worker_process_binds_request_and_has_no_dispatcher_surface(self):
        isolated = automation.IsolatedProcessWorker(timeout_seconds=20)
        request = {
            "schema_version": automation.WORKER_SCHEMA_VERSION,
            "kind": "execute",
            "operation": "email.classify",
            "instruction": "Classify only.",
            "inputs": {
                "message_id": "m", "sender": "a", "subject": "Invoice",
                "body": "Payment due.",
            },
            "prior_outputs": {},
            "expected_output_key": "classification",
            "acceptance_criteria": ["grounded"],
            "execution_context": {"config_name": None, "style_prompt": ""},
        }
        result = isolated.invoke(request)
        self.assertEqual(result["boundary"], "separate_no_tools_process")
        self.assertEqual(result["request_digest"], automation._digest_json(request))
        source = (ORCH / "process_automation_worker.py").read_text(encoding="utf-8")
        for forbidden in ("execute_tool", "dispatcher_dispatch", "subprocess", "os.system"):
            self.assertNotIn(forbidden, source)

    def test_canonical_guides_match_runtime_and_record_exact_g1_1_reconciliation(self):
        technical = _body(VAULT_ORA / "Reference — Ora Technical Documentation.md")
        guide = _body(VAULT_ORA / "Guide — Using Ora.md")
        evidence = (ROOT / "outputs" / "g1-18" / "closeout-evidence.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(technical, _body(ROOT / "docs" / "technical-documentation.md"))
        self.assertEqual(guide, _body(ROOT / "docs" / "user-guide.md"))
        for token in (
            "## 19. G1.18 Reusable Process Authoring and Isolated Execution",
            "execute its graph through `GovernedProcessRuntime`",
            "Trigger binding and scheduling belong to G1.19",
            "strict definition root remains unchanged",
            "G1.20 owns the additional tracking and telemetry UI",
            "Persona is not a dependency or a placeholder field",
            "**UNSENT DRAFT**",
        ):
            self.assertIn(token, technical)
        for token in (
            "### Author a reusable Process",
            "### Run a reusable Process manually",
            "I confirm this Run belongs to Project",
            "It cannot send the draft",
        ):
            self.assertIn(token, guide)
        for token in (
            "## 2026-07-24 gate correction",
            "Wrong, partial, contradictory, or fabricated success cannot authorize `ACCEPT`",
            "Restart resumes only verification",
            "Unsupported keywords fail during authoring",
            "# 32 passed, 12 subtests passed; exit 0",
            "# 374 passed, 201 subtests passed; exit 0",
        ):
            self.assertIn(token, evidence)

    def test_tracker_program_and_registry_preserve_gate_boundaries(self):
        tracker = (VAULT_ORA / "Working — Ora Setup and Refinement.md").read_text(
            encoding="utf-8"
        )
        program = (VAULT_ORA / "Working — Framework — Ora Project Integration Program.md").read_text(
            encoding="utf-8"
        )
        registry = (VAULT_ORA / "Registry — Ora Overview and Document Registry.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((tracker, program, registry))
        for token in (
            "G1.17 is user-deferred",
            "without an architecture choice",
            "G1.18’s bounded correction is implemented and awaits independent re-judgment",
            "G1.19 and G1.20 remain unauthorized",
            "no Trigger, Persona, outbound effect, alternate engine, or G1.20 telemetry",
        ):
            self.assertIn(token, combined)
        self.assertNotIn("G1.17 is complete", combined)
        self.assertNotIn("G1.18 is complete", combined)


class ProcessAutomationAuthoringTests(ProcessAutomationFixture):
    def test_authoring_and_worker_event_families_cannot_be_forged_as_observations(self):
        run_id = self.interview_state["run_id"]
        before = self.runtime.load_records(run_id)
        for event_type in (
            automation.AUTHORING_PROPOSED_EVENT,
            automation.AUTHORING_REVISION_EVENT,
            "isolated_process_step_completed",
            "isolated_process_verification_started",
            "isolated_process_verification_failed",
            "isolated_process_verification_completed",
        ):
            with self.subTest(event_type=event_type), self.assertRaises(
                AuthorityDeniedError
            ):
                self.runtime.record_event(run_id, event_type, {"forged": True})
        self.assertEqual(self.runtime.load_records(run_id), before)

    def test_real_management_interview_constructs_registers_and_promotes_exact_definition(self):
        approved = self.author()
        self.assertEqual(approved["status"], "available")
        self.assertEqual(approved["management_run_id"], self.interview_state["run_id"])
        self.assertEqual(approved["construction"]["run_state"], "completed")
        self.assertEqual(
            approved["construction"]["lifecycle"]["closure"]["disposition"],
            "promote",
        )
        ref = approved["proposal"]["definition_ref"]
        self.assertEqual(
            self.registry.resolve(ref["definition_id"], ref["version"], ref["digest"]),
            approved["proposal"]["definition"],
        )
        entry = self.library.list_entries(project_ref="ora")["entries"][0]
        self.assertTrue(entry["automated_execution_available"])
        self.assertFalse(entry["manual_invocation_available"])
        self.assertEqual(entry["input_schema"], approved["proposal"]["definition"]["input_schema"])
        events = self.runtime.load_records(approved["construction"]["run_id"])
        event_types = [(record.get("event") or {}).get("event_type") for record in events]
        self.assertIn("process_definition_registered", event_types)
        self.assertIn("lifecycle_disposition_recorded", event_types)

    def test_proposal_and_approval_are_idempotent_but_stale_identity_fails(self):
        first = self.service.propose(
            "dialogue-g1-18",
            idempotency_key="proposal:email:1",
            blueprint=automation.email_processing_blueprint("ora"),
        )
        retry = self.service.propose(
            "dialogue-g1-18",
            idempotency_key="proposal:email:1",
            blueprint=automation.email_processing_blueprint("ora"),
        )
        self.assertEqual(retry, first)
        with self.assertRaises(automation.ProcessAutomationConflict):
            self.service.approve_and_register(
                "dialogue-g1-18",
                proposal_id=first["proposal"]["proposal_id"],
                proposal_digest="sha256:" + "f" * 64,
                decision_by="principal:user",
            )
        approved = self.service.approve_and_register(
            "dialogue-g1-18",
            proposal_id=first["proposal"]["proposal_id"],
            proposal_digest=first["proposal"]["proposal_digest"],
            decision_by="principal:user",
        )
        replay = self.service.approve_and_register(
            "dialogue-g1-18",
            proposal_id=first["proposal"]["proposal_id"],
            proposal_digest=first["proposal"]["proposal_digest"],
            decision_by="principal:user",
        )
        self.assertEqual(replay["status"], "available")
        self.assertEqual(replay["construction"]["run_id"], approved["construction"]["run_id"])

    def test_concurrent_proposal_delivery_persists_one_authoritative_identity(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def deliver():
            try:
                barrier.wait()
                results.append(self.service.propose(
                    "dialogue-g1-18", idempotency_key="proposal:concurrent:1",
                    blueprint=automation.email_processing_blueprint("ora"),
                ))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=deliver) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(errors)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["proposal"]["proposal_id"], results[1]["proposal"]["proposal_id"])
        records = self.runtime.load_records(self.interview_state["run_id"])
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == automation.AUTHORING_PROPOSED_EVENT
            for record in records
        ), 1)

    def test_nonprincipal_cannot_approve_and_revision_prevents_approval(self):
        proposed = self.service.propose(
            "dialogue-g1-18", idempotency_key="proposal:email:1",
            blueprint=automation.email_processing_blueprint("ora"),
        )
        with self.assertRaises(automation.ProcessAutomationConflict):
            self.service.approve_and_register(
                "dialogue-g1-18",
                proposal_id=proposed["proposal"]["proposal_id"],
                proposal_digest=proposed["proposal"]["proposal_digest"],
                decision_by="reviewer:other",
            )
        revised = self.service.request_revision(
            "dialogue-g1-18",
            proposal_id=proposed["proposal"]["proposal_id"],
            reason="Add a clearer draft checkpoint.",
        )
        self.assertEqual(revised["status"], "revision_requested")
        with self.assertRaisesRegex(
            automation.ProcessAutomationConflict, "changed proposal identity"
        ):
            self.service.propose(
                "dialogue-g1-18", idempotency_key="proposal:email:unchanged",
                blueprint=automation.email_processing_blueprint("ora"),
            )
        with self.assertRaises(automation.ProcessAutomationConflict):
            self.service.approve_and_register(
                "dialogue-g1-18",
                proposal_id=proposed["proposal"]["proposal_id"],
                proposal_digest=proposed["proposal"]["proposal_digest"],
                decision_by="principal:user",
            )


class ProcessAutomationExecutionTests(ProcessAutomationFixture):
    def test_run_binds_existing_profile_precedence_without_persona_or_trigger_fields(self):
        authored = self.author()
        state = self.service.begin_run(
            definition_ref=authored["proposal"]["definition_ref"],
            project_ref="ora", inputs=self.inputs(), idempotency_key="run:profiles:1",
            process_profile="process-profile",
            step_profiles={"email.summarize": "step-profile"},
            one_run_profile="one-run-profile",
        )
        run = self.runtime.load_run(state["run_id"])
        context = run["input_bindings"]["execution_context"]
        self.assertNotIn("persona", context)
        self.assertNotIn("trigger", context)
        self.assertNotIn("persona", state)
        self.assertNotIn("trigger", state)
        calls = automation.resolve_effective_profile.call_args_list
        self.assertEqual(len(calls), 3)
        by_step = {
            call.kwargs.get("step_profile"): call.kwargs for call in calls
        }
        self.assertIn("step-profile", by_step)
        for call in calls:
            self.assertEqual(call.kwargs["project_nexus"], "ora")
            self.assertEqual(call.kwargs["process_profile"], "process-profile")
            self.assertEqual(call.kwargs["one_run_profile"], "one-run-profile")

    def test_full_email_proof_runs_only_through_real_worker_processes(self):
        authored = self.author()
        self.service.worker = automation.IsolatedProcessWorker(timeout_seconds=20)
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        completed = self.service.resolve_checkpoint(
            paused["run_id"], outcome="approved", decision_by="principal:user",
        )
        self.assertEqual(completed["run_state"], "completed")
        records = self.runtime.load_records(completed["run_id"])
        boundaries = [
            record["event"]["details"]["worker_boundary"]
            for record in records
            if (record.get("event") or {}).get("event_type") in {
                "isolated_process_step_completed",
                "isolated_process_verification_completed",
            }
        ]
        self.assertEqual(boundaries, ["separate_no_tools_process"] * 4)

    def test_artifact_alone_cannot_complete_an_automation_action(self):
        authored = self.author()
        state = self.begin(authored["proposal"]["definition_ref"])
        artifact = self.service._record_content_artifact(
            state["run_id"], "forged-step-output", {"classification": "normal:general"},
            role="working", node_id="classify", source_artifact_ids=[],
        )
        with self.assertRaisesRegex(
            GovernedRuntimeError, "runtime-issued isolated execution record"
        ):
            self.runtime.complete_action_node(
                state["run_id"], "email.classify",
                reason="Attempt to skip the isolated worker",
                completion_details={
                    "worker_boundary": "separate_no_tools_process",
                    "worker_request_digest": "sha256:" + "1" * 64,
                    "worker_response_digest": "sha256:" + "2" * 64,
                    "execution_context_binding_digest": (
                        self.runtime.load_run(state["run_id"])["input_bindings"]
                        ["execution_context"]["binding_digest"]
                    ),
                },
                artifact_ids=[artifact["artifact_id"]],
            )

    def test_fabricated_evidence_cannot_authorize_automation_acceptance(self):
        authored = self.author()
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        self.runtime.resume_run(paused["run_id"])
        self.runtime.resolve_human_checkpoint(
            paused["run_id"], "approved", decision_by="principal:user",
            reason="Advance only to exercise the review boundary",
        )
        definition = self.runtime.load_definition(paused["run_id"])
        draft_node = next(
            node for node in definition["graph"]["nodes"]
            if node["node_id"] == "draft"
        )
        self.service._execute_action(paused["run_id"], definition, draft_node)
        result = automation._latest_result_artifact(self.runtime, paused["run_id"])
        self.assertIsNotNone(result)
        forged = self.runtime.record_inline_artifact(
            paused["run_id"], "forged-verification", "claimed pass",
            role="evidence", node_id="final-review", action="record_evidence",
            selector=automation.OUTPUT_SELECTOR,
            source_artifact_ids=[result["artifact_id"]],
            satisfied_conditions=automation.CONDITIONS,
            media_type="text/plain",
        )["artifact"]
        with self.assertRaisesRegex(FinalReviewRequired, "runtime-issued"):
            self.runtime.record_final_review(
                paused["run_id"], artifact_id=result["artifact_id"],
                evidence_id="result_verified",
                evidence_artifact_id=forged["artifact_id"], outcome="PASS",
                reviewer_id="reviewer:forged", independent=True,
                satisfied_conditions=automation.CONDITIONS,
            )

    def test_email_process_stops_at_checkpoint_then_completes_with_authenticated_result(self):
        authored = self.author()
        state = self.begin(authored["proposal"]["definition_ref"])
        state = self.service.execute(state["run_id"])
        self.assertEqual(state["status"], "awaiting_human_checkpoint")
        self.assertEqual(state["current_node"]["node_id"], "draft-approval")
        self.assertEqual(state["attempt"], 2)
        records = self.runtime.load_records(state["run_id"])
        self.assertGreaterEqual(sum(
            (record.get("event") or {}).get("event_type") == "checkpoint_created"
            for record in records
        ), 3)
        completed = self.service.resolve_checkpoint(
            state["run_id"], outcome="approved", decision_by="principal:user",
        )
        self.assertEqual(completed["run_state"], "completed")
        result = completed["result"]["content"]
        self.assertEqual(set(result), {"classification", "summary", "draft"})
        self.assertTrue(result["draft"].startswith("UNSENT DRAFT"))
        serialized = json.dumps(self.runtime.load_records(state["run_id"]))
        self.assertNotIn('"send"', serialized)
        self.assertNotIn("external_action_authorized", serialized)
        before_retry = self.runtime.load_records(state["run_id"])
        replay = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        self.assertEqual(replay["state_digest"], completed["state_digest"])
        self.assertEqual(self.runtime.load_records(state["run_id"]), before_retry)

    def test_denied_checkpoint_stops_without_preparing_or_accepting_a_result(self):
        authored = self.author()
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        stopped = self.service.resolve_checkpoint(
            paused["run_id"], outcome="denied", decision_by="principal:user",
        )
        self.assertEqual(stopped["run_state"], "blocked")
        self.assertIsNone(stopped["result"])
        records = self.runtime.load_records(stopped["run_id"])
        self.assertFalse(any(
            record["node_id"] == "draft"
            for record in records
        ))
        self.assertFalse(any(
            (record.get("transition") or {}).get("directive") == "ACCEPT"
            for record in records
        ))

    def test_checkpoint_and_execution_resume_after_service_restart(self):
        authored = self.author()
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        restarted = automation.ProcessAutomationService(
            runtime=GovernedProcessRuntime(self.root / "runs"),
            registry=ProcessDefinitionRegistry(self.root / "registry"),
            management_interview=ManagementInterviewService(
                runtime=GovernedProcessRuntime(self.root / "runs"),
                sessions_root=self.root / "sessions",
                repository_root=ROOT,
            ),
            library=ProcessLibraryLifecycleService(
                runtime=GovernedProcessRuntime(self.root / "runs"),
                registry_root=self.root / "registry",
                seed_definitions=[],
            ),
            worker=self.worker,
        )
        completed = restarted.resolve_checkpoint(
            paused["run_id"], outcome="approved", decision_by="principal:user",
        )
        self.assertEqual(completed["run_state"], "completed")
        self.assertEqual(completed["result"]["content"]["classification"], "urgent:finance")

    def test_failure_is_persisted_and_retry_does_not_replay_completed_steps(self):
        authored = self.author()
        calls = []

        def flaky(request):
            calls.append(request["operation"])
            if request["operation"] == "email.classify" and calls.count("email.classify") == 1:
                raise RuntimeError("worker unavailable")
            return worker_module.execute(request)

        self.service.worker = automation.IsolatedProcessWorker(runner=flaky)
        state = self.begin(authored["proposal"]["definition_ref"])
        with self.assertRaises(automation.ProcessAutomationWorkerError):
            self.service.execute(state["run_id"])
        failed = self.service.run_state(state["run_id"])
        self.assertEqual(failed["status"], "paused_after_failure")
        paused = self.service.execute(state["run_id"])
        self.assertEqual(paused["status"], "awaiting_human_checkpoint")
        self.assertEqual(calls.count("email.classify"), 2)
        self.assertEqual(calls.count("email.summarize"), 1)
        completed = self.service.resolve_checkpoint(
            paused["run_id"], outcome="approved", decision_by="principal:user",
        )
        self.assertEqual(completed["run_state"], "completed")
        self.assertEqual(calls.count("email.draft"), 1)

    def test_wrong_or_partially_satisfied_criteria_cannot_authorize_accept(self):
        blueprint = automation.email_processing_blueprint("ora")
        blueprint["acceptance_criteria"] = [
            {
                "criterion_id": "draft-boundary",
                "description": "The draft is explicitly unsent.",
                "kind": "field_prefix",
                "field": "draft",
                "expected": "UNSENT DRAFT",
            },
            {
                "criterion_id": "exact-classification",
                "description": "The classification exactly matches the reviewed value.",
                "kind": "field_equals",
                "field": "classification",
                "expected": "EXPECTED",
            },
        ]
        proposed = self.service.propose(
            "dialogue-g1-18", idempotency_key="proposal:wrong-result:1",
            blueprint=blueprint,
        )
        authored = self.service.approve_and_register(
            "dialogue-g1-18",
            proposal_id=proposed["proposal"]["proposal_id"],
            proposal_digest=proposed["proposal"]["proposal_digest"],
            decision_by="principal:user",
        )
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        stopped = self.service.resolve_checkpoint(
            paused["run_id"], outcome="approved", decision_by="principal:user",
        )
        self.assertEqual(stopped["run_state"], "blocked")
        records = self.runtime.load_records(stopped["run_id"])
        self.assertFalse(any(
            (record.get("transition") or {}).get("directive") == "ACCEPT"
            for record in records
        ))
        reviews = [
            record for record in records
            if (record.get("event") or {}).get("event_type") == "final_review_completed"
        ]
        self.assertTrue(reviews)
        self.assertTrue(all(
            review["event"]["details"]["outcome"] == "FAIL"
            for review in reviews
        ))

    def test_output_schema_constraint_failure_stops_before_verification(self):
        blueprint = automation.email_processing_blueprint("ora")
        blueprint["output_schema"]["properties"]["classification"]["enum"] = [
            "EXPECTED",
        ]
        proposed = self.service.propose(
            "dialogue-g1-18", idempotency_key="proposal:output-schema:1",
            blueprint=blueprint,
        )
        authored = self.service.approve_and_register(
            "dialogue-g1-18",
            proposal_id=proposed["proposal"]["proposal_id"],
            proposal_digest=proposed["proposal"]["proposal_digest"],
            decision_by="principal:user",
        )
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        with self.assertRaises(automation.ProcessAutomationWorkerError):
            self.service.resolve_checkpoint(
                paused["run_id"], outcome="approved", decision_by="principal:user",
            )
        failed = self.service.run_state(paused["run_id"])
        self.assertEqual(failed["status"], "paused_after_failure")
        self.assertEqual(failed["current_node"]["node_id"], "draft")
        records = self.runtime.load_records(paused["run_id"])
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type")
            == "isolated_process_verification_started"
            for record in records
        ))
        self.assertFalse(any(
            (record.get("transition") or {}).get("directive") == "ACCEPT"
            for record in records
        ))

    def test_verification_failure_restart_retry_and_exhaustion_are_persisted(self):
        authored = self.author()

        def unavailable_verifier(request):
            if request["kind"] == "verify":
                raise RuntimeError("verifier unavailable")
            return worker_module.execute(request)

        self.service.worker = automation.IsolatedProcessWorker(
            runner=unavailable_verifier,
        )
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        with self.assertRaises(automation.ProcessAutomationWorkerError):
            self.service.resolve_checkpoint(
                paused["run_id"], outcome="approved", decision_by="principal:user",
            )
        failed = self.service.run_state(paused["run_id"])
        self.assertEqual(failed["status"], "paused_after_failure")
        self.assertEqual(failed["current_node"]["node_id"], "final-review")
        records = self.runtime.load_records(paused["run_id"])
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "isolated_process_verification_started"
            for record in records
        ), 1)
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "isolated_process_verification_failed"
            for record in records
        ), 1)

        restarted = automation.ProcessAutomationService(
            runtime=GovernedProcessRuntime(self.root / "runs"),
            registry=ProcessDefinitionRegistry(self.root / "registry"),
            management_interview=ManagementInterviewService(
                runtime=GovernedProcessRuntime(self.root / "runs"),
                sessions_root=self.root / "sessions", repository_root=ROOT,
            ),
            library=ProcessLibraryLifecycleService(
                runtime=GovernedProcessRuntime(self.root / "runs"),
                registry_root=self.root / "registry", seed_definitions=[],
            ),
            worker=automation.IsolatedProcessWorker(runner=unavailable_verifier),
        )
        with self.assertRaises(automation.ProcessAutomationWorkerError):
            restarted.execute(paused["run_id"])
        self.assertEqual(
            restarted.run_state(paused["run_id"])["status"],
            "paused_after_failure",
        )
        with self.assertRaises(automation.ProcessAutomationWorkerError):
            restarted.execute(paused["run_id"])
        exhausted = restarted.run_state(paused["run_id"])
        self.assertEqual(exhausted["run_state"], "blocked")
        final_records = restarted.runtime.load_records(paused["run_id"])
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "isolated_process_verification_failed"
            for record in final_records
        ), 3)
        self.assertFalse(any(
            (record.get("transition") or {}).get("directive") == "ACCEPT"
            for record in final_records
        ))

    def test_verification_failure_can_resume_after_restart_without_replaying_actions(self):
        authored = self.author()
        operations = []

        def fail_verifier_once(request):
            operations.append((request["kind"], request["operation"]))
            if request["kind"] == "verify":
                raise RuntimeError("temporary verifier outage")
            return worker_module.execute(request)

        self.service.worker = automation.IsolatedProcessWorker(runner=fail_verifier_once)
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        with self.assertRaises(automation.ProcessAutomationWorkerError):
            self.service.resolve_checkpoint(
                paused["run_id"], outcome="approved", decision_by="principal:user",
            )
        restarted_operations = []

        def recovered_worker(request):
            restarted_operations.append((request["kind"], request["operation"]))
            return worker_module.execute(request)

        restarted = automation.ProcessAutomationService(
            runtime=GovernedProcessRuntime(self.root / "runs"),
            registry=ProcessDefinitionRegistry(self.root / "registry"),
            management_interview=ManagementInterviewService(
                runtime=GovernedProcessRuntime(self.root / "runs"),
                sessions_root=self.root / "sessions", repository_root=ROOT,
            ),
            library=ProcessLibraryLifecycleService(
                runtime=GovernedProcessRuntime(self.root / "runs"),
                registry_root=self.root / "registry", seed_definitions=[],
            ),
            worker=automation.IsolatedProcessWorker(runner=recovered_worker),
        )
        completed = restarted.execute(paused["run_id"])
        self.assertEqual(completed["run_state"], "completed")
        self.assertEqual(restarted_operations, [("verify", "verify.process_result")])
        self.assertEqual(sum(kind == "execute" for kind, _ in operations), 3)
        records = restarted.runtime.load_records(paused["run_id"])
        self.assertEqual(sum(
            (record.get("event") or {}).get("event_type")
            == "isolated_process_verification_failed"
            for record in records
        ), 1)
        self.assertEqual(sum(
            (record.get("transition") or {}).get("directive") == "ACCEPT"
            for record in records
        ), 1)

    def test_duplicate_begin_returns_same_run_and_cross_identity_changes_run(self):
        authored = self.author()
        ref = authored["proposal"]["definition_ref"]
        first = self.begin(ref)
        second = self.begin(ref)
        self.assertEqual(first["run_id"], second["run_id"])
        changed = self.service.begin_run(
            definition_ref=ref, project_ref="ora",
            inputs={**self.inputs(), "message_id": "message-002"},
            idempotency_key="run:email:1",
        )
        self.assertNotEqual(changed["run_id"], first["run_id"])

    def test_unpromoted_definition_and_wrong_project_fail_closed(self):
        definition = automation.compile_blueprint(
            automation.email_processing_blueprint("ora")
        )
        self.registry.register(definition)
        with self.assertRaises(automation.ProcessAutomationInputRequired):
            self.service.begin_run(
                definition_ref=automation._definition_ref(definition),
                project_ref="ora", inputs=self.inputs(), idempotency_key="run:unpromoted",
            )
        authored = self.author()
        with self.assertRaises(automation.ProcessAutomationInputRequired):
            self.service.begin_run(
                definition_ref=authored["proposal"]["definition_ref"],
                project_ref="msi", inputs=self.inputs(), idempotency_key="run:wrong-project",
            )

    def test_content_drift_and_nonprincipal_checkpoint_fail_closed(self):
        authored = self.author()
        paused = self.service.execute(
            self.begin(authored["proposal"]["definition_ref"])["run_id"]
        )
        before = self.runtime.load_run(paused["run_id"])
        with self.assertRaises(automation.ProcessAutomationConflict):
            self.service.resolve_checkpoint(
                paused["run_id"], outcome="approved", decision_by="reviewer:other",
            )
        after = self.runtime.load_run(paused["run_id"])
        self.assertEqual(after, before)
        working = next(
            self.runtime.load_artifact(paused["run_id"], artifact_id)
            for artifact_id in self.runtime.load_run(paused["run_id"])["artifact_ids"]
            if self.runtime.load_artifact(paused["run_id"], artifact_id)["role"] == "working"
        )
        Path(working["locator"]["ref"]).write_text("{}\n", encoding="utf-8")
        with self.assertRaises(automation.ProcessAutomationIntegrityError):
            self.service.resolve_checkpoint(
                paused["run_id"], outcome="approved", decision_by="principal:user",
            )


class ProcessAutomationServerTests(ProcessAutomationFixture):
    def setUp(self):
        super().setUp()
        server.app.config["TESTING"] = True
        self.client = server.app.test_client()
        self.service_patch = mock.patch.object(
            server, "_process_automation_service", return_value=self.service,
        )
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)

    def test_public_authoring_and_run_boundary(self):
        proposed = self.client.post(
            "/api/process-authoring/dialogue-g1-18",
            json={
                "action": "propose",
                "idempotency_key": "api:proposal:1",
                "blueprint": automation.email_processing_blueprint("ora"),
            },
        )
        self.assertEqual(proposed.status_code, 200, proposed.get_json())
        proposal = proposed.get_json()["authoring"]["proposal"]
        approved = self.client.post(
            "/api/process-authoring/dialogue-g1-18",
            json={
                "action": "approve_and_register",
                "proposal_id": proposal["proposal_id"],
                "proposal_digest": proposal["proposal_digest"],
            },
        )
        self.assertEqual(approved.status_code, 200, approved.get_json())
        ref = approved.get_json()["authoring"]["proposal"]["definition_ref"]
        started = self.client.post(
            "/api/process-automation/runs",
            json={
                "definition_ref": ref,
                "project_ref": "ora",
                "inputs": self.inputs(),
                "idempotency_key": "api:run:1",
            },
        )
        self.assertEqual(started.status_code, 201, started.get_json())
        run = started.get_json()["run"]
        self.assertEqual(run["status"], "awaiting_human_checkpoint")
        finished = self.client.post(
            "/api/process-automation/runs/" + run["run_id"],
            json={
                "action": "resolve_checkpoint",
                "outcome": "approved",
            },
        )
        self.assertEqual(finished.status_code, 200, finished.get_json())
        self.assertEqual(finished.get_json()["run"]["run_state"], "completed")

    def test_public_boundary_rejects_implicit_approval_and_unknown_fields(self):
        response = self.client.post(
            "/api/process-authoring/dialogue-g1-18",
            json={"action": "approve_and_register"},
        )
        self.assertEqual(response.status_code, 422)

    def test_public_run_enforces_enum_and_string_constraints(self):
        blueprint = automation.email_processing_blueprint("ora")
        blueprint["input_schema"]["properties"]["sender"]["enum"] = ["Alex"]
        blueprint["input_schema"]["properties"]["body"]["minLength"] = 20
        proposed = self.client.post(
            "/api/process-authoring/dialogue-g1-18",
            json={
                "action": "propose", "idempotency_key": "api:schema:proposal",
                "blueprint": blueprint,
            },
        )
        self.assertEqual(proposed.status_code, 200, proposed.get_json())
        proposal = proposed.get_json()["authoring"]["proposal"]
        approved = self.client.post(
            "/api/process-authoring/dialogue-g1-18",
            json={
                "action": "approve_and_register",
                "proposal_id": proposal["proposal_id"],
                "proposal_digest": proposal["proposal_digest"],
            },
        )
        self.assertEqual(approved.status_code, 200, approved.get_json())
        ref = approved.get_json()["authoring"]["proposal"]["definition_ref"]
        for bad_inputs in (
            {**self.inputs(), "sender": "Mallory"},
            {**self.inputs(), "body": "too short"},
        ):
            with self.subTest(bad_inputs=bad_inputs):
                response = self.client.post(
                    "/api/process-automation/runs",
                    json={
                        "definition_ref": ref, "project_ref": "ora",
                        "inputs": bad_inputs,
                        "idempotency_key": "api:schema:" + automation._digest_json(bad_inputs)[-12:],
                    },
                )
                self.assertEqual(response.status_code, 422, response.get_json())
        accepted = self.client.post(
            "/api/process-automation/runs",
            json={
                "definition_ref": ref, "project_ref": "ora",
                "inputs": self.inputs(), "idempotency_key": "api:schema:valid",
            },
        )
        self.assertEqual(accepted.status_code, 201, accepted.get_json())
        response = self.client.post(
            "/api/process-authoring/dialogue-g1-18",
            json={
                "action": "approve_and_register",
                "proposal_id": "proposal:forged",
                "proposal_digest": "sha256:" + ("0" * 64),
                "decision_by": "principal:attacker",
            },
        )
        self.assertEqual(response.status_code, 422)
        response = self.client.post(
            "/api/process-automation/runs/automated-run-forged",
            json={
                "action": "resolve_checkpoint",
                "outcome": "approved",
                "decision_by": "principal:attacker",
            },
        )
        self.assertEqual(response.status_code, 422)
        response = self.client.post(
            "/api/process-automation/runs",
            json={"definition_ref": {}, "project_ref": "ora", "inputs": {},
                  "idempotency_key": "api:bad", "trigger": "daily"},
        )
        self.assertEqual(response.status_code, 422)
        response = self.client.post(
            "/api/process-automation/runs",
            json={"definition_ref": {}, "project_ref": "ora", "inputs": {},
                  "idempotency_key": "api:bad-principal",
                  "principal_id": "principal:attacker"},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
