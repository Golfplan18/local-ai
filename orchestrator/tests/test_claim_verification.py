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

    def test_overall_budget_exceeded_marks_pending_as_failed(self):
        # Simulate a hung DDG call: web_search_structured sleeps longer
        # than the overall budget (per_query_timeout_seconds * 2). The
        # as_completed loop's timeout argument fires; the pending future
        # gets cancelled and recorded as a budget-exceeded failure
        # rather than hanging the iterator forever.
        import time
        claim = {
            "claim_num": 1, "claim_type": "x", "risk_level": "high",
            "claim": "a", "why_flagged": "", "challenge_query": "q",
        }

        def hung_search(query, max_results=6):
            time.sleep(2.0)  # well beyond the 0.1s * 2 = 0.2s budget
            return []

        with mock.patch.object(claim_verification, "web_search_structured",
                                side_effect=hung_search):
            out = claim_verification.assemble_claim_verification_evidence(
                [claim],
                per_query_timeout_seconds=0.1,
            )
        # Budget fired; the claim is recorded as failed with the
        # overall_budget_exceeded marker.
        self.assertEqual(out["trace"]["claims_failed"], 1)
        self.assertEqual(out["trace"]["claims_succeeded"], 0)
        self.assertEqual(len(out["per_claim_evidence"]), 1)
        self.assertIn("overall_budget_exceeded",
                       out["per_claim_evidence"][0].get("error", ""))
        # And the function returned in roughly the budget time, not
        # the full hung-search duration. Allow generous headroom for
        # CI jitter.
        self.assertLess(out["trace"]["elapsed_seconds"], 1.0)


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


# ---------------------------------------------------------------------------
# extract_revised_draft_section
# ---------------------------------------------------------------------------


class ExtractRevisedDraftSection(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(
            claim_verification.extract_revised_draft_section(""), "",
        )

    def test_missing_section(self):
        text = "## ADDRESSED\nfoo\n\n## CHANGELOG\nbar"
        self.assertEqual(
            claim_verification.extract_revised_draft_section(text), "",
        )

    def test_extracts_body_stops_at_changelog(self):
        text = (
            "## ADDRESSED\nfoo\n\n"
            "## REVISED DRAFT\n\n"
            "This is the revised analysis.\n"
            "It has multiple lines.\n\n"
            "## Some sub-H2 inside the draft\nstill part of the draft\n\n"
            "## CHANGELOG\nchangelog content\n"
        )
        body = claim_verification.extract_revised_draft_section(text)
        self.assertIn("This is the revised analysis", body)
        self.assertIn("Some sub-H2 inside the draft", body)
        self.assertIn("still part of the draft", body)
        self.assertNotIn("changelog content", body)

    def test_extracts_to_eof_when_no_changelog(self):
        text = (
            "## REVISED DRAFT\n\n"
            "draft body without changelog"
        )
        body = claim_verification.extract_revised_draft_section(text)
        self.assertIn("draft body without changelog", body)


# ---------------------------------------------------------------------------
# _parse_extracted_claims (V8 unflagged-claim scan parser)
# ---------------------------------------------------------------------------


class ParseExtractedClaims(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(claim_verification._parse_extracted_claims(""), [])

    def test_none_marker(self):
        self.assertEqual(
            claim_verification._parse_extracted_claims("EXTRACTED:\n(none)"),
            [],
        )

    def test_single_extraction(self):
        text = (
            "EXTRACTED:\n"
            '- claim: "the company has 500 employees"\n'
            "  claim_type: quantitative-figure\n"
            "  risk_level: moderate\n"
            "  challenge_query: ACME Corp employee count 2025"
        )
        out = claim_verification._parse_extracted_claims(text)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["claim_type"], "quantitative-figure")
        self.assertEqual(out[0]["risk_level"], "moderate")
        self.assertIn("500 employees", out[0]["claim"])

    def test_multiple_extractions(self):
        text = (
            "EXTRACTED:\n"
            '- claim: "claim 1"\n'
            "  claim_type: dated-event\n"
            "  risk_level: high\n"
            "  challenge_query: q1\n"
            '- claim: "claim 2"\n'
            "  claim_type: named-entity\n"
            "  risk_level: low\n"
            "  challenge_query: q2"
        )
        out = claim_verification._parse_extracted_claims(text)
        self.assertEqual(len(out), 2)
        self.assertEqual(
            [c["risk_level"] for c in out], ["high", "low"],
        )


# ---------------------------------------------------------------------------
# extract_and_verify_unflagged_claims (V8 scan end-to-end)
# ---------------------------------------------------------------------------


def _make_fast_endpoint():
    return {"name": "test-fast", "type": "api"}


class ExtractAndVerifyUnflagged(unittest.TestCase):
    def test_no_fast_endpoint_skips(self):
        out = claim_verification.extract_and_verify_unflagged_claims(
            revised_draft="some draft",
            flagged_claims=[],
            call_model=lambda m, e: "",
            fast_endpoint=None,
        )
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_fast_endpoint")
        self.assertEqual(out["evidence_text"], "")

    def test_empty_draft_skips(self):
        out = claim_verification.extract_and_verify_unflagged_claims(
            revised_draft="",
            flagged_claims=[],
            call_model=lambda m, e: "EXTRACTED:\n(none)",
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "empty_revised_draft")

    def test_extractor_returns_none(self):
        out = claim_verification.extract_and_verify_unflagged_claims(
            revised_draft="some draft text",
            flagged_claims=[],
            call_model=lambda m, e: "EXTRACTED:\n(none)",
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertEqual(out["trace"]["extracted_count"], 0)
        self.assertEqual(out["evidence_text"], "")

    def test_extractor_call_error(self):
        def failing_call(messages, endpoint):
            raise RuntimeError("extractor down")
        out = claim_verification.extract_and_verify_unflagged_claims(
            revised_draft="some draft text",
            flagged_claims=[],
            call_model=failing_call,
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "errored")
        self.assertIn("extractor down", out["trace"]["reason"])

    def test_full_path_renders_unflagged_label(self):
        extractor_response = (
            "EXTRACTED:\n"
            '- claim: "unflagged claim text"\n'
            "  claim_type: dated-event\n"
            "  risk_level: high\n"
            "  challenge_query: when did X happen"
        )
        results = [_ddg_result("https://example.com/x", "title", "snippet body")]
        with mock.patch.object(claim_verification, "web_search_structured",
                                return_value=results):
            out = claim_verification.extract_and_verify_unflagged_claims(
                revised_draft="The analysis says X happened recently.",
                flagged_claims=[
                    {"claim_num": 1, "claim_type": "named-entity",
                     "claim": "previously-flagged"},
                ],
                call_model=lambda m, e: extractor_response,
                fast_endpoint=_make_fast_endpoint(),
            )
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertEqual(out["trace"]["extracted_count"], 1)
        self.assertGreater(out["trace"]["chunks_total"], 0)
        # Evidence text uses the "Unflagged Claim" label, not "Claim".
        self.assertIn("### Unflagged Claim 1", out["evidence_text"])
        self.assertNotIn("### Claim 1", out["evidence_text"])


# ---------------------------------------------------------------------------
# _format_evidence_block label_prefix parameter
# ---------------------------------------------------------------------------


class FormatEvidenceBlockLabelPrefix(unittest.TestCase):
    def test_default_label_is_claim(self):
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
        self.assertIn("### Claim 1", out)
        self.assertNotIn("### Unflagged", out)

    def test_custom_label_prefix(self):
        per_claim = [{
            "claim": {
                "claim_num": 1, "claim_type": "x", "risk_level": "low",
                "claim": "a",
            },
            "query": "q",
            "chunks": [],
            "error": None,
        }]
        out = claim_verification._format_evidence_block(
            per_claim, label_prefix="Unflagged Claim",
        )
        self.assertIn("### Unflagged Claim 1", out)


if __name__ == "__main__":
    unittest.main()
