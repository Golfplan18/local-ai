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


if __name__ == "__main__":
    unittest.main()
