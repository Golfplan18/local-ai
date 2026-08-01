#!/usr/bin/env python3
"""Retrieval embedding-rebuild job endpoints (2026-07-01).

Covers /api/retrieval/rebuild/start + /status: profile validation
(unknown id, missing dimensions, already-active), the single-job guard,
progress-line capture from the subprocess, and the requires_restart
flag on success. The heavy lifting (scripts/re-embed-local.py) is
replaced with a tiny fake script so no ChromaDB/embedder is touched.

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_retrieval_rebuild -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

FAKE_OK = """\
import sys, time
print("== knowledge ==", flush=True)
print("  progress: 500/1000 (50.0%)  rate: 99.0 docs/sec", flush=True)
time.sleep(0.1)
print("  progress: 1000/1000 (100.0%)  rate: 99.0 docs/sec", flush=True)
print("activated", flush=True)
sys.exit(0)
"""

FAKE_FAIL = """\
import sys
print("  progress: 10/1000 (1.0%)  rate: 1.0 docs/sec", flush=True)
print("FATAL: target embedder unreachable", file=sys.stderr, flush=True)
sys.exit(3)
"""

PROFILE = {
    "id": "openrouter:test/embed-model",
    "label": "Test Embed Model",
    "provider": "openrouter",
    "model": "test/embed-model",
    "dimensions": 1024,
}


class RetrievalRebuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORCHESTRATOR.parent / "server"))
        try:
            import server as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:  # pragma: no cover
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_script = self.S._REEMBED_SCRIPT
        self._saved_resolve = self.S._resolve_reembed_profile
        self.S._resolve_reembed_profile = lambda pid: (
            dict(PROFILE) if pid == PROFILE["id"] else None)
        # Reset job state between tests.
        with self.S._reembed_lock:
            self.S._reembed_state.update({
                "in_progress": False, "started_at": 0.0, "completed_at": 0.0,
                "profile_id": "", "progress": "", "last_summary": None,
            })
        self.client = self.S.app.test_client()
        import oversight_queue
        import tool_events
        from orchestrator import system_protection
        self._protection = system_protection
        self._tool_events = tool_events
        self._oversight_queue = oversight_queue
        self._vector_root = Path(self._tmp.name) / "chromadb"
        self._vector_root.mkdir()
        self._config_path = Path(self._tmp.name) / "chromadb.json"
        self._config_path.write_text("{}", encoding="utf-8")
        self._patches = [
            mock.patch.object(self.S.rp, "CHROMADB_DIR", self._vector_root),
            mock.patch.object(
                self.S._retrieval_config, "CHROMADB_CONFIG_PATH", self._config_path,
            ),
            mock.patch.object(
                system_protection, "_actions_path",
                return_value=str(Path(self._tmp.name) / "actions.jsonl"),
            ),
            mock.patch.object(
                tool_events, "APPROVALS_PATH",
                str(Path(self._tmp.name) / "approvals.json"),
            ),
            mock.patch.object(
                oversight_queue, "HUMAN_QUEUE_PATH",
                str(Path(self._tmp.name) / "queue.jsonl"),
            ),
        ]
        for patcher in self._patches:
            patcher.start()
        tool_events._queued_hashes.clear()

    def tearDown(self):
        if self.import_ok:
            self._wait_done()
            self.S._REEMBED_SCRIPT = self._saved_script
            self.S._resolve_reembed_profile = self._saved_resolve
            self._tool_events._queued_hashes.clear()
            for patcher in reversed(self._patches):
                patcher.stop()
            self._tmp.cleanup()

    def _fake_script(self, body):
        path = os.path.join(self._tmp.name, "fake-reembed.py")
        with open(path, "w") as f:
            f.write(body)
        self.S._REEMBED_SCRIPT = path
        return path

    def _start(self, profile_id=PROFILE["id"]):
        return self.client.post(
            "/api/retrieval/rebuild/start",
            data=json.dumps({"embedding_profile_id": profile_id}),
            content_type="application/json",
        )

    def _approved_start(self, profile_id=PROFILE["id"]):
        first = self._start(profile_id)
        self.assertEqual(first.status_code, 409, first.data)
        self.assertEqual(
            json.loads(first.data)["status"],
            "awaiting_system_protection_approval",
        )
        with open(self._oversight_queue.HUMAN_QUEUE_PATH, encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip()]
        result = self._tool_events.resolve_gate_entry(records[-1], approve=True)
        self.assertIn("One-shot token", result)
        return self._start(profile_id)

    def _status(self):
        return json.loads(self.client.get("/api/retrieval/rebuild/status").data)

    def _wait_done(self, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._status()["in_progress"]:
                return self._status()
            time.sleep(0.05)
        return self._status()

    # ── validation ───────────────────────────────────────────────────────

    def test_missing_profile_id_rejected(self):
        resp = self.client.post(
            "/api/retrieval/rebuild/start", data="{}",
            content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_unknown_profile_rejected(self):
        self.assertEqual(self._start("nope:missing").status_code, 400)

    def test_missing_dimensions_rejected(self):
        dimless = dict(PROFILE, dimensions=None)
        self.S._resolve_reembed_profile = lambda pid: dict(dimless)
        resp = self._start()
        self.assertEqual(resp.status_code, 400)
        self.assertIn("dimension", json.loads(resp.data)["error"])

    # ── happy path ───────────────────────────────────────────────────────

    def test_successful_rebuild_reports_progress_and_restart_flag(self):
        self._fake_script(FAKE_OK)
        resp = self._approved_start()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(json.loads(resp.data)["status"], "started")
        final = self._wait_done()
        self.assertFalse(final["in_progress"])
        summary = final["last_summary"]
        self.assertTrue(summary["ok"], summary)
        self.assertTrue(summary["requires_restart"])
        # Lines streamed through: the script's final line is what remains.
        self.assertEqual(final["progress"], "activated")

    def test_failed_rebuild_surfaces_returncode(self):
        self._fake_script(FAKE_FAIL)
        self.assertEqual(self._approved_start().status_code, 200)
        final = self._wait_done()
        summary = final["last_summary"]
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["returncode"], 3)

    # ── single-job guard ─────────────────────────────────────────────────

    def test_second_start_while_running_returns_409(self):
        slow = ("import time, sys\n"
                "print('  progress: 1/10 (10.0%)  rate: 1.0 docs/sec', flush=True)\n"
                "time.sleep(1.5)\nsys.exit(0)\n")
        self._fake_script(slow)
        self.assertEqual(self._approved_start().status_code, 200)
        time.sleep(0.2)
        second = self._start()
        self.assertEqual(second.status_code, 409)
        self.assertEqual(json.loads(second.data)["status"], "in_progress")
        self._wait_done()


if __name__ == "__main__":
    unittest.main()
