"""Tests for the per-machine MLX mutex layer.

Covers acquire/try_acquire semantics, the waiting counter, and the API
in-flight counter. Per Working — Framework — Concurrency Architecture.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import mlx_mutex


class TestAcquire(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_single_thread_acquire_release(self):
        with mlx_mutex.acquire("studio-128"):
            pass
        with mlx_mutex.acquire("studio-128"):
            pass

    def test_acquire_is_exclusive(self):
        """Two threads contending — second waits until first releases."""
        events = []
        start_b = threading.Event()
        a_holding = threading.Event()
        release_a = threading.Event()

        def thread_a():
            with mlx_mutex.acquire("studio-128"):
                events.append("a-acquired")
                a_holding.set()
                release_a.wait(timeout=2)
                events.append("a-releasing")

        def thread_b():
            start_b.wait(timeout=2)
            with mlx_mutex.acquire("studio-128"):
                events.append("b-acquired")

        ta = threading.Thread(target=thread_a)
        tb = threading.Thread(target=thread_b)
        ta.start()
        a_holding.wait(timeout=2)
        start_b.set()
        tb.start()
        time.sleep(0.05)
        self.assertEqual(events, ["a-acquired"])
        release_a.set()
        ta.join(timeout=2)
        tb.join(timeout=2)
        self.assertEqual(events, ["a-acquired", "a-releasing", "b-acquired"])

    def test_different_machines_dont_block(self):
        with mlx_mutex.acquire("studio-128"):
            with mlx_mutex.acquire("studio-64"):
                pass

    def test_release_on_exception(self):
        with self.assertRaises(RuntimeError):
            with mlx_mutex.acquire("studio-128"):
                raise RuntimeError("oops")
        with mlx_mutex.acquire("studio-128"):
            pass


class TestTryAcquire(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_try_acquire_succeeds_when_free(self):
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it)

    def test_try_acquire_fails_when_held(self):
        a_holding = threading.Event()
        release_a = threading.Event()
        result = []

        def thread_a():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        ta = threading.Thread(target=thread_a)
        ta.start()
        a_holding.wait(timeout=2)

        with mlx_mutex.try_acquire("studio-128") as got_it:
            result.append(got_it)

        release_a.set()
        ta.join(timeout=2)
        self.assertEqual(result, [False])

    def test_try_acquire_doesnt_release_when_it_didnt_acquire(self):
        a_holding = threading.Event()
        release_a = threading.Event()

        def thread_a():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        ta = threading.Thread(target=thread_a)
        ta.start()
        a_holding.wait(timeout=2)

        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertFalse(got_it)

        with mlx_mutex.try_acquire("studio-128") as got_again:
            self.assertFalse(got_again)

        release_a.set()
        ta.join(timeout=2)

        with mlx_mutex.try_acquire("studio-128") as got_now:
            self.assertTrue(got_now)


class TestWaitingCount(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_waiting_count_is_zero_for_unknown_machine(self):
        self.assertEqual(mlx_mutex.waiting_count("studio-128"), 0)

    def test_waiting_count_reflects_blocked_acquires(self):
        a_holding = threading.Event()
        release_a = threading.Event()
        b_started = threading.Event()
        c_started = threading.Event()

        def thread_a():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        def thread_b():
            b_started.set()
            with mlx_mutex.acquire("studio-128"):
                pass

        def thread_c():
            c_started.set()
            with mlx_mutex.acquire("studio-128"):
                pass

        ta = threading.Thread(target=thread_a)
        ta.start()
        a_holding.wait(timeout=2)

        tb = threading.Thread(target=thread_b)
        tc = threading.Thread(target=thread_c)
        tb.start()
        tc.start()
        b_started.wait(timeout=2)
        c_started.wait(timeout=2)
        time.sleep(0.1)

        self.assertEqual(mlx_mutex.waiting_count("studio-128"), 2)

        release_a.set()
        ta.join(timeout=2)
        tb.join(timeout=2)
        tc.join(timeout=2)
        self.assertEqual(mlx_mutex.waiting_count("studio-128"), 0)

    def test_try_acquire_doesnt_touch_waiting_count(self):
        with mlx_mutex.try_acquire("studio-128"):
            self.assertEqual(mlx_mutex.waiting_count("studio-128"), 0)


class TestApiCallTracking(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_in_flight_count_increments_and_decrements(self):
        self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 0)
        with mlx_mutex.track_api_call("openrouter-free"):
            self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 1)
        self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 0)

    def test_in_flight_count_nested(self):
        with mlx_mutex.track_api_call("openrouter-free"):
            with mlx_mutex.track_api_call("openrouter-free"):
                self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 2)
            self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 1)
        self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 0)

    def test_api_call_tracking_doesnt_block(self):
        results = []

        def call_api():
            with mlx_mutex.track_api_call("openrouter-free"):
                results.append(mlx_mutex.in_flight_count("openrouter-free"))
                time.sleep(0.05)

        threads = [threading.Thread(target=call_api) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        self.assertEqual(mlx_mutex.in_flight_count("openrouter-free"), 0)
        self.assertEqual(len(results), 5)
        self.assertGreater(max(results), 1)


if __name__ == "__main__":
    unittest.main()
