"""Shared test fixture: redirect the oversight durable logs to a tempdir.

Several oversight suites exercise code that emits through
``oversight_events.emit()`` — corpus_runtime / output_runtime (runtime
events), milestone_executor (framework events), redefinition_handler
(redefinition verdicts). ``oversight_events`` holds its own module-level
log-path constants, so patching OVERSIGHT_DATA_DIR on the *other*
oversight modules does not redirect the durable write — without this
fixture every suite run appends its test events to the LIVE log at
~/ora/data/oversight/events.jsonl. Same story for ``oversight_router``'s
router.jsonl.

Usage — call from setUp; cleanup is registered via addCleanup, so no
tearDown counterpart is needed:

    from oversight_sandbox import redirect_oversight_logs

    class MyTest(unittest.TestCase):
        def setUp(self):
            redirect_oversight_logs(self)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import oversight_events  # noqa: E402
import oversight_router  # noqa: E402


def redirect_oversight_logs(test_case: unittest.TestCase) -> str:
    """Point the oversight event log and router log at a fresh tempdir for
    the duration of the test. Returns the tempdir path so a test can
    inspect what was written durably."""
    tmpdir = tempfile.mkdtemp(prefix="ora-oversight-logs-")
    test_case.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
    patches = [
        mock.patch.object(oversight_events, "OVERSIGHT_DATA_DIR", tmpdir),
        mock.patch.object(
            oversight_events, "EVENT_LOG_PATH",
            os.path.join(tmpdir, "events.jsonl"),
        ),
        mock.patch.object(
            oversight_router, "ROUTER_LOG_PATH",
            os.path.join(tmpdir, "router.jsonl"),
        ),
    ]
    for p in patches:
        p.start()
        test_case.addCleanup(p.stop)
    return tmpdir
