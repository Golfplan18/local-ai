"""Tests for orchestrator/web_consultation.py — F-Consult's CAG web stream.

Coverage:
  - _parse_intents: empty/malformed input, single/multiple intents,
    intent without justification gets dropped.
  - _parse_sanity_flags: empty/malformed input, multiple flags.
  - _execute_intent_query: happy path with mocked DDG, empty results,
    DDG raising an exception.
  - assemble_consultation_package: end-to-end with mocked call_model +
    web_search_structured; no_fast_endpoint short-circuit; intent parse
    failure path; zero intents emitted (pure-conceptual prompt);
    prompt-sanity check disabled.
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

import web_consultation  # noqa: E402


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


class ParseIntents(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(web_consultation._parse_intents(""), [])

    def test_none_marker(self):
        self.assertEqual(
            web_consultation._parse_intents("INTENTS:\n(none)"),
            [],
        )

    def test_single_intent(self):
        text = (
            "INTENTS:\n"
            "- query: moon landing year\n"
            "  justification: dated event central to the analysis"
        )
        intents = web_consultation._parse_intents(text)
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["query"], "moon landing year")
        self.assertIn("dated event", intents[0]["justification"])

    def test_multiple_intents(self):
        text = (
            "INTENTS:\n"
            "- query: q1\n"
            "  justification: j1\n"
            "- query: q2\n"
            "  justification: j2\n"
            "- query: q3\n"
            "  justification: j3"
        )
        intents = web_consultation._parse_intents(text)
        self.assertEqual(len(intents), 3)
        self.assertEqual(
            [i["query"] for i in intents],
            ["q1", "q2", "q3"],
        )

    def test_intent_without_justification_is_dropped(self):
        # The regex requires both fields — an intent missing the
        # justification line cannot match and is silently dropped, which
        # is the anti-nitpicking discipline F-Consult specifies.
        text = (
            "INTENTS:\n"
            "- query: legitimate\n"
            "  justification: real reason\n"
            "- query: nitpick\n"
            "(no justification line)"
        )
        intents = web_consultation._parse_intents(text)
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["query"], "legitimate")

    def test_strips_surrounding_quotes(self):
        text = (
            "INTENTS:\n"
            '- query: "quoted query"\n'
            "  justification: reason"
        )
        intents = web_consultation._parse_intents(text)
        self.assertEqual(intents[0]["query"], "quoted query")


class ParseSanityFlags(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(web_consultation._parse_sanity_flags(""), [])

    def test_none_marker(self):
        self.assertEqual(
            web_consultation._parse_sanity_flags("FLAGS:\n(none)"),
            [],
        )

    def test_single_flag(self):
        text = (
            "FLAGS:\n"
            '- claim: "the moon landing was in 1970"\n'
            "  suspected_error: actual year was 1969\n"
            "  reasoning: Apollo 11 landed July 20 1969"
        )
        flags = web_consultation._parse_sanity_flags(text)
        self.assertEqual(len(flags), 1)
        self.assertIn("moon landing", flags[0]["claim"])
        self.assertIn("1969", flags[0]["suspected_error"])

    def test_multiple_flags(self):
        text = (
            "FLAGS:\n"
            '- claim: "first claim"\n'
            "  suspected_error: e1\n"
            "  reasoning: r1\n"
            '- claim: "second claim"\n'
            "  suspected_error: e2\n"
            "  reasoning: r2"
        )
        flags = web_consultation._parse_sanity_flags(text)
        self.assertEqual(len(flags), 2)


# ---------------------------------------------------------------------------
# Per-intent query execution
# ---------------------------------------------------------------------------


def _ddg_result(url, title, snippet):
    return {"url": url, "title": title, "snippet": snippet}


class ExecuteIntentQuery(unittest.TestCase):
    def setUp(self):
        from tools import web_corroboration
        self.registry = web_corroboration.TrustedSourcesRegistry()

    def test_happy_path(self):
        intent = {"query": "test query", "justification": "test"}
        results = [
            _ddg_result("https://en.wikipedia.org/wiki/x", "title", "snippet"),
        ]
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=results):
            out = web_consultation._execute_intent_query(
                intent, max_results=6, timeout_seconds=15,
                registry=self.registry,
            )
        self.assertIsNone(out["error"])
        self.assertEqual(out["query"], "test query")
        self.assertGreater(len(out["chunks"]), 0)

    def test_empty_results(self):
        intent = {"query": "test", "justification": "reason"}
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=[]):
            out = web_consultation._execute_intent_query(
                intent, max_results=6, timeout_seconds=15,
                registry=self.registry,
            )
        self.assertIsNone(out["error"])
        self.assertEqual(out["chunks"], [])

    def test_search_exception(self):
        intent = {"query": "test", "justification": "reason"}
        with mock.patch.object(web_consultation, "web_search_structured",
                                side_effect=RuntimeError("DDG down")):
            out = web_consultation._execute_intent_query(
                intent, max_results=6, timeout_seconds=15,
                registry=self.registry,
            )
        self.assertIsNotNone(out["error"])
        self.assertIn("DDG down", out["error"])
        self.assertEqual(out["chunks"], [])


# ---------------------------------------------------------------------------
# Public entry point — assemble_consultation_package
# ---------------------------------------------------------------------------


def _make_fast_endpoint():
    return {"name": "test-endpoint", "type": "api"}


def _make_call_model(intent_response="", sanity_response=""):
    """Build a call_model mock that returns different responses based on
    which system prompt is being sent (intent identification vs sanity
    check)."""
    def call_model(messages, endpoint):
        system = messages[0]["content"] if messages else ""
        if "factual-sanity check" in system or "sanity check" in system.lower():
            return sanity_response
        return intent_response
    return call_model


class AssembleConsultationPackage(unittest.TestCase):
    def test_no_fast_endpoint_short_circuits(self):
        out = web_consultation.assemble_consultation_package(
            user_prompt="hello",
            call_model=_make_call_model(),
            fast_endpoint=None,
        )
        self.assertEqual(out["web_rag"], "")
        self.assertEqual(out["prompt_sanity_flags"], [])
        self.assertEqual(out["consultation_trace"]["status"], "skipped")
        self.assertEqual(
            out["consultation_trace"]["reason"], "no_fast_endpoint",
        )

    def test_zero_intents_emitted(self):
        # Pure-conceptual prompt — intent identifier returns (none).
        out = web_consultation.assemble_consultation_package(
            user_prompt="what is the meaning of life?",
            call_model=_make_call_model(
                intent_response="INTENTS:\n(none)",
                sanity_response="FLAGS:\n(none)",
            ),
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["web_rag"], "")
        self.assertEqual(out["consultation_trace"]["intents_identified"], 0)
        # Status is "ran" (we did consult, no intents was the answer) or
        # "skipped" with no_intents_emitted reason if sanity disabled —
        # either is acceptable; assert the field is present.
        self.assertIn(out["consultation_trace"]["status"], {"ran", "skipped"})

    def test_intent_call_error_returns_errored(self):
        def call_model(messages, endpoint):
            raise RuntimeError("model failed")
        out = web_consultation.assemble_consultation_package(
            user_prompt="x",
            call_model=call_model,
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["consultation_trace"]["status"], "errored")
        self.assertIn("model failed", out["consultation_trace"]["reason"])

    def test_happy_path_with_intents(self):
        intent_response = (
            "INTENTS:\n"
            "- query: test query 1\n"
            "  justification: load-bearing factual angle"
        )
        sanity_response = "FLAGS:\n(none)"
        results = [_ddg_result("https://en.wikipedia.org/x", "T", "snippet")]
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=results):
            out = web_consultation.assemble_consultation_package(
                user_prompt="when did event X happen?",
                call_model=_make_call_model(intent_response, sanity_response),
                fast_endpoint=_make_fast_endpoint(),
            )
        self.assertEqual(out["consultation_trace"]["status"], "ran")
        self.assertEqual(out["consultation_trace"]["intents_identified"], 1)
        self.assertEqual(out["consultation_trace"]["intents_executed"], 1)
        self.assertGreater(out["consultation_trace"]["chunks_total"], 0)
        # web_rag carries the formatted chunks.
        self.assertIn("snippet", out["web_rag"])

    def test_sanity_check_disabled(self):
        intent_response = (
            "INTENTS:\n"
            "- query: q\n"
            "  justification: j"
        )
        results = [_ddg_result("https://x/y", "t", "s")]
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=results):
            out = web_consultation.assemble_consultation_package(
                user_prompt="x",
                call_model=_make_call_model(intent_response, "should not be called"),
                fast_endpoint=_make_fast_endpoint(),
                prompt_sanity_enabled=False,
            )
        self.assertEqual(out["prompt_sanity_flags"], [])
        # Should still process the intent.
        self.assertEqual(out["consultation_trace"]["intents_executed"], 1)

    def test_sanity_flag_surfaces_in_output(self):
        intent_response = "INTENTS:\n(none)"
        sanity_response = (
            "FLAGS:\n"
            '- claim: "moon landing in 1970"\n'
            "  suspected_error: was 1969\n"
            "  reasoning: Apollo 11 was July 1969"
        )
        out = web_consultation.assemble_consultation_package(
            user_prompt="discuss the 1970 moon landing",
            call_model=_make_call_model(intent_response, sanity_response),
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(len(out["prompt_sanity_flags"]), 1)
        self.assertIn("moon landing", out["prompt_sanity_flags"][0]["claim"])


# ---------------------------------------------------------------------------
# _parse_conflict_blocks
# ---------------------------------------------------------------------------


class ParseConflictBlocks(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(web_consultation._parse_conflict_blocks(""), [])

    def test_none_marker(self):
        self.assertEqual(
            web_consultation._parse_conflict_blocks("CONFLICTS:\n(none)"),
            [],
        )

    def test_single_conflict(self):
        text = (
            "CONFLICTS:\n"
            "- web_chunk_index: 2\n"
            '  vault_reference: "Engram says X happened in 1990"\n'
            "  contradiction: Web result places it in 1991"
        )
        out = web_consultation._parse_conflict_blocks(text)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["web_chunk_index"], 2)
        self.assertIn("1990", out[0]["vault_reference"])
        self.assertIn("1991", out[0]["contradiction"])

    def test_multiple_conflicts(self):
        text = (
            "CONFLICTS:\n"
            "- web_chunk_index: 0\n"
            "  vault_reference: ref0\n"
            "  contradiction: c0\n"
            "- web_chunk_index: 7\n"
            "  vault_reference: ref7\n"
            "  contradiction: c7"
        )
        out = web_consultation._parse_conflict_blocks(text)
        self.assertEqual(len(out), 2)
        self.assertEqual([c["web_chunk_index"] for c in out], [0, 7])


# ---------------------------------------------------------------------------
# _format_web_consultation_body (intent_justification + conflict surfacing)
# ---------------------------------------------------------------------------


class FormatWebConsultationBody(unittest.TestCase):
    def test_empty_chunks_returns_empty(self):
        self.assertEqual(web_consultation._format_web_consultation_body([]), "")

    def test_renders_classification_weight_source(self):
        chunks = [{
            "classification": "whitelisted",
            "weight": 0.95,
            "url": "https://en.wikipedia.org/wiki/X",
            "document": "Body content here.",
        }]
        out = web_consultation._format_web_consultation_body(chunks)
        self.assertIn("[classification: whitelisted | weight: 0.95 | source: https://en.wikipedia.org/wiki/X]", out)
        self.assertIn("Body content here.", out)

    def test_intent_justification_appears_when_present(self):
        chunks = [{
            "classification": "corroborated",
            "weight": 0.4,
            "url": "https://x/y",
            "document": "Body",
            "intent_justification": "anchors the unemployment-rate claim",
        }]
        out = web_consultation._format_web_consultation_body(chunks)
        self.assertIn("[intent: anchors the unemployment-rate claim]", out)

    def test_intent_justification_omitted_when_absent(self):
        chunks = [{
            "classification": "single",
            "weight": 0.15,
            "url": "https://x/y",
            "document": "Body",
        }]
        out = web_consultation._format_web_consultation_body(chunks)
        self.assertNotIn("[intent:", out)

    def test_conflict_marker_appears_when_flagged(self):
        chunks = [{
            "classification": "corroborated",
            "weight": 0.3,
            "url": "https://x/y",
            "document": "Body",
            "consultation_conflict": True,
            "conflicts_with": "Engram (Q2 2020) — vault says 13.0%, web says 13.3%",
        }]
        out = web_consultation._format_web_consultation_body(chunks)
        self.assertIn("[CONFLICT: Engram (Q2 2020) — vault says 13.0%, web says 13.3%]", out)

    def test_conflict_marker_omitted_when_not_flagged(self):
        chunks = [{
            "classification": "corroborated",
            "weight": 0.3,
            "url": "https://x/y",
            "document": "Body",
            "consultation_conflict": False,
        }]
        out = web_consultation._format_web_consultation_body(chunks)
        self.assertNotIn("[CONFLICT:", out)

    def test_max_chars_truncates(self):
        chunks = [
            {"classification": "single", "weight": 0.15,
             "url": "https://x/1", "document": "A" * 5000},
            {"classification": "single", "weight": 0.15,
             "url": "https://x/2", "document": "B" * 5000},
            {"classification": "single", "weight": 0.15,
             "url": "https://x/3", "document": "C" * 5000},
        ]
        out = web_consultation._format_web_consultation_body(chunks, max_chars=6000)
        # First chunk always renders; later chunks stop when budget exceeded.
        self.assertIn("https://x/1", out)
        # The third chunk should not appear given the budget.
        self.assertNotIn("https://x/3", out)


# ---------------------------------------------------------------------------
# _detect_conflicts_against_vault
# ---------------------------------------------------------------------------


class DetectConflictsAgainstVault(unittest.TestCase):
    def test_no_web_chunks_skips(self):
        out = web_consultation._detect_conflicts_against_vault(
            [], "vault content here",
            call_model=lambda m, e: "CONFLICTS:\n(none)",
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_web_chunks")
        self.assertEqual(out["conflicts_count"], 0)

    def test_no_vault_skips(self):
        out = web_consultation._detect_conflicts_against_vault(
            [{"url": "x", "document": "y"}], "",
            call_model=lambda m, e: "CONFLICTS:\n(none)",
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_vault_context")

    def test_no_endpoint_skips(self):
        out = web_consultation._detect_conflicts_against_vault(
            [{"url": "x", "document": "y"}], "vault content",
            call_model=lambda m, e: "CONFLICTS:\n(none)",
            fast_endpoint=None,
        )
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_fast_endpoint")

    def test_detector_error_fail_soft(self):
        def failing(messages, endpoint):
            raise RuntimeError("model down")
        out = web_consultation._detect_conflicts_against_vault(
            [{"url": "x", "document": "y"}], "vault content",
            call_model=failing,
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "errored")
        self.assertIn("model down", out["trace"]["reason"])
        # Chunks unchanged.
        self.assertNotIn("consultation_conflict", out["annotated_chunks"][0])

    def test_none_response_no_annotations(self):
        out = web_consultation._detect_conflicts_against_vault(
            [{"url": "x", "document": "y"}], "vault content",
            call_model=lambda m, e: "CONFLICTS:\n(none)",
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertEqual(out["conflicts_count"], 0)
        # Chunks unchanged.
        self.assertNotIn("consultation_conflict", out["annotated_chunks"][0])

    def test_detected_conflict_annotates_chunk(self):
        response = (
            "CONFLICTS:\n"
            "- web_chunk_index: 1\n"
            "  vault_reference: vault says 1990\n"
            "  contradiction: web places it in 1991"
        )
        chunks = [
            {"url": "https://a", "document": "doc a"},
            {"url": "https://b", "document": "doc b says 1991"},
            {"url": "https://c", "document": "doc c"},
        ]
        out = web_consultation._detect_conflicts_against_vault(
            chunks, "vault content with 1990",
            call_model=lambda m, e: response,
            fast_endpoint=_make_fast_endpoint(),
        )
        self.assertEqual(out["conflicts_count"], 1)
        # Only index 1 annotated.
        self.assertNotIn("consultation_conflict", out["annotated_chunks"][0])
        self.assertTrue(out["annotated_chunks"][1].get("consultation_conflict"))
        self.assertIn("1990", out["annotated_chunks"][1]["conflicts_with"])
        self.assertIn("1991", out["annotated_chunks"][1]["conflicts_with"])
        self.assertNotIn("consultation_conflict", out["annotated_chunks"][2])

    def test_invalid_chunk_index_silently_skipped(self):
        # Detector returns an out-of-range index — code skips it without
        # crashing.
        response = (
            "CONFLICTS:\n"
            "- web_chunk_index: 99\n"
            "  vault_reference: ref\n"
            "  contradiction: c"
        )
        chunks = [{"url": "https://a", "document": "doc"}]
        out = web_consultation._detect_conflicts_against_vault(
            chunks, "vault",
            call_model=lambda m, e: response,
            fast_endpoint=_make_fast_endpoint(),
        )
        # parsed 1 conflict, but no chunk was actually annotated
        self.assertEqual(out["conflicts_count"], 1)
        self.assertNotIn("consultation_conflict", out["annotated_chunks"][0])


# ---------------------------------------------------------------------------
# assemble_consultation_package — vault_rag_context wiring
# ---------------------------------------------------------------------------


class ConsultationPackageWithVaultContext(unittest.TestCase):
    def test_conflict_detection_runs_when_vault_present(self):
        # Intent → 1 web chunk → conflict detector flags it.
        intent_response = (
            "INTENTS:\n"
            "- query: q\n"
            "  justification: j"
        )
        conflict_response = (
            "CONFLICTS:\n"
            "- web_chunk_index: 0\n"
            "  vault_reference: vault says X\n"
            "  contradiction: web says Y"
        )
        sanity_response = "FLAGS:\n(none)"

        def call_model(messages, endpoint):
            sys = messages[0]["content"]
            if "conflict" in sys.lower() and "factual" in sys.lower():
                return conflict_response
            if "sanity" in sys.lower() or "factual-sanity" in sys.lower():
                return sanity_response
            return intent_response

        results = [_ddg_result("https://x", "T", "snippet")]
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=results):
            out = web_consultation.assemble_consultation_package(
                user_prompt="discuss X",
                call_model=call_model,
                fast_endpoint=_make_fast_endpoint(),
                vault_rag_context="some vault content",
            )
        self.assertEqual(out["consultation_trace"]["conflicts_count"], 1)
        # web_rag carries the [CONFLICT: ...] marker because the chunk
        # was annotated.
        self.assertIn("[CONFLICT:", out["web_rag"])

    def test_conflict_detection_skips_when_vault_empty(self):
        intent_response = "INTENTS:\n- query: q\n  justification: j"
        results = [_ddg_result("https://x", "T", "snippet")]
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=results):
            out = web_consultation.assemble_consultation_package(
                user_prompt="x",
                call_model=_make_call_model(intent_response, "FLAGS:\n(none)"),
                fast_endpoint=_make_fast_endpoint(),
                vault_rag_context="",  # empty
            )
        self.assertEqual(out["consultation_trace"]["conflicts_count"], 0)
        self.assertEqual(
            out["consultation_trace"]["conflict_detection"]["status"],
            "skipped",
        )

    def test_conflict_detection_disabled_via_flag(self):
        intent_response = "INTENTS:\n- query: q\n  justification: j"
        results = [_ddg_result("https://x", "T", "snippet")]
        with mock.patch.object(web_consultation, "web_search_structured",
                                return_value=results):
            out = web_consultation.assemble_consultation_package(
                user_prompt="x",
                call_model=_make_call_model(intent_response, "FLAGS:\n(none)"),
                fast_endpoint=_make_fast_endpoint(),
                vault_rag_context="vault content",
                conflict_detection_enabled=False,
            )
        self.assertEqual(out["consultation_trace"]["conflicts_count"], 0)
        # Conflict detection branch never executed.
        self.assertEqual(
            out["consultation_trace"]["conflict_detection"]["status"],
            "skipped",
        )


if __name__ == "__main__":
    unittest.main()
