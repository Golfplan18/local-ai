"""Tests for the MLX worker heartbeat (Phase 2c).

Verifies the heartbeat writer produces a file in the format
oversight_health reads, that the background thread emits periodically
without blocking the main process, and that the threshold registration
in oversight_health.HEARTBEAT_INTERVALS is correct.
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import mlx_mutex
import oversight_health


class TestWriteHeartbeat(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "mlx-worker-heartbeat.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_file_with_expected_fields(self):
        mlx_mutex.write_heartbeat(machine_id="test-machine", path=str(self.path))
        self.assertTrue(self.path.exists())
        data = json.loads(self.path.read_text())
        self.assertIn("beat_at", data)
        self.assertEqual(data["machine_id"], "test-machine")
        self.assertEqual(data["queue_depth"], 0)

    def test_beat_at_is_recent_iso_utc(self):
        mlx_mutex.write_heartbeat(path=str(self.path))
        data = json.loads(self.path.read_text())
        beat = datetime.datetime.fromisoformat(data["beat_at"])
        now = datetime.datetime.now(datetime.timezone.utc)
        self.assertLess((now - beat).total_seconds(), 1.0)

    def test_creates_parent_directory(self):
        nested = Path(self.tmp.name) / "a" / "b" / "c" / "heartbeat.json"
        mlx_mutex.write_heartbeat(path=str(nested))
        self.assertTrue(nested.exists())

    def test_overwrites_atomically(self):
        mlx_mutex.write_heartbeat(path=str(self.path))
        first = json.loads(self.path.read_text())
        time.sleep(0.02)
        mlx_mutex.write_heartbeat(path=str(self.path))
        second = json.loads(self.path.read_text())
        self.assertNotEqual(first["beat_at"], second["beat_at"])

    def test_queue_depth_reflects_waiting_callers(self):
        machine_id = "test-machine"
        a_holding = threading.Event()
        release_a = threading.Event()
        b_waiting = threading.Event()

        def holder():
            with mlx_mutex.acquire(machine_id):
                a_holding.set()
                release_a.wait(timeout=2)

        def waiter():
            b_waiting.set()
            with mlx_mutex.acquire(machine_id):
                pass

        ta = threading.Thread(target=holder)
        ta.start()
        a_holding.wait(timeout=2)

        tb = threading.Thread(target=waiter)
        tb.start()
        b_waiting.wait(timeout=2)
        time.sleep(0.05)

        mlx_mutex.write_heartbeat(machine_id=machine_id, path=str(self.path))
        data = json.loads(self.path.read_text())
        self.assertEqual(data["queue_depth"], 1)

        release_a.set()
        ta.join(timeout=2)
        tb.join(timeout=2)


class TestHeartbeatThread(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "mlx-worker-heartbeat.json"

    def tearDown(self):
        mlx_mutex.stop_heartbeat()
        self.tmp.cleanup()

    def test_thread_emits_multiple_beats(self):
        mlx_mutex.start_heartbeat(
            interval_seconds=0.05, path=str(self.path),
        )
        time.sleep(0.2)
        first = json.loads(self.path.read_text())
        time.sleep(0.1)
        second = json.loads(self.path.read_text())
        self.assertNotEqual(first["beat_at"], second["beat_at"])

    def test_thread_is_daemon(self):
        thread = mlx_mutex.start_heartbeat(
            interval_seconds=10.0, path=str(self.path),
        )
        self.assertTrue(thread.daemon)

    def test_second_start_replaces_first(self):
        t1 = mlx_mutex.start_heartbeat(
            interval_seconds=10.0, path=str(self.path),
        )
        t2 = mlx_mutex.start_heartbeat(
            interval_seconds=10.0, path=str(self.path),
        )
        # t1 should be stopped; t2 should be running
        time.sleep(0.05)
        self.assertFalse(t1.is_alive(), "First thread should have been stopped")
        self.assertTrue(t2.is_alive(), "Second thread should be running")

    def test_stop_heartbeat_actually_stops(self):
        thread = mlx_mutex.start_heartbeat(
            interval_seconds=10.0, path=str(self.path),
        )
        mlx_mutex.stop_heartbeat()
        time.sleep(0.05)
        self.assertFalse(thread.is_alive())


class TestOversightHealthIntegration(unittest.TestCase):
    def test_mlx_worker_registered_in_intervals(self):
        self.assertIn("mlx_worker", oversight_health.HEARTBEAT_INTERVALS)
        self.assertEqual(oversight_health.HEARTBEAT_INTERVALS["mlx_worker"], 30)

    def test_heartbeat_path_matches_oversight_health_pattern(self):
        """oversight_health reads heartbeat files at
        ~/ora/data/oversight/<dash-name>-heartbeat.json."""
        expected = oversight_health.heartbeat_path("mlx_worker")
        self.assertTrue(expected.endswith("mlx-worker-heartbeat.json"))

    def test_freshly_written_heartbeat_is_readable_by_oversight_health(self):
        """End-to-end: write_heartbeat produces a file that
        oversight_health.read_heartbeat can parse and timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat_path = Path(tmp) / "mlx-worker-heartbeat.json"
            mlx_mutex.write_heartbeat(path=str(heartbeat_path))

            with mock.patch.object(
                oversight_health, "heartbeat_path",
                return_value=str(heartbeat_path),
            ):
                ts = oversight_health.read_heartbeat("mlx_worker")
            self.assertIsNotNone(ts)
            self.assertLess(time.time() - ts, 5.0)

    def test_live_event_runtime_ignores_retired_watcher_heartbeats(self):
        stale = time.time() - 100_000
        with mock.patch("oversight_daemon.runtime_health", return_value={
                "running": True, "event_lane": True, "deadline_lane": True,
        }), mock.patch.object(oversight_health, "_oversight_active", return_value=True), \
                mock.patch.object(oversight_health, "read_heartbeat",
                                  side_effect=lambda name: None if name == "mlx_worker" else stale):
            self.assertEqual(oversight_health.check_health(), [])


if __name__ == "__main__":
    unittest.main()
