#!/usr/bin/env python3
"""
WP-4.2 — Per-mode structural success criteria + adversarial hook.

Covers two properties that have to hold now that the adversarial
reviewer consumes the machine-readable success criteria from each
mode file:

1. ``mode_success_criteria.check_structural`` dispatches to the right
   per-mode checker and returns the expected ``CriterionResult`` shape
   for both valid (all-pass) and invalid (selective-fail) envelopes.
2. ``visual_adversarial.review_envelope`` surfaces Major findings
   keyed ``mode_success_criterion_<id>`` for every structural
   criterion a real envelope violates — and stays silent when the
   envelope passes every criterion.

The tests construct envelopes inline (no schema files read, no Tier A
network calls). That keeps them fast and deterministic while still
exercising the full dispatch → checker → finding-emission path.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from mode_success_criteria import (  # noqa: E402
    CriterionResult,
    check_structural,
    NO_VISUAL_MODES,
    OPTIONAL_ENVELOPE_MODES,
)
from visual_adversarial import review_envelope  # noqa: E402


# ---------------------------------------------------------------------------
# Envelope fixtures — load the canonical examples authored into each mode
# file so we're testing against the exact shapes the harness already proves
# valid via TestModeFileStructure_*.
# ---------------------------------------------------------------------------

MODES_DIR = WORKSPACE / "modes"


def _load_canonical_envelope(mode_name: str) -> dict:
    """Extract the first ``ora-visual`` fence from ``mode_name.md``'s
    EMISSION CONTRACT section and return the parsed envelope."""
    import re as _re
    text = (MODES_DIR / f"{mode_name}.md").read_text()
    ec = _re.search(r"## EMISSION CONTRACT\s*\n(.*?)(?=\n## |\Z)",
                    text, _re.DOTALL)
    if not ec:
        raise RuntimeError(f"{mode_name}: no EMISSION CONTRACT section")
    fence = _re.search(r"```ora-visual\s*\n(.*?)\n```",
                       ec.group(1), _re.DOTALL)
    if not fence:
        raise RuntimeError(f"{mode_name}: no canonical envelope fence")
    return json.loads(fence.group(1))


# ---------------------------------------------------------------------------
# 1) check_structural dispatch
# ---------------------------------------------------------------------------

class TestCheckStructuralDispatch(unittest.TestCase):

    def test_canonical_rca_envelope_passes_all_criteria(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        results = check_structural("root-cause-analysis", env)
        failed = [r for r in results if not r.passed]
        self.assertEqual(
            [], failed,
            f"canonical RCA envelope should pass every structural "
            f"criterion; failed: {[(r.id, r.detail) for r in failed]}",
        )

    def test_canonical_sd_envelope_passes(self) -> None:
        env = _load_canonical_envelope("systems-dynamics")
        results = check_structural("systems-dynamics", env)
        failed = [r for r in results if not r.passed]
        self.assertEqual([], failed,
                         f"canonical SD envelope failed: "
                         f"{[(r.id, r.detail) for r in failed]}")

    def test_canonical_ach_envelope_passes(self) -> None:
        env = _load_canonical_envelope("competing-hypotheses")
        results = check_structural("competing-hypotheses", env)
        failed = [r for r in results if not r.passed]
        self.assertEqual([], failed)

    def test_invalid_rca_type_flagged(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        env["type"] = "quadrant_matrix"  # wrong allowlist
        results = check_structural("root-cause-analysis", env)
        s3 = next(r for r in results if r.id == "S3")
        self.assertFalse(s3.passed, "S3 should flag type outside allowlist")

    def test_invalid_rca_mode_context_flagged(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        env["mode_context"] = "not-root-cause-analysis"
        results = check_structural("root-cause-analysis", env)
        s4 = next(r for r in results if r.id == "S4")
        self.assertFalse(s4.passed, "S4 should flag wrong mode_context")

    def test_rca_effect_solution_phrased_flagged(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        env["spec"]["effect"] = "Improve deployment reliability"
        results = check_structural("root-cause-analysis", env)
        s6 = next(r for r in results if r.id == "S6")
        self.assertFalse(s6.passed, "S6 should flag solution-phrased effect")

    def test_rca_non_canonical_category_flagged(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        env["spec"]["categories"][0]["name"] = "Infrastructure"
        results = check_structural("root-cause-analysis", env)
        s11 = next(r for r in results if r.id == "S11")
        self.assertFalse(s11.passed,
                         "S11 should flag non-canonical 6M category name")

    def test_unknown_mode_returns_empty_list(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        self.assertEqual(
            [], check_structural("not-a-real-mode", env),
            "unknown modes should silently return an empty list, not raise",
        )

    def test_none_envelope_in_no_visual_mode_is_silent_pass(self) -> None:
        for mode in NO_VISUAL_MODES:
            self.assertEqual(
                [], check_structural(mode, None),
                f"{mode}: envelope absent is the expected state",
            )

    def test_none_envelope_in_optional_envelope_mode_is_silent_pass(self) -> None:
        for mode in OPTIONAL_ENVELOPE_MODES:
            self.assertEqual(
                [], check_structural(mode, None),
                f"{mode}: envelope optional, absence is pass",
            )


# ---------------------------------------------------------------------------
# 2) review_envelope adversarial hook
# ---------------------------------------------------------------------------

class TestReviewEnvelopePerModeHook(unittest.TestCase):

    def test_canonical_rca_envelope_emits_no_mode_criterion_findings(self) -> None:
        """The canonical example envelope is authored to pass every
        structural criterion — the adversarial hook should emit no
        ``mode_success_criterion_*`` findings for it."""
        env = _load_canonical_envelope("root-cause-analysis")
        review = review_envelope(env, mode="root-cause-analysis")
        mode_findings = [
            f for bucket in (review.blocks, review.warns, review.infos)
            for f in bucket
            if f.rule.startswith("mode_success_criterion_")
        ]
        self.assertEqual(
            [], mode_findings,
            f"canonical envelope should not produce mode-criterion "
            f"findings; got: {[(f.rule, f.message) for f in mode_findings]}",
        )

    def test_broken_rca_envelope_emits_specific_criterion_finding(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        # Drop below S8's ≥3-category minimum.
        env["spec"]["categories"] = env["spec"]["categories"][:2]
        review = review_envelope(env, mode="root-cause-analysis")
        matching = [
            f for bucket in (review.blocks, review.warns, review.infos)
            for f in bucket
            if f.rule == "mode_success_criterion_S8"
        ]
        self.assertEqual(1, len(matching),
                         "exactly one S8 finding expected")
        self.assertIn("root-cause-analysis/S8", matching[0].message)

    def test_finding_severity_defaults_to_major(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        env["spec"]["categories"] = env["spec"]["categories"][:2]
        review = review_envelope(env, mode="root-cause-analysis")
        s8 = next(
            f for bucket in (review.blocks, review.warns, review.infos)
            for f in bucket
            if f.rule == "mode_success_criterion_S8"
        )
        # root-cause-analysis has standard strictness → Major stays Major
        self.assertEqual("Major", s8.severity)

    def test_envelope_with_no_mode_context_still_reviews(self) -> None:
        """Upstream callers (``visual_adversarial.process_response``)
        may pass an envelope with no explicit mode. The hook must not
        crash, must not emit mode-criterion findings when no checker
        is registered, and must still run the T-rule pass."""
        env = _load_canonical_envelope("root-cause-analysis")
        env["mode_context"] = ""
        review = review_envelope(env, mode=None)
        mode_findings = [
            f for bucket in (review.blocks, review.warns, review.infos)
            for f in bucket
            if f.rule.startswith("mode_success_criterion_")
        ]
        self.assertEqual(
            [], mode_findings,
            "review with no mode should not emit mode-criterion findings",
        )

    def test_unknown_mode_does_not_crash_review(self) -> None:
        env = _load_canonical_envelope("root-cause-analysis")
        review = review_envelope(env, mode="not-a-real-mode")
        # The hook should silently no-op on unknown modes.
        mode_findings = [
            f for bucket in (review.blocks, review.warns, review.infos)
            for f in bucket
            if f.rule.startswith("mode_success_criterion_")
        ]
        self.assertEqual([], mode_findings)


if __name__ == "__main__":
    unittest.main()
