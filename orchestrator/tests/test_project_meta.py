"""Tests for the G1.33 project-record layer (orchestrator/project_meta.py)."""

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

from orchestrator import project_meta as pm  # noqa: E402


class ProjectMetaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_slugify(self):
        self.assertEqual(pm.slugify_nexus("My Book Project"), "my-book-project")
        self.assertEqual(pm.slugify_nexus("  Hello!! World  "), "hello-world")
        self.assertEqual(pm.slugify_nexus("already-kebab"), "already-kebab")

    def test_create_and_read(self):
        meta = pm.create_project("My Book", pointer_dir=self.d)
        self.assertEqual(meta["nexus"], "my-book")
        self.assertEqual(meta["name"], "My Book")
        self.assertEqual(meta["status"], "active")
        self.assertFalse(meta["is_default"])
        self.assertIsNotNone(meta["created"])
        again = pm.read_project_meta("my-book", pointer_dir=self.d)
        self.assertEqual(again["name"], "My Book")

    def test_create_reserved_and_collision(self):
        with self.assertRaises(pm.ProjectMetaError):
            pm.create_project("General", pointer_dir=self.d)  # legacy reserved word
        with self.assertRaises(pm.ProjectMetaError):
            pm.create_project("Commons", pointer_dir=self.d)  # canonical reserved word
        pm.create_project("Book", pointer_dir=self.d)
        with self.assertRaises(pm.ProjectMetaError):
            pm.create_project("Book", pointer_dir=self.d)

    def test_commons_is_synthetic_default(self):
        g = pm.read_project_meta("commons", pointer_dir=self.d)
        self.assertEqual(g["nexus"], "commons")
        self.assertTrue(g["is_default"])
        # Never written to disk.
        self.assertFalse((self.d / "commons.json").exists())

    def test_legacy_general_resolves_to_commons(self):
        # Permanent backward compatibility, not a one-time migration.
        g = pm.read_project_meta("general", pointer_dir=self.d)
        self.assertEqual(g["nexus"], "commons")
        self.assertTrue(g["is_default"])
        self.assertFalse((self.d / "general.json").exists())

    def test_read_missing_returns_none(self):
        self.assertIsNone(pm.read_project_meta("nope", pointer_dir=self.d))

    def test_list_commons_first_and_recency_desc(self):
        pm.create_project("Alpha", pointer_dir=self.d)
        pm.create_project("Beta", pointer_dir=self.d)
        # Explicit, distinct recency so the sort is deterministic.
        (self.d / "alpha.json").write_text(
            json.dumps({"nexus": "alpha", "name": "Alpha", "status": "active",
                        "last_accessed_at": "2026-06-28T10:00:00"}), encoding="utf-8")
        (self.d / "beta.json").write_text(
            json.dumps({"nexus": "beta", "name": "Beta", "status": "active",
                        "last_accessed_at": "2026-06-27T10:00:00"}), encoding="utf-8")
        lst = pm.list_project_meta(pointer_dir=self.d)
        self.assertEqual(lst[0]["nexus"], "commons")
        nexuses = [m["nexus"] for m in lst]
        self.assertLess(nexuses.index("alpha"), nexuses.index("beta"))

    def test_set_status(self):
        pm.create_project("Book", pointer_dir=self.d)
        m = pm.set_project_status("book", "archived", pointer_dir=self.d)
        self.assertEqual(m["status"], "archived")
        with self.assertRaises(pm.ProjectMetaError):
            pm.set_project_status("book", "bogus", pointer_dir=self.d)

    def test_touch_sets_last_accessed(self):
        pm.create_project("Book", pointer_dir=self.d)
        m = pm.touch_project("book", pointer_dir=self.d)
        self.assertIsNotNone(m["last_accessed_at"])
        self.assertIsNone(pm.touch_project("ghost", pointer_dir=self.d))

    def test_plugin_pointer_normalized(self):
        # A plugin-style pointer (root, no name) reads as a project with
        # name == nexus and is_plugin True — the "unify" coexistence.
        (self.d / "msi.json").write_text(
            json.dumps({"nexus": "msi", "root": "/x"}), encoding="utf-8")
        m = pm.read_project_meta("msi", pointer_dir=self.d)
        self.assertEqual(m["name"], "msi")
        self.assertTrue(m["is_plugin"])
        self.assertEqual(m["status"], "active")

    def test_update_project_meta(self):
        pm.create_project("Book", pointer_dir=self.d)
        m = pm.update_project_meta(
            "book", {"name": "Book of Law", "private": True, "bogus": 1},
            pointer_dir=self.d)
        self.assertEqual(m["name"], "Book of Law")
        self.assertTrue(m["private"])
        raw = json.loads((self.d / "book.json").read_text())
        self.assertNotIn("bogus", raw)  # unknown field ignored

    def test_update_invalid_and_missing(self):
        pm.create_project("Book", pointer_dir=self.d)
        with self.assertRaises(pm.ProjectMetaError):
            pm.update_project_meta("book", {"status": "bogus"}, pointer_dir=self.d)
        with self.assertRaises(pm.ProjectMetaError):
            pm.update_project_meta("book", {"name": "  "}, pointer_dir=self.d)
        self.assertIsNone(
            pm.update_project_meta("ghost", {"name": "x"}, pointer_dir=self.d))

    def test_ensure_project_folder(self):
        proj_dir = self.d / "vault-projects"
        folder = pm.ensure_project_folder("My Book", vault_projects_dir=proj_dir)
        self.assertIsNotNone(folder)
        self.assertTrue(folder.is_dir())
        self.assertEqual(folder.name, "My Book")
        f2 = pm.ensure_project_folder("a/b", vault_projects_dir=proj_dir)
        self.assertTrue(f2.is_dir())
        self.assertNotIn("/", f2.name)

    def test_list_project_files_missing_folder(self):
        idx = pm.list_project_files("Nope", vault_projects_dir=self.d / "vp")
        self.assertFalse(idx["exists"])
        self.assertEqual(idx["files"], [])

    def test_list_project_files(self):
        proj_dir = self.d / "vp"
        folder = pm.ensure_project_folder("My Book", vault_projects_dir=proj_dir)
        (folder / "draft.md").write_text("hi", encoding="utf-8")
        sub = folder / "notes"
        sub.mkdir()
        (sub / "ideas.md").write_text("x", encoding="utf-8")
        # Skipped junk.
        (folder / ".DS_Store").write_text("", encoding="utf-8")
        idx = pm.list_project_files("My Book", vault_projects_dir=proj_dir)
        self.assertTrue(idx["exists"])
        names = {f["name"] for f in idx["files"]}
        self.assertEqual(names, {"draft.md", "ideas.md"})
        rels = {f["rel_path"] for f in idx["files"]}
        self.assertIn(os.path.join("notes", "ideas.md"), rels)

    def test_list_project_files_truncation(self):
        proj_dir = self.d / "vp"
        folder = pm.ensure_project_folder("Big", vault_projects_dir=proj_dir)
        for i in range(5):
            (folder / f"f{i}.md").write_text("x", encoding="utf-8")
        idx = pm.list_project_files("Big", vault_projects_dir=proj_dir, max_files=3)
        self.assertEqual(len(idx["files"]), 3)
        self.assertTrue(idx["truncated"])


if __name__ == "__main__":
    unittest.main()
