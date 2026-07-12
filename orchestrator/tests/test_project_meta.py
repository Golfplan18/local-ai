"""Tests for the G1.33 project-record layer (orchestrator/project_meta.py)."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
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
        self.assertEqual(meta["folder_name"], "My Book")
        self.assertIsNotNone(meta["created"])
        again = pm.read_project_meta("my-book", pointer_dir=self.d)
        self.assertEqual(again["name"], "My Book")

    def test_display_name_change_preserves_immutable_folder(self):
        pm.create_project("My Book", pointer_dir=self.d)
        changed = pm.update_project_meta(
            "my-book",
            {"name": "Book of Law", "folder_name": "Should Not Move"},
            pointer_dir=self.d,
        )
        self.assertEqual(changed["name"], "Book of Law")
        self.assertEqual(changed["folder_name"], "My Book")
        raw = json.loads((self.d / "my-book.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["name"], "My Book")
        self.assertEqual(raw["display_name"], "Book of Law")
        self.assertEqual(raw["folder_name"], "My Book")

    def test_legacy_name_change_freezes_old_folder_before_mutation(self):
        (self.d / "legacy.json").write_text(
            json.dumps({"nexus": "legacy", "name": "Legacy Folder"}),
            encoding="utf-8",
        )
        changed = pm.update_project_meta(
            "legacy", {"name": "New Label"}, pointer_dir=self.d
        )
        self.assertEqual(changed["name"], "New Label")
        self.assertEqual(changed["folder_name"], "Legacy Folder")
        raw = json.loads((self.d / "legacy.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["name"], "Legacy Folder")
        self.assertEqual(raw["display_name"], "New Label")
        self.assertEqual(raw["folder_name"], "Legacy Folder")

    def test_rollback_reader_keeps_folder_and_current_display_remains_authoritative(self):
        pm.create_project("My Book", pointer_dir=self.d)
        pm.update_project_meta(
            "my-book", {"name": "Book of Law"}, pointer_dir=self.d
        )
        pointer = self.d / "my-book.json"
        rolled_back = json.loads(pointer.read_text(encoding="utf-8"))

        # The prior release knows only `name`; immediately after rollback it
        # therefore continues deriving the original folder.
        self.assertEqual(rolled_back["name"], "My Book")
        self.assertEqual(rolled_back["folder_name"], "My Book")

        # Rewriting that same legacy value (including an attempted rename back
        # to the original label) carries no semantic signal that can safely
        # override the additive display-only field.
        pointer.write_text(json.dumps(rolled_back), encoding="utf-8")
        self.assertEqual(
            pm.read_project_meta("my-book", pointer_dir=self.d)["name"],
            "Book of Law",
        )

        # Simulate an unsafe display-name edit made by that prior release. It
        # cannot distinguish display label from folder identity. On the next
        # forward upgrade, current code restores the folder-bearing field and
        # retains the additive current display label rather than guessing.
        rolled_back["name"] = "Legacy Edited Label"
        pointer.write_text(json.dumps(rolled_back), encoding="utf-8")

        current = pm.read_project_meta("my-book", pointer_dir=self.d)
        repaired = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertEqual(current["name"], "Book of Law")
        self.assertEqual(current["folder_name"], "My Book")
        self.assertEqual(repaired["name"], "My Book")
        self.assertEqual(repaired["display_name"], "Book of Law")
        self.assertEqual(repaired["folder_name"], "My Book")

    def test_startup_folder_migration_is_idempotent_and_preserves_plugin_fields(self):
        pointer = self.d / "legacy.json"
        pointer.write_text(
            json.dumps({
                "nexus": "legacy",
                "name": "Legacy Folder",
                "root": "/plugin/root",
                "future_field": {"kept": True},
            }),
            encoding="utf-8",
        )

        self.assertEqual(pm.migrate_project_folder_names(self.d), 1)
        self.assertEqual(pm.migrate_project_folder_names(self.d), 0)
        raw = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertEqual(raw["name"], "Legacy Folder")
        self.assertEqual(raw["display_name"], "Legacy Folder")
        self.assertEqual(raw["folder_name"], "Legacy Folder")
        self.assertEqual(raw["root"], "/plugin/root")
        self.assertEqual(raw["future_field"], {"kept": True})

    def test_startup_folder_migration_leaves_pure_plugin_pointer_minimal(self):
        pointer = self.d / "plugin-only.json"
        original = {"nexus": "plugin-only", "root": "/plugin/root"}
        pointer.write_text(json.dumps(original), encoding="utf-8")

        self.assertEqual(pm.migrate_project_folder_names(self.d), 0)
        self.assertEqual(json.loads(pointer.read_text(encoding="utf-8")), original)

    def test_pointer_stores_follow_relocated_ora_home(self):
        relocated = self.d / "relocated ora"
        env = os.environ.copy()
        env["ORA_HOME"] = str(relocated)
        env["PYTHONPATH"] = _REPO
        script = (
            "from orchestrator import active_project, project_meta, project_registry; "
            "print(active_project.DATA_DIR); print(project_meta.POINTER_DIR); "
            "print(project_registry.POINTER_DIR)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=_REPO,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        lines = result.stdout.strip().splitlines()
        expected_data = relocated / "data"
        expected_projects = expected_data / "projects"
        self.assertEqual(pathlib.Path(lines[0]), expected_data)
        self.assertEqual(pathlib.Path(lines[1]), expected_projects)
        self.assertEqual(pathlib.Path(lines[2]), expected_projects)

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

    def test_deprecated_aliases_remain_import_compatible(self):
        self.assertEqual(pm.GENERAL_NEXUS, "general")
        self.assertEqual(pm.general_meta(), pm.default_project_meta())
        self.assertEqual(pm.general_meta()["nexus"], "commons")

    def test_default_inputs_are_canonicalized(self):
        for nexus in (" General ", "COMMONS", " commons "):
            self.assertEqual(
                pm.read_project_meta(nexus, pointer_dir=self.d)["nexus"],
                "commons",
            )

    def test_reserved_pointer_files_never_duplicate_commons(self):
        for nexus in ("commons", "general"):
            (self.d / f"{nexus}.json").write_text(
                json.dumps({"nexus": nexus, "name": f"stale {nexus}", "root": "/x"}),
                encoding="utf-8",
            )
        listed = pm.list_project_meta(pointer_dir=self.d)
        self.assertEqual([m["nexus"] for m in listed], ["commons"])
        self.assertEqual(listed[0]["name"], "Commons")
        self.assertFalse(listed[0]["is_plugin"])

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
        for traversal in (".", ".."):
            safe = pm.ensure_project_folder(traversal, vault_projects_dir=proj_dir)
            self.assertEqual(safe, proj_dir / "Untitled")

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

    def test_list_commons_files_uses_only_direct_vault_root_files(self):
        vault = self.d / "vault"
        projects_dir = vault / "Projects"
        project_folder = projects_dir / "My Book"
        project_folder.mkdir(parents=True)
        (vault / "commons-output.md").write_text("root", encoding="utf-8")
        (project_folder / "project-output.md").write_text("project", encoding="utf-8")

        idx = pm.list_project_files(None, vault_projects_dir=projects_dir)

        self.assertTrue(idx["exists"])
        self.assertTrue(idx["is_vault_root"])
        self.assertEqual(pathlib.Path(idx["folder"]), vault)
        self.assertEqual({f["name"] for f in idx["files"]}, {"commons-output.md"})

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
