#!/usr/bin/env python3
"""
WP-5.4 — unit tests for ``mode_success_criteria.check_evaluator_output_shape``.

The universal evaluator output contract (defined in ``frameworks/book/
f-evaluate.md`` and reproduced in §5 of the Pipeline Cascade Integration
Plan) requires every evaluator response to emit seven Markdown sections in
order: VERDICT / CONFIDENCE / MANDATORY FIXES / SUGGESTED IMPROVEMENTS /
COVERAGE GAPS / UNCERTAINTIES / CROSS-FINDING CONFLICTS.

These tests exercise both synthetic well-formed and synthetic ill-formed
evaluator outputs. Live evaluator outputs captured during WP-5.5 cascade
harness runs will slot into this test surface as regression cases.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))


def _well_formed_evaluator_output() -> str:
    return """## VERDICT

partial — the fishbone covers three 6M categories but S12 fails.

## CONFIDENCE

moderate

## MANDATORY FIXES

- **Finding 1 — `S12`**
  - citation: "short_alt: 'Fishbone of intermittent software deployment failures across Method, Machine, Material, Measurement, Milieu, and Man categories highlighting procedural, infrastructural and human factors.'"
  - violated_criterion_id: S12
  - what's_wrong: short_alt exceeds 150 characters (185 chars observed).
  - what's_required: short_alt ≤ 150 chars; apply the mode's S12 template ('Fishbone of <short noun phrase ≤ 60 chars>.').

- **Finding 2 — `S10`**
  - citation: §categories — all branches are depth 1
  - violated_criterion_id: S10
  - what's_wrong: no branch reaches sub_cause depth 2.
  - what's_required: at least one branch with cause → sub_cause depth 2.

## SUGGESTED IMPROVEMENTS

- **Suggestion 1 — priority 1**
  - citation: "Method category contains 'deployment is unreliable'"
  - current_state: cause paraphrases the effect.
  - suggested_change: Rewrite cause to name a specific process failure, e.g. "no canary stage in the deployment pipeline".
  - reasoning: Restatement is not a cause; the restatement trap triggers M3.
  - expected_benefit: M3 (non-trivial chain) moves from fail to pass.
  - criterion_it_would_move: M3

## COVERAGE GAPS

- §Evidence assessment: missing — content contract clause 5 required.

## UNCERTAINTIES

- M3: requires domain expertise to judge whether sub-cause is genuinely deeper than parent. Would resolve with: engineering-domain reviewer check.

## CROSS-FINDING CONFLICTS

None.
"""


def _missing_sections_output() -> str:
    return """## VERDICT

pass — looks good.

## CONFIDENCE

high

## MANDATORY FIXES

None.
"""


def _wrong_verdict_token_output() -> str:
    return """## VERDICT

maybe — unsure.

## CONFIDENCE

moderate

## MANDATORY FIXES

None.

## SUGGESTED IMPROVEMENTS

None.

## COVERAGE GAPS

None.

## UNCERTAINTIES

None.

## CROSS-FINDING CONFLICTS

None.
"""


def _out_of_order_sections_output() -> str:
    # VERDICT comes after CONFIDENCE — violates E2.
    return """## CONFIDENCE

high

## VERDICT

pass — fine.

## MANDATORY FIXES

None.

## SUGGESTED IMPROVEMENTS

None.

## COVERAGE GAPS

None.

## UNCERTAINTIES

None.

## CROSS-FINDING CONFLICTS

None.
"""


def _finding_missing_fields_output() -> str:
    return """## VERDICT

fail — multiple criteria unmet.

## CONFIDENCE

moderate

## MANDATORY FIXES

- **Finding 1 — `S8`**
  - citation: "category count is 2"
  - violated_criterion_id: S8

## SUGGESTED IMPROVEMENTS

None.

## COVERAGE GAPS

None.

## UNCERTAINTIES

None.

## CROSS-FINDING CONFLICTS

None.
"""


class TestCheckEvaluatorOutputShape(unittest.TestCase):

    def test_well_formed_output_passes_all_seven_checks(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        results = check_evaluator_output_shape(_well_formed_evaluator_output())
        self.assertEqual(len(results), 7)
        failed = [(r.id, r.detail) for r in results if not r.passed]
        self.assertEqual(failed, [], f"unexpected failures: {failed}")

    def test_missing_sections_fails_e1_and_e7(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        results = check_evaluator_output_shape(_missing_sections_output())
        by_id = {r.id: r for r in results}
        self.assertFalse(by_id["E1"].passed)  # headers missing
        self.assertFalse(by_id["E7"].passed)  # tail sections absent
        # E3 and E4 should still pass (VERDICT / CONFIDENCE valid).
        self.assertTrue(by_id["E3"].passed)
        self.assertTrue(by_id["E4"].passed)

    def test_wrong_verdict_token_fails_e3(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        results = check_evaluator_output_shape(_wrong_verdict_token_output())
        by_id = {r.id: r for r in results}
        self.assertFalse(by_id["E3"].passed)
        self.assertIn("maybe", by_id["E3"].detail)

    def test_out_of_order_sections_fails_e2(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        results = check_evaluator_output_shape(_out_of_order_sections_output())
        by_id = {r.id: r for r in results}
        self.assertFalse(by_id["E2"].passed)
        self.assertIn("out-of-order", by_id["E2"].detail)

    def test_finding_missing_fields_fails_e5(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        results = check_evaluator_output_shape(_finding_missing_fields_output())
        by_id = {r.id: r for r in results}
        self.assertFalse(by_id["E5"].passed)
        # The missing fields should be named in the detail.
        self.assertIn("missing=", by_id["E5"].detail)

    def test_empty_mandatory_fixes_as_none_passes_e5(self) -> None:
        """A section legitimately empty of findings emits the literal
        ``None.`` — this is a pass, not a fail."""
        from mode_success_criteria import check_evaluator_output_shape
        results = check_evaluator_output_shape(_well_formed_evaluator_output()
            .replace(
            "## CROSS-FINDING CONFLICTS\n\nNone.",
            "## CROSS-FINDING CONFLICTS\n\nNone."
        ))
        by_id = {r.id: r for r in results}
        # CROSS-FINDING CONFLICTS is 'None.' in the well-formed fixture;
        # E7 should still pass because the header is present.
        self.assertTrue(by_id["E7"].passed)

    def test_suggestions_missing_fields_fails_e6(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        bad = _well_formed_evaluator_output().replace(
            "  - criterion_it_would_move: M3",
            "  # removed criterion_it_would_move intentionally"
        )
        results = check_evaluator_output_shape(bad)
        by_id = {r.id: r for r in results}
        self.assertFalse(by_id["E6"].passed)
        self.assertIn("criterion_it_would_move", by_id["E6"].detail)

    def test_canonical_section_tuple_exposed(self) -> None:
        """EVALUATOR_CONTRACT_SECTIONS is part of the public surface — it
        documents the mandated section order for downstream consumers."""
        from mode_success_criteria import EVALUATOR_CONTRACT_SECTIONS
        self.assertEqual(EVALUATOR_CONTRACT_SECTIONS, (
            "VERDICT",
            "CONFIDENCE",
            "MANDATORY FIXES",
            "SUGGESTED IMPROVEMENTS",
            "COVERAGE GAPS",
            "UNCERTAINTIES",
            "CROSS-FINDING CONFLICTS",
        ))

    def test_wrong_confidence_token_fails_e4(self) -> None:
        from mode_success_criteria import check_evaluator_output_shape
        bad = _well_formed_evaluator_output().replace(
            "## CONFIDENCE\n\nmoderate",
            "## CONFIDENCE\n\nsomewhat"
        )
        results = check_evaluator_output_shape(bad)
        by_id = {r.id: r for r in results}
        self.assertFalse(by_id["E4"].passed)
        self.assertIn("somewhat", by_id["E4"].detail)


if __name__ == "__main__":
    unittest.main()
