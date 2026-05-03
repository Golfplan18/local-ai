"""Tests for the Phase 9 four-stage pre-routing pipeline.

Covers Stage 1 (pre-analysis filter), Stage 2 (sufficiency analyzer),
Stage 3 (input completeness check), the dispatch-announcement helper,
and the orchestrating run_pre_routing_pipeline entry point.
"""
from __future__ import annotations

import os
import sys
import unittest

WORKSPACE = os.path.expanduser("~/ora")
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))

import boot  # noqa: E402


class TestStage1PreAnalysisFilter(unittest.TestCase):
    def test_greeting_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("Hi there!")
        self.assertTrue(r["bypass_to_direct_response"])

    def test_thanks_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("Thanks, that was helpful.")
        self.assertTrue(r["bypass_to_direct_response"])

    def test_factual_lookup_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("What time is it in Tokyo?")
        self.assertTrue(r["bypass_to_direct_response"])

    def test_translation_is_bypassed(self):
        r = boot.stage1_pre_analysis_filter("Translate this paragraph into French.")
        self.assertTrue(r["bypass_to_direct_response"])

    def test_negation_bypasses_analytical_signal(self):
        r = boot.stage1_pre_analysis_filter("Don't analyze this; just summarize.")
        self.assertTrue(r["bypass_to_direct_response"])

    def test_strong_signal_passes_filter(self):
        r = boot.stage1_pre_analysis_filter("Run an ACH on these explanations.")
        self.assertFalse(r["bypass_to_direct_response"])
        self.assertGreater(len(r["matches"]), 0)

    def test_steelman_signal_matches(self):
        r = boot.stage1_pre_analysis_filter("Steelman this op-ed quickly.")
        self.assertFalse(r["bypass_to_direct_response"])
        modes = {m["mode"] for m in r["matches"]}
        self.assertIn("steelman-construction", modes)

    def test_word_boundary_blocks_short_signal_collision(self):
        # Signal "Ma" (T19 ma-reading) must NOT match inside "Make"
        r = boot.stage1_pre_analysis_filter("Make some coffee for the meeting.")
        modes = {m["mode"] for m in r["matches"]}
        self.assertNotIn("ma-reading", modes)


class TestStage2SufficiencyAnalyzer(unittest.TestCase):
    def test_strong_dispatch_steelman(self):
        prompt = "Steelman this argument."
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertEqual(s2["dispatched_mode_id"], "steelman-construction")
        self.assertEqual(s2["disambiguation_questions_asked"], [])

    def test_strong_dispatch_cui_bono(self):
        prompt = "Who benefits from this zoning amendment?"
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertEqual(s2["dispatched_mode_id"], "cui-bono")

    def test_conflict_surfaces_question(self):
        prompt = "Quick deep-dive on this argument."
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertIsNone(s2["dispatched_mode_id"])
        self.assertGreater(len(s2["disambiguation_questions_asked"]), 0)

    def test_no_strong_signals_falls_back_to_pattern_a(self):
        prompt = "tell me something interesting"
        s1 = boot.stage1_pre_analysis_filter(prompt)
        s2 = boot.stage2_sufficiency_analyzer(prompt, s1)
        self.assertIsNone(s2["dispatched_mode_id"])
        # Pattern-A canonical question stem
        joined = " ".join(s2["disambiguation_questions_asked"])
        self.assertIn("Quick check", joined)


class TestStage3InputCompletenessCheck(unittest.TestCase):
    def test_cui_bono_with_short_prompt_missing_input(self):
        r = boot.stage3_input_completeness_check(
            "cui-bono", "who benefits", {}
        )
        self.assertFalse(r["inputs_complete"])
        self.assertGreater(len(r["missing_fields"]), 0)
        self.assertIsNotNone(r["completeness_question"])

    def test_unknown_mode_passes_through_safely(self):
        r = boot.stage3_input_completeness_check(
            "definitely-not-a-real-mode", "anything", {}
        )
        self.assertTrue(r["inputs_complete"])

    def test_long_situation_satisfies_situation_field(self):
        prompt = (
            "Who benefits from this new municipal zoning amendment that "
            "the city council passed last week reducing setback requirements "
            "for multi-family housing in transit-rich corridors near downtown?"
        )
        r = boot.stage3_input_completeness_check("cui-bono", prompt, {})
        # Long, substantive prompt should satisfy situation_or_artifact
        self.assertTrue(r["inputs_complete"])


class TestDispatchAnnouncement(unittest.TestCase):
    def test_format_has_italic_parenthetical(self):
        s = boot.format_dispatch_announcement("plain language", "named technique")
        self.assertEqual(s, "plain language *(named technique)*")

    def test_compose_for_steelman(self):
        s = boot.compose_dispatch_announcement(
            "steelman-construction", "Steelman this op-ed."
        )
        self.assertIn("strongest case", s.lower())
        self.assertIn("*(", s)
        self.assertIn(")*", s)

    def test_compose_falls_back_for_unknown_mode(self):
        # Even an unknown mode should produce some announcement (no crash)
        s = boot.compose_dispatch_announcement("unknown-mode", "anything")
        self.assertIn("*(", s)
        self.assertIn(")*", s)


class TestRunPreRoutingPipeline(unittest.TestCase):
    def test_bypass_path(self):
        r = boot.run_pre_routing_pipeline("Hi there!")
        self.assertTrue(r["bypass_to_direct_response"])
        self.assertIsNone(r["dispatched_mode_id"])

    def test_strong_dispatch_no_clarification(self):
        r = boot.run_pre_routing_pipeline(
            "Steelman this argument: people should be allowed to drive any "
            "car they want without restrictions whatsoever, because freedom."
        )
        self.assertEqual(r["dispatched_mode_id"], "steelman-construction")
        self.assertIsNotNone(r["dispatch_announcement"])

    def test_weak_signal_returns_disambiguation_question(self):
        r = boot.run_pre_routing_pipeline("Look at this op-ed.")
        # Could be Stage 2 disambiguation or Stage 3 missing input
        self.assertIsNotNone(r["pending_clarification"])

    def test_runtime_config_default_on_missing_errors(self):
        # Per Decision C: missing entries error safely.
        with self.assertRaises(KeyError):
            boot.load_runtime_config_for_mode("definitely-not-a-real-mode")


if __name__ == "__main__":
    unittest.main()
