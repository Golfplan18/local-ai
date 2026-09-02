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

import io
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
        # The env override short-circuits _load_cascade_order before the
        # routing-config file is read, so these tests must neutralise it —
        # otherwise they fail on any machine that sets it, which includes the
        # production host this feature exists for.
        self._env = mock.patch.dict(
            os.environ, {"ORA_SEARCH_CASCADE_ORDER": ""}, clear=False
        )
        self._env.start()
        ws._reset_cascade_order_cache()

    def tearDown(self):
        ws._reset_cascade_order_cache()
        self._env.stop()

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

    def test_empty_results_cascade_to_next_tier(self):
        """Provider returning [] is a soft miss — cascade continues to next tier."""
        self._set_fetcher("tavily", result=[])
        self._set_fetcher("brave",  result=[{"title": "b"}])
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(provider, "brave")
        self.assertEqual(results, [{"title": "b"}])
        ws._PROVIDERS["tavily"][1].assert_called_once()
        ws._PROVIDERS["brave"][1].assert_called_once()

    def test_all_tiers_empty_returns_none(self):
        """When every tier returns [], the cascade reports ([], 'none')."""
        self._set_fetcher("tavily", result=[])
        self._set_fetcher("brave",  result=[])
        self._set_fetcher("ddg",    result=[])
        with _isolate_keys(TAVILY_API_KEY="key", BRAVE_API_KEY="key"):
            results, provider = ws._search_text("q", 5)
        self.assertEqual(results, [])
        self.assertEqual(provider, "none")

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

    def test_order_param_forces_single_provider(self):
        """order=("exa",) bypasses the configured cascade for this call."""
        self._set_fetcher("exa",    result=[{"title": "e"}])
        self._set_fetcher("tavily", result=[{"title": "t"}])
        with _isolate_keys(EXA_API_KEY="key", TAVILY_API_KEY="key"):
            results, provider = ws._search_text("q", 5, order=("exa",))
        self.assertEqual(provider, "exa")
        self.assertEqual(results, [{"title": "e"}])
        ws._PROVIDERS["tavily"][1].assert_not_called()

    def test_order_param_unknown_falls_back_to_configured(self):
        """An all-invalid order override falls back to the configured cascade."""
        self._set_fetcher("tavily", result=[{"title": "t"}])
        with _isolate_keys(TAVILY_API_KEY="key"):
            results, provider = ws._search_text("q", 5, order=("bogus",))
        self.assertEqual(provider, "tavily")

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

    def test_max_results_threaded_to_provider(self):
        """query + max_results reach the selected provider's fetcher verbatim."""
        self._set_fetcher("tavily", result=[{"title": "t"}])
        with _isolate_keys(TAVILY_API_KEY="key"):
            ws._search_text("test query", 12)
        ws._PROVIDERS["tavily"][1].assert_called_once_with("test query", 12)


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


class SemanticAugmentTests(unittest.TestCase):
    """_gather_raw merges keyword + semantic results when a caller opts in."""

    def setUp(self):
        ws._reset_semantic_augment_cache()

    def tearDown(self):
        ws._reset_semantic_augment_cache()

    @staticmethod
    def _kw_or_exa(q, n, order=None):
        """order=('exa',) → a semantic hit; anything else → a keyword hit."""
        if order == ("exa",):
            return ([{"title": "e", "href": "https://exa.com", "body": "x"}], "exa")
        return ([{"title": "k", "href": "https://kw.com", "body": "y"}], "tavily")

    def test_augment_merges_keyword_and_semantic(self):
        with mock.patch.object(ws, "_load_semantic_augment", return_value=(True, "exa")), \
             mock.patch.object(ws, "_search_text", side_effect=self._kw_or_exa), \
             _isolate_keys(EXA_API_KEY="key"):
            out = ws.web_search_structured("q", 5, semantic_augment=True)
        self.assertEqual({r["url"] for r in out}, {"https://kw.com", "https://exa.com"})

    def test_augment_dedups_shared_url(self):
        def both_same(q, n, order=None):
            url = "https://dup.com"
            tag = "exa" if order == ("exa",) else "tavily"
            return ([{"title": "d", "href": url, "body": tag}], tag)
        with mock.patch.object(ws, "_load_semantic_augment", return_value=(True, "exa")), \
             mock.patch.object(ws, "_search_text", side_effect=both_same), \
             _isolate_keys(EXA_API_KEY="key"):
            out = ws.web_search_structured("q", 5, semantic_augment=True)
        self.assertEqual(len(out), 1)

    def test_augment_interleaves_semantic_co_equal(self):
        """Exa is co-primary: its hit lands at position 2 (interleaved), not
        after every keyword result."""
        def kw_or_exa(q, n, order=None):
            if order == ("exa",):
                return ([{"title": "e", "href": "https://exa.com", "body": "x"}],
                        "exa")
            return ([
                {"title": "k1", "href": "https://kw1.com", "body": "y"},
                {"title": "k2", "href": "https://kw2.com", "body": "y"},
                {"title": "k3", "href": "https://kw3.com", "body": "y"},
            ], "tavily")
        with mock.patch.object(ws, "_load_semantic_augment",
                               return_value=(True, "exa")), \
             mock.patch.object(ws, "_search_text", side_effect=kw_or_exa), \
             _isolate_keys(EXA_API_KEY="key"):
            out = ws.web_search_structured("q", 5, semantic_augment=True)
        urls = [r["url"] for r in out]
        self.assertEqual(urls, ["https://kw1.com", "https://exa.com",
                                "https://kw2.com", "https://kw3.com"])

    def test_augment_noop_without_key(self):
        with mock.patch.object(ws, "_load_semantic_augment", return_value=(True, "exa")), \
             mock.patch.object(ws, "_search_text", side_effect=self._kw_or_exa) as m, \
             _isolate_keys():  # EXA_API_KEY absent
            out = ws.web_search_structured("q", 5, semantic_augment=True)
        self.assertEqual([r["url"] for r in out], ["https://kw.com"])
        self.assertEqual(m.call_count, 1)  # the exa sub-call is never made

    def test_augment_noop_when_disabled(self):
        with mock.patch.object(ws, "_load_semantic_augment", return_value=(False, "exa")), \
             mock.patch.object(ws, "_search_text", side_effect=self._kw_or_exa) as m, \
             _isolate_keys(EXA_API_KEY="key"):
            out = ws.web_search_structured("q", 5, semantic_augment=True)
        self.assertEqual([r["url"] for r in out], ["https://kw.com"])
        self.assertEqual(m.call_count, 1)

    def test_no_augment_flag_skips_config_and_semantic(self):
        with mock.patch.object(ws, "_load_semantic_augment", return_value=(True, "exa")) as la, \
             mock.patch.object(ws, "_search_text", side_effect=self._kw_or_exa) as m, \
             _isolate_keys(EXA_API_KEY="key"):
            out = ws.web_search_structured("q", 5)  # semantic_augment defaults False
        self.assertEqual([r["url"] for r in out], ["https://kw.com"])
        self.assertEqual(m.call_count, 1)
        la.assert_not_called()


class PublicEntryPointErrorPaths(unittest.TestCase):
    """Both public entry points degrade gracefully when the cascade raises
    (rather than returning the ``([], "none")`` soft-miss tuple). The
    cascade tests above only exercise return values, so these two paths —
    ``web_search``'s ``"Search error:"`` string and
    ``web_search_structured``'s empty-list-plus-stderr-log — are the slice
    of the retired ``test_web_search.py`` not otherwise covered."""

    def test_web_search_returns_error_string_on_exception(self):
        with mock.patch.object(
            ws, "_gather_raw", side_effect=RuntimeError("rate limited")
        ):
            text = ws.web_search("any query")
        self.assertTrue(text.startswith("Search error:"))
        self.assertIn("rate limited", text)

    def test_web_search_structured_returns_empty_and_logs(self):
        captured = io.StringIO()
        with mock.patch.object(
            ws, "_gather_raw", side_effect=RuntimeError("rate limited")
        ), mock.patch.object(sys, "stderr", captured):
            out = ws.web_search_structured("any query")
        self.assertEqual(out, [])
        msg = captured.getvalue()
        self.assertIn("web_search_structured", msg)
        self.assertIn("rate limited", msg)




class CascadeEnvOverrideTests(unittest.TestCase):
    """ORA_SEARCH_CASCADE_ORDER pins a deployment's cascade without forking
    the whole routing-config file, which ORA_ROUTING_CONFIG_PATH would
    require (it is a full-file replacement, not a merge)."""

    def setUp(self):
        ws._reset_cascade_order_cache()

    def tearDown(self):
        ws._reset_cascade_order_cache()

    def test_env_override_beats_routing_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump({"search_cascade_order": ["tavily", "brave", "ddg"]}, fh)
            path = fh.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path), \
                    mock.patch.dict(
                        os.environ,
                        {"ORA_SEARCH_CASCADE_ORDER": "ddg,brave"},
                        clear=False,
                    ):
                self.assertEqual(ws._load_cascade_order(), ("ddg", "brave"))
        finally:
            os.unlink(path)

    def test_unknown_names_in_env_fall_back_to_config_not_to_paid_default(self):
        """A typo must not silently promote the paid default cascade."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump({"search_cascade_order": ["ddg"]}, fh)
            path = fh.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path), \
                    mock.patch.dict(
                        os.environ,
                        {"ORA_SEARCH_CASCADE_ORDER": "duckduckgo,brave-search"},
                        clear=False,
                    ):
                self.assertEqual(ws._load_cascade_order(), ("ddg",))
        finally:
            os.unlink(path)

    def test_unreadable_config_announces_the_paid_fallback(self):
        """The default cascade leads with billed providers. Reverting to it
        silently is how a config typo turns into a bill, so it must speak."""
        buf = io.StringIO()
        with mock.patch.object(
            ws, "_ROUTING_CONFIG_PATH", "/nonexistent/path.json"
        ), mock.patch.dict(
            os.environ, {"ORA_SEARCH_CASCADE_ORDER": ""}, clear=False
        ), mock.patch.object(sys, "stderr", buf):
            order = ws._load_cascade_order()
        self.assertEqual(order, ("tavily", "brave", "ddg"))
        self.assertIn("routing-config unreadable", buf.getvalue())


class KeylessTierVisibilityTests(unittest.TestCase):
    """A keyed tier with no key used to vanish in total silence — that is how
    a missing key can delete a fallback with nothing in the logs. Providers are
    patched wholesale (``_PROVIDERS`` captures the fetchers by reference at
    import, so patching the module-level names alone would let real network
    calls through)."""

    def setUp(self):
        ws._reset_cascade_order_cache()
        ws._KEYLESS_SKIP_ANNOUNCED.clear()
        self._providers = mock.patch.object(ws, "_PROVIDERS", {
            "tavily": ("TAVILY_API_KEY", mock.MagicMock(name="tavily_fetcher")),
            "brave":  ("BRAVE_API_KEY",  mock.MagicMock(name="brave_fetcher")),
            "exa":    ("EXA_API_KEY",    mock.MagicMock(name="exa_fetcher")),
            "ddg":    (None,             mock.MagicMock(name="ddg_fetcher")),
        })
        self._providers.start()

    def tearDown(self):
        self._providers.stop()
        ws._reset_cascade_order_cache()
        ws._KEYLESS_SKIP_ANNOUNCED.clear()

    @staticmethod
    def _hit():
        return [{"title": "t", "href": "u", "body": "b"}]

    def test_missing_key_is_announced_once(self):
        ws._PROVIDERS["ddg"][1].return_value = self._hit()
        buf = io.StringIO()
        with _isolate_keys(BRAVE_API_KEY=""), mock.patch.object(sys, "stderr", buf):
            for _ in range(3):
                ws._search_text("q", 5, order=("brave", "ddg"))
        out = buf.getvalue()
        self.assertIn("BRAVE_API_KEY is not set", out)
        self.assertEqual(out.count("that tier is inactive"), 1)
        ws._PROVIDERS["brave"][1].assert_not_called()

    def test_fallthrough_names_the_provider_that_served(self):
        ws._PROVIDERS["ddg"][1].side_effect = RuntimeError("throttled")
        ws._PROVIDERS["brave"][1].return_value = self._hit()
        buf = io.StringIO()
        with _isolate_keys(BRAVE_API_KEY="k"), mock.patch.object(sys, "stderr", buf):
            _, tag = ws._search_text("q", 5, order=("ddg", "brave"))
        self.assertEqual(tag, "brave")
        self.assertIn("brave served query", buf.getvalue())

    def test_empty_result_also_falls_through_and_is_attributed(self):
        """The soft-miss path, not just the exception path — this is what makes
        Brave a real safety net behind a free primary rather than a decoration."""
        ws._PROVIDERS["ddg"][1].return_value = []
        ws._PROVIDERS["brave"][1].return_value = self._hit()
        buf = io.StringIO()
        with _isolate_keys(BRAVE_API_KEY="k"), mock.patch.object(sys, "stderr", buf):
            _, tag = ws._search_text("q", 5, order=("ddg", "brave"))
        self.assertEqual(tag, "brave")
        self.assertIn("brave served query", buf.getvalue())

    def test_first_tier_win_stays_quiet(self):
        ws._PROVIDERS["ddg"][1].return_value = self._hit()
        buf = io.StringIO()
        with _isolate_keys(BRAVE_API_KEY="k"), mock.patch.object(sys, "stderr", buf):
            _, tag = ws._search_text("q", 5, order=("ddg", "brave"))
        self.assertEqual(tag, "ddg")
        self.assertNotIn("served query", buf.getvalue())
        ws._PROVIDERS["brave"][1].assert_not_called()


class QueryCapTests(unittest.TestCase):
    """search_query_cap() reads the per-fan-out ceiling. 0 == unlimited, so
    machines that do not set it keep their existing behaviour."""

    def test_absent_is_unlimited(self):
        with mock.patch.dict(os.environ, {"ORA_SEARCH_MAX_QUERIES": ""}, clear=False):
            self.assertEqual(ws.search_query_cap(), 0)

    def test_value_is_read(self):
        with mock.patch.dict(os.environ, {"ORA_SEARCH_MAX_QUERIES": "12"}, clear=False):
            self.assertEqual(ws.search_query_cap(), 12)

    def test_garbage_is_unlimited_not_zero_searches(self):
        """A malformed value must not silently disable search entirely."""
        with mock.patch.dict(os.environ, {"ORA_SEARCH_MAX_QUERIES": "twelve"}, clear=False):
            self.assertEqual(ws.search_query_cap(), 0)

    def test_negative_is_unlimited(self):
        with mock.patch.dict(os.environ, {"ORA_SEARCH_MAX_QUERIES": "-5"}, clear=False):
            self.assertEqual(ws.search_query_cap(), 0)


class CascadeTypoSafetyTests(unittest.TestCase):
    """A partially valid override must not delete a tier in silence.

    This is the failure the whole change exists to prevent: one mistyped name
    in a unit file leaving production on a single free tier, while the
    accepted-order log line still reads like success.
    """

    def setUp(self):
        ws._reset_cascade_order_cache()

    def tearDown(self):
        ws._reset_cascade_order_cache()

    def _resolve(self, value, config=("tavily", "brave", "ddg")):
        buf = io.StringIO()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump({"search_cascade_order": list(config)}, fh)
            path = fh.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path), \
                    mock.patch.dict(
                        os.environ, {"ORA_SEARCH_CASCADE_ORDER": value}, clear=False
                    ), mock.patch.object(sys, "stderr", buf):
                return ws._load_cascade_order(), buf.getvalue()
        finally:
            os.unlink(path)

    def test_one_mistyped_name_is_named_in_the_warning(self):
        order, out = self._resolve("ddg,brve")
        self.assertEqual(order, ("ddg",))
        self.assertIn("Unknown provider(s) in ORA_SEARCH_CASCADE_ORDER", out)
        self.assertIn("brve", out)

    def test_case_is_folded_rather_than_rejected(self):
        """"DDG,BRAVE" must not fall back to a cascade that leads with a paid
        tier merely because the operator used capitals."""
        order, out = self._resolve("DDG,BRAVE")
        self.assertEqual(order, ("ddg", "brave"))
        self.assertNotIn("Unknown provider", out)

    def test_whitespace_and_empty_segments_are_tolerated(self):
        order, _ = self._resolve(" ddg , , brave ")
        self.assertEqual(order, ("ddg", "brave"))

    def test_resolved_order_is_always_announced(self):
        """The routing-config path resolves to a paid-first cascade on the
        shipped tree; it must never be the one path that stays quiet."""
        order, out = self._resolve("", config=("tavily", "brave", "ddg"))
        self.assertEqual(order, ("tavily", "brave", "ddg"))
        self.assertIn("cascade order:", out)
        self.assertIn("routing-config", out)


class SemanticAugmentOverrideTests(unittest.TestCase):
    """Semantic augmentation is a second search per query that the cascade
    order does not govern — pinning a free cascade must be able to stop it."""

    def setUp(self):
        ws._reset_semantic_augment_cache()

    def tearDown(self):
        ws._reset_semantic_augment_cache()

    def _load(self, env, config_enabled=True):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump({"semantic_augment": {"enabled": config_enabled,
                                            "provider": "exa"}}, fh)
            path = fh.name
        try:
            with mock.patch.object(ws, "_ROUTING_CONFIG_PATH", path), \
                    mock.patch.dict(
                        os.environ, {"ORA_SEARCH_SEMANTIC_AUGMENT": env}, clear=False
                    ), mock.patch.object(sys, "stderr", io.StringIO()):
                return ws._load_semantic_augment()
        finally:
            os.unlink(path)

    def test_env_off_beats_config_on(self):
        enabled, _ = self._load("0", config_enabled=True)
        self.assertFalse(enabled)

    def test_env_on_beats_config_off(self):
        enabled, _ = self._load("1", config_enabled=False)
        self.assertTrue(enabled)

    def test_unset_leaves_config_in_charge(self):
        enabled, _ = self._load("", config_enabled=True)
        self.assertTrue(enabled)

    def test_garbage_leaves_config_in_charge(self):
        enabled, _ = self._load("maybe", config_enabled=True)
        self.assertTrue(enabled)


if __name__ == "__main__":
    unittest.main()
