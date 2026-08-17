"""Tests for oversight_daemon — lane split, sweep-overrun logging, watchdog.

Covers the survivability work from the 2026-06-12 incident: a maintenance
task wedged the single shared daemon thread for hours, every watcher
heartbeat went stale, and the health check injected a degraded banner into
every chat response. The daemon now runs fast watchers and slow mechanical
sweeps on separate lanes, logs sweeps that overrun their interval, and a
watchdog dumps the stack of a stalled lane thread and restarts the lane.

Run::

    /opt/homebrew/bin/python3 -m unittest orchestrator.tests.test_oversight_daemon -v
"""
from __future__ import annotations

import contextlib
import io
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import oversight_daemon as od  # noqa: E402
from orchestrator import runtime_hygiene  # noqa: E402
from oversight_sandbox import redirect_oversight_logs  # noqa: E402


class RuntimePathTests(unittest.TestCase):
    def test_default_vault_path_delegates_to_shared_resolver(self):
        target = Path("/tmp/redirected-oversight-vault")
        with mock.patch.object(od._rp, "vault_dir", return_value=target):
            self.assertEqual(od._vault_path(), str(target))

    def test_scan_pruning_is_separator_independent(self):
        dirs = ["Archive", ".obsidian", "Sessions", "Projects", "Notes"]
        od._prune_scan_dirs(dirs)
        self.assertEqual(dirs, ["Projects", "Notes"])

    def test_runtime_health_reads_actual_blocking_lanes(self):
        daemon = od.OversightDaemon()
        alive = mock.MagicMock()
        alive.is_alive.return_value = True
        daemon._running = True
        daemon._event_thread = alive
        daemon._deadline_thread = alive
        with mock.patch.object(od, "_daemon", daemon):
            health = od.runtime_health()
        self.assertEqual(
            {k: health[k] for k in ("running", "event_lane", "deadline_lane")},
            {"running": True, "event_lane": True, "deadline_lane": True},
        )
        # Liveness alone cannot distinguish a healthy lane from one the
        # watchdog keeps resurrecting, so the contract also carries restart
        # counts. A never-restarted daemon reports them empty.
        self.assertEqual(health["lane_restarts"], {})
        self.assertEqual(health["lane_restart_at"], {})

    def test_runtime_health_reports_watchdog_restart_counts(self):
        daemon = od.OversightDaemon()
        alive = mock.MagicMock()
        alive.is_alive.return_value = True
        daemon._running = True
        daemon._event_thread = alive
        daemon._deadline_thread = alive
        daemon._record_restart("event_lane")
        daemon._record_restart("event_lane")
        with mock.patch.object(od, "_daemon", daemon):
            health = od.runtime_health()
        # Alive AND repeatedly restarted — the crash-loop shape that went
        # unreported for 2,257 event-lane deaths before 2026-08-16.
        self.assertTrue(health["event_lane"])
        self.assertEqual(health["lane_restarts"]["event_lane"], 2)
        self.assertIn("event_lane", health["lane_restart_at"])

    def test_runtime_health_when_stopped_carries_empty_restart_maps(self):
        with mock.patch.object(od, "_daemon", None):
            health = od.runtime_health()
        self.assertFalse(health["running"])
        self.assertEqual(health["lane_restarts"], {})
        self.assertEqual(health["lane_restart_at"], {})

    def test_startup_recovers_exact_retention_intents_before_lanes_start(self):
        daemon = od.OversightDaemon()
        queue = mock.MagicMock()
        thread = mock.MagicMock()
        with (
            mock.patch.dict(
                "sys.modules", {"oversight_router": mock.MagicMock()},
            ),
            mock.patch.object(runtime_hygiene, "deadline_queue", return_value=queue),
            mock.patch.object(
                runtime_hygiene, "recover_retention_intents",
                return_value={"registered": ["intent-a"], "failed": []},
            ) as recover,
            mock.patch.object(daemon, "_ensure_daily_note_deadline") as daily,
            mock.patch.object(od.threading, "Thread", return_value=thread),
        ):
            daemon.start()
        recover.assert_called_once_with(queue=queue)
        daily.assert_called_once_with()
        self.assertEqual(thread.start.call_count, 4)

    def test_daily_deadline_uses_persisted_day_and_chains_missed_day(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        completed = mock.MagicMock(success=True, message="wrote exact day")
        with mock.patch(
            "orchestrator.tools.daily_note.task_daily_note",
            return_value=completed,
        ) as task:
            receipt = daemon._handle_daily_note_deadline({
                "completed_date": "2026-07-19",
                "timezone": "America/Los_Angeles",
            })
        task.assert_called_once_with(date_str="2026-07-19")
        self.assertEqual(receipt["completed_date"], "2026-07-19")
        args = daemon._deadline_queue.put.call_args.args
        self.assertTrue(args[0].startswith("daily-note-v2:2026-07-20:"))
        self.assertEqual(args[2], "daily_note")
        self.assertEqual(args[3], {
            "completed_date": "2026-07-20",
            "timezone": "America/Los_Angeles",
        })

    def test_failed_daily_deadline_still_chains_distinct_next_day(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        failed = mock.MagicMock(success=False, message="bounded failure")
        with mock.patch(
            "orchestrator.tools.daily_note.task_daily_note", return_value=failed,
        ), self.assertRaisesRegex(RuntimeError, "bounded failure"):
            daemon._handle_daily_note_deadline({
                "completed_date": "2026-07-19",
                "timezone": "America/Los_Angeles",
            })
        self.assertTrue(
            daemon._deadline_queue.put.call_args.args[0].startswith(
                "daily-note-v2:2026-07-20:"
            )
        )

    def test_legacy_daily_deadline_resolves_named_zone_before_chaining(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        completed = mock.MagicMock(success=True, message="legacy completed")
        with (
            mock.patch.object(
                od, "_local_timezone_name", return_value="America/Los_Angeles",
            ),
            mock.patch(
                "orchestrator.tools.daily_note.task_daily_note",
                return_value=completed,
            ),
        ):
            daemon._handle_daily_note_deadline({"completed_date": "2026-07-19"})
        self.assertEqual(
            daemon._deadline_queue.put.call_args.args[3]["timezone"],
            "America/Los_Angeles",
        )

    def test_pending_fixed_offset_deadline_is_atomically_replaced(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        daemon._deadline_queue.get.return_value = {
            "key": "daily-note:2026-03-08", "status": "pending",
        }
        daemon._ensure_daily_note_deadline(
            "2026-03-08", timezone_name="America/Los_Angeles",
        )
        daemon._deadline_queue.cancel.assert_called_once_with(
            "daily-note:2026-03-08",
            reason=("migrated from fixed-offset calendar deadline to "
                    "named timezone America/Los_Angeles"),
        )
        args = daemon._deadline_queue.put.call_args.args
        self.assertEqual(args[1], "2026-03-09T00:00:00-07:00")
        self.assertEqual(args[3]["timezone"], "America/Los_Angeles")

    def test_calendar_deadline_recomputes_both_dst_transitions(self):
        cases = {
            "2026-03-07": "2026-03-08T00:00:00-08:00",
            "2026-03-08": "2026-03-09T00:00:00-07:00",
            "2026-10-31": "2026-11-01T00:00:00-07:00",
            "2026-11-01": "2026-11-02T00:00:00-08:00",
        }
        for completed, expected in cases.items():
            with self.subTest(completed=completed):
                self.assertEqual(
                    od._calendar_midnight_after(
                        completed, "America/Los_Angeles",
                    ).isoformat(),
                    expected,
                )


class MaybeRunTests(unittest.TestCase):
    def test_runs_when_due_and_records_last_run(self):
        d = od.OversightDaemon()
        calls = []
        d._maybe_run("x", 60, 1000.0, lambda: calls.append(1))
        self.assertEqual(calls, [1])
        self.assertEqual(d._last_run["x"], 1000.0)

    def test_skips_when_not_due(self):
        d = od.OversightDaemon()
        d._last_run["x"] = 1000.0
        calls = []
        d._maybe_run("x", 60, 1030.0, lambda: calls.append(1))
        self.assertEqual(calls, [])

    def test_logs_when_sweep_overruns_interval(self):
        d = od.OversightDaemon()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            d._maybe_run("slowpoke", 0, time.time(), lambda: time.sleep(0.02))
        out = buf.getvalue()
        self.assertIn("slowpoke sweep took", out)
        self.assertIn("longer than its 0s interval", out)

    def test_no_log_when_sweep_fits_interval(self):
        d = od.OversightDaemon()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            d._maybe_run("quick", 60, time.time(), lambda: None)
        self.assertEqual(buf.getvalue(), "")


class WatchdogLaneTests(unittest.TestCase):
    def _fake_thread(self, alive=True, ident=999999999):
        t = mock.MagicMock()
        t.is_alive.return_value = alive
        t.ident = ident
        return t

    def test_stalled_lane_restarts_and_dumps_stack(self):
        d = od.OversightDaemon()
        d._running = True
        restart = mock.MagicMock()
        thread = self._fake_thread(alive=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            d._check_lane("fast", thread, time.time() - 10_000, 300, restart)
        restart.assert_called_once()
        out = buf.getvalue()
        self.assertIn("WATCHDOG: fast lane has not completed a loop iteration", out)
        # ident doesn't match a real thread, so the dump reports no frame
        self.assertIn("no frame found", out)

    def test_fresh_lane_left_alone(self):
        d = od.OversightDaemon()
        d._running = True
        restart = mock.MagicMock()
        d._check_lane("fast", self._fake_thread(alive=True), time.time(), 300, restart)
        restart.assert_not_called()

    def test_dead_lane_thread_restarts(self):
        d = od.OversightDaemon()
        d._running = True
        restart = mock.MagicMock()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            d._check_lane("slow", self._fake_thread(alive=False), time.time(), 7200, restart)
        restart.assert_called_once()
        self.assertIn("WATCHDOG: slow lane thread died", buf.getvalue())

    def test_no_thread_is_noop(self):
        d = od.OversightDaemon()
        d._running = True
        restart = mock.MagicMock()
        d._check_lane("fast", None, 0.0, 300, restart)
        restart.assert_not_called()

    def test_stack_dump_of_real_thread_shows_frames(self):
        d = od.OversightDaemon()
        release = threading.Event()
        started = threading.Event()

        def _wedge():
            started.set()
            release.wait(timeout=10)

        t = threading.Thread(target=_wedge, daemon=True)
        t.start()
        started.wait(timeout=5)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            d._dump_thread_stack(t, "test lane")
        release.set()
        t.join(timeout=5)
        out = buf.getvalue()
        self.assertIn("test lane stack", out)
        self.assertIn("_wedge", out)


class LaneGenerationTests(unittest.TestCase):
    def setUp(self):
        # Redirects every watcher heartbeat (written by lane startup) plus
        # the event/router logs away from the real ~/ora/data/oversight.
        redirect_oversight_logs(self)

    def test_stale_generation_fast_loop_exits_immediately(self):
        d = od.OversightDaemon()
        d._running = True
        d._fast_gen = 2  # loop below carries gen=1 → stale
        done = threading.Event()

        def _run():
            d._fast_loop(1)
            done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        self.assertTrue(done.wait(timeout=5), "stale-generation fast loop did not exit")
        self.assertEqual(d._last_run, {}, "stale loop must not dispatch sweeps")

    def test_stale_generation_slow_loop_exits_but_completes_vault_scan(self):
        d = od.OversightDaemon()
        d._running = True
        d._slow_gen = 2
        with mock.patch.object(d, "_initial_vault_scan", mock.MagicMock()) as scan:
            done = threading.Event()

            def _run():
                d._slow_loop(1)
                done.set()

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            self.assertTrue(done.wait(timeout=5), "stale-generation slow loop did not exit")
            scan.assert_called_once()
            self.assertTrue(d._vault_scan_done)

    def test_lane_restart_bumps_generation(self):
        d = od.OversightDaemon()
        d._running = True
        # Stub the fast-lane sweep runners: a live fast loop dispatches all
        # four watchers on its first iteration, and this test is about
        # generation mechanics, not sweeping real vault/pointer state.
        for runner in ("_run_ped_watcher", "_run_corpus_watcher",
                       "_run_workflow_spec_sweeper", "_run_revisit_sweeper"):
            p = mock.patch.object(d, runner, mock.MagicMock())
            p.start()
            self.addCleanup(p.stop)
        with mock.patch.object(d, "_initial_vault_scan", mock.MagicMock()):
            d._start_fast_lane()
            first_gen = d._fast_gen
            first_thread = d._fast_thread
            d._start_fast_lane()
            self.assertEqual(d._fast_gen, first_gen + 1)
            self.assertIsNot(d._fast_thread, first_thread)
        d._running = False
        d._fast_thread.join(timeout=10)
        first_thread.join(timeout=10)
        self.assertFalse(first_thread.is_alive(),
                         "superseded lane thread should exit after generation bump")

    def test_stale_generation_resources_loop_exits_without_dispatch(self):
        d = od.OversightDaemon()
        d._running = True
        d._resources_gen = 2
        with mock.patch.object(d, "_run_resources_watcher") as run:
            d._resources_loop(1)
        run.assert_not_called()

    def test_resources_watcher_has_dedicated_due_check(self):
        d = od.OversightDaemon()
        d._running = True
        d._resources_gen = 1

        def one_iteration(name, interval, now, fn):
            self.assertEqual(name, "resources_watcher")
            self.assertEqual(interval, od.DEFAULT_RESOURCES_WATCHER_INTERVAL_SEC)
            fn()
            d._running = False

        with mock.patch.object(d, "_maybe_run", side_effect=one_iteration), \
                mock.patch.object(d, "_run_resources_watcher") as run:
            d._resources_loop(1)
        run.assert_called_once()

    def test_resources_watcher_heartbeat_and_health_are_registered(self):
        import oversight_health

        self.assertIn("resources_watcher", od.WATCHER_HEARTBEAT_MODULES)
        self.assertEqual(
            oversight_health.HEARTBEAT_INTERVALS["resources_watcher"],
            od.DEFAULT_RESOURCES_WATCHER_INTERVAL_SEC,
        )


if __name__ == "__main__":
    unittest.main()
