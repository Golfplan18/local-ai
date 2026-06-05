"""Tests for engram_promotion — the staging->vault step that closes the
conversation->engram loop.

Hermetic: uses temp staging/vault dirs and index=False (no ChromaDB / no model).
Locks the transform (type working->engram, subtype folded into tags, canonical
filename, body preserved, staging archived) and the batch helper.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)
_ORA = os.path.dirname(_ORCHESTRATOR)
if _ORA not in sys.path:
    sys.path.insert(0, _ORA)

from orchestrator.tools import engram_promotion as ep  # noqa: E402

STAGED = """---
nexus: null
type: working
tags:
- atomic
subtype: fact
relationships:
- target: 2026-03-20_some-other-note
  type: parallels
  confidence: 0.86
  source: pass2_runtime
---

# A vetted claim about something

- A vetted claim about something
- Source: extracted from session abc123
"""


class TestStagingNoteToEngram(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.staging = os.path.join(self.tmp, "staging")
        self.vault = os.path.join(self.tmp, "Engrams")
        self.promoted = os.path.join(self.tmp, "promoted")
        os.makedirs(self.staging)
        self.note = os.path.join(self.staging, "A vetted claim about something.md")
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)

    def _promote(self, **kw):
        return ep.staging_note_to_engram(
            self.note, vault_engrams=self.vault, promoted_dir=self.promoted,
            index=False, **kw)

    def test_type_becomes_engram(self):
        r = self._promote()
        body = open(r["dest"], encoding="utf-8").read()
        self.assertIn("type: engram", body)
        self.assertNotIn("type: working", body)

    def test_subtype_folded_into_tags(self):
        r = self._promote()
        body = open(r["dest"], encoding="utf-8").read()
        self.assertIn("- atomic", body)
        self.assertIn("- fact", body)        # subtype folded in
        self.assertNotIn("subtype:", body)   # subtype field removed

    def test_canonical_filename(self):
        r = self._promote()
        name = os.path.basename(r["dest"])
        # YYYY-MM-DD_<slug>.md
        self.assertRegex(name, r"^\d{4}-\d{2}-\d{2}_[a-z0-9-]+\.md$")

    def test_body_and_relationships_preserved(self):
        r = self._promote()
        body = open(r["dest"], encoding="utf-8").read()
        self.assertIn("A vetted claim about something", body)
        self.assertIn("extracted from session abc123", body)
        self.assertIn("2026-03-20_some-other-note", body)   # relationship target kept

    def test_provenance_marker(self):
        r = self._promote()
        body = open(r["dest"], encoding="utf-8").read()
        self.assertIn("source_platform: ora-local", body)

    def test_staging_archived(self):
        r = self._promote()
        self.assertFalse(os.path.exists(self.note))          # moved out of staging
        self.assertTrue(os.path.exists(
            os.path.join(self.promoted, os.path.basename(self.note))))

    def test_dry_run_writes_nothing(self):
        r = self._promote(dry_run=True)
        self.assertIn("preview", r)
        self.assertFalse(os.path.exists(r["dest"]))          # nothing written
        self.assertTrue(os.path.exists(self.note))           # staging untouched

    def test_collision_suffix(self):
        r1 = self._promote()
        # re-create the staged note and promote again — must not overwrite
        with open(self.note, "w", encoding="utf-8") as f:
            f.write(STAGED)
        r2 = self._promote()
        self.assertNotEqual(r1["dest"], r2["dest"])
        self.assertTrue(os.path.exists(r1["dest"]) and os.path.exists(r2["dest"]))


class TestPromoteStagingDir(unittest.TestCase):
    def test_batch(self):
        tmp = tempfile.mkdtemp()
        staging = os.path.join(tmp, "staging")
        vault = os.path.join(tmp, "Engrams")
        promoted = os.path.join(tmp, "promoted")
        os.makedirs(staging)
        for i in range(3):
            with open(os.path.join(staging, f"claim number {i}.md"), "w", encoding="utf-8") as f:
                f.write(STAGED.replace("A vetted claim about something", f"claim number {i}"))
        res = ep.promote_staging_dir(staging_dir=staging, vault_engrams=vault,
                                     promoted_dir=promoted, index=False)
        self.assertEqual(res["promoted"], 3)
        self.assertEqual(len([f for f in os.listdir(vault) if f.endswith(".md")]), 3)
        self.assertEqual(len([f for f in os.listdir(staging) if f.endswith(".md")]), 0)


if __name__ == "__main__":
    unittest.main()
