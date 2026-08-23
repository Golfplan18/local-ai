"""Native-Windows dispatcher/direct-argv integration smoke.

This suite owns only the dispatcher-level seam: one-time command preparation,
gate, permission path, real handler execution, result serialization, and the
final command event. ``test_portability.TestCrossPlatformDirectArgv`` owns the
lower-level exact-argv and ``shell=False`` contracts.

Ordinary non-Windows discovery skips this module. Native acceptance requires
Git, which is already an Ora installation prerequisite.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pathlib import Path

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.append(str(_TOOLS))

import bash_execute  # noqa: E402
import dispatcher  # noqa: E402
import oversight_queue  # noqa: E402
import tool_events  # noqa: E402


def _read_events(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


@unittest.skipUnless(sys.platform == "win32" and os.name == "nt",
                     "native Windows dispatcher smoke")
class TestNativeWindowsDispatcher(unittest.TestCase):
    def setUp(self):
        # On native Windows, an import failure is a failed install—not a skip.
        self.assertTrue(
            dispatcher._TOOLS_LOADED,
            "dispatcher tool imports failed on native Windows",
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.sink = os.path.join(self.tmp.name, "tool-events.jsonl")
        self._private_root = tool_events._cmp_key(self.tmp.name)
        self._orig_sink = tool_events.GLOBAL_SINK_DEFAULT
        self._orig_approvals = tool_events.APPROVALS_PATH
        self._orig_queue = oversight_queue.HUMAN_QUEUE_PATH
        self._orig_permission_mode = dispatcher._permission_mode
        self._orig_approved_categories = set(dispatcher._approved_categories)
        self._orig_queued_hashes = set(tool_events._queued_hashes)
        self._orig_telemetry_health = tool_events.get_telemetry_health()
        self._orig_te_env = os.environ.pop("ORA_TOOL_EVENTS", None)
        self._orig_te_path_env = os.environ.pop("ORA_TOOL_EVENTS_PATH", None)
        tool_events.GLOBAL_SINK_DEFAULT = self.sink
        tool_events.APPROVALS_PATH = os.path.join(self.tmp.name, "appr.json")
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(
            self.tmp.name, "human-queue.jsonl")
        tool_events._PRIVATE_ROOTS.append(self._private_root)
        tool_events.reset_telemetry_health()
        tool_events._queued_hashes.clear()
        self._turn_token = tool_events.set_turn_context()
        dispatcher.reset_consecutive()
        dispatcher.set_permission_mode("auto-approve")
        self._patches = [
            # Orthogonal operator hooks and retired-log cleanup are not part
            # of this live seam; direct process launch stays real.
            mock.patch.object(dispatcher, "fire_hooks", return_value=[]),
            mock.patch.object(dispatcher,
                              "_retire_legacy_session_logs_once",
                              return_value=None),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self):
        try:
            for patcher in reversed(self._patches):
                patcher.stop()
            tool_events.GLOBAL_SINK_DEFAULT = self._orig_sink
            tool_events.APPROVALS_PATH = self._orig_approvals
            oversight_queue.HUMAN_QUEUE_PATH = self._orig_queue
            tool_events._queued_hashes.clear()
            tool_events._queued_hashes.update(self._orig_queued_hashes)
            with tool_events._health_lock:
                tool_events._telemetry_failures = \
                    self._orig_telemetry_health["failures"]
                tool_events._telemetry_last_error = \
                    self._orig_telemetry_health["last_error"]
            tool_events.reset_turn_context(self._turn_token)
            if self._orig_te_env is None:
                os.environ.pop("ORA_TOOL_EVENTS", None)
            else:
                os.environ["ORA_TOOL_EVENTS"] = self._orig_te_env
            if self._orig_te_path_env is None:
                os.environ.pop("ORA_TOOL_EVENTS_PATH", None)
            else:
                os.environ["ORA_TOOL_EVENTS_PATH"] = self._orig_te_path_env
            dispatcher._permission_mode = self._orig_permission_mode
            dispatcher._approved_categories.clear()
            dispatcher._approved_categories.update(
                self._orig_approved_categories)
            tool_events._PRIVATE_ROOTS.remove(self._private_root)
        finally:
            self.tmp.cleanup()

    def _events(self):
        return _read_events(self.sink)

    def test_shell_grammar_gates_before_handler(self):
        with mock.patch.object(dispatcher, "execute_command") as execute:
            result = dispatcher.dispatch(
                "bash_execute",
                {"command": "git status && git log -1",
                 "cwd": self.tmp.name},
            )

        self.assertIn("SYSTEM PROTECTION", result)
        execute.assert_not_called()
        gate_events = [e for e in self._events() if e.get("event") == "gate"]
        self.assertTrue(gate_events)
        self.assertEqual(gate_events[-1]["action"], "bash_execute")
        self.assertEqual(gate_events[-1]["mutability"], "irreversible")
        self.assertEqual(gate_events[-1]["sensitivity"], "secret")
        self.assertIn("shell operators", gate_events[-1]["gate"]["why"])
        self.assertFalse(any(e.get("event") == "shell"
                             for e in self._events()))

    def test_dispatch_direct_git_read_runs_and_records_event(self):
        git = shutil.which("git")
        self.assertIsNotNone(git, "Git is required for native Ora acceptance")
        subprocess.run(
            [git, "init", "--quiet"], cwd=self.tmp.name, check=True,
            capture_output=True, text=True,
        )
        result = dispatcher.dispatch(
            "bash_execute", {"command": "git status --short",
                             "cwd": self.tmp.name})

        payload = json.loads(result)
        self.assertEqual(payload["returncode"], 0)
        self.assertEqual(payload["stdout"], "")

        shell_events = [e for e in self._events() if e.get("event") == "shell"]
        self.assertEqual(len(shell_events), 1)
        event = shell_events[0]
        self.assertEqual(event["action"], "bash:git")
        self.assertEqual(event["gate"]["decision"], "allowed")
        self.assertTrue(event["exit"]["ok"])
        self.assertEqual(event["mutability"], "read")
        self.assertFalse(event["mutated"])

    def test_quoted_executable_and_repository_paths_bind_exact_native_argv(self):
        git = shutil.which("git")
        self.assertIsNotNone(git, "Git is required for native Ora acceptance")
        repository = os.path.join(self.tmp.name, "repository with spaces")
        os.makedirs(repository)
        subprocess.run(
            [git, "init", "--quiet"], cwd=repository, check=True,
            capture_output=True, text=True,
        )
        command = subprocess.list2cmdline([git, "-C", repository, "status", "--short"])
        prepared = bash_execute.prepare_command(command, cwd=self.tmp.name)
        self.assertEqual(
            prepared.argv,
            (os.path.realpath(git), "-C", repository, "status", "--short"),
        )
        completed = subprocess.run(
            list(prepared.argv), cwd=prepared.cwd, env=prepared.env,
            shell=False, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
