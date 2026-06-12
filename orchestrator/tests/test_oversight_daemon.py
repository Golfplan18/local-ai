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

import oversight_daemon as od  # noqa: E402


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
    def _patch_heartbeats(self):
        """Stub every watcher module's _write_heartbeat so lane startup
        doesn't touch the real ~/ora/data/oversight directory."""
        patches = []
        for name in ("ped_watcher", "corpus_watcher", "workflow_spec_sweeper",
                     "revisit_sweeper", "retention_sweeper", "maintenance_scheduler"):
            mod = __import__(name)
            patches.append(mock.patch.object(mod, "_write_heartbeat", mock.MagicMock()))
        return patches

    def test_stale_generation_fast_loop_exits_immediately(self):
        d = od.OversightDaemon()
        d._running = True
        d._fast_gen = 2  # loop below carries gen=1 → stale
        patches = self._patch_heartbeats()
        for p in patches:
            p.start()
        try:
            done = threading.Event()

            def _run():
                d._fast_loop(1)
                done.set()

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            self.assertTrue(done.wait(timeout=5), "stale-generation fast loop did not exit")
            self.assertEqual(d._last_run, {}, "stale loop must not dispatch sweeps")
        finally:
            for p in patches:
                p.stop()

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
        patches = self._patch_heartbeats()
        for p in patches:
            p.start()
        try:
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
        finally:
            for p in patches:
                p.stop()


if __name__ == "__main__":
    unittest.main()
