"""Tests for the per-endpoint circuit breaker (Phase 2b).

Covers threshold-cross trip, cooldown expiry, half-open probe behavior,
record_success reset, and the rolling-window pruning. Plus integration
tests that verify call_model records outcomes correctly and the
router's chain walk skips endpoints in cooldown.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import boot
import endpoint_health
import mlx_mutex
from router import Router


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        endpoint_health.reset_for_tests()

    def test_fresh_endpoint_is_healthy(self):
        self.assertFalse(endpoint_health.is_in_cooldown("test"))

    def test_below_threshold_failures_stay_healthy(self):
        endpoint_health.configure(failure_threshold=3)
        endpoint_health.record_failure("test")
        endpoint_health.record_failure("test")
        self.assertFalse(endpoint_health.is_in_cooldown("test"))

    def test_threshold_failures_trip_breaker(self):
        endpoint_health.configure(failure_threshold=3)
        for _ in range(3):
            endpoint_health.record_failure("test")
        self.assertTrue(endpoint_health.is_in_cooldown("test"))

    def test_cooldown_expires_to_half_open_probe(self):
        endpoint_health.configure(
            failure_threshold=3, cooldown_seconds=0.05,
        )
        for _ in range(3):
            endpoint_health.record_failure("test")
        self.assertTrue(endpoint_health.is_in_cooldown("test"))
        time.sleep(0.06)
        # First call after cooldown is the probe — should be allowed (False)
        self.assertFalse(endpoint_health.is_in_cooldown("test"))
        # Subsequent calls block until the probe resolves
        self.assertTrue(endpoint_health.is_in_cooldown("test"))

    def test_probe_success_returns_to_healthy(self):
        endpoint_health.configure(
            failure_threshold=3, cooldown_seconds=0.05,
        )
        for _ in range(3):
            endpoint_health.record_failure("test")
        time.sleep(0.06)
        endpoint_health.is_in_cooldown("test")  # arms the probe
        endpoint_health.record_success("test")
        self.assertFalse(endpoint_health.is_in_cooldown("test"))
        status = endpoint_health.endpoint_status("test")
        self.assertTrue(status["healthy"])

    def test_probe_failure_extends_cooldown(self):
        endpoint_health.configure(
            failure_threshold=3, cooldown_seconds=0.05,
        )
        for _ in range(3):
            endpoint_health.record_failure("test")
        time.sleep(0.06)
        endpoint_health.is_in_cooldown("test")  # arms the probe
        endpoint_health.record_failure("test")
        # Probe failed → cooldown re-arms
        self.assertTrue(endpoint_health.is_in_cooldown("test"))

    def test_success_during_partial_failure_doesnt_reset_window(self):
        """Successes interspersed with failures don't wipe the rolling
        window — that would let a flaky endpoint (fail/succeed/fail/…)
        evade the breaker forever. Only the half-open probe success
        clears state; otherwise the window prunes by age."""
        endpoint_health.configure(failure_threshold=3)
        endpoint_health.record_failure("test")
        endpoint_health.record_failure("test")
        endpoint_health.record_success("test")
        endpoint_health.record_failure("test")
        self.assertTrue(endpoint_health.is_in_cooldown("test"))

    def test_rolling_window_prunes_old_failures(self):
        endpoint_health.configure(
            failure_threshold=3, failure_window_seconds=0.05,
        )
        endpoint_health.record_failure("test")
        endpoint_health.record_failure("test")
        time.sleep(0.06)
        # Old failures fall off the window
        endpoint_health.record_failure("test")
        self.assertFalse(endpoint_health.is_in_cooldown("test"))

    def test_different_endpoints_have_independent_state(self):
        endpoint_health.configure(failure_threshold=3)
        for _ in range(3):
            endpoint_health.record_failure("ep-a")
        self.assertTrue(endpoint_health.is_in_cooldown("ep-a"))
        self.assertFalse(endpoint_health.is_in_cooldown("ep-b"))

    def test_endpoint_status_returns_useful_diagnostics(self):
        endpoint_health.configure(
            failure_threshold=3, cooldown_seconds=10,
        )
        for _ in range(3):
            endpoint_health.record_failure("test")
        status = endpoint_health.endpoint_status("test")
        self.assertFalse(status["healthy"])
        self.assertEqual(status["recent_failures"], 3)
        self.assertGreater(status["cooldown_remaining"], 0)


class TestCallModelRecordsOutcomes(unittest.TestCase):
    def setUp(self):
        endpoint_health.reset_for_tests()
        mlx_mutex.reset_for_tests()

    def test_successful_api_call_records_success(self):
        with mock.patch.object(boot, "call_api_endpoint", return_value="hello"):
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "api", "id": "test-api"},
            )
        self.assertEqual(result, "hello")
        status = endpoint_health.endpoint_status("test-api")
        self.assertTrue(status["healthy"])

    def test_api_error_string_records_failure(self):
        with mock.patch.object(
            boot, "call_api_endpoint",
            return_value="[Error calling Claude API: rate limited]",
        ):
            for _ in range(3):
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "api", "id": "test-api"},
                )
        self.assertTrue(endpoint_health.is_in_cooldown("test-api"))

    def test_local_load_failure_records_failure(self):
        with mock.patch.object(
            boot, "call_local_endpoint",
            return_value="[Error loading model: weights file missing]",
        ):
            for _ in range(3):
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "id": "hermes-70b", "machine": "studio-128"},
                )
        self.assertTrue(endpoint_health.is_in_cooldown("hermes-70b"))


class TestRouterSkipsCooldownEndpoints(unittest.TestCase):
    def setUp(self):
        endpoint_health.reset_for_tests()
        mlx_mutex.reset_for_tests()

    def _router(self, primary_id, fallback_ids, endpoints):
        cfg = {
            "name": "user-pipeline",
            "cells": {
                "analysis": {
                    "gear4": {
                        "depth": {"primary": primary_id, "fallback": fallback_ids},
                        "breadth": {"primary": primary_id, "fallback": fallback_ids},
                    },
                    "gear3": {
                        "depth": {"primary": primary_id, "fallback": fallback_ids},
                        "breadth": {"primary": primary_id, "fallback": fallback_ids},
                    },
                },
            },
        }
        rc = {
            "_schema_version": "2.0",
            "endpoints": endpoints,
            "machines": [{"id": "studio-128", "ram_gb": 128}],
            "buckets": {},
            "slot_assignments": {},
            "configurations": {},
        }
        router = Router(config_dict=rc)
        router._configurations["user-pipeline"] = cfg
        return router

    def test_cooldown_endpoint_is_skipped(self):
        router = self._router(
            "openrouter-claude", ["openrouter-free"],
            [
                {"id": "openrouter-claude", "name": "openrouter-claude",
                 "type": "api", "enabled": True, "status": "active"},
                {"id": "openrouter-free", "name": "openrouter-free",
                 "type": "api", "enabled": True, "status": "active"},
            ],
        )

        endpoint_health.configure(failure_threshold=3)
        for _ in range(3):
            endpoint_health.record_failure("openrouter-claude")

        ep = router.resolve_endpoint(
            "depth", gear=4, context="interactive",
            config_name="user-pipeline",
        )
        self.assertEqual(
            ep["id"], "openrouter-free",
            "Should advance past the cooled-down primary to the fallback",
        )

    def test_all_endpoints_in_cooldown_returns_none(self):
        router = self._router(
            "openrouter-claude", ["openrouter-free"],
            [
                {"id": "openrouter-claude", "name": "openrouter-claude",
                 "type": "api", "enabled": True, "status": "active"},
                {"id": "openrouter-free", "name": "openrouter-free",
                 "type": "api", "enabled": True, "status": "active"},
            ],
        )

        endpoint_health.configure(failure_threshold=3)
        for ep_id in ("openrouter-claude", "openrouter-free"):
            for _ in range(3):
                endpoint_health.record_failure(ep_id)

        ep = router.resolve_endpoint(
            "depth", gear=4, context="interactive",
            config_name="user-pipeline",
        )
        self.assertIsNone(
            ep,
            "When every chain entry is in cooldown, return None — caller "
            "should surface the error rather than silently using a known-bad endpoint",
        )


if __name__ == "__main__":
    unittest.main()
