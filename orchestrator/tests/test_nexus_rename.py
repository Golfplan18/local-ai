"""Tests for the G1.33 nexus-rename bulk-YAML cascade
(orchestrator/nexus_rename.py). All operations run against temp dirs — never
the real vault."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_REPO, os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator import nexus_rename as nr  # noqa: E402


class RewriteFrontmatterTests(unittest.TestCase):
    def test_block_list(self):
        text = "---\nnexus:\n  - old\n  - keep\ntype: matrix\n---\n\nbody - old stays\n"
        out = nr.rewrite_frontmatter_nexus(text, "old", "new")
        self.assertIn("  - new\n", out)
        self.assertIn("  - keep\n", out)
        self.assertIn("body - old stays", out)  # body untouched
        self.assertNotIn("  - old\n", out)

    def test_scalar(self):
        text = "---\nnexus: old\ntype: x\n---\nbody\n"
        out = nr.rewrite_frontmatter_nexus(text, "old", "new")
        self.assertIn("nexus: new\n", out)

    def test_no_match_returns_none(self):
        text = "---\nnexus:\n  - other\n---\nbody\n"
        self.assertIsNone(nr.rewrite_frontmatter_nexus(text, "old", "new"))

    def test_no_frontmatter_returns_none(self):
        self.assertIsNone(nr.rewrite_frontmatter_nexus("no frontmatter old\n", "old", "new"))

    def test_only_frontmatter_not_body(self):
        # A body line that looks like a list item must NOT change.
        text = "---\nnexus:\n  - old\n---\n\n## Tasks\n  - old task\n"
        out = nr.rewrite_frontmatter_nexus(text, "old", "new")
        self.assertIn("  - new\n", out)
        self.assertIn("  - old task\n", out)  # body list item preserved


class RenameCascadeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.vault = self.root / "vault"
        (self.vault / "Matrix").mkdir(parents=True)
        (self.vault / "Notes").mkdir()
        # Two files carrying the nexus + one that doesn't.
        (self.vault / "Matrix" / "Project Matrix Book.md").write_text(
            "---\nnexus:\n  - book\ntype: matrix\n---\n\n## Mission\n\nWrite.\n", encoding="utf-8")
        (self.vault / "Notes" / "n1.md").write_text(
            "---\nnexus: book\n---\nbody\n", encoding="utf-8")
        (self.vault / "Notes" / "other.md").write_text(
            "---\nnexus:\n  - elsewhere\n---\nbody\n", encoding="utf-8")
        # Skipped dir.
        (self.vault / ".obsidian").mkdir()
        (self.vault / ".obsidian" / "junk.md").write_text(
            "---\nnexus:\n  - book\n---\n", encoding="utf-8")

        self.pdir = self.root / "projects"
        self.pdir.mkdir()
        (self.pdir / "book.json").write_text(
            json.dumps({"nexus": "book", "name": "Book", "status": "active"}), encoding="utf-8")

        self.sess = self.root / "sessions"
        self.sess.mkdir()
        self._mk_conv("c1", ["book"])
        self._mk_conv("c2", ["book", "other"])
        self._mk_conv("c3", ["unrelated"])

    def tearDown(self):
        self._tmp.cleanup()

    def _mk_conv(self, cid, pids):
        d = self.sess / cid
        d.mkdir()
        (d / "conversation.json").write_text(
            json.dumps({"conversation_id": cid, "project_ids": pids, "messages": []}),
            encoding="utf-8")

    def _conv_pids(self, cid):
        data = json.loads((self.sess / cid / "conversation.json").read_text())
        return data.get("project_ids")

    def _report(self, dry_run):
        return nr.rename_nexus(
            "book", "memoir",
            vault=self.vault, pointer_dir=self.pdir, sessions_root=self.sess,
            dry_run=dry_run)

    def test_dry_run_previews_without_writing(self):
        rep = self._report(dry_run=True)
        self.assertEqual(rep["vault_file_count"], 2)  # 2 hits, .obsidian skipped
        self.assertEqual(rep["conversation_count"], 2)  # c1, c2
        # Nothing written.
        self.assertIn("  - book\n", (self.vault / "Matrix" / "Project Matrix Book.md").read_text())
        self.assertTrue((self.pdir / "book.json").exists())
        self.assertFalse((self.pdir / "memoir.json").exists())
        self.assertEqual(self._conv_pids("c1"), ["book"])

    def test_execute_cascades(self):
        rep = self._report(dry_run=False)
        self.assertEqual(rep["errors"], [])
        # 1) Vault frontmatter rewritten; bodies + other nexuses preserved.
        bm = (self.vault / "Matrix" / "Project Matrix Book.md").read_text()
        self.assertIn("  - memoir\n", bm)
        self.assertNotIn("  - book\n", bm)
        self.assertIn("Write.", bm)
        self.assertIn("nexus: memoir\n", (self.vault / "Notes" / "n1.md").read_text())
        self.assertIn("  - elsewhere\n", (self.vault / "Notes" / "other.md").read_text())
        # .obsidian was skipped (still book).
        self.assertIn("  - book\n", (self.vault / ".obsidian" / "junk.md").read_text())
        # 2) Conversation memberships remapped (other memberships preserved).
        self.assertEqual(self._conv_pids("c1"), ["memoir"])
        self.assertEqual(self._conv_pids("c2"), ["memoir", "other"])
        self.assertEqual(self._conv_pids("c3"), ["unrelated"])
        # 3) Pointer renamed with internal nexus updated.
        self.assertFalse((self.pdir / "book.json").exists())
        self.assertTrue((self.pdir / "memoir.json").exists())
        self.assertEqual(json.loads((self.pdir / "memoir.json").read_text())["nexus"], "memoir")
        self.assertTrue(rep["pointer_renamed"])

    def test_validation(self):
        with self.assertRaises(nr.NexusRenameError):
            nr.rename_nexus("book", "general", vault=self.vault, pointer_dir=self.pdir,
                            sessions_root=self.sess, dry_run=True)
        with self.assertRaises(nr.NexusRenameError):
            nr.rename_nexus("book", "Bad Slug!", vault=self.vault, pointer_dir=self.pdir,
                            sessions_root=self.sess, dry_run=True)
        with self.assertRaises(nr.NexusRenameError):
            nr.rename_nexus("ghost", "x", vault=self.vault, pointer_dir=self.pdir,
                            sessions_root=self.sess, dry_run=True)

    def test_collision(self):
        (self.pdir / "taken.json").write_text(json.dumps({"nexus": "taken"}), encoding="utf-8")
        with self.assertRaises(nr.NexusRenameError):
            nr.rename_nexus("book", "taken", vault=self.vault, pointer_dir=self.pdir,
                            sessions_root=self.sess, dry_run=True)

    def test_active_project_bumped(self):
        from orchestrator import active_project as ap
        orig = ap.ACTIVE_PROJECT_POINTER
        ap.ACTIVE_PROJECT_POINTER = self.root / "active-project.json"
        try:
            ap.set_active_project("book")
            nr.rename_nexus("book", "memoir", vault=self.vault, pointer_dir=self.pdir,
                            sessions_root=self.sess, dry_run=False)
            self.assertEqual(ap.get_active_project(), "memoir")
        finally:
            ap.ACTIVE_PROJECT_POINTER = orig


class RenameEndpointTests(unittest.TestCase):
    """The endpoint defaults to dry-run; only an explicit dry_run:false writes."""

    def setUp(self):
        for _p in (os.path.join(_REPO, "server"),):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        from orchestrator.embedding import install_test_stub
        install_test_stub()
        import server
        self.server = server
        self.client = server.app.test_client()
        self._orig = nr.rename_nexus

    def tearDown(self):
        nr.rename_nexus = self._orig

    def test_default_is_dry_run(self):
        seen = {}
        def _spy(old, new, **kw):
            seen.update(kw)
            return {"old": old, "new": new, "dry_run": kw.get("dry_run"),
                    "vault_file_count": 3, "conversation_count": 1,
                    "vault_files": [], "conversations": [], "errors": []}
        nr.rename_nexus = _spy
        r = self.client.post("/api/projects/book/rename-nexus", json={"new_nexus": "memoir"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(seen["dry_run"])  # default preview, no write

    def test_explicit_execute(self):
        seen = {}
        nr.rename_nexus = lambda old, new, **kw: (seen.update(kw) or {
            "old": old, "new": new, "dry_run": kw.get("dry_run"),
            "vault_file_count": 0, "conversation_count": 0,
            "vault_files": [], "conversations": [], "errors": []})
        self.client.post("/api/projects/book/rename-nexus",
                         json={"new_nexus": "memoir", "dry_run": False})
        self.assertFalse(seen["dry_run"])

    def test_validation_error_400(self):
        def _raise(*a, **k):
            raise nr.NexusRenameError("reserved")
        nr.rename_nexus = _raise
        r = self.client.post("/api/projects/book/rename-nexus", json={"new_nexus": "general"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
