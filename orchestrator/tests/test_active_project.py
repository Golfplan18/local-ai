"""Tests for the G1.33 active-project pointer (orchestrator/active_project.py)."""

from __future__ import annotations

import os
import json
import pathlib
import sys
import tempfile
import threading
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator import active_project as ap  # noqa: E402


class ActiveProjectPointerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self._tmp.name)
        self._orig = (ap.DATA_DIR, ap.ACTIVE_PROJECT_POINTER)
        ap.DATA_DIR = d
        ap.ACTIVE_PROJECT_POINTER = d / "active-project.json"

    def tearDown(self):
        ap.DATA_DIR, ap.ACTIVE_PROJECT_POINTER = self._orig
        self._tmp.cleanup()

    def test_default_commons_when_unset(self):
        self.assertEqual(ap.get_active_project(), "commons")

    def test_set_get_roundtrip(self):
        ap.set_active_project("book")
        self.assertEqual(ap.get_active_project(), "book")
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "book", "canonical_nexus": "book"})

    def test_commons_and_empty_reset(self):
        ap.set_active_project("book")
        ap.set_active_project("")
        self.assertEqual(ap.get_active_project(), "commons")
        ap.set_active_project("law")
        ap.set_active_project(None)
        self.assertEqual(ap.get_active_project(), "commons")

    def test_legacy_setter_persists_dual_default(self):
        ap.set_active_project(" General ")
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "general", "canonical_nexus": "commons"})
        # Simulate a pre-rename reader, which only knows the original field.
        self.assertEqual(raw["nexus"], "general")
        self.assertEqual(ap.get_active_project(), "commons")

    def test_legacy_pointer_read_is_pure_then_startup_migration_expands(self):
        ap.ACTIVE_PROJECT_POINTER.write_text(
            json.dumps({"nexus": "general"}), encoding="utf-8"
        )
        self.assertEqual(ap.get_active_project(), "commons")
        # Reads cannot overwrite a concurrent explicit selection.
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "general"})
        self.assertTrue(ap.migrate_active_project_pointer())
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "general", "canonical_nexus": "commons"})
        self.assertFalse(ap.migrate_active_project_pointer())  # idempotent

    def test_commons_only_pointer_is_expanded_explicitly_for_old_readers(self):
        ap.ACTIVE_PROJECT_POINTER.write_text(
            json.dumps({"nexus": "commons"}), encoding="utf-8"
        )
        self.assertEqual(ap.get_active_project(), "commons")
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "commons"})
        self.assertTrue(ap.migrate_active_project_pointer())
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "general", "canonical_nexus": "commons"})

    def test_canonical_field_is_preferred_and_startup_migration_reconciles(self):
        ap.ACTIVE_PROJECT_POINTER.write_text(
            json.dumps({"nexus": "general", "canonical_nexus": "book"}),
            encoding="utf-8",
        )
        self.assertEqual(ap.get_active_project(), "book")
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "general", "canonical_nexus": "book"})
        self.assertTrue(ap.migrate_active_project_pointer())
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "book", "canonical_nexus": "book"})

    def test_pointer_whitespace_is_explicitly_migrated(self):
        ap.ACTIVE_PROJECT_POINTER.write_text(
            json.dumps({"nexus": " book "}), encoding="utf-8"
        )
        self.assertEqual(ap.get_active_project(), "book")
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": " book "})
        self.assertTrue(ap.migrate_active_project_pointer())
        raw = json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"nexus": "book", "canonical_nexus": "book"})

    def test_malformed_pointer_defaults_commons(self):
        ap.ACTIVE_PROJECT_POINTER.write_text("not json{", encoding="utf-8")
        self.assertEqual(ap.get_active_project(), "commons")
        self.assertFalse(ap.migrate_active_project_pointer())

    def test_missing_pointer_has_nothing_to_migrate(self):
        self.assertFalse(ap.migrate_active_project_pointer())

    def test_resolve_project_ids(self):
        self.assertEqual(ap.resolve_project_ids(None), [])
        self.assertEqual(ap.resolve_project_ids(""), [])
        self.assertEqual(ap.resolve_project_ids("commons"), [])
        self.assertEqual(ap.resolve_project_ids("Commons"), [])
        self.assertEqual(ap.resolve_project_ids("book"), ["book"])
        self.assertEqual(ap.resolve_project_ids("  book  "), ["book"])

    def test_resolve_project_ids_legacy_general(self):
        self.assertEqual(ap.resolve_project_ids("general"), [])
        self.assertEqual(ap.resolve_project_ids("General"), [])

    def test_module_constants(self):
        self.assertEqual(ap.DEFAULT, "commons")
        self.assertEqual(ap.LEGACY_DEFAULT, "general")
        self.assertEqual(ap.GENERAL, "general")

    def test_canonicalize_project_nexus(self):
        self.assertEqual(ap.canonicalize_project_nexus(None), "commons")
        self.assertEqual(ap.canonicalize_project_nexus(" Commons "), "commons")
        self.assertEqual(ap.canonicalize_project_nexus(" GENERAL "), "commons")
        self.assertEqual(ap.canonicalize_project_nexus(" book "), "book")

    def test_project_nexus_fields_expand_for_old_and_new_readers(self):
        self.assertEqual(
            ap.project_nexus_fields("commons"),
            {"nexus": "general", "canonical_nexus": "commons"},
        )
        self.assertEqual(
            ap.project_nexus_fields("book"),
            {"nexus": "book", "canonical_nexus": "book"},
        )

    def test_cross_module_migration_cannot_overwrite_explicit_selection(self):
        """The sidecar lock is shared even when Python loads two module names."""
        orchestrator_dir = str(pathlib.Path(_REPO) / "orchestrator")
        if orchestrator_dir not in sys.path:
            sys.path.insert(0, orchestrator_dir)
        import active_project as top_level_ap

        self.assertIsNot(top_level_ap, ap)
        original_paths = (
            top_level_ap.DATA_DIR,
            top_level_ap.ACTIVE_PROJECT_POINTER,
        )
        top_level_ap.DATA_DIR = ap.DATA_DIR
        top_level_ap.ACTIVE_PROJECT_POINTER = ap.ACTIVE_PROJECT_POINTER
        ap.ACTIVE_PROJECT_POINTER.write_text(
            json.dumps({"nexus": "general"}), encoding="utf-8"
        )

        migration_at_write = threading.Event()
        release_migration = threading.Event()
        selection_done = threading.Event()
        errors: list[BaseException] = []
        original_write = top_level_ap._write_active_project_unlocked

        def delayed_migration_write(slug):
            migration_at_write.set()
            release_migration.wait(timeout=5)
            return original_write(slug)

        def migrate():
            try:
                top_level_ap.migrate_active_project_pointer()
            except BaseException as exc:  # pragma: no cover - regression diagnostics
                errors.append(exc)

        def select():
            try:
                ap.set_active_project("book")
            except BaseException as exc:  # pragma: no cover - regression diagnostics
                errors.append(exc)
            finally:
                selection_done.set()

        top_level_ap._write_active_project_unlocked = delayed_migration_write
        try:
            migration_thread = threading.Thread(target=migrate)
            migration_thread.start()
            self.assertTrue(migration_at_write.wait(timeout=5))
            selection_thread = threading.Thread(target=select)
            selection_thread.start()
            # The explicit setter must wait on the migration's filesystem lock.
            self.assertFalse(selection_done.wait(timeout=0.2))
            release_migration.set()
            migration_thread.join(timeout=5)
            selection_thread.join(timeout=5)
        finally:
            release_migration.set()
            top_level_ap._write_active_project_unlocked = original_write
            top_level_ap.DATA_DIR, top_level_ap.ACTIVE_PROJECT_POINTER = original_paths

        self.assertFalse(errors)
        self.assertEqual(ap.get_active_project(), "book")
        self.assertEqual(
            json.loads(ap.ACTIVE_PROJECT_POINTER.read_text(encoding="utf-8")),
            {"nexus": "book", "canonical_nexus": "book"},
        )


if __name__ == "__main__":
    unittest.main()
