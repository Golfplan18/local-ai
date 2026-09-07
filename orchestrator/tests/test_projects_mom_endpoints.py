"""Tests for the G1.33 sub-step 5 MOM endpoints
(GET/POST /api/projects/<nexus>/mom) over the vault Operation-Matrix file."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _p in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()
from server import app as server  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_task_runtime(tmp_path, monkeypatch):
    import runtime_hygiene
    from orchestrator import operation_matrix
    monkeypatch.setattr(runtime_hygiene._rp, "DATA_DIR_STR", str(tmp_path / "runtime"))
    monkeypatch.setattr(operation_matrix._rp, "DATA_DIR_STR", str(tmp_path / "runtime"))


class ProjectsMomEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        (self.vault / "Matrix").mkdir()
        self._orig_env = os.environ.get("ORA_VAULT_PATH")
        os.environ["ORA_VAULT_PATH"] = str(self.vault)
        from orchestrator import project_meta as pm
        self._pm = pm
        self._orig_pointer_dir = pm.POINTER_DIR
        self._orig_projects_dir = pm.DEFAULT_VAULT_PROJECTS_DIR
        pm.POINTER_DIR = self.vault / "project-pointers"
        pm.DEFAULT_VAULT_PROJECTS_DIR = self.vault / "Projects"
        pm.create_project(
            "My Book",
            pointer_dir=pm.POINTER_DIR,
            vault_projects_dir=pm.DEFAULT_VAULT_PROJECTS_DIR,
        )
        self.client = server.app.test_client()

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._orig_env
        self._pm.POINTER_DIR = self._orig_pointer_dir
        self._pm.DEFAULT_VAULT_PROJECTS_DIR = self._orig_projects_dir
        self._tmp.cleanup()

    def test_get_missing_project_is_404(self):
        r = self.client.get("/api/projects/ghost/mom?name=Ghost")
        self.assertEqual(r.status_code, 404)
        body = json.loads(r.data)
        self.assertFalse(body["ok"])

    def test_post_creates_then_get_reads(self):
        from orchestrator import operation_matrix as om
        with mock.patch.object(om, "_new_matrix_text", return_value="---\ntype: [matrix]\n---\n"):
            refusal = self.client.post("/api/projects/my-book/mom", json={"mission": "Refused"})
        self.assertEqual(refusal.status_code, 409, refusal.data)
        self.assertTrue(refusal.json["metadata_invalid"])
        self.assertNotIn("mom", refusal.json)
        self.assertFalse(list((self.vault / "Matrix").iterdir()))
        r = self.client.post(
            "/api/projects/my-book/mom",
            json={
                "name": "Attacker Supplied Name Is Ignored",
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
        self.assertTrue(mom["warnings"])
        self.assertEqual(mom["mission"], "Tell a story.")
        self.assertEqual(len(mom["milestones"]), 2)
        # File actually landed in the vault Matrix dir.
        self.assertTrue((self.vault / "Matrix" / "Project Matrix My Book.md").is_file())

        # GET reads it back.
        g = self.client.get("/api/projects/my-book/mom?name=Also Ignored")
        gmom = json.loads(g.data)["mom"]
        self.assertEqual(gmom["objectives"], "Finish the draft.")
        self.assertTrue(gmom["milestones"][0]["done"])

    def _classify_matrix_as_project(self, filename):
        """Stamp the explicit project_type the MOM write gate requires.

        The gate (#260, 2026-07-13) refuses a MOM write unless the Matrix
        frontmatter declares project_type: [project]. A matrix created through
        this endpoint does not carry it — _new_matrix_text writes nexus/type/
        dates only — so the create succeeds (no file yet, gate skipped) and
        every later write is 403'd, which is what broke this test. Doing here
        what the gate's own error message tells the operator to do keeps the
        subject of the test the patch semantics rather than the gate.
        """
        path = self.vault / "Matrix" / filename
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        end = text.index("\n---\n", 4)
        path.write_text(
            text[:end] + "\nproject_type:\n  - project" + text[end:],
            encoding="utf-8",
        )

    def test_post_patch_preserves_other_sections(self):
        self.client.post(
            "/api/projects/my-book/mom",
            json={"name": "Wrong", "mission": "First.", "objectives": "Obj."},
        )
        self._classify_matrix_as_project("Project Matrix My Book.md")
        # Patch only the mission; objectives must remain.
        self.client.post(
            "/api/projects/my-book/mom",
            json={"name": "Still Wrong", "mission": "Second."},
        )
        g = self.client.get("/api/projects/my-book/mom?name=Wrong")
        mom = json.loads(g.data)["mom"]
        self.assertEqual(mom["mission"], "Second.")
        self.assertEqual(mom["objectives"], "Obj.")

    def test_commons_post_404(self):
        r = self.client.post("/api/projects/commons/mom", json={"mission": "x"})
        self.assertEqual(r.status_code, 404)

    def test_legacy_general_post_404(self):
        r = self.client.post("/api/projects/general/mom", json={"mission": "x"})
        self.assertEqual(r.status_code, 404)

    def test_display_rename_does_not_move_matrix_filename(self):
        self._pm.update_project_meta("my-book", {"name": 'Book: A "Law"?'})
        r = self.client.post(
            "/api/projects/my-book/mom",
            json={"name": "Client Lie", "mission": "Stable storage."},
        )
        self.assertEqual(r.status_code, 200)
        path = self.vault / "Matrix" / "Project Matrix My Book.md"
        self.assertTrue(path.is_file())
        self.assertIn('# Project Matrix Book: A "Law"?', path.read_text(encoding="utf-8"))

    def test_ambiguous_matrix_returns_409(self):
        body = "---\nnexus:\n  - my-book\ntype: matrix\n---\n"
        for name in ("One", "Two"):
            (self.vault / "Matrix" / f"Project Matrix {name}.md").write_text(
                body, encoding="utf-8"
            )
        r = self.client.get("/api/projects/my-book/mom")
        self.assertEqual(r.status_code, 409)
        payload = json.loads(r.data)
        self.assertTrue(payload["migration_required"])

    def task_matrix(self, classification="[project]"):
        path = self.vault / "Matrix" / "Original.md"
        path.write_text(f"---\nnexus: [my-book]\nproject_type: {classification}\n---\n## Tasks\n- [ ] Duplicate\n- [ ] Duplicate\n")
        return path

    def test_tasks_routes_mutate_real_service_once_and_return_actual_snapshot(self):
        from orchestrator import operation_matrix as om
        outside = self.vault / "Unrelated.md"
        outside.write_bytes(b"---\nnexus: [my-book]\n---\nUnrelated content must remain.\n")
        outside_before = outside.read_bytes()
        candidate = self.vault / "Matrix" / "Project Matrix My Book.md"
        for classification, entry in (("project", "directory"), ("operation", "symlink"), ("passion", "directory")):
            with self.subTest(classification=classification, entry=entry):
                path = self.task_matrix(f"[{classification}]")
                if entry == "directory":
                    candidate.mkdir()
                else:
                    candidate.symlink_to(outside)
                group = self.client.get("/api/projects/my-book/tasks").json["group"]
                with mock.patch.object(om._rp, "atomic_write_bytes", wraps=om._rp.atomic_write_bytes) as writer:
                    response = self.client.post("/api/projects/my-book/tasks", json={
                        "expected_digest": group["digest"], "operation": "edit",
                        "target": group["tasks"][1]["ref"], "value": "Edited second",
                    })
                    self.assertEqual(response.status_code, 200, response.json)
                    writer.assert_called_once()
                self.assertEqual(response.json["group"], self.client.get("/api/projects/my-book/tasks").json["group"])
                self.assertIn("- [ ] Duplicate\n- [ ] Edited second", path.read_text())
                self.assertIn(group["tasks"][1]["ref"], response.json["correspondence"])
                mom = self.client.get("/api/projects/my-book/mom")
                self.assertEqual(mom.status_code, 200, mom.json)
                self.assertEqual(mom.json["mom"]["matrix_path"], str(path))
                self.assertEqual(outside.read_bytes(), outside_before)
                if entry == "directory":
                    self.assertTrue(candidate.is_dir())
                    candidate.rmdir()
                else:
                    self.assertTrue(candidate.is_symlink())
                    self.assertEqual(candidate.readlink(), outside)
                    candidate.unlink()

    def test_tasks_readonly_missing_strict_body_and_cross_site(self):
        response = self.client.get("/api/projects/my-book/tasks")
        self.assertEqual(response.json["group"]["state"], "unavailable")
        self.assertIsNone(response.json["group"]["counts"]["total"])
        self.assertFalse(list((self.vault / "Matrix").iterdir()))
        for classification in ("project", "null", "[project, passion]", "[project, unknown]"):
            self.task_matrix(classification)
            group = self.client.get("/api/projects/my-book/tasks").json["group"]
            self.assertFalse(group["editable"])
            self.assertEqual(len(group["tasks"]), 2)
            response = self.client.post("/api/projects/my-book/tasks", json={"expected_digest": group["digest"], "operation": "complete", "target": group["tasks"][0]["ref"]})
            self.assertEqual(response.status_code, 403)
        self.task_matrix()
        group = self.client.get("/api/projects/my-book/tasks").json["group"]
        body = {"expected_digest": group["digest"], "operation": "complete", "target": group["tasks"][0]["ref"]}
        for extra in ("path", "name", "classification", "text", "filename"):
            self.assertEqual(self.client.post("/api/projects/my-book/tasks", json={**body, extra: "client authority"}).status_code, 400)
        self.assertEqual(self.client.post("/api/projects/my-book/tasks", json={**body, "target": 0}).status_code, 400)
        self.assertEqual(self.client.get("/api/projects/my-book/tasks?name=Other").status_code, 400)
        self.assertEqual(self.client.post("/api/projects/my-book/tasks", json=body, headers={"Origin": "https://untrusted.example", "Sec-Fetch-Site": "cross-site"}).status_code, 403)
        self.assertEqual(self.client.get("/api/projects/commons/tasks").status_code, 404)

    def test_tasks_conflict_and_unknown_outcome_are_distinct(self):
        from orchestrator import operation_matrix as om
        path = self.task_matrix()
        group = self.client.get("/api/projects/my-book/tasks").json["group"]
        body = {"expected_digest": group["digest"], "operation": "complete", "target": group["tasks"][0]["ref"]}
        path.write_bytes(path.read_bytes() + b"External\n")
        conflict = self.client.post("/api/projects/my-book/tasks", json=body)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json["code"], "conflict")
        self.assertIs(conflict.json["saved"], False)
        group = self.client.get("/api/projects/my-book/tasks").json["group"]
        body.update(expected_digest=group["digest"], target=group["tasks"][0]["ref"])
        original = om._rp.atomic_write_bytes
        def landed_then_error(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("response could not confirm write")
        with mock.patch.object(om._rp, "atomic_write_bytes", side_effect=landed_then_error):
            response = self.client.post("/api/projects/my-book/tasks", json=body)
        self.assertEqual(response.json["code"], "unknown-outcome")
        self.assertIsNone(response.json["saved"])
        self.assertTrue(self.client.get("/api/projects/my-book/tasks").json["group"]["tasks"][0]["done"])


if __name__ == "__main__":
    unittest.main()
