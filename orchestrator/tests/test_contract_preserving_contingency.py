"""Tests for Chunk C — contract-preserving reviser contingency (2026-05-20).

Closes the silent-shape-violation class. Before Chunk C, the Step-5
reviser-degraded contingency substituted the raw Step-3 analyst output
verbatim. The analyst output has no F-Revise contract sections (`##
ADDRESSED`, `## NOT ADDRESSED`, `## CLAIM RESOLUTIONS`, etc.), so when
the verifier or (Gear 4) consolidator parsed it expecting the 8-section
reviser envelope, it failed to find the load-bearing fields. The
verifier's V1 (mandatory-fix coverage) check had nothing to match
against; the consolidator received content shaped differently from
the other healthy stream.

Chunk A + B reduce how often the contingency fires (smoke test:
0 firings). Chunk C makes the residual firings degrade gracefully:
the verifier receives a parseable envelope, registers a substantive
verdict against it, and the cycle loop gets another chance.

Pins:

  1. The wrapped envelope contains all 8 F-Revise contract section
     headers in the canonical order.
  2. The original analyst text is preserved in `## REVISED DRAFT`.
  3. The CHANGELOG names the degradation (audit-trail discipline).
  4. The stream label flows into the diagnostic sections.
  5. The output is non-empty and exceeds the F-Revise minimum chars
     so downstream `_step_output_health` passes.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from boot import _wrap_analyst_as_degraded_reviser_envelope


# The F-Revise universal output contract — these 8 sections, in this
# order, are what the spec mandates (Specification — F-Revise.md §
# "Universal reviser output contract"). The verifier's V1 + V9 checks
# walk these headers; the consolidator parses them when synthesising
# across both Gear 4 streams.
F_REVISE_SECTIONS = [
    "## ADDRESSED",
    "## NOT ADDRESSED",
    "## INCORPORATED",
    "## DECLINED",
    "## CLAIM RESOLUTIONS",
    "## REMAINING UNCERTAINTIES",
    "## REVISED DRAFT",
    "## CHANGELOG",
]


class TestWrappedEnvelopeStructure(unittest.TestCase):
    """The wrapped envelope must satisfy the F-Revise contract shape so
    downstream consumers parse it through their standard regex without
    special-casing."""

    def setUp(self):
        self.analyst_text = (
            "## Root Cause Analysis: Cuprate Superconductivity\n\n"
            "**Why 1:** Because the cuprate phase diagram hosts multiple "
            "intertwined orders rather than a single instability of a "
            "conventional metal.\n\n"
            "**Why 2:** Because the parent compound is a Mott insulator "
            "and doping introduces carriers into a strongly correlated "
            "system where electron-electron interactions dominate."
        )
        self.wrapped = _wrap_analyst_as_degraded_reviser_envelope(
            self.analyst_text, stream_label="depth"
        )

    def test_all_eight_contract_sections_present(self):
        for header in F_REVISE_SECTIONS:
            self.assertIn(
                header, self.wrapped,
                f"Missing F-Revise section: {header!r}",
            )

    def test_sections_appear_in_canonical_order(self):
        positions = [self.wrapped.find(h) for h in F_REVISE_SECTIONS]
        # Each must appear (no -1) and be strictly increasing.
        self.assertTrue(all(p > -1 for p in positions),
                        f"Some sections missing: {positions}")
        self.assertEqual(
            positions, sorted(positions),
            "F-Revise sections must appear in canonical order",
        )

    def test_analyst_text_preserved_in_revised_draft(self):
        # The F-Revise spec allows REVISED DRAFT to carry H2 sub-headings
        # from the mode's original output, so the section extractor must
        # stop at ``## CHANGELOG`` specifically (the canonical last
        # section), not at any ``##``. Slice accordingly and check the
        # analyst text round-tripped intact even though it starts with
        # its own ``## Root Cause Analysis`` heading.
        idx = self.wrapped.find("## REVISED DRAFT")
        self.assertGreater(idx, -1)
        rest = self.wrapped[idx + len("## REVISED DRAFT"):]
        changelog = rest.find("## CHANGELOG")
        self.assertGreater(changelog, -1)
        draft_body = rest[:changelog]
        self.assertIn(self.analyst_text.strip(), draft_body)

    def test_bookkeeping_sections_emit_none_literal(self):
        # Sections with no items must be emitted as the header plus
        # the literal "None." line, per F-Revise spec.
        bookkeeping = [
            "## ADDRESSED",
            "## NOT ADDRESSED",
            "## INCORPORATED",
            "## DECLINED",
            "## CLAIM RESOLUTIONS",
        ]
        for header in bookkeeping:
            idx = self.wrapped.find(header)
            rest = self.wrapped[idx + len(header):]
            next_section = rest.find("\n## ")
            section_body = rest[:next_section].strip()
            self.assertEqual(
                section_body, "None.",
                f"{header} should be empty (None.) — got {section_body!r}",
            )

    def test_changelog_names_the_degradation(self):
        # CHANGELOG must announce that this is a contingency
        # substitution, not a real reviser output — so audits don't
        # mistake the analyst content for a reviser-blessed revision.
        idx = self.wrapped.find("## CHANGELOG")
        self.assertGreater(idx, -1)
        changelog = self.wrapped[idx:]
        self.assertIn("degraded", changelog.lower())
        self.assertIn("analyst output", changelog.lower())

    def test_stream_label_flows_into_diagnostic_sections(self):
        # The 'depth' label should appear in REMAINING UNCERTAINTIES
        # and CHANGELOG so trace audits know which Gear 4 stream
        # degraded.
        self.assertIn("depth", self.wrapped)

    def test_breadth_label_variant(self):
        wrapped_b = _wrap_analyst_as_degraded_reviser_envelope(
            self.analyst_text, stream_label="breadth"
        )
        self.assertIn("breadth", wrapped_b)
        self.assertNotIn("(depth)", wrapped_b)

    def test_gear3_reviser_label_variant(self):
        # Gear 3 passes 'reviser' (no depth/breadth distinction).
        wrapped = _wrap_analyst_as_degraded_reviser_envelope(
            self.analyst_text, stream_label="reviser"
        )
        self.assertIn("reviser", wrapped)

    def test_output_long_enough_for_health_check(self):
        # The reviser's `_call_with_supplement` uses min_chars=200.
        # If the wrapped envelope were shorter, downstream stages
        # that re-pipe through health checks would mark it DEGRADED.
        self.assertGreater(
            len(self.wrapped), 200,
            "wrapped envelope must clear the 200-char min_chars floor",
        )


class TestContractIntegrationWithExistingMachinery(unittest.TestCase):
    """The synthetic envelope should parse through `extract_revised_draft_section`
    (used by the unflagged-claim scan) and any other section-extractor
    consumers without raising.
    """

    def test_revised_draft_extractor_finds_analyst_text(self):
        # `extract_revised_draft_section` (in claim_verification module)
        # walks the reviser output for the `## REVISED DRAFT` section
        # body. The wrapped envelope must round-trip through it.
        try:
            from claim_verification import extract_revised_draft_section
        except ImportError:
            self.skipTest("claim_verification module not importable")

        analyst = "Analyst content goes here. Sufficient length."
        wrapped = _wrap_analyst_as_degraded_reviser_envelope(
            analyst, stream_label="depth"
        )
        extracted = extract_revised_draft_section(wrapped)
        self.assertIn(analyst, extracted or "")


if __name__ == "__main__":
    unittest.main()
