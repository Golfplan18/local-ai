#!/usr/bin/env python3
"""A/V Phase 8 — media-library transcript endpoint tests.

Covers ``GET /api/media-library/<conversation_id>/<entry_id>/transcript``:
the route reads the persistent ``.whisper.json`` that ``transcription.py``
writes next to every transcribed source file and returns normalized
segments to the browser.

Cases:
  * Happy path — entry exists, ``.whisper.json`` exists → 200 + segments
    in the in-memory shape (start_ms / end_ms / text).
  * Missing transcript — entry exists but no ``.whisper.json`` → 404
    with ``{"error": "no transcript"}`` (this is the common state for
    fresh captures, so it must be a clean 404 rather than 500).
  * Unknown entry id → 404.
  * Malformed JSON on disk → 500 with a descriptive message.

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))


class TranscriptEndpoint(unittest.TestCase):
    """End-to-end tests for ``/api/media-library/.../transcript``."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path.home() / "ora" / "server"))
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
        # Sandbox the media library under a temp dir so the test never
        # touches ~/ora/sessions/. media_library.MediaLibrary computes
        # its own paths from the conversation_id; we bypass the cache
        # and instantiate one rooted at our tmp dir.
        import media_library as ML  # noqa: WPS433
        self._ML = ML
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        # Force MediaLibrary to use the tmp sessions root.
        self._saved_sessions_root = ML.SESSIONS_ROOT
        ML.SESSIONS_ROOT = self._tmp_path / "sessions"
        ML.SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)

        # Drop any cached library so the next get_library() rebuilds
        # against the patched SESSIONS_ROOT.
        ML._libraries.clear()

        # Patch the server's reference to get_media_library so it
        # routes through the same patched module.
        from media_library import get_library as _get_library
        self._saved_server_getter = self.S._get_media_library
        self.S._get_media_library = _get_library
        self._saved_has_flag = self.S._HAS_MEDIA_LIBRARY
        self.S._HAS_MEDIA_LIBRARY = True

        self.client = self.S.app.test_client()
        self.conv_id = "test_conv_phase8"

    def tearDown(self):
        self.S._get_media_library = self._saved_server_getter
        self.S._HAS_MEDIA_LIBRARY = self._saved_has_flag
        self._ML.SESSIONS_ROOT = self._saved_sessions_root
        self._ML._libraries.clear()
        self._tmp.cleanup()

    # ── helpers ──────────────────────────────────────────────────────────

    def _add_dummy_entry(self, basename="clip.wav"):
        """Create a dummy media file + library entry; return entry dict."""
        media_dir = self._tmp_path / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        src = media_dir / basename
        # Minimal valid WAV header — enough that probe doesn't crash.
        # We don't actually exercise probe in this test; an empty file
        # works because add_entry only requires .exists() to be True.
        src.write_bytes(b"\x00" * 64)
        lib = self._ML.get_library(self.conv_id)
        return lib.add_entry(str(src))

    def _write_whisper_json(self, entry, content):
        json_path = Path(entry["source_path"]).with_suffix(".whisper.json")
        json_path.write_text(json.dumps(content), encoding="utf-8")
        return json_path

    # ── tests ────────────────────────────────────────────────────────────

    def test_happy_path_returns_normalized_segments(self):
        entry = self._add_dummy_entry()
        whisper_data = {
            "result": {"language": "en"},
            "transcription": [
                {
                    "timestamps": {"from": "00:00:00,000", "to": "00:00:02,500"},
                    "offsets": {"from": 0, "to": 2500},
                    "text": " Hello world.",
                },
                {
                    "timestamps": {"from": "00:00:02,500", "to": "00:00:05,000"},
                    "offsets": {"from": 2500, "to": 5000},
                    "text": " This is the second segment.",
                },
            ],
        }
        self._write_whisper_json(entry, whisper_data)

        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/{entry['id']}/transcript"
        )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertEqual(data["entry_id"], entry["id"])
        self.assertEqual(data["language"], "en")
        self.assertEqual(data["duration_ms"], 5000)
        self.assertEqual(len(data["segments"]), 2)
        self.assertEqual(data["segments"][0], {
            "start_ms": 0,
            "end_ms": 2500,
            "text": "Hello world.",
        })
        self.assertEqual(data["segments"][1]["text"], "This is the second segment.")

    def test_missing_transcript_returns_404(self):
        entry = self._add_dummy_entry()
        # Don't write the .whisper.json file.
        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/{entry['id']}/transcript"
        )
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data.get("error"), "no transcript")

    def test_unknown_entry_returns_404(self):
        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/nonexistent_id/transcript"
        )
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data.get("error"), "unknown entry")

    def test_malformed_json_returns_500(self):
        entry = self._add_dummy_entry()
        json_path = Path(entry["source_path"]).with_suffix(".whisper.json")
        json_path.write_text("not valid json {{{", encoding="utf-8")
        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/{entry['id']}/transcript"
        )
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertIn("json parse", data.get("error", ""))

    def test_empty_text_segments_are_skipped(self):
        entry = self._add_dummy_entry()
        # whisper-cli sometimes emits a whitespace-only segment at the end.
        whisper_data = {
            "result": {"language": "en"},
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 1000},
                    "text": " Real content.",
                },
                {
                    "offsets": {"from": 1000, "to": 1100},
                    "text": "   ",  # whitespace only
                },
                {
                    "offsets": {"from": 1100, "to": 2000},
                    "text": " More content.",
                },
            ],
        }
        self._write_whisper_json(entry, whisper_data)

        resp = self.client.get(
            f"/api/media-library/{self.conv_id}/{entry['id']}/transcript"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data["segments"]), 2)
        self.assertEqual(data["segments"][0]["text"], "Real content.")
        self.assertEqual(data["segments"][1]["text"], "More content.")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
