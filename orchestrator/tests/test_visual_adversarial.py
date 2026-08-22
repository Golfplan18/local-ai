#!/usr/bin/env python3
"""
Unit tests for ``orchestrator/visual_adversarial.py`` (WP-1.6).

Invoke::

    /opt/homebrew/bin/python3 -m pytest ~/ora/orchestrator/tests -q
    # or
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tests/test_visual_adversarial.py

Coverage:
* T-rule findings per-family (bar without zero baseline, pie-chart token,
  3D mark dimensional conformance, log scale without base, temporal x on
  comparison, banking aspect-ratio check).
* LLM-prior-inversion: template-trap strings, chart-type misselection,
  default-settings passthrough.
* Per-mode strictness escalation: lax demotes Major→Minor, strict escalates
  Major→Critical, Critical is unmovable.
* A focused integration test for the ``process_response`` helper that
  mocks the ``boot.py`` integration path: valid block passes through,
  Critical block is suppressed with a fallback marker.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import visual_adversarial as va  # noqa: E402
from visual_adversarial import (  # noqa: E402
    Finding,
    ReviewResult,
    review_envelope,
    process_response,
    TEMPLATE_TRAP_STRINGS,
    _apply_strictness,
)

EXAMPLES = (Path(__file__).resolve().parents[2]
            / "config" / "visual-schemas" / "examples")


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


# ---------------------------------------------------------------------------
# T-rule findings
# ---------------------------------------------------------------------------

class TestT1T2ZeroBaseline(unittest.TestCase):
    def _bar(self) -> dict:
        env = _load("comparison.valid.json")
        env["spec"]["data"]["values"] = [{"c": "A", "v": 100}, {"c": "B", "v": 105}]
        return env

    def test_non_zero_baseline_blocks(self):
        env = self._bar()
        env["spec"]["encoding"]["y"]["scale"] = {"zero": False, "domain": [95, 110]}
        result = review_envelope(env)
        rules = [f.rule for f in result.blocks]
        self.assertIn("T2", rules)

    def test_lie_factor_outside_range_blocks(self):
        """A floor just under the data inflates the apparent ratio.

        Values 100 and 105 differ by 5%. Floored at 99 they read as 6:1.
        (This case previously asserted the opposite property — that a WIDE
        zero-based domain blocks — which is an honest chart. See
        TestT1LieFactorDirection for the full inversion.)
        """
        env = self._bar()
        env["spec"]["encoding"]["y"]["scale"] = {"zero": False, "domain": [99, 110]}
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T1" for f in result.blocks))

    def test_wide_zero_based_domain_is_honest(self):
        """Headroom is not a lie. A zero floor gives lie factor 1.0 however
        much empty space sits above the data."""
        env = self._bar()
        env["spec"]["encoding"]["y"]["scale"] = {"domain": [0, 1000]}
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "T1" for f in result.blocks))

    def test_zero_baseline_justification_clears_block(self):
        env = self._bar()
        env["spec"]["encoding"]["y"]["scale"] = {"zero": False, "domain": [95, 110]}
        env["integrity_declarations"] = {"non_zero_baseline_justified": "index"}
        result = review_envelope(env)
        # With lie factor still potentially off, T1 may fire — but T2 should NOT
        self.assertFalse(any(f.rule == "T2" for f in result.blocks))

    def test_valid_bar_no_blocks(self):
        env = _load("comparison.valid.json")
        result = review_envelope(env)
        self.assertEqual([], [f for f in result.blocks if f.rule in {"T1", "T2"}])


class TestT3DimensionalConformance(unittest.TestCase):
    def test_3d_mark_blocked(self):
        env = _load("comparison.valid.json")
        env["spec"]["mark"] = {"type": "bar3d"}
        result = review_envelope(env)
        # schema disallows this mark — but for adversarial purposes we
        # bypass schema and test the adversarial path directly.
        rules = [f.rule for f in result.blocks]
        self.assertIn("T3", rules)


class TestT5Chartjunk(unittest.TestCase):
    def test_pie_mark_blocked(self):
        env = _load("comparison.valid.json")
        env["spec"]["mark"] = "pie"
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T5" for f in result.blocks))

    def test_arc_mark_blocked(self):
        env = _load("comparison.valid.json")
        env["spec"]["mark"] = "arc"
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T5" for f in result.blocks))

    def test_cylinder_mark_blocked(self):
        env = _load("comparison.valid.json")
        env["spec"]["mark"] = "cylinder"
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T5" for f in result.blocks))

    def test_cld_unaffected_by_t5(self):
        env = _load("causal_loop_diagram.valid.json")
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "T5" for f in result.blocks))


class TestT7Labelling(unittest.TestCase):
    def test_missing_title_warns(self):
        env = _load("comparison.valid.json")
        env.pop("title", None)
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T7" for f in (result.warns + result.blocks)))

    def test_missing_caption_n_warns(self):
        env = _load("comparison.valid.json")
        env["spec"]["caption"].pop("n", None)
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T7" for f in result.warns + result.blocks))


class TestT8ScaleDisclosure(unittest.TestCase):
    def test_log_without_base_blocks(self):
        env = _load("comparison.valid.json")
        env["spec"]["encoding"]["y"]["scale"] = {"type": "log"}
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T8" for f in result.blocks))

    def test_log_with_base_no_block(self):
        env = _load("comparison.valid.json")
        env["spec"]["encoding"]["y"]["scale"] = {"type": "log", "base": 10}
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "T8" for f in result.blocks))


class TestT10Banking(unittest.TestCase):
    def test_time_series_aspect_ratio_deviation_warns(self):
        env = _load("time_series.valid.json")
        env["spec"]["mark"] = "line"
        env["spec"]["data"] = {"values": [
            {"x": 0, "y": 10}, {"x": 1, "y": 11}, {"x": 2, "y": 10.5},
            {"x": 3, "y": 12}, {"x": 4, "y": 13}
        ]}
        env["render_hints"] = {"aspect_ratio": 20.0}  # wildly off
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T10" for f in result.warns))


class TestT15CaptionSource(unittest.TestCase):
    def test_caption_complete_no_finding(self):
        env = _load("comparison.valid.json")
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "T15" for f in (result.blocks + result.warns)))

    def test_visually_native_missing_caption_blocks(self):
        env = _load("comparison.valid.json")
        env["relation_to_prose"] = "visually_native"
        env["spec"]["caption"].pop("source", None)
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T15" and f.severity == "Critical" for f in result.blocks))


class TestPhase7CaptionFallback(unittest.TestCase):
    """Phase 7 — Track 2. ``_t7_labelling`` / ``_t15_caption_source_n``
    resolution order:

    1. Non-empty top-level ``envelope.caption`` string → satisfied.
    2. ``spec.caption`` object (when the mode's spec schema permits it)
       → check source / period / n fields.
    3. Neither → flag at path ``envelope.caption``.

    Closes the DUU / tornado schema-vs-checker mismatch diagnosed at
    Phase 6 (``specs/tornado.json`` has no ``caption`` property; the
    old checker required ``spec.caption.source/period/n`` that the
    schema rejects)."""

    def test_tornado_with_envelope_caption_no_finding(self):
        """Top-level envelope.caption string satisfies T7+T15 for
        tornado, which the schema does not permit spec.caption on."""
        env = _load("tornado.valid.json")
        env["caption"] = "Source: internal KPI dashboard. Period: 2026-Q1. n=48."
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "T7" and "caption" in f.path for f in (result.warns + result.blocks + result.infos)))
        self.assertFalse(any(f.rule == "T15" for f in (result.warns + result.blocks + result.infos)))

    def test_tornado_without_caption_flags_envelope_caption(self):
        """Missing both envelope.caption and spec.caption → single T7
        + single T15 finding, both at path envelope.caption."""
        env = _load("tornado.valid.json")
        env.pop("caption", None)  # ensure absent
        result = review_envelope(env)
        t7_caption_findings = [f for f in (result.warns + result.blocks + result.infos)
                               if f.rule == "T7" and "caption" in f.path]
        t15_findings = [f for f in (result.warns + result.blocks + result.infos)
                        if f.rule == "T15"]
        self.assertEqual(len(t7_caption_findings), 1,
                         f"expected exactly 1 T7 caption finding, got {len(t7_caption_findings)}")
        self.assertEqual(t7_caption_findings[0].path, "envelope.caption")
        self.assertEqual(len(t15_findings), 1)
        self.assertEqual(t15_findings[0].path, "envelope.caption")

    def test_comparison_with_envelope_caption_skips_spec_check(self):
        """Top-level envelope.caption takes priority — spec.caption
        check is skipped even if fields would be incomplete."""
        env = _load("comparison.valid.json")
        env["caption"] = "Source: X. Period: Y. n=10."
        env["spec"]["caption"].pop("n", None)  # would normally flag
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "T7" and "caption" in f.path for f in (result.warns + result.blocks + result.infos)))
        self.assertFalse(any(f.rule == "T15" for f in (result.warns + result.blocks + result.infos)))

    def test_comparison_without_envelope_caption_uses_spec_caption(self):
        """No envelope.caption → falls back to legacy spec.caption
        object check (comparison's schema permits the object)."""
        env = _load("comparison.valid.json")
        # Fixture already has no envelope.caption and a complete spec.caption.
        self.assertIsNone(env.get("caption"))
        env["spec"]["caption"].pop("n", None)
        result = review_envelope(env)
        t7_caption_findings = [f for f in (result.warns + result.blocks + result.infos)
                               if f.rule == "T7" and "caption" in f.path]
        self.assertTrue(any(f.path == "spec.caption.n" for f in t7_caption_findings))

    def test_empty_envelope_caption_string_does_not_satisfy(self):
        """Empty / whitespace-only envelope.caption falls through to
        the spec.caption / absent path."""
        env = _load("tornado.valid.json")
        env["caption"] = "   "
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "T7" and f.path == "envelope.caption"
                            for f in (result.warns + result.blocks + result.infos)))

    def test_visually_native_without_any_caption_blocks(self):
        """visually_native without any caption → T15 Critical severity,
        path = envelope.caption (preferred top-level location)."""
        env = _load("tornado.valid.json")
        env.pop("caption", None)
        env["relation_to_prose"] = "visually_native"
        result = review_envelope(env)
        critical_t15 = [f for f in result.blocks
                        if f.rule == "T15" and f.severity == "Critical"]
        self.assertEqual(len(critical_t15), 1)
        self.assertEqual(critical_t15[0].path, "envelope.caption")


# ---------------------------------------------------------------------------
# LLM-prior-inversion checks
# ---------------------------------------------------------------------------

class TestTemplateTrap(unittest.TestCase):
    def test_title_untitled_detected(self):
        env = _load("comparison.valid.json")
        env["title"] = "Untitled"
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "inv.template_trap" for f in result.warns + result.blocks))

    def test_label_chart_1_detected(self):
        env = _load("comparison.valid.json")
        env["title"] = "Chart 1"
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "inv.template_trap" for f in result.warns + result.blocks))

    def test_sample_data_string_detected(self):
        env = _load("comparison.valid.json")
        env["spec"]["data"]["values"] = [{"c": "Sample Data", "v": 1}]
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "inv.template_trap" for f in result.warns + result.blocks))

    def test_clean_title_no_trap(self):
        env = _load("comparison.valid.json")
        env["title"] = "Q1 support ticket volumes by category"
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "inv.template_trap" for f in result.warns + result.blocks))


class TestChartTypeMisselection(unittest.TestCase):
    def test_temporal_x_on_comparison_warns(self):
        env = _load("comparison.valid.json")
        env["spec"]["encoding"]["x"] = {"field": "date", "type": "temporal"}
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "inv.chart_type" for f in result.warns + result.blocks))

    def test_causal_mode_non_causal_type_warns(self):
        env = _load("comparison.valid.json")
        env["mode_context"] = "causal_analysis"
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "inv.chart_type" for f in result.warns + result.blocks))

    def test_causal_mode_on_cld_no_warn(self):
        env = _load("causal_loop_diagram.valid.json")
        env["mode_context"] = "causal_analysis"
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "inv.chart_type" for f in result.warns + result.blocks))


class TestDefaultSettings(unittest.TestCase):
    def test_empty_config_flagged(self):
        env = _load("comparison.valid.json")
        env["spec"]["config"] = {}
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "inv.default_settings" for f in result.infos + result.warns))

    def test_no_config_no_finding(self):
        env = _load("comparison.valid.json")
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "inv.default_settings" for f in result.infos + result.warns + result.blocks))


# ---------------------------------------------------------------------------
# Per-mode strictness escalation
# ---------------------------------------------------------------------------

class TestStrictness(unittest.TestCase):
    def test_strict_mode_escalates_major_to_critical(self):
        # systems-dynamics is 'critical' strictness
        env = _load("comparison.valid.json")
        env.pop("title", None)
        # With no title we expect a T7 Major finding — escalated to Critical.
        result = review_envelope(env, mode="systems-dynamics")
        self.assertTrue(any(f.rule == "T7" and f.severity == "Critical" for f in result.blocks))

    def test_lax_mode_demotes_major_to_minor(self):
        env = _load("comparison.valid.json")
        env.pop("title", None)
        result = review_envelope(env, mode="passion-exploration")
        # T7 should now be Minor
        self.assertTrue(any(f.rule == "T7" and f.severity == "Minor" for f in result.infos))

    def test_standard_mode_keeps_major(self):
        env = _load("comparison.valid.json")
        env.pop("title", None)
        result = review_envelope(env, mode="synthesis")
        self.assertTrue(any(f.rule == "T7" and f.severity == "Major" for f in result.warns))

    def test_critical_never_demoted_in_lax_mode(self):
        env = _load("comparison.valid.json")
        env["spec"]["mark"] = "pie"
        result = review_envelope(env, mode="passion-exploration")
        # T5 is Critical; must remain Critical even in lax mode.
        self.assertTrue(any(f.rule == "T5" and f.severity == "Critical" for f in result.blocks))

    def test_apply_strictness_unit(self):
        self.assertEqual("Critical", _apply_strictness("Major", "systems-dynamics"))
        self.assertEqual("Minor",    _apply_strictness("Major", "passion-exploration"))
        self.assertEqual("Major",    _apply_strictness("Major", "synthesis"))
        self.assertEqual("Critical", _apply_strictness("Critical", "passion-exploration"))
        self.assertEqual("Minor",    _apply_strictness("Minor", "systems-dynamics"))


# ---------------------------------------------------------------------------
# Quadrant axes dependence
# ---------------------------------------------------------------------------

class TestQuadrantDependence(unittest.TestCase):
    def test_perfect_correlation_warns(self):
        env = _load("quadrant_matrix.valid.json")
        env["spec"]["items"] = [
            {"label": "a", "x": 0.1, "y": 0.1},
            {"label": "b", "x": 0.3, "y": 0.3},
            {"label": "c", "x": 0.5, "y": 0.5},
            {"label": "d", "x": 0.7, "y": 0.7},
        ]
        result = review_envelope(env)
        self.assertTrue(any(f.rule == "struct.axes_dependent" for f in result.warns + result.blocks))

    def test_uncorrelated_no_warn(self):
        env = _load("quadrant_matrix.valid.json")
        env["spec"]["items"] = [
            {"label": "a", "x": 0.1, "y": 0.9},
            {"label": "b", "x": 0.2, "y": 0.1},
            {"label": "c", "x": 0.8, "y": 0.5},
            {"label": "d", "x": 0.5, "y": 0.2},
        ]
        result = review_envelope(env)
        self.assertFalse(any(f.rule == "struct.axes_dependent" for f in result.warns + result.blocks))


# ---------------------------------------------------------------------------
# Data/contract
# ---------------------------------------------------------------------------

class TestContract(unittest.TestCase):
    def test_review_result_is_a_ReviewResult(self):
        env = _load("comparison.valid.json")
        result = review_envelope(env)
        self.assertIsInstance(result, ReviewResult)
        self.assertIsInstance(result.blocks, list)
        self.assertIsInstance(result.warns, list)
        self.assertIsInstance(result.infos, list)

    def test_clean_visual_has_no_blocks(self):
        for name in (
            "comparison.valid.json",
            "causal_loop_diagram.valid.json",
            "decision_tree.valid.json",
            "ibis.valid.json",
            "bow_tie.valid.json",
        ):
            env = _load(name)
            result = review_envelope(env)
            self.assertEqual([], result.blocks, f"{name} should produce no blocks")

    def test_finding_as_dict_shape(self):
        f = Finding(rule="T1", severity="Critical", message="m", path="p", suggestion="s")
        d = f.as_dict()
        self.assertEqual(d["rule"], "T1")
        self.assertEqual(d["severity"], "Critical")
        self.assertEqual(d["suggestion"], "s")

    def test_template_trap_constant_nonempty(self):
        self.assertGreater(len(TEMPLATE_TRAP_STRINGS), 5)
        self.assertIn("untitled", TEMPLATE_TRAP_STRINGS)


# ---------------------------------------------------------------------------
# boot.py integration — focused unit test
# ---------------------------------------------------------------------------

class TestProcessResponseIntegration(unittest.TestCase):
    """Mock the boot.py visual hook by passing a sample response through
    ``process_response`` and verifying block/warn behavior. This exercises
    the same code path _run_visual_hook uses — no full pipeline boot."""

    def _wrap(self, env: dict) -> str:
        return (
            "Here is prose context.\n\n"
            "```ora-visual\n"
            + json.dumps(env)
            + "\n```\n\n"
            "More prose."
        )

    def test_valid_block_passes_through(self):
        env = _load("comparison.valid.json")
        text = self._wrap(env)
        new_text, diag = process_response(text, mode="root-cause-analysis")
        self.assertIn("ora-visual", new_text)
        self.assertEqual(1, len(diag["visuals"]))
        self.assertFalse(diag["visuals"][0]["blocked"])

    def test_schema_invalid_block_suppressed(self):
        env = _load("comparison.valid.json")
        env["type"] = "not_a_known_type"
        text = self._wrap(env)
        new_text, diag = process_response(text)
        self.assertNotIn("```ora-visual", new_text)  # block removed
        self.assertTrue(diag["visuals"][0]["blocked"])
        self.assertIn("suppressed", new_text)

    def test_adversarial_critical_suppressed(self):
        env = _load("comparison.valid.json")
        env["spec"]["mark"] = "pie"
        text = self._wrap(env)
        new_text, diag = process_response(text)
        self.assertTrue(diag["visuals"][0]["blocked"])
        self.assertIn("suppressed", new_text)

    def test_no_visual_blocks_is_noop(self):
        text = "Just prose, no ora-visual here."
        new_text, diag = process_response(text)
        self.assertEqual(text, new_text)
        self.assertEqual([], diag["visuals"])

    def test_malformed_json_block_suppressed(self):
        text = "Prose\n\n```ora-visual\n{this is not json}\n```\n\nMore."
        new_text, diag = process_response(text)
        self.assertTrue(diag["visuals"][0]["blocked"])
        self.assertIn("parse error", new_text)

    def test_multiple_blocks_independent(self):
        ok = _load("comparison.valid.json")
        bad = _load("comparison.valid.json")
        bad["spec"]["mark"] = "pie"
        text = self._wrap(ok) + "\n" + self._wrap(bad)
        new_text, diag = process_response(text)
        self.assertEqual(2, len(diag["visuals"]))
        self.assertFalse(diag["visuals"][0]["blocked"])
        self.assertTrue(diag["visuals"][1]["blocked"])


class TestT1LieFactorDirection(unittest.TestCase):
    """Regression: T1 scored its two decisive cases backwards.

    It computed ``data_range / domain_range`` — a fill ratio, how much of the
    axis the data happens to occupy — and called it a lie factor. Consequences:
    an honest zero-baseline chart with any headroom fell below 0.95 and was
    blocked Critical, while the textbook truncated axis fitted snugly to its
    data scored exactly 1.000 and passed. The declaration its own suggestion
    text advertised was never read.
    """

    def _chart(self, values, domain, declared=None) -> dict:
        env = {
            "type": "comparison",
            "spec": {
                "mark": "bar",
                "data": {"values": [{"k": str(i), "v": v}
                                    for i, v in enumerate(values)]},
                "encoding": {"y": {"field": "v", "type": "quantitative",
                                   "scale": {"domain": domain}}},
            },
        }
        if declared:
            env["integrity_declarations"] = {"non_zero_baseline_justified": declared}
        return env

    def _fires(self, values, domain, declared=None) -> bool:
        return bool(va._t1_lie_factor(self._chart(values, domain, declared),
                                      "comparison"))

    # -- honest charts must pass -------------------------------------------
    def test_zero_baseline_with_headroom_passes(self):
        self.assertFalse(self._fires([10, 55, 100], [0, 110]))

    def test_zero_baseline_exact_fit_passes(self):
        self.assertFalse(self._fires([10, 55, 100], [0, 100]))

    def test_zero_baseline_with_tightly_clustered_data_passes(self):
        """The case that most looks like a lie and isn't: near-identical
        values on a zero axis read as near-identical bars."""
        self.assertFalse(self._fires([90, 95, 100], [0, 100]))

    # -- dishonest charts must block ---------------------------------------
    def test_truncated_axis_fitted_to_data_blocks(self):
        """The classic deception, and the exact case the old rule passed."""
        self.assertTrue(self._fires([90, 95, 100], [90, 100]))

    def test_floor_just_below_the_data_blocks(self):
        self.assertTrue(self._fires([90, 95, 100], [88, 102]))

    def test_small_difference_magnified_by_a_high_floor_blocks(self):
        self.assertTrue(self._fires([48, 50, 52], [47, 53]))

    # -- the escape hatch the suggestion advertised ------------------------
    def test_declared_non_zero_baseline_clears_the_block(self):
        self.assertFalse(self._fires([90, 95, 100], [88, 102],
                                     declared="index rebased to 88"))

    # -- scope guards -------------------------------------------------------
    def test_non_length_mark_is_out_of_scope(self):
        env = self._chart([90, 95, 100], [88, 102])
        env["spec"]["mark"] = "line"
        self.assertEqual([], va._t1_lie_factor(env, "comparison"))

    def test_negative_values_are_left_to_other_rules(self):
        self.assertFalse(self._fires([-10, 5, 20], [-20, 30]))

    def test_reported_factor_names_both_ratios(self):
        f = va._t1_lie_factor(self._chart([90, 95, 100], [88, 102]), "comparison")
        self.assertEqual(1, len(f))
        self.assertEqual("Critical", f[0].severity)
        self.assertIn("lie factor", f[0].message)
        self.assertIn("non_zero_baseline_justified", f[0].suggestion)


class TestUnterminatedFenceDoesNotEatProse(unittest.TestCase):
    """Regression: an unterminated ``ora-visual`` fence must not consume the
    prose that follows it.

    The old pattern (```` ```ora-visual\\s*\\n(.*?)\\n``` ````) was non-greedy,
    so an unterminated opening fence closed on the next ``` it could find —
    normally the OPENING fence of an unrelated code block further down. Every
    line in between was captured and replaced with the one-line suppression
    marker, deleting delivered analytical prose and mangling the innocent
    block whose fence was eaten.
    """

    BROKEN = (
        "## Findings\n\n"
        "The mechanism fails under load.\n\n"
        "```ora-visual\n"
        '{"schema_version": "0.2", "id": "fig-1"\n'   # never terminated
        "\n"
        "## Second finding\n\n"
        "This paragraph is real analysis.\n\n"
        "```python\n"
        'print("unrelated code")\n'
        "```\n\n"
        "## Conclusion\n"
    )

    def test_prose_after_unterminated_fence_survives(self):
        new_text, _diag = process_response(self.BROKEN)
        self.assertIn("## Second finding", new_text)
        self.assertIn("This paragraph is real analysis.", new_text)
        self.assertIn("## Conclusion", new_text)

    def test_unrelated_code_fence_is_not_consumed(self):
        new_text, _diag = process_response(self.BROKEN)
        self.assertIn("```python", new_text)
        self.assertIn('print("unrelated code")', new_text)

    def test_unterminated_fence_is_left_inspectable(self):
        """No match means the raw text stays put — the same failure posture
        the client-side dispatcher takes for unparseable JSON."""
        new_text, diag = process_response(self.BROKEN)
        self.assertEqual(self.BROKEN, new_text)
        self.assertEqual([], diag["visuals"])

    def test_language_tagged_fence_is_not_a_closer(self):
        """```` ```python ```` opens a block; it must never close an
        ora-visual block."""
        from visual_recovery import ORA_VISUAL_FENCE_RE
        text = "```ora-visual\n{}\n```python\nx = 1\n```\n"
        m = ORA_VISUAL_FENCE_RE.search(text)
        self.assertIsNone(m)

    def test_well_formed_block_still_matches(self):
        from visual_recovery import ORA_VISUAL_FENCE_RE
        text = 'Above.\n\n```ora-visual\n{"id": "fig-1"}\n```\n\nBelow.\n'
        m = ORA_VISUAL_FENCE_RE.search(text)
        self.assertIsNotNone(m)
        self.assertEqual({"id": "fig-1"}, json.loads(m.group(1)))
        self.assertEqual("Above.\n\n[X]\n\nBelow.\n",
                         ORA_VISUAL_FENCE_RE.sub("[X]", text))

    def test_two_well_formed_blocks_match_separately(self):
        from visual_recovery import ORA_VISUAL_FENCE_RE
        text = ('A\n\n```ora-visual\n{"id":"a"}\n```\n\n'
                'B\n\n```ora-visual\n{"id":"b"}\n```\n\nC\n')
        self.assertEqual(2, len(ORA_VISUAL_FENCE_RE.findall(text)))
        self.assertEqual("A\n\n[X]\n\nB\n\n[X]\n\nC\n",
                         ORA_VISUAL_FENCE_RE.sub("[X]", text))

    def test_strip_helper_shares_the_invariant(self):
        """``boot._strip_visual_blocks_and_markers`` deletes matched blocks
        outright, so it carries the same data-loss risk and must use the same
        pattern."""
        import boot
        stripped = boot._strip_visual_blocks_and_markers(self.BROKEN)
        self.assertIn("This paragraph is real analysis.", stripped)
        self.assertIn('print("unrelated code")', stripped)

    def test_vault_export_span_does_not_overrun(self):
        """The exporter reports spans into the source document; an overrunning
        match would splice away unrelated prose on export."""
        import vault_export
        self.assertEqual([], vault_export._extract_ora_visuals(self.BROKEN))


if __name__ == "__main__":
    unittest.main(verbosity=2)
