"""API-level failure-isolation tests for GET /api/projects/meta.

Verifies that per-record Matrix diagnostics work through the actual Flask
endpoint, including plugin-only records and one bad Matrix not failing the
entire response.
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


_VALID_PROJECT_MATRIX = """\
---
nexus:
  - good-project
project_type:
  - project
type: matrix
---

# Project Matrix Good Project

## Mission

- **Resolution Statement:** Ship the thing.

## Objectives

- To finish.

## Milestones

- [ ] Done.
"""

_AMBIGUOUS_MATRIX_A = """\
---
nexus:
  - clash
project_type:
  - project
type: matrix
---

# Project Matrix Clash A

## Mission

A.
"""

_AMBIGUOUS_MATRIX_B = """\
---
nexus:
  - clash
project_type:
  - project
type: matrix
---

# Project Matrix Clash B

## Mission

B.
"""

_INVALID_MATRIX = """\
---
nexus:
  - bad-type
project_type:
  - project
  - operation
type: matrix
---

# Project Matrix Bad Type

## Mission

Confused.
"""


class ProjectsMetaMatrixDiagnosticsTests(unittest.TestCase):
    """API-level tests for the 'matrix' field on /api/projects/meta."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.vault = self.root / "vault"
        self.matrix_dir = self.vault / "Matrix"
        self.pointer_dir = self.root / "projects"
        self.matrix_dir.mkdir(parents=True)
        self.pointer_dir.mkdir(parents=True)

        # Patch project_meta and conversation_memory to use temp dirs.
        self._orig_pointer_dir = pm.POINTER_DIR
        self._orig_sessions_root = cm._DEFAULT_SESSIONS_ROOT
        self._orig_active_data = (ap.DATA_DIR, ap.ACTIVE_PROJECT_POINTER)
        pm.POINTER_DIR = self.pointer_dir
        cm._DEFAULT_SESSIONS_ROOT = self.root / "sessions"
        cm._DEFAULT_SESSIONS_ROOT.mkdir(exist_ok=True)
        ap.DATA_DIR = self.root / "data"
        ap.ACTIVE_PROJECT_POINTER = ap.DATA_DIR / "active-project.json"

        # Patch operation_matrix to use temp vault.
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

    def _get_meta(self) -> list[dict]:
        resp = self.client.get("/api/projects/meta")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.data)
        self.assertTrue(payload["ok"])
        return payload["projects"]

    def _by_nexus(self, projects: list[dict]) -> dict[str, dict]:
        return {p["nexus"]: p for p in projects}

    # ---- Test cases ----

    def test_commons_has_missing_matrix(self):
        """Commons is synthetic — matrix field should be missing."""
        projects = self._get_meta()
        commons = next(p for p in projects if p.get("is_default"))
        self.assertEqual(commons["matrix"]["state"], "missing")
        self.assertIsNone(commons["matrix"]["classification"])

    def test_project_without_matrix_returns_missing(self):
        """A project pointer with no Matrix file returns state=missing."""
        self._write_pointer("orphan", {
            "nexus": "orphan",
            "name": "Orphan",
            "display_name": "Orphan",
            "folder_name": "Orphan",
            "status": "active",
        })
        projects = self._by_nexus(self._get_meta())
        self.assertEqual(projects["orphan"]["matrix"]["state"], "missing")

    def test_plugin_only_pointer_returns_missing(self):
        """A plugin-only pointer (root, no container metadata) returns missing."""
        self._write_pointer("msi-plugin", {
            "root": "/sites/mainstreetindependent/ora-project",
        })
        projects = self._by_nexus(self._get_meta())
        self.assertEqual(projects["msi-plugin"]["matrix"]["state"], "missing")

    def test_valid_project_matrix_returns_ok(self):
        """A project with a valid Matrix file returns state=ok."""
        self._write_pointer("good-project", {
            "nexus": "good-project",
            "name": "Good Project",
            "display_name": "Good Project",
            "folder_name": "Good Project",
            "status": "active",
        })
        self._write_matrix("Project Matrix Good Project.md", _VALID_PROJECT_MATRIX)
        projects = self._by_nexus(self._get_meta())
        gp = projects["good-project"]
        self.assertEqual(gp["matrix"]["state"], "ok")
        self.assertEqual(gp["matrix"]["classification"], "project")
        self.assertTrue(gp["matrix"]["schema_valid"])

    def test_ambiguous_matrix_returns_ambiguous(self):
        """Two Matrix files claiming the same nexus → state=ambiguous."""
        self._write_pointer("clash", {
            "nexus": "clash",
            "name": "Clash",
            "display_name": "Clash",
            "folder_name": "Clash",
            "status": "active",
        })
        self._write_matrix("Project Matrix Clash A.md", _AMBIGUOUS_MATRIX_A)
        self._write_matrix("Project Matrix Clash B.md", _AMBIGUOUS_MATRIX_B)
        projects = self._by_nexus(self._get_meta())
        self.assertEqual(projects["clash"]["matrix"]["state"], "ambiguous")
        self.assertIsNone(projects["clash"]["matrix"]["classification"])

    def test_invalid_classification_returns_invalid(self):
        """A Matrix with multiple core classifications → state=invalid."""
        self._write_pointer("bad-type", {
            "nexus": "bad-type",
            "name": "Bad Type",
            "display_name": "Bad Type",
            "folder_name": "Bad Type",
            "status": "active",
        })
        self._write_matrix("Project Matrix Bad Type.md", _INVALID_MATRIX)
        projects = self._by_nexus(self._get_meta())
        self.assertEqual(projects["bad-type"]["matrix"]["state"], "invalid")

    def test_one_bad_matrix_does_not_fail_others(self):
        """One project's invalid Matrix doesn't prevent other projects from
        getting their own matrix diagnostics."""
        self._write_pointer("good-project", {
            "nexus": "good-project",
            "name": "Good Project",
            "display_name": "Good Project",
            "folder_name": "Good Project",
            "status": "active",
        })
        self._write_pointer("bad-type", {
            "nexus": "bad-type",
            "name": "Bad Type",
            "display_name": "Bad Type",
            "folder_name": "Bad Type",
            "status": "active",
        })
        self._write_pointer("orphan", {
            "nexus": "orphan",
            "name": "Orphan",
            "display_name": "Orphan",
            "folder_name": "Orphan",
            "status": "active",
        })
        self._write_matrix("Project Matrix Good Project.md", _VALID_PROJECT_MATRIX)
        self._write_matrix("Project Matrix Bad Type.md", _INVALID_MATRIX)

        projects = self._by_nexus(self._get_meta())
        # Good project unaffected by bad one.
        self.assertEqual(projects["good-project"]["matrix"]["state"], "ok")
        self.assertEqual(projects["good-project"]["matrix"]["classification"], "project")
        # Bad project shows invalid.
        self.assertEqual(projects["bad-type"]["matrix"]["state"], "invalid")
        # Orphan shows missing.
        self.assertEqual(projects["orphan"]["matrix"]["state"], "missing")
        # Endpoint returned successfully.
        self.assertTrue(True)

    def test_mixed_ok_missing_ambiguous_invalid_all_present(self):
        """All four matrix states coexist in one response without failure."""
        self._write_pointer("good-project", {
            "nexus": "good-project", "name": "Good",
            "display_name": "Good", "folder_name": "Good", "status": "active",
        })
        self._write_pointer("orphan", {
            "nexus": "orphan", "name": "Orphan",
            "display_name": "Orphan", "folder_name": "Orphan", "status": "active",
        })
        self._write_pointer("clash", {
            "nexus": "clash", "name": "Clash",
            "display_name": "Clash", "folder_name": "Clash", "status": "active",
        })
        self._write_pointer("bad-type", {
            "nexus": "bad-type", "name": "Bad",
            "display_name": "Bad", "folder_name": "Bad", "status": "active",
        })
        self._write_matrix("Project Matrix Good Project.md", _VALID_PROJECT_MATRIX)
        self._write_matrix("Project Matrix Clash A.md", _AMBIGUOUS_MATRIX_A)
        self._write_matrix("Project Matrix Clash B.md", _AMBIGUOUS_MATRIX_B)
        self._write_matrix("Project Matrix Bad Type.md", _INVALID_MATRIX)

        projects = self._by_nexus(self._get_meta())
        states = {n: projects[n]["matrix"]["state"] for n in projects if not projects[n].get("is_default")}
        self.assertEqual(states["good-project"], "ok")
        self.assertEqual(states["orphan"], "missing")
        self.assertEqual(states["clash"], "ambiguous")
        self.assertEqual(states["bad-type"], "invalid")


if __name__ == "__main__":
    unittest.main()
