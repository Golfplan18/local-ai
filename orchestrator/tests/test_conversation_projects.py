"""Tests for G1.33 project membership on the conversation envelope.

Covers ``project_ids`` end-to-end in ``conversation_memory``:
  - set on a NEW envelope from ``save_turn_spatial_state``
  - default empty (== General) and legacy backfill
  - preserved on existing envelopes (membership is edited via the modal)
  - ``set_conversation_projects`` cleaning / dedupe / General-is-implicit
  - surfaced by ``iter_conversations``
  - inherited by ``fork_conversation``

Plus the ``vault_export`` Master Matrix default-path resolver (the
``Engrams/`` -> ``Administration/`` fix that was silently zeroing nexus).
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import conversation_memory as cm  # noqa: E402
from orchestrator import vault_export as ve  # noqa: E402


class ProjectMembershipTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _read(self, conv_id):
        return cm.load_conversation_json(conv_id, sessions_root=self.root)

    def test_new_envelope_sets_project_ids(self):
        cm.save_turn_spatial_state(
            "c1", "hello", "hi", project_ids=["book"], sessions_root=self.root
        )
        self.assertEqual(self._read("c1")["project_ids"], ["book"])

    def test_new_envelope_defaults_empty(self):
        cm.save_turn_spatial_state("c2", "hello", "hi", sessions_root=self.root)
        self.assertEqual(self._read("c2")["project_ids"], [])

    def test_existing_envelope_preserves_membership(self):
        cm.save_turn_spatial_state(
            "c3", "u1", "a1", project_ids=["book"], sessions_root=self.root
        )
        # A later turn passing a different project must NOT overwrite — the
        # creation binding is sticky; membership changes go through the modal.
        cm.save_turn_spatial_state(
            "c3", "u2", "a2", project_ids=["other"], sessions_root=self.root
        )
        self.assertEqual(self._read("c3")["project_ids"], ["book"])

    def test_legacy_envelope_backfills_empty(self):
        # An envelope written before this field existed.
        conv_dir = self.root / "c4"
        conv_dir.mkdir(parents=True)
        (conv_dir / "conversation.json").write_text(
            json.dumps({"conversation_id": "c4", "tag": "", "messages": []}),
            encoding="utf-8",
        )
        cm.save_turn_spatial_state("c4", "u", "a", sessions_root=self.root)
        self.assertEqual(self._read("c4")["project_ids"], [])

    def test_set_conversation_projects_cleans(self):
        cm.save_turn_spatial_state("c5", "u", "a", sessions_root=self.root)
        cm.set_conversation_projects(
            "c5",
            ["book", "book", "general", "", "  ", "other"],
            sessions_root=self.root,
        )
        # Exact-duplicate "book" deduped; "general"/empty stripped (General
        # is the implicit baseline, never stored); order preserved.
        self.assertEqual(self._read("c5")["project_ids"], ["book", "other"])

    def test_set_conversation_projects_missing_returns_none(self):
        self.assertIsNone(
            cm.set_conversation_projects("nope", ["x"], sessions_root=self.root)
        )

    def test_iter_conversations_surfaces_project_ids(self):
        cm.save_turn_spatial_state(
            "c6", "u", "a", project_ids=["book", "law"], sessions_root=self.root
        )
        rows = {r["conversation_id"]: r for r in cm.iter_conversations(self.root)}
        self.assertEqual(rows["c6"]["project_ids"], ["book", "law"])

    def test_fork_inherits_project_ids(self):
        cm.save_turn_spatial_state(
            "parent", "u", "a", project_ids=["book"], sessions_root=self.root
        )
        new_id = cm.fork_conversation(
            "parent", "child", sessions_root=self.root
        )
        self.assertIsNotNone(new_id)
        self.assertEqual(self._read("child")["project_ids"], ["book"])


class MasterMatrixPathTests(unittest.TestCase):
    def test_administration_is_primary_candidate(self):
        # Regression: the hard-coded default used the non-existent Engrams/
        # path, zeroing every export's nexus. Administration/ must lead.
        self.assertIn("Administration", str(ve._MASTER_MATRIX_CANDIDATES[0]))

    def test_default_path_prefers_existing_candidate(self):
        original = ve._MASTER_MATRIX_CANDIDATES
        try:
            with tempfile.TemporaryDirectory() as d:
                missing = pathlib.Path(d) / "missing.md"
                present = pathlib.Path(d) / "present.md"
                present.write_text("x", encoding="utf-8")
                ve._MASTER_MATRIX_CANDIDATES = (missing, present)
                self.assertEqual(ve._default_master_matrix_path(), present)
                # When none exist, fall back to the first (canonical) candidate.
                ve._MASTER_MATRIX_CANDIDATES = (missing,)
                self.assertEqual(ve._default_master_matrix_path(), missing)
        finally:
            ve._MASTER_MATRIX_CANDIDATES = original


if __name__ == "__main__":
    unittest.main()
