"""Tests for the G1.33 sub-step 5 MOM endpoints
(GET/POST /api/projects/<nexus>/mom) over the vault Operation-Matrix file."""

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


class ProjectsMomEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        (self.vault / "Matrix").mkdir()
        self._orig_env = os.environ.get("ORA_VAULT_PATH")
        os.environ["ORA_VAULT_PATH"] = str(self.vault)
        self.client = server.app.test_client()

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._orig_env
        self._tmp.cleanup()

    def test_get_missing_matrix_is_ok_not_error(self):
        r = self.client.get("/api/projects/ghost/mom?name=Ghost")
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.data)
        self.assertTrue(body["ok"])
        self.assertFalse(body["mom"]["exists"])

    def test_post_creates_then_get_reads(self):
        r = self.client.post(
            "/api/projects/my-book/mom",
            json={
                "name": "My Book",
                "mission": "Tell a story.",
                "objectives": "Finish the draft.",
                "milestones": [
                    {"text": "Outline", "done": True},
                    {"text": "Chapter 1", "done": False, "indent": 1},
                ],
            },
        )
        self.assertEqual(r.status_code, 200)
        mom = json.loads(r.data)["mom"]
        self.assertTrue(mom["exists"])
        self.assertEqual(mom["mission"], "Tell a story.")
        self.assertEqual(len(mom["milestones"]), 2)
        # File actually landed in the vault Matrix dir.
        self.assertTrue((self.vault / "Matrix" / "Project Matrix My Book.md").is_file())

        # GET reads it back.
        g = self.client.get("/api/projects/my-book/mom?name=My Book")
        gmom = json.loads(g.data)["mom"]
        self.assertEqual(gmom["objectives"], "Finish the draft.")
        self.assertTrue(gmom["milestones"][0]["done"])

    def test_post_patch_preserves_other_sections(self):
        self.client.post(
            "/api/projects/my-book/mom",
            json={"name": "My Book", "mission": "First.", "objectives": "Obj."},
        )
        # Patch only the mission; objectives must remain.
        self.client.post(
            "/api/projects/my-book/mom",
            json={"name": "My Book", "mission": "Second."},
        )
        g = self.client.get("/api/projects/my-book/mom?name=My Book")
        mom = json.loads(g.data)["mom"]
        self.assertEqual(mom["mission"], "Second.")
        self.assertEqual(mom["objectives"], "Obj.")

    def test_commons_post_404(self):
        r = self.client.post("/api/projects/commons/mom", json={"mission": "x"})
        self.assertEqual(r.status_code, 404)

    def test_legacy_general_post_404(self):
        r = self.client.post("/api/projects/general/mom", json={"mission": "x"})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
