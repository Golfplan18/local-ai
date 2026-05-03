#!/usr/bin/env python3
"""A/V Phase 8 — Video Editing Suggestions framework tests.

Covers two layers:

1. The heuristic generator (`video_suggestions.generate_suggestions_heuristic`)
   — verifies that filler-only segments, silence gaps, false starts, and
   topic-shift discourse markers all surface as suggestions, that the output
   is in source-time order, and that schema validation passes.

2. The Flask endpoint (`POST /api/media-library/<conv>/<entry>/suggest-edits`)
   — verifies happy path against a sandboxed media library + .whisper.json,
   404s for unknown entries / missing transcripts, and validation surfacing.

3. JSON extraction helper (`_extract_json`) — verifies the LLM-path
   parser handles markdown fences and embedded prose around the JSON.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))


class HeuristicGeneratorTests(unittest.TestCase):

    def setUp(self):
        from video_suggestions import (
            generate_suggestions_heuristic,
            validate_suggestions,
            SuggestionValidationError,
        )
        self.gen = generate_suggestions_heuristic
        self.validate = validate_suggestions
        self.SuggestionValidationError = SuggestionValidationError

    def test_filler_only_segment_yields_cut(self):
        transcript = {
            "language": "en",
            "duration_ms": 10_000,
            "segments": [
                {"start_ms": 0, "end_ms": 1500, "text": "Welcome to today's talk."},
                {"start_ms": 1500, "end_ms": 2200, "text": "um"},
                {"start_ms": 2200, "end_ms": 5000, "text": "Let's get started."},
            ],
        }
        result = self.gen(transcript, entry_id="e1")
        cuts = [s for s in result["suggestions"] if s["type"] == "cut"]
        self.assertTrue(any(c["start_ms"] == 1500 and c["end_ms"] == 2200 for c in cuts),
                        f"expected filler cut at 1500-2200, got {cuts}")
        self.assertEqual(result["entry_id"], "e1")
        self.validate(result)  # must pass schema

    def test_silence_gap_yields_cut(self):
        transcript = {
            "language": "en",
            "duration_ms": 30_000,
            "segments": [
                {"start_ms": 0, "end_ms": 2000, "text": "Welcome to the talk."},
                # 5-second silence gap
                {"start_ms": 7000, "end_ms": 9000, "text": "Now we begin."},
            ],
        }
        result = self.gen(transcript, entry_id="e1")
        cuts = [s for s in result["suggestions"] if s["type"] == "cut"]
        self.assertTrue(any(c["start_ms"] == 2000 and c["end_ms"] == 7000 for c in cuts))

    def test_chapter_marker_after_pause_with_discourse_marker(self):
        transcript = {
            "language": "en",
            "duration_ms": 600_000,
            "segments": [
                {"start_ms": 0, "end_ms": 3000, "text": "Welcome to the talk about systems."},
                {"start_ms": 3000, "end_ms": 60_000, "text": "First topic content here."},
                # pause...
                {"start_ms": 62_000, "end_ms": 70_000,
                 "text": "Okay so let's move on to the next part."},
            ],
        }
        result = self.gen(transcript, entry_id="e1")
        chapters = [s for s in result["suggestions"] if s["type"] == "chapter"]
        self.assertTrue(len(chapters) >= 1, f"expected chapter, got {result}")
        self.assertEqual(chapters[0]["at_ms"], 62_000)

    def test_no_intro_yields_title_card(self):
        transcript = {
            "language": "en",
            "duration_ms": 60_000,
            "segments": [
                # Doesn't start with welcome/hi/today/etc.
                {"start_ms": 0, "end_ms": 5000, "text": "Containers manage process isolation."},
                {"start_ms": 5000, "end_ms": 10_000,
                 "text": "Containers share the host kernel."},
                {"start_ms": 10_000, "end_ms": 15_000,
                 "text": "Containers are lighter than VMs."},
            ],
        }
        result = self.gen(transcript, entry_id="e1")
        title_cards = [s for s in result["suggestions"] if s["type"] == "title_card"]
        self.assertEqual(len(title_cards), 1)
        self.assertEqual(title_cards[0]["at_ms"], 0)
        self.assertTrue(title_cards[0]["title"])  # non-empty

    def test_intro_present_no_title_card(self):
        transcript = {
            "language": "en",
            "duration_ms": 60_000,
            "segments": [
                {"start_ms": 0, "end_ms": 5000, "text": "Welcome to today's session."},
                {"start_ms": 5000, "end_ms": 10_000, "text": "We'll cover three things."},
            ],
        }
        result = self.gen(transcript, entry_id="e1")
        title_cards = [s for s in result["suggestions"] if s["type"] == "title_card"]
        self.assertEqual(len(title_cards), 0)

    def test_empty_transcript_returns_empty_suggestions(self):
        result = self.gen({"segments": [], "duration_ms": 0}, entry_id="e1")
        self.assertEqual(result["suggestions"], [])
        self.validate(result)

    def test_results_ordered_by_source_time(self):
        transcript = {
            "language": "en",
            "duration_ms": 400_000,
            "segments": [
                {"start_ms": 0, "end_ms": 1000, "text": "Containers are fun."},
                {"start_ms": 1000, "end_ms": 1500, "text": "uh"},  # filler
                # silence gap
                {"start_ms": 5000, "end_ms": 8000, "text": "Now to the second part."},
                {"start_ms": 200_000, "end_ms": 205_000,
                 "text": "Okay, let's wrap up."},
            ],
        }
        result = self.gen(transcript, entry_id="e1")
        starts = []
        for s in result["suggestions"]:
            starts.append(s.get("start_ms") if "start_ms" in s else s.get("at_ms"))
        self.assertEqual(starts, sorted(starts))

    def test_validation_catches_malformed_cut(self):
        with self.assertRaises(self.SuggestionValidationError):
            self.validate({
                "entry_id": "e1",
                "suggestions": [
                    {"type": "cut", "start_ms": 100, "end_ms": 50, "reason": "bad"},
                ],
            })

    def test_validation_catches_unknown_type(self):
        with self.assertRaises(self.SuggestionValidationError):
            self.validate({
                "entry_id": "e1",
                "suggestions": [{"type": "explode", "reason": "x"}],
            })


class JSONExtractionTests(unittest.TestCase):
    """The LLM path parses possibly-fenced JSON out of model output."""

    def setUp(self):
        from video_suggestions import _extract_json
        self.extract = _extract_json

    def test_plain_json(self):
        out = self.extract('{"entry_id": "x", "suggestions": []}')
        self.assertEqual(out["entry_id"], "x")

    def test_markdown_fenced(self):
        raw = '```json\n{"entry_id": "x", "suggestions": []}\n```'
        out = self.extract(raw)
        self.assertEqual(out["entry_id"], "x")

    def test_unfenced_with_prose_around(self):
        raw = ('Here are the suggestions you asked for:\n'
               '{"entry_id": "x", "suggestions": [{"type": "cut", '
               '"start_ms": 0, "end_ms": 100, "reason": "noise"}]}\n'
               'Hope this helps.')
        out = self.extract(raw)
        self.assertEqual(out["entry_id"], "x")
        self.assertEqual(len(out["suggestions"]), 1)

    def test_returns_none_on_unparseable(self):
        self.assertIsNone(self.extract("not json at all"))


class SuggestEditsEndpointTests(unittest.TestCase):

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
        import media_library as ML  # noqa: WPS433
        self._ML = ML
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        self._saved_sessions_root = ML.SESSIONS_ROOT
        ML.SESSIONS_ROOT = self._tmp_path / "sessions"
        ML.SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
        ML._libraries.clear()

        from media_library import get_library
        self._saved_server_getter = self.S._get_media_library
        self.S._get_media_library = get_library
        self._saved_has_flag = self.S._HAS_MEDIA_LIBRARY
        self.S._HAS_MEDIA_LIBRARY = True

        self.client = self.S.app.test_client()
        self.conv_id = "test_conv_suggest"

    def tearDown(self):
        if self.import_ok:
            self.S._get_media_library = self._saved_server_getter
            self.S._HAS_MEDIA_LIBRARY = self._saved_has_flag
            self._ML.SESSIONS_ROOT = self._saved_sessions_root
            self._ML._libraries.clear()
            self._tmp.cleanup()

    def _add_dummy_entry(self, basename="clip.wav"):
        media_dir = self._tmp_path / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        src = media_dir / basename
        src.write_bytes(b"\x00" * 64)
        lib = self._ML.get_library(self.conv_id)
        return lib.add_entry(str(src))

    def _write_whisper_json(self, entry, content):
        json_path = Path(entry["source_path"]).with_suffix(".whisper.json")
        json_path.write_text(json.dumps(content), encoding="utf-8")
        return json_path

    def test_endpoint_happy_path(self):
        entry = self._add_dummy_entry()
        whisper_data = {
            "result": {"language": "en"},
            "transcription": [
                {"offsets": {"from": 0, "to": 1500}, "text": " Welcome to the talk."},
                {"offsets": {"from": 1500, "to": 2200}, "text": " um"},
                {"offsets": {"from": 7000, "to": 9000}, "text": " Now we begin."},
            ],
        }
        self._write_whisper_json(entry, whisper_data)

        resp = self.client.post(
            f"/api/media-library/{self.conv_id}/{entry['id']}/suggest-edits",
            json={},
        )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertEqual(data["entry_id"], entry["id"])
        self.assertIn("suggestions", data)
        cuts = [s for s in data["suggestions"] if s["type"] == "cut"]
        # Both the filler cut AND the silence gap should be present.
        self.assertTrue(len(cuts) >= 2,
                        f"expected at least 2 cuts, got {data['suggestions']}")

    def test_endpoint_unknown_entry(self):
        resp = self.client.post(
            f"/api/media-library/{self.conv_id}/notreal/suggest-edits",
            json={},
        )
        self.assertEqual(resp.status_code, 404)

    def test_endpoint_no_transcript(self):
        entry = self._add_dummy_entry()
        resp = self.client.post(
            f"/api/media-library/{self.conv_id}/{entry['id']}/suggest-edits",
            json={},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("error"), "no transcript")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
