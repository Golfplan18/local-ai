#!/usr/bin/env python3
"""Install Chunk 3 — per-process configuration plumbing tests.

Covers:
- _lookup_framework_default_configuration reads config/framework-routing.json
  in its multiple supported shapes (string shorthand, full object).
- The cache invalidation hook (reset_framework_routing_cache) works so
  tests can swap routing tables between assertions.
- execute_framework's config_name parameter is propagated through
  _run_milestone → _run_through_gear_pipeline → run_gear3/run_gear4
  (smoke test against the signature; actual model dispatch is mocked
  elsewhere).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import milestone_executor  # noqa: E402


class TestFrameworkRoutingLookup(unittest.TestCase):
    """_lookup_framework_default_configuration covers the supported shapes."""

    def setUp(self):
        milestone_executor.reset_framework_routing_cache()

    def tearDown(self):
        milestone_executor.reset_framework_routing_cache()

    def _patch_routing(self, routing_dict):
        """Inject a fake routing dict into the loader via mock."""
        return mock.patch.object(
            milestone_executor, "_load_framework_routing",
            return_value=routing_dict,
        )

    def test_string_shorthand(self):
        with self._patch_routing({"frameworks": {"my-framework": "premium"}}):
            self.assertEqual(
                milestone_executor._lookup_framework_default_configuration("my-framework"),
                "premium",
            )

    def test_object_form_with_default_configuration(self):
        with self._patch_routing({
            "frameworks": {"my-framework": {"default_configuration": "budget"}},
        }):
            self.assertEqual(
                milestone_executor._lookup_framework_default_configuration("my-framework"),
                "budget",
            )

    def test_unknown_framework_returns_none(self):
        with self._patch_routing({"frameworks": {"other": "premium"}}):
            self.assertIsNone(
                milestone_executor._lookup_framework_default_configuration("my-framework"),
            )

    def test_empty_routing_returns_none(self):
        with self._patch_routing({}):
            self.assertIsNone(
                milestone_executor._lookup_framework_default_configuration("any"),
            )

    def test_object_without_default_configuration_returns_none(self):
        # Future-proofing: an object with only per-mode-configuration but no
        # default_configuration falls through to the Router's auto-derivation.
        with self._patch_routing({
            "frameworks": {"my-framework": {"per_mode_configuration": {}}},
        }):
            self.assertIsNone(
                milestone_executor._lookup_framework_default_configuration("my-framework"),
            )


class TestFrameworkRoutingCacheBehavior(unittest.TestCase):
    """Loader caches the routing file; reset_framework_routing_cache clears it."""

    def setUp(self):
        milestone_executor.reset_framework_routing_cache()

    def tearDown(self):
        milestone_executor.reset_framework_routing_cache()

    def test_cache_is_populated_after_first_call(self):
        milestone_executor._load_framework_routing()
        self.assertIsNotNone(milestone_executor._FRAMEWORK_ROUTING_CACHE)

    def test_reset_clears_cache(self):
        milestone_executor._load_framework_routing()
        milestone_executor.reset_framework_routing_cache()
        self.assertIsNone(milestone_executor._FRAMEWORK_ROUTING_CACHE)


class TestExecuteFrameworkSignature(unittest.TestCase):
    """execute_framework carries config_name through to milestone execution."""

    def test_signature_carries_config_name(self):
        import inspect
        sig = inspect.signature(milestone_executor.execute_framework)
        self.assertIn("config_name", sig.parameters)
        self.assertIsNone(sig.parameters["config_name"].default)

    def test_run_milestone_carries_config_name(self):
        import inspect
        sig = inspect.signature(milestone_executor._run_milestone)
        self.assertIn("config_name", sig.parameters)

    def test_run_through_gear_pipeline_carries_config_name(self):
        import inspect
        sig = inspect.signature(milestone_executor._run_through_gear_pipeline)
        self.assertIn("config_name", sig.parameters)


if __name__ == "__main__":
    unittest.main()
