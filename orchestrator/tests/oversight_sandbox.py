"""Shared test fixture: redirect the oversight durable writes to a tempdir.

Several oversight suites exercise code that emits through
``oversight_events.emit()`` — corpus_runtime / output_runtime (runtime
events), milestone_executor (framework events), redefinition_handler
(redefinition verdicts). ``oversight_events`` holds its own module-level
log-path constants, so patching OVERSIGHT_DATA_DIR on the *other*
oversight modules does not redirect the durable write — without this
fixture every suite run appends its test events to the LIVE log at
~/ora/data/oversight/events.jsonl. Same story for ``oversight_router``'s
router.jsonl, and — the 2026-07-09 residue lesson — for the Paused queue
writers (``oversight_queue.add_entry`` fed by tool_events.gate() /
risk_gate.write_task_gate_card / execution_loop.push_handback, plus the
``oversight_actions._append_human_queue`` fallback), the actions log, the
re-eval queue, and tool_events' global sink + approvals store. The fixture
redirects ALL of those now.

The watcher / sweeper / scheduler modules carry the same trap for their
heartbeat files: each derives ``HEARTBEAT_FILE`` from its own
OVERSIGHT_DATA_DIR at import time, so a test that patches the data dir
(or nothing at all) and then triggers a sweep still overwrites the LIVE
heartbeat — which can mask a stalled daemon from oversight_health. The
fixture therefore redirects every heartbeat path as well.

Importing this module also arms the process-wide ORA_OVERSIGHT_SANDBOX
quarantine (see ``live_guard``): every durable writer resolves its path at
call time, so even a test that never calls this fixture cannot reach the
live oversight files. The fixture remains the right tool when a test needs
per-test isolation or wants to inspect what was written durably.

Usage — call FIRST in setUp, before starting any of the test's own
path patches (mock.patch restores in reverse start order, so the
fixture must be outermost). Cleanup is registered via addCleanup, so no
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
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import live_guard  # noqa: E402,F401 — arms ORA_OVERSIGHT_SANDBOX process-wide

import oversight_actions  # noqa: E402
import oversight_events  # noqa: E402
import oversight_queue  # noqa: E402
import oversight_router  # noqa: E402
import redefinition_handler  # noqa: E402
import tool_events  # noqa: E402

# Modules whose HEARTBEAT_FILE is derived from OVERSIGHT_DATA_DIR at
# import time — the single source of truth is the daemon's startup list.
from oversight_daemon import WATCHER_HEARTBEAT_MODULES as _HEARTBEAT_MODULES  # noqa: E402


def redirect_oversight_logs(test_case: unittest.TestCase) -> str:
    """Point the oversight event log, router log, and every watcher
    heartbeat (plus each watcher module's OVERSIGHT_DATA_DIR, so
    _write_heartbeat's makedirs never touches the live tree either) at a
    fresh tempdir for the duration of the test. Returns the tempdir path
    so a test can inspect what was written durably."""
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
        # Paused-queue + actions-log writers (oversight_actions owns the
        # canonical constants; oversight_queue and redefinition_handler hold
        # their own import-time bindings, so each must be patched).
        mock.patch.object(oversight_actions, "OVERSIGHT_DATA_DIR", tmpdir),
        mock.patch.object(
            oversight_actions, "HUMAN_QUEUE_PATH",
            os.path.join(tmpdir, "human-queue.jsonl"),
        ),
        mock.patch.object(
            oversight_actions, "ACTIONS_LOG_PATH",
            os.path.join(tmpdir, "actions.jsonl"),
        ),
        mock.patch.object(
            oversight_actions, "REVISE_COUNTERS_PATH",
            os.path.join(tmpdir, "revise-counters.json"),
        ),
        mock.patch.object(oversight_queue, "OVERSIGHT_DATA_DIR", tmpdir),
        mock.patch.object(
            oversight_queue, "HUMAN_QUEUE_PATH",
            os.path.join(tmpdir, "human-queue.jsonl"),
        ),
        mock.patch.object(
            oversight_queue, "REEVAL_QUEUE_PATH",
            os.path.join(tmpdir, "reeval-queue.jsonl"),
        ),
        mock.patch.object(redefinition_handler, "OVERSIGHT_DATA_DIR", tmpdir),
        mock.patch.object(
            redefinition_handler, "HUMAN_QUEUE_PATH",
            os.path.join(tmpdir, "human-queue.jsonl"),
        ),
        mock.patch.object(
            redefinition_handler, "REEVAL_QUEUE_PATH",
            os.path.join(tmpdir, "reeval-queue.jsonl"),
        ),
        mock.patch.object(
            redefinition_handler, "ARCHIVED_PEDS_LOG",
            os.path.join(tmpdir, "archived-peds.jsonl"),
        ),
        # Execution Review telemetry: the gate's tool-event sink and the
        # one-shot approval store.
        mock.patch.object(
            tool_events, "GLOBAL_SINK_DEFAULT",
            os.path.join(tmpdir, "tool-events.jsonl"),
        ),
        mock.patch.object(
            tool_events, "APPROVALS_PATH",
            os.path.join(tmpdir, "execution-approvals.json"),
        ),
    ]
    for mod_name in _HEARTBEAT_MODULES:
        module = __import__(mod_name)
        patches.append(mock.patch.object(module, "OVERSIGHT_DATA_DIR", tmpdir))
        patches.append(mock.patch.object(
            module, "HEARTBEAT_FILE",
            os.path.join(tmpdir, os.path.basename(module.HEARTBEAT_FILE)),
        ))
    for p in patches:
        p.start()
        test_case.addCleanup(p.stop)
    return tmpdir
