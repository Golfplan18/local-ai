"""G1.10 adversarial tests for event-only maintenance."""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_ORCH = str(Path(__file__).resolve().parent.parent)
if _ORCH not in sys.path:
    sys.path.insert(0, _ORCH)

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
        module, _ = self._load_hook("_vep")
        self.addCleanup(lambda: sys.modules.pop("_vep", None))

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
        module, _ = self._load_hook("_vep_prune")
        self.addCleanup(lambda: sys.modules.pop("_vep_prune", None))

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

    @staticmethod
    def _load_hook(alias: str):
        """Import the standalone hook without leaving bytecode behind.

        `operations/g1-10-current/` is hash-bound by the G1.10 operational
        manifest, so a stray __pycache__ inside it fails the manifest test —
        which is the guard doing exactly its job.
        """
        import importlib.util, sys
        hook = (Path(__file__).resolve().parents[2] / "operations" /
                "g1-10-current" / "macos" / "vault-event-pipeline.py")
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec = importlib.util.spec_from_file_location(alias, hook)
            module = importlib.util.module_from_spec(spec)
            sys.modules[alias] = module
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        return module, hook

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
        from orchestrator import slash_commands

        def complete_mutation(
            event_id, path, before, after, *,
            before_mode=0o640, after_mode=0o600,
        ):
            path.write_bytes(before)
            path.chmod(before_mode)
            ledger.claim(event_id=event_id, event_type="test",
                         subject={"id": event_id})
            with hygiene.MutationTransaction(ledger, event_id, [path]) as tx:
                path.write_bytes(after)
                path.chmod(after_mode)
                tx.commit()
            record = ledger.get(event_id)
            return Path(record["rollback_manifest"])

        exact = self.root / "exact.bin"
        before_bytes = b"before\x00authenticated\xffbytes"
        ledger = hygiene.EventLedger()
        exact_manifest_path = complete_mutation(
            "evt-exact", exact, before_bytes, b"after",
        )
        exact_manifest = json.loads(
            exact_manifest_path.read_text(encoding="utf-8")
        )
        exact_snapshot = exact_manifest["snapshots"][0]
        self.assertEqual(exact_snapshot["before_mode"], 0o640)
        self.assertEqual(
            Path(exact_snapshot["backup"]).stat().st_mode & 0o7777,
            0o640,
        )
        self.assertEqual(ledger.get("evt-exact")["after"][0]["mode"], 0o600)
        result = slash_commands.run_runtime_command(
            "/maintenance rollback evt-exact"
        )
        self.assertIn("Rolled back", result)
        self.assertEqual(exact.read_bytes(), before_bytes)
        self.assertEqual(exact.stat().st_mode & 0o7777, 0o640)
        self.assertEqual(ledger.get("evt-exact")["status"], "rolled_back")
        exact_record = ledger.get("evt-exact")
        self.assertNotIn("rollback_operation_id", exact_record)
        self.assertNotIn("rollback_started_at", exact_record)
        self.assertEqual(
            exact_record["rollback_manifest_sha256"],
            hygiene.sha256_file(Path(exact_record["rollback_manifest"])),
        )

        # Upgrade recovery may encounter rollback records created before the
        # manifest digest was independently bound. Those bytes cannot become
        # trusted retrospectively: each legacy event fails closed without
        # touching any referenced bytes and cannot prevent a later
        # authenticated event recovering.
        def legacy_manifest(event_id, path, before):
            rollback_dir = hygiene._root() / "rollback" / event_id
            rollback_dir.mkdir(parents=True)
            backup = rollback_dir / "0000.before"
            backup.write_bytes(before)
            manifest = rollback_dir / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": hygiene.SCHEMA_VERSION,
                "event_id": event_id,
                "prepared_at": "2026-09-01T00:00:00+00:00",
                "snapshots": [{
                    "path": str(path.resolve()),
                    "existed": True,
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "backup": str(backup),
                }],
            }), encoding="utf-8")
            return manifest, backup

        legacy_material = {}
        for status in ("prepared", "applying", "rollback_applying"):
            event_id = f"evt-legacy-{status}"
            path = self.root / f"legacy-{status}.bin"
            before = f"before-{status}".encode()
            after = f"after-{status}".encode()
            path.write_bytes(after)
            ledger.claim(
                event_id=event_id, event_type="test",
                subject={"id": event_id},
            )
            manifest, backup = legacy_manifest(event_id, path, before)
            if status in {"prepared", "applying"}:
                ledger.transition(
                    event_id, {"claimed"}, "prepared",
                    rollback_manifest=str(manifest),
                )
                if status == "applying":
                    ledger.transition(event_id, {"prepared"}, "applying")
            else:
                ledger.transition(
                    event_id, {"claimed"}, "completed",
                    rollback_manifest=str(manifest),
                    after=[{
                        "path": str(path.resolve()), "exists": True,
                        "sha256": hashlib.sha256(after).hexdigest(),
                    }],
                    completed_at="2026-09-01T00:01:00+00:00",
                )
                ledger.transition(
                    event_id, {"completed"}, "rollback_applying",
                )
            legacy_material[event_id] = {
                "path": path, "after": after, "manifest": manifest,
                "manifest_bytes": manifest.read_bytes(), "backup": backup,
                "backup_bytes": backup.read_bytes(),
            }

        actual_refusal = self.root / "actual-call-refusal.bin"
        actual_refusal_manifest = complete_mutation(
            "evt-actual-call-refusal", actual_refusal,
            b"actual-call-before", b"actual-call-after",
        )
        ledger.transition(
            "evt-actual-call-refusal", {"completed"}, "rollback_applying",
        )
        actual_refusal_manifest_value = json.loads(
            actual_refusal_manifest.read_text(encoding="utf-8")
        )
        actual_refusal_backup = Path(
            actual_refusal_manifest_value["snapshots"][0]["backup"]
        )
        actual_refusal_backup_bytes = actual_refusal_backup.read_bytes()

        recoverable = self.root / "later-authenticated.bin"
        recoverable.write_bytes(b"authenticated-before")
        ledger.claim(
            event_id="evt-later-authenticated", event_type="test",
            subject={"id": "evt-later-authenticated"},
        )
        recoverable_tx = hygiene.MutationTransaction(
            ledger, "evt-later-authenticated", [recoverable],
        )
        recoverable_tx.prepare()
        ledger.transition(
            "evt-later-authenticated", {"prepared"}, "applying",
        )
        recoverable.write_bytes(b"authenticated-after")

        real_rollback_completed_event = hygiene.rollback_completed_event
        actual_call_reached = False

        def change_manifest_at_actual_rollback_call(event_id, active_ledger=None):
            nonlocal actual_call_reached
            if event_id == "evt-actual-call-refusal":
                self.assertFalse(actual_call_reached)
                actual_call_reached = True
                actual_refusal_manifest.write_bytes(b"{")
            return real_rollback_completed_event(event_id, active_ledger)

        with mock.patch.object(
            hygiene, "rollback_completed_event",
            side_effect=change_manifest_at_actual_rollback_call,
        ):
            recovered = hygiene.restore_incomplete_events(ledger)

        for event_id, material in legacy_material.items():
            with self.subTest(legacy_restart_status=event_id):
                record = ledger.get(event_id)
                self.assertEqual(record["status"], "failed")
                self.assertNotIn(event_id, recovered)
                self.assertNotIn("rollback_material_retained", record)
                self.assertIn(
                    "refused rollback because rollback material "
                    "authentication failed",
                    record["error"],
                )
                self.assertIn(
                    "did not modify the referenced target, manifest, backups, "
                    "or rollback material",
                    record["error"],
                )
                self.assertEqual(material["path"].read_bytes(), material["after"])
                self.assertEqual(
                    material["manifest"].read_bytes(),
                    material["manifest_bytes"],
                )
                self.assertEqual(
                    material["backup"].read_bytes(), material["backup_bytes"],
                )

        with self.subTest(refusal_at="actual rollback call"):
            refused = ledger.get("evt-actual-call-refusal")
            self.assertTrue(actual_call_reached)
            self.assertEqual(refused["status"], "failed")
            self.assertNotIn("evt-actual-call-refusal", recovered)
            self.assertNotIn("rollback_material_retained", refused)
            self.assertIn(
                "refused rollback because rollback material authentication "
                "failed",
                refused["error"],
            )
            self.assertEqual(actual_refusal.read_bytes(), b"actual-call-after")
            self.assertEqual(actual_refusal_manifest.read_bytes(), b"{")
            self.assertEqual(
                actual_refusal_backup.read_bytes(),
                actual_refusal_backup_bytes,
            )
            self.assertIn("evt-later-authenticated", recovered)
            self.assertEqual(
                recoverable.read_bytes(), b"authenticated-before",
            )
            self.assertEqual(
                ledger.get("evt-later-authenticated")["status"], "failed",
            )

        legacy_completed = self.root / "legacy-completed.bin"
        legacy_completed.write_bytes(b"legacy-current")
        ledger.claim(
            event_id="evt-legacy-completed", event_type="test",
            subject={"id": "evt-legacy-completed"},
        )
        legacy_completed_manifest, legacy_completed_backup = legacy_manifest(
            "evt-legacy-completed", legacy_completed, b"legacy-before",
        )
        ledger.transition(
            "evt-legacy-completed", {"claimed"}, "completed",
            rollback_manifest=str(legacy_completed_manifest),
            after=[{
                "path": str(legacy_completed.resolve()), "exists": True,
                "sha256": hashlib.sha256(b"legacy-current").hexdigest(),
            }],
            completed_at="2026-09-01T00:01:00+00:00",
        )
        retained_manifest = legacy_completed_manifest.read_bytes()
        retained_backup = legacy_completed_backup.read_bytes()
        refusal = slash_commands.run_runtime_command(
            "/maintenance rollback evt-legacy-completed"
        )
        self.assertIn("invalid after-identities", refusal)
        self.assertEqual(legacy_completed.read_bytes(), b"legacy-current")
        self.assertEqual(
            legacy_completed_manifest.read_bytes(), retained_manifest,
        )
        self.assertEqual(legacy_completed_backup.read_bytes(), retained_backup)
        self.assertEqual(
            ledger.get("evt-legacy-completed")["status"], "completed",
        )

        subject = self.root / "subject.md"
        subject.write_text("before", encoding="utf-8")
        ledger.claim(event_id="evt-complete", event_type="test", subject={"id": 1})
        with hygiene.MutationTransaction(ledger, "evt-complete", [subject]) as tx:
            subject.write_text("after", encoding="utf-8")
            tx.commit()
        subject.write_text("later user work", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "drift"):
            hygiene.rollback_completed_event("evt-complete", ledger)
        self.assertEqual(subject.read_text(encoding="utf-8"), "later user work")

        mode_drift = self.root / "mode-drift.bin"
        complete_mutation(
            "evt-mode-drift", mode_drift, b"mode-before", b"mode-after",
            before_mode=0o640, after_mode=0o600,
        )
        mode_drift.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "artifact drift"):
            hygiene.rollback_completed_event("evt-mode-drift", ledger)
        self.assertEqual(mode_drift.read_bytes(), b"mode-after")
        self.assertEqual(mode_drift.stat().st_mode & 0o7777, 0o644)
        self.assertEqual(ledger.get("evt-mode-drift")["status"], "completed")

        # Mutation completion has one finalization boundary. If either its
        # terminal audit or terminal state write fails, context exit restores
        # the before-bytes and neither durable surface may claim completion.
        for event_id, failure_surface in (
            ("evt-commit-audit-failure", "audit"),
            ("evt-commit-state-failure", "state"),
        ):
            with self.subTest(commit_failure=failure_surface):
                commit_subject = self.root / f"{failure_surface}-commit.bin"
                commit_subject.write_bytes(b"before-commit")
                ledger.claim(
                    event_id=event_id, event_type="test",
                    subject={"id": event_id},
                )
                real_atomic_json = hygiene._atomic_json
                real_write = hygiene.os.write
                real_fsync = hygiene.os.fsync
                terminal_audit_write = False
                terminal_audit_fsync_failed = False

                def write_with_terminal_marker(fd, payload):
                    nonlocal terminal_audit_write
                    if (
                        failure_surface == "audit"
                        and b'"kind": "event_completed"' in payload
                        and event_id.encode("utf-8") in payload
                    ):
                        terminal_audit_write = True
                    return real_write(fd, payload)

                def fsync_with_failure(fd):
                    nonlocal terminal_audit_fsync_failed
                    if (
                        terminal_audit_write
                        and not terminal_audit_fsync_failed
                    ):
                        terminal_audit_fsync_failed = True
                        raise OSError("injected mutation terminal audit failure")
                    return real_fsync(fd)

                def state_with_failure(path, value):
                    current = value.get("events", {}).get(event_id, {})
                    if (
                        failure_surface == "state"
                        and Path(path) == ledger.state_file
                        and current.get("status") == "completed"
                    ):
                        raise OSError("injected mutation terminal state failure")
                    return real_atomic_json(path, value)

                with (
                    mock.patch.object(
                        hygiene.os, "write", side_effect=write_with_terminal_marker,
                    ),
                    mock.patch.object(
                        hygiene.os, "fsync", side_effect=fsync_with_failure,
                    ),
                    mock.patch.object(
                        hygiene, "_atomic_json", side_effect=state_with_failure,
                    ),
                ):
                    with self.assertRaisesRegex(
                        OSError, f"terminal {failure_surface} failure",
                    ):
                        with hygiene.MutationTransaction(
                            ledger, event_id, [commit_subject],
                        ) as tx:
                            commit_subject.write_bytes(b"after-commit")
                            tx.commit()
                self.assertEqual(commit_subject.read_bytes(), b"before-commit")
                self.assertEqual(ledger.get(event_id)["status"], "failed")
                terminal_rows = [
                    json.loads(line)
                    for line in ledger.audit_file.read_text(
                        encoding="utf-8",
                    ).splitlines()
                    if line.strip()
                ]
                self.assertFalse(any(
                    row.get("kind") == "event_completed"
                    and row.get("event_id") == event_id
                    for row in terminal_rows
                ))

        for suffix, mutate_manifest, error in (
            ("schema", lambda value: value.update({
                "schema_version": hygiene.SCHEMA_VERSION + 1,
            }), "manifest"),
            ("event", lambda value: value.update({
                "event_id": "evt-substituted",
            }), "manifest"),
            ("paths", lambda value: value["snapshots"][0].update({
                "path": str((self.root / "outside.bin").resolve()),
            }), "manifest"),
        ):
            with self.subTest(manifest=suffix):
                path = self.root / f"manifest-{suffix}.bin"
                event_id = f"evt-manifest-{suffix}"
                manifest_path = complete_mutation(
                    event_id, path, b"original", b"current",
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                mutate_manifest(manifest)
                manifest_path.write_text(
                    json.dumps(manifest), encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, error):
                    hygiene.rollback_completed_event(event_id, ledger)
                self.assertEqual(path.read_bytes(), b"current")
                self.assertEqual(ledger.get(event_id)["status"], "completed")

        backup_subject = self.root / "backup-drift.bin"
        backup_manifest_path = complete_mutation(
            "evt-backup-drift", backup_subject, b"trusted", b"current",
        )
        backup_manifest = json.loads(
            backup_manifest_path.read_text(encoding="utf-8")
        )
        Path(backup_manifest["snapshots"][0]["backup"]).write_bytes(b"substituted")
        with self.assertRaisesRegex(ValueError, "backup drift"):
            hygiene.rollback_completed_event("evt-backup-drift", ledger)
        self.assertEqual(backup_subject.read_bytes(), b"current")
        self.assertEqual(ledger.get("evt-backup-drift")["status"], "completed")

        backup_mode_subject = self.root / "backup-mode-drift.bin"
        backup_mode_manifest_path = complete_mutation(
            "evt-backup-mode-drift", backup_mode_subject,
            b"trusted-mode", b"current-mode",
        )
        backup_mode_manifest = json.loads(
            backup_mode_manifest_path.read_text(encoding="utf-8")
        )
        backup_mode_path = Path(
            backup_mode_manifest["snapshots"][0]["backup"]
        )
        backup_mode_path.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "backup mode drift"):
            hygiene.rollback_completed_event("evt-backup-mode-drift", ledger)
        self.assertEqual(backup_mode_subject.read_bytes(), b"current-mode")
        self.assertEqual(
            backup_mode_subject.stat().st_mode & 0o7777, 0o600,
        )
        self.assertEqual(
            ledger.get("evt-backup-mode-drift")["status"], "completed",
        )

        # The backup digest is not self-authenticating: replacing both the
        # bytes and their adjacent digest still fails the independent digest
        # bound into the EventLedger before mutation.
        circular_subject = self.root / "circular-drift.bin"
        circular_manifest_path = complete_mutation(
            "evt-circular-drift", circular_subject, b"trusted", b"current",
        )
        circular_manifest = json.loads(
            circular_manifest_path.read_text(encoding="utf-8")
        )
        substituted = b"attacker-controlled"
        Path(circular_manifest["snapshots"][0]["backup"]).write_bytes(
            substituted
        )
        circular_manifest["snapshots"][0]["before_sha256"] = (
            hashlib.sha256(substituted).hexdigest()
        )
        circular_manifest_path.write_text(
            json.dumps(circular_manifest), encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "manifest authentication"):
            hygiene.rollback_completed_event("evt-circular-drift", ledger)
        self.assertEqual(circular_subject.read_bytes(), b"current")
        self.assertEqual(
            ledger.get("evt-circular-drift")["status"], "completed",
        )

        # A later restore write can fail after an earlier path changed. The
        # durable in-progress state accepts exactly that before/after mixture,
        # and startup recovery finishes the same rollback.
        partial_a = self.root / "partial-a.bin"
        partial_b = self.root / "partial-b.bin"
        partial_a.write_bytes(b"a-before")
        partial_b.write_bytes(b"b-before")
        ledger.claim(event_id="evt-partial-write", event_type="test",
                     subject={"id": "partial-write"})
        with hygiene.MutationTransaction(
            ledger, "evt-partial-write", [partial_a, partial_b],
        ) as tx:
            partial_a.write_bytes(b"a-after")
            partial_b.write_bytes(b"b-after")
            tx.commit()
        real_restore = hygiene._restore_snapshots

        def restore_one_then_fail(snapshots, restore_bytes):
            ordered = list(snapshots)
            real_restore([ordered[1]], restore_bytes)
            raise OSError("injected second restore failure")

        with mock.patch.object(
            hygiene, "_restore_snapshots", side_effect=restore_one_then_fail,
        ):
            with self.assertRaisesRegex(OSError, "second restore failure"):
                hygiene.rollback_completed_event("evt-partial-write", ledger)
        self.assertEqual(
            ledger.get("evt-partial-write")["status"], "rollback_applying",
        )
        self.assertEqual(
            {partial_a.read_bytes(), partial_b.read_bytes()},
            {b"a-after", b"b-before"},
        )
        self.assertIn(
            "evt-partial-write", hygiene.restore_incomplete_events(ledger),
        )
        self.assertEqual(partial_a.read_bytes(), b"a-before")
        self.assertEqual(partial_b.read_bytes(), b"b-before")
        self.assertEqual(
            ledger.get("evt-partial-write")["status"], "rolled_back",
        )

        # An unlink failure is recoverable by the same operation: an already
        # restored existing file remains valid while the created file waits
        # for the retry to remove it.
        created = self.root / "a-created.bin"
        existing = self.root / "z-existing.bin"
        existing.write_bytes(b"z-before")
        ledger.claim(event_id="evt-partial-unlink", event_type="test",
                     subject={"id": "partial-unlink"})
        with hygiene.MutationTransaction(
            ledger, "evt-partial-unlink", [created, existing],
        ) as tx:
            created.write_bytes(b"created-after")
            existing.write_bytes(b"z-after")
            tx.commit()
        real_restore = hygiene._restore_snapshots

        def restore_existing_then_fail_unlink(snapshots, restore_bytes):
            existing_snapshot = next(
                snapshot for snapshot in snapshots if snapshot.existed
            )
            real_restore([existing_snapshot], restore_bytes)
            raise OSError("injected unlink failure")

        with mock.patch.object(
            hygiene, "_restore_snapshots",
            side_effect=restore_existing_then_fail_unlink,
        ):
            with self.assertRaisesRegex(OSError, "unlink failure"):
                hygiene.rollback_completed_event("evt-partial-unlink", ledger)
        self.assertEqual(existing.read_bytes(), b"z-before")
        self.assertEqual(created.read_bytes(), b"created-after")
        self.assertEqual(
            ledger.get("evt-partial-unlink")["status"], "rollback_applying",
        )
        hygiene.rollback_completed_event("evt-partial-unlink", ledger)
        self.assertFalse(created.exists())
        self.assertEqual(
            ledger.get("evt-partial-unlink")["status"], "rolled_back",
        )

        # Terminal evidence is ordered before the terminal state. Either sink
        # may fail after the bytes are restored; the in-progress state remains
        # retryable and never claims a rollback that lacks durable evidence.
        audit_subject = self.root / "terminal-audit.bin"
        complete_mutation(
            "evt-terminal-audit", audit_subject, b"before", b"after",
        )
        real_append = ledger._append

        def fail_terminal_audit(record):
            if record.get("kind") == "event_rolled_back":
                raise OSError("injected terminal audit failure")
            return real_append(record)

        with mock.patch.object(
            ledger, "_append", side_effect=fail_terminal_audit,
        ):
            with self.assertRaisesRegex(OSError, "terminal audit failure"):
                hygiene.rollback_completed_event("evt-terminal-audit", ledger)
        self.assertEqual(audit_subject.read_bytes(), b"before")
        self.assertEqual(
            ledger.get("evt-terminal-audit")["status"], "rollback_applying",
        )
        hygiene.rollback_completed_event("evt-terminal-audit", ledger)
        self.assertEqual(
            ledger.get("evt-terminal-audit")["status"], "rolled_back",
        )

        state_subject = self.root / "terminal-state.bin"
        complete_mutation(
            "evt-terminal-state", state_subject, b"before", b"after",
        )
        real_atomic_json = hygiene._atomic_json

        def fail_terminal_state(path, value):
            record = value.get("events", {}).get("evt-terminal-state", {})
            if Path(path) == ledger.state_file and record.get("status") == "rolled_back":
                raise OSError("injected terminal state failure")
            return real_atomic_json(path, value)

        with mock.patch.object(
            hygiene, "_atomic_json", side_effect=fail_terminal_state,
        ):
            with self.assertRaisesRegex(OSError, "terminal state failure"):
                hygiene.rollback_completed_event("evt-terminal-state", ledger)
        self.assertEqual(state_subject.read_bytes(), b"before")
        self.assertEqual(
            ledger.get("evt-terminal-state")["status"], "rollback_applying",
        )
        terminal_rows = [
            json.loads(line)
            for line in ledger.audit_file.read_text(
                encoding="utf-8",
            ).splitlines()
            if line.strip()
        ]
        self.assertFalse(any(
            row.get("kind") == "event_rolled_back"
            and row.get("event_id") == "evt-terminal-state"
            for row in terminal_rows
        ))
        hygiene.rollback_completed_event("evt-terminal-state", ledger)
        terminal_state = ledger.get("evt-terminal-state")
        self.assertEqual(terminal_state["status"], "rolled_back")
        self.assertNotIn("rollback_operation_id", terminal_state)
        self.assertNotIn("rollback_started_at", terminal_state)
        # Direct terminal retry is idempotent and cannot append duplicate
        # evidence after the compensated state-write failure above.
        self.assertEqual(
            ledger.finalize_rollback("evt-terminal-state"), terminal_state,
        )
        terminal_rows = [
            json.loads(line)
            for line in ledger.audit_file.read_text(
                encoding="utf-8",
            ).splitlines()
            if line.strip()
        ]
        self.assertEqual(sum(
            row.get("kind") == "event_rolled_back"
            and row.get("event_id") == "evt-terminal-state"
            for row in terminal_rows
        ), 1)

        # A campaign's index refresh is derived from committed file/log
        # truth. Refresh failure is recorded after commit and never causes a
        # second refresh or rolls authenticated bytes back underneath it.
        news_source = self.resources / "campaign-source.md"
        news_target = self.resources / "campaign-target.md"
        news_source.write_text("# Source\n\nnew", encoding="utf-8")
        news_target.write_text("# Target\n\nold", encoding="utf-8")
        candidate = {
            "newer": {
                "path": str(news_source), "slug": "campaign-source",
                "h1": "Source", "date_created": "2026-08-02",
            },
            "older": {
                "path": str(news_target), "slug": "campaign-target",
                "h1": "Target", "date_created": "2026-08-01",
            },
            "similarity": 0.9, "entity_overlap": 2, "date_gap_days": 1,
        }
        campaign_id = "post-commit-index-failure"
        campaign_event_id = hygiene.event_identity(
            "news_supersession.historical_campaign",
            {"campaign_id": campaign_id, "kind": "news_supersession",
             "ceiling": supersession.MAX_NEWS_PAIRS},
        )
        refresh_states = []

        def apply_campaign_mutation(**_kwargs):
            news_target.write_text("committed target", encoding="utf-8")
            return {"errors": [], "mutated_files": [str(news_target)]}

        def fail_campaign_refresh(_slugs):
            refresh_states.append(
                hygiene.EventLedger().get(campaign_event_id)["status"]
            )
            raise RuntimeError("injected post-commit index failure")

        with (
            mock.patch.object(
                supersession.news_det, "build_resources_index", return_value={},
            ),
            mock.patch.object(
                supersession.news_det, "_load_resolved_pair_set",
                return_value=set(),
            ),
            mock.patch.object(
                supersession.news_det, "detect_topic_cluster",
                return_value=[candidate],
            ),
            mock.patch.object(
                supersession.judge, "judge_pair",
                return_value=SimpleNamespace(
                    decision="supersede", reason="newer", slot="test",
                ),
            ),
            mock.patch.object(
                supersession.news_res, "apply_supersession",
                side_effect=apply_campaign_mutation,
            ),
            mock.patch.object(
                supersession.news_res, "refresh_chromadb",
                side_effect=fail_campaign_refresh,
            ) as refresh,
        ):
            campaign_result = supersession.task_news_supersession(
                campaign_id=campaign_id,
            )
        self.assertFalse(campaign_result.success)
        self.assertIn("mutation committed", campaign_result.message)
        self.assertEqual(refresh_states, ["completed"])
        refresh.assert_called_once_with({"campaign-source", "campaign-target"})
        self.assertEqual(
            news_target.read_text(encoding="utf-8"), "committed target",
        )
        campaign_record = hygiene.EventLedger().get(campaign_event_id)
        self.assertEqual(campaign_record["status"], "completed")
        self.assertFalse(campaign_record["index_refreshed"])
        self.assertIn("post-commit", campaign_record["index_error"])

        with self.assertRaisesRegex(RuntimeError, "legacy news resolver apply"):
            supersession.news_res.run_resolver(dry_run=False)

        race_subject = self.root / "race.bin"
        complete_mutation(
            "evt-race", race_subject, b"before", b"after",
        )
        identity_checked = threading.Event()
        writer_attempted = threading.Event()
        errors = []
        rollback_result = []
        real_identity = hygiene.artifact_identity

        def pause_after_locked_identity(path):
            identity = real_identity(path)
            if Path(path).resolve() == race_subject.resolve():
                identity_checked.set()
                if not writer_attempted.wait(2):
                    raise AssertionError("cooperating writer did not attempt its lock")
            return identity

        def rollback_worker():
            try:
                rollback_result.append(
                    hygiene.rollback_completed_event("evt-race", ledger)
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        def later_writer():
            try:
                if not identity_checked.wait(2):
                    raise AssertionError("rollback did not reach its locked identity check")
                writer_attempted.set()
                with hygiene.mutation_path_locks([race_subject]):
                    race_subject.write_bytes(b"later writer")
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        with mock.patch.object(
            hygiene, "artifact_identity", side_effect=pause_after_locked_identity,
        ):
            rollback_thread = threading.Thread(target=rollback_worker)
            writer_thread = threading.Thread(target=later_writer)
            rollback_thread.start()
            writer_thread.start()
            rollback_thread.join(3)
            writer_thread.join(3)
        self.assertFalse(rollback_thread.is_alive())
        self.assertFalse(writer_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(rollback_result[0]["status"], "rolled_back")
        self.assertEqual(race_subject.read_bytes(), b"later writer")

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


class MirrorExclusionTests(unittest.TestCase):
    """The MSI News mirror is machine-synced output, not a vault write.

    Treating a mirror refresh as a user edit is self-sustaining: the cloud
    sync writes ~17k files, the notification fires, the handler runs
    vault_git_sync + vault_cloud_sync, and the sync writes them again. The
    loop was invisible until 2026-08-16 only because a batch that size
    overflowed the OS argument limit and killed the lane before it could
    recur.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "vault"
        (self.vault / "MSI News").mkdir(parents=True)
        (self.vault / "Projects" / "Ora").mkdir(parents=True)
        (self.vault / "Notes" / "MSI News").mkdir(parents=True)
        patcher = mock.patch.object(
            event_dispatcher._rp, "VAULT_STR", str(self.vault))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mirror_writes_are_not_actionable(self):
        article = self.vault / "MSI News" / "2024-05-14-some-article.md"
        article.write_text("# x\n", encoding="utf-8")
        self.assertFalse(event_dispatcher._actionable(str(article)))

    def test_ordinary_vault_writes_remain_actionable(self):
        note = self.vault / "Projects" / "Ora" / "Framework — Thing.md"
        note.write_text("# x\n", encoding="utf-8")
        self.assertTrue(event_dispatcher._actionable(str(note)))

    def test_exclusion_is_anchored_at_the_vault_root(self):
        """A same-named folder deeper in the tree is still the user's work."""
        note = self.vault / "Notes" / "MSI News" / "my own thoughts.md"
        note.write_text("# x\n", encoding="utf-8")
        self.assertTrue(event_dispatcher._actionable(str(note)))

    def test_a_mirror_only_batch_dispatches_nothing(self):
        """The exact shape that drove the loop: every path in the mirror."""
        paths = set()
        for n in range(50):
            p = self.vault / "MSI News" / f"2024-01-{n:02d}-article.md"
            p.write_text("# x\n", encoding="utf-8")
            paths.add(str(p))
        inert = {
            "oversight_events": SimpleNamespace(emit=lambda _e: None),
            "ped_watcher": SimpleNamespace(sweep=lambda: []),
            "corpus_watcher": SimpleNamespace(sweep=lambda: []),
            "workflow_spec_sweeper": SimpleNamespace(sweep=lambda **_k: []),
            "revisit_sweeper": SimpleNamespace(
                sweep=lambda **_k: [], register_age_review_deadlines=lambda: []),
        }
        with (
            mock.patch.dict("sys.modules", inert),
            mock.patch.object(event_dispatcher._rp, "DATA_DIR_STR",
                              str(Path(self.temp.name) / "data")),
            mock.patch.object(event_dispatcher._rp, "ORA_HOME",
                              str(Path(self.temp.name) / "runtime")),
        ):
            result = event_dispatcher.dispatch_paths(paths)
        self.assertEqual(result["paths"], [])
        self.assertIsNone(result["operational_hook"],
                          "a mirror refresh must not run the sync pipeline")


class EventRecordFormatTests(unittest.TestCase):
    """The event contract is written once, not on every state transition.

    A batch carries one identity per changed file. Re-emitting that list at
    claim, resume, each step boundary and completion multiplied one event's
    write cost by its transition count — and the state file, rewritten and
    fsync'd in full each time, carried it too. Measured at the 17,731-path
    batch that drove the 2026-08-17 mirror loop: audit 23.3 MB -> 3.1 MB,
    state 5.45 MB -> ~0.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        (self.vault / "Notes").mkdir(parents=True)
        env = mock.patch.dict("os.environ", {
            "ORA_VAULT": str(self.vault), "ORA_HOME": str(self.root / "ora")})
        env.start()
        self.addCleanup(env.stop)
        self.module = self._load_hook()
        # The real step scripts hardcode the live vault and reach the network;
        # this suite is about record shape, so they are stubbed.
        self.module._run = lambda name, argv: {
            "name": name, "argv": argv, "exit_status": 0,
            "stdout_tail": "", "stderr_tail": ""}
        self.hygiene = self.root / "ora" / "data" / "runtime-hygiene"

    def _load_hook(self):
        import importlib.util, sys
        hook = (Path(__file__).resolve().parents[2] / "operations" /
                "g1-10-current" / "macos" / "vault-event-pipeline.py")
        previous = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            alias = f"_vep_fmt_{id(self)}"
            spec = importlib.util.spec_from_file_location(alias, hook)
            module = importlib.util.module_from_spec(spec)
            sys.modules[alias] = module
            self.addCleanup(lambda: sys.modules.pop(alias, None))
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        return module

    def _write_batch(self, count):
        paths = []
        for n in range(count):
            f = self.vault / "Notes" / f"n{n:05d}.md"
            f.write_text("# x\n", encoding="utf-8")
            paths.append(str(f))
        return paths

    def _run_event(self, paths):
        import io, contextlib
        pf = self.root / "batch.json"
        pf.write_text(json.dumps(paths), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = self.module.main(["--paths-file", str(pf)])
        return rc

    def _audit(self):
        text = (self.hygiene / "mac-vault-events.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def _state_records(self):
        raw = (self.hygiene / "mac-vault-event-state.json").read_text(encoding="utf-8")
        return json.loads(raw)["events"]

    def test_contract_is_written_exactly_once(self):
        paths = self._write_batch(30)
        self.assertEqual(self._run_event(paths), 0)
        lines = self._audit()
        self.assertGreater(len(lines), 1, "expected several transitions")
        carrying = [r for r in lines if "identities" in r]
        self.assertEqual(len(carrying), 1)
        self.assertEqual(carrying[0]["status"], "claimed")
        self.assertEqual(len(carrying[0]["identities"]), len(paths))
        for r in lines:
            if r is carrying[0]:
                continue
            self.assertNotIn("identities", r)
            self.assertNotIn("paths", r)
            self.assertIn("identities_digest", r)

    def test_state_never_holds_the_identity_list(self):
        self.assertEqual(self._run_event(self._write_batch(30)), 0)
        record = next(iter(self._state_records().values()))
        self.assertNotIn("identities", record)
        self.assertNotIn("paths", record)
        self.assertEqual(record["path_count"], 30)
        self.assertRegex(record["identities_digest"], r"^[0-9a-f]{64}$")

    def test_state_size_does_not_scale_with_batch_size(self):
        """The state file is rewritten and fsync'd on every transition."""
        self.assertEqual(self._run_event(self._write_batch(2000)), 0)
        size = (self.hygiene / "mac-vault-event-state.json").stat().st_size
        self.assertLess(size, 8 * 1024, f"state grew to {size} bytes for 2000 paths")

    def test_drift_after_claim_is_still_refused(self):
        """Digest comparison must be no weaker than comparing the lists."""
        paths = self._write_batch(5)
        self.assertEqual(self._run_event(paths), 0)
        event_id = next(iter(self._state_records()))
        # Same paths, changed bytes -> a different contract for the same id.
        Path(paths[0]).write_text("# mutated\n", encoding="utf-8")
        pf = self.root / "retry.json"
        pf.write_text(json.dumps(paths), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "drifted"):
            self.module.main(["--event-id", event_id, "--paths-file", str(pf)])

    def test_legacy_inline_record_is_accepted_and_normalised(self):
        """A record claimed before this change must still resume."""
        paths = self._write_batch(4)
        identities = self.module._event_contract(paths)
        digest = self.module._identities_digest(identities)
        event_id = self.module._issue_event_id(identities)
        legacy = {
            "event_id": event_id,
            "identities": identities,                       # old shape
            "paths": [i["path"] for i in identities],       # old shape
            "status": "running",
            "steps": [],
            "started_at": "2026-08-01T00:00:00+00:00",
        }
        self.hygiene.mkdir(parents=True, exist_ok=True)
        (self.hygiene / "mac-vault-event-state.json").write_text(
            json.dumps({"schema_version": 1, "events": {event_id: legacy}}),
            encoding="utf-8")

        self.assertEqual(self.module._record_digest(legacy), digest)
        pf = self.root / "resume.json"
        pf.write_text(json.dumps(paths), encoding="utf-8")
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            rc = self.module.main(["--event-id", event_id, "--paths-file", str(pf)])
        self.assertEqual(rc, 0)
        resumed = self._state_records()[event_id]
        self.assertEqual(resumed["status"], "completed")
        self.assertNotIn("identities", resumed)
        self.assertNotIn("paths", resumed)
        self.assertEqual(resumed["identities_digest"], digest)
        self.assertEqual(resumed["path_count"], 4)


class LedgerRecordFormatTests(RuntimeHygieneBase):
    """EventLedger writes each fact once, and bounds what it keeps resident.

    The state file is rewritten and fsync'd in full on every claim and
    transition, so both the per-record size and the record count are per-event
    write costs. By 2026-08-17 it held 4,311 finished records in 3.21 MB, of
    which `subject` alone was 882 KB — re-emitted into the audit log on every
    transition as well.
    """

    def _claim(self, ledger, n, *, subject=None):
        subject = subject or {"path": f"/vault/Notes/n{n}.md", "sha256": f"{n:064x}"}
        return ledger.claim(event_id=f"evt-{n:05d}",
                            event_type="test.artifact_written", subject=subject)

    def _audit_lines(self, ledger):
        text = ledger.audit_file.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def test_transition_lines_carry_the_delta_not_the_whole_record(self):
        ledger = hygiene.EventLedger()
        self._claim(ledger, 1)
        ledger.transition("evt-00001", {"claimed"}, "prepared", rollback_manifest={"a": 1})
        ledger.transition("evt-00001", {"prepared"}, "completed", after=[{"path": "/x"}])

        lines = self._audit_lines(ledger)
        claimed = [l for l in lines if l.get("kind") == "event_claimed"]
        self.assertEqual(len(claimed), 1)
        self.assertIn("subject", claimed[0])
        self.assertIn("event_type", claimed[0])

        for line in lines:
            if line.get("kind") == "event_claimed":
                continue
            self.assertNotIn("subject", line, line)
            self.assertNotIn("event_type", line, line)
            self.assertIn("subject_digest", line)
        # A field appears on the transition that introduced it, and not again.
        self.assertEqual(sum("rollback_manifest" in l for l in lines), 1)
        self.assertEqual(sum("after" in l for l in lines), 1)

    def test_subject_digest_joins_a_transition_line_to_its_claim(self):
        ledger = hygiene.EventLedger()
        subject = {"path": "/vault/Notes/joined.md", "sha256": "a" * 64}
        ledger.claim(event_id="evt-join", event_type="t", subject=subject)
        ledger.transition("evt-join", {"claimed"}, "completed")
        line = [l for l in self._audit_lines(ledger) if l.get("kind") == "event_completed"][0]
        self.assertEqual(line["subject_digest"], hygiene.subject_digest(subject))

    def test_state_record_and_return_value_are_unchanged(self):
        """Only the audit shape changed; state stays the accumulated record."""
        ledger = hygiene.EventLedger()
        self._claim(ledger, 2)
        result = ledger.transition("evt-00002", {"claimed"}, "completed",
                                   after=[{"path": "/y", "sha256": "b" * 64}])
        self.assertEqual(result["status"], "completed")
        self.assertIn("subject", result)
        stored = ledger.get("evt-00002")
        self.assertIn("subject", stored)
        self.assertIn("after", stored)

    def test_finished_records_are_bounded(self):
        ledger = hygiene.EventLedger()
        with mock.patch.object(hygiene, "LEDGER_TERMINAL_RETENTION", 10):
            for n in range(40):
                self._claim(ledger, n)
                ledger.transition(f"evt-{n:05d}", {"claimed"}, "completed")
            self._claim(ledger, 99)          # the claim that triggers the prune
        events = json.loads(ledger.state_file.read_text())["events"]
        terminal = [k for k, r in events.items() if r.get("status") == "completed"]
        self.assertEqual(len(terminal), 10)
        # The newest survive, so recent history stays inspectable.
        self.assertIn("evt-00039", events)
        self.assertNotIn("evt-00000", events)

    def test_autonomous_judgment_records_are_never_pruned(self):
        """These back the self-write suppression join, so they must survive.

        completed_mutation_causing scans them to recognise Ora's own
        rollback-protected writes when the OS reports them back. Dropping one
        would let a bounded autonomous judgment recurse into another.
        """
        ledger = hygiene.EventLedger()
        auto_subject = {"path": "/vault/Resources/auto.md", "sha256": "c" * 64}
        after = [{"path": "/vault/Resources/auto.md", "sha256": "d" * 64, "exists": True}]
        ledger.claim(event_id="evt-auto", event_type="news_supersession.artifact_written",
                     subject=auto_subject)
        ledger.transition("evt-auto", {"claimed"}, "completed",
                          autonomous_judgment=True, after=after)

        with mock.patch.object(hygiene, "LEDGER_TERMINAL_RETENTION", 5):
            for n in range(60):
                self._claim(ledger, n)
                ledger.transition(f"evt-{n:05d}", {"claimed"}, "completed")
            self._claim(ledger, 999)

        events = json.loads(ledger.state_file.read_text())["events"]
        self.assertIn("evt-auto", events, "the self-write guard's record was pruned")
        # And the guard itself still resolves.
        self.assertEqual(
            ledger.completed_mutation_causing(
                {"path": "/vault/Resources/auto.md", "sha256": "d" * 64}),
            "evt-auto",
        )

    def test_in_flight_records_are_never_pruned(self):
        ledger = hygiene.EventLedger()
        ledger.claim(event_id="evt-open", event_type="t", subject={"path": "/open"})
        ledger.transition("evt-open", {"claimed"}, "applying")
        with mock.patch.object(hygiene, "LEDGER_TERMINAL_RETENTION", 2):
            for n in range(20):
                self._claim(ledger, n)
                ledger.transition(f"evt-{n:05d}", {"claimed"}, "completed")
            self._claim(ledger, 888)
        events = json.loads(ledger.state_file.read_text())["events"]
        self.assertIn("evt-open", events)
        self.assertEqual(events["evt-open"]["status"], "applying")
