"""Tests for the G1.33 sub-step 5 modal-backend endpoints:
project files index, project conversation list (incl. closed), conversation
project membership, and the vault-sandboxed reveal-in-Finder guard."""

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

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()
import server  # noqa: E402
import conversation_memory as cm  # noqa: E402


class ModalEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        (self.vault / "Projects" / "My Book").mkdir(parents=True)
        (self.vault / "Projects" / "My Book" / "draft.md").write_text("hi", encoding="utf-8")
        self._orig_env = os.environ.get("ORA_VAULT_PATH")
        os.environ["ORA_VAULT_PATH"] = str(self.vault)

        # Point project_meta's vault Projects dir + conversation root at temps.
        from orchestrator import project_meta as pm
        self._pm = pm
        self._orig_projects_dir = pm.DEFAULT_VAULT_PROJECTS_DIR
        pm.DEFAULT_VAULT_PROJECTS_DIR = self.vault / "Projects"

        self.sess = pathlib.Path(self._tmp.name) / "sessions"
        self.sess.mkdir()
        self._orig_root = cm._DEFAULT_SESSIONS_ROOT
        cm._DEFAULT_SESSIONS_ROOT = self.sess
        cm.save_turn_spatial_state("c-book", "u", "a", project_ids=["my-book"], sessions_root=self.sess)
        cm.save_turn_spatial_state("c-other", "u", "a", project_ids=["other"], sessions_root=self.sess)

        self.client = server.app.test_client()

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._orig_env
        self._pm.DEFAULT_VAULT_PROJECTS_DIR = self._orig_projects_dir
        cm._DEFAULT_SESSIONS_ROOT = self._orig_root
        self._tmp.cleanup()

    # ── files ────────────────────────────────────────────────────────────
    def test_files_index(self):
        r = self.client.get("/api/projects/my-book/files?name=My Book")
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertTrue(body["exists"])
        names = {f["name"] for f in body["files"]}
        self.assertIn("draft.md", names)
        # obsidian_uri points into the vault.
        uri = body["files"][0]["obsidian_uri"]
        self.assertIsNotNone(uri)
        self.assertIn("obsidian://open", uri)

    def test_files_missing_folder_ok(self):
        r = self.client.get("/api/projects/ghost/files?name=Ghost")
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertFalse(body["exists"])

    # ── conversations ──────────────────────────────────────────────────────
    def test_project_conversations_filter(self):
        r = self.client.get("/api/projects/my-book/conversations")
        ids = {c["conversation_id"] for c in json.loads(r.data)["conversations"]}
        self.assertIn("c-book", ids)
        self.assertNotIn("c-other", ids)

    def test_project_conversations_general_all(self):
        r = self.client.get("/api/projects/general/conversations")
        ids = {c["conversation_id"] for c in json.loads(r.data)["conversations"]}
        self.assertIn("c-book", ids)
        self.assertIn("c-other", ids)

    def test_project_conversations_include_closed(self):
        cm.set_conversation_closed("c-book", True, sessions_root=self.sess)
        # Default excludes closed.
        r = self.client.get("/api/projects/my-book/conversations")
        ids = {c["conversation_id"] for c in json.loads(r.data)["conversations"]}
        self.assertNotIn("c-book", ids)
        # include_closed surfaces it (for the restore browser).
        r2 = self.client.get("/api/projects/my-book/conversations?include_closed=1")
        rows = json.loads(r2.data)["conversations"]
        closed = {c["conversation_id"]: c.get("closed") for c in rows}
        self.assertTrue(closed.get("c-book"))

    def test_project_conversations_candidates(self):
        # Candidates = threads NOT already in this project, not closed.
        r = self.client.get("/api/projects/my-book/conversations?candidates=1")
        ids = {c["conversation_id"] for c in json.loads(r.data)["conversations"]}
        self.assertIn("c-other", ids)      # not in my-book → a candidate
        self.assertNotIn("c-book", ids)    # already a member → excluded

    def test_candidates_query_filter_and_general(self):
        # q filters by title substring (titles derive from the first user msg "u").
        r = self.client.get("/api/projects/my-book/conversations?candidates=1&q=zzznope")
        self.assertEqual(json.loads(r.data)["conversations"], [])
        # General contains everything → no candidates to add.
        r2 = self.client.get("/api/projects/general/conversations?candidates=1")
        self.assertEqual(json.loads(r2.data)["conversations"], [])

    def test_candidates_excludes_closed(self):
        cm.set_conversation_closed("c-other", True, sessions_root=self.sess)
        r = self.client.get("/api/projects/my-book/conversations?candidates=1")
        ids = {c["conversation_id"] for c in json.loads(r.data)["conversations"]}
        self.assertNotIn("c-other", ids)  # closed threads aren't add-candidates

    # ── membership ─────────────────────────────────────────────────────────
    def test_set_conversation_projects(self):
        r = self.client.post(
            "/api/conversation/c-book/projects",
            json={"project_ids": ["my-book", "alpha", "general"]},
        )
        self.assertEqual(r.status_code, 200)
        stored = json.loads(r.data)["project_ids"]
        # general is dropped (implicit baseline); order + dedup preserved.
        self.assertEqual(stored, ["my-book", "alpha"])

    def test_set_projects_bad_body(self):
        r = self.client.post("/api/conversation/c-book/projects", json={"project_ids": "x"})
        self.assertEqual(r.status_code, 400)

    def test_set_projects_missing_conversation(self):
        r = self.client.post("/api/conversation/ghost/projects", json={"project_ids": []})
        self.assertEqual(r.status_code, 404)

    # ── reveal sandbox ─────────────────────────────────────────────────────
    def test_reveal_outside_vault_forbidden(self):
        r = self.client.post("/api/fs/reveal", json={"path": "/etc/hosts"})
        self.assertEqual(r.status_code, 403)

    def test_reveal_missing_path(self):
        r = self.client.post("/api/fs/reveal", json={})
        self.assertEqual(r.status_code, 400)

    def test_reveal_nonexistent_inside_vault(self):
        ghost = str(self.vault / "Projects" / "My Book" / "nope.md")
        r = self.client.post("/api/fs/reveal", json={"path": ghost})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
