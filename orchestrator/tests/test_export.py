"""Tests for the G1.34 output-export module + endpoints
(orchestrator/export.py, /api/export, /api/export/locations). Temp dirs only."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

    def tearDown(self):
        self._tmp.cleanup()

    def test_ensure_export_dirs(self):
        ex_dir = self.root / "Ora Exports"
        res_dir = self.root / "Ora Resources"
        out = ex.ensure_export_dirs(exports_dir=ex_dir, resources_dir=res_dir)
        self.assertTrue(out["exports"]["exists"])
        self.assertTrue(out["resources"]["exists"])
        self.assertTrue(ex_dir.is_dir())
        self.assertTrue(res_dir.is_dir())

    def test_save_general_goes_to_outputs(self):
        path = ex.save_output_to_vault("# Hello\n\nbody", title="My Note", vault=self.vault)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent.name, "Outputs")
        text = path.read_text(encoding="utf-8")
        self.assertIn("type: output", text)
        self.assertIn("title: My Note", text)
        self.assertIn("nexus:\n", text)  # General → bare nexus
        self.assertNotIn("nexus:\n  -", text)
        self.assertIn("# Hello", text)

    def test_save_project_goes_to_project_folder(self):
        path = ex.save_output_to_vault(
            "content", title="Draft", project_nexus="my-book",
            project_name="My Book", vault=self.vault)
        self.assertEqual(path.parent.name, "My Book")
        self.assertEqual(path.parent.parent.name, "Projects")
        self.assertIn("nexus:\n  - my-book", path.read_text(encoding="utf-8"))

    def test_filename_collision(self):
        p1 = ex.save_output_to_vault("a", title="Same", vault=self.vault)
        p2 = ex.save_output_to_vault("b", title="Same", vault=self.vault)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p2.name.endswith("-2.md"))

    def test_derives_title_when_absent(self):
        path = ex.save_output_to_vault("## First Heading\n\nrest", vault=self.vault)
        self.assertIn("First Heading", path.read_text(encoding="utf-8"))

    def test_missing_vault_returns_none(self):
        # A vault path that can't be created (a file in the way) → None, no raise.
        blocker = self.root / "blocker"
        blocker.write_text("x")
        self.assertIsNone(ex.save_output_to_vault("c", vault=blocker / "vault"))

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
        from orchestrator.embedding import install_test_stub
        install_test_stub()
        import server
        self.client = server.app.test_client()

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._orig_env
        self._tmp.cleanup()

    def test_current_output_saves_markdown(self):
        r = self.client.post("/api/export", json={
            "scope": "current_output", "content": "# Out\n\nbody", "title": "T",
            "project": "general"})
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertTrue(pathlib.Path(body["path"]).is_file())
        self.assertIn("Outputs", body["path"])

    def test_empty_content_400(self):
        r = self.client.post("/api/export", json={"scope": "current_output", "content": "  "})
        self.assertEqual(r.status_code, 400)

    def test_pandoc_deferred_when_incapable(self):
        # No Pandoc → docx/pdf report deferred (501), never write.
        import server as _srv
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
