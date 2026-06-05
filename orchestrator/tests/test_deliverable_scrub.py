"""Unit tests for the Step 8.5 deliverable scrub (``_scrub_pipeline_leaks``).

Deterministic, no model calls. The scrub's whole value rests on a single
property: it strips leaked Ora pipeline vocabulary while NEVER touching
legitimate answer content. The "never" half is the load-bearing one — a false
positive silently deletes a line of the user's answer — so the no-false-
positive cases below are the real test surface.

Run:
    cd ~/ora && /opt/homebrew/bin/python3 -m unittest orchestrator.tests.test_deliverable_scrub
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # orchestrator/
WORKTREE_ROOT = os.path.dirname(HERE)                                # repo root
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util as _ilu


def _load_worktree(modname: str):
    """Force-load THIS worktree's boot.py (mirrors test_gear4_degradation)."""
    fname = os.path.join(HERE, f"{modname}.py")
    spec = _ilu.spec_from_file_location(modname, fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


boot = _load_worktree("boot")

try:
    from claim_verification import extract_revised_draft_section
    _HAVE_EXTRACTOR = True
except Exception:  # pragma: no cover
    _HAVE_EXTRACTOR = False


class TestStripsLeakedScaffolding(unittest.TestCase):
    def test_strips_reviser_envelope_headings(self):
        text = (
            "## NOT ADDRESSED\n\nThe evaluator's point about X stands.\n\n"
            "## REVISED DRAFT\n\nThe real answer the user wants is right here.\n\n"
            "## CLAIM RESOLUTIONS\n\n- claim 1: verified against FRED\n"
        )
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertIn("The real answer the user wants is right here.", cleaned)
        self.assertNotIn("## NOT ADDRESSED", cleaned)
        self.assertNotIn("## REVISED DRAFT", cleaned)
        self.assertNotIn("## CLAIM RESOLUTIONS", cleaned)
        self.assertEqual(len(removed), 3)
        self.assertFalse(err)

    def test_strips_verifier_output_and_verdict_line(self):
        text = (
            "## VERIFIED FINAL OUTPUT\n\nThe answer body.\n\n"
            "VERDICT: PASS\n"
        )
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertNotIn("VERIFIED FINAL OUTPUT", cleaned)
        self.assertNotIn("VERDICT: PASS", cleaned)
        self.assertIn("The answer body.", cleaned)
        self.assertEqual(len(removed), 2)

    def test_strips_lowercase_and_deeper_heading(self):
        # Case-insensitive, any heading depth.
        text = "#### claim resolutions\n\nbody\n"
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertEqual(len(removed), 1)
        self.assertIn("body", cleaned)

    def test_flags_leaked_error_marker(self):
        text = "[Error calling OpenAI API: rate_limit_exceeded (429)]"
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertTrue(err)

    def test_flags_truncation_marker(self):
        text = "Some partial analysis...\n\n[TRUNCATED at max_tokens=32000: the model's]"
        _, _, err = boot._scrub_pipeline_leaks(text)
        self.assertTrue(err)


class TestNeverStripsLegitimateContent(unittest.TestCase):
    def test_preserves_normal_answer_headings(self):
        text = (
            "## Summary\n\nThe tariff policy has three effects.\n\n"
            "## Analysis\n\nFirst, prices rise.\n\n"
            "## Recommendations\n\nDo X, then Y.\n\n"
            "## Key Findings\n\n- a\n- b\n"
        )
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertEqual(cleaned, text)          # returned verbatim
        self.assertEqual(removed, [])
        self.assertFalse(err)

    def test_preserves_ambiguous_headings_excluded_by_design(self):
        # These appear in the frameworks but are too generic to deny-list.
        text = (
            "## Changelog\n\n- v2 released.\n\n"
            "## Coverage Gaps\n\nThe insurance policy omits flood damage.\n\n"
            "## Trigger Conditions\n\nAsthma attacks follow cold air.\n\n"
            "## Success Criteria\n\nShip by Q3.\n\n"
            "## Mandatory Fixes\n\nPatch the null deref.\n"
        )
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(removed, [])

    def test_preserves_inline_pipeline_words(self):
        # "corpus", "provenance", "depth", "verdict" as ordinary words survive.
        text = (
            "The training corpus was large, and the provenance of each claim "
            "was checked in depth. The court's verdict was unanimous."
        )
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(removed, [])
        self.assertFalse(err)

    def test_preserves_verdict_as_prose_line(self):
        # A "verdict:" line that is not the contract form must survive.
        text = "Verdict: the merger is anticompetitive on three grounds."
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(removed, [])

    def test_does_not_match_partial_heading(self):
        # End-anchored: a real heading that merely starts with a denied name
        # must not be stripped.
        text = "## Revised draft of the merger agreement\n\nClause 1 ...\n"
        cleaned, removed, err = boot._scrub_pipeline_leaks(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(removed, [])

    def test_empty_and_whitespace_input(self):
        for blank in ("", "   ", "\n\n"):
            cleaned, removed, err = boot._scrub_pipeline_leaks(blank)
            self.assertEqual(cleaned, blank)
            self.assertEqual(removed, [])
            self.assertFalse(err)


@unittest.skipUnless(_HAVE_EXTRACTOR, "claim_verification not importable")
class TestGear3LeakFixContract(unittest.TestCase):
    """run_gear3 now surfaces only the ``## REVISED DRAFT`` body instead of the
    whole reviser envelope. This guards the extractor contract that fix relies
    on: a full envelope reduces to just the answer, every bookkeeping section
    dropped; a missing draft returns "" (the signal run_gear3 uses to fall back
    to the full text, so the change is never worse than the prior behaviour).
    """

    def test_full_envelope_reduces_to_draft_body(self):
        envelope = (
            "## ADDRESSED\n\nThe evaluator's three fixes were applied.\n\n"
            "## NOT ADDRESSED\n\nNone.\n\n"
            "## INCORPORATED\n\nWeb evidence on tariffs.\n\n"
            "## DECLINED\n\nNone.\n\n"
            "## CLAIM RESOLUTIONS\n\n- 3.4% verified vs FRED.\n\n"
            "## REMAINING UNCERTAINTIES\n\nQ3 data not yet released.\n\n"
            "## REVISED DRAFT\n\n"
            "## The tariff's real effect\n\n"
            "The policy raises consumer prices by roughly 3%, and here is why ...\n\n"
            "## CHANGELOG\n\n- tightened the second paragraph.\n"
        )
        body = extract_revised_draft_section(envelope)
        # The answer (including its own H2 heading) survives ...
        self.assertIn("The tariff's real effect", body)
        self.assertIn("raises consumer prices by roughly 3%", body)
        # ... and none of the pipeline bookkeeping does.
        for leaked in ("## ADDRESSED", "## NOT ADDRESSED", "## INCORPORATED",
                       "## DECLINED", "## CLAIM RESOLUTIONS",
                       "## REMAINING UNCERTAINTIES", "## CHANGELOG"):
            self.assertNotIn(leaked, body)

    def test_missing_draft_returns_empty_triggering_fallback(self):
        self.assertEqual(extract_revised_draft_section("## ADDRESSED\n\nx\n"), "")
        self.assertEqual(extract_revised_draft_section(""), "")


class TestScrubDoesNotShadowVerifier(unittest.TestCase):
    """Regression guard for the _VERDICT_LINE_RE name collision (2026-06-05).

    The scrub's verdict regex must NOT reuse the name of the verifier's own
    ``_VERDICT_LINE_RE`` (whose ``(?P<verdict>...)`` group
    ``_extract_structured_verdict`` reads). The collision shadowed the
    verifier's regex with one that has no named group, so every verifier
    health-check raised ``no such group`` — silently disabling verification
    across gear-3 and gear-4 (the structural-fallback unblocked every cycle).
    These assert the verifier path is intact.
    """

    def test_extract_structured_verdict_does_not_raise(self):
        # The exact operation that threw: .group("verdict") on a verdict line.
        self.assertEqual(boot._extract_structured_verdict("checks done.\n\nVERDICT: PASS"), "PASS")
        self.assertEqual(boot._extract_structured_verdict("issues found.\n\nVERDICT: FAIL"), "FAIL")
        self.assertEqual(boot._extract_structured_verdict("VERDICT: BROKEN"), "BROKEN")
        # legacy free-form must still classify (not raise)
        self.assertIsNotNone(boot._extract_structured_verdict("The analysis is sound.\n\nVERIFIED"))

    def test_verifier_health_check_passes_on_valid_verdict(self):
        # The exact call that threw in the gear-4 smoke test (step6 verifier).
        ok, reason = boot._step_output_health(
            "Ran V1-V9. All checks pass.\n\nVERDICT: PASS", "verifier", min_chars=20)
        self.assertTrue(ok, f"verifier health check should pass, got: {reason!r}")

    def test_the_two_verdict_regexes_are_distinct(self):
        # Verifier's regex carries the named group; the scrub's deliberately does not.
        self.assertIn("verdict", boot._VERDICT_LINE_RE.groupindex)
        self.assertEqual(boot._SCRUB_VERDICT_LINE_RE.groupindex, {})


if __name__ == "__main__":
    unittest.main()
