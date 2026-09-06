"""Tests for the G1.33 sub-step 5 Operation-Matrix MOM layer
(orchestrator/operation_matrix.py)."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import operation_matrix as om  # noqa: E402
from orchestrator import matrix_tasks as tasks


@pytest.fixture(autouse=True)
def isolated_matrix_locks(tmp_path, monkeypatch):
    import runtime_hygiene
    monkeypatch.setattr(runtime_hygiene._rp, "DATA_DIR_STR", str(tmp_path / "runtime"))
    monkeypatch.setattr(om._rp, "DATA_DIR_STR", str(tmp_path / "runtime"))


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


class ProjectPriorityConsumerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pointer_dir = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_project(
        self,
        nexus: str,
        *,
        status: str = "active",
        priority: int | None = None,
        last_accessed_at: str,
    ) -> None:
        (self.pointer_dir / f"{nexus}.json").write_text(
            json.dumps({
                "nexus": nexus,
                "name": nexus,
                "display_name": nexus,
                "folder_name": nexus,
                "status": status,
                "priority": priority,
                "last_accessed_at": last_accessed_at,
            }),
            encoding="utf-8",
        )

    def test_active_projects_keep_canonical_priority_and_stable_nexus_order(self):
        self._write_project(
            "inactive-first", status="inactive", priority=0,
            last_accessed_at="2026-06-01T00:00:00",
        )
        self._write_project(
            "zulu-ranked", priority=1,
            last_accessed_at="2026-01-01T00:00:00",
        )
        self._write_project(
            "beta-ranked", priority=2,
            last_accessed_at="2026-07-01T00:00:00",
        )
        self._write_project(
            "zeta-recent", last_accessed_at="2026-05-01T00:00:00",
        )
        self._write_project(
            "alpha-old", last_accessed_at="2026-03-01T00:00:00",
        )
        self._write_project(
            "archived", status="archived",
            last_accessed_at="2026-08-01T00:00:00",
        )
        (self.pointer_dir / "broken.json").write_text("{not-json}", encoding="utf-8")

        skipped: list[str] = []
        rows = om.list_active_project_meta(
            self.pointer_dir, skipped_authority=skipped,
        )

        self.assertEqual(
            [row["nexus"] for row in rows],
            ["zulu-ranked", "beta-ranked", "alpha-old", "zeta-recent"],
        )
        self.assertTrue(all(row["status"] == "active" for row in rows))
        self.assertTrue(all(not row.get("is_default") for row in rows))
        self.assertEqual(skipped, ["broken.json"])


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


_PROJECTED_MATRIX = """---
nexus:
  - projected
type: matrix
project_type:
  - project
---

# Project Matrix Projected

<!-- MASTER_MATRIX_PROJECTION_START nexus=projected -->
## Mission

- **Core Essence:** Ship the thing.

## Objectives

- To build it.

## Milestones

- [ ] M1: First draft is complete.
- [x] M2: Outline is accepted.
<!-- MASTER_MATRIX_PROJECTION_END -->

## Problem Solving

Keep me.
"""

# Operations Manifest Appendix A form: prose milestones with structured
# sub-bullets, under two headings, and no `## Milestones` section at all.
_OPERATION_MATRIX = """---
nexus:
  - op-matrix
type: matrix
project_type:
  - operation
---

# Operation Matrix Op

## Mission

- **Service Statement:** Ships a daily edition.

## Objectives

- To sustain the cadence.

## Active Milestones (Recurring)

- **Milestone A1 — Cycle closes.** Each cycle ships by 9am ET.
  - Verification criterion: Cycle Close Verification.
  - P-Feasibility Verdict: Reachable
  - Status: active

## Aspirational Milestones (Maturity Gates)

- **Milestone B1:** 100 cycles shipped without missing cadence.
  - Gate condition: Performance Log shows 100 consecutive successes.

## Performance Log

Keep me.
"""

_PASSION_MATRIX = """---
nexus:
  - a-passion
type: matrix
project_type:
  - passion
---

# Passion Matrix A Passion

## Mission

- **Core Essence:** Keep learning.

## Objectives

- To read widely.

## Practices

1. Weekly reading.

## Directions of Travel

1. Toward fluency.
"""


class ProjectionMarkerTests(unittest.TestCase):
    """The Master Matrix projection block must survive an MOM edit.

    35 of the vault's matrices carry these markers; a splice that drops the
    closing marker breaks the projection's authentication for all of them.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmp.name)
        self.mdir = self.vault / "Matrix"
        self.mdir.mkdir()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, text):
        p = self.mdir / name
        p.write_bytes(text.encode("utf-8"))
        return p

    def test_end_marker_survives_milestone_write(self):
        for newline in ("\n", "\r\n"):
            for separator in (newline, newline * 2):
                with self.subTest(newline=newline, separator=separator):
                    before = _PROJECTED_MATRIX.replace("\n", newline).replace(
                        newline + "<!-- MASTER_MATRIX_PROJECTION_END",
                        separator + "<!-- MASTER_MATRIX_PROJECTION_END",
                    )
                    p = self._write("Project Matrix Projected.md", before)
                    om.write_mom(
                        "projected", "Projected",
                        milestones=[{"text": "M9: replaced.", "done": False, "indent": 0}],
                        vault=self.vault,
                    )
                    text = p.read_bytes().decode("utf-8")
                    self.assertEqual(text.count("MASTER_MATRIX_PROJECTION_START"), 1)
                    self.assertEqual(text.count("MASTER_MATRIX_PROJECTION_END"), 1)
                    self.assertIn("- [ ] M9: replaced." + separator + "<!--", text)
                    marker = "<!-- MASTER_MATRIX_PROJECTION_END"
                    self.assertEqual(text[text.index(marker):], before[before.index(marker):])

    def test_marker_never_leaks_into_the_editable_body(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=newline):
                self._write("Project Matrix Projected.md", _PROJECTED_MATRIX.replace("\n", newline))
                mom = om.read_mom("projected", "Projected", vault=self.vault)
                self.assertNotIn("MASTER_MATRIX_PROJECTION", mom["milestones_raw"])
                self.assertEqual(len(mom["milestones"]), 2)

    def test_unchanged_save_is_byte_identical(self):
        """Re-saving what was just read must not drift the file.

        Only ``date modified`` may move — every other byte, including the
        blank-line separator before the projection marker, must be preserved.
        """
        for newline in ("\n", "\r\n"):
            for separator in (newline, newline * 2):
                with self.subTest(newline=newline, separator=separator):
                    source = _PROJECTED_MATRIX.replace("\n", newline).replace(
                        newline + "<!-- MASTER_MATRIX_PROJECTION_END",
                        separator + "<!-- MASTER_MATRIX_PROJECTION_END",
                    )
                    p = self._write("Project Matrix Projected.md", source)
                    before = p.read_bytes()
                    mom = om.read_mom("projected", "Projected", vault=self.vault)
                    om.write_mom(
                        "projected", "Projected", mission=mom["mission"],
                        objectives=mom["objectives"], milestones_raw=mom["milestones_raw"],
                        vault=self.vault,
                    )
                    strip_stamp = lambda s: re.sub(rb"date modified: [0-9-]+\r?\n", b"", s)
                    self.assertEqual(strip_stamp(p.read_bytes()), strip_stamp(before))


class OperationMilestoneFormTests(unittest.TestCase):
    """Operation matrices record milestones as prose, not checkboxes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmp.name)
        self.mdir = self.vault / "Matrix"
        self.mdir.mkdir()
        (self.mdir / "Operation Matrix Op.md").write_text(
            _OPERATION_MATRIX, encoding="utf-8")
        (self.mdir / "Passion Matrix A Passion.md").write_text(
            _PASSION_MATRIX, encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_prose_milestones_are_parsed_not_empty(self):
        mom = om.read_mom("op-matrix", "Op", vault=self.vault)
        self.assertEqual(mom["milestone_form"], "operation")
        texts = [m["text"] for m in mom["milestones"]]
        self.assertTrue(any(t.startswith("Milestone A1") for t in texts), texts)
        self.assertTrue(any(t.startswith("Milestone B1") for t in texts), texts)
        # Sub-bullets are preserved as indented children.
        self.assertIn("Status: active", texts)
        self.assertTrue(
            all(m["done"] is False for m in mom["milestones"]),
            "a recurring milestone has no binary done state",
        )

    def test_write_returns_to_source_sections_without_duplicating(self):
        p = self.mdir / "Operation Matrix Op.md"
        mom = om.read_mom("op-matrix", "Op", vault=self.vault)
        om.write_mom(
            "op-matrix", "Op", milestones_raw=mom["milestones_raw"],
            vault=self.vault,
        )
        text = p.read_text(encoding="utf-8")
        # No synthetic `## Milestones` section is appended.
        self.assertNotIn("\n## Milestones", text)
        self.assertEqual(text.count("## Active Milestones (Recurring)"), 1)
        self.assertEqual(text.count("## Aspirational Milestones (Maturity Gates)"), 1)
        self.assertIn("## Performance Log\n\nKeep me.", text)

    def test_editing_a_prose_milestone_lands_in_its_own_section(self):
        p = self.mdir / "Operation Matrix Op.md"
        mom = om.read_mom("op-matrix", "Op", vault=self.vault)
        edited = mom["milestones_raw"].replace("by 9am ET", "by 7am ET")
        om.write_mom("op-matrix", "Op", milestones_raw=edited, vault=self.vault)
        text = p.read_text(encoding="utf-8")
        self.assertIn("by 7am ET", text)
        self.assertNotIn("by 9am ET", text)
        self.assertIn("Gate condition:", text)

    def test_passion_save_does_not_grow_a_milestones_section(self):
        p = self.mdir / "Passion Matrix A Passion.md"
        mom = om.read_mom("a-passion", "A Passion", vault=self.vault)
        self.assertEqual(mom["milestones_raw"], "")
        om.write_mom(
            "a-passion", "A Passion", mission=mom["mission"],
            objectives=mom["objectives"], milestones_raw=mom["milestones_raw"],
            vault=self.vault,
        )
        text = p.read_text(encoding="utf-8")
        self.assertNotIn("## Milestones", text)
        self.assertIn("## Practices", text)
        self.assertIn("## Directions of Travel", text)


    def test_empty_patch_does_not_restamp_the_file(self):
        """Opening a project and saving nothing must not churn the vault.

        The vault auto-syncs on a timer, so a gratuitous `date modified` bump
        lands as a real commit against every matrix the user merely looked at.
        """
        p = self.mdir / "Operation Matrix Op.md"
        before = p.read_text(encoding="utf-8")
        result = om.write_mom("op-matrix", "Op", vault=self.vault)
        self.assertIsNotNone(result)
        self.assertEqual(p.read_text(encoding="utf-8"), before)


class MatrixTasksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = pathlib.Path(self.tmp.name)
        (self.vault / "Matrix").mkdir()
        self.path = self.vault / "Matrix" / "Historical Name.md"

    def put(self, body, classification="project", ending="\n"):
        text = f"---\nnexus: [sample]\nproject_type: [{classification}]\ncustom: keep\ndate modified: 2001-01-01\n---\n# Example\n{body}"
        self.path.write_bytes(text.replace("\n", ending).encode())
        return self.read()

    def read(self):
        return om.read_tasks("sample", "Sample", vault=self.vault)

    def act(self, op, group=None, index=0, **values):
        group = group or self.read()
        body = {"expected_digest": group["digest"], "operation": op, **values}
        if "target" in tasks.FIELDS[op]:
            body["target"] = group["tasks"][index]["ref"]
        if op == "add" and "destination" not in body:
            body.update(destination=group["root_ref"], position="root")
        return om.write_tasks("sample", "Sample", body, vault=self.vault)

    def test_duplicate_labels_dates_and_noops_preserve_exact_surrounding_bytes(self):
        self.put("## Mission\nUntouched Ω.\n## Tasks\n\n*  [ ] Same #tag 🗓 2025-04-09\n*  [X] Same ✅ 2024-02-29\n\n<!-- literal -->\n## Notes\nKeep this.\n", ending="\r\n")
        self.path.chmod(0o640)
        before = self.path.read_bytes()
        result = self.act("edit", index=1, value="Changed **explicitly** ✅ 2024-02-29")
        self.assertTrue(result["saved"])
        self.assertIn(b"*  [ ] Same #tag", self.path.read_bytes())
        self.assertIn(b"## Notes\r\nKeep this.\r\n", self.path.read_bytes())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertNotIn(b"\n", self.path.read_bytes().replace(b"\r\n", b""))
        self.assertNotEqual(result["group"]["tasks"][0]["ref"], result["group"]["tasks"][1]["ref"])
        result = self.act("complete", index=0)
        self.assertIn("🗓 2025-04-09 ✅ " + tasks.date.today().isoformat(), result["group"]["tasks"][0]["text"])
        self.act("set-date", index=0, value="2020-02-29")
        self.assertEqual(self.read()["tasks"][0]["completion_date"], "2020-02-29")
        self.act("reopen", index=0)
        self.assertEqual(self.read()["tasks"][0]["text"], "Same #tag 🗓 2025-04-09")
        self.act("set-date", index=0, value="2025-03-01")
        self.assertFalse(self.read()["tasks"][0]["done"])
        self.act("clear-date", index=0)
        stable = self.path.read_bytes()
        with mock.patch.object(om._rp, "atomic_write_bytes", side_effect=AssertionError("no-op wrote")):
            self.assertFalse(self.act("clear-date", index=0)["changed"])
            self.assertFalse(self.act("edit", index=0, value=self.read()["tasks"][0]["text"])["changed"])
        self.assertEqual(self.path.read_bytes(), stable)
        self.assertIn(b"custom: keep\r\n", before)
        self.put("## Tasks\n- [x] Keep ✅   2024-02-29  \n")
        stable = self.path.read_bytes()
        self.assertFalse(self.act("set-date", value="2024-02-29")["changed"])
        self.assertEqual(self.path.read_bytes(), stable)

    def test_every_structure_operation_preserves_subtrees_and_attached_notes(self):
        self.put("## Tasks\n- [ ] First\n  - [ ] Child\n    continued **note**\n- [ ] Second\n- [ ] Third\n## Notes\nKeep\n")
        group = self.read()
        moved = self.act("reorder", group, destination=group["tasks"][3]["ref"], position="after")
        self.assertEqual([t["text"] for t in moved["group"]["tasks"]], ["Second", "Third", "First", "Child"])
        self.assertIn("    continued **note**", self.path.read_text())
        self.act("indent", index=2)
        self.assertEqual([t["depth"] for t in self.read()["tasks"]], [0, 0, 1, 2])
        self.act("outdent", index=3)
        self.assertEqual(self.read()["tasks"][3]["depth"], 1)
        self.act("promote", index=3)
        self.assertEqual(self.read()["tasks"][3]["depth"], 0)
        with self.assertRaisesRegex(tasks.TaskError, "attached"):
            self.act("delete", index=3)
        self.act("delete", index=0)
        group = self.read()
        added = self.act("add", group, destination=group["tasks"][0]["ref"], position="child", value="New child")
        self.assertEqual(added["group"]["tasks"][2]["text"], "New child")
        self.assertEqual(added["group"]["tasks"][2]["depth"], 1)
        self.assertIn("## Notes\nKeep\n", self.path.read_text())
        self.put("## Tasks\n- [ ] First\n- [ ] Last")
        group = self.read()
        self.act("reorder", group, index=1, destination=group["tasks"][0]["ref"], position="before")
        self.assertEqual([t["text"] for t in self.read()["tasks"]], ["Last", "First"])
        self.put("## Tasks\n- [ ] Parent\n  - [ ] Child\n  Parent continuation\n  - [ ] Sibling\n")
        self.assertEqual([t["depth"] for t in self.read()["tasks"]], [0, 1, 1])
        self.act("promote", index=1)
        self.assertIn("  Parent continuation\n  - [ ] Sibling\n- [ ] Child", self.path.read_text())

    def test_first_add_uses_full_classification_specific_strategic_section(self):
        layouts = {
            "project": "## Milestones\n- [ ] Strategic\n### Detail\nKeep\n",
            "operation": "## Active Milestones\nRecurring\n## Aspirational Milestones (Maturity Gates)\nGate\n",
            "passion": "## Practices\nPractice\n## Directions of Travel\nTravel\n",
        }
        for classification, strategic in layouts.items():
            with self.subTest(classification=classification):
                self.put(strategic + "## Notes\nKeep\n", classification)
                before = self.path.read_bytes()
                group = self.read()
                self.assertEqual(group["counts"]["total"], 0)
                self.assertEqual(self.path.read_bytes(), before)
                self.act("add", value="First task")
                text = self.path.read_text()
                self.assertIn(strategic + "\n## Tasks\n\n- [ ] First task\n\n## Notes", text)
                self.assertEqual(text.count("## Tasks"), 1)
        self.put("## Unfamiliar\nNot strategic\n", "passion")
        self.act("add", value="At EOF")
        self.assertTrue(self.path.read_text().endswith("## Tasks\n\n- [ ] At EOF\n\n"))

    def test_fences_projection_and_opaque_text_never_become_task_authority(self):
        self.put("````md\n## Tasks\n- [ ] literal\n```\n````\n~~~md\n## Tasks\n- [ ] tilde literal\n~~~\n<!-- MASTER_MATRIX_PROJECTION_START source=\"x\" -->\n## Milestones\n- [ ] Strategic\n<!-- MASTER_MATRIX_PROJECTION_END -->\n## Notes\nKeep\n")
        self.assertEqual(self.read()["counts"]["total"], 0)
        self.act("add", value="Actual")
        text = self.path.read_text()
        self.assertIn("<!-- MASTER_MATRIX_PROJECTION_END -->\n\n## Tasks", text)
        self.assertEqual([t["text"] for t in self.read()["tasks"]], ["Actual"])
        self.put("<!--\n## Tasks\n- [ ] Commented example\n-->\n## Tasks\n- [ ] Actual\n")
        self.assertEqual([t["text"] for t in self.read()["tasks"]], ["Actual"])
        self.act("edit", value="Actual changed")
        self.assertIn("- [ ] Commented example", self.path.read_text())
        for opening, closing in (("~~~markdown", "~~~"), ("````markdown", "````")):
            with self.subTest(opening=opening):
                example = f"{opening}\n<!-- MASTER_MATRIX_PROJECTION_START -->\n<!-- MASTER_MATRIX_PROJECTION_END -->\n{closing}\n"
                group = self.put("## Tasks\n- [ ] One\n\n" + example)
                self.assertTrue(group["editable"])
                self.assertEqual(group["counts"], {"total": 1, "completed": 0, "incomplete": 1})
                original = self.path.read_bytes()
                result = self.act("edit", group, value="One revised")
                self.assertTrue(result["saved"])
                self.assertEqual(result["group"]["source_text"], "- [ ] One revised\n\n" + example)
                expected = original.replace(b"- [ ] One\n", b"- [ ] One revised\n").replace(
                    b"date modified: 2001-01-01", f"date modified: {tasks.date.today().isoformat()}".encode())
                self.assertEqual(self.path.read_bytes(), expected)
        for commented in ("- [ ] Commented continuation", "Keep this note commented."):
            with self.subTest(commented=commented):
                group = self.put(f"## Tasks\n- [ ] Review MASTER_MATRIX_PROJECTION_START <!--\n{commented}\n-->\n- [ ] Visible\n")
                self.assertEqual(len(group["tasks"]), 2)
                self.assertTrue(group["editable"])
                self.assertIn("split a comment or fenced block", group["tasks"][0]["limitations"]["delete"])
                original = self.path.read_bytes()
                with self.assertRaisesRegex(tasks.TaskError, "split a comment or fenced block") as caught:
                    self.act("delete", group)
                self.assertIs(caught.exception.saved, False)
                self.assertEqual(self.path.read_bytes(), original)
                self.act("edit", value="Review draft <!--")
                completed = self.act("complete")
                self.assertTrue(completed["group"]["tasks"][0]["done"])
                self.act("reopen")
                self.act("edit", index=1, value="Still visible")
                self.act("delete", index=1)
                self.assertEqual(self.read()["source_text"], f"- [ ] Review draft <!--\n{commented}\n-->\n")
        for body in (
            "<!-- MASTER_MATRIX_PROJECTION_START -->\n## Mission\nUnclosed\n",
            "<!-- MASTER_MATRIX_PROJECTION_END -->\n",
            "## Tasks\n- [ ] One\n## TASKS\n- [ ] Two\n",
            "<!-- MASTER_MATRIX_PROJECTION_START -->\n## Tasks\n- [ ] Protected\n<!-- MASTER_MATRIX_PROJECTION_END -->\n",
            "## Tasks\n- [ ] One\n<!-- MASTER_MATRIX_PROJECTION_START -->\n<!-- MASTER_MATRIX_PROJECTION_END -->\n",
        ):
            with self.subTest(body=body):
                self.put(body)
                original = self.path.read_bytes()
                self.assertFalse(self.read()["editable"])
                if body.count("## TASKS"):
                    self.assertIn("- [ ] One", self.read()["source_text"])
                    self.assertIn("- [ ] Two", self.read()["source_text"])
                with self.assertRaises(tasks.TaskError):
                    self.act("add", value="No write")
                self.assertEqual(original, self.path.read_bytes())
        self.put("## Tasks\n- [ ] One\n\nUnattached source\n\n- [ ] Two\n")
        group = self.read()
        self.assertEqual(group["state"], "partial")
        self.assertIn("Unattached source", group["source_text"])
        with self.assertRaisesRegex(tasks.TaskError, "Unattached"):
            self.act("reorder", group, destination=group["tasks"][1]["ref"], position="after")
        self.act("edit", value="Safe text edit")

    def test_refusals_do_not_rewrite_or_drop_metadata(self):
        self.put("## Tasks\n- [ ] Parent ✅ maybe\n  - [ ] Child\n- [ ] End\n")
        for op, kwargs in (("complete", {}), ("reopen", {}), ("set-date", {"value": "2024-02-29"}),
                           ("delete", {}), ("indent", {}), ("outdent", {}), ("promote", {}),
                           ("set-date", {"value": "2023-02-29"}), ("edit", {"value": "bad\nline"})):
            with self.subTest(op=op):
                before = self.path.read_bytes()
                with self.assertRaises(tasks.TaskError):
                    self.act(op, **kwargs)
                self.assertEqual(self.path.read_bytes(), before)
        self.act("edit", value="Parent with metadata deliberately edited")
        self.act("complete")
        self.assertFalse(self.read()["tasks"][1]["done"])

    def test_stale_digest_rebound_identity_unsafe_file_and_atomic_failure(self):
        group = self.put("## Tasks\n- [ ] One\n")
        self.path.write_bytes(self.path.read_bytes() + b"external\n")
        with self.assertRaisesRegex(tasks.TaskError, "changed"):
            self.act("edit", group, value="Lost edit")
        group = self.read()
        original = self.path.read_bytes()
        with mock.patch.object(om._rp, "atomic_write_bytes", side_effect=OSError("replace failed")):
            with self.assertRaises(tasks.TaskError) as caught:
                self.act("edit", value="Failed")
        self.assertIs(caught.exception.saved, False)
        self.assertEqual(self.path.read_bytes(), original)
        rebound = self.path.with_name("Rebound.md")
        self.path.rename(rebound)
        with self.assertRaises(tasks.TaskError) as caught:
            self.act("edit", group, value="Wrong identity")
        self.assertEqual(caught.exception.code, "conflict")
        outside = self.vault / "Outside.md"
        rebound.rename(outside)
        rebound = outside
        self.path.symlink_to(rebound)
        self.assertEqual(self.read()["state"], "unavailable")
        self.path.unlink()
        rebound.rename(self.path)
        self.path.chmod(0o400)
        self.assertEqual(self.read()["state"], "read-only")

    def test_shared_resolution_detects_duplicates_in_one_pass(self):
        self.path = self.path.with_name("Operation Matrix Sample.md")
        self.put("## Mission\nKeep this mission.\n## Tasks\n- [ ] One\n")
        other = self.path.with_name("Other.md")
        other.write_text("---\nnexus: [other]\n---\n")
        snapshots = om.resolve_matrix_snapshots({"sample": "Sample", "other": "Other", "commons": None}, vault=self.vault)
        self.assertEqual(snapshots["sample"][0], self.path)
        self.assertEqual(snapshots["other"][0], other)
        self.assertIsNone(snapshots["commons"])
        (self.path.parent / "Malformed.md").write_text("---\nnexus: [broken]\ndate modified: 2026-99-99\n---\n")
        self.assertEqual(om.resolve_matrix_snapshots({"sample": "Sample"}, vault=self.vault)["sample"][0], self.path)
        candidate = self.path.with_name("Project Matrix Sample.md")
        for entry in ("directory", "symlink"):
            with self.subTest(entry=entry):
                if entry == "directory":
                    candidate.mkdir()
                else:
                    candidate.symlink_to(other)
                resolved = om.resolve_matrix_snapshots({"sample": "Sample", "other": "Other", "missing": "Missing"}, vault=self.vault)
                self.assertEqual(resolved["sample"], snapshots["sample"])
                self.assertEqual(resolved["other"], snapshots["other"])
                self.assertIsNone(resolved["missing"])
                self.assertEqual(om.resolve_matrix_path("sample", "Sample", vault=self.vault), self.path)
                self.assertEqual(self.read()["state"], "ready")
                self.assertEqual(om.read_mom("sample", "Sample", vault=self.vault)["mission"], "Keep this mission.")
                self.assertIsInstance(om.resolve_matrix_snapshots({"unknown": "Sample"}, vault=self.vault)["unknown"], om.MatrixError)
                if entry == "directory":
                    candidate.rmdir()
                else:
                    candidate.unlink()
        other.write_bytes(self.path.read_bytes())
        duplicate = om.resolve_matrix_snapshots({"sample": "Sample"}, vault=self.vault)["sample"]
        self.assertIsInstance(duplicate, om.MatrixAmbiguityError)

    def test_mom_save_holds_same_lock_and_preserves_concurrent_task_edit(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        import runtime_hygiene
        self.put("## Mission\nOriginal\n## Tasks\n- [ ] One\n")
        entered, release = threading.Event(), threading.Event()
        original = om._rp.atomic_write_bytes
        def paused_write(path, payload, **kwargs):
            if b"Task changed" in payload and b"Mission changed" not in payload:
                entered.set()
                self.assertTrue(release.wait(3))
            return original(path, payload, **kwargs)
        with mock.patch.object(om._rp, "atomic_write_bytes", side_effect=paused_write), ThreadPoolExecutor(max_workers=2) as pool:
            task_future = pool.submit(self.act, "edit", value="Task changed")
            self.assertTrue(entered.wait(3))
            mom_future = pool.submit(om.write_mom, "sample", "Sample", mission="Mission changed", vault=self.vault)
            release.set()
            self.assertTrue(task_future.result(timeout=5)["saved"])
            self.assertIsNotNone(mom_future.result(timeout=5))
        text = self.path.read_text()
        self.assertIn("Task changed", text)
        self.assertIn("Mission changed", text)


class NewMatrixTemplateTests(unittest.TestCase):
    def test_created_matrix_is_writable_by_the_gate(self):
        """A matrix Ora creates must not fail Ora's own MOM write gate."""
        from orchestrator.matrix_classifier import classify_matrix, schema_valid
        text = om._new_matrix_text("fresh", "Fresh")
        fm, _ = om._split_frontmatter(text)
        self.assertEqual(classify_matrix(fm, "Project Matrix Fresh.md")[0], "project")
        self.assertTrue(schema_valid(fm))


if __name__ == "__main__":
    unittest.main()
