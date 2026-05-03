#!/usr/bin/env python3
"""A/V Phase 8 follow-up — URL import (yt-dlp) tests.

Covers:
  * URLImportManager state machine: queued → fetching_metadata →
    downloading → registering → complete (with mocked yt-dlp).
  * Progress line parsing.
  * Failure surfacing on metadata error, download error, library error.
  * Endpoint validation: missing url, malformed url, unknown import_id.

yt-dlp is mocked at the subprocess layer — tests do not hit the
network.

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))


class _FakeLibrary:
    """In-memory media-library replacement for tests."""

    def __init__(self, conversation_id):
        self.conversation_id = conversation_id
        self.entries = []

    def add_entry(self, source_path, display_name=None, mime=None):
        entry = {
            "id": "fake_" + str(len(self.entries) + 1),
            "source_path": source_path,
            "display_name": display_name or "untitled",
        }
        self.entries.append(entry)
        return entry


def _fake_lib_factory_factory():
    libs = {}

    def factory(conv_id):
        if conv_id not in libs:
            libs[conv_id] = _FakeLibrary(conv_id)
        return libs[conv_id]

    factory.libs = libs  # for inspection
    return factory


class URLImportManagerTests(unittest.TestCase):
    """Direct tests of url_import.URLImportManager with subprocess mocked."""

    def setUp(self):
        from url_import import URLImportManager  # noqa: WPS433
        self.URLImportManager = URLImportManager
        self._tmp = tempfile.TemporaryDirectory()
        self._sessions_root = Path(self._tmp.name)
        self._lib_factory = _fake_lib_factory_factory()

    def tearDown(self):
        self._tmp.cleanup()

    def _make_mgr(self):
        return self.URLImportManager(
            sessions_root=self._sessions_root,
            media_library_factory=self._lib_factory,
        )

    def _wait_for_terminal(self, mgr, import_id, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = mgr.get_state(import_id)
            if state["state"] in ("complete", "failed"):
                return state
            time.sleep(0.05)
        raise AssertionError(
            f"import {import_id} did not reach terminal state in {timeout}s"
        )

    def test_full_happy_path(self):
        """Happy path: metadata + download + register all succeed."""
        meta_json = {
            "id": "abc123",
            "title": "Sample Video",
            "duration": 125.5,
            "extractor_key": "Youtube",
        }

        # _fetch_metadata calls subprocess.run; _download calls Popen.
        meta_proc = mock.Mock()
        meta_proc.returncode = 0
        meta_proc.stdout = json.dumps(meta_json).encode("utf-8")
        meta_proc.stderr = b""

        # Build a fake Popen whose stdout iterator yields a few progress
        # lines + the final after_move:filepath line.
        download_dir = self._sessions_root / "conv1" / "imports"

        def make_download_popen(*args, **kwargs):
            # Create the file yt-dlp "downloaded".
            download_dir.mkdir(parents=True, exist_ok=True)
            output_file = download_dir / "abc123.mp4"
            output_file.write_bytes(b"\x00" * 1024)

            fake_popen = mock.Mock()
            fake_popen.stdout = io.StringIO(
                "[download] Destination: " + str(output_file) + "\n"
                "[download]  10.0% of ~  10.50MiB at  1.20MiB/s ETA 00:08\n"
                "[download]  50.0% of ~  10.50MiB at  1.20MiB/s ETA 00:04\n"
                "[download] 100.0% of ~  10.50MiB at  2.00MiB/s ETA 00:00\n"
                + str(output_file) + "\n"
            )
            fake_popen.wait = mock.Mock(return_value=0)
            fake_popen.returncode = 0
            return fake_popen

        with mock.patch("url_import.subprocess.run", return_value=meta_proc), \
             mock.patch("url_import.subprocess.Popen", side_effect=make_download_popen):
            mgr = self._make_mgr()
            import_id = mgr.start("conv1", "https://www.youtube.com/watch?v=abc123")
            state = self._wait_for_terminal(mgr, import_id)

        self.assertEqual(state["state"], "complete", state)
        self.assertEqual(state["title"], "Sample Video")
        self.assertEqual(state["video_id"], "abc123")
        self.assertEqual(state["duration_ms"], 125500)
        self.assertEqual(state["progress_pct"], 100.0)
        self.assertIsNotNone(state["library_entry_id"])
        self.assertTrue(state["output_path"].endswith("abc123.mp4"))

        # Library got the entry with the upstream title as display_name.
        lib = self._lib_factory("conv1")
        self.assertEqual(len(lib.entries), 1)
        self.assertEqual(lib.entries[0]["display_name"], "Sample Video")

    def test_metadata_failure_marks_failed(self):
        meta_proc = mock.Mock()
        meta_proc.returncode = 1
        meta_proc.stdout = b""
        meta_proc.stderr = b"Video unavailable"
        with mock.patch("url_import.subprocess.run", return_value=meta_proc):
            mgr = self._make_mgr()
            import_id = mgr.start("conv1", "https://example.com/dead")
            state = self._wait_for_terminal(mgr, import_id)
        self.assertEqual(state["state"], "failed")
        self.assertIn("metadata", state["last_error"])

    def test_download_failure_marks_failed(self):
        meta_proc = mock.Mock()
        meta_proc.returncode = 0
        meta_proc.stdout = json.dumps({
            "id": "x", "title": "T", "duration": 10,
        }).encode("utf-8")
        meta_proc.stderr = b""

        def fail_popen(*args, **kwargs):
            fake_popen = mock.Mock()
            fake_popen.stdout = io.StringIO(
                "[download] starting\n"
                "ERROR: download failed mid-stream\n"
            )
            fake_popen.wait = mock.Mock(return_value=1)
            fake_popen.returncode = 1
            return fake_popen

        with mock.patch("url_import.subprocess.run", return_value=meta_proc), \
             mock.patch("url_import.subprocess.Popen", side_effect=fail_popen):
            mgr = self._make_mgr()
            import_id = mgr.start("conv1", "https://example.com/x")
            state = self._wait_for_terminal(mgr, import_id)
        self.assertEqual(state["state"], "failed")
        self.assertIn("download", state["last_error"])

    def test_start_validates_inputs(self):
        mgr = self._make_mgr()
        with self.assertRaises(ValueError):
            mgr.start("", "https://example.com/")
        with self.assertRaises(ValueError):
            mgr.start("conv1", "")

    def test_progress_line_parsing(self):
        from url_import import _PROGRESS_RE, _to_bytes, _parse_eta
        m = _PROGRESS_RE.search(
            "[download]  42.5% of ~ 100.00MiB at 5.00MiB/s ETA 01:23"
        )
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group("pct")), 42.5)
        self.assertEqual(m.group("total_unit"), "MiB")
        self.assertEqual(_parse_eta(m.group("eta")), 83)
        self.assertEqual(_to_bytes(1, "MiB"), 1048576)
        self.assertEqual(_to_bytes(1, "KB"), 1000)

    def test_progress_line_parsing_plain_bytes(self):
        """Tiny files report sizes in plain B — must not silently skip them."""
        from url_import import _PROGRESS_RE, _to_bytes
        m = _PROGRESS_RE.search(
            "[download]  50.0% of    520.00B at 100.00B/s ETA 00:05"
        )
        self.assertIsNotNone(m, "regex must match plain-B size lines")
        self.assertEqual(m.group("total_unit"), "B")
        self.assertEqual(_to_bytes(520, "B"), 520)

    def test_progress_line_parsing_no_eta(self):
        """Completion lines drop the ETA — must still match."""
        from url_import import _PROGRESS_RE
        m = _PROGRESS_RE.search(
            "[download] 100.0% of   10.50MiB"
        )
        self.assertIsNotNone(m)
        self.assertEqual(float(m.group("pct")), 100.0)
        self.assertIsNone(m.group("eta"))


class URLImportEndpointTests(unittest.TestCase):
    """End-to-end tests for the import-url + state endpoints."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path.home() / "ora" / "server"))
        try:
            import server as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        # Inject a manager that always returns a fixed import_id without
        # really starting downloads.
        import url_import as UI  # noqa: WPS433
        self._UI = UI

        self._fake_jobs = {}

        class _FakeManager:
            def start(self_inner, conv_id, url):
                jid = "fakejob_" + str(len(self._fake_jobs) + 1)
                self._fake_jobs[jid] = {
                    "import_id": jid,
                    "conversation_id": conv_id,
                    "url": url,
                    "state": "downloading",
                    "title": "Sample",
                    "progress_pct": 25.0,
                    "library_entry_id": None,
                    "last_error": None,
                }
                return jid

            def get_state(self_inner, jid):
                if jid not in self._fake_jobs:
                    raise KeyError(jid)
                return dict(self._fake_jobs[jid])

            def list_states(self_inner, conv_id):
                return [s for s in self._fake_jobs.values()
                        if s["conversation_id"] == conv_id]

        self._fake_mgr = _FakeManager()
        self._saved_getter = self.S._get_url_import_manager
        self._saved_flag = self.S._HAS_URL_IMPORT
        self.S._get_url_import_manager = lambda: self._fake_mgr
        self.S._HAS_URL_IMPORT = True

        self.client = self.S.app.test_client()

    def tearDown(self):
        if self.import_ok:
            self.S._get_url_import_manager = self._saved_getter
            self.S._HAS_URL_IMPORT = self._saved_flag

    def test_post_starts_import_and_returns_id(self):
        resp = self.client.post(
            "/api/media-library/conv1/import-url",
            json={"url": "https://www.youtube.com/watch?v=abc"},
        )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertIn("import_id", data)
        self.assertEqual(data["conversation_id"], "conv1")

    def test_post_rejects_missing_url(self):
        resp = self.client.post(
            "/api/media-library/conv1/import-url",
            json={},
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_rejects_non_http_url(self):
        resp = self.client.post(
            "/api/media-library/conv1/import-url",
            json={"url": "javascript:alert(1)"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_state_endpoint_returns_state(self):
        resp = self.client.post(
            "/api/media-library/conv1/import-url",
            json={"url": "https://example.com/x"},
        )
        import_id = resp.get_json()["import_id"]
        resp = self.client.get(
            f"/api/media-library/conv1/import/{import_id}/state"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["state"], "downloading")
        self.assertEqual(data["progress_pct"], 25.0)

    def test_state_endpoint_404_for_unknown_id(self):
        resp = self.client.get(
            "/api/media-library/conv1/import/nosuch/state"
        )
        self.assertEqual(resp.status_code, 404)

    def test_state_endpoint_404_when_conversation_id_mismatches(self):
        resp = self.client.post(
            "/api/media-library/conv1/import-url",
            json={"url": "https://example.com/x"},
        )
        import_id = resp.get_json()["import_id"]
        # Right job_id but wrong conversation_id.
        resp = self.client.get(
            f"/api/media-library/other_conv/import/{import_id}/state"
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
