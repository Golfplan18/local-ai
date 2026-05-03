#!/usr/bin/env python3
"""WP-7.6.3 — async-cancel endpoint tests.

The §13.6 acceptance criterion is verbatim:

    Dispatch async job; click cancel; verify warning; click again;
    verify cancel signal sent and job removed.

The "click cancel" + "verify warning" + "click again" half is exercised
by ``server/static/tests/test-job-queue-cancel.js``. This Python test
covers the **server-side** cancel-signal path:

* POST /api/jobs/<id>/cancel on a queued job → returns 200 and the
  job transitions to ``cancelled`` immediately (queued cancel is
  synchronous — nothing is running, no provider billing risk).
* POST on an in-progress job → returns 200, ``cancel_requested``
  flips to True, job stays ``in_progress`` until the provider
  polling thread sees the flag and finishes the cancellation. We
  drive the polling-thread side directly via
  ``JobQueue.cancel_job`` to verify the full flow lands the job in
  the terminal cancelled state (= "job removed" once the strip's
  terminal-delay elapses on the client).
* Missing conversation_id → 400.
* Unknown job id → 404.
* Already-terminal job → 409.

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
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


class WP_7_6_3_CancelEndpoint(unittest.TestCase):
    """End-to-end tests for ``/api/jobs/<job_id>/cancel``."""

    @classmethod
    def setUpClass(cls):
        # Lazy server import — drags a lot of orchestrator code in.
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
        # Swap the module-level default queue for one rooted at a tmp
        # sessions dir so we don't touch ~/ora/sessions. Patch BOTH
        # import paths (``job_queue`` from orchestrator/ insertion +
        # ``orchestrator.job_queue`` which the server endpoint imports)
        # so they share the same singleton.
        import job_queue as JQ_short  # noqa: WPS433
        import orchestrator.job_queue as JQ_long  # noqa: WPS433
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_short = JQ_short._default_queue
        self._saved_long = JQ_long._default_queue
        # Use the long-path JobQueue class so the JobNotFound /
        # InvalidStatusTransition exceptions it raises match the
        # exception classes the server endpoint catches (the route
        # imports ``orchestrator.job_queue``, so its ``except`` clauses
        # only match that module's exception classes — not the
        # short-path duplicates).
        shared = JQ_long.JobQueue(sessions_root=self._tmp.name)
        JQ_short._default_queue = shared
        JQ_long._default_queue = shared
        self._queue = shared
        self._cid = "cid-cancel-tests"
        self.client = self.S.app.test_client()

    def tearDown(self):
        import job_queue as JQ_short  # noqa: WPS433
        import orchestrator.job_queue as JQ_long  # noqa: WPS433
        JQ_short._default_queue = self._saved_short
        JQ_long._default_queue = self._saved_long
        self._tmp.cleanup()

    # -- §13.6 cancel signal -------------------------------------------------

    def test_cancel_in_progress_job_signals_provider_thread(self):
        """The full cancel-signal path the §13.6 test calls out:

            * dispatch (async)
            * cancel POST → cancel_requested flag set, status still in_progress
            * provider polling thread observes the flag, calls cancel_job
            * job lands in terminal "cancelled" status
        """
        job = self._queue.dispatch(
            self._cid, "video_generates", {"prompt": "a sunset"},
        )
        # Mark in-progress to mirror what the provider poll thread does
        # when the prediction starts.
        self._queue.mark_in_progress(self._cid, job["id"])

        resp = self.client.post(
            f"/api/jobs/{job['id']}/cancel",
            data=json.dumps({"conversation_id": self._cid}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertTrue(payload.get("success"))
        # WP-7.6.3 contract: in-progress jobs flip cancel_requested but
        # remain in_progress until the provider polling thread confirms.
        self.assertEqual(payload["job"]["status"], "in_progress")
        self.assertTrue(payload["job"]["cancel_requested"])

        # The replicate poll thread (orchestrator/integrations/replicate.py
        # :_poll_thread) calls cancel_job once it observes the flag. We
        # invoke that directly here to verify the terminal transition
        # the user sees as "job removed" on the strip.
        self._queue.cancel_job(self._cid, job["id"])
        snap = self._queue.get_job(self._cid, job["id"])
        self.assertEqual(snap["status"], "cancelled")

    # -- Queued jobs cancel synchronously (no billing risk) ----------------

    def test_cancel_queued_job_terminates_immediately(self):
        job = self._queue.dispatch(
            self._cid, "image_generates", {"prompt": "a kitten"},
        )
        self.assertEqual(job["status"], "queued")
        resp = self.client.post(
            f"/api/jobs/{job['id']}/cancel",
            data=json.dumps({"conversation_id": self._cid}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertEqual(payload["job"]["status"], "cancelled")

    # -- Error shapes ------------------------------------------------------

    def test_missing_conversation_id_returns_400(self):
        resp = self.client.post(
            "/api/jobs/anything/cancel",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"conversation_id", resp.data)

    def test_unknown_job_returns_404(self):
        resp = self.client.post(
            "/api/jobs/does-not-exist/cancel",
            data=json.dumps({"conversation_id": self._cid}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_terminal_job_returns_409(self):
        job = self._queue.dispatch(
            self._cid, "image_generates", {"prompt": "x"},
        )
        # Drive to terminal so request_cancel raises InvalidStatusTransition.
        self._queue.mark_in_progress(self._cid, job["id"])
        self._queue.mark_complete(self._cid, job["id"], "result-ref-1")
        resp = self.client.post(
            f"/api/jobs/{job['id']}/cancel",
            data=json.dumps({"conversation_id": self._cid}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)


if __name__ == "__main__":
    unittest.main()
