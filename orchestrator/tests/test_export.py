"""Tests for the G1.34 output-export module + endpoints
(orchestrator/export.py, /api/export, /api/export/locations). Temp dirs only."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORA_HOME", _REPO)
for _p in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator import export as ex  # noqa: E402


class ExportModuleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        from orchestrator import project_meta as pm
        self.pm = pm
        self._orig_pointer_dir = pm.POINTER_DIR
        self._orig_projects_dir = pm.DEFAULT_VAULT_PROJECTS_DIR
        pm.POINTER_DIR = self.root / "project-pointers"
        pm.DEFAULT_VAULT_PROJECTS_DIR = self.vault / "Projects"

    def tearDown(self):
        self.pm.POINTER_DIR = self._orig_pointer_dir
        self.pm.DEFAULT_VAULT_PROJECTS_DIR = self._orig_projects_dir
        self._tmp.cleanup()

    def test_ensure_export_dirs(self):
        ex_dir = self.root / "Ora Exports"
        res_dir = self.root / "Ora Resources"
        out = ex.ensure_export_dirs(exports_dir=ex_dir, resources_dir=res_dir)
        self.assertTrue(out["exports"]["exists"])
        self.assertTrue(out["resources"]["exists"])
        self.assertTrue(ex_dir.is_dir())
        self.assertTrue(res_dir.is_dir())

    def test_default_export_roots_follow_late_documents_override(self):
        docs = self.root / "Redirected Documents"
        with mock.patch.dict(os.environ, {"ORA_DOCUMENTS": str(docs)}, clear=False):
            self.assertEqual(ex.current_exports_dir(), docs / "Ora Exports")
            self.assertEqual(ex.current_resources_dir(), docs / "Ora Resources")

    def test_windows_binary_search_dirs_cover_common_installers(self):
        dirs = ex._binary_search_dirs("nt", {
            "LOCALAPPDATA": r"C:\Users\ora\AppData\Local",
            "ProgramFiles": r"C:\Program Files",
            "ProgramFiles(x86)": r"C:\Program Files (x86)",
            "ProgramData": r"C:\ProgramData",
            "USERPROFILE": r"C:\Users\ora",
        })
        self.assertIn(r"C:\Users\ora\AppData\Local\Pandoc", dirs)
        self.assertIn(r"C:\Program Files\Pandoc", dirs)
        self.assertIn(r"C:\ProgramData\chocolatey\bin", dirs)
        self.assertIn(r"C:\Users\ora\scoop\shims", dirs)
        self.assertIn(r"C:\Users\ora\.cargo\bin", dirs)
        self.assertIn(
            r"C:\Users\ora\AppData\Local\Microsoft\WinGet\Links", dirs,
        )

    def test_binary_lookup_uses_which_for_pathext_fallback(self):
        directory = r"C:\Program Files\Pandoc"
        resolved = directory + r"\pandoc.exe"
        with (
            mock.patch.object(ex, "_binary_search_dirs", return_value=(directory,)),
            mock.patch.object(ex.shutil, "which", side_effect=[None, resolved]) as which,
        ):
            self.assertEqual(ex._which("pandoc"), resolved)
        self.assertEqual(which.call_args_list[1], mock.call("pandoc", path=directory))

    def test_save_commons_goes_to_vault_root(self):
        path = ex.save_output_to_vault("# Hello\n\nbody", title="My Note", vault=self.vault)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent, self.vault)
        text = path.read_text(encoding="utf-8")
        self.assertIn("type: output", text)
        self.assertIn("title: My Note", text)
        self.assertIn("nexus:\n", text)  # Commons → bare nexus
        self.assertNotIn("nexus:\n  -", text)
        self.assertIn("# Hello", text)

    def test_save_project_goes_to_project_folder(self):
        self.pm.create_project("My Book")
        path = ex.save_output_to_vault(
            "content", title="Draft", project_nexus="my-book",
            vault=self.vault)
        self.assertEqual(path.parent.name, "My Book")
        self.assertEqual(path.parent.parent.name, "Projects")
        self.assertIn("nexus:\n  - my-book", path.read_text(encoding="utf-8"))

    def test_immutable_folder_name_is_loaded_from_record(self):
        self.pm.create_project("My Book")
        self.pm.update_project_meta("my-book", {"name": "Book of Law"})
        path = ex.save_output_to_vault(
            "content", title="Draft", project_nexus="my-book", vault=self.vault)
        self.assertEqual(path.parent, self.vault / "Projects" / "My Book")

    def test_project_name_is_never_a_storage_fallback(self):
        self.pm.create_project("My Book")
        with self.assertRaises(ex.ProjectExportIdentityError):
            ex.save_output_to_vault(
                "content", project_nexus="my-book", project_name="My Book",
                vault=self.vault,
            )

    def test_supplied_folder_must_match_persisted_identity(self):
        self.pm.create_project("My Book")
        with self.assertRaises(ex.ProjectExportIdentityError):
            ex.save_output_to_vault(
                "content", project_nexus="my-book",
                project_folder_name="Different", vault=self.vault,
            )

    def test_missing_project_fails_typed_without_creating_folder(self):
        with self.assertRaises(ex.ProjectExportNotFoundError):
            ex.save_output_to_vault(
                "content", project_nexus="ghost", vault=self.vault,
            )
        self.assertFalse((self.vault / "Projects" / "ghost").exists())

    def test_explicit_compatibility_subdir_is_honored(self):
        path = ex.save_output_to_vault(
            "content", title="Legacy", vault=self.vault,
            outputs_subdir=ex.DEFAULT_OUTPUTS_SUBDIR)
        self.assertEqual(path.parent, self.vault / "Outputs")

    def test_exact_dot_folders_cannot_escape_intended_directory(self):
        for traversal in (".", ".."):
            subdir_path = ex.save_output_to_vault(
                "subdir", title="Subdir", vault=self.vault,
                outputs_subdir=traversal)
            self.assertEqual(subdir_path.parent, self.vault / "Untitled")

    def test_invalid_persisted_project_folder_requires_migration(self):
        pointer = self.pm.POINTER_DIR / "legacy.json"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(json.dumps({
            "nexus": "legacy", "name": "CON.txt",
            "display_name": "Legacy", "folder_name": "CON.txt",
        }), encoding="utf-8")
        with self.assertRaises(ex.ProjectExportMigrationRequiredError):
            ex.save_output_to_vault(
                "content", project_nexus="legacy", vault=self.vault,
            )

    def test_filename_collision(self):
        p1 = ex.save_output_to_vault("a", title="Same", vault=self.vault)
        p2 = ex.save_output_to_vault("b", title="Same", vault=self.vault)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p2.name.endswith("-2.md"))

    def test_project_output_filename_reserves_collision_and_temp_suffix(self):
        self.pm.create_project("My Book")
        title = " ".join(["astronomicallylongword" * 10] * 8)
        p1 = ex.save_output_to_vault(
            "a", title=title, project_nexus="my-book", vault=self.vault)
        p2 = ex.save_output_to_vault(
            "b", title=title, project_nexus="my-book", vault=self.vault)
        self.assertNotEqual(p1, p2)
        for path in (p1, p2):
            simulated_temp = path.name + ".tmp"
            self.assertLessEqual(
                len(simulated_temp.encode("utf-16-le")) // 2,
                ex.PROJECT_OUTPUT_CHILD_BUDGET_UNITS,
            )
            self.assertLessEqual(
                len(str(path.resolve()).encode("utf-16-le")) // 2,
                ex.WINDOWS_PORTABLE_PATH_LIMIT,
            )

    def test_derives_title_when_absent(self):
        path = ex.save_output_to_vault("## First Heading\n\nrest", vault=self.vault)
        self.assertIn("First Heading", path.read_text(encoding="utf-8"))

    def test_missing_vault_returns_none(self):
        missing = self.root / "missing" / "vault"
        self.assertIsNone(ex.save_output_to_vault("c", vault=missing))
        self.assertFalse(missing.exists())

    def test_export_capabilities_shape(self):
        caps = ex.export_capabilities()
        for key in ("pandoc", "docx", "pdf"):
            self.assertIn(key, caps)
            self.assertIsInstance(caps[key], bool)

    def test_export_to_file_guards(self):
        # Empty content / unsupported format → None regardless of Pandoc.
        self.assertIsNone(ex.export_to_file("", fmt="docx", exports_dir=self.root))
        self.assertIsNone(ex.export_to_file("x", fmt="rtf", exports_dir=self.root))

    @unittest.skipUnless(ex.pandoc_path(), "pandoc not installed")
    def test_export_to_file_docx_real(self):
        out = ex.export_to_file(
            "# Title\n\nA **paragraph**.\n", title="Doc", fmt="docx",
            exports_dir=self.root)
        self.assertIsNotNone(out)
        self.assertTrue(out.is_file())
        self.assertEqual(out.suffix, ".docx")
        self.assertGreater(out.stat().st_size, 0)
        self.assertEqual(out.parent, self.root)  # landed in the given exports dir

    @unittest.skipUnless(ex.pandoc_path() and ex.pdf_engine_path(), "no pandoc+pdf engine")
    def test_export_to_file_pdf_real(self):
        out = ex.export_to_file("# P\n\nbody\n", fmt="pdf", exports_dir=self.root)
        self.assertIsNotNone(out)
        self.assertEqual(out.suffix, ".pdf")
        self.assertGreater(out.stat().st_size, 0)


class ExportEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name) / "vault"
        self.vault.mkdir()
        self._orig_env = os.environ.get("ORA_VAULT_PATH")
        os.environ["ORA_VAULT_PATH"] = str(self.vault)
        from orchestrator import project_meta as pm
        self.pm = pm
        self._orig_pointer_dir = pm.POINTER_DIR
        self._orig_projects_dir = pm.DEFAULT_VAULT_PROJECTS_DIR
        pm.POINTER_DIR = pathlib.Path(self._tmp.name) / "project-pointers"
        pm.DEFAULT_VAULT_PROJECTS_DIR = self.vault / "Projects"
        from orchestrator.embedding import install_test_stub
        install_test_stub()
        from server import app as server
        self.client = server.app.test_client()

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._orig_env
        self.pm.POINTER_DIR = self._orig_pointer_dir
        self.pm.DEFAULT_VAULT_PROJECTS_DIR = self._orig_projects_dir
        self._tmp.cleanup()

    def test_current_output_saves_markdown(self):
        r = self.client.post("/api/export", json={
            "scope": "current_output", "content": "# Out\n\nbody", "title": "T",
            "project": "commons"})
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertTrue(pathlib.Path(body["path"]).is_file())
        self.assertEqual(pathlib.Path(body["path"]).parent.resolve(), self.vault.resolve())

    def test_current_output_saves_markdown_legacy_general(self):
        r = self.client.post("/api/export", json={
            "scope": "current_output", "content": "# Out\n\nbody", "title": "T2",
            "project": "general"})
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertTrue(pathlib.Path(body["path"]).is_file())
        self.assertEqual(pathlib.Path(body["path"]).parent.resolve(), self.vault.resolve())

    def test_project_rename_keeps_export_in_original_folder(self):
        self.pm.create_project("My Book")
        self.pm.update_project_meta("my-book", {"name": "Book of Law"})
        r = self.client.post("/api/export", json={
            "scope": "current_output",
            "content": "# Renamed project output",
            "title": "Renamed",
            "project": "my-book",
        })
        self.assertEqual(r.status_code, 200)
        path = pathlib.Path(json.loads(r.data)["path"])
        self.assertEqual(
            path.parent.resolve(),
            (self.vault / "Projects" / "My Book").resolve(),
        )
        self.assertFalse((self.vault / "Projects" / "Book of Law").exists())

    def test_missing_project_returns_404_without_nexus_folder_fallback(self):
        r = self.client.post("/api/export", json={
            "scope": "current_output", "content": "x", "project": "ghost",
        })
        self.assertEqual(r.status_code, 404)
        self.assertFalse((self.vault / "Projects" / "ghost").exists())

    def test_invalid_project_folder_returns_migration_409(self):
        pointer = self.pm.POINTER_DIR / "legacy.json"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(json.dumps({
            "nexus": "legacy", "name": "CON.txt",
            "display_name": "Legacy", "folder_name": "CON.txt",
        }), encoding="utf-8")
        r = self.client.post("/api/export", json={
            "scope": "current_output", "content": "x", "project": "legacy",
        })
        self.assertEqual(r.status_code, 409)
        self.assertTrue(json.loads(r.data)["migration_required"])

    def test_empty_content_400(self):
        r = self.client.post("/api/export", json={"scope": "current_output", "content": "  "})
        self.assertEqual(r.status_code, 400)

    def test_pandoc_deferred_when_incapable(self):
        # No Pandoc → docx/pdf report deferred (501), never write.
        from server import app as _srv
        _mod = _srv.__dict__  # endpoint imports orchestrator.export lazily
        from orchestrator import export as _ex
        orig = _ex.export_capabilities
        _ex.export_capabilities = lambda: {"pandoc": False, "docx": False, "pdf": False}
        try:
            for fmt in ("docx", "pdf"):
                r = self.client.post("/api/export", json={"format": fmt, "content": "x"})
                self.assertEqual(r.status_code, 501)
                self.assertTrue(json.loads(r.data).get("deferred"))
        finally:
            _ex.export_capabilities = orig

    def test_docx_converts_when_capable(self):
        # Capable → the endpoint returns the rendered file path (conversion
        # stubbed so the test needs neither Pandoc nor the real Exports dir).
        from orchestrator import export as _ex
        orig_caps, orig_conv = _ex.export_capabilities, _ex.export_to_file
        _ex.export_capabilities = lambda: {"pandoc": True, "docx": True, "pdf": True}
        _ex.export_to_file = lambda content, **k: pathlib.Path(self._tmp.name) / "out.docx"
        try:
            r = self.client.post("/api/export", json={"format": "docx", "content": "# X"})
            self.assertEqual(r.status_code, 200)
            body = json.loads(r.data)
            self.assertTrue(body["ok"])
            self.assertTrue(body["path"].endswith("out.docx"))
        finally:
            _ex.export_capabilities, _ex.export_to_file = orig_caps, orig_conv

    def test_unknown_format_400(self):
        r = self.client.post("/api/export", json={"format": "rtf", "content": "x"})
        self.assertEqual(r.status_code, 400)

    def test_full_conversation_requires_id(self):
        r = self.client.post("/api/export", json={"scope": "full_conversation"})
        self.assertEqual(r.status_code, 400)

    def test_locations_endpoint(self):
        r = self.client.get("/api/export/locations")
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertIn("exports", body)
        self.assertIn("resources", body)


if __name__ == "__main__":
    unittest.main()
