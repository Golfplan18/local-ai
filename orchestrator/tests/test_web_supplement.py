"""Tests for orchestrator/web_supplement.py — the Step 2.5 anticipatory
web-supplement loop.

The loop has two model calls (decision + per-attempt eval) and one
external dependency (web_search.web_search_structured → DDG). All three
are mocked here — no network, no real model. The tests pin the
contract: what shapes the model is expected to emit, how the parser
handles malformed output, how the attempt cascade behaves under each
verdict, and what the assembled output looks like.
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

import web_supplement  # noqa: E402
from tools import web_corroboration  # noqa: E402


FAKE_ENDPOINT = {"name": "anthropic-api-haiku", "type": "api"}


SAMPLE_TRUSTED_SOURCES = """\
# Reference — Trusted Web Sources

## High Provenance

### Generalist

```
en.wikipedia.org/*
plato.stanford.edu/*
```

## Medium Provenance

## Page-Specific Overrides

## Excluded
"""


def _registry_from(tmp_text: str) -> web_corroboration.TrustedSourcesRegistry:
    """Build a TrustedSourcesRegistry pointing at a tmp file with the
    given content. Avoids depending on the live vault file."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tmp_text)
    return web_corroboration.TrustedSourcesRegistry(path=path)


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------


class DecisionParser(unittest.TestCase):
    def test_parses_needs_web_yes_with_gaps(self):
        text = """\
NEEDS_WEB: yes
RATIONALE: the prompt references a specific recent bill
GAPS:
- gap: What does the EARN IT Act of 2025 actually require?
  query: EARN IT Act 2025 requirements
- gap: When was it introduced or passed?
  query: EARN IT Act 2025 timeline
"""
        out = web_supplement._parse_decision(text, max_gaps=3)
        self.assertTrue(out["needs_web"])
        self.assertFalse(out["parse_failed"])
        self.assertEqual(len(out["gaps"]), 2)
        self.assertEqual(out["gaps"][0]["query"],
                         "EARN IT Act 2025 requirements")
        self.assertIn("recent bill", out["rationale"])

    def test_parses_needs_web_no(self):
        text = "NEEDS_WEB: no\nRATIONALE: purely conceptual question"
        out = web_supplement._parse_decision(text, max_gaps=3)
        self.assertFalse(out["needs_web"])
        self.assertEqual(out["gaps"], [])
        self.assertFalse(out["parse_failed"])

    def test_caps_gaps_at_max(self):
        text = "NEEDS_WEB: yes\nRATIONALE: r\nGAPS:\n" + "\n".join(
            f"- gap: g{i}\n  query: q{i}" for i in range(6)
        )
        out = web_supplement._parse_decision(text, max_gaps=3)
        self.assertEqual(len(out["gaps"]), 3)

    def test_parse_failure_degrades_to_no_web(self):
        out = web_supplement._parse_decision("just some prose", max_gaps=3)
        self.assertFalse(out["needs_web"])
        self.assertTrue(out["parse_failed"])

    def test_yes_with_no_gaps_treated_as_no(self):
        out = web_supplement._parse_decision(
            "NEEDS_WEB: yes\nRATIONALE: r", max_gaps=3,
        )
        self.assertFalse(out["needs_web"])
        self.assertTrue(out["parse_failed"])


class EvalParser(unittest.TestCase):
    def test_parses_answered_yes_with_indices(self):
        text = """\
ANSWERED: yes
RELEVANT: 1, 3
RATIONALE: first two results match the gap"""
        out = web_supplement._parse_evaluation(text, num_results=5)
        self.assertTrue(out["answered"])
        self.assertEqual(out["relevant_indices"], [0, 2])
        self.assertFalse(out["parse_failed"])

    def test_parses_answered_no_with_reformulated_query(self):
        text = """\
ANSWERED: no
REFORMULATED_QUERY: privacy bill 2025 site:congress.gov
RATIONALE: results were too generic"""
        out = web_supplement._parse_evaluation(text, num_results=3)
        self.assertFalse(out["answered"])
        self.assertEqual(out["reformulated_query"],
                         "privacy bill 2025 site:congress.gov")

    def test_stop_token_yields_no_reformulated_query(self):
        text = """\
ANSWERED: no
REFORMULATED_QUERY: stop
RATIONALE: domain not on the web"""
        out = web_supplement._parse_evaluation(text, num_results=2)
        self.assertFalse(out["answered"])
        self.assertIsNone(out["reformulated_query"])

    def test_drops_out_of_range_indices(self):
        text = "ANSWERED: yes\nRELEVANT: 1, 99, 2\nRATIONALE: r"
        out = web_supplement._parse_evaluation(text, num_results=3)
        # 1 → 0, 99 → dropped, 2 → 1
        self.assertEqual(out["relevant_indices"], [0, 1])

    def test_parse_failure_degrades_to_not_answered(self):
        out = web_supplement._parse_evaluation("hello", num_results=1)
        self.assertFalse(out["answered"])
        self.assertTrue(out["parse_failed"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SiteFilteredQuery(unittest.TestCase):
    def test_wraps_with_site_clause(self):
        out = web_supplement._site_filtered_query(
            "quantum mechanics", hint_domains=("en.wikipedia.org", "plato.stanford.edu"),
        )
        self.assertIn("quantum mechanics", out)
        self.assertIn("site:en.wikipedia.org", out)
        self.assertIn("OR site:plato.stanford.edu", out)

    def test_empty_hint_domains_returns_unchanged(self):
        out = web_supplement._site_filtered_query("foo", hint_domains=())
        self.assertEqual(out, "foo")


# ---------------------------------------------------------------------------
# End-to-end loop tests
# ---------------------------------------------------------------------------


WIKI_RESULTS = [
    {"title":   "Quantum mechanics — Wikipedia",
     "url":     "https://en.wikipedia.org/wiki/Quantum_mechanics",
     "snippet": "Quantum mechanics is the fundamental theory in physics..."},
    {"title":   "Quantum mechanics — Stanford Encyclopedia of Philosophy",
     "url":     "https://plato.stanford.edu/entries/qm/",
     "snippet": "Quantum mechanics is, at least at first glance..."},
]


class EndToEndLoop(unittest.TestCase):
    def setUp(self):
        self.registry = _registry_from(SAMPLE_TRUSTED_SOURCES)
        self.tmp_paths = [self.registry.path]

    def tearDown(self):
        for p in self.tmp_paths:
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass

    def test_no_fast_endpoint_returns_empty_silently(self):
        out = web_supplement.assemble_web_supplemental_context(
            "anything", call_model=lambda *a, **k: "", fast_endpoint=None,
            trusted_registry=self.registry,
        )
        self.assertEqual(out["text"], "")
        self.assertFalse(out["decision"]["needs_web"])
        self.assertIn("no fast endpoint", out["signals"][0])

    def test_decision_no_skips_search(self):
        call_log = []

        def fake_call(messages, endpoint):
            call_log.append(messages)
            return "NEEDS_WEB: no\nRATIONALE: conceptual question only"

        with mock.patch.object(web_supplement, "web_search_structured") as ws:
            out = web_supplement.assemble_web_supplemental_context(
                "what is consciousness",
                call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
                trusted_registry=self.registry,
            )
        self.assertEqual(out["text"], "")
        self.assertEqual(len(call_log), 1, "only decision pass should fire")
        ws.assert_not_called()
        self.assertFalse(out["decision"]["needs_web"])

    def test_resolved_on_attempt_one_with_site_filter(self):
        # Decision says yes with one gap; eval says answered on attempt 1.
        responses = [
            "NEEDS_WEB: yes\nRATIONALE: needs current physics summary\n"
            "GAPS:\n- gap: define quantum mechanics\n  query: quantum mechanics overview",
            "ANSWERED: yes\nRELEVANT: 1,2\nRATIONALE: both match",
        ]
        resp_iter = iter(responses)

        def fake_call(messages, endpoint):
            return next(resp_iter)

        with mock.patch.object(web_supplement, "web_search_structured",
                               return_value=WIKI_RESULTS) as ws:
            out = web_supplement.assemble_web_supplemental_context(
                "explain quantum mechanics",
                call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
                trusted_registry=self.registry,
            )
        # Site filter on first attempt — verify the search call used it.
        ws.assert_called_once()
        query_arg = ws.call_args.args[0]
        self.assertIn("site:en.wikipedia.org", query_arg)

        self.assertTrue(out["decision"]["needs_web"])
        self.assertEqual(len(out["gaps_processed"]), 1)
        self.assertTrue(out["gaps_processed"][0]["resolved"])
        self.assertEqual(out["gaps_processed"][0]["chunks_retained"], 2)
        # Output text carries provenance markers.
        self.assertIn("classification:", out["text"])
        self.assertIn("weight:", out["text"])
        self.assertIn("Wikipedia", out["text"])

    def test_resolved_on_attempt_two_after_filter_dropped(self):
        responses = [
            "NEEDS_WEB: yes\nRATIONALE: r\n"
            "GAPS:\n- gap: g\n  query: initial query",
            "ANSWERED: no\nREFORMULATED_QUERY: reformulated\nRATIONALE: nothing",
            "ANSWERED: yes\nRELEVANT: 1\nRATIONALE: match",
        ]
        resp_iter = iter(responses)

        def fake_call(messages, endpoint):
            return next(resp_iter)

        searches_seen: list[str] = []

        def fake_search(query, max_results=5):
            searches_seen.append(query)
            # Return empty on attempt 1, results on attempt 2.
            return [] if len(searches_seen) == 1 else WIKI_RESULTS[:1]

        with mock.patch.object(web_supplement, "web_search_structured",
                               side_effect=fake_search):
            out = web_supplement.assemble_web_supplemental_context(
                "user q", call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
                trusted_registry=self.registry, max_attempts_per_gap=2,
            )
        self.assertEqual(len(searches_seen), 2)
        # First search has the site filter; second doesn't.
        self.assertIn("site:en.wikipedia.org", searches_seen[0])
        self.assertNotIn("site:", searches_seen[1])
        self.assertTrue(out["gaps_processed"][0]["resolved"])
        self.assertEqual(len(out["gaps_processed"][0]["attempts"]), 2)

    def test_unresolved_gap_after_attempt_cap(self):
        responses = [
            "NEEDS_WEB: yes\nRATIONALE: r\nGAPS:\n- gap: g\n  query: q",
            "ANSWERED: no\nREFORMULATED_QUERY: q2\nRATIONALE: nope",
            "ANSWERED: no\nREFORMULATED_QUERY: q3\nRATIONALE: still no",
        ]
        resp_iter = iter(responses)

        def fake_call(messages, endpoint):
            return next(resp_iter)

        with mock.patch.object(web_supplement, "web_search_structured",
                               return_value=[]):
            out = web_supplement.assemble_web_supplemental_context(
                "x", call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
                trusted_registry=self.registry, max_attempts_per_gap=2,
            )
        self.assertFalse(out["gaps_processed"][0]["resolved"])
        self.assertEqual(out["text"], "")
        summary = next((s for s in out["signals"]
                        if s.startswith("web_supplement_summary")), "")
        self.assertIn("resolved=0", summary)

    def test_stop_token_terminates_attempts_early(self):
        responses = [
            "NEEDS_WEB: yes\nRATIONALE: r\nGAPS:\n- gap: g\n  query: q",
            "ANSWERED: no\nREFORMULATED_QUERY: stop\nRATIONALE: not searchable",
        ]
        resp_iter = iter(responses)

        def fake_call(messages, endpoint):
            return next(resp_iter)

        with mock.patch.object(web_supplement, "web_search_structured",
                               return_value=[]) as ws:
            out = web_supplement.assemble_web_supplemental_context(
                "x", call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
                trusted_registry=self.registry, max_attempts_per_gap=3,
            )
        # Only one search ran — the model said "stop" after the first eval.
        self.assertEqual(ws.call_count, 1)
        self.assertFalse(out["gaps_processed"][0]["resolved"])
        stop_signal = next((s for s in out["signals"]
                            if s.startswith("web_supplement_gap_stopped_by_model")), "")
        self.assertTrue(stop_signal)

    def test_decision_call_exception_returns_empty(self):
        def fake_call(messages, endpoint):
            raise RuntimeError("haiku unavailable")

        out = web_supplement.assemble_web_supplemental_context(
            "x", call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
            trusted_registry=self.registry,
        )
        self.assertEqual(out["text"], "")
        self.assertTrue(out["decision"]["parse_failed"])
        self.assertIn("decision_call_error", out["signals"][0])

    def test_multiple_gaps_processed_independently(self):
        responses = [
            "NEEDS_WEB: yes\nRATIONALE: two distinct facts\n"
            "GAPS:\n"
            "- gap: g1\n  query: q1\n"
            "- gap: g2\n  query: q2",
            "ANSWERED: yes\nRELEVANT: 1\nRATIONALE: first matches",  # g1 a1
            "ANSWERED: yes\nRELEVANT: 2\nRATIONALE: second matches", # g2 a1
        ]
        resp_iter = iter(responses)

        def fake_call(messages, endpoint):
            return next(resp_iter)

        with mock.patch.object(web_supplement, "web_search_structured",
                               return_value=WIKI_RESULTS):
            out = web_supplement.assemble_web_supplemental_context(
                "x", call_model=fake_call, fast_endpoint=FAKE_ENDPOINT,
                trusted_registry=self.registry,
            )
        self.assertEqual(len(out["gaps_processed"]), 2)
        self.assertTrue(all(g["resolved"] for g in out["gaps_processed"]))
        # Two retained chunks total (one per gap).
        total = sum(g["chunks_retained"] for g in out["gaps_processed"])
        self.assertEqual(total, 2)


if __name__ == "__main__":
    unittest.main()
