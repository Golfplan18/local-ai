"""Tests for orchestrator/claim_verification.py — Pattern B's pre-flight.

Coverage:
  - parse_flagged_claims: section detection, "None." handling, multi-claim
    parsing, surface-variation tolerance, dropping entries without
    challenge_query.
  - assemble_claim_verification_evidence: empty list, single-claim happy
    path with mocked DDG, multi-claim parallel execution, errored search,
    empty results.
  - _format_evidence_block: empty, single claim, error case, no-results
    case.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import claim_verification  # noqa: E402


# ---------------------------------------------------------------------------
# parse_flagged_claims
# ---------------------------------------------------------------------------


class ParseFlaggedClaims(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(claim_verification.parse_flagged_claims(""), [])

    def test_missing_section(self):
        text = "## VERDICT\npass\n\n## UNCERTAINTIES\nNone.\n"
        self.assertEqual(claim_verification.parse_flagged_claims(text), [])

    def test_none_body(self):
        text = "## FLAGGED CLAIMS\n\nNone.\n\n## UNCERTAINTIES\nNone.\n"
        self.assertEqual(claim_verification.parse_flagged_claims(text), [])

    def test_parens_none(self):
        text = "## FLAGGED CLAIMS\n\n(none)\n\n## UNCERTAINTIES\nNone.\n"
        self.assertEqual(claim_verification.parse_flagged_claims(text), [])

    def test_single_claim(self):
        text = (
            "## FLAGGED CLAIMS\n\n"
            "- **Claim 1 — `dated-event` — risk: high**\n"
            '  - claim: "the moon landing was in 1970"\n'
            "  - why_flagged: load-bearing date claim\n"
            "  - challenge_query: Apollo 11 moon landing year\n\n"
            "## UNCERTAINTIES\nNone.\n"
        )
        claims = claim_verification.parse_flagged_claims(text)
        self.assertEqual(len(claims), 1)
        c = claims[0]
        self.assertEqual(c["claim_num"], 1)
        self.assertEqual(c["claim_type"], "dated-event")
        self.assertEqual(c["risk_level"], "high")
        self.assertEqual(c["claim"], "the moon landing was in 1970")
        self.assertEqual(c["challenge_query"], "Apollo 11 moon landing year")

    def test_multiple_claims(self):
        text = (
            "## FLAGGED CLAIMS\n\n"
            "- **Claim 1 — `dated-event` — risk: high**\n"
            '  - claim: "first"\n'
            "  - why_flagged: a\n"
            "  - challenge_query: q1\n\n"
            "- **Claim 2 — `quantitative-figure` — risk: moderate**\n"
            '  - claim: "second"\n'
            "  - why_flagged: b\n"
            "  - challenge_query: q2\n\n"
            "- **Claim 3 — `named-entity` — risk: low**\n"
            '  - claim: "third"\n'
            "  - why_flagged: c\n"
            "  - challenge_query: q3\n\n"
            "## UNCERTAINTIES\nNone.\n"
        )
        claims = claim_verification.parse_flagged_claims(text)
        self.assertEqual(len(claims), 3)
        self.assertEqual([c["claim_num"] for c in claims], [1, 2, 3])
        self.assertEqual(
            [c["risk_level"] for c in claims],
            ["high", "moderate", "low"],
        )

    def test_drops_entry_without_challenge_query(self):
        # A claim entry with no challenge_query has nothing to verify; the
        # parser drops it so the assembler doesn't receive empty queries.
        text = (
            "## FLAGGED CLAIMS\n\n"
            "- **Claim 1 — `dated-event` — risk: high**\n"
            '  - claim: "good"\n'
            "  - why_flagged: a\n"
            "  - challenge_query: q1\n\n"
            "- **Claim 2 — `named-entity` — risk: low**\n"
            '  - claim: "bad"\n'
            "  - why_flagged: b\n"
            # no challenge_query line
            "\n"
            "## UNCERTAINTIES\nNone.\n"
        )
        claims = claim_verification.parse_flagged_claims(text)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim_num"], 1)

    def test_surface_variation_em_dash_vs_hyphen(self):
        # Em-dash and hyphen both accepted as separators in claim header.
        text_em = (
            "## FLAGGED CLAIMS\n\n"
            "- **Claim 1 — `dated-event` — risk: high**\n"
            '  - claim: "x"\n'
            "  - why_flagged: a\n"
            "  - challenge_query: q\n\n"
            "## UNCERTAINTIES\nNone.\n"
        )
        text_hy = (
            "## FLAGGED CLAIMS\n\n"
            "- **Claim 1 - `dated-event` - risk: high**\n"
            '  - claim: "x"\n'
            "  - why_flagged: a\n"
            "  - challenge_query: q\n\n"
            "## UNCERTAINTIES\nNone.\n"
        )
        self.assertEqual(len(claim_verification.parse_flagged_claims(text_em)), 1)
        self.assertEqual(len(claim_verification.parse_flagged_claims(text_hy)), 1)

    def test_section_at_end_of_document(self):
        # When FLAGGED CLAIMS is the last section, the parser still works.
        text = (
            "## VERDICT\npass\n\n"
            "## FLAGGED CLAIMS\n\n"
            "- **Claim 1 — `dated-event` — risk: high**\n"
            '  - claim: "x"\n'
            "  - why_flagged: a\n"
            "  - challenge_query: q\n"
        )
        claims = claim_verification.parse_flagged_claims(text)
        self.assertEqual(len(claims), 1)


# ---------------------------------------------------------------------------
# assemble_claim_verification_evidence
# ---------------------------------------------------------------------------


def _ddg_result(url: str, title: str, snippet: str) -> dict:
    return {"url": url, "title": title, "snippet": snippet}


class AssembleEvidence(unittest.TestCase):
    def test_empty_claim_list(self):
        out = claim_verification.assemble_claim_verification_evidence([])
        self.assertEqual(out["evidence_text"], "")
        self.assertEqual(out["per_claim_evidence"], [])
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_flagged_claims")

    def test_single_claim_happy_path(self):
        claim = {
            "claim_num": 1, "claim_type": "dated-event", "risk_level": "high",
            "claim": "X happened in 1970", "why_flagged": "date check",
            "challenge_query": "when did X happen",
        }
        results = [
            _ddg_result("https://en.wikipedia.org/wiki/X",
                        "X event", "X happened in 1969 according to..."),
        ]
        with mock.patch.object(claim_verification, "web_search_structured",
                                return_value=results):
            out = claim_verification.assemble_claim_verification_evidence(
                [claim],
            )
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertEqual(out["trace"]["claims_total"], 1)
        self.assertEqual(out["trace"]["claims_succeeded"], 1)
        self.assertEqual(out["trace"]["claims_failed"], 0)
        self.assertGreater(out["trace"]["chunks_total"], 0)
        # Evidence text contains the per-claim header and the result URL.
        self.assertIn("Claim 1", out["evidence_text"])
        self.assertIn("when did X happen", out["evidence_text"])
        self.assertIn("en.wikipedia.org", out["evidence_text"])

    def test_multiple_claims_parallel(self):
        # Two claims with different mocked results — both should run, both
        # should appear in evidence_text in claim_num order.
        claims = [
            {"claim_num": 1, "claim_type": "x", "risk_level": "high",
             "claim": "a", "why_flagged": "", "challenge_query": "qa"},
            {"claim_num": 2, "claim_type": "y", "risk_level": "low",
             "claim": "b", "why_flagged": "", "challenge_query": "qb"},
        ]
        call_count = {"n": 0}

        def fake_search(query, max_results=6):
            call_count["n"] += 1
            return [_ddg_result(
                f"https://example.com/{query}",
                f"result for {query}",
                f"snippet {query}",
            )]

        with mock.patch.object(claim_verification, "web_search_structured",
                                side_effect=fake_search):
            out = claim_verification.assemble_claim_verification_evidence(
                claims,
            )
        self.assertEqual(call_count["n"], 2)
        self.assertEqual(out["trace"]["claims_total"], 2)
        # Evidence text is ordered by claim_num.
        evidence = out["evidence_text"]
        self.assertLess(evidence.find("Claim 1"), evidence.find("Claim 2"))

    def test_search_error_isolated_to_failing_claim(self):
        # When one claim's search raises, the other claims still process.
        claims = [
            {"claim_num": 1, "claim_type": "x", "risk_level": "high",
             "claim": "a", "why_flagged": "", "challenge_query": "qa"},
            {"claim_num": 2, "claim_type": "y", "risk_level": "low",
             "claim": "b", "why_flagged": "", "challenge_query": "qb"},
        ]

        def fake_search(query, max_results=6):
            if query == "qa":
                raise RuntimeError("simulated DDG failure")
            return [_ddg_result("https://example.com/y", "ok", "ok body")]

        with mock.patch.object(claim_verification, "web_search_structured",
                                side_effect=fake_search):
            out = claim_verification.assemble_claim_verification_evidence(
                claims,
            )
        self.assertEqual(out["trace"]["claims_total"], 2)
        self.assertEqual(out["trace"]["claims_failed"], 1)
        self.assertEqual(out["trace"]["claims_succeeded"], 1)
        # Evidence text includes both claims — the failed one shows the
        # query-failed marker rather than chunks.
        self.assertIn("Claim 1", out["evidence_text"])
        self.assertIn("query failed", out["evidence_text"])
        self.assertIn("Claim 2", out["evidence_text"])

    def test_empty_results_no_chunks(self):
        claim = {
            "claim_num": 1, "claim_type": "x", "risk_level": "low",
            "claim": "a", "why_flagged": "", "challenge_query": "q",
        }
        with mock.patch.object(claim_verification, "web_search_structured",
                                return_value=[]):
            out = claim_verification.assemble_claim_verification_evidence(
                [claim],
            )
        self.assertEqual(out["trace"]["chunks_total"], 0)
        self.assertEqual(out["trace"]["claims_succeeded"], 1)
        self.assertIn("_no results returned_", out["evidence_text"])


# ---------------------------------------------------------------------------
# _format_evidence_block
# ---------------------------------------------------------------------------


class FormatEvidenceBlock(unittest.TestCase):
    def test_empty_list_returns_empty_string(self):
        self.assertEqual(claim_verification._format_evidence_block([]), "")

    def test_renders_claim_header_and_metadata(self):
        per_claim = [{
            "claim": {
                "claim_num": 1, "claim_type": "dated-event",
                "risk_level": "high", "claim": "X in 1970",
            },
            "query": "when X",
            "chunks": [{
                "url": "https://w/x",
                "document": "**Title**\nbody line",
                "source_tier": "approved",
                "weight": 0.9,
            }],
            "error": None,
        }]
        out = claim_verification._format_evidence_block(per_claim)
        self.assertIn("### Claim 1 — `dated-event` — risk: high", out)
        self.assertIn('**Claim:** "X in 1970"', out)
        self.assertIn('**Challenge query:** "when X"', out)
        self.assertIn("[approved | weight: 0.90 | source: https://w/x]", out)
        self.assertIn("**Title**", out)
        self.assertIn("body line", out)

    def test_renders_error_state(self):
        per_claim = [{
            "claim": {
                "claim_num": 1, "claim_type": "x", "risk_level": "low",
                "claim": "a",
            },
            "query": "q",
            "chunks": [],
            "error": "web_search_failed: timeout",
        }]
        out = claim_verification._format_evidence_block(per_claim)
        self.assertIn("query failed: web_search_failed: timeout", out)

    def test_renders_no_results_state(self):
        per_claim = [{
            "claim": {
                "claim_num": 1, "claim_type": "x", "risk_level": "low",
                "claim": "a",
            },
            "query": "q",
            "chunks": [],
            "error": None,
        }]
        out = claim_verification._format_evidence_block(per_claim)
        self.assertIn("_no results returned_", out)


if __name__ == "__main__":
    unittest.main()
