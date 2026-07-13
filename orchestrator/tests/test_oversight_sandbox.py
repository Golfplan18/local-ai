"""Tests for the shared oversight_sandbox fixture itself.

Locks in the guarantee the fixture exists to provide: code that emits
oversight events, routes them, or writes watcher heartbeats during a
test lands in the fixture tempdir — never in the live
~/ora/data/oversight directory.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import live_guard  # noqa: E402
import oversight_actions  # noqa: E402
import oversight_events  # noqa: E402
import oversight_queue  # noqa: E402
import oversight_router  # noqa: E402
import tool_events  # noqa: E402
from unittest import mock  # noqa: E402
from oversight_sandbox import (  # noqa: E402
    _HEARTBEAT_MODULES,
    redirect_oversight_logs,
)

# Captured at import time, before any fixture patch is active. (The module
# constants stay pointed at the LIVE files by design — only the effective
# call-time paths shift under patches or the ORA_OVERSIGHT_SANDBOX guard.)
LIVE_EVENT_LOG = oversight_events.EVENT_LOG_PATH
LIVE_ROUTER_LOG = oversight_router.ROUTER_LOG_PATH
LIVE_HUMAN_QUEUE = oversight_actions.HUMAN_QUEUE_PATH
LIVE_DATA_DIRS = {
    name: __import__(name).OVERSIGHT_DATA_DIR for name in _HEARTBEAT_MODULES
}

PROBE_EVENT = "SandboxProbe"


class TestRedirectOversightLogs(unittest.TestCase):

    def setUp(self):
        self.tmpdir = redirect_oversight_logs(self)

    def test_paths_point_into_tempdir(self):
        self.assertEqual(
            oversight_events.EVENT_LOG_PATH,
            os.path.join(self.tmpdir, "events.jsonl"),
        )
        self.assertEqual(
            oversight_router.ROUTER_LOG_PATH,
            os.path.join(self.tmpdir, "router.jsonl"),
        )
        for name in _HEARTBEAT_MODULES:
            mod = __import__(name)
            self.assertEqual(
                os.path.dirname(mod.HEARTBEAT_FILE), self.tmpdir,
                f"{name}.HEARTBEAT_FILE not redirected",
            )
            self.assertEqual(
                mod.OVERSIGHT_DATA_DIR, self.tmpdir,
                f"{name}.OVERSIGHT_DATA_DIR not redirected",
            )

    def test_emit_lands_in_tempdir_not_live(self):
        oversight_events.emit({"event_type": PROBE_EVENT})
        with open(os.path.join(self.tmpdir, "events.jsonl")) as f:
            events = [json.loads(line) for line in f]
        self.assertEqual([e["event_type"] for e in events], [PROBE_EVENT])
        # Probe-absence rather than size equality: the live daemon may
        # legitimately append its own events mid-test, but never a probe.
        if os.path.isfile(LIVE_EVENT_LOG):
            with open(LIVE_EVENT_LOG) as f:
                self.assertNotIn(PROBE_EVENT, f.read())

    def test_heartbeats_land_in_tempdir(self):
        for name in _HEARTBEAT_MODULES:
            mod = __import__(name)
            mod._write_heartbeat()
        beats = {
            f for f in os.listdir(self.tmpdir)
            if f.endswith("-heartbeat.json")
        }
        self.assertEqual(
            len(beats), len(_HEARTBEAT_MODULES),
            f"expected one heartbeat per module, got {sorted(beats)}",
        )


class TestHumanQueueRedirection(unittest.TestCase):
    """The 2026-07-09 residue class: Paused-queue writes during tests.

    tool_events.gate() escalations, risk_gate task-gate holds and
    execution_loop handbacks all funnel through oversight_queue.add_entry
    (falling back to oversight_actions._append_human_queue) — 1,444 fake
    escalations reached the LIVE queue this way during the Execution Review
    build. These tests lock in the fixture's redirection of that funnel."""

    def setUp(self):
        self.tmpdir = redirect_oversight_logs(self)

    def test_add_entry_lands_in_tempdir_not_live(self):
        entry = oversight_queue.add_entry({
            "kind": "execution_gate",
            # Pre-filled name skips add_entry's synchronous model naming.
            "name": "Sandbox probe entry",
            "event": {"event_type": PROBE_EVENT},
            "verdict": {"verdict": "GATED", "reasoning": "sandbox probe"},
            "redefinition": False,
        })
        self.assertTrue(entry.id)
        with open(os.path.join(self.tmpdir, "human-queue.jsonl")) as f:
            self.assertIn(PROBE_EVENT, f.read())
        if os.path.isfile(LIVE_HUMAN_QUEUE):
            with open(LIVE_HUMAN_QUEUE) as f:
                self.assertNotIn(PROBE_EVENT, f.read())

    def test_gate_escalation_lands_in_tempdir_not_live(self):
        tool_events._queued_hashes.clear()
        self.addCleanup(tool_events._queued_hashes.clear)
        decision = tool_events.gate(
            "sandbox-probe-unknown-action", {"unknown": True},
            description="sandbox probe gate escalation")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.decision, "queued")
        with open(os.path.join(self.tmpdir, "human-queue.jsonl")) as f:
            self.assertIn("sandbox-probe-unknown-action", f.read())
        if os.path.isfile(LIVE_HUMAN_QUEUE):
            with open(LIVE_HUMAN_QUEUE) as f:
                self.assertNotIn("sandbox-probe-unknown-action", f.read())


class TestEnvQuarantineWithoutFixture(unittest.TestCase):
    """Even a test that never calls the fixture must not reach the live
    oversight files: live_guard arms ORA_OVERSIGHT_SANDBOX process-wide and
    every writer resolves its path at call time."""

    def test_live_guard_is_armed(self):
        box = os.environ.get(live_guard.ENV_VAR)
        self.assertTrue(box)
        self.assertTrue(os.path.isdir(box))

    def test_live_guard_box_is_absolute_under_tempdir(self):
        # No residue may land outside the system temp root: the armed sandbox
        # must be an absolute path so rebased sink writes never fall into cwd.
        import tempfile
        box = os.environ[live_guard.ENV_VAR]
        self.assertTrue(os.path.isabs(box), box)
        self.assertTrue(
            os.path.realpath(box).startswith(
                os.path.realpath(tempfile.gettempdir())), box)

    def test_arm_replaces_non_absolute_preset(self):
        # A relative pre-set (which would leak oversight residue into cwd) is
        # rejected and replaced with a fresh absolute tempdir; an absolute
        # pre-set is honored unchanged.
        with mock.patch.dict(os.environ,
                             {live_guard.ENV_VAR: "relative-box"}, clear=False):
            replaced = live_guard.arm()
            self.assertTrue(os.path.isabs(replaced))
            self.assertNotEqual(replaced, "relative-box")
        with mock.patch.dict(os.environ,
                             {live_guard.ENV_VAR: os.path.abspath(os.sep + "tmp")},
                             clear=False):
            self.assertEqual(live_guard.arm(), os.path.abspath(os.sep + "tmp"))

    def test_append_human_queue_quarantined(self):
        marker = "EnvQuarantineProbe"
        oversight_actions._append_human_queue({"event_type": marker})
        box = os.environ[live_guard.ENV_VAR]
        with open(os.path.join(box, "human-queue.jsonl")) as f:
            self.assertIn(marker, f.read())
        if os.path.isfile(LIVE_HUMAN_QUEUE):
            with open(LIVE_HUMAN_QUEUE) as f:
                self.assertNotIn(marker, f.read())

    def test_emit_quarantined(self):
        marker = "EnvQuarantineEmitProbe"
        oversight_events.emit({"event_type": marker})
        box = os.environ[live_guard.ENV_VAR]
        with open(os.path.join(box, "events.jsonl")) as f:
            self.assertIn(marker, f.read())
        if os.path.isfile(LIVE_EVENT_LOG):
            with open(LIVE_EVENT_LOG) as f:
                self.assertNotIn(marker, f.read())

    def test_explicit_patch_wins_over_quarantine(self):
        # Per-test path patches (the established suite idiom) must keep
        # working with the quarantine armed underneath.
        target = os.path.join(os.environ[live_guard.ENV_VAR],
                              "explicit-patch-queue.jsonl")
        with mock.patch.object(oversight_actions, "HUMAN_QUEUE_PATH", target):
            self.assertEqual(oversight_actions.human_queue_path(), target)
        # Restored: back to quarantine resolution, not the live file.
        self.assertEqual(
            oversight_actions.human_queue_path(),
            os.path.join(os.environ[live_guard.ENV_VAR], "human-queue.jsonl"))


class TestFixtureRestoresPaths(unittest.TestCase):

    def test_paths_restored_after_cleanup(self):
        class Probe(unittest.TestCase):
            def runTest(self):
                redirect_oversight_logs(self)

        probe = Probe()
        probe.setUp()
        probe.runTest()
        probe.doCleanups()
        self.assertEqual(oversight_events.EVENT_LOG_PATH, LIVE_EVENT_LOG)
        self.assertEqual(oversight_router.ROUTER_LOG_PATH, LIVE_ROUTER_LOG)
        for name in _HEARTBEAT_MODULES:
            self.assertEqual(
                __import__(name).OVERSIGHT_DATA_DIR, LIVE_DATA_DIRS[name],
                f"{name}.OVERSIGHT_DATA_DIR not restored",
            )


if __name__ == "__main__":
    unittest.main()
