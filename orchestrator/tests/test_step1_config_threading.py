#!/usr/bin/env python3
"""Per-request config_name threading into step-1/step-2 model resolution.

Regression guard for the 2026-06-12 campaign fidelity fix: before it,
``run_step1_cleanup`` (Phase A cleanup) resolved its utility endpoint
without the per-request ``config_name``, so a `/chat` request that named
a configuration still ran its step-1 calls on the ACTIVE configuration's
models — caught live by the campaign runner's fidelity gate (gpt-5.4-nano
executing inside a campaign-premium run).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import boot  # noqa: E402


class TestStep1ConfigThreading(unittest.TestCase):
    def test_run_step1_cleanup_passes_config_name(self):
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append({"slot": slot, "config_name": config_name})
            return None  # passthrough path — no model call attempted

        prompt = "Run a full cui bono analysis on this policy proposal."
        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint), \
             mock.patch.object(boot, "pre_phase_a_bypass_check",
                               return_value=None):
            boot.run_step1_cleanup(prompt, "", {},
                                   config_name="campaign-premium")
        step1_calls = [c for c in calls if c["slot"] == "step1_cleanup"]
        self.assertTrue(step1_calls, "step1_cleanup endpoint never resolved")
        self.assertEqual(step1_calls[0]["config_name"], "campaign-premium")

    def test_synthesis_endpoint_honors_config_name(self):
        # Visual repair-on-miss synthesis must resolve from the named
        # configuration (fast → small), never the active configuration —
        # third instance of the class the campaign fidelity gate caught.
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append({"slot": slot, "config_name": config_name})
            return {"id": "cfg-model"} if slot == "fast" else None

        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint), \
             mock.patch.object(boot, "load_routing_config", return_value={}):
            ep = boot._resolve_synthesis_endpoint("campaign-premium")
        self.assertEqual(ep, {"id": "cfg-model"})
        self.assertEqual(calls[0],
                         {"slot": "fast", "config_name": "campaign-premium"})

    def test_synthesis_endpoint_no_cross_config_fallback(self):
        # A named-config turn whose config has no fast/small endpoint must
        # SKIP synthesis (return None), not fall back to the active config.
        with mock.patch.object(boot, "get_slot_endpoint",
                               return_value=None), \
             mock.patch.object(boot, "load_routing_config",
                               return_value={"visual_synthesis":
                                             {"preferred": "active-model"}}):
            self.assertIsNone(
                boot._resolve_synthesis_endpoint("campaign-premium"))

    def test_unflagged_claim_scan_passes_config_name(self):
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append({"slot": slot, "config_name": config_name})
            return None  # scan degrades gracefully with no endpoint

        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint):
            boot._run_unflagged_claim_scan(
                "## REVISED DRAFT\ntext", [], {},
                label="t", config_name="campaign-premium")
        self.assertTrue(calls)
        self.assertEqual(calls[0]["config_name"], "campaign-premium")


if __name__ == "__main__":
    unittest.main()
