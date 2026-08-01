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
    def test_pre_phase_a_retrieval_dispatch_remains_gear2(self):
        result = boot.run_step1_cleanup(
            "Who is the current president of France?", "", {})
        self.assertEqual(result["mode"], "factual-lookup")
        self.assertEqual(result["classification_intent"], "LOOKUP")
        self.assertFalse(result["pre_routing"]["bypass_to_direct_response"])
        self.assertTrue(result["pre_routing"]["gear2_rag_dispatch"])
        self.assertEqual(
            boot.extract_default_gear(boot.load_mode(result["mode"])), 2)

    def test_pre_phase_a_greeting_dispatch_remains_gear1(self):
        result = boot.run_step1_cleanup("Hello", "", {})
        self.assertEqual(result["mode"], "simple")
        self.assertTrue(result["pre_routing"]["bypass_to_direct_response"])
        self.assertEqual(
            boot.extract_default_gear(boot.load_mode(result["mode"])), 1)

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

    def test_phase_a_provider_error_never_becomes_cleaned_prompt(self):
        prompt = "I've been wondering why landscapes feel restorative."
        with mock.patch.object(
                boot, "get_slot_endpoint",
                return_value={"id": "qwen/qwen3.5-9b", "name": "qwen-9b"}), \
             mock.patch.object(boot, "call_model", return_value=(
                 "[Error calling OpenRouter API: Error code: 401 - "
                 "{'error': {'message': 'User not found.'}}]")), \
             mock.patch.object(boot, "pre_phase_a_bypass_check",
                               return_value=None):
            result = boot.run_step1_cleanup(
                prompt, "", {}, config_name="campaign-optimum-plus")
        self.assertEqual(result["cleaned_prompt"], prompt)
        self.assertEqual(result["operational_notation"], prompt)
        self.assertTrue(result["phase_a_transport_failed"])

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

    def test_gear2_resolves_named_fast_cell_without_active_fallback(self):
        calls = []

        def fake_get_slot_endpoint(config, slot, context="interactive",
                                   config_name=None):
            calls.append((slot, config_name))
            return {"id": "campaign-fast"} if slot == "fast" else None

        with mock.patch.object(boot, "get_slot_endpoint",
                               side_effect=fake_get_slot_endpoint), \
             mock.patch.object(boot, "get_active_endpoint",
                               return_value={"id": "active-must-not-run"}):
            endpoint, slot = boot.resolve_single_pass_endpoint(
                {}, 2, config_name="campaign-optimum-plus")
        self.assertEqual(endpoint["id"], "campaign-fast")
        self.assertEqual(slot, "gear2_rag_lookup")
        self.assertEqual(calls[0], ("fast", "campaign-optimum-plus"))

    def test_missing_named_fast_cells_fail_closed(self):
        with mock.patch.object(boot, "get_slot_endpoint", return_value=None), \
             mock.patch.object(boot, "get_active_endpoint",
                               return_value={"id": "active-must-not-run"}):
            endpoint, slot = boot.resolve_single_pass_endpoint(
                {}, 2, config_name="campaign-optimum-plus")
        self.assertIsNone(endpoint)
        self.assertEqual(slot, "gear2_rag_lookup")

    def test_single_pass_trace_binds_slot_gear_and_configuration(self):
        observed = []

        def fake_call_model(messages, endpoint, images=None):
            observed.append(dict(boot._CALL_METADATA_CV.get() or {}))
            return "done"

        with mock.patch.object(boot, "call_model", side_effect=fake_call_model):
            result = boot.run_single_pass_with_tools(
                [{"role": "user", "content": "test"}],
                {"id": "campaign-fast"},
                slot="gear2_rag_lookup",
                gear=2,
                config_name="campaign-optimum-plus",
            )
        self.assertEqual(result, "done")
        self.assertEqual(observed, [{
            "step": "gear2-single-pass",
            "slot": "gear2_rag_lookup",
            "gear": 2,
            "config_name": "campaign-optimum-plus",
        }])

    def test_web_consultation_binds_named_utility_cell(self):
        observed = []

        def fake_call_model(messages, endpoint, images=None):
            observed.append(dict(boot._CALL_METADATA_CV.get() or {}))
            return "[]"

        invoke = boot._make_web_consultation_invoker(
            "campaign-optimum-plus", "step1_cleanup")
        with mock.patch.object(boot, "call_model", side_effect=fake_call_model):
            self.assertEqual(invoke([], {"id": "qwen/qwen3.5-9b"}), "[]")
            self.assertEqual(invoke([], {"id": "qwen/qwen3.5-9b"}), "[]")
        self.assertEqual(observed, [
            {
                "step": "web-consultation",
                "slot": "step1_cleanup",
                "gear": 1,
                "config_name": "campaign-optimum-plus",
            },
            {
                "step": "web-consultation",
                "slot": "step1_cleanup",
                "gear": 1,
                "config_name": "campaign-optimum-plus",
            },
        ])

    def test_analysis_slot_resolution_uses_exact_gear(self):
        class FakeRouter:
            def resolve_endpoint(self, slot, gear, context,
                                 config_name=None):
                return {"id": f"gear{gear}-{slot}"}

            @staticmethod
            def _to_v1_endpoint(endpoint):
                return dict(endpoint)

        with mock.patch.object(boot, "_get_router", return_value=FakeRouter()):
            gear3 = boot.get_analysis_slot_endpoint(
                {}, "breadth", 3, config_name="campaign-optimum-plus")
            gear4 = boot.get_analysis_slot_endpoint(
                {}, "breadth", 4, config_name="campaign-optimum-plus")
        self.assertEqual(gear3["id"], "gear3-breadth")
        self.assertEqual(gear4["id"], "gear4-breadth")


if __name__ == "__main__":
    unittest.main()
