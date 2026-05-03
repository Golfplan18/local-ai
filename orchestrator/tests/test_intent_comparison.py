#!/usr/bin/env python3
"""V3 Input Handling Phase 1 — alignment-prefilter parser + comparison tests.

Covers two pieces of pure logic added by Phase 1:

1. ``parse_classification_output`` extracts the new ``Detected invocation``
   field with the same template-skip and mode-name-validation rules as the
   existing ``Selected mode`` extractor.
2. ``compare_intent_with_mode`` resolves expressed intent (manual selection
   OR detected invocation) against the classifier's picked mode, with
   framework selection suppressing the prefilter entirely.

Both functions are deterministic Python — no model calls. Live-fire
verification of the classifier emitting the new field belongs in a separate
end-to-end check the user runs against the local-fast endpoint.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from boot import compare_intent_with_mode, parse_classification_output


class TestDetectedInvocationParsing(unittest.TestCase):
    """``parse_classification_output`` extracts the new field correctly."""

    def _classification(self, detected_line: str) -> dict:
        """Build a synthetic classifier response with the given line."""
        return parse_classification_output(
            "### MODE CLASSIFICATION\n"
            "- Selected mode: standard\n"
            "- Runner-up: adversarial\n"
            "- Confidence: high\n"
            "- Intent category: LEARNING\n"
            "- Reasoning: explanatory prompt\n"
            "- Triage tier: 1\n"
            f"- Detected invocation: {detected_line}\n"
        )

    def test_extracts_known_mode(self):
        result = self._classification("steelman-construction")
        self.assertEqual(result["detected_invocation"], "steelman-construction")

    def test_none_yields_empty_string(self):
        result = self._classification("NONE")
        self.assertEqual(result["detected_invocation"], "")

    def test_template_placeholder_yields_empty(self):
        result = self._classification("[mode-name or NONE]")
        self.assertEqual(result["detected_invocation"], "")

    def test_unknown_mode_yields_empty(self):
        # Validation is anchored to MODES_DIR; fabricated names are rejected
        # so the prefilter never compares against a non-existent mode.
        result = self._classification("not-a-real-mode")
        self.assertEqual(result["detected_invocation"], "")

    def test_field_absent_defaults_to_empty(self):
        # Backward compatibility with classifier responses produced before
        # the prompt was extended (legacy six-field shape).
        legacy = parse_classification_output(
            "### MODE CLASSIFICATION\n"
            "- Selected mode: standard\n"
            "- Runner-up: adversarial\n"
            "- Confidence: high\n"
            "- Intent category: LEARNING\n"
            "- Reasoning: explanatory prompt\n"
            "- Triage tier: 1\n"
        )
        self.assertEqual(legacy["detected_invocation"], "")

    def test_other_fields_unchanged(self):
        result = self._classification("steelman-construction")
        self.assertEqual(result["mode"], "standard")
        self.assertEqual(result["runner_up"], "adversarial")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["intent_category"], "LEARNING")
        self.assertEqual(result["triage_tier"], 1)


class TestCompareIntentWithMode(unittest.TestCase):
    """``compare_intent_with_mode`` resolution rules across all branches."""

    def test_no_expression_matches(self):
        r = compare_intent_with_mode(picked_mode="standard")
        self.assertTrue(r["matches"])
        self.assertIsNone(r["expressed_intent"])
        self.assertIsNone(r["expressed_source"])
        self.assertEqual(r["picked_mode"], "standard")

    def test_manual_matches_picked(self):
        r = compare_intent_with_mode(
            picked_mode="root-cause-analysis",
            manual_mode_selection="root-cause-analysis",
        )
        self.assertTrue(r["matches"])
        self.assertEqual(r["expressed_intent"], "root-cause-analysis")
        self.assertEqual(r["expressed_source"], "manual")

    def test_manual_mismatches_picked(self):
        # Classic prefilter trigger — user picked steelman, classifier said
        # standard. Mismatch surfaces; UI shows the popup.
        r = compare_intent_with_mode(
            picked_mode="standard",
            manual_mode_selection="steelman-construction",
        )
        self.assertFalse(r["matches"])
        self.assertEqual(r["expressed_intent"], "steelman-construction")
        self.assertEqual(r["expressed_source"], "manual")

    def test_detected_matches_picked(self):
        r = compare_intent_with_mode(
            picked_mode="root-cause-analysis",
            detected_invocation="root-cause-analysis",
        )
        self.assertTrue(r["matches"])
        self.assertEqual(r["expressed_intent"], "root-cause-analysis")
        self.assertEqual(r["expressed_source"], "detected")

    def test_detected_mismatches_picked(self):
        # User wrote "steelman this" but classifier picked standard.
        # Prose-level intent disagrees with classifier — prefilter trigger.
        r = compare_intent_with_mode(
            picked_mode="standard",
            detected_invocation="steelman-construction",
        )
        self.assertFalse(r["matches"])
        self.assertEqual(r["expressed_intent"], "steelman-construction")
        self.assertEqual(r["expressed_source"], "detected")

    def test_manual_wins_over_detected(self):
        # Both set → manual is the source of expressed intent. Detected is
        # echoed in the result for telemetry but does not gate the match.
        r = compare_intent_with_mode(
            picked_mode="standard",
            manual_mode_selection="root-cause-analysis",
            detected_invocation="steelman-construction",
        )
        self.assertEqual(r["expressed_source"], "manual")
        self.assertEqual(r["expressed_intent"], "root-cause-analysis")
        self.assertEqual(r["detected_invocation"], "steelman-construction")
        self.assertFalse(r["matches"])  # manual != picked

    def test_framework_suppresses_prefilter(self):
        # Per V3 Q3: framework selected → prefilter suppressed entirely,
        # regardless of how mode intent is expressed.
        r = compare_intent_with_mode(
            picked_mode="standard",
            manual_mode_selection="steelman-construction",  # would mismatch
            detected_invocation="root-cause-analysis",       # would mismatch
            framework_selected="document-processing",
        )
        self.assertTrue(r["matches"])
        self.assertEqual(r["expressed_source"], "framework")
        self.assertIsNone(r["expressed_intent"])

    def test_explicit_none_in_detected_treated_as_empty(self):
        # Defensive: if upstream forwards "NONE" verbatim, treat it as no
        # invocation rather than a mode named NONE.
        r = compare_intent_with_mode(
            picked_mode="standard",
            detected_invocation="NONE",
        )
        self.assertTrue(r["matches"])
        self.assertIsNone(r["expressed_intent"])
        self.assertEqual(r["detected_invocation"], "")

    def test_whitespace_in_inputs_stripped(self):
        r = compare_intent_with_mode(
            picked_mode="standard",
            manual_mode_selection="  steelman-construction  ",
        )
        self.assertEqual(r["expressed_intent"], "steelman-construction")
        self.assertFalse(r["matches"])


if __name__ == "__main__":
    unittest.main()
