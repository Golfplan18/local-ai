"""Tests for privacy_tagging's pair→files index over the flat vault
Resources/ layout (Schema rev 5, 2026-05-09).

The retired Sources/{News,Opinion,Resources} tree no longer exists;
until 2026-07 the walk still targeted it and silently matched zero
source notes — leaving every source note untagged by privacy passes.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.privacy_tagging import (  # noqa: E402
    PairDetection,
    _build_pair_to_files_index,
    main,
    propagate_within_chains,
    run_privacy_tagging,
)


_NOTE_TEMPLATE = """---
nexus:
type: resource
tags:
  - {kind}
source_chat: {source_chat}
source_pair_num: {pair_num}
---

# {title}

Body text.
"""


class TestBuildPairToFilesIndexFlatResources(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        self.conversations = os.path.join(self.tmp, "conversations")
        os.makedirs(os.path.join(self.vault, "Resources"))
        os.makedirs(os.path.join(self.vault, "Engrams",
                                 "Historical Atomics"))
        os.makedirs(self.conversations)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_resource_note(self, name: str, kind: str,
                             source_chat: str, pair_num: int) -> str:
        path = Path(self.vault) / "Resources" / name
        path.write_text(_NOTE_TEMPLATE.format(
            kind=kind, source_chat=source_chat, pair_num=pair_num,
            title=name,
        ), encoding="utf-8")
        return str(path)

    def test_flat_resources_notes_are_indexed_as_source_layer(self):
        chat = os.path.expanduser("~/Documents/conversations/raw/x.md")
        p_news = self._write_resource_note(
            "2025-07-14_climate-bill.md", "news", chat, 3)
        p_opinion = self._write_resource_note(
            "2025-07-15_why-x-matters.md", "opinion", chat, 4)

        idx = _build_pair_to_files_index(self.conversations, self.vault)

        self.assertIn((chat, 3), idx)
        self.assertEqual(idx[(chat, 3)]["source"], [p_news])
        self.assertIn((chat, 4), idx)
        self.assertEqual(idx[(chat, 4)]["source"], [p_opinion])

    def test_retired_sources_tree_is_not_required(self):
        # No vault/Sources/ directory exists at all — the walk must not
        # error and must still find flat Resources/ notes.
        chat = os.path.expanduser("~/Documents/conversations/raw/y.md")
        self._write_resource_note("2025-01-01_note.md", "resource", chat, 7)
        self.assertFalse(os.path.exists(os.path.join(self.vault, "Sources")))

        idx = _build_pair_to_files_index(self.conversations, self.vault)

        self.assertEqual(len(idx[(chat, 7)]["source"]), 1)

    def test_note_without_provenance_yaml_is_ignored(self):
        path = Path(self.vault) / "Resources" / "stray.md"
        path.write_text("# No YAML here\n\nJust text.", encoding="utf-8")

        idx = _build_pair_to_files_index(self.conversations, self.vault)

        self.assertEqual(len(idx), 0)


class TestPrivacyPropagation(unittest.TestCase):

    @staticmethod
    def _detection(uid: str, *, thread: str, private: bool = False):
        return PairDetection(
            file_path=f"/{uid}.md",
            source_chat="source.md",
            source_pair_num=int(uid.removeprefix("pair-")),
            thread_id=thread,
            chain_id="chain-a",
            is_private=private,
            detected_by="keyword" if private else "",
        )

    def test_thread_propagation_does_not_inflate_chain_threshold(self):
        detections = {
            f"pair-{i}": self._detection(
                f"pair-{i}",
                thread="large-thread" if i < 6 else f"thread-{i}",
                private=(i == 0),
            )
            for i in range(10)
        }
        with mock.patch(
            "orchestrator.historical.privacy_tagging.detect_privacy",
            return_value=(detections, {"pairs_total": 10}),
        ):
            summary = run_privacy_tagging(
                detection_only=True,
                progress_to_stderr=False,
            )

        self.assertEqual(summary["pairs_independently_detected"], 1)
        self.assertEqual(summary["thread_propagation_added"], 5)
        self.assertEqual(summary["chain_propagation_added"], 0)
        self.assertEqual(summary["chains_propagated"], 0)
        self.assertEqual(summary["pairs_flagged_after_propagation"], 6)

    def test_chain_propagates_at_independent_fifty_percent_threshold(self):
        detections = {
            f"pair-{i}": self._detection(
                f"pair-{i}", thread=f"thread-{i}", private=(i < 5)
            )
            for i in range(10)
        }
        independently_private = frozenset(
            uid for uid, d in detections.items() if d.is_private
        )

        added, chains = propagate_within_chains(
            detections,
            independently_private=independently_private,
        )

        self.assertEqual(added, 5)
        self.assertEqual(chains, ["chain-a"])
        self.assertTrue(all(d.is_private for d in detections.values()))


class TestRetiredManifestOption(unittest.TestCase):

    def test_manifest_option_is_hidden_from_help(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as cm:
            main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertNotIn("--manifest", stdout.getvalue())

    def test_legacy_manifest_option_warns_and_remains_parse_compatible(self):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            report = str(Path(tmp) / "privacy-report.json")
            with mock.patch(
                "orchestrator.historical.privacy_tagging.run_privacy_tagging",
                return_value={"ok": True},
            ) as run_mock, redirect_stderr(stderr), redirect_stdout(stdout):
                rc = main([
                    "--manifest", str(Path(tmp) / "retired.json"),
                    "--report", report,
                    "--quiet",
                ])

            self.assertEqual(rc, 0)
            run_mock.assert_called_once()
            self.assertIn("--manifest is retired and ignored", stderr.getvalue())
            self.assertTrue(Path(report).exists())


if __name__ == "__main__":
    unittest.main()
