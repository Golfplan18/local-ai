"""Dispatcher/code-execute platform integration tests.

These tests are intentionally separate from the hermetic dispatcher gate
suite: five methods launch the real platform sandbox and validate its OS-level
network and filesystem boundaries. On platforms without that sandbox they
skip explicitly; registry and unknown-tool dispatch coverage still runs.
"""

from __future__ import annotations

import json
import os
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

import dispatcher  # noqa: E402
import oversight_queue  # noqa: E402
import tool_events  # noqa: E402

_RUNTIME_WORKSPACE = Path(dispatcher.WORKSPACE)


def _read_events(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class CodeExecuteDispatchBase(unittest.TestCase):
    """Redirect dispatcher state while leaving code_execute itself live."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sink = os.path.join(self.tmp.name, "tool-events.jsonl")
        self._orig_sink = tool_events.GLOBAL_SINK_DEFAULT
        self._orig_approvals = tool_events.APPROVALS_PATH
        self._orig_queue = oversight_queue.HUMAN_QUEUE_PATH
        self._orig_permission_mode = dispatcher._permission_mode
        self._orig_approved_categories = set(dispatcher._approved_categories)
        self._orig_consecutive = (dispatcher._consecutive_tool,
                                  dispatcher._consecutive_count)
        self._orig_queued_hashes = set(tool_events._queued_hashes)
        self._orig_telemetry_health = tool_events.get_telemetry_health()
        self._orig_te_env = os.environ.pop("ORA_TOOL_EVENTS", None)
        self._orig_te_path_env = os.environ.pop("ORA_TOOL_EVENTS_PATH", None)
        tool_events.GLOBAL_SINK_DEFAULT = self.sink
        tool_events.APPROVALS_PATH = os.path.join(self.tmp.name, "appr.json")
        oversight_queue.HUMAN_QUEUE_PATH = os.path.join(
            self.tmp.name, "human-queue.jsonl")
        tool_events.reset_telemetry_health()
        tool_events._queued_hashes.clear()
        self._turn_token = tool_events.set_turn_context()
        dispatcher.reset_consecutive()
        dispatcher.set_permission_mode("auto-approve")
        self._patches = [
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
            (dispatcher._consecutive_tool,
             dispatcher._consecutive_count) = self._orig_consecutive
        finally:
            self.tmp.cleanup()

    def _events(self):
        return _read_events(self.sink)


@unittest.skipUnless(dispatcher._TOOLS_LOADED, "dispatcher tools not loaded")
class TestCodeExecute(CodeExecuteDispatchBase):
    def test_code_execute_registered_and_runs_sandboxed(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        result = dispatcher.dispatch("code_execute",
                                     {"code": "print(2**10)"})
        self.assertIn("1024", result)
        ev = [e for e in self._events() if e["action"] == "code_execute"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["enforcement_model"], "orchestrated")

    def test_code_execute_normal_output_is_unchanged(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        self.assertEqual(ce.code_execute("print('normal-result')"),
                         "normal-result")

    def test_code_execute_denies_process_fork(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        result = ce.code_execute(
            "import os\n"
            "try:\n"
            "    os.fork()\n"
            "    print('FORK-ALLOWED')\n"
            "except OSError as exc:\n"
            "    print('fork denied', type(exc).__name__)\n"
        )
        self.assertNotIn("FORK-ALLOWED", result)
        self.assertIn("fork denied", result)

    def test_code_execute_large_output_is_bounded_and_terminates(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        result = ce.code_execute(
            f"import sys\n"
            f"sys.stdout.write('x' * {ce.MAX_RESULT_BYTES * 2})\n"
            "sys.stdout.flush()\n"
            "while True: pass\n"
        )
        self.assertIn("Output truncated", result)
        self.assertIn("process terminated", result)
        self.assertLessEqual(len(result.encode()), ce.MAX_RESULT_BYTES + 128)

    def test_code_execute_timeout_terminates_and_reaps(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        self.assertEqual(ce.code_execute("while True: pass", timeout=0.1),
                         "[code_execute] Timeout after 0.1s")

    def test_code_execute_network_denied(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        result = dispatcher.dispatch("code_execute", {"code": (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
            "    print('NETWORK-OPEN')\n"
            "except Exception as e:\n"
            "    print('denied', type(e).__name__)\n")})
        self.assertNotIn("NETWORK-OPEN", result)
        self.assertIn("denied", result)

    def test_code_execute_private_home_read_denied(self):
        # Arbitrary Python must not read a non-secret private file (outside
        # scratch) and exfiltrate it via stdout — stdout is the one egress
        # the network-deny does not cover.
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        target = str(_RUNTIME_WORKSPACE / "CLAUDE.md")
        result = dispatcher.dispatch("code_execute", {"code": (
            f"try:\n"
            f"    print('LEAK:' + open({target!r}).read()[:20])\n"
            f"except Exception as e:\n"
            f"    print('read denied', type(e).__name__)\n")})
        self.assertNotIn("LEAK:", result)
        self.assertIn("denied", result)

    def test_code_execute_stdlib_and_scratch_still_work(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        result = dispatcher.dispatch("code_execute", {"code": (
            "import json, math\n"
            "print(json.dumps({'f': math.factorial(5)}))\n")})
        self.assertIn("120", result)

    def test_code_execute_workspace_write_denied(self):
        import code_execute as ce
        if not ce.sandbox_available():
            self.skipTest("platform code-execute sandbox unavailable")
        probe = str(_RUNTIME_WORKSPACE / "config" /
                    "sandbox-escape-probe")
        result = dispatcher.dispatch("code_execute", {"code": (
            f"open({probe!r}, 'w').write('x'); print('ESCAPE-OK')")})
        # The write must raise inside the sandbox (the traceback quotes the
        # source line, so assert on the outcome, not on source echoes).
        self.assertNotIn("ESCAPE-OK\n", result + "\n")
        self.assertIn("PermissionError", result)
        self.assertFalse(os.path.exists(probe))

    def test_legacy_tools_registered(self):
        self.assertIn("code_execute", dispatcher.TOOL_REGISTRY)
        # continuity_save / queue_read register when boot imports; assert
        # register_tool exists and produces valid entries either way.
        missing = object()
        previous = dispatcher.TOOL_REGISTRY.get("test_legacy", missing)
        dispatcher.register_tool(
            "test_legacy", lambda p: "ok", permission="auto",
            category="read", mutability="read", sensitivity="private",
            egress="none")
        try:
            self.assertNotIn("GATED",
                             dispatcher.dispatch("test_legacy", {}))
        finally:
            if previous is missing:
                dispatcher.TOOL_REGISTRY.pop("test_legacy", None)
            else:
                dispatcher.TOOL_REGISTRY["test_legacy"] = previous

    def test_unknown_tool_recorded(self):
        result = dispatcher.dispatch("no_such_tool", {})
        self.assertIn("Unknown tool", result)
        self.assertTrue(any(e["action"] == "no_such_tool"
                            for e in self._events()))


if __name__ == "__main__":
    unittest.main()
