"""Tests for Chunk D — BROKEN structural backstop (2026-05-20).

When the verifier itself goes BROKEN, the prior behaviour was to
always unblock the cycle (re-revising against transport noise can't
help). Chunk D refines that: BROKEN + structurally-sound revised
output still unblocks (output is well-shaped enough to ship without
a verifier blessing), but BROKEN + structurally-bad revised output
treats the cycle as FAIL and re-revises rather than approving garbage.

The structural check is deterministic and permissive — anything
that looks like a reasonable reviser attempt passes. Specifically:

  - Total length >= 200 chars
  - Contains a ``## REVISED DRAFT`` section header
  - REVISED DRAFT body >= 50 chars

Pins:

  1. Empty / very short text fails the check.
  2. Long text without ``## REVISED DRAFT`` fails.
  3. ``## REVISED DRAFT`` with empty body fails.
  4. The synthetic envelope from Chunk C (which is the fall-through
     for degraded reviser streams) passes the check — these two
     defense-in-depth layers compose correctly.
  5. A well-formed reviser output (real one or Chunk C wrapper)
     passes.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from boot import (
    _reviser_output_structural_check,
    _wrap_analyst_as_degraded_reviser_envelope,
)


class TestStructuralCheckFailureModes(unittest.TestCase):

    def test_empty_string_fails(self):
        ok, reason = _reviser_output_structural_check("")
        self.assertFalse(ok)
        self.assertEqual(reason, "empty")

    def test_none_input_fails(self):
        ok, reason = _reviser_output_structural_check(None)
        self.assertFalse(ok)
        # Treated as empty (falsy).
        self.assertIn("empty", reason)

    def test_too_short_fails(self):
        ok, reason = _reviser_output_structural_check("short text")
        self.assertFalse(ok)
        self.assertIn("too short", reason)

    def test_long_text_missing_revised_draft_fails(self):
        # 250 chars of prose with no ## REVISED DRAFT — could be raw
        # analyst output substituted before Chunk C wrapping.
        text = ("Long analyst prose. " * 20)  # ~400 chars
        ok, reason = _reviser_output_structural_check(text)
        self.assertFalse(ok)
        self.assertIn("REVISED DRAFT", reason)

    def test_revised_draft_with_empty_body_fails(self):
        # The reviser emitted the header but no content under it —
        # then transitioned straight into CHANGELOG.
        text = (
            "## ADDRESSED\n" + "x" * 100 + "\n\n"
            "## REVISED DRAFT\n\n"
            "## CHANGELOG\n"
            "Refused to produce a draft.\n"
        )
        # Make it long enough to pass the length floor.
        text = text + ("padding " * 30)
        ok, reason = _reviser_output_structural_check(text)
        self.assertFalse(ok)
        self.assertIn("REVISED DRAFT body", reason)


class TestStructuralCheckPasses(unittest.TestCase):

    def test_chunk_c_synthetic_envelope_passes(self):
        # The Chunk C contingency wraps degraded reviser output in a
        # synthetic envelope. The two defenses must compose: Chunk C's
        # output must pass Chunk D's structural check, so when both
        # defenses fire together (degraded reviser AND broken verifier),
        # the structural-pass path triggers.
        analyst = (
            "Cuprate phase diagram hosts antiferromagnetism, pseudogap, "
            "and strange-metal regions that no single weak-coupling "
            "framework cleanly explains. The Mott parent compound, "
            "intertwined orders, and absence of a small expansion "
            "parameter together obstruct a unified theory."
        )
        wrapped = _wrap_analyst_as_degraded_reviser_envelope(
            analyst, stream_label="depth"
        )
        ok, reason = _reviser_output_structural_check(wrapped)
        self.assertTrue(ok, f"Chunk C envelope failed structural check: {reason}")
        self.assertEqual(reason, "ok")

    def test_realistic_reviser_output_passes(self):
        # A bare-bones but well-formed reviser output. Mirrors what
        # the verifier sees when the reviser model behaved.
        text = (
            "## ADDRESSED\n"
            "- Finding 1 — addressed: framework header inserted.\n\n"
            "## NOT ADDRESSED\nNone.\n\n"
            "## INCORPORATED\nNone.\n\n"
            "## DECLINED\nNone.\n\n"
            "## CLAIM RESOLUTIONS\nNone.\n\n"
            "## REMAINING UNCERTAINTIES\nNone.\n\n"
            "## REVISED DRAFT\n"
            "Detailed analytical text spanning the full 5 Whys cascade. "
            "Why 1, Why 2, Why 3, Why 4 each filled in with depth-4 "
            "reasoning. Alternative branches considered.\n\n"
            "## CHANGELOG\nFramework header added.\n"
        )
        ok, reason = _reviser_output_structural_check(text)
        self.assertTrue(ok, f"realistic reviser output failed: {reason}")

    def test_revised_draft_with_h2_subheadings_in_body_passes(self):
        # F-Revise spec allows REVISED DRAFT to carry mode-specific
        # H2 sub-headings. The structural check must NOT mistake an
        # inner ## for an early section boundary.
        text = (
            "## ADDRESSED\nNone.\n\n"
            "## NOT ADDRESSED\nNone.\n\n"
            "## INCORPORATED\nNone.\n\n"
            "## DECLINED\nNone.\n\n"
            "## CLAIM RESOLUTIONS\nNone.\n\n"
            "## REMAINING UNCERTAINTIES\nNone.\n\n"
            "## REVISED DRAFT\n"
            "## Root Cause Analysis\n\n"
            "Why 1: substantial body content here exceeding fifty chars.\n\n"
            "## Alternative Chains\n\n"
            "Branch A and Branch B considered.\n\n"
            "## CHANGELOG\n"
            "No substantive changes.\n"
        )
        ok, reason = _reviser_output_structural_check(text)
        self.assertTrue(ok, f"H2-subheading-in-body failed: {reason}")


class TestChunkCAndChunkDComposition(unittest.TestCase):
    """Chunks C and D are two layers of defense for the same failure
    class. C produces a contract-shaped fallback when the reviser
    degrades; D gates BROKEN-unblock on a structural check. They must
    compose cleanly: a degraded reviser run produces Chunk C output,
    which then passes Chunk D's check.
    """

    def test_degraded_reviser_to_passing_structural_check(self):
        analyst_outputs = [
            # Short but >= the substituted-analyst content size
            ("Short analyst content. " * 10),
            # Realistic length
            ("Full root-cause analysis output. " * 50),
        ]
        for analyst in analyst_outputs:
            with self.subTest(analyst_len=len(analyst)):
                wrapped = _wrap_analyst_as_degraded_reviser_envelope(
                    analyst, stream_label="depth"
                )
                ok, reason = _reviser_output_structural_check(wrapped)
                self.assertTrue(
                    ok,
                    f"Chunk C/D composition failed for analyst len "
                    f"{len(analyst)}: {reason}",
                )

    def test_degraded_reviser_with_minimal_analyst_still_passes(self):
        # Edge: the analyst itself was very short. The synthetic
        # envelope adds ~700 chars of contract scaffolding, so even a
        # tiny analyst text yields a structurally-passing wrap.
        wrapped = _wrap_analyst_as_degraded_reviser_envelope(
            "Brief.", stream_label="depth"
        )
        ok, reason = _reviser_output_structural_check(wrapped)
        # The wrapper's contract scaffolding gives us total length;
        # the REVISED DRAFT body is just "Brief." — only 6 chars,
        # which fails the >=50-char body floor. This is the boundary
        # case worth pinning.
        self.assertFalse(ok)
        self.assertIn("REVISED DRAFT body", reason)


if __name__ == "__main__":
    unittest.main()
