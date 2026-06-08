"""Tests for the Phase 2 adversarial rules (remaining Tufte + clarity gates)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import visual_adversarial as va  # noqa: E402


def _rules(findings, rule):
    return [f for f in findings if f.rule == rule]


class TestTufteCompletion(unittest.TestCase):
    def test_t9_inverted_axis_critical(self):
        env = {"type": "comparison", "spec": {"encoding": {"y": {"scale": {"reverse": True}}}}}
        f = va._t9_axis_orientation(env, "comparison")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "Critical")

    def test_t9_inverted_axis_justified_passes(self):
        env = {"type": "comparison",
               "integrity_declarations": {"inverted_axis_justified": "depth below surface"},
               "spec": {"encoding": {"y": {"scale": {"reverse": True}}}}}
        self.assertEqual(va._t9_axis_orientation(env, "comparison"), [])

    def test_t6_aggregate_hides_distribution(self):
        env = {"type": "comparison", "spec": {
            "encoding": {"y": {"aggregate": "mean"}},
            "data": {"values": [{"v": i} for i in range(25)]}}}
        f = va._t6_show_the_data(env, "comparison")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "Major")

    def test_t6_small_n_ok(self):
        env = {"type": "comparison", "spec": {
            "encoding": {"y": {"aggregate": "mean"}},
            "data": {"values": [{"v": i} for i in range(5)]}}}
        self.assertEqual(va._t6_show_the_data(env, "comparison"), [])

    def test_t11_too_many_colors(self):
        env = {"type": "comparison", "spec": {
            "encoding": {"color": {"field": "g"}},
            "data": {"values": [{"g": f"c{i}"} for i in range(8)]}}}
        f = va._t11_small_multiples(env, "comparison")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "Minor")

    def test_t14_nonuniform_ticks(self):
        env = {"type": "comparison", "spec": {
            "encoding": {"y": {"axis": {"values": [0, 1, 5, 6]}}}}}
        f = va._t14_tick_consistency(env, "comparison")
        self.assertEqual(len(f), 1)

    def test_t14_uniform_ticks_ok(self):
        env = {"type": "comparison", "spec": {
            "encoding": {"y": {"axis": {"values": [0, 2, 4, 6]}}}}}
        self.assertEqual(va._t14_tick_consistency(env, "comparison"), [])

    def test_t4_decoration_flagged_and_memorability_exempt(self):
        env = {"type": "comparison", "spec": {"mark": {"type": "bar", "shadow": True}}}
        self.assertEqual(len(va._t4_data_ink(env, "comparison")), 1)
        env["memorability_goal"] = True
        self.assertEqual(va._t4_data_ink(env, "comparison"), [])

    def test_t12_nominal_currency(self):
        env = {"type": "time_series", "title": "Median wage in $", "spec": {}}
        self.assertEqual(len(va._t12_currency(env, "time_series")), 1)
        env["title"] = "Median wage in real (inflation-adjusted) $"
        self.assertEqual(va._t12_currency(env, "time_series"), [])

    def test_t13_long_series_no_events(self):
        env = {"type": "time_series", "spec": {"data": {"values": [{"t": i} for i in range(70)]}}}
        self.assertEqual(len(va._t13_event_labelling(env, "time_series")), 1)


class TestClarityGates(unittest.TestCase):
    def test_redundant_is_critical(self):
        env = {"type": "concept_map", "relation_to_prose": "redundant"}
        f = va._clarity_redundant(env, "concept_map")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].severity, "Critical")
        self.assertEqual(f[0].rule, "clarity.redundant")

    def test_redundant_blocks_in_review(self):
        env = {"type": "concept_map", "relation_to_prose": "redundant",
               "mode_context": "synthesis", "spec": {}}
        review = va.review_envelope(env, "synthesis")
        self.assertTrue(any(b.rule == "clarity.redundant" for b in review.blocks))

    def test_empty_short_alt_major(self):
        env = {"type": "comparison",
               "semantic_description": {"short_alt": "  ",
                                        "level_1_elemental": "a", "level_2_statistical": "b",
                                        "level_3_perceptual": "c"}}
        f = _rules(va._clarity_semantic_quality(env, "comparison"), "clarity.semantic")
        self.assertTrue(any(x.severity == "Major" for x in f))

    def test_identical_levels_minor(self):
        env = {"type": "comparison",
               "semantic_description": {"short_alt": "ok alt",
                                        "level_1_elemental": "same", "level_2_statistical": "same",
                                        "level_3_perceptual": "same"}}
        f = _rules(va._clarity_semantic_quality(env, "comparison"), "clarity.semantic")
        self.assertTrue(any("identical" in x.message for x in f))

    def test_good_semantic_description_clean(self):
        env = {"type": "comparison",
               "semantic_description": {"short_alt": "bar chart of 4 categories",
                                        "level_1_elemental": "bar chart, x category, y count",
                                        "level_2_statistical": "max C=42, min A=10",
                                        "level_3_perceptual": "two clusters, low and high"}}
        self.assertEqual(va._clarity_semantic_quality(env, "comparison"), [])


if __name__ == "__main__":
    unittest.main()
