"""G1.10 adversarial tests for event-only maintenance."""
from __future__ import annotations

import hashlib
import importlib
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
            # The inbound root is the external Resources folder, not
            # ORA_HOME/Resources — see test_inbound_root_is_the_real_folder.
            mock.patch.object(event_dispatcher, "_resources_root",
                              return_value=Path("/runtime/Resources")),
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

    def test_operational_circuit_breaker_suppresses_only_autonomous_handlers(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "data"
            sentinel = (data / "runtime-hygiene" /
                        event_dispatcher._AUTONOMOUS_HANDLER_SENTINEL)
            sentinel.parent.mkdir(parents=True)
            with mock.patch.object(event_dispatcher._rp, "DATA_DIR_STR", str(data)):
                self.assertTrue(event_dispatcher.autonomous_hygiene_enabled())
                sentinel.touch()
                self.assertFalse(event_dispatcher.autonomous_hygiene_enabled())

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
                mock.patch.object(event_dispatcher._rp, "DATA_DIR_STR",
                                  str(Path(temp) / "data")),
                mock.patch.object(
                    supersession, "process_artifact_write", return_value=failed),
            ):
                result = event_dispatcher.dispatch_paths({str(resource)})
        self.assertEqual(result["supersession_events"], [failed])
        self.assertTrue(any("model unavailable" in value
                            for value in result["errors"]))

    def test_legacy_interval_scheduler_no_longer_exists(self):
        """The retired module is gone, not merely fail-closed.

        It previously survived as a compatibility surface whose every path
        raised. Deletion is the stronger guarantee: there is no scheduler to
        route recurring work to, and the registry file it read is gone too.
        """
        with self.assertRaises(ImportError):
            importlib.import_module("orchestrator.scheduler")
        root = Path(__file__).resolve().parents[2]
        self.assertFalse((root / "orchestrator" / "scheduler.py").exists())
        self.assertFalse((root / "config" / "scheduled-tasks.json").exists())

    def test_schedule_task_tool_surface_is_absent(self):
        """No chat tool may offer recurring scheduling.

        The four registry-management tools outlived the engine and presented a
        control panel for a machine that had been removed.
        """
        from orchestrator import dispatcher
        for name in ("schedule_task", "list_scheduled_tasks",
                     "pause_scheduled_task", "resume_scheduled_task",
                     "remove_scheduled_task"):
            self.assertNotIn(name, dispatcher.TOOL_REGISTRY)

    def test_paths_file_round_trip_survives_hostile_filenames(self):
        """The writer and the hook must agree on the exact path set.

        Both sides are ours, so the contract is only as good as the tests on
        it: a mutation to either serialization was previously undetected. A
        newline is a legal macOS filename character, and the earlier
        newline-delimited form split such a name into two bogus paths and
        bound them into the exactly-once event contract.
        """
        import importlib.util, json as _json, subprocess, sys, tempfile as _tf
        hook = (Path(__file__).resolve().parents[2] / "operations" /
                "g1-10-current" / "macos" / "vault-event-pipeline.py")
        self.assertTrue(hook.is_file(), hook)

        hostile = [
            "/vault/ordinary.md",
            "/vault/two\nlines.md",
            "/vault/trailing space .md",
            "/vault/unicodé — em dash.md",
            "/vault/carriage\rreturn.md",
        ]
        # Writer side, exactly as runtime_event_dispatcher writes it.
        with _tf.NamedTemporaryFile("w", encoding="utf-8", suffix=".paths",
                                    delete=False) as handle:
            _json.dump(hostile, handle)
            paths_file = handle.name
        self.addCleanup(lambda: Path(paths_file).unlink(missing_ok=True))

        # Reader side, loaded from the hook module itself.
        spec = importlib.util.spec_from_file_location("_vep", hook)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_vep"] = module
        self.addCleanup(lambda: sys.modules.pop("_vep", None))
        spec.loader.exec_module(module)

        listed = _json.loads(Path(paths_file).read_text(encoding="utf-8"))
        self.assertEqual(listed, hostile)
        self.assertEqual([x for x in listed if x.strip()], hostile)

        # And the real CLI accepts the file (it rejects on the vault boundary,
        # which proves it parsed all five paths rather than splitting them).
        proc = subprocess.run(
            ["/opt/homebrew/bin/python3", str(hook), "--paths-file", paths_file],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("outside the vault", proc.stdout + proc.stderr)

    def test_hook_prunes_terminal_events_but_keeps_in_flight(self):
        """The state map is rewritten and fsync'd on every step.

        At 4,452 finished events it was 31 MB, so each notification cost
        ~157 MB of fsync for entries nothing reads. Terminal records are
        bounded; anything still running is never dropped.
        """
        import importlib.util, sys
        hook = (Path(__file__).resolve().parents[2] / "operations" /
                "g1-10-current" / "macos" / "vault-event-pipeline.py")
        spec = importlib.util.spec_from_file_location("_vep_prune", hook)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_vep_prune"] = module
        self.addCleanup(lambda: sys.modules.pop("_vep_prune", None))
        spec.loader.exec_module(module)

        state = {"events": {}}
        for n in range(50):
            state["events"][f"done-{n:03d}"] = {
                "status": "completed", "completed_at": f"2026-08-16T00:{n:02d}:00Z",
            }
        state["events"]["still-running"] = {
            "status": "running", "started_at": "2020-01-01T00:00:00Z",
        }
        with mock.patch.object(module, "TERMINAL_EVENT_RETENTION", 10):
            dropped = module._prune_terminal_events(state)

        self.assertEqual(dropped, 40)
        self.assertIn("still-running", state["events"],
                      "an in-flight event must never be pruned")
        remaining = sorted(k for k in state["events"] if k.startswith("done-"))
        self.assertEqual(len(remaining), 10)
        # The newest are kept, so duplicate suppression still covers recent work.
        self.assertEqual(remaining[0], "done-040")
        self.assertEqual(remaining[-1], "done-049")

    def test_inbound_root_is_the_real_folder_not_ora_home(self):
        """The watched inbound root must be the folder documents land in.

        From the G1.10 cutover until 2026-08-16 the dispatcher watched
        ORA_HOME/Resources — a directory that has never existed — so a document
        dropped into the real inbound folder raised no event at all, and the
        interval lane that used to cover it is never started.
        """
        real = Path(event_dispatcher._export.current_resources_dir())
        self.assertEqual(event_dispatcher._resources_root(), real)
        self.assertNotEqual(
            event_dispatcher._resources_root().resolve(),
            (Path(event_dispatcher._rp.ORA_HOME) / "Resources").resolve(),
        )


class LedgerTests(RuntimeHygieneBase):
    def test_deadline_queue_is_interned_by_canonical_data_root(self):
        first = hygiene.deadline_queue(self.data)
        second = hygiene.deadline_queue(self.data / ".." / "data")
        self.assertIs(first, second)
        self.assertEqual(first.storage_root,
                         (self.data / "runtime-hygiene").resolve())

    def test_deadline_ordering_uses_instants_across_mixed_offsets(self):
        queue = hygiene.DeadlineQueue()
        queue.put(
            "later", "2026-07-21T02:00:00-05:00", "test", {"id": "later"},
        )  # 07:00Z
        queue.put(
            "earlier", "2026-07-21T08:00:00+02:00", "test", {"id": "earlier"},
        )  # 06:00Z
        self.assertEqual(queue.next_due()["key"], "earlier")
        stored = queue._load()["deadlines"]
        self.assertEqual(stored["earlier"]["due_at"],
                         "2026-07-21T06:00:00+00:00")
        self.assertEqual(stored["later"]["due_at"],
                         "2026-07-21T07:00:00+00:00")

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

    def test_future_deadline_does_not_fire_when_queue_is_nudged(self):
        """A queue insert must not fire a deadline whose time has not come.

        The worker waits on a condition that is notified by every ``put``. It
        re-read the head record but never re-checked the clock, so any
        unrelated insert that left the head in place dispatched it early —
        and every finalized pipeline trace inserts one. On 2026-08-11 that
        walked the daily-note chain nine days into the future in two bursts,
        writing empty notes for days that had not happened; because an
        existing note is never overwritten, those stubs then permanently
        blocked the real notes.
        """
        queue = hygiene.DeadlineQueue()
        far_future = "2099-01-01T00:00:00+00:00"
        queue.put("deadline-future", far_future, "test", {"id": 9})
        stop = threading.Event()
        fired: list[dict] = []

        def handler(payload):
            fired.append(payload)
            stop.set()
            return {"ok": True}

        def nudge():
            # A later deadline: notifies the worker, leaves the head
            # unchanged. Deliberately does NOT set stop — setting it here
            # would short-circuit the dispatch path this test exists to
            # exercise, and the test would pass with the bug present.
            queue.put("deadline-later", "2099-06-01T00:00:00+00:00",
                      "test", {"id": 10})
            with queue._condition:
                queue._condition.notify_all()

        def end():
            stop.set()
            with queue._condition:
                queue._condition.notify_all()

        threading.Timer(0.25, nudge).start()
        threading.Timer(0.75, end).start()
        queue.run({"test": handler}, stop)

        self.assertEqual(fired, [])
        state = queue._load()["deadlines"]["deadline-future"]
        self.assertEqual(state["status"], "pending")

    def test_oversized_audit_sink_rotates_on_append(self):
        """An append-only sink must not grow without bound.

        ``mac-vault-events.jsonl`` reached 113 MB unrotated. The append is the
        size-threshold event; no clock is involved.
        """
        sink = self.data / "runtime-hygiene" / "big.jsonl"
        sink.parent.mkdir(parents=True, exist_ok=True)
        sink.write_bytes(b"x" * 2048)

        self.assertIsNone(hygiene.rotate_if_oversized(sink, limit_mb=1))
        self.assertTrue(sink.exists())

        archive = hygiene.rotate_if_oversized(sink, limit_mb=0.001)
        self.assertIsNotNone(archive)
        self.assertFalse(sink.exists())
        self.assertTrue(Path(archive).is_file())
        self.assertEqual(Path(archive).read_bytes(), b"x" * 2048)

    def test_rotation_failure_never_breaks_the_append(self):
        """Losing the event is worse than the sink growing."""
        missing = self.data / "runtime-hygiene" / "not-there.jsonl"
        self.assertIsNone(hygiene.rotate_if_oversized(missing, limit_mb=1))
        # An unreadable parent is the realistic failure: it must return, not raise.
        blocked = self.data / "runtime-hygiene" / "blocked.jsonl"
        blocked.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_bytes(b"x" * 4096)
        with mock.patch.object(hygiene.Path, "rename",
                               side_effect=OSError("read-only file system")):
            self.assertIsNone(hygiene.rotate_if_oversized(blocked, limit_mb=0.001))
        self.assertTrue(blocked.exists(), "the sink must survive a failed rotation")

    def test_rotation_never_overwrites_an_existing_archive(self):
        """Two rotations inside one second must not destroy the first archive.

        The stamp has one-second granularity and `Path.rename` replaces its
        destination silently on POSIX, so without a uniquifier a whole
        rotation's evidence disappears with no error.
        """
        sink = self.data / "runtime-hygiene" / "twice.jsonl"
        sink.parent.mkdir(parents=True, exist_ok=True)

        sink.write_bytes(b"first")
        first = hygiene.rotate_if_oversized(sink, limit_mb=0.000001)
        sink.write_bytes(b"second")
        second = hygiene.rotate_if_oversized(sink, limit_mb=0.000001)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), b"first")
        self.assertEqual(Path(second).read_bytes(), b"second")

    def test_rotated_archives_are_bounded(self):
        """Bounding one file while its archives grow forever fixes nothing.

        There is no clock left to prune them — G1.10 removed the retention
        sweeper's interval — so rotation time is the only reliable moment.
        """
        sink = self.data / "runtime-hygiene" / "many.jsonl"
        sink.parent.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(hygiene, "AUDIT_ARCHIVE_KEEP", 3):
            for n in range(8):
                sink.write_bytes(f"gen{n}".encode())
                hygiene.rotate_if_oversized(sink, limit_mb=0.000001)
        archives = sorted(p.name for p in sink.parent.glob("many.jsonl.*"))
        self.assertEqual(len(archives), 3, archives)
        # The survivors must be the NEWEST three, not an arbitrary subset.
        kept = {Path(sink.parent / a).read_bytes() for a in archives}
        self.assertEqual(kept, {b"gen5", b"gen6", b"gen7"})

    def test_malformed_rotation_threshold_falls_back(self):
        """A typo in the env var must not stop the runtime from starting."""
        for bad in ("64MB", "", "  ", "none"):
            with mock.patch.dict("os.environ",
                                 {"ORA_RUNTIME_AUDIT_ROTATE_MB": bad}):
                self.assertEqual(hygiene._audit_rotate_mb(), 32.0)

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

    def test_subject_drift_during_judgment_prevents_all_ora_mutation(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        source.write_text("source", encoding="utf-8")
        older.write_text("older", encoding="utf-8")
        candidate = {
            "newer": self._meta(source, "source"),
            "older": self._meta(older, "older"),
            "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
        }

        def drift_subject(*_args, **_kwargs):
            source.write_text("concurrent subject edit", encoding="utf-8")
            return SimpleNamespace(decision="supersede", reason="newer", slot="test")

        with (
            mock.patch.object(supersession, "_event_news_candidates",
                              return_value=[candidate]),
            mock.patch.object(supersession.judge, "judge_pair",
                              side_effect=drift_subject),
            mock.patch.object(supersession.news_res, "apply_supersession") as apply,
            mock.patch.object(supersession.news_res, "refresh_chromadb") as refresh,
        ):
            result = supersession.process_artifact_write(str(source))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["mutation_count"], 0)
        self.assertIn("drifted before mutation", result["error"])
        self.assertEqual(source.read_text(), "concurrent subject edit")
        self.assertEqual(older.read_text(), "older")
        apply.assert_not_called()
        refresh.assert_not_called()

    def test_candidate_drift_during_judgment_prevents_all_ora_mutation(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        source.write_text("source", encoding="utf-8")
        older.write_text("older", encoding="utf-8")
        candidate = {
            "newer": self._meta(source, "source"),
            "older": self._meta(older, "older"),
            "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
        }

        def drift_neighbor(*_args, **_kwargs):
            older.write_text("concurrent neighbor edit", encoding="utf-8")
            return SimpleNamespace(decision="supersede", reason="newer", slot="test")

        with (
            mock.patch.object(supersession, "_event_news_candidates",
                              return_value=[candidate]),
            mock.patch.object(supersession.judge, "judge_pair",
                              side_effect=drift_neighbor),
            mock.patch.object(supersession.news_res, "apply_supersession") as apply,
        ):
            result = supersession.process_artifact_write(str(source))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(source.read_text(), "source")
        self.assertEqual(older.read_text(), "concurrent neighbor edit")
        apply.assert_not_called()

    def test_multi_candidate_aba_uses_only_authenticated_snapshots(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        other = self.resources / "other.md"
        source.write_text("# Source\nsource-bound", encoding="utf-8")
        older.write_text("# Older\nolder-bound", encoding="utf-8")
        original_other_body = "# Other Authenticated\nother-bound"
        original_other = (
            "---\n"
            "date created: 2026/07/19\n"
            "---\n\n"
            f"{original_other_body}"
        )
        other.write_text(original_other, encoding="utf-8")
        candidates = [
            {
                "newer": self._meta(source, "source"),
                "older": self._meta(older, "older"),
                "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
            },
            {
                "newer": self._meta(source, "source"),
                "older": {
                    **self._meta(other, "other"),
                    "h1": "Unbound index H1",
                    "date_created": "1900-01-01",
                },
                "similarity": .8, "entity_overlap": 1, "date_gap_days": 8,
            },
        ]
        model_calls = []

        def aba_between_model_calls(*args, **_kwargs):
            model_calls.append(args)
            if len(model_calls) == 1:
                other.write_text(
                    "# Other\nother-transient-unbound", encoding="utf-8")
                return SimpleNamespace(
                    decision="skip", reason="first pair", slot="test")
            other.write_text(original_other, encoding="utf-8")
            return SimpleNamespace(
                decision="supersede", reason="second pair", slot="test")

        def apply_mutation(*_args, **_kwargs):
            other.write_text("# Other\nsuperseded", encoding="utf-8")
            return {"mutated_files": ["other.md"], "errors": []}

        with (
            mock.patch.object(supersession, "_event_news_candidates",
                              return_value=candidates),
            mock.patch.object(supersession.judge, "judge_pair",
                              side_effect=aba_between_model_calls),
            mock.patch.object(supersession.news_res, "apply_supersession",
                              side_effect=apply_mutation),
            mock.patch.object(supersession.news_res, "refresh_chromadb",
                              return_value={"errors": 0}),
        ):
            result = supersession.process_artifact_write(str(source))

        self.assertEqual(result["status"], "completed")
        self.assertEqual(model_calls[1][5], original_other_body)
        self.assertEqual(model_calls[1][3], "Other Authenticated")
        self.assertEqual(model_calls[1][4], "2026/07/19")
        self.assertNotIn("other-transient-unbound", repr(model_calls))
        expected_digest = hashlib.sha256(
            original_other.encode("utf-8")
        ).hexdigest()
        self.assertIn(
            expected_digest,
            {item["sha256"] for item in result["judgment_input_identities"]},
        )
        self.assertEqual(other.read_text(encoding="utf-8"),
                         "# Other\nsuperseded")

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
        self.assertIn("judgment_inputs_bound", audit)
        self.assertIn('"human_triage": false', audit)

    def test_failed_index_refresh_restores_index_from_rolled_back_files(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        source.write_text("source", encoding="utf-8")
        older.write_text("older", encoding="utf-8")
        candidate = {
            "newer": self._meta(source, "source"),
            "older": self._meta(older, "older"),
            "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
        }
        index = {"older": "older"}
        refresh_calls = []

        def apply_mutation(*_args, **_kwargs):
            older.write_text("superseded", encoding="utf-8")
            return {"mutated_files": ["older.md"], "errors": []}

        def refresh(_affected):
            index["older"] = older.read_text(encoding="utf-8")
            refresh_calls.append(index["older"])
            return ({"errors": ["simulated index failure"]}
                    if len(refresh_calls) == 1 else {"errors": []})

        with (
            mock.patch.object(supersession, "_event_news_candidates",
                              return_value=[candidate]),
            mock.patch.object(supersession.judge, "judge_pair",
                              return_value=SimpleNamespace(
                                  decision="supersede", reason="newer", slot="test")),
            mock.patch.object(supersession.news_res, "apply_supersession",
                              side_effect=apply_mutation),
            mock.patch.object(supersession.news_res, "refresh_chromadb",
                              side_effect=refresh),
        ):
            result = supersession.process_artifact_write(str(source))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(refresh_calls, ["superseded", "older"])
        self.assertEqual(older.read_text(), "older")
        self.assertEqual(index["older"], "older")
        self.assertEqual(result["index_restoration_receipt"]["affected_slugs"],
                         ["older", "source"])

    def test_failed_index_restoration_surfaces_broken_infrastructure(self):
        source = self.resources / "source.md"
        older = self.resources / "older.md"
        source.write_text("source", encoding="utf-8")
        older.write_text("older", encoding="utf-8")
        candidate = {
            "newer": self._meta(source, "source"),
            "older": self._meta(older, "older"),
            "similarity": .9, "entity_overlap": 2, "date_gap_days": 10,
        }

        def apply_mutation(*_args, **_kwargs):
            older.write_text("superseded", encoding="utf-8")
            return {"mutated_files": ["older.md"], "errors": []}

        with (
            mock.patch.object(supersession, "_event_news_candidates",
                              return_value=[candidate]),
            mock.patch.object(supersession.judge, "judge_pair",
                              return_value=SimpleNamespace(
                                  decision="supersede", reason="newer", slot="test")),
            mock.patch.object(supersession.news_res, "apply_supersession",
                              side_effect=apply_mutation),
            mock.patch.object(supersession.news_res, "refresh_chromadb",
                              return_value={"errors": ["unavailable"]}),
        ):
            result = supersession.process_artifact_write(str(source))
        self.assertEqual(result["status"], "infrastructure_broken")
        self.assertEqual(older.read_text(), "older")
        self.assertIn("restored index refresh failed",
                      result["index_restoration_error"])


if __name__ == "__main__":
    unittest.main()
