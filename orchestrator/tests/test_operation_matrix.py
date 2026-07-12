"""Tests for the G1.33 sub-step 5 Operation-Matrix MOM layer
(orchestrator/operation_matrix.py)."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import operation_matrix as om  # noqa: E402


# A realistic matrix file: MOM sections plus a Bases query + a registry table
# that MUST survive an MOM edit byte-for-byte.
_RICH_MATRIX = """---
nexus:
  - my-book
type: matrix
hub: "030"
date created: 2025-02-07
date modified: 2025-09-12
---

# Project Matrix My Book

## Mission

Tell a story that matters.

## Objectives

- Finish the draft.

## Milestones

- [x] Outline ✅ 2025-02-20
- [ ] Draft chapter 1
\t- [ ] Scene A
- [ ] Draft chapter 2

## Projects

```base
filters:
  and:
    - type == "matrix"
    - nexus == "my-book"
```

## Spawned Activity Registry

| Name | Type | Relation | Status | Notes |
|---|---|---|---|---|
"""


class OperationMatrixReadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        self.mdir = self.vault / "Matrix"
        self.mdir.mkdir()
        (self.mdir / "Project Matrix My Book.md").write_text(
            _RICH_MATRIX, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_resolve_by_name(self):
        p = om.resolve_matrix_path("my-book", "My Book", vault=self.vault)
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "Project Matrix My Book.md")

    def test_resolve_by_frontmatter_nexus(self):
        # Name mismatch → falls through to the frontmatter scan.
        p = om.resolve_matrix_path("my-book", "Different Name", vault=self.vault)
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "Project Matrix My Book.md")

    def test_convention_candidate_must_belong_to_requested_nexus(self):
        self.assertIsNone(
            om.resolve_matrix_path("other", "My Book", vault=self.vault)
        )

    def test_duplicate_nexus_claims_raise_typed_ambiguity(self):
        (self.mdir / "Project Matrix Duplicate.md").write_text(
            _RICH_MATRIX.replace("# Project Matrix My Book", "# Duplicate"),
            encoding="utf-8",
        )
        with self.assertRaises(om.MatrixAmbiguityError):
            om.resolve_matrix_path("my-book", "My Book", vault=self.vault)

    def test_resolve_missing(self):
        self.assertIsNone(om.resolve_matrix_path("ghost", "Ghost", vault=self.vault))
        self.assertIsNone(om.resolve_matrix_path("commons", "Commons", vault=self.vault))

    def test_resolve_missing_legacy_general(self):
        self.assertIsNone(om.resolve_matrix_path("general", "General", vault=self.vault))

    def test_read_mom(self):
        mom = om.read_mom("my-book", "My Book", vault=self.vault)
        self.assertTrue(mom["exists"])
        self.assertEqual(mom["mission"], "Tell a story that matters.")
        self.assertIn("Finish the draft.", mom["objectives"])
        self.assertEqual(len(mom["milestones"]), 4)
        self.assertEqual(mom["milestones"][0]["text"], "Outline ✅ 2025-02-20")
        self.assertTrue(mom["milestones"][0]["done"])
        self.assertFalse(mom["milestones"][1]["done"])
        self.assertEqual(mom["milestones"][2]["indent"], 1)  # the tabbed sub-task

    def test_read_missing_returns_empty(self):
        mom = om.read_mom("ghost", "Ghost", vault=self.vault)
        self.assertFalse(mom["exists"])
        self.assertEqual(mom["mission"], "")
        self.assertEqual(mom["milestones"], [])


class OperationMatrixWriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        self.mdir = self.vault / "Matrix"
        self.mdir.mkdir()
        self.path = self.mdir / "Project Matrix My Book.md"
        self.path.write_text(_RICH_MATRIX, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_mission_preserves_rest(self):
        om.write_mom("my-book", "My Book", mission="A new mission.", vault=self.vault)
        text = self.path.read_text(encoding="utf-8")
        # Edited section updated.
        self.assertIn("## Mission\n\nA new mission.", text)
        self.assertNotIn("Tell a story that matters.", text)
        # Untouched content survives byte-for-byte.
        self.assertIn('- type == "matrix"', text)
        self.assertIn("## Spawned Activity Registry", text)
        self.assertIn("| Name | Type | Relation | Status | Notes |", text)
        # Objectives + milestones untouched.
        self.assertIn("Finish the draft.", text)
        self.assertIn("- [ ] Draft chapter 1", text)

    def test_write_milestones_structured(self):
        om.write_mom(
            "my-book", "My Book",
            milestones=[
                {"text": "Done thing", "done": True, "indent": 0},
                {"text": "Sub thing", "done": False, "indent": 1},
            ],
            vault=self.vault,
        )
        mom = om.read_mom("my-book", "My Book", vault=self.vault)
        self.assertEqual(len(mom["milestones"]), 2)
        self.assertTrue(mom["milestones"][0]["done"])
        self.assertEqual(mom["milestones"][1]["indent"], 1)
        # Mission untouched.
        self.assertEqual(mom["mission"], "Tell a story that matters.")

    def test_write_milestones_raw_wins(self):
        om.write_mom(
            "my-book", "My Book",
            milestones=[{"text": "ignored", "done": False}],
            milestones_raw="- [ ] Raw one\n- [x] Raw two",
            vault=self.vault,
        )
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("- [ ] Raw one", text)
        self.assertIn("- [x] Raw two", text)
        self.assertNotIn("ignored", text)

    def test_bump_modified(self):
        om.write_mom("my-book", "My Book", mission="x", vault=self.vault)
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("date modified: 2025-09-12", text)
        self.assertRegex(text, r"date modified: \d{4}-\d{2}-\d{2}")

    def test_create_if_missing(self):
        mom = om.write_mom(
            "fresh-proj", "Fresh Proj",
            display_name='Fresh: A "Project"?',
            mission="Begin.", objectives="Ship it.",
            milestones=[{"text": "step one", "done": False}],
            vault=self.vault,
        )
        self.assertIsNotNone(mom)
        created = self.mdir / "Project Matrix Fresh Proj.md"
        self.assertTrue(created.is_file())
        text = created.read_text(encoding="utf-8")
        self.assertIn("type: matrix", text)
        self.assertIn("nexus:\n  - fresh-proj", text)
        self.assertIn('# Project Matrix Fresh: A "Project"?', text)
        self.assertIn("## Mission\n\nBegin.", text)
        self.assertIn("## Objectives\n\nShip it.", text)
        self.assertIn("- [ ] step one", text)

    def test_create_refuses_convention_collision_owned_by_another_nexus(self):
        collision = self.mdir / "Project Matrix Taken.md"
        collision.write_text(
            "---\nnexus:\n  - other\ntype: matrix\n---\n",
            encoding="utf-8",
        )
        with self.assertRaises(om.MatrixMigrationRequiredError):
            om.write_mom(
                "taken", "Taken", display_name="Taken", mission="x",
                vault=self.vault,
            )
        self.assertIn("  - other", collision.read_text(encoding="utf-8"))

    def test_missing_vault_is_not_created(self):
        missing = self.vault / "not-a-vault"
        self.assertIsNone(om.write_mom(
            "ghost", "Ghost", display_name="Ghost", mission="x", vault=missing,
        ))
        self.assertFalse(missing.exists())

    def test_invalid_persisted_component_requires_migration(self):
        with self.assertRaises(om.MatrixMigrationRequiredError):
            om.write_mom(
                "legacy", "CON.txt", display_name="Legacy", mission="x",
                vault=self.vault,
            )

    def test_commons_is_noop(self):
        self.assertIsNone(om.write_mom("commons", "Commons", mission="x", vault=self.vault))

    def test_legacy_general_is_noop(self):
        self.assertIsNone(om.write_mom("general", "General", mission="x", vault=self.vault))

    def test_no_create_when_disabled(self):
        self.assertIsNone(om.write_mom(
            "ghost", "Ghost", mission="x", create_if_missing=False, vault=self.vault))

    def test_insert_missing_section(self):
        # A matrix with only Mission; writing Objectives must insert it in order
        # (before Projects), not clobber Mission or Projects.
        partial = (
            "---\nnexus:\n  - partial\ntype: matrix\n---\n\n"
            "# Project Matrix Partial\n\n## Mission\n\nM.\n\n## Projects\n\nP.\n"
        )
        p = self.mdir / "Project Matrix Partial.md"
        p.write_text(partial, encoding="utf-8")
        om.write_mom("partial", "Partial", objectives="New objs.", vault=self.vault)
        text = p.read_text(encoding="utf-8")
        self.assertIn("## Objectives\n\nNew objs.", text)
        self.assertIn("## Mission\n\nM.", text)
        self.assertIn("## Projects\n\nP.", text)
        # Objectives sits between Mission and Projects.
        self.assertLess(text.index("## Mission"), text.index("## Objectives"))
        self.assertLess(text.index("## Objectives"), text.index("## Projects"))


if __name__ == "__main__":
    unittest.main()
