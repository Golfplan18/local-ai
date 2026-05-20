"""Verify call_model holds the per-machine MLX mutex for local endpoints
and the in-flight counter for API endpoints.

Stubs out the actual model invocation so the test runs without a server
or model files.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import boot
import mlx_mutex


class TestCallModelMutex(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_local_call_holds_machine_mutex_during_invocation(self):
        """While call_local_endpoint runs, try_acquire on the same machine
        must fail (mutex is held)."""
        machine_id = "studio-128"
        observed = {}

        def fake_local(messages, endpoint, images=None):
            with mlx_mutex.try_acquire(machine_id) as got_it:
                observed["mutex_was_free"] = got_it
            return "local-result"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "local", "machine": machine_id, "name": "hermes"},
            )

        self.assertEqual(result, "local-result")
        self.assertFalse(
            observed["mutex_was_free"],
            "Mutex must be held during the local call, not free",
        )

    def test_local_call_releases_mutex_after_return(self):
        with mock.patch.object(boot, "call_local_endpoint", return_value="ok"):
            boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "local", "machine": "studio-128", "name": "hermes"},
            )
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it, "Mutex should be free after call_model returns")

    def test_local_call_releases_mutex_on_exception(self):
        def boom(messages, endpoint, images=None):
            raise RuntimeError("model crashed")

        with mock.patch.object(boot, "call_local_endpoint", side_effect=boom):
            with self.assertRaises(RuntimeError):
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "machine": "studio-128", "name": "hermes"},
                )
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it, "Mutex must be released on exception")

    def test_missing_machine_field_defaults_to_studio_128(self):
        observed = {}

        def fake_local(messages, endpoint, images=None):
            observed["waiting_on_default"] = mlx_mutex.waiting_count("studio-128")
            with mlx_mutex.try_acquire("studio-128") as got_it:
                observed["default_machine_was_free"] = got_it
            return "ok"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "local", "name": "hermes"},
            )

        self.assertFalse(
            observed["default_machine_was_free"],
            "When endpoint omits 'machine', call_model must default to studio-128",
        )

    def test_two_local_calls_on_same_machine_serialize(self):
        """The whole point: two threads can't both be inside
        call_local_endpoint on the same machine simultaneously."""
        machine_id = "studio-128"
        in_flight = {"count": 0, "max_seen": 0, "lock": threading.Lock()}

        def fake_local(messages, endpoint, images=None):
            with in_flight["lock"]:
                in_flight["count"] += 1
                in_flight["max_seen"] = max(in_flight["max_seen"], in_flight["count"])
            time.sleep(0.05)
            with in_flight["lock"]:
                in_flight["count"] -= 1
            return "ok"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            def call():
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "machine": machine_id, "name": "hermes"},
                )

            threads = [threading.Thread(target=call) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertEqual(
            in_flight["max_seen"], 1,
            "At most one local call may be in flight per machine at a time",
        )

    def test_two_local_calls_on_different_machines_run_in_parallel(self):
        in_flight = {"count": 0, "max_seen": 0, "lock": threading.Lock()}

        def fake_local(messages, endpoint, images=None):
            with in_flight["lock"]:
                in_flight["count"] += 1
                in_flight["max_seen"] = max(in_flight["max_seen"], in_flight["count"])
            time.sleep(0.1)
            with in_flight["lock"]:
                in_flight["count"] -= 1
            return "ok"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            def call(machine):
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "machine": machine, "name": "hermes"},
                )

            ta = threading.Thread(target=call, args=("studio-128",))
            tb = threading.Thread(target=call, args=("studio-64",))
            ta.start()
            tb.start()
            ta.join(timeout=5)
            tb.join(timeout=5)

        self.assertEqual(
            in_flight["max_seen"], 2,
            "Different machines should allow concurrent local calls",
        )


class TestCallModelApiTracking(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_api_call_increments_in_flight_counter(self):
        observed = {}

        def fake_api(messages, endpoint, images=None):
            observed["in_flight_during_call"] = mlx_mutex.in_flight_count("test-api")
            return "api-result"

        with mock.patch.object(boot, "call_api_endpoint", side_effect=fake_api):
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "api", "id": "test-api"},
            )

        self.assertEqual(result, "api-result")
        self.assertEqual(observed["in_flight_during_call"], 1)
        self.assertEqual(mlx_mutex.in_flight_count("test-api"), 0)

    def test_api_call_does_not_block_on_local_machine_mutex(self):
        """API calls must not be gated by a local-machine mutex —
        even when the local mutex is held by another thread."""
        a_holding = threading.Event()
        release_a = threading.Event()

        def thread_a():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        ta = threading.Thread(target=thread_a)
        ta.start()
        a_holding.wait(timeout=2)

        with mock.patch.object(boot, "call_api_endpoint", return_value="api-ok"):
            start = time.time()
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "api", "id": "openrouter"},
            )
            elapsed = time.time() - start

        release_a.set()
        ta.join(timeout=2)

        self.assertEqual(result, "api-ok")
        self.assertLess(elapsed, 0.5, "API call should not wait on local mutex")


class TestUnknownEndpoint(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_unknown_type_returns_error_string_without_mutex(self):
        result = boot.call_model(
            [{"role": "user", "content": "hi"}],
            {"type": "weird"},
        )
        self.assertIn("Unknown endpoint type", result)
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it)


if __name__ == "__main__":
    unittest.main()
