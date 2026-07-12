"""Tests for the G1.33 active-project pointer (orchestrator/active_project.py)."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
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

    def test_commons_and_empty_reset(self):
        ap.set_active_project("book")
        ap.set_active_project("")
        self.assertEqual(ap.get_active_project(), "commons")
        ap.set_active_project("law")
        ap.set_active_project(None)
        self.assertEqual(ap.get_active_project(), "commons")

    def test_malformed_pointer_defaults_commons(self):
        ap.ACTIVE_PROJECT_POINTER.write_text("not json{", encoding="utf-8")
        self.assertEqual(ap.get_active_project(), "commons")

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


if __name__ == "__main__":
    unittest.main()
