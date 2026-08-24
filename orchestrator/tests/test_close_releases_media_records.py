"""Closing a Dialogue releases finished media records — and nothing else.

Ora keeps per-conversation records in memory for renders, transcriptions,
captures, URL imports and queued jobs, plus cached timelines and media
libraries. Until 2026-08-16 the only thing that released them was Delete
Forever, which is available on Off-Record Dialogues alone, so for every
Standard and Private Dialogue they lived for the life of the process.

Close now releases them. Close is reversible and retains data, so the release
is deliberately NOT the Delete Forever path. These tests hold that line:

  • finished records are dropped (the memory is actually released);
  • in-flight work is left completely alone — record, subprocess and all;
  • nothing is tombstoned, so a restored Dialogue can still render, record
    and import;
  • the disk-backed caches drop cleanly and reload;
  • no file is removed.

The last two matter most. If a future change makes Close call
``forget_conversation`` instead, restoring a closed Dialogue would find
rendering permanently refused — and that is exactly what these assert against.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator import job_queue  # noqa: E402
from server import app as _server_app  # noqa: E402,F401 - configures plugin context
from plugins.video.backend import media_library, timeline  # noqa: E402
from plugins.video.backend.media_capture import (  # noqa: E402
    STATE_COMPLETE as CAPTURE_COMPLETE,
    STATE_RECORDING as CAPTURE_RECORDING,
)
from plugins.video.backend.render import (  # noqa: E402
    STATE_CANCELLED,
    STATE_COMPLETE,
    STATE_FAILED,
    STATE_RENDERING,
    RenderManager,
)


class _FakeRender:
    def __init__(self, render_id, conversation_id, state):
        self.render_id = render_id
        self.conversation_id = conversation_id
        self.state = state
        self.process = None
        self.cancel_requested = False


class RenderReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mgr = RenderManager(default_export_dir=Path(self.tmp.name))
        for rid, conv, state in (
            ("r-done",      "conv-1", STATE_COMPLETE),
            ("r-failed",    "conv-1", STATE_FAILED),
            ("r-cancelled", "conv-1", STATE_CANCELLED),
            ("r-running",   "conv-1", STATE_RENDERING),
            ("r-other",     "conv-2", STATE_COMPLETE),
        ):
            self.mgr._renders[rid] = _FakeRender(rid, conv, state)

    def test_finished_records_are_released(self):
        result = self.mgr.release_finished("conv-1")
        self.assertEqual(result["renders"], 3)
        for gone in ("r-done", "r-failed", "r-cancelled"):
            self.assertNotIn(gone, self.mgr._renders)

    def test_in_flight_render_is_untouched(self):
        self.mgr.release_finished("conv-1")
        self.assertIn("r-running", self.mgr._renders,
                      "a render still in progress was released")
        self.assertFalse(self.mgr._renders["r-running"].cancel_requested,
                         "closing a Dialogue must not cancel a running render")

    def test_other_conversations_are_untouched(self):
        self.mgr.release_finished("conv-1")
        self.assertIn("r-other", self.mgr._renders)

    def test_conversation_is_not_tombstoned(self):
        """The guarantee that makes Close reversible."""
        self.mgr.release_finished("conv-1")
        self.assertEqual(
            self.mgr._deleted_conversations, set(),
            "Close tombstoned the conversation — a restored Dialogue would be "
            "permanently unable to render",
        )

    def test_release_is_case_insensitive_like_its_sibling(self):
        self.assertEqual(self.mgr.release_finished("CONV-1")["renders"], 3)

    def test_forget_conversation_still_tombstones(self):
        """Delete Forever must keep the behaviour Close deliberately avoids."""
        self.mgr.forget_conversation("conv-1")
        self.assertIn("conv-1", self.mgr._deleted_conversations)


class CaptureReleaseTests(unittest.TestCase):
    def test_a_recording_in_progress_survives_close(self):
        from plugins.video.backend.media_capture import CaptureManager

        mgr = CaptureManager()

        class _FakeCapture:
            def __init__(self, cid, conv, state):
                self.capture_id = cid
                self.conversation_id = conv
                self.state = state
                self.current_process = None
                self._deleted = False

        mgr._captures["c-done"] = _FakeCapture("c-done", "conv-1", CAPTURE_COMPLETE)
        mgr._captures["c-live"] = _FakeCapture("c-live", "conv-1", CAPTURE_RECORDING)

        mgr.release_finished("conv-1")

        self.assertNotIn("c-done", mgr._captures)
        self.assertIn("c-live", mgr._captures,
                      "a capture still recording was released mid-recording")
        self.assertFalse(mgr._captures["c-live"]._deleted)
        self.assertEqual(mgr._deleted_conversations, set())


class DiskBackedCacheReleaseTests(unittest.TestCase):
    """The two caches drop cleanly, keep their file, and do not tombstone."""

    def test_timeline_cache_release(self):
        timeline._timelines["conv-cache"] = object()
        self.assertTrue(timeline.release_timeline("conv-cache"))
        self.assertNotIn("conv-cache", timeline._timelines)
        self.assertNotIn("conv-cache", timeline._deleted_timelines)
        self.assertFalse(timeline.release_timeline("conv-cache"),
                         "releasing an absent entry should report nothing done")

    def test_media_library_cache_release(self):
        media_library._libraries["conv-cache"] = object()
        self.assertTrue(media_library.release_library("conv-cache"))
        self.assertNotIn("conv-cache", media_library._libraries)
        self.assertNotIn("conv-cache", media_library._deleted_libraries)

    def test_job_queue_release_keeps_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = job_queue.JobQueue(sessions_root=Path(tmp))
            job = q.dispatch(
                conversation_id="conv-1",
                capability="video_generates",
                parameters={"prompt": "x"},
            )
            jobs_file = Path(tmp) / "conv-1" / job_queue.JOBS_FILENAME
            self.assertTrue(jobs_file.exists())

            q.release_cached("conv-1")

            self.assertNotIn("conv-1", q._jobs, "in-memory jobs were not released")
            self.assertNotIn("conv-1", q._deleted_conversations,
                             "Close tombstoned the queue for this conversation")
            self.assertTrue(jobs_file.exists(),
                            "Close deleted jobs.json — Close must retain data")
            # And the queue rebuilds from disk, so a restored Dialogue is intact.
            self.assertEqual(len(q.list_jobs("conv-1")), 1)


if __name__ == "__main__":
    unittest.main()
