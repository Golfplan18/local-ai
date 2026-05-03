#!/usr/bin/env python3
"""WP-7.6.1 — async job queue tests.

The §13.6 acceptance criterion is:

    Dispatch 2 async jobs; both visible in queue; placeholders on
    canvas; mock completion of one; queue and placeholder update.

The Python side covers the queue half (dispatch + visible-in-queue +
mock-completion + on-disk persistence + event emission). The
canvas-placeholder half is server-agnostic JavaScript exercised in the
client test harness — a small jsdom suite at
``server/static/tests/job-queue.test.js`` runs alongside the existing
ora-visual-compiler tests via ``run.js`` (added separately).

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from job_queue import (  # noqa: E402
    JobQueue,
    JobNotFound,
    InvalidStatusTransition,
    STATUS_QUEUED,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETE,
    STATUS_CANCELLED,
    STATUS_FAILED,
    get_default_queue,
)


# ---------------------------------------------------------------------------
# §13.6 acceptance criterion (Python-side coverage)
# ---------------------------------------------------------------------------

class WP_7_6_1_AcceptanceCriterion(unittest.TestCase):
    """Verbatim §13.6 test:

        Dispatch 2 async jobs; both visible in queue; placeholders on
        canvas; mock completion of one; queue and placeholder update.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.queue = JobQueue(sessions_root=self._tmp.name)
        self.events = []
        self.queue.subscribe(self.events.append)
        self.cid = "main"

    def tearDown(self):
        self._tmp.cleanup()

    def test_two_dispatch_one_complete_queue_and_placeholder_update(self):
        # Dispatch two async jobs with explicit placeholder anchors —
        # the anchors round-trip to the JS placeholder renderer.
        anchor_a = {"x": 100, "y": 100, "width": 256, "height": 256}
        anchor_b = {"x": 400, "y": 100, "width": 256, "height": 256}

        job_a = self.queue.dispatch(
            self.cid, "video_generates", {"prompt": "a sunset"},
            placeholder_anchor=anchor_a,
        )
        job_b = self.queue.dispatch(
            self.cid, "style_trains", {"images": ["a.png", "b.png"]},
            placeholder_anchor=anchor_b,
        )

        # Both visible in queue.
        active = self.queue.list_active_jobs(self.cid)
        self.assertEqual(len(active), 2,
                         "Both jobs should be visible in the active queue")
        ids = {j["id"] for j in active}
        self.assertEqual(ids, {job_a["id"], job_b["id"]})

        # Placeholder anchors persisted (the JS side reads these via
        # the hydration endpoint).
        for j, expected in [(active[0], anchor_a), (active[1], anchor_b)]:
            self.assertEqual(j["placeholder_anchor"], expected)

        # Mock completion of one — A.
        result_ref = {"image_id": "canvas-img-42", "url": "/uploads/sunset.mp4"}
        updated = self.queue.mark_complete(self.cid, job_a["id"], result_ref)
        self.assertEqual(updated["status"], STATUS_COMPLETE)
        self.assertEqual(updated["result_ref"], result_ref)

        # Queue update: A is no longer in active list, B still is.
        active_after = self.queue.list_active_jobs(self.cid)
        self.assertEqual(len(active_after), 1)
        self.assertEqual(active_after[0]["id"], job_b["id"])

        # Full list still has both — completion preserves history.
        full = self.queue.list_jobs(self.cid)
        self.assertEqual(len(full), 2)

        # Placeholder update is signalled via events — the JS layer
        # listens to the SSE bridge and calls Konva.
        event_types = [e["type"] for e in self.events]
        self.assertEqual(event_types,
                         ["job_dispatched", "job_dispatched", "status_changed"])

        last = self.events[-1]
        self.assertEqual(last["job"]["id"], job_a["id"])
        self.assertEqual(last["job"]["status"], STATUS_COMPLETE)
        self.assertEqual(last["previous_status"], STATUS_QUEUED)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class JobQueuePersistenceTests(unittest.TestCase):
    """jobs.json round-trips and survives a fresh JobQueue instance —
    mirroring a server restart (per §13.6 deliverable 5)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_dispatch_writes_jobs_json(self):
        q = JobQueue(sessions_root=self.root)
        q.dispatch("alpha", "video_generates", {"prompt": "x"})
        path = Path(self.root) / "alpha" / "jobs.json"
        self.assertTrue(path.exists())
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["capability"], "video_generates")
        self.assertEqual(data[0]["status"], STATUS_QUEUED)

    def test_jobs_survive_server_restart(self):
        """Drop the queue, build a fresh one against the same dir; jobs
        should rehydrate with full state."""
        q1 = JobQueue(sessions_root=self.root)
        a = q1.dispatch("conv1", "video_generates", {"prompt": "p"})
        q1.mark_in_progress("conv1", a["id"])
        del q1

        q2 = JobQueue(sessions_root=self.root)
        jobs = q2.list_jobs("conv1")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], a["id"])
        self.assertEqual(jobs[0]["status"], STATUS_IN_PROGRESS)
        self.assertIsNotNone(jobs[0]["started_at"])

    def test_session_slug_strips_unsafe_chars(self):
        """The slug rule mirrors server.py's _vision_retry_queue_path."""
        q = JobQueue(sessions_root=self.root)
        q.dispatch("conv with/slash", "video_generates", {"prompt": "p"})
        # Resulting directory must not contain forbidden chars.
        contents = os.listdir(self.root)
        self.assertEqual(len(contents), 1)
        slug = contents[0]
        for bad in [" ", "/"]:
            self.assertNotIn(bad, slug)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class JobQueueStateMachineTests(unittest.TestCase):
    """Permitted and forbidden transitions."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.q = JobQueue(sessions_root=self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_happy_path(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.q.mark_complete("c", j["id"], "result-id-42")
        out = self.q.get_job("c", j["id"])
        self.assertEqual(out["status"], STATUS_COMPLETE)
        self.assertEqual(out["result_ref"], "result-id-42")
        self.assertIsNotNone(out["completed_at"])

    def test_failure_path(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.q.mark_failed("c", j["id"], "provider 5xx")
        out = self.q.get_job("c", j["id"])
        self.assertEqual(out["status"], STATUS_FAILED)
        self.assertEqual(out["error"], "provider 5xx")

    def test_request_cancel_while_queued_cancels_immediately(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.request_cancel("c", j["id"])
        self.assertEqual(self.q.get_job("c", j["id"])["status"], STATUS_CANCELLED)

    def test_request_cancel_while_in_progress_flags_only(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.q.request_cancel("c", j["id"])
        out = self.q.get_job("c", j["id"])
        self.assertEqual(out["status"], STATUS_IN_PROGRESS)
        self.assertTrue(out["cancel_requested"])

    def test_force_cancel_terminates_in_progress(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.q.cancel_job("c", j["id"])
        self.assertEqual(self.q.get_job("c", j["id"])["status"], STATUS_CANCELLED)

    def test_cannot_complete_already_terminal(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.q.mark_complete("c", j["id"], "r")
        with self.assertRaises(InvalidStatusTransition):
            self.q.mark_complete("c", j["id"], "r2")
        with self.assertRaises(InvalidStatusTransition):
            self.q.mark_failed("c", j["id"], "e")
        with self.assertRaises(InvalidStatusTransition):
            self.q.cancel_job("c", j["id"])

    def test_unknown_job_raises(self):
        with self.assertRaises(JobNotFound):
            self.q.mark_complete("c", "no-such-id", "r")


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

class JobQueueEventBusTests(unittest.TestCase):
    """``subscribe`` fires a synchronous handler on each transition."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.q = JobQueue(sessions_root=self._tmp.name)
        self.events = []
        self.unsubscribe = self.q.subscribe(self.events.append)

    def tearDown(self):
        self._tmp.cleanup()

    def test_dispatch_emits_job_dispatched(self):
        self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["type"], "job_dispatched")
        self.assertEqual(self.events[0]["conversation_id"], "c")

    def test_status_change_emits_status_changed_with_previous(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.q.mark_complete("c", j["id"], "r")
        self.assertEqual([e["type"] for e in self.events],
                         ["job_dispatched", "status_changed", "status_changed"])
        self.assertEqual(self.events[1]["previous_status"], STATUS_QUEUED)
        self.assertEqual(self.events[2]["previous_status"], STATUS_IN_PROGRESS)

    def test_request_cancel_in_progress_emits_cancel_requested(self):
        j = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.q.mark_in_progress("c", j["id"])
        self.events.clear()
        self.q.request_cancel("c", j["id"])
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["type"], "cancel_requested")

    def test_unsubscribe_stops_delivery(self):
        self.unsubscribe()
        self.q.dispatch("c", "video_generates", {"prompt": "x"})
        self.assertEqual(len(self.events), 0)

    def test_subscriber_error_does_not_break_others(self):
        bad = lambda evt: (_ for _ in ()).throw(RuntimeError("boom"))
        self.q.subscribe(bad)
        good_events = []
        self.q.subscribe(good_events.append)
        self.q.dispatch("c", "video_generates", {"prompt": "x"})
        # bad subscriber errored; both the original `events` and `good_events`
        # still received the event.
        self.assertEqual(len(good_events), 1)
        self.assertEqual(len(self.events), 1)


# ---------------------------------------------------------------------------
# Multi-conversation reach (used by the global queue strip)
# ---------------------------------------------------------------------------

class JobQueueMultiConversationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.q = JobQueue(sessions_root=self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_active_across_conversations(self):
        self.q.dispatch("alpha", "video_generates", {"prompt": "a"})
        self.q.dispatch("beta", "style_trains", {"images": []})
        bravo_done = self.q.dispatch("beta", "video_generates", {"prompt": "b"})
        self.q.mark_complete("beta", bravo_done["id"], "r")

        out = self.q.list_all_active_across_conversations()
        self.assertIn("alpha", out)
        self.assertIn("beta", out)
        self.assertEqual(len(out["alpha"]), 1)
        self.assertEqual(len(out["beta"]), 1)
        self.assertEqual(out["beta"][0]["capability"], "style_trains")

    def test_purge_terminal_drops_done_jobs(self):
        a = self.q.dispatch("c", "video_generates", {"prompt": "x"})
        b = self.q.dispatch("c", "video_generates", {"prompt": "y"})
        self.q.mark_complete("c", a["id"], "r")
        removed = self.q.purge_terminal("c")
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.q.list_jobs("c")), 1)
        self.assertEqual(self.q.list_jobs("c")[0]["id"], b["id"])


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

class DefaultQueueTests(unittest.TestCase):
    def test_singleton_returns_same_instance(self):
        q1 = get_default_queue()
        q2 = get_default_queue()
        self.assertIs(q1, q2)


if __name__ == "__main__":
    unittest.main()
