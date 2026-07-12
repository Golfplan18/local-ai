"""Tests for privacy_tagging's pair→files index over the flat vault
Resources/ layout (Schema rev 5, 2026-05-09).

The retired Sources/{News,Opinion,Resources} tree no longer exists;
until 2026-07 the walk still targeted it and silently matched zero
source notes — leaving every source note untagged by privacy passes.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.privacy_tagging import (  # noqa: E402
    _build_pair_to_files_index,
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


if __name__ == "__main__":
    unittest.main()
