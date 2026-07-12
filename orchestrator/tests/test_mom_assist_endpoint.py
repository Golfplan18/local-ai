"""Tests for the G1.33 sub-step 5 small-model MOM assist endpoint
(POST /api/projects/<nexus>/mom-assist). The model call is stubbed; the
endpoint must be READ-ONLY (never write the matrix), parse the labeled blocks,
round-trip milestones, and degrade gracefully."""

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
from orchestrator import operation_matrix as om  # noqa: E402

_GOOD = (
    "MISSION:\nShip a useful tool.\n\n"
    "OBJECTIVES:\nReliability; clarity.\n\n"
    "MILESTONES:\n- [ ] Draft v1 by Friday\n- [x] Outline done\n"
)


class MomAssistTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._tmp.name)
        (self.vault / "Matrix").mkdir()
        self._orig_vault_env = os.environ.get("ORA_VAULT_PATH")
        os.environ["ORA_VAULT_PATH"] = str(self.vault)
        from orchestrator import project_meta as pm
        self._pm = pm
        self._orig_pointer_dir = pm.POINTER_DIR
        self._orig_projects_dir = pm.DEFAULT_VAULT_PROJECTS_DIR
        pm.POINTER_DIR = self.vault / "project-pointers"
        pm.DEFAULT_VAULT_PROJECTS_DIR = self.vault / "Projects"
        pm.create_project("My Book")
        self.client = server.app.test_client()
        self._orig_call = server._call_small_model_with_system
        self._orig_write = om.write_mom
        # Spy: fail loudly if the endpoint ever writes the matrix.
        def _no_write(*a, **k):
            raise AssertionError("mom-assist must never call write_mom")
        om.write_mom = _no_write

    def tearDown(self):
        server._call_small_model_with_system = self._orig_call
        om.write_mom = self._orig_write
        self._pm.POINTER_DIR = self._orig_pointer_dir
        self._pm.DEFAULT_VAULT_PROJECTS_DIR = self._orig_projects_dir
        if self._orig_vault_env is None:
            os.environ.pop("ORA_VAULT_PATH", None)
        else:
            os.environ["ORA_VAULT_PATH"] = self._orig_vault_env
        self._tmp.cleanup()

    def _stub(self, ret):
        server._call_small_model_with_system = lambda *a, **k: ret

    def test_commons_400_no_model_call(self):
        called = {"n": 0}
        def _spy(*a, **k):
            called["n"] += 1
            return _GOOD
        server._call_small_model_with_system = _spy
        r = self.client.post("/api/projects/commons/mom-assist", json={"intent": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(called["n"], 0)  # never calls the model

    def test_legacy_general_400_no_model_call(self):
        called = {"n": 0}
        def _spy(*a, **k):
            called["n"] += 1
            return _GOOD
        server._call_small_model_with_system = _spy
        r = self.client.post("/api/projects/general/mom-assist", json={"intent": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(called["n"], 0)  # never calls the model

    def test_good_draft_parses_and_roundtrips(self):
        prompts = []
        def _capture(prompt, *args, **kwargs):
            prompts.append(prompt)
            return _GOOD
        server._call_small_model_with_system = _capture
        r = self.client.post("/api/projects/my-book/mom-assist",
                             json={"name": "Attacker Supplied", "intent": "a tool"})
        self.assertEqual(r.status_code, 200)
        s = json.loads(r.data)["suggestions"]
        self.assertEqual(s["mission"], "Ship a useful tool.")
        self.assertIn("Reliability", s["objectives"])
        self.assertEqual(len(s["milestones"]), 2)
        self.assertEqual(s["milestones"][0]["text"], "Draft v1 by Friday")
        self.assertTrue(s["milestones"][1]["done"])
        self.assertIn("Project name: My Book", prompts[0])
        self.assertNotIn("Attacker Supplied", prompts[0])
        # milestones_raw is the canonical round-trip of the parsed list.
        self.assertEqual(
            s["milestones_raw"],
            om.render_milestones(s["milestones"]).strip(),
        )

    def test_strips_code_fences(self):
        self._stub("```\n" + _GOOD + "\n```")
        r = self.client.post("/api/projects/my-book/mom-assist", json={"name": "My Book"})
        s = json.loads(r.data)["suggestions"]
        self.assertEqual(s["mission"], "Ship a useful tool.")

    def test_model_unavailable_503(self):
        self._stub(None)
        r = self.client.post("/api/projects/my-book/mom-assist", json={"name": "My Book"})
        self.assertEqual(r.status_code, 503)
        self.assertFalse(json.loads(r.data)["ok"])

    def test_unparseable_502_after_retry(self):
        calls = {"n": 0}
        def _spy(*a, **k):
            calls["n"] += 1
            return "I cannot help with that."  # no MISSION/OBJECTIVES labels
        server._call_small_model_with_system = _spy
        r = self.client.post("/api/projects/my-book/mom-assist", json={"name": "My Book"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(calls["n"], 2)  # one-shot retry happened

    def test_partial_blocks_ok(self):
        # Mission only (no milestones) still parses — milestones default empty.
        self._stub("MISSION:\nJust a mission.\nOBJECTIVES:\nOne focus.")
        r = self.client.post("/api/projects/my-book/mom-assist", json={"name": "My Book"})
        self.assertEqual(r.status_code, 200)
        s = json.loads(r.data)["suggestions"]
        self.assertEqual(s["mission"], "Just a mission.")
        self.assertEqual(s["milestones"], [])

    def test_parse_blocks_unit(self):
        m, o, ms = server._parse_mom_blocks(_GOOD)
        self.assertEqual(m, "Ship a useful tool.")
        self.assertIn("clarity", o)
        self.assertIn("- [ ] Draft v1 by Friday", ms)
        # Nothing parseable → all None.
        self.assertEqual(server._parse_mom_blocks("nope"), (None, None, None))


if __name__ == "__main__":
    unittest.main()
