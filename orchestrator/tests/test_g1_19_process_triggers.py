"""G1.19 Trigger Manager authority, lineage, recovery, and time proofs."""
from __future__ import annotations

import copy
import inspect
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from orchestrator import process_automation as automation
from orchestrator import process_triggers as triggers
from orchestrator.tests.test_g1_18_process_automation import ProcessAutomationFixture
from orchestrator.tests.test_g1_18_process_automation import ANSWERS
from orchestrator.process_entry_routing import route_process_entry
from server import server


ROOT = Path(__file__).resolve().parents[2]
VAULT_ORA = Path.home() / "Documents" / "vault" / "Projects" / "Ora"


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        marker = text.find("\n---\n", 4)
        if marker < 0:
            raise AssertionError(f"unterminated frontmatter: {path}")
        text = text[marker + 5:]
    return text.lstrip("\n").rstrip()


RUNTIME_PRINCIPLE = {
    "declared_cause": "passage of time is the declared input",
    "runtime_impossibility": (
        "A calendar check-in has no earlier file, framework, or inbound event; "
        "the elapsed calendar boundary is the information being requested."
    ),
    "runtime_alternative": "no runtime event can represent passage of time",
    "availability_boundary": "only while ora is running",
    "no_clock_fallback": "no cron, launchd, or deferred sweep fallback",
}


class ProcessTriggerTests(ProcessAutomationFixture):
    def setUp(self):
        super().setUp()
        authored = self.author()
        self.definition_ref = authored["proposal"]["definition_ref"]
        self.trigger_service = triggers.ProcessTriggerService(
            root=self.root / "triggers",
            automation=self.service,
            now=lambda: "2026-07-20T00:00:00Z",
            vault=self.root / "vault",
            sessions_root=self.root / "sessions",
        )

    def spec(self, trigger_id="email-manual", *, kind="manual", condition=None, bindings=None):
        if condition is None:
            condition = {}
        return {
            "trigger_id": trigger_id,
            "name": trigger_id.replace("-", " ").title(),
            "definition_ref": copy.deepcopy(self.definition_ref),
            "project_ref": "ora",
            "kind": kind,
            "condition": condition,
            "input_bindings": bindings or {
                key: {"source": "literal", "value": value}
                for key, value in self.inputs().items()
            },
            "principal_id": "principal:user",
        }

    def create_and_activate(self, spec):
        state = self.trigger_service.create(spec)
        request = state["activation_request"]
        return self.trigger_service.activate(
            spec["trigger_id"],
            expected_spec_digest=state["spec_digest"],
            approval={
                "decision": "approve_activation",
                "principal_id": "principal:user",
                "request_digest": request["request_digest"],
            },
            idempotency_key=f"activate:{spec['trigger_id']}",
        )

    def author_followup(self):
        route = route_process_entry({
            "source": "natural_language",
            "objective": "Build another reusable email processing capability.",
            "project_ref": "ora",
            "project_confirmed": True,
        })
        state = self.interview.start_or_resume("dialogue-g1-19-followup", route)
        while state["status"] == "interviewing":
            question = state["current_question"]
            state = self.interview.answer(
                state["dialogue_ref"], ANSWERS[question["dimension"]],
                question_id=question["question_id"],
                idempotency_key=f"g119-answer:{question['dimension']}",
            )
        blueprint = automation.email_processing_blueprint("ora")
        blueprint["definition_id"] = "user/email-followup"
        blueprint["title"] = "Email Followup"
        proposed = self.service.propose(
            state["dialogue_ref"], idempotency_key="proposal:g119:followup",
            blueprint=blueprint,
        )
        approved = self.service.approve_and_register(
            state["dialogue_ref"],
            proposal_id=proposed["proposal"]["proposal_id"],
            proposal_digest=proposed["proposal"]["proposal_digest"],
            decision_by="principal:user",
        )
        return approved["proposal"]["definition_ref"]

    def test_registration_does_not_activate_and_exact_review_is_required(self):
        state = self.trigger_service.create(self.spec())
        self.assertEqual(state["status"], "draft")
        with self.assertRaises(triggers.ProcessTriggerConflict):
            self.trigger_service.fire_manual(
                "email-manual", request_id="request:1", requested_by="principal:user"
            )
        with self.assertRaises(triggers.ProcessTriggerConflict):
            self.trigger_service.activate(
                "email-manual",
                expected_spec_digest=state["spec_digest"],
                approval={
                    "decision": "approve_activation",
                    "principal_id": "principal:user",
                    "request_digest": "sha256:" + "0" * 64,
                },
                idempotency_key="activate:forged",
            )
        self.assertEqual(self.trigger_service.get("email-manual")["status"], "draft")

    def test_interrupted_creation_repairs_only_the_same_exact_spec(self):
        original = triggers._write_json
        calls = 0

        def interrupt_anchor(path, value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected anchor interruption")
            return original(path, value)

        with mock.patch.object(triggers, "_write_json", side_effect=interrupt_anchor):
            with self.assertRaises(OSError):
                self.trigger_service.create(self.spec("interrupted-create"))
        repaired = self.trigger_service.create(self.spec("interrupted-create"))
        self.assertEqual(repaired["status"], "draft")
        created = [
            row for row in self.trigger_service._load_records("interrupted-create")
            if row["event_type"] == "trigger_created"
        ]
        self.assertEqual(len(created), 1)
        changed = self.spec("interrupted-create")
        changed["name"] = "Substituted"
        with self.assertRaises(triggers.ProcessTriggerConflict):
            self.trigger_service.create(changed)

    def test_manual_fire_creates_exact_trigger_bound_run_and_retry_is_idempotent(self):
        self.create_and_activate(self.spec())
        first = self.trigger_service.fire_manual(
            "email-manual", request_id="request:1", requested_by="principal:user"
        )
        replay = self.trigger_service.fire_manual(
            "email-manual", request_id="request:1", requested_by="principal:user"
        )
        self.assertEqual(first["state_digest"], replay["state_digest"])
        delivered = [row for row in first["firings"] if row["status"] == "waiting"]
        self.assertEqual(len(delivered), 1)
        run = self.runtime.load_run(delivered[0]["run_id"])
        binding = run["input_bindings"]["trigger_binding"]
        self.assertEqual(binding["trigger_id"], "email-manual")
        self.assertEqual(binding["spec_digest"], first["spec_digest"])
        self.assertEqual(
            self.service.run_state(run["run_id"])["status"],
            "awaiting_human_checkpoint",
        )

    def test_one_claim_derives_every_invocation_field_and_binds_one_run(self):
        active = self.create_and_activate(self.spec())
        source = {
            "kind": "manual", "request_id": "request:bound-contract",
            "requested_by": "principal:user",
        }
        firing, created = self.trigger_service._claim(
            active["spec"], active["spec_digest"], source
        )
        self.assertTrue(created)
        contract = firing["invocation_contract"]
        binding = contract["trigger_binding"]
        first = self.service.begin_triggered_run(trigger_binding=binding)
        records_before = self.runtime.load_records(first["run_id"])

        with self.assertRaises(TypeError):
            self.service.begin_triggered_run(
                trigger_binding=binding,
                inputs={**self.inputs(), "email_body": "attacker substitution"},
                principal_id="principal:attacker",
                idempotency_key="attacker:key",
            )
        replay = self.service.begin_triggered_run(trigger_binding=binding)
        self.assertEqual(replay["run_id"], contract["run_id"])
        self.assertEqual(replay["run_id"], first["run_id"])
        self.assertEqual(self.runtime.load_records(first["run_id"]), records_before)
        run = self.runtime.load_run(first["run_id"])
        self.assertEqual(run["input_bindings"]["principal_id"], "principal:user")
        self.assertEqual(run["input_bindings"]["inputs"], self.inputs())
        self.assertEqual(
            run["input_bindings"]["idempotency_key"],
            contract["idempotency_key"],
        )

    def test_generic_service_cannot_forge_trigger_bound_run(self):
        forged = automation.ProcessAutomationService(
            runtime=self.runtime,
            registry=self.registry,
            management_interview=self.interview,
            library=self.library,
            worker=self.worker,
        )
        with self.assertRaisesRegex(
            automation.ProcessAutomationIntegrityError, "authenticated Trigger Manager"
        ):
            forged.begin_triggered_run(
                trigger_binding={
                    "schema_version": triggers.TRIGGER_SCHEMA_VERSION,
                    "trigger_id": "email-manual",
                    "spec_digest": "sha256:" + "1" * 64,
                    "firing_id": "firing-forged",
                    "source_digest": "sha256:" + "2" * 64,
                },
            )

    def test_concurrent_delivery_claims_one_firing_and_one_run(self):
        self.create_and_activate(self.spec())
        barrier = threading.Barrier(2)
        results, errors = [], []

        def deliver():
            try:
                barrier.wait()
                results.append(self.trigger_service.fire_manual(
                    "email-manual", request_id="request:race", requested_by="principal:user"
                ))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        workers = [threading.Thread(target=deliver) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertFalse(errors)
        self.assertEqual(len(results), 2)
        state = self.trigger_service.get("email-manual")
        claims = [row for row in self.trigger_service._load_records("email-manual") if row["event_type"] == "firing_claimed"]
        self.assertEqual(len(claims), 1)
        self.assertEqual(len({row.get("run_id") for row in state["firings"] if row.get("run_id")}), 1)

    def test_pause_retire_and_stale_lifecycle_requests_fail_closed(self):
        active = self.create_and_activate(self.spec())
        with self.assertRaises(triggers.ProcessTriggerConflict):
            self.trigger_service.lifecycle(
                "email-manual", action="pause",
                expected_state_digest="sha256:" + "0" * 64,
                idempotency_key="pause:stale",
            )
        paused = self.trigger_service.lifecycle(
            "email-manual", action="pause", expected_state_digest=active["state_digest"],
            idempotency_key="pause:1",
        )
        self.assertEqual(paused["status"], "paused")
        replay = self.trigger_service.lifecycle(
            "email-manual", action="pause", expected_state_digest=active["state_digest"],
            idempotency_key="pause:1",
        )
        self.assertEqual(replay["state_digest"], paused["state_digest"])
        with self.assertRaisesRegex(triggers.ProcessTriggerConflict, "not activatable"):
            self.trigger_service.activate(
                "email-manual", expected_spec_digest=paused["spec_digest"],
                approval={
                    "decision": "approve_activation",
                    "principal_id": "principal:user",
                    "request_digest": paused["activation_request"]["request_digest"],
                },
                idempotency_key="activate:paused-bypass",
            )
        with self.assertRaises(triggers.ProcessTriggerConflict):
            self.trigger_service.fire_manual(
                "email-manual", request_id="request:paused", requested_by="principal:user"
            )
        resumed = self.trigger_service.lifecycle(
            "email-manual", action="resume", expected_state_digest=paused["state_digest"],
            idempotency_key="resume:1",
        )
        self.assertEqual(resumed["status"], "active")
        historical = self.trigger_service.lifecycle(
            "email-manual", action="pause", expected_state_digest=active["state_digest"],
            idempotency_key="pause:1",
        )
        self.assertEqual(historical["state_digest"], paused["state_digest"])
        self.assertEqual(self.trigger_service.get("email-manual")["status"], "active")

    def test_inbound_contract_exists_but_cannot_activate_before_g1_21(self):
        spec = self.spec(
            "inbound-email", kind="inbound",
            condition={"channel": "email", "source_scope": "approved mailbox identity"},
        )
        state = self.trigger_service.create(spec)
        with self.assertRaisesRegex(triggers.ProcessTriggerConflict, "G1.21"):
            self.trigger_service.activate(
                "inbound-email", expected_spec_digest=state["spec_digest"],
                approval={
                    "decision": "approve_activation",
                    "principal_id": "principal:user",
                    "request_digest": state["activation_request"]["request_digest"],
                },
                idempotency_key="activate:inbound",
            )

    def test_file_change_dispatch_is_exact_scoped_and_idempotent(self):
        watched = self.root / "watched"
        watched.mkdir()
        target = watched / "message.md"
        target.write_text("first", encoding="utf-8")
        spec = self.spec(
            "file-email", kind="event",
            condition={"event_type": "file_change", "path_selectors": [str(watched)]},
        )
        self.create_and_activate(spec)
        unrelated = self.root / "other.md"
        unrelated.write_text("other", encoding="utf-8")
        self.assertFalse(self.trigger_service.dispatch_paths([str(unrelated)])["fired"])
        first = self.trigger_service.dispatch_paths([str(target)])
        replay = self.trigger_service.dispatch_paths([str(target)])
        self.assertEqual(len(first["fired"]), 1)
        self.assertEqual(len(replay["fired"]), 1)
        claims = [row for row in self.trigger_service._load_records("file-email") if row["event_type"] == "firing_claimed"]
        self.assertEqual(len(claims), 1)
        target.write_text("second", encoding="utf-8")
        changed = self.trigger_service.dispatch_paths([str(target)])
        self.assertEqual(len(changed["fired"]), 1)
        claims = [row for row in self.trigger_service._load_records("file-email") if row["event_type"] == "firing_claimed"]
        self.assertEqual(len(claims), 2)

    def test_pause_wins_after_event_selection_but_before_claim(self):
        watched = self.root / "pause-race"
        watched.mkdir()
        target = watched / "message.md"
        target.write_text("selected before pause", encoding="utf-8")
        spec = self.spec(
            "file-pause-race", kind="event",
            condition={"event_type": "file_change", "path_selectors": [str(watched)]},
        )
        active = self.create_and_activate(spec)
        capture = self.trigger_service._file_identity
        paused_once = False

        def pause_after_selection(path):
            nonlocal paused_once
            if not paused_once:
                paused_once = True
                self.trigger_service.lifecycle(
                    "file-pause-race", action="pause",
                    expected_state_digest=active["state_digest"],
                    idempotency_key="pause:event-race",
                )
            return capture(path)

        with mock.patch.object(
            self.trigger_service, "_file_identity", side_effect=pause_after_selection,
        ):
            result = self.trigger_service.dispatch_paths([str(target)])
        self.assertEqual(result["fired"], [])
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(self.trigger_service.get("file-pause-race")["status"], "paused")
        claims = [
            row for row in self.trigger_service._load_records("file-pause-race")
            if row["event_type"] == "firing_claimed"
        ]
        self.assertEqual(claims, [])

    def test_time_requires_written_justification_and_preserves_named_timezone(self):
        condition = {
            "event_type": "time",
            "schedule": {
                "timezone": "America/Los_Angeles", "local_time": "09:00",
                "cadence": "daily", "weekdays": [], "start_date": "2026-03-01",
                "missed_policy": "run_once", "grace_seconds": 300,
            },
        }
        spec = self.spec("daily-email", kind="time", condition=condition)
        with self.assertRaisesRegex(triggers.ProcessTriggerInputRequired, "Runtime-Principle"):
            self.trigger_service.create(spec)
        spec["runtime_principle"] = copy.deepcopy(RUNTIME_PRINCIPLE)
        self.create_and_activate(spec)
        spring = triggers._occurrences(
            condition["schedule"],
            datetime(2026, 3, 7, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 10, 23, tzinfo=timezone.utc),
        )
        self.assertEqual(spring[0].hour, 17)  # PST
        self.assertEqual(spring[-1].hour, 16)  # PDT, named zone retained
        fall = triggers._occurrences(
            condition["schedule"],
            datetime(2026, 10, 31, 0, tzinfo=timezone.utc),
            datetime(2026, 11, 3, 23, tzinfo=timezone.utc),
        )
        self.assertEqual(fall[0].hour, 16)  # PDT
        self.assertEqual(fall[-1].hour, 17)  # PST

    def test_time_intermitttency_run_once_coalesces_and_skip_records_no_run(self):
        base_schedule = {
            "timezone": "UTC", "local_time": "10:00", "cadence": "daily",
            "weekdays": [], "start_date": "2026-07-20", "grace_seconds": 10,
        }
        for trigger_id, policy in (("time-run-once", "run_once"), ("time-skip", "skip")):
            spec = self.spec(
                trigger_id, kind="time",
                condition={"event_type": "time", "schedule": {**base_schedule, "missed_policy": policy}},
            )
            spec["runtime_principle"] = copy.deepcopy(RUNTIME_PRINCIPLE)
            self.create_and_activate(spec)
        result = self.trigger_service.run_due(now="2026-07-24T12:00:00Z")
        self.assertEqual([row["trigger_id"] for row in result["fired"]], ["time-run-once"])
        self.assertEqual(result["skipped"], ["time-skip"])
        run_once = self.trigger_service.get("time-run-once")
        self.assertEqual(run_once["firings"][-1]["status"], "waiting")
        self.assertEqual(self.trigger_service.get("time-skip")["firings"][-1]["status"], "skipped")

    def test_clock_uses_recalculated_one_shot_wakes_without_interval_polling(self):
        class FakeService:
            def __init__(self):
                self.recover_calls = 0
                self.due_calls = 0
                self.target = None
                self.second_due = threading.Event()

            def recover_incomplete(self):
                self.recover_calls += 1
                return {"recovered": [], "failures": []}

            def run_due(self):
                self.due_calls += 1
                if self.due_calls == 2:
                    self.second_due.set()
                return {"fired": [], "skipped": [], "failures": []}

            def next_wake_at(self):
                return self.target if self.due_calls == 1 else None

        source = inspect.getsource(triggers.ProcessTriggerClock._run)
        self.assertNotIn("interval_seconds", source)
        self.assertIn("next_wake_at", source)
        fake = FakeService()
        clock = triggers.ProcessTriggerClock(fake)
        clock.start()
        self.assertEqual(fake.recover_calls, 1)
        self.assertEqual(fake.due_calls, 1)
        fake.target = datetime.now(timezone.utc) + timedelta(milliseconds=40)
        triggers._notify_clock_change()
        self.assertTrue(fake.second_due.wait(timeout=1.0))
        clock.stop()
        self.assertEqual(fake.due_calls, 2)

    def test_time_activation_and_lifecycle_recalculate_one_shot_wake(self):
        schedule = {
            "timezone": "UTC", "local_time": "10:00", "cadence": "daily",
            "weekdays": [], "start_date": "2026-07-20",
            "missed_policy": "skip", "grace_seconds": 30,
        }
        spec = self.spec(
            "time-wake", kind="time",
            condition={"event_type": "time", "schedule": schedule},
        )
        spec["runtime_principle"] = copy.deepcopy(RUNTIME_PRINCIPLE)
        draft = self.trigger_service.create(spec)
        with mock.patch.object(triggers, "_notify_clock_change") as notify:
            active = self.trigger_service.activate(
                "time-wake", expected_spec_digest=draft["spec_digest"],
                approval={
                    "decision": "approve_activation",
                    "principal_id": "principal:user",
                    "request_digest": draft["activation_request"]["request_digest"],
                },
                idempotency_key="activate:time-wake",
            )
            paused = self.trigger_service.lifecycle(
                "time-wake", action="pause",
                expected_state_digest=active["state_digest"],
                idempotency_key="pause:time-wake",
            )
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(notify.call_count, 2)

    def test_definition_and_ledger_tampering_fail_listing_closed(self):
        self.trigger_service.create(self.spec())
        definition_path, _, records_path = self.trigger_service._paths("email-manual")
        envelope = json.loads(definition_path.read_text(encoding="utf-8"))
        envelope["spec"]["name"] = "Substituted"
        definition_path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaises(triggers.ProcessTriggerIntegrityError):
            self.trigger_service.list()
        # Restore definition, then prove record-chain substitution also closes listing.
        spec = triggers.normalize_trigger_spec(self.spec())
        definition_path.write_text(json.dumps({"spec": spec, "spec_digest": triggers._digest_json(spec)}), encoding="utf-8")
        records = json.loads(records_path.read_text(encoding="utf-8"))
        records[0]["details"]["project_ref"] = "other"
        records_path.write_text(json.dumps(records), encoding="utf-8")
        with self.assertRaises(triggers.ProcessTriggerIntegrityError):
            self.trigger_service.list()

    def test_failed_begin_is_durable_and_restart_recovery_reuses_claim(self):
        self.create_and_activate(self.spec())
        original = self.service.begin_triggered_run
        with mock.patch.object(self.service, "begin_triggered_run", side_effect=RuntimeError("injected unavailable")):
            with self.assertRaises(RuntimeError):
                self.trigger_service.fire_manual(
                    "email-manual", request_id="request:failure", requested_by="principal:user"
                )
        state = self.trigger_service.get("email-manual")
        self.assertEqual(state["firings"][-1]["status"], "failed")
        self.assertIs(original.__self__, self.service)

    def test_restart_recovers_a_claim_interrupted_before_run_creation(self):
        state = self.create_and_activate(self.spec())
        spec = state["spec"]
        source = {
            "kind": "manual", "request_id": "request:interrupted",
            "requested_by": "principal:user",
        }
        with self.trigger_service._locked():
            firing, created = self.trigger_service._claim(spec, state["spec_digest"], source)
        self.assertTrue(created)
        self.assertEqual(firing["status"], "claimed")
        restarted = triggers.ProcessTriggerService(
            root=self.root / "triggers", automation=self.service,
            now=lambda: "2026-07-20T00:00:00Z",
            vault=self.root / "vault", sessions_root=self.root / "sessions",
        )
        recovered = restarted.recover_incomplete()
        self.assertEqual(recovered["failures"], [])
        self.assertEqual(recovered["recovered"][0]["firing_id"], firing["firing_id"])
        claims = [
            row for row in restarted._load_records("email-manual")
            if row["event_type"] == "firing_claimed"
        ]
        self.assertEqual(len(claims), 1)

    def test_framework_completion_requires_exact_accepted_source(self):
        target_ref = self.author_followup()
        target_spec = self.spec(
            "after-email", kind="event",
            condition={
                "event_type": "framework_completion",
                "source_definition_ref": copy.deepcopy(self.definition_ref),
            },
        )
        target_spec["definition_ref"] = target_ref
        self.create_and_activate(target_spec)
        source = self.begin(self.definition_ref)
        source = self.service.execute(source["run_id"])
        self.assertEqual(source["status"], "awaiting_human_checkpoint")
        self.assertFalse(
            self.trigger_service.dispatch_framework_completion(source["run_id"])["fired"]
        )
        source = self.service.resolve_checkpoint(
            source["run_id"], outcome="approved", decision_by="principal:user"
        )
        self.assertEqual(source["run_state"], "completed")
        dispatched = self.trigger_service.dispatch_framework_completion(source["run_id"])
        self.assertEqual([row["trigger_id"] for row in dispatched["fired"]], ["after-email"])
        replay = self.trigger_service.dispatch_framework_completion(source["run_id"])
        self.assertEqual([row["trigger_id"] for row in replay["fired"]], ["after-email"])
        claims = [
            row for row in self.trigger_service._load_records("after-email")
            if row["event_type"] == "firing_claimed"
        ]
        self.assertEqual(len(claims), 1)

    def test_framework_completion_causal_cycle_is_rejected(self):
        with self.assertRaisesRegex(triggers.ProcessTriggerConflict, "causal cycle"):
            self.trigger_service.create(self.spec(
                "self-cycle", kind="event",
                condition={
                    "event_type": "framework_completion",
                    "source_definition_ref": copy.deepcopy(self.definition_ref),
                },
            ))

    def test_public_api_binds_create_activation_fire_and_attention_projection(self):
        client = server.app.test_client()
        with mock.patch.object(server, "_process_trigger_service", return_value=self.trigger_service):
            created = client.post("/api/process-triggers", json={"spec": self.spec()})
            self.assertEqual(created.status_code, 201)
            draft = created.get_json()["trigger"]
            rejected = client.post("/api/process-triggers/email-manual", json={
                "action": "activate",
                "expected_spec_digest": draft["spec_digest"],
                "approval": {
                    "decision": "approve_activation", "principal_id": "principal:user",
                    "request_digest": "sha256:" + "0" * 64,
                },
                "idempotency_key": "activate:forged",
            })
            self.assertEqual(rejected.status_code, 409)
            accepted = client.post("/api/process-triggers/email-manual", json={
                "action": "activate",
                "expected_spec_digest": draft["spec_digest"],
                "approval": {
                    "decision": "approve_activation", "principal_id": "principal:user",
                    "request_digest": draft["activation_request"]["request_digest"],
                },
                "idempotency_key": "activate:api",
            })
            self.assertEqual(accepted.status_code, 200)
            fired = client.post("/api/process-triggers/email-manual", json={
                "action": "fire", "request_id": "manual:api",
            })
            self.assertEqual(fired.status_code, 200)
            self.assertEqual(fired.get_json()["trigger"]["firings"][-1]["status"], "waiting")
            attention = client.get("/api/process-attention")
            self.assertEqual(attention.status_code, 200)
            automated = attention.get_json()["automated_processes"]
            self.assertEqual(automated[0]["trigger_id"], "email-manual")

    def test_milestone_snapshot_binds_matrix_and_dialogue_content(self):
        matrix_dir = self.root / "vault" / "Matrix"
        matrix_dir.mkdir(parents=True)
        matrix = matrix_dir / "Project Matrix Ora.md"
        matrix.write_text(
            "---\nnexus:\n  - ora\ntype: matrix\ntags: []\n---\n# Ora\n\n## Milestones\n- [ ] Trigger proof is reviewed.\n",
            encoding="utf-8",
        )
        snapshot = self.trigger_service._project_snapshot("ora")
        self.assertEqual(snapshot["matrix"]["locator"], str(matrix.resolve()))
        self.assertIn("Trigger proof", snapshot["matrix"]["content"])
        self.assertTrue(snapshot["dialogues"])
        self.assertTrue(snapshot["snapshot_digest"].startswith("sha256:"))


class TestProcessTriggerDocumentation:
    def test_user_and_technical_mirrors_are_exact_and_describe_shipped_boundaries(self):
        user_runtime = ROOT / "docs" / "user-guide.md"
        user_vault = VAULT_ORA / "Guide — Using Ora.md"
        technical_runtime = ROOT / "docs" / "technical-documentation.md"
        technical_vault = VAULT_ORA / "Reference — Ora Technical Documentation.md"
        assert _body(user_runtime) == _body(user_vault)
        assert _body(technical_runtime) == _body(technical_vault)
        user = _body(user_runtime)
        for token in (
            "### Deploy and manage a Trigger",
            "Processes → Trigger Manager",
            "only while Ora is running",
            "no cron, launchd, scheduled sweep, polling loop, or 24/7 fallback",
            "with no active time Trigger, no periodic work runs",
            "cannot be activated until G1.21",
            "A firing that reaches a human checkpoint remains visible as waiting",
        ):
            assert token in user
        technical = _body(technical_runtime)
        for token in (
            "## 21. G1.19 Trigger Manager",
            "Separate activation object over one Process engine",
            "Exactly-once firing and governed Run join",
            "Runtime-Principle disposition for time",
            "installs no OS task",
            "one startup missed-window reconciliation",
            "performs no periodic scan",
            "adds no second Process engine, telemetry database, Persona/MindSpec precedence",
        ):
            assert token in technical

    def test_tracker_program_registry_record_submission_and_preserve_deferrals(self):
        combined = "\n".join(
            (VAULT_ORA / name).read_text(encoding="utf-8")
            for name in (
                "Working — Ora Setup and Refinement.md",
                "Working — Framework — Ora Project Integration Program.md",
                "Registry — Ora Overview and Document Registry.md",
            )
        )
        for token in (
            "G1.19 is implemented and submitted",
            "G1.19 IMPLEMENTED FOR JUDGMENT",
            "independent judgment is pending",
            "G1.17 is user-deferred",
            "G1.12, G1.3, and G1.7 remain user-deferred",
            "no Persona, channel credential/transport, outbound effect, second engine",
        ):
            assert token in combined
        assert "G1.19 is independently accepted" not in combined


if __name__ == "__main__":
    import unittest
    unittest.main()
