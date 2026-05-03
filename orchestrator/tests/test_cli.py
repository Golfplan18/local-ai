"""Tests for the batch CLI + manifest (Phase 1.12)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.cli import (  # noqa: E402
    _empty_manifest,
    chat_creation_date,
    enumerate_input_files,
    load_manifest,
    manifest_completed,
    manifest_record_completed,
    manifest_record_errored,
    passes_date_filter,
    save_manifest,
)
from orchestrator.historical.file_orchestrator import (  # noqa: E402
    FileProcessingResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_SAMPLE_CHAT = """---
title: Sample
type: chat
---
# Sample

## Overview

- **Title:** Sample
- **Url:** [https://chatgpt.com/c/x](https://chatgpt.com/c/x)
- **ID:** x
- **Created:** {created}
- **Last Updated:** {created}
- **Total Messages:** 2

## Conversation

<i>[{created}]</i> 👉 <b>👤 User</b>: Hi.
<i>[{created}]</i> 👉 <b>🤖 Assistant</b>: Hello.<br>
"""


def _write_sample(dir_: str, name: str, created: str) -> str:
    path = os.path.join(dir_, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_SAMPLE_CHAT.format(created=created))
    return path


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class TestManifest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "manifest.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_manifest_returns_empty_when_missing(self):
        m = load_manifest(self.path)
        self.assertIn("completed_files", m)
        self.assertEqual(m["completed_files"], {})

    def test_save_load_roundtrip(self):
        m = _empty_manifest()
        m["completed_files"]["x.md"] = {"pairs_total": 5}
        save_manifest(self.path, m)
        m2 = load_manifest(self.path)
        self.assertIn("x.md", m2["completed_files"])
        self.assertEqual(m2["completed_files"]["x.md"]["pairs_total"], 5)

    def test_record_completed_updates_totals(self):
        m = _empty_manifest()
        result = FileProcessingResult(
            raw_path="x.md",
            chat_title="X", chat_platform="chatgpt",
            pairs_total=10, pairs_succeeded=10, pairs_with_errors=0,
            output_paths=["a.md", "b.md"],
            total_input_tokens=100, total_output_tokens=50,
            total_cost_usd=0.05,
        )
        manifest_record_completed(m, "x.md", result)
        self.assertTrue(manifest_completed(m, "x.md"))
        self.assertEqual(m["totals"]["pairs_total"], 10)
        self.assertAlmostEqual(m["totals"]["cost_usd"], 0.05)

    def test_record_errored_then_completed_clears_error(self):
        m = _empty_manifest()
        err_result = FileProcessingResult(
            raw_path="x.md", aborted=True, abort_reason="test",
            errors=["e1"], pairs_total=3,
        )
        manifest_record_errored(m, "x.md", err_result)
        self.assertIn("x.md", m["errored_files"])

        ok_result = FileProcessingResult(
            raw_path="x.md", pairs_total=3, pairs_succeeded=3,
        )
        manifest_record_completed(m, "x.md", ok_result)
        self.assertNotIn("x.md", m["errored_files"])
        self.assertIn("x.md", m["completed_files"])


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------


class TestEnumeration(unittest.TestCase):

    def test_enumerate_recursive_md_only(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "sub"))
            for n in ("a.md", "b.md", "c.txt"):
                open(os.path.join(tmp, n), "w").close()
            for n in ("d.md", "e.md"):
                open(os.path.join(tmp, "sub", n), "w").close()
            files = enumerate_input_files(tmp)
            self.assertEqual(len(files), 4)   # a, b, sub/d, sub/e
            self.assertTrue(all(f.endswith(".md") for f in files))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_enumerate_missing_dir_returns_empty(self):
        self.assertEqual(enumerate_input_files("/no/such/path"), [])


# ---------------------------------------------------------------------------
# Date filter
# ---------------------------------------------------------------------------


class TestDateFilter(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chat_creation_date_extracted(self):
        path = _write_sample(self.tmp, "x.md", "7/14/2025, 9:00:00 AM")
        d = chat_creation_date(path)
        self.assertEqual(d, date(2025, 7, 14))

    def test_chat_creation_date_unparseable(self):
        path = os.path.join(self.tmp, "junk.md")
        with open(path, "w") as f:
            f.write("no frontmatter, no overview")
        d = chat_creation_date(path)
        self.assertIsNone(d)

    def test_passes_filter_in_range(self):
        path = _write_sample(self.tmp, "x.md", "3/15/2026, 9:00:00 AM")
        self.assertTrue(passes_date_filter(
            path, from_date=date(2026, 2, 1), to_date=None,
        ))

    def test_passes_filter_before_from_date(self):
        path = _write_sample(self.tmp, "x.md", "1/15/2026, 9:00:00 AM")
        self.assertFalse(passes_date_filter(
            path, from_date=date(2026, 2, 1), to_date=None,
        ))

    def test_passes_filter_after_to_date(self):
        path = _write_sample(self.tmp, "x.md", "5/15/2026, 9:00:00 AM")
        self.assertFalse(passes_date_filter(
            path, from_date=None, to_date=date(2026, 4, 1),
        ))

    def test_passes_filter_when_no_dates_set(self):
        path = _write_sample(self.tmp, "x.md", "5/15/2026, 9:00:00 AM")
        self.assertTrue(passes_date_filter(path, None, None))

    def test_unparseable_date_passes_filter_safely(self):
        # Default policy: include unparseable dates rather than drop them.
        path = os.path.join(self.tmp, "junk.md")
        with open(path, "w") as f:
            f.write("no frontmatter")
        self.assertTrue(passes_date_filter(
            path, from_date=date(2026, 2, 1), to_date=None,
        ))


if __name__ == "__main__":
    unittest.main()
