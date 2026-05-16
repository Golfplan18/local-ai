"""Tests for orchestrator/tools/web_search.py — both web_search (markdown
return) and web_search_structured (list-of-dicts return).

These tests don't hit the live DDG service — that would be flaky in CI
and slow in dev. ``_ddgs_text`` is monkey-patched to return controlled
fixtures so the wrapper logic is the unit under test.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

from tools import web_search  # noqa: E402


# Fixtures — what DDG returns in the two library-version shapes we've seen.

DDGS_HREF_BODY_SHAPE = [
    {"title": "Quantum mechanics — Wikipedia",
     "href":  "https://en.wikipedia.org/wiki/Quantum_mechanics",
     "body":  "Quantum mechanics is the fundamental theory in physics..."},
    {"title": "Stanford Encyclopedia of Philosophy: Quantum Mechanics",
     "href":  "https://plato.stanford.edu/entries/qm/",
     "body":  "Quantum mechanics is, at least at first glance..."},
]

DDGS_URL_SNIPPET_SHAPE = [
    {"title":   "GDP — World Bank Open Data",
     "url":     "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
     "snippet": "GDP at purchaser's prices is the sum of gross value..."},
]


class WebSearchStructured(unittest.TestCase):
    def test_returns_list_of_dicts_with_normalised_keys(self):
        with mock.patch.object(web_search, "_ddgs_text",
                               return_value=DDGS_HREF_BODY_SHAPE):
            out = web_search.web_search_structured("quantum mechanics")
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 2)
        self.assertEqual(set(out[0].keys()), {"title", "url", "snippet"})
        self.assertEqual(out[0]["url"],
                         "https://en.wikipedia.org/wiki/Quantum_mechanics")
        self.assertIn("Quantum mechanics", out[0]["snippet"])

    def test_handles_url_snippet_key_variant(self):
        # Newer/older DDG library versions use different result keys.
        with mock.patch.object(web_search, "_ddgs_text",
                               return_value=DDGS_URL_SNIPPET_SHAPE):
            out = web_search.web_search_structured("gdp")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"],
                         "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD")
        self.assertTrue(out[0]["snippet"].startswith("GDP at purchaser"))

    def test_empty_results_returns_empty_list(self):
        with mock.patch.object(web_search, "_ddgs_text", return_value=[]):
            out = web_search.web_search_structured("no-hits-query")
        self.assertEqual(out, [])

    def test_ddg_exception_returns_empty_list_and_logs_to_stderr(self):
        captured = io.StringIO()
        with mock.patch.object(web_search, "_ddgs_text",
                               side_effect=RuntimeError("rate limited")), \
             mock.patch.object(sys, "stderr", captured):
            out = web_search.web_search_structured("any query")
        self.assertEqual(out, [])
        msg = captured.getvalue()
        self.assertIn("web_search_structured", msg)
        self.assertIn("rate limited", msg)

    def test_skips_results_with_no_url(self):
        broken = [
            {"title": "Has URL",     "href": "https://example.com/", "body": "yes"},
            {"title": "Missing URL", "href": "",                     "body": "no"},
            {"title": "No URL key",                                  "body": "also no"},
        ]
        with mock.patch.object(web_search, "_ddgs_text", return_value=broken):
            out = web_search.web_search_structured("q")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "https://example.com/")

    def test_max_results_threaded_to_ddg(self):
        captured_kwargs = {}

        def fake(query, max_results):
            captured_kwargs["query"] = query
            captured_kwargs["max_results"] = max_results
            return []

        with mock.patch.object(web_search, "_ddgs_text", side_effect=fake):
            web_search.web_search_structured("test query", max_results=12)
        self.assertEqual(captured_kwargs["query"], "test query")
        self.assertEqual(captured_kwargs["max_results"], 12)


class WebSearchMarkdownStillWorks(unittest.TestCase):
    """The original tool-surface function must continue to behave the
    same way after the refactor (markdown numbered list, error string
    on failure, "no results" sentinel on empty)."""

    def test_markdown_output_shape(self):
        with mock.patch.object(web_search, "_ddgs_text",
                               return_value=DDGS_HREF_BODY_SHAPE):
            text = web_search.web_search("quantum mechanics")
        self.assertIn("1. Quantum mechanics — Wikipedia", text)
        self.assertIn("URL: https://en.wikipedia.org/wiki/Quantum_mechanics", text)
        self.assertIn("2. Stanford Encyclopedia of Philosophy", text)

    def test_markdown_no_results_sentinel(self):
        with mock.patch.object(web_search, "_ddgs_text", return_value=[]):
            text = web_search.web_search("no-hits-query")
        self.assertEqual(text, "No results found for: no-hits-query")

    def test_markdown_returns_error_string_on_exception(self):
        with mock.patch.object(web_search, "_ddgs_text",
                               side_effect=RuntimeError("rate limited")):
            text = web_search.web_search("any")
        self.assertTrue(text.startswith("Search error:"))
        self.assertIn("rate limited", text)


if __name__ == "__main__":
    unittest.main()
