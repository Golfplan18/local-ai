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

    def test_register_existing_container_project_adopts_folder_with_custom_nexus(self):
        projects = self.d / "Projects"
        (projects / "We Too").mkdir(parents=True)
        meta = pm.register_existing_container_project(
            "wetoo",
            "We Too",
            "We Too",
            pointer_dir=self.d / "pointers",
            vault_projects_dir=projects,
        )
        self.assertEqual(meta["nexus"], "wetoo")
        self.assertEqual(meta["name"], "We Too")
        self.assertEqual(meta["folder_name"], "We Too")
        raw = json.loads((self.d / "pointers" / "wetoo.json").read_text(encoding="utf-8"))
        self.assertNotIn("root", raw)
        self.assertEqual(raw["folder_name"], "We Too")

        again = pm.register_existing_container_project(
            "wetoo",
            "We Too",
            "We Too",
            pointer_dir=self.d / "pointers",
            vault_projects_dir=projects,
        )
        self.assertEqual(again["folder_name"], "We Too")

    def test_register_existing_container_project_preserves_plugin_and_unknown_fields(self):
        projects = self.d / "Projects"
        (projects / "Main Street Independent").mkdir(parents=True)
        pointers = self.d / "pointers"
        pointers.mkdir()
        (pointers / "main-street-independent.json").write_text(
            json.dumps({
                "nexus": "main-street-independent",
                "root": "/plugin/root",
                "future": {"kept": True},
            }),
            encoding="utf-8",
        )

        pm.register_existing_container_project(
            "main-street-independent",
            "Main Street Independent",
            "Main Street Independent",
            pointer_dir=pointers,
            vault_projects_dir=projects,
        )
        raw = json.loads((pointers / "main-street-independent.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["root"], "/plugin/root")
        self.assertEqual(raw["future"], {"kept": True})
        self.assertEqual(raw["folder_name"], "Main Street Independent")

    def test_register_existing_container_project_rejects_conflicts(self):
        projects = self.d / "Projects"
        (projects / "American King").mkdir(parents=True)
        (projects / "Other Folder").mkdir()
        pointers = self.d / "pointers"
        pointers.mkdir()
        pm.register_existing_container_project(
            "american_king",
            "American King",
            "American King",
            pointer_dir=pointers,
            vault_projects_dir=projects,
        )
        with self.assertRaises(pm.ProjectMetaError):
            pm.register_existing_container_project(
                "american_king",
                "American King",
                "Other Folder",
                pointer_dir=pointers,
                vault_projects_dir=projects,
            )
        with self.assertRaises(pm.ProjectMetaError):
            pm.register_existing_container_project(
                "ai_writing_method",
                "AI Assisted Writing",
                "AI Assisted Writing",
                pointer_dir=pointers,
                vault_projects_dir=projects,
            )

    def test_register_existing_container_project_rejects_folder_owned_by_other_nexus(self):
        projects = self.d / "Projects"
        (projects / "Shared").mkdir(parents=True)
        (projects / "shared").mkdir(exist_ok=True)
        pointers = self.d / "pointers"

        pm.register_existing_container_project(
            "alpha", "Alpha", "Shared",
            pointer_dir=pointers, vault_projects_dir=projects,
        )
        with self.assertRaises(pm.ProjectMetaError):
            pm.register_existing_container_project(
                "beta", "Beta", "Shared",
                pointer_dir=pointers, vault_projects_dir=projects,
            )

    def test_register_existing_container_project_rejects_case_insensitive_folder_collision(self):
        projects = self.d / "Projects"
        (projects / "Shared").mkdir(parents=True)
        pointers = self.d / "pointers"

        pm.register_existing_container_project(
            "alpha", "Alpha", "Shared",
            pointer_dir=pointers, vault_projects_dir=projects,
        )
        with self.assertRaises(pm.ProjectMetaError):
            pm.register_existing_container_project(
                "beta", "Beta", "shared",
                pointer_dir=pointers, vault_projects_dir=projects,
            )

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
        unchanged = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertEqual(current["name"], "Book of Law")
        self.assertEqual(current["folder_name"], "My Book")
        # Reads are pure even when the compatibility fields disagree.
        self.assertEqual(unchanged["name"], "Legacy Edited Label")
        self.assertEqual(unchanged["folder_name"], "My Book")

        # The explicit startup schema expansion repairs only the rollback field;
        # it does not transform the persisted folder identity.
        self.assertEqual(pm.migrate_project_folder_names(self.d), 1)
        repaired = json.loads(pointer.read_text(encoding="utf-8"))
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

    def test_central_nexus_policy_length_and_windows_devices(self):
        self.assertEqual(pm.validate_nexus("a" * 64), "a" * 64)
        for bad in ("a" * 65, "commons", "general", "con", "COM1", "lpt9"):
            with self.subTest(bad=bad):
                with self.assertRaises(pm.NexusValidationError):
                    pm.validate_nexus(bad)

    def test_legacy_invalid_nexus_can_be_remediation_source(self):
        self.assertEqual(pm.validate_existing_nexus_source("con"), "con")
        self.assertEqual(pm.validate_existing_nexus_source("a" * 65), "a" * 65)
        for bad in ("commons", "general", "../escape", "Bad"):
            with self.subTest(bad=bad):
                with self.assertRaises(pm.NexusValidationError):
                    pm.validate_existing_nexus_source(bad)

    def test_read_present_folder_identity_is_exact_and_pure(self):
        pointer = self.d / "portable-read.json"
        raw = {
            "nexus": "portable-read",
            "name": "Legacy Edited",
            "display_name": "Visible",
            "folder_name": "Already:Persisted. ",
        }
        pointer.write_text(json.dumps(raw), encoding="utf-8")
        before = pointer.read_bytes()

        meta = pm.read_project_meta("portable-read", pointer_dir=self.d)

        self.assertEqual(meta["name"], "Visible")
        self.assertEqual(meta["folder_name"], "Already:Persisted. ")
        self.assertEqual(pointer.read_bytes(), before)

    def test_portable_folder_allocator_and_casefold_collision(self):
        projects = self.d / "vault" / "Projects"
        projects.mkdir(parents=True)
        first = pm.allocate_folder_name(
            '  CON<>:"/\\|?*\x01.  ', "first",
            pointer_dir=self.d / "pointers", vault_projects_dir=projects,
        )
        self.assertTrue(first.startswith("_CON"))
        self.assertNotRegex(first, r'[<>:"/\\|?*\x00-\x1f]')
        self.assertFalse(first.endswith((" ", ".")))

        (projects / "My Book").mkdir()
        second = pm.allocate_folder_name(
            "my book", "other",
            pointer_dir=self.d / "pointers", vault_projects_dir=projects,
        )
        self.assertEqual(second, "my book -- d9298a10")

    def test_portable_collision_key_catches_unicode_equivalence(self):
        projects = self.d / "vault" / "Projects"
        projects.mkdir(parents=True)
        (projects / "Cafe\u0301").mkdir()

        allocated = pm.allocate_folder_name(
            "Caf\u00e9", "other",
            pointer_dir=self.d / "pointers", vault_projects_dir=projects,
        )

        self.assertEqual(allocated, "Caf\u00e9 -- d9298a10")

    def test_collision_hash_suffix_stays_bounded_for_maximum_nexus(self):
        projects = self.d / "vault" / "Projects"
        projects.mkdir(parents=True)
        (projects / "Same").mkdir()
        nexus = "a" * pm.MAX_NEXUS_LENGTH

        allocated = pm.allocate_folder_name(
            "Same", nexus,
            pointer_dir=self.d / "pointers", vault_projects_dir=projects,
        )

        self.assertRegex(allocated, r"^Same -- [0-9a-f]{8}$")
        self.assertLessEqual(pm._utf16_units(allocated), pm.MAX_FOLDER_COMPONENT_UNITS)

    def test_folder_allocator_enforces_utf16_and_full_path_budget(self):
        projects = self.d / "vault" / "Projects"
        projects.mkdir(parents=True)
        allocated = pm.allocate_folder_name(
            "😀" * 100, "emoji",
            pointer_dir=self.d / "pointers", vault_projects_dir=projects,
        )
        self.assertLessEqual(pm._utf16_units(allocated), pm.MAX_FOLDER_COMPONENT_UNITS)

        deep = self.d / ("d" * 100) / ("e" * 100) / "Projects"
        with self.assertRaises(pm.ProjectStorageError):
            pm.allocate_folder_name(
                "Project", "project",
                pointer_dir=self.d / "pointers", vault_projects_dir=deep,
            )

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
        for invalid in ("a/b", ".", ".."):
            with self.subTest(invalid=invalid):
                with self.assertRaises(pm.ProjectStorageError):
                    pm.ensure_project_folder(invalid, vault_projects_dir=proj_dir)

    def test_project_folder_path_is_exact_not_resanitized(self):
        projects = self.d / "Projects"
        self.assertEqual(
            pm.project_folder_path("Exact Name", projects),
            projects / "Exact Name",
        )
        for invalid in ("a/b", "..", "CON", "trailing."):
            with self.subTest(invalid=invalid):
                with self.assertRaises(pm.ProjectStorageError):
                    pm.project_folder_path(invalid, projects)

    def test_windows_storage_migration_is_report_first_and_confirmed(self):
        pdir = self.d / "pointers"
        projects = self.d / "vault" / "Projects"
        pdir.mkdir(parents=True)
        source = projects / "Bad: Folder."
        source.mkdir(parents=True)
        (source / "draft.md").write_text("keep", encoding="utf-8")
        pointer = pdir / "book.json"
        pointer.write_text(json.dumps({
            "nexus": "book",
            "name": "Bad: Folder.",
            "display_name": "Book Display",
            "folder_name": "Bad: Folder.",
            "future": {"kept": True},
        }), encoding="utf-8")
        before = pointer.read_bytes()

        plan = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )

        self.assertTrue(plan["can_apply"])
        self.assertEqual(pointer.read_bytes(), before)
        self.assertTrue(source.is_dir())
        with self.assertRaises(pm.ProjectStorageError):
            pm.apply_windows_project_storage_migration(plan)

        outcome = pm.apply_windows_project_storage_migration(plan, confirmed=True)
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["applied"], ["book"])
        raw = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertEqual(raw["name"], raw["folder_name"])
        self.assertEqual(raw["display_name"], "Book Display")
        self.assertEqual(raw["future"], {"kept": True})
        target = projects / raw["folder_name"]
        self.assertTrue((target / "draft.md").is_file())
        self.assertFalse(source.exists())

    def test_windows_storage_migration_moves_matrix_resolved_by_frontmatter(self):
        from orchestrator import operation_matrix as om

        pdir = self.d / "pointers"
        vault = self.d / "vault"
        projects = vault / "Projects"
        matrix_dir = vault / "Matrix"
        pdir.mkdir(parents=True)
        source_folder = projects / "Bad: Folder."
        source_folder.mkdir(parents=True)
        matrix_dir.mkdir()
        pointer = pdir / "book.json"
        pointer.write_text(json.dumps({
            "nexus": "book", "name": "Bad: Folder.",
            "display_name": "Book", "folder_name": "Bad: Folder.",
        }), encoding="utf-8")
        matrix_source = matrix_dir / "Project Matrix Bad: Folder..md"
        matrix_source.write_text(
            "---\nnexus:\n  - book\ntype: matrix\n---\n\n## Mission\n\nKeep me.\n",
            encoding="utf-8",
        )

        plan = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )

        self.assertTrue(plan["can_apply"])
        entry = plan["changes"][0]
        self.assertTrue(entry["folder_move"])
        self.assertTrue(entry["matrix_move"])
        self.assertEqual(pathlib.Path(entry["matrix_source_path"]), matrix_source)

        outcome = pm.apply_windows_project_storage_migration(plan, confirmed=True)

        self.assertTrue(outcome["ok"])
        raw = json.loads(pointer.read_text(encoding="utf-8"))
        matrix_target = matrix_dir / f"Project Matrix {raw['folder_name']}.md"
        self.assertFalse(matrix_source.exists())
        self.assertIn("Keep me.", matrix_target.read_text(encoding="utf-8"))
        self.assertEqual(
            om.resolve_matrix_path("book", raw["folder_name"], vault=vault),
            matrix_target,
        )

    def test_windows_storage_migration_can_move_only_nonportable_matrix(self):
        pdir = self.d / "pointers"
        vault = self.d / "vault"
        projects = vault / "Projects"
        matrix_dir = vault / "Matrix"
        pdir.mkdir(parents=True)
        projects.mkdir(parents=True)
        matrix_dir.mkdir()
        pointer = pdir / "book.json"
        pointer.write_text(json.dumps({
            "nexus": "book", "name": "Book",
            "display_name": "Book", "folder_name": "Book",
        }), encoding="utf-8")
        before = pointer.read_bytes()
        matrix_source = matrix_dir / "Legacy: Book Matrix.md"
        matrix_source.write_text(
            "---\nnexus:\n  - book\ntype: matrix\n---\n\nbody\n",
            encoding="utf-8",
        )

        plan = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )

        entry = plan["changes"][0]
        self.assertFalse(entry["folder_move"])
        self.assertTrue(entry["matrix_move"])
        outcome = pm.apply_windows_project_storage_migration(plan, confirmed=True)
        self.assertTrue(outcome["ok"])
        self.assertEqual(pointer.read_bytes(), before)
        self.assertFalse(matrix_source.exists())
        self.assertTrue((matrix_dir / "Project Matrix Book.md").is_file())

    def test_windows_storage_migration_blocks_ambiguous_or_colliding_matrix(self):
        pdir = self.d / "pointers"
        vault = self.d / "vault"
        projects = vault / "Projects"
        matrix_dir = vault / "Matrix"
        pdir.mkdir(parents=True)
        projects.mkdir(parents=True)
        matrix_dir.mkdir()
        (pdir / "book.json").write_text(json.dumps({
            "nexus": "book", "name": "Book",
            "display_name": "Book", "folder_name": "Book",
        }), encoding="utf-8")
        for name in ("One.md", "Two.md"):
            (matrix_dir / name).write_text(
                "---\nnexus:\n  - book\ntype: matrix\n---\n", encoding="utf-8",
            )

        ambiguous = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )
        self.assertFalse(ambiguous["can_apply"])
        self.assertIn("multiple Matrix files", ambiguous["blocked"][0]["reasons"][-1])

        for path in matrix_dir.glob("*.md"):
            path.unlink()
        (matrix_dir / "Legacy: Book.md").write_text(
            "---\nnexus:\n  - book\ntype: matrix\n---\n", encoding="utf-8",
        )
        (matrix_dir / "Project Matrix Book.md").write_text(
            "---\nnexus:\n  - other\ntype: matrix\n---\n", encoding="utf-8",
        )
        collision = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )
        self.assertFalse(collision["can_apply"])
        self.assertIn("already exists", collision["blocked"][0]["reasons"][-1])

    def test_windows_storage_migration_reports_missing_source_as_blocker(self):
        pdir = self.d / "pointers"
        projects = self.d / "vault" / "Projects"
        pdir.mkdir(parents=True)
        (pdir / "book.json").write_text(json.dumps({
            "nexus": "book", "name": "Bad:Name",
            "display_name": "Book", "folder_name": "Bad:Name",
        }), encoding="utf-8")

        plan = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )

        self.assertFalse(plan["can_apply"])
        self.assertTrue(plan["blocked"])

    def test_windows_storage_migration_rolls_back_failed_pointer_write(self):
        pdir = self.d / "pointers"
        projects = self.d / "vault" / "Projects"
        pdir.mkdir(parents=True)
        source = projects / "Bad:Folder"
        source.mkdir(parents=True)
        matrix_dir = projects.parent / "Matrix"
        matrix_dir.mkdir()
        matrix_source = matrix_dir / "Bad:Matrix.md"
        matrix_source.write_text(
            "---\nnexus:\n  - book\ntype: matrix\n---\n", encoding="utf-8",
        )
        pointer = pdir / "book.json"
        pointer.write_text(json.dumps({
            "nexus": "book", "name": "Bad:Folder",
            "display_name": "Book", "folder_name": "Bad:Folder",
        }), encoding="utf-8")
        plan = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )
        original_write = pm._write_pointer
        try:
            pm._write_pointer = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
            outcome = pm.apply_windows_project_storage_migration(plan, confirmed=True)
        finally:
            pm._write_pointer = original_write

        self.assertFalse(outcome["ok"])
        self.assertTrue(source.is_dir())
        self.assertFalse(pathlib.Path(plan["changes"][0]["target_path"]).exists())
        self.assertTrue(matrix_source.is_file())
        self.assertFalse(
            pathlib.Path(plan["changes"][0]["matrix_target_path"]).exists()
        )
        raw = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertEqual(raw["folder_name"], "Bad:Folder")

    def test_windows_storage_migration_cli_reports_without_writes_and_applies_saved_plan(self):
        pdir = self.d / "pointers"
        projects = self.d / "vault" / "Projects"
        pdir.mkdir(parents=True)
        source = projects / "Bad:Folder"
        source.mkdir(parents=True)
        (source / "draft.md").write_text("keep", encoding="utf-8")
        pointer = pdir / "book.json"
        pointer.write_text(json.dumps({
            "nexus": "book", "name": "Bad:Folder",
            "display_name": "Book", "folder_name": "Bad:Folder",
        }), encoding="utf-8")
        pointer_before = pointer.read_bytes()
        command = [
            sys.executable, "-m", "orchestrator.project_meta",
            "windows-storage-migration", "report",
            "--pointer-dir", str(pdir),
            "--vault-projects-dir", str(projects),
        ]

        reported = subprocess.run(
            command, cwd=_REPO, text=True, capture_output=True, check=False,
        )

        self.assertEqual(reported.returncode, 0, reported.stderr)
        plan = json.loads(reported.stdout)
        self.assertTrue(plan["can_apply"])
        self.assertEqual(pointer.read_bytes(), pointer_before)
        self.assertTrue(source.is_dir())

        plan_path = self.d / "reviewed-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        apply_command = [
            sys.executable, "-m", "orchestrator.project_meta",
            "windows-storage-migration", "apply", "--plan", str(plan_path),
        ]
        unconfirmed = subprocess.run(
            apply_command, cwd=_REPO, text=True, capture_output=True, check=False,
        )
        self.assertEqual(unconfirmed.returncode, 2)
        self.assertFalse(json.loads(unconfirmed.stderr)["ok"])
        self.assertEqual(pointer.read_bytes(), pointer_before)
        self.assertTrue(source.is_dir())

        applied = subprocess.run(
            [
                *apply_command,
                "--confirm-apply-fingerprint", plan["fingerprint"],
            ],
            cwd=_REPO, text=True, capture_output=True, check=False,
        )

        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(json.loads(applied.stdout)["ok"])
        migrated = json.loads(pointer.read_text(encoding="utf-8"))
        self.assertNotEqual(migrated["folder_name"], "Bad:Folder")
        self.assertTrue((projects / migrated["folder_name"] / "draft.md").is_file())

    def test_windows_storage_migration_cli_can_apply_exact_current_fingerprint(self):
        pdir = self.d / "pointers"
        projects = self.d / "vault" / "Projects"
        pdir.mkdir(parents=True)
        source = projects / "Bad:Folder"
        source.mkdir(parents=True)
        pointer = pdir / "book.json"
        pointer.write_text(json.dumps({
            "nexus": "book", "name": "Bad:Folder",
            "display_name": "Book", "folder_name": "Bad:Folder",
        }), encoding="utf-8")
        plan = pm.plan_windows_project_storage_migration(
            pointer_dir=pdir, vault_projects_dir=projects,
        )
        base_command = [
            sys.executable, "-m", "orchestrator.project_meta",
            "windows-storage-migration", "apply",
            "--pointer-dir", str(pdir),
            "--vault-projects-dir", str(projects),
        ]

        stale = subprocess.run(
            [
                *base_command, "--fingerprint", "0" * 64,
                "--confirm-apply-fingerprint", "0" * 64,
            ],
            cwd=_REPO, text=True, capture_output=True, check=False,
        )
        self.assertEqual(stale.returncode, 2)
        self.assertIn("fresh report", json.loads(stale.stderr)["error"])
        self.assertTrue(source.is_dir())

        applied = subprocess.run(
            [
                *base_command, "--fingerprint", plan["fingerprint"],
                "--confirm-apply-fingerprint", plan["fingerprint"],
            ],
            cwd=_REPO, text=True, capture_output=True, check=False,
        )

        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(json.loads(applied.stdout)["ok"])
        self.assertFalse(source.exists())

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
