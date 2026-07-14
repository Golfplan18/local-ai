"""Tests for the batch CLI + manifest (Phase 1.12)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import cli as cli_module  # noqa: E402
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


class TestRuntimePathDefaults(unittest.TestCase):

    def _run_empty_batch(self, **kwargs):
        client = mock.Mock()
        with (
            mock.patch.object(
                cli_module, "load_manifest", return_value=_empty_manifest(),
            ) as load_manifest_mock,
            mock.patch.object(
                cli_module, "load_index", return_value={"entries": []},
            ) as load_index_mock,
            mock.patch.object(
                cli_module, "enumerate_input_files", return_value=[],
            ) as enumerate_mock,
            mock.patch.object(cli_module, "build_client", return_value=client),
        ):
            result = cli_module.run_batch(
                progress_to_stderr=False, **kwargs,
            )
        return result, load_manifest_mock, load_index_mock, enumerate_mock

    def test_omitted_defaults_relocate_at_call_time(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conversations = root / "redirected" / "conversations"
            ora_home = root / "Ora Home"
            env = {
                "HOME": str(root / "profile"),
                "USERPROFILE": str(root / "profile"),
                "ORA_HOME": str(ora_home),
                "ORA_CONVERSATIONS": str(conversations),
            }
            with mock.patch.dict(os.environ, env, clear=True):
                result, load_manifest_mock, load_index_mock, enumerate_mock = (
                    self._run_empty_batch()
                )

        expected_input = str(conversations / "raw")
        expected_data = ora_home / "data"
        enumerate_mock.assert_called_once_with(expected_input)
        load_manifest_mock.assert_called_once_with(
            str(expected_data / "cleanup-manifest.json")
        )
        load_index_mock.assert_called_once_with(
            str(expected_data / "vault-index.json")
        )
        self.assertEqual(result["input_dir"], expected_input)
        self.assertEqual(
            result["manifest_path"],
            str(expected_data / "cleanup-manifest.json"),
        )

    def test_explicit_paths_win_after_relocation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            explicit_input = str(root / "explicit-input")
            explicit_manifest = str(root / "explicit-manifest.json")
            explicit_index = str(root / "explicit-index.json")
            with mock.patch.dict(os.environ, {
                "HOME": str(root / "profile"),
                "USERPROFILE": str(root / "profile"),
                "ORA_HOME": str(root / "relocated-home"),
                "ORA_CONVERSATIONS": str(root / "relocated-conversations"),
            }, clear=True):
                result, load_manifest_mock, load_index_mock, enumerate_mock = (
                    self._run_empty_batch(
                        input_dir=explicit_input,
                        manifest_path=explicit_manifest,
                        vault_index_path=explicit_index,
                    )
                )

        enumerate_mock.assert_called_once_with(explicit_input)
        load_manifest_mock.assert_called_once_with(explicit_manifest)
        load_index_mock.assert_called_once_with(explicit_index)
        self.assertEqual(result["input_dir"], explicit_input)
        self.assertEqual(result["manifest_path"], explicit_manifest)


if __name__ == "__main__":
    unittest.main()
