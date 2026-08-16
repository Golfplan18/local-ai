"""Tests for the server-side MOM write gate.

Verifies that POST /api/projects/<nexus>/mom enforces the write-authorization
rule: writes require explicit schema-valid project_type: [project].
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORA_HOME", _REPO)
for _p in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()
from server import app as server  # noqa: E402
import conversation_memory as cm  # noqa: E402
from orchestrator import active_project as ap  # noqa: E402
from orchestrator import project_meta as pm  # noqa: E402
from orchestrator import operation_matrix as om  # noqa: E402


def _matrix(nexus: str, project_type_yaml: str, sections: str = "") -> str:
    """Build a minimal Matrix file with a given project_type.

    ``project_type_yaml`` is inserted verbatim after ``project_type:``.
    For lists, pass ``"  - project\\n  - book\\n"``.
    For scalars, pass ``"project"`` (no newline).
    """
    pt_block = ""
    if project_type_yaml:
        pt_block = f"project_type: {project_type_yaml}\n"
    body = sections or "## Mission\n\nTest mission.\n\n## Objectives\n\n- Goal 1.\n\n## Milestones\n\n- [ ] Task 1.\n"
    return (
        f"---\nnexus:\n  - {nexus}\ntype: matrix\n{pt_block}---\n\n"
        f"# Project Matrix {nexus.title()}\n\n{body}"
    )


class MomWriteGateTests(unittest.TestCase):
    """API-level tests for the MOM write gate on POST /api/projects/<nexus>/mom."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.vault = self.root / "vault"
        self.matrix_dir = self.vault / "Matrix"
        self.projects_dir = self.vault / "Projects"
        self.pointer_dir = self.root / "projects"
        self.matrix_dir.mkdir(parents=True)
        self.projects_dir.mkdir(parents=True)
        self.pointer_dir.mkdir(parents=True)

        self._orig_pointer_dir = pm.POINTER_DIR
        self._orig_sessions_root = cm._DEFAULT_SESSIONS_ROOT
        self._orig_active_data = (ap.DATA_DIR, ap.ACTIVE_PROJECT_POINTER)
        pm.POINTER_DIR = self.pointer_dir
        cm._DEFAULT_SESSIONS_ROOT = self.root / "sessions"
        cm._DEFAULT_SESSIONS_ROOT.mkdir(exist_ok=True)
        ap.DATA_DIR = self.root / "data"
        ap.ACTIVE_PROJECT_POINTER = ap.DATA_DIR / "active-project.json"

        self._orig_vault_dir = getattr(om._rp, "vault_dir", None)
        om._rp.vault_dir = lambda: self.vault

        self.client = server.app.test_client()

    def tearDown(self):
        pm.POINTER_DIR = self._orig_pointer_dir
        cm._DEFAULT_SESSIONS_ROOT = self._orig_sessions_root
        ap.DATA_DIR, ap.ACTIVE_PROJECT_POINTER = self._orig_active_data
        if self._orig_vault_dir is not None:
            om._rp.vault_dir = self._orig_vault_dir
        else:
            del om._rp.vault_dir
        self._tmp.cleanup()

    def _write_pointer(self, nexus: str, data: dict):
        (self.pointer_dir / f"{nexus}.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8",
        )

    def _write_matrix(self, filename: str, content: str):
        (self.matrix_dir / filename).write_text(content, encoding="utf-8")

    def _pointer(self, nexus: str, folder: str) -> dict:
        return {
            "nexus": nexus,
            "name": folder,
            "display_name": folder,
            "folder_name": folder,
            "status": "active",
        }

    def _post_mom(self, nexus: str, body: dict | None = None) -> tuple[int, dict]:
        resp = self.client.post(
            f"/api/projects/{nexus}/mom",
            json=body or {"mission": "Updated mission."},
            content_type="application/json",
        )
        return resp.status_code, json.loads(resp.data)

    # ---- Authorization (write allowed) ----

    def test_explicit_project_type_allows_write(self):
        """project_type: [project] → write allowed (200)."""
        self._write_pointer("allowed", self._pointer("allowed", "Allowed"))
        self._write_matrix(
            "Project Matrix Allowed.md",
            _matrix("allowed", "\n  - project\n"),
        )
        status, body = self._post_mom("allowed")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_project_plus_domain_allows_write(self):
        """project_type: [project, book] → write allowed (200)."""
        self._write_pointer("book-proj", self._pointer("book-proj", "BookProj"))
        self._write_matrix(
            "Project Matrix BookProj.md",
            _matrix("book-proj", "\n  - project\n  - book\n"),
        )
        status, body = self._post_mom("book-proj")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    # ---- Rejection (write blocked) ----

    def test_missing_project_type_blocks_write(self):
        """No project_type → write blocked (403)."""
        self._write_pointer("no-type", self._pointer("no-type", "NoType"))
        self._write_matrix(
            "Project Matrix NoType.md",
            _matrix("no-type", ""),
        )
        status, body = self._post_mom("no-type")
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])
        self.assertIn("project_type", body["error"])
        self.assertIn("write_gate", body)

    def test_scalar_operation_blocks_write(self):
        """project_type: operation (scalar) → write blocked (403)."""
        self._write_pointer("scalar-op", self._pointer("scalar-op", "ScalarOp"))
        self._write_matrix(
            "Project Matrix ScalarOp.md",
            _matrix("scalar-op", "operation"),
        )
        status, body = self._post_mom("scalar-op")
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    def test_domain_only_blocks_write(self):
        """project_type: [book, knowledge] → write blocked (403)."""
        self._write_pointer("domain-only", self._pointer("domain-only", "DomainOnly"))
        self._write_matrix(
            "Project Matrix DomainOnly.md",
            _matrix("domain-only", "\n  - book\n  - knowledge\n"),
        )
        status, body = self._post_mom("domain-only")
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    def test_multiple_classifications_blocks_write(self):
        """project_type: [project, operation] → write blocked (403, invalid)."""
        self._write_pointer("multi", self._pointer("multi", "Multi"))
        self._write_matrix(
            "Project Matrix Multi.md",
            _matrix("multi", "\n  - project\n  - operation\n"),
        )
        status, body = self._post_mom("multi")
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    # Every classification the MOM framework defines is editable. The gate's
    # job is to refuse an untrustworthy project_type declaration, not to refuse
    # three of the four lifecycles — a read-only pane on the user's Operations
    # was the defect these three tests used to enshrine.

    def test_operation_classification_allows_write(self):
        """project_type: [operation] → write allowed (200)."""
        self._write_pointer("op-only", self._pointer("op-only", "OpOnly"))
        self._write_matrix(
            "Operation Matrix OpOnly.md",
            _matrix("op-only", "\n  - operation\n"),
        )
        status, body = self._post_mom("op-only")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_passion_classification_allows_write(self):
        """project_type: [passion] → write allowed (200)."""
        self._write_pointer("passion", self._pointer("passion", "Passion"))
        self._write_matrix(
            "Passion Matrix Passion.md",
            _matrix("passion", "\n  - passion\n"),
        )
        status, body = self._post_mom("passion")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_incubator_classification_allows_write(self):
        """project_type: [incubator] → write allowed (200)."""
        self._write_pointer("incu", self._pointer("incu", "Incu"))
        self._write_matrix(
            "Incubator Matrix Incu.md",
            _matrix("incu", "\n  - incubator\n"),
        )
        status, body = self._post_mom("incu")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    # ---- Gate response shape ----

    def test_blocked_response_has_write_gate_field(self):
        """The 403 response includes a write_gate diagnostic field."""
        self._write_pointer("no-type", self._pointer("no-type", "NoType"))
        self._write_matrix(
            "Project Matrix NoType.md",
            _matrix("no-type", ""),
        )
        status, body = self._post_mom("no-type")
        self.assertEqual(status, 403)
        self.assertIn("write_gate", body)
        self.assertIn("classification", body["write_gate"])
        self.assertIn("schema_valid", body["write_gate"])
        self.assertIn("warnings", body["write_gate"])

    # ---- Missing Matrix (no matrix file → gate allows, write_mom creates) ----

    def test_no_matrix_file_allows_write(self):
        """When no Matrix file exists, write_mom creates one. Gate is permissive
        for missing matrices (fail-open) since write_mom handles creation."""
        self._write_pointer("new-proj", self._pointer("new-proj", "New Proj"))
        status, body = self._post_mom("new-proj")
        # write_mom creates the Matrix file when missing (create_if_missing=True).
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])


if __name__ == "__main__":
    unittest.main()
