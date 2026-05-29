"""Tests for the three-tier cascade in ``orchestrator/tools/web_search.py``.

Default suite is offline:
  - cascade respects configured order
  - providers without a key are skipped silently
  - exception in one tier falls through to next
  - all-fail returns ([], "none")
  - cascade order loads from routing-config.json
  - unknown providers in the config are dropped

No live network calls — neither Tavily nor Brave keys are guaranteed
to be configured on a dev machine.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.join(_HERE, "..", "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import web_search as ws  # noqa: E402


def _isolate_keys(**env):
    """Patch all keyed provider envs at once. Empty string ⇒ absent."""
    base = {"TAVILY_API_KEY": "", "BRAVE_API_KEY": "", "EXA_API_KEY": ""}
    base.update(env)
    return mock.patch.dict(os.environ, base, clear=False)


class CascadeOrderTests(unittest.TestCase):
    """Cascade walks providers in the configured order."""

    def setUp(self):
        ws._reset_cascade_order_cache()

    def tearDown(self):
        ws._reset_cascade_order_cache()

    def test_default_order_is_tavily_brave_ddg(self):
        with mock.patch.object(
            ws, "_ROUTING_CONFIG_PATH", "/nonexistent/path.json"
        ):
            self.assertEqual(
                ws._load_cascade_order(),
                ("tavily", "brave", "ddg"),
            )

    def test_custom_order_from_routing_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"search_cascade_order": ["brave", "ddg"]}, f)
            path = f.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path):
                self.assertEqual(
                    ws._load_cascade_order(),
                    ("brave", "ddg"),
                )
        finally:
            os.unlink(path)

    def test_unknown_provider_dropped(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {"search_cascade_order": ["tavily", "kagi", "ddg"]}, f,
            )
            path = f.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path):
                self.assertEqual(
                    ws._load_cascade_order(),
                    ("tavily", "ddg"),
                )
        finally:
            os.unlink(path)

    def test_exa_recognized_in_custom_order(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {"search_cascade_order": ["exa", "tavily", "ddg"]}, f,
            )
            path = f.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path):
                self.assertEqual(
                    ws._load_cascade_order(),
                    ("exa", "tavily", "ddg"),
                )
        finally:
            os.unlink(path)

    def test_malformed_config_falls_back_to_default(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{ this is not json")
            path = f.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path):
                self.assertEqual(
                    ws._load_cascade_order(),
                    ("tavily", "brave", "ddg"),
                )
        finally:
            os.unlink(path)


class SearchTextCascadeTests(unittest.TestCase):
    """_search_text walks the cascade and stops at first success."""

    def setUp(self):
        ws._reset_cascade_order_cache()
        self._patches = [
            mock.patch.object(ws, "_PROVIDERS", {
                "tavily": ("TAVILY_API_KEY", mock.MagicMock(
                    name="tavily_fetcher")),
                "brave":  ("BRAVE_API_KEY",  mock.MagicMock(
                    name="brave_fetcher")),
                "exa":    ("EXA_API_KEY",    mock.MagicMock(
                    name="exa_fetcher")),
                "ddg":    (None,             mock.MagicMock(
                    name="ddg_fetcher")),
            }),
            mock.patch.object(
                ws, "_load_cascade_order",
                return_value=("tavily", "brave", "ddg"),
            ),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        ws._reset_cascade_order_cache()

    def _set_fetcher(self, name, result=None, raises=None):
        env_var, fetcher = ws._PROVIDERS[name]
        if raises is not None:
            fetcher.side_effect = raises
        else:
            fetcher.return_value = result

    def test_tavily_wins_when_key_present_and_succeeds(self):
        self._set_fetcher("tavily", result=[{"title": "t"}])
        self._set_fetcher("brave",  result=[{"title": "b"}])
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(provider, "tavily")
        self.assertEqual(results, [{"title": "t"}])
        ws._PROVIDERS["brave"][1].assert_not_called()
        ws._PROVIDERS["ddg"][1].assert_not_called()

    def test_tavily_skipped_when_key_absent(self):
        self._set_fetcher("brave", result=[{"title": "b"}])
        with _isolate_keys(BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(provider, "brave")
        ws._PROVIDERS["tavily"][1].assert_not_called()
        ws._PROVIDERS["ddg"][1].assert_not_called()

    def test_tavily_error_cascades_to_brave(self):
        self._set_fetcher("tavily", raises=RuntimeError("upstream timeout"))
        self._set_fetcher("brave",  result=[{"title": "b"}])
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(provider, "brave")
        ws._PROVIDERS["tavily"][1].assert_called_once()
        ws._PROVIDERS["brave"][1].assert_called_once()

    def test_double_error_cascades_to_ddg(self):
        self._set_fetcher("tavily", raises=RuntimeError("upstream"))
        self._set_fetcher("brave",  raises=RuntimeError("upstream"))
        self._set_fetcher("ddg",    result=[{"title": "d"}])
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(provider, "ddg")

    def test_all_fail_returns_empty_and_none(self):
        self._set_fetcher("tavily", raises=RuntimeError("a"))
        self._set_fetcher("brave",  raises=RuntimeError("b"))
        self._set_fetcher("ddg",    raises=RuntimeError("c"))
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(results, [])
        self.assertEqual(provider, "none")

    def test_empty_results_not_treated_as_failure(self):
        """Provider returning [] is a real 'no results' answer — cascade stops."""
        self._set_fetcher("tavily", result=[])
        self._set_fetcher("brave",  result=[{"title": "should-not-appear"}])
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(provider, "tavily")
        self.assertEqual(results, [])
        ws._PROVIDERS["brave"][1].assert_not_called()

    def test_exa_first_when_listed_and_key_present(self):
        with mock.patch.object(
            ws, "_load_cascade_order",
            return_value=("exa", "tavily", "ddg"),
        ):
            self._set_fetcher("exa",    result=[{"title": "e"}])
            self._set_fetcher("tavily", result=[{"title": "t"}])
            with _isolate_keys(EXA_API_KEY="key", TAVILY_API_KEY="key"):
                results, provider = ws._search_text("q", 5)
            self.assertEqual(provider, "exa")
            self.assertEqual(results, [{"title": "e"}])
            ws._PROVIDERS["tavily"][1].assert_not_called()

    def test_exa_skipped_when_key_absent(self):
        with mock.patch.object(
            ws, "_load_cascade_order",
            return_value=("exa", "tavily", "ddg"),
        ):
            self._set_fetcher("tavily", result=[{"title": "t"}])
            with _isolate_keys(TAVILY_API_KEY="key"):
                results, provider = ws._search_text("q", 5)
            self.assertEqual(provider, "tavily")
            ws._PROVIDERS["exa"][1].assert_not_called()

    def test_exa_error_cascades_to_next_tier(self):
        with mock.patch.object(
            ws, "_load_cascade_order",
            return_value=("exa", "ddg"),
        ):
            self._set_fetcher("exa", raises=RuntimeError("upstream"))
            self._set_fetcher("ddg", result=[{"title": "d"}])
            with _isolate_keys(EXA_API_KEY="key"):
                results, provider = ws._search_text("q", 5)
            self.assertEqual(provider, "ddg")
            ws._PROVIDERS["exa"][1].assert_called_once()

    def test_custom_order_brave_first(self):
        with mock.patch.object(
            ws, "_load_cascade_order",
            return_value=("brave", "tavily", "ddg"),
        ):
            self._set_fetcher("brave",  result=[{"title": "b"}])
            self._set_fetcher("tavily", result=[{"title": "t"}])
            with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
                results, provider = ws._search_text("q", 5)
            self.assertEqual(provider, "brave")


class StructuredEntryPointTests(unittest.TestCase):
    """web_search_structured normalises across provider shapes."""

    def test_normalises_brave_dicts(self):
        # Brave fetcher returns DDG-shape (title/href/body).
        with mock.patch.object(
            ws, "_search_text",
            return_value=([
                {"title": "Brave Result", "href": "https://e.com",
                 "body": "snippet"}
            ], "brave"),
        ):
            out = ws.web_search_structured("q", 5)
        self.assertEqual(out, [{
            "title":   "Brave Result",
            "url":     "https://e.com",
            "snippet": "snippet",
        }])

    def test_handles_legacy_url_snippet_keys(self):
        with mock.patch.object(
            ws, "_search_text",
            return_value=([
                {"title": "Legacy", "url": "https://e.com",
                 "snippet": "old-shape"}
            ], "ddg"),
        ):
            out = ws.web_search_structured("q", 5)
        self.assertEqual(out, [{
            "title":   "Legacy",
            "url":     "https://e.com",
            "snippet": "old-shape",
        }])

    def test_dropped_when_no_url(self):
        with mock.patch.object(
            ws, "_search_text",
            return_value=([
                {"title": "No url here", "href": "", "body": "x"}
            ], "ddg"),
        ):
            out = ws.web_search_structured("q", 5)
        self.assertEqual(out, [])

    def test_cascade_failure_returns_empty(self):
        with mock.patch.object(
            ws, "_search_text", return_value=([], "none"),
        ):
            self.assertEqual(ws.web_search_structured("q", 5), [])


class WebSearchMarkdownTests(unittest.TestCase):
    """web_search returns formatted markdown or a graceful no-result string."""

    def test_returns_formatted_lines(self):
        with mock.patch.object(
            ws, "_search_text",
            return_value=([
                {"title": "Result 1", "href": "https://e.com",
                 "body": "first hit"}
            ], "brave"),
        ):
            out = ws.web_search("q", 5)
        self.assertIn("1. Result 1", out)
        self.assertIn("https://e.com", out)
        self.assertIn("first hit", out)

    def test_no_results_string(self):
        with mock.patch.object(
            ws, "_search_text", return_value=([], "none"),
        ):
            self.assertEqual(
                ws.web_search("anything", 5),
                "No results found for: anything",
            )


if __name__ == "__main__":
    unittest.main()
