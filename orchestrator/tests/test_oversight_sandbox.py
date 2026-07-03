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

import oversight_events  # noqa: E402
import oversight_router  # noqa: E402
from oversight_sandbox import (  # noqa: E402
    _HEARTBEAT_MODULES,
    redirect_oversight_logs,
)

# Captured at import time, before any fixture patch is active.
LIVE_EVENT_LOG = oversight_events.EVENT_LOG_PATH
LIVE_ROUTER_LOG = oversight_router.ROUTER_LOG_PATH
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
