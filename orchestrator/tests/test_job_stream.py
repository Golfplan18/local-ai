#!/usr/bin/env python3
"""WP-7.6.2 — async job-queue → SSE delivery tests.

Verbatim §13.6 Python-side criterion:

    Dispatch async job; verify pending entry available for chat;
    mock completion; entry transitions to result.

Server-side this means:

    * /api/jobs/<conversation_id> hydration endpoint returns the
      job in 'queued' state immediately after dispatch.
    * The fan-out subscriber forwards every state transition to
      every live SSE consumer (we test the fan-out function directly
      since spinning up Flask in unittest is unnecessary noise).
    * On mark_complete the same fan-out fires with the result_ref
      payload — the chat panel transitions the pending entry into
      the actual result entry on this signal.

Run:

    /opt/homebrew/bin/python3 -m unittest \\
        orchestrator.tests.test_job_stream -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from job_queue import (  # noqa: E402
    JobQueue,
    STATUS_QUEUED,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETE,
    STATUS_FAILED,
)


class JobStreamFanout(unittest.TestCase):
    """The server's fan-out subscriber forwards events to every live
    SSE generator. We test the contract by emulating the same shape
    server.py uses: a list of stdlib queues, a fanout function the
    queue calls, and the per-subscriber drain loop the SSE generator
    runs."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.queue = JobQueue(sessions_root=self._tmp.name)
        self.cid = "panel-1"

        # Mirror server.py's structure — a list of stdlib queues that
        # the fanout pushes events into; one per simulated SSE client.
        import queue as _stdlib_queue
        self._stdlib_queue_mod = _stdlib_queue
        self.subscribers: list = []

        def _fanout(event):
            for sub in list(self.subscribers):
                sub.put_nowait(event)

        self.queue.subscribe(_fanout)

    def tearDown(self):
        self._tmp.cleanup()

    def _new_subscriber(self):
        q = self._stdlib_queue_mod.Queue()
        self.subscribers.append(q)
        return q

    def _drain(self, sub_q):
        out = []
        while True:
            try:
                out.append(sub_q.get_nowait())
            except self._stdlib_queue_mod.Empty:
                break
        return out

    def test_dispatch_then_complete_flows_through_to_subscribers(self):
        """§13.6: dispatch async; mock completion; entry transitions."""
        sub = self._new_subscriber()

        anchor = {"x": 64, "y": 64, "width": 256, "height": 256}
        job = self.queue.dispatch(
            self.cid, "video_generates", {"prompt": "a sunset"},
            placeholder_anchor=anchor,
        )
        # Dispatch event delivered to the subscriber.
        events = self._drain(sub)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "job_dispatched")
        self.assertEqual(events[0]["conversation_id"], self.cid)
        self.assertEqual(events[0]["job"]["id"], job["id"])
        self.assertEqual(events[0]["job"]["status"], STATUS_QUEUED)
        # placeholder_anchor round-trips so the canvas placeholder code
        # has the layout info.
        self.assertEqual(events[0]["job"]["placeholder_anchor"], anchor)

        # Hydration endpoint contract — the on-disk mirror returns the
        # job verbatim. (We exercise the queue's reader directly; the
        # Flask wrapper just JSON-dumps the same list.)
        listed = self.queue.list_jobs(self.cid)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], job["id"])
        self.assertEqual(listed[0]["status"], STATUS_QUEUED)

        # Provider transitions to in_progress.
        self.queue.mark_in_progress(self.cid, job["id"])
        events = self._drain(sub)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "status_changed")
        self.assertEqual(events[0]["previous_status"], STATUS_QUEUED)
        self.assertEqual(events[0]["job"]["status"], STATUS_IN_PROGRESS)

        # Completion — the chat panel transitions pending → result on
        # this event. result_ref is preserved verbatim so the renderer
        # can dispatch on shape (image_url, video_url, string, dict).
        result_ref = {"video_url": "https://cdn.example/sunset.mp4"}
        self.queue.mark_complete(self.cid, job["id"], result_ref)
        events = self._drain(sub)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "status_changed")
        self.assertEqual(events[0]["previous_status"], STATUS_IN_PROGRESS)
        self.assertEqual(events[0]["job"]["status"], STATUS_COMPLETE)
        self.assertEqual(events[0]["job"]["result_ref"], result_ref)

    def test_failure_transition_emits_status_changed(self):
        """A failed job must emit status_changed so the chat panel can
        render the error state in the same DOM node."""
        sub = self._new_subscriber()
        job = self.queue.dispatch(self.cid, "video_generates", {"prompt": "x"})
        self.queue.mark_in_progress(self.cid, job["id"])
        self.queue.mark_failed(self.cid, job["id"], "model timed out")

        events = self._drain(sub)
        self.assertEqual([e["type"] for e in events],
                         ["job_dispatched", "status_changed", "status_changed"])
        self.assertEqual(events[-1]["job"]["status"], STATUS_FAILED)
        self.assertEqual(events[-1]["job"]["error"], "model timed out")

    def test_multiple_subscribers_each_get_full_sequence(self):
        """Two browsers connected = two SSE streams. Both must see the
        same event order without one starving the other."""
        sub_a = self._new_subscriber()
        sub_b = self._new_subscriber()

        job = self.queue.dispatch(self.cid, "video_generates", {"prompt": "x"})
        self.queue.mark_in_progress(self.cid, job["id"])
        self.queue.mark_complete(self.cid, job["id"], {"video_url": "v"})

        for sub in (sub_a, sub_b):
            evts = self._drain(sub)
            self.assertEqual([e["type"] for e in evts],
                             ["job_dispatched", "status_changed", "status_changed"])
            self.assertEqual(evts[-1]["job"]["status"], STATUS_COMPLETE)

    def test_other_conversation_events_still_fan_out(self):
        """Server-side fan-out is conversation-agnostic; the panel
        filters by conversation_id. Verify the event reaches every
        subscriber regardless of which conversation it targets — the
        client filters."""
        sub = self._new_subscriber()
        self.queue.dispatch("other-panel", "video_generates", {"prompt": "x"})
        events = self._drain(sub)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["conversation_id"], "other-panel")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
