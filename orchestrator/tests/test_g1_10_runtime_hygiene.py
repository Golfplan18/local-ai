"""G1.10 adversarial tests for event-only maintenance."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from orchestrator import maintenance_scheduler as scheduler
from orchestrator import runtime_hygiene as hygiene
from orchestrator.tools import supersession_sweep as supersession
from orchestrator import runtime_event_dispatcher as event_dispatcher
from orchestrator import scheduler as legacy_scheduler


class RuntimeHygieneBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.resources = self.root / "Resources"
        self.engrams = self.root / "Engrams"
        self.resources.mkdir()
        self.engrams.mkdir()
        self.data.mkdir()
        self.patchers = [
            mock.patch.object(hygiene._rp, "DATA_DIR_STR", str(self.data)),
            mock.patch.object(supersession.news_res, "RESOURCES_DIR", str(self.resources)),
            mock.patch.object(supersession.eng_res, "ENGRAMS_DIR", str(self.engrams)),
            mock.patch.object(supersession.news_res, "LOG_FILE", str(self.root / "news-log.md")),
            mock.patch.object(supersession.eng_res, "LOG_FILE", str(self.root / "engram-log.md")),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)


class SchedulerBoundaryTests(unittest.TestCase):
    def test_hidden_clock_defaults_are_impossible(self):
        self.assertEqual(scheduler.DEFAULT_CONFIG["news_supersession"], "off")
        self.assertEqual(scheduler.DEFAULT_CONFIG["engram_cleaning"], "off")
        self.assertEqual(scheduler.DEFAULT_CONFIG["orphan_cleanup"], "off")
        self.assertEqual(scheduler.DEFAULT_CONFIG["vault_health"], "off")
        self.assertEqual(scheduler.DEFAULT_CONFIG["graph_density"], "off")
        hostile = {"news_supersession": "daily", "engram_cleaning": "monthly"}
        self.assertEqual(scheduler.due_tasks(hostile, {}), [])
        self.assertNotIn("news_supersession", scheduler.TASK_FUNCTIONS)
        self.assertNotIn("engram_cleaning", scheduler.TASK_FUNCTIONS)
        self.assertNotIn("daily_note", scheduler.TASK_FUNCTIONS)
        self.assertEqual(scheduler.due_tasks({"daily_note": "daily"}, {}), [])

    def test_historical_backlog_requires_explicit_campaign_identity(self):
        with self.assertRaises(TypeError):
            supersession.task_news_supersession()
        invalid = supersession.task_engram_cleaning(campaign_id="contains a space")
        self.assertFalse(invalid.success)
        self.assertIn("explicit campaign id", invalid.message)

    def test_repository_internals_cannot_recursively_dispatch(self):
        self.assertFalse(event_dispatcher._actionable(
            "/Users/example/Documents/vault/.git/HEAD"))
        self.assertFalse(event_dispatcher._actionable(
            "/Users/example/Documents/vault/.obsidian/workspace.json"))
        self.assertTrue(event_dispatcher._actionable(
            "/Users/example/Documents/vault/Engrams/exact.md"))

    def test_artifact_classification_is_top_level_and_scope_bound(self):
        with (
            mock.patch.object(event_dispatcher._rp, "VAULT_STR", "/vault"),
            mock.patch.object(event_dispatcher._rp, "ORA_HOME", "/runtime"),
        ):
            self.assertEqual(
                event_dispatcher._artifact_kind("/vault/Resources/exact.md"),
                "resource",
            )
            self.assertEqual(
                event_dispatcher._artifact_kind("/vault/Engrams/exact.md"),
                "engram",
            )
            self.assertIsNone(
                event_dispatcher._artifact_kind("/vault/Engrams/nested/exact.md")
            )
            self.assertEqual(
                event_dispatcher._artifact_kind("/runtime/Resources/inbound.md"),
                "inbound_resource",
            )

    def test_failed_supersession_is_visible_to_event_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "vault"
            resource = vault / "Resources" / "exact.md"
            resource.parent.mkdir(parents=True)
            resource.write_text("# exact\n", encoding="utf-8")
            inert_modules = {
                "oversight_events": SimpleNamespace(emit=lambda _event: None),
                "ped_watcher": SimpleNamespace(sweep=lambda: []),
                "corpus_watcher": SimpleNamespace(sweep=lambda: []),
                "workflow_spec_sweeper": SimpleNamespace(
                    sweep=lambda **_kwargs: []),
                "revisit_sweeper": SimpleNamespace(
                    sweep=lambda **_kwargs: [],
                    register_age_review_deadlines=lambda: []),
            }
            failed = {
                "event_id": "evt-failed", "status": "failed",
                "error": "model unavailable",
            }
            with (
                mock.patch.dict("sys.modules", inert_modules),
                mock.patch.object(event_dispatcher._rp, "VAULT_STR", str(vault)),
                mock.patch.object(event_dispatcher._rp, "ORA_HOME", Path(temp) / "runtime"),
                mock.patch.object(
                    supersession, "process_artifact_write", return_value=failed),
            ):
                result = event_dispatcher.dispatch_paths({str(resource)})
        self.assertEqual(result["supersession_events"], [failed])
        self.assertTrue(any("model unavailable" in value
                            for value in result["errors"]))

    def test_legacy_private_scheduler_paths_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "retired"):
            legacy_scheduler._run_task({"id": "x"}, {"tasks": []})
        with self.assertRaisesRegex(RuntimeError, "retired"):
            legacy_scheduler.Scheduler()._check_tasks()


class LedgerTests(RuntimeHygieneBase):
    def test_deadline_queue_is_interned_by_canonical_data_root(self):
        first = hygiene.deadline_queue(self.data)
        second = hygiene.deadline_queue(self.data / ".." / "data")
        self.assertIs(first, second)
        self.assertEqual(first.storage_root,
                         (self.data / "runtime-hygiene").resolve())

    def test_claim_is_exactly_once_and_collision_fails(self):
        ledger = hygiene.EventLedger()
        first, created = ledger.claim(
            event_id="evt-fixed", event_type="artifact_written",
            subject={"path": "/x", "sha256": "a" * 64, "size": 1},
        )
        second, created_again = ledger.claim(
            event_id="evt-fixed", event_type="artifact_written",
            subject={"path": "/x", "sha256": "a" * 64, "size": 1},
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, second)
        with self.assertRaises(ValueError):
            ledger.claim(
                event_id="evt-fixed", event_type="artifact_written",
                subject={"path": "/other", "sha256": "b" * 64, "size": 2},
            )

    def test_transaction_error_restores_every_file(self):
        subject = self.root / "subject.md"
        subject.write_text("before", encoding="utf-8")
        ledger = hygiene.EventLedger()
        ledger.claim(event_id="evt-rollback", event_type="test", subject={"id": 1})
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with hygiene.MutationTransaction(ledger, "evt-rollback", [subject]):
                subject.write_text("mutated", encoding="utf-8")
                raise RuntimeError("stop")
        self.assertEqual(subject.read_text(encoding="utf-8"), "before")
        self.assertEqual(ledger.get("evt-rollback")["status"], "failed")

    def test_deadline_failure_is_terminal_and_has_no_clock_retry(self):
        queue = hygiene.DeadlineQueue()
        queue.put(
            "deadline-fail", "2000-01-01T00:00:00+00:00", "test", {"id": 1},
        )
        stop = threading.Event()

        def fail(_payload):
            stop.set()
            raise RuntimeError("bounded failure")

        queue.run({"test": fail}, stop)
        state = queue._load()["deadlines"]["deadline-fail"]
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"], "bounded failure")

    def test_deadline_persists_handler_receipt(self):
        queue = hygiene.DeadlineQueue()
        queue.put(
            "deadline-ok", "2000-01-01T00:00:00+00:00", "test", {"id": 2},
        )
        stop = threading.Event()

        def complete(payload):
            stop.set()
            return {"handled": payload["id"]}

        queue.run({"test": complete}, stop)
        state = queue._load()["deadlines"]["deadline-ok"]
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["receipt"], {"handled": 2})

    def test_unknown_deadline_handler_fails_once_without_killing_lane(self):
        queue = hygiene.DeadlineQueue()
        queue.put(
            "deadline-unknown", "2000-01-01T00:00:00+00:00",
            "missing", {"id": 3},
        )
        stop = threading.Event()
        original_load = queue._load

        def load_and_stop_after_terminal():
            value = original_load()
            record = value["deadlines"].get("deadline-unknown")
            if record and record.get("status") == "failed":
                stop.set()
            return value

        with mock.patch.object(queue, "_load", side_effect=load_and_stop_after_terminal):
            queue.run({}, stop)
        state = original_load()["deadlines"]["deadline-unknown"]
        self.assertEqual(state["status"], "failed")
        self.assertIn("no deadline handler", state["error"])

    def test_restart_terminalizes_pre_mutation_claim(self):
        ledger = hygiene.EventLedger()
        ledger.claim(event_id="evt-claimed", event_type="test", subject={"id": 4})
        self.assertEqual(hygiene.restore_incomplete_events(ledger), ["evt-claimed"])
        state = ledger.get("evt-claimed")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["mutation_count"], 0)

    def test_rollback_refuses_later_artifact_drift(self):
        subject = self.root / "subject.md"
        subject.write_text("before", encoding="utf-8")
        ledger = hygiene.EventLedger()
        ledger.claim(event_id="evt-complete", event_type="test", subject={"id": 1})
        with hygiene.MutationTransaction(ledger, "evt-complete", [subject]) as tx:
            subject.write_text("after", encoding="utf-8")
            tx.commit()
        subject.write_text("later user work", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "drift"):
            hygiene.rollback_completed_event("evt-complete", ledger)
        self.assertEqual(subject.read_text(encoding="utf-8"), "later user work")

    def test_completed_autonomous_after_identity_suppresses_cascade(self):
        subject = self.root / "subject.md"
        subject.write_text("before", encoding="utf-8")
        ledger = hygiene.EventLedger()
        ledger.claim(event_id="evt-autonomous", event_type="test",
                     subject={"id": 1})
        with hygiene.MutationTransaction(ledger, "evt-autonomous", [subject]) as tx:
            subject.write_text("after", encoding="utf-8")
            tx.commit(autonomous_judgment=True)
        self.assertEqual(
            ledger.completed_mutation_causing(hygiene.artifact_identity(subject)),
            "evt-autonomous",
        )
        subject.write_text("later", encoding="utf-8")
        self.assertIsNone(
            ledger.completed_mutation_causing(hygiene.artifact_identity(subject)))


class SupersessionEventTests(RuntimeHygieneBase):
    def _meta(self, path: Path, slug: str) -> dict:
        return {
            "path": str(path), "slug": slug, "h1": slug.title(),
            "date_created": "2026-07-20",
        }

    def test_judgment_error_causes_zero_subject_mutation(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        other = self.resources / "other.md"
        for path, body in [(source, "source"), (older, "older"), (other, "other")]:
            path.write_text(body, encoding="utf-8")
        candidates = [
            {"newer": self._meta(source, "source"), "older": self._meta(older, "older"),
             "similarity": .9, "entity_overlap": 2, "date_gap_days": 10},
            {"newer": self._meta(source, "source"), "older": self._meta(other, "other"),
             "similarity": .8, "entity_overlap": 1, "date_gap_days": 8},
        ]
        with (
            mock.patch.object(supersession, "_event_news_candidates", return_value=candidates),
            mock.patch.object(supersession.judge, "judge_pair", side_effect=[
                SimpleNamespace(decision="supersede", reason="newer", slot="test"),
                SimpleNamespace(decision="error", reason="model unavailable", slot="test"),
            ]),
            mock.patch.object(supersession.news_res, "apply_supersession") as apply,
        ):
            result = supersession.process_artifact_write(str(source))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["mutation_count"], 0)
        apply.assert_not_called()
        self.assertEqual(source.read_text(), "source")
        self.assertEqual(older.read_text(), "older")

    def test_forged_event_identity_is_rejected_before_judgment(self):
        source = self.resources / "source.md"
        source.write_text("source", encoding="utf-8")
        with (
            mock.patch.object(supersession, "_event_news_candidates") as candidates,
            self.assertRaisesRegex(ValueError, "does not authenticate"),
        ):
            supersession.process_artifact_write(str(source), event_id="evt-forged")
        candidates.assert_not_called()

    def test_apply_error_rolls_back_and_duplicate_does_not_retry(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        source.write_text("source", encoding="utf-8")
        older.write_text("older", encoding="utf-8")
        candidate = {
            "newer": self._meta(source, "source"), "older": self._meta(older, "older"),
            "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
        }

        def mutate_then_fail(*_args, **_kwargs):
            source.write_text("mutated", encoding="utf-8")
            return {"mutated_files": ["source.md"], "errors": ["receipt failed"]}

        with (
            mock.patch.object(supersession, "_event_news_candidates", return_value=[candidate]),
            mock.patch.object(supersession.judge, "judge_pair", return_value=SimpleNamespace(
                decision="supersede", reason="newer", slot="test")),
            mock.patch.object(supersession.news_res, "apply_supersession",
                              side_effect=mutate_then_fail) as apply,
        ):
            first = supersession.process_artifact_write(str(source))
            second = supersession.process_artifact_write(str(source))
        self.assertEqual(first["status"], "failed")
        self.assertEqual(first, second)
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(source.read_text(), "source")

    def test_success_is_idempotent_and_records_autonomous_evidence(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        source.write_text("source", encoding="utf-8")
        older.write_text("older", encoding="utf-8")
        candidate = {
            "newer": self._meta(source, "source"), "older": self._meta(older, "older"),
            "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
        }

        def apply_mutation(*_args, **_kwargs):
            older.write_text("superseded", encoding="utf-8")
            return {"mutated_files": ["older.md"], "errors": []}

        with (
            mock.patch.object(supersession, "_event_news_candidates", return_value=[candidate]),
            mock.patch.object(supersession.judge, "judge_pair", return_value=SimpleNamespace(
                decision="supersede", reason="newer", slot="test")),
            mock.patch.object(supersession.news_res, "apply_supersession",
                              side_effect=apply_mutation) as apply,
            mock.patch.object(supersession.news_res, "refresh_chromadb",
                              return_value={"errors": 0}),
        ):
            first = supersession.process_artifact_write(str(source))
            second = supersession.process_artifact_write(str(source))
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first, second)
        self.assertTrue(first["autonomous_judgment"])
        self.assertFalse(first["human_triage"])
        self.assertEqual(apply.call_count, 1)
        audit = (self.data / "runtime-hygiene" / "events.jsonl").read_text()
        self.assertIn("bounded_neighborhood_judged", audit)
        self.assertIn('"human_triage": false', audit)


if __name__ == "__main__":
    unittest.main()
