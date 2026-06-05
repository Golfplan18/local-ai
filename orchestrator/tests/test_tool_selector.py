"""Tests for the deterministic tool resolver (tool_selector.py).

Covers the Option C deterministic lane (G1.10 #7): ## TOOLS parsing,
prompt-derived web_fetch params, JSON-result formatting, and the fail-soft
execution loop with an injected fake executor (no real dispatcher / network).
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tool_selector as ts  # noqa: E402


SECTIONED_MODE = """# MODE: Demo

## ANALYTICAL PERSPECTIVES

Thinking tools:
- CAF

## TOOLS

### Deterministic (Ora runs at context assembly)
- web_fetch — fetch any URLs in the prompt
- nonexistent_tool — should be recorded as unsupported

### Model-requestable (escape hatch; capable slots only)
- web_search
- knowledge_search

## RAG PROFILE

stuff
"""

NO_TOOLS_MODE = """# MODE: Plain

## DEFAULT GEAR
Gear 4
"""


def _fake_web_fetch_executor(name, params):
    """Mimic dispatcher.dispatch: web_fetch's dict result arrives json.dumps'd."""
    assert name == "web_fetch"
    return json.dumps({
        "url": params["url"],
        "markdown": "# Heading\n\nThe fetched article body, long enough to clear the floor.",
        "title": "Fetched Article",
        "channel": "httpx",
        "fetched_at": "2026-06-05T00:00:00Z",
    })


class TestParseToolProfile(unittest.TestCase):
    def test_no_section(self):
        self.assertEqual(ts.parse_tool_profile(NO_TOOLS_MODE),
                         {"deterministic": [], "model_requestable": []})

    def test_empty_string(self):
        self.assertEqual(ts.parse_tool_profile(""),
                         {"deterministic": [], "model_requestable": []})

    def test_parses_both_subheadings(self):
        p = ts.parse_tool_profile(SECTIONED_MODE)
        self.assertEqual(p["deterministic"], ["web_fetch", "nonexistent_tool"])
        self.assertEqual(p["model_requestable"], ["web_search", "knowledge_search"])

    def test_strips_backticks(self):
        mode = "## TOOLS\n\n### Deterministic\n- `web_fetch` — x\n"
        self.assertEqual(ts.parse_tool_profile(mode)["deterministic"], ["web_fetch"])


class TestDeriveWebFetch(unittest.TestCase):
    def test_extracts_urls(self):
        calls = ts._derive_web_fetch_calls("see https://example.com/a and http://foo.org")
        self.assertEqual([c["url"] for c in calls],
                         ["https://example.com/a", "http://foo.org"])
        self.assertTrue(all(c["persist"] is False for c in calls))

    def test_dedup_and_trailing_punct(self):
        calls = ts._derive_web_fetch_calls("read https://x.com/p. also https://x.com/p again")
        self.assertEqual([c["url"] for c in calls], ["https://x.com/p"])

    def test_cap(self):
        urls = " ".join(f"https://s{i}.com" for i in range(10))
        self.assertEqual(len(ts._derive_web_fetch_calls(urls)), ts._MAX_CALLS_PER_TOOL)

    def test_no_urls(self):
        self.assertEqual(ts._derive_web_fetch_calls("no links here"), [])


class TestFormatWebFetch(unittest.TestCase):
    def test_extracts_markdown_and_title(self):
        raw = json.dumps({"markdown": "Body text here that is sufficiently long.",
                          "title": "T"})
        out = ts._format_web_fetch_result(raw)
        self.assertIn("**T**", out)
        self.assertIn("Body text here", out)

    def test_non_json_fallback(self):
        self.assertEqual(ts._format_web_fetch_result("a plain string result"),
                         "a plain string result")

    def test_empty_markdown_with_error(self):
        out = ts._format_web_fetch_result(json.dumps({"markdown": "", "error": "timeout"}))
        self.assertIn("no content retrieved", out)
        self.assertIn("timeout", out)

    def test_truncation(self):
        big = "x" * (ts._FETCH_MARKDOWN_CAP + 500)
        out = ts._format_web_fetch_result(json.dumps({"markdown": big, "title": ""}))
        self.assertIn("[truncated]", out)


class TestRunDeterministicTools(unittest.TestCase):
    def test_no_section_returns_empty(self):
        r = ts.run_deterministic_tools(NO_TOOLS_MODE, "https://x.com",
                                       executor=_fake_web_fetch_executor)
        self.assertEqual(r["body"], "")
        self.assertEqual(r["trace"]["status"], "skipped")
        self.assertEqual(r["trace"]["reason"], "no_deterministic_tools_declared")

    def test_web_fetch_runs_and_injects(self):
        r = ts.run_deterministic_tools(
            SECTIONED_MODE, "audit this argument: https://example.com/post",
            executor=_fake_web_fetch_executor,
        )
        self.assertEqual(r["trace"]["status"], "ran")
        self.assertIn("web_fetch — https://example.com/post", r["body"])
        self.assertIn("Fetched Article", r["body"])
        self.assertIn("article body", r["body"])
        self.assertIn("nonexistent_tool", r["trace"]["tools_unsupported"])
        self.assertEqual(r["trace"]["tools_supported"], ["web_fetch"])

    def test_no_url_in_prompt(self):
        r = ts.run_deterministic_tools(SECTIONED_MODE, "no links present",
                                       executor=_fake_web_fetch_executor)
        self.assertEqual(r["body"], "")
        self.assertIn("no_params_derived",
                      [c.get("outcome") for c in r["trace"]["calls"]])

    def test_executor_error_is_failsoft(self):
        def boom(name, params):
            raise RuntimeError("network down")
        r = ts.run_deterministic_tools(SECTIONED_MODE, "https://x.com", executor=boom)
        self.assertEqual(r["body"], "")
        self.assertIn("error", [c.get("outcome") for c in r["trace"]["calls"]])

    def test_empty_result_skipped(self):
        r = ts.run_deterministic_tools(SECTIONED_MODE, "https://x.com",
                                       executor=lambda n, p: "")
        self.assertEqual(r["body"], "")
        self.assertIn("empty", [c.get("outcome") for c in r["trace"]["calls"]])


class TestRequestableToolsCatalog(unittest.TestCase):
    def test_disabled_returns_empty(self):
        self.assertEqual(
            ts.build_requestable_tools_catalog(SECTIONED_MODE, enabled=False), "")

    def test_enabled_lists_requestable(self):
        out = ts.build_requestable_tools_catalog(SECTIONED_MODE, enabled=True)
        self.assertIn("## REQUESTABLE TOOLS", out)
        self.assertIn("web_search", out)         # declared + known read tool
        self.assertIn("knowledge_search", out)   # declared + known read tool
        self.assertIn("<tool_call><n>", out)     # exact parser protocol format

    def test_no_section_returns_empty_even_if_enabled(self):
        self.assertEqual(
            ts.build_requestable_tools_catalog(NO_TOOLS_MODE, enabled=True), "")

    def test_unknown_requestable_tool_filtered(self):
        mode = "## TOOLS\n\n### Model-requestable\n- bogus_tool — not real\n"
        self.assertEqual(
            ts.build_requestable_tools_catalog(mode, enabled=True), "")

    def test_write_tools_not_offered(self):
        # Even if a mode declares a write/execute tool as requestable, the
        # catalog only surfaces read-category tools.
        mode = "## TOOLS\n\n### Model-requestable\n- file_write\n- bash_execute\n"
        self.assertEqual(
            ts.build_requestable_tools_catalog(mode, enabled=True), "")


if __name__ == "__main__":
    unittest.main()
