"""Tests for the engagement-wrapper strip (Phase 1.4).

Verifies the strict 5-step rule:
  - Trailing paragraph with `?` is stripped
  - Iterate until last paragraph is question-free
  - URLs and code blocks containing `?` don't trigger false positives
  - Empty response no-ops
  - Logging produces JSONL audit records
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.engagement import (  # noqa: E402
    StripRecord,
    log_strips,
    strip_and_log,
    strip_engagement,
)


# ---------------------------------------------------------------------------
# Strip behavior — the 5-step rule
# ---------------------------------------------------------------------------


class TestStripEngagement(unittest.TestCase):

    def test_no_questions_no_strip(self):
        text = "Here is your answer.\n\nThe value is 42."
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(records, [])

    def test_trailing_question_stripped(self):
        text = ("The answer is 42.\n\n"
                "Would you like me to elaborate further?")
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, "The answer is 42.")
        self.assertEqual(len(records), 1)
        self.assertIn("Would you like", records[0].paragraph)

    def test_question_anywhere_in_last_paragraph_strips(self):
        # Question embedded mid-paragraph (not at start) — still strip.
        text = ("Here's the result.\n\n"
                "The output is 42. Should I run again? Let me know.")
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, "Here's the result.")
        self.assertEqual(len(records), 1)

    def test_iterates_through_multiple_trailing_questions(self):
        text = (
            "Real content here.\n\n"
            "First trailing paragraph with content.\n\n"
            "Want me to explain?\n\n"
            "Or maybe go deeper?"
        )
        cleaned, records = strip_engagement(text)
        # Both trailing question paragraphs gone.
        self.assertEqual(cleaned,
                         "Real content here.\n\nFirst trailing paragraph with content.")
        self.assertEqual(len(records), 2)

    def test_question_mid_response_not_stripped(self):
        # Questions mid-response (with non-question paragraph after) survive.
        text = ("First, did you know?\n\n"
                "The answer is yes.\n\n"
                "Final non-question content.")
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(records, [])

    def test_entire_response_one_paragraph_with_question(self):
        text = "I think this is right. Want to verify?"
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, "")
        self.assertEqual(len(records), 1)

    def test_empty_response_no_op(self):
        cleaned, records = strip_engagement("")
        self.assertEqual(cleaned, "")
        self.assertEqual(records, [])

    def test_whitespace_only_response(self):
        cleaned, records = strip_engagement("   \n\n   \n\n   ")
        self.assertEqual(cleaned, "")
        self.assertEqual(records, [])


# ---------------------------------------------------------------------------
# False-positive guards (URLs, code, inline code)
# ---------------------------------------------------------------------------


class TestFalsePositiveGuards(unittest.TestCase):

    def test_url_with_query_string_not_a_question(self):
        text = ("Here are the results.\n\n"
                "See https://example.com/search?q=foo&n=10 for details.")
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(records, [])

    def test_code_fence_question_mark_not_a_question(self):
        text = ("Here is your code:\n\n"
                "```python\nx = data.get('key', '?')\n```")
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(records, [])

    def test_inline_code_question_mark_not_a_question(self):
        text = ("The regex is `[a-z]+\\?` and matches.\n\n"
                "Use that to detect the pattern.")
        cleaned, records = strip_engagement(text)
        self.assertEqual(cleaned, text)
        self.assertEqual(records, [])

    def test_real_question_alongside_url_still_strips(self):
        text = ("Here's the link.\n\n"
                "Check https://example.com?foo=bar — does that work for you?")
        cleaned, records = strip_engagement(text)
        # The URL has `?`, but there's also a real `?` after.
        self.assertEqual(cleaned, "Here's the link.")
        self.assertEqual(len(records), 1)


# ---------------------------------------------------------------------------
# Strip-record metadata
# ---------------------------------------------------------------------------


class TestStripRecord(unittest.TestCase):

    def test_record_carries_metadata(self):
        text = "Real content.\n\nWant more?"
        _, records = strip_engagement(text)
        rec = records[0]
        self.assertEqual(rec.paragraph_index, 0)   # this was the LAST
        self.assertGreater(rec.paragraph_length, 0)
        self.assertEqual(rec.reason, "trailing-question")
        self.assertIn("Want more", rec.paragraph)

    def test_record_indices_pop_order(self):
        text = ("Real content.\n\n"
                "Filler paragraph about nothing relevant here today.\n\n"
                "Want more?\n\n"
                "Or shall I expand?")
        _, records = strip_engagement(text)
        # First record popped = index 0 (the original last);
        # second popped = index 1 (the previous-to-last).
        self.assertEqual([r.paragraph_index for r in records], [0, 1])


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestLogging(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmp, "engagement-strips.log")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_writes_jsonl(self):
        text = "Real content.\n\nWant more?"
        cleaned, records = strip_engagement(text)
        n = log_strips(records,
                        context={"source_path": "test.md", "pair_num": 5},
                        log_path=self.log_path)
        self.assertEqual(n, 1)
        with open(self.log_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 1)
        entry = lines[0]
        self.assertEqual(entry["source_path"], "test.md")
        self.assertEqual(entry["pair_num"], 5)
        self.assertEqual(entry["reason"], "trailing-question")
        self.assertIn("Want more", entry["paragraph"])

    def test_log_appends_not_overwrites(self):
        # Two separate strip events; log should accumulate.
        for i in range(2):
            _, records = strip_engagement(f"Real {i}.\n\nQuestion {i}?")
            log_strips(records,
                        context={"source_path": f"file-{i}.md"},
                        log_path=self.log_path)
        with open(self.log_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["source_path"], "file-0.md")
        self.assertEqual(lines[1]["source_path"], "file-1.md")

    def test_log_no_op_on_empty_records(self):
        n = log_strips([], context={"source_path": "x.md"},
                        log_path=self.log_path)
        self.assertEqual(n, 0)
        # File should not even exist.
        self.assertFalse(os.path.exists(self.log_path))

    def test_strip_and_log_helper(self):
        text = "Content.\n\nMore?"
        cleaned, records = strip_and_log(
            text, context={"source_path": "x.md"},
            log_path=self.log_path,
        )
        self.assertEqual(cleaned, "Content.")
        self.assertEqual(len(records), 1)
        with open(self.log_path, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(entries), 1)


if __name__ == "__main__":
    unittest.main()
