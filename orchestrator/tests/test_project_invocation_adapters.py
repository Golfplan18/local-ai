"""Behavioral proofs for the exact Project execution adapters."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
ORCHESTRATOR = HERE.parents[1]
for path in (ORCHESTRATOR, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orchestrator import project_registry as pr  # noqa: E402
from orchestrator import slash_commands  # noqa: E402
import system_protection as protection  # noqa: E402
import oversight_queue  # noqa: E402
import tool_events  # noqa: E402


_TOOL = """\
import json, os, sys
marker = os.environ.get("PROJECT_TEST_MARKER")
if marker:
    with open(marker, "a", encoding="utf-8") as stream:
        stream.write("tool\\n")
print(json.dumps({"argv": sys.argv[1:]}))
"""

_STDIN_TOOL = """\
import json, os, sys
marker = os.environ.get("PROJECT_TEST_MARKER")
if marker:
    with open(marker, "a", encoding="utf-8") as stream:
        stream.write("stdin\\n")
print(json.dumps({"received": json.loads(sys.stdin.read() or "{}")}))
"""

_SLASH = """\
import os, sys
marker = os.environ.get("PROJECT_TEST_MARKER")
if marker:
    with open(marker, "a", encoding="utf-8") as stream:
        stream.write("slash\\n")
print("# Project result")
print("Args:", *sys.argv[1:])
"""

_FAIL = """\
import sys
sys.stderr.write("project failure\\n")
sys.exit(7)
"""


class ProjectAdapterBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.pointer_dir = root / "pointers"
        self.project_root = root / "project"
        tools = self.project_root / "tools"
        tools.mkdir(parents=True)
        (tools / "tool.py").write_text(_TOOL, encoding="utf-8")
        (tools / "stdin.py").write_text(_STDIN_TOOL, encoding="utf-8")
        (tools / "slash.py").write_text(_SLASH, encoding="utf-8")
        (tools / "fail.py").write_text(_FAIL, encoding="utf-8")
        (self.project_root / pr.MANIFEST_FILENAME).write_text(
            json.dumps({
                "nexus": "test-project",
                "name": "Test Project",
                "tools": [
                    {"name": "echo", "command": ["python3", "tools/tool.py"]},
                    {"name": "stdin", "command": [
                        "python3", "tools/stdin.py",
                    ], "interface": "stdin-stdout-json"},
                    {"name": "fail", "command": ["python3", "tools/fail.py"]},
                ],
                "slash_commands": [
                    {"name": "say-hi", "command": ["python3", "tools/slash.py"]},
                    {"name": "fail-slash", "command": ["python3", "tools/fail.py"]},
                ],
            }),
            encoding="utf-8",
        )
        pr.register_project(self.project_root, pointer_dir=str(self.pointer_dir))
        self.marker = root / "called.log"
        self.env = mock.patch.dict(
            os.environ,
            {
                "PROJECT_TEST_MARKER": str(self.marker),
                "ORA_HOME": str(root / "ora-home"),
                "ORA_DATA_ROOT": str(root / "data"),
            },
        )
        self.env.start()
        self._patches = [
            mock.patch.object(pr, "POINTER_DIR", str(self.pointer_dir)),
            mock.patch.object(
                protection, "_actions_path", return_value=str(root / "actions.jsonl"),
            ),
            mock.patch.object(tool_events, "APPROVALS_PATH", str(root / "approvals.json")),
            mock.patch.object(tool_events, "GLOBAL_SINK_DEFAULT", str(root / "events.jsonl")),
            mock.patch.object(oversight_queue, "HUMAN_QUEUE_PATH", str(root / "queue.jsonl")),
        ]
        for patcher in self._patches:
            patcher.start()
        self.turn_token = tool_events.set_turn_context(
            conversation_id="project-adapter-test", surface="test",
            principal_id="principal:user",
        )
        tool_events._queued_hashes.clear()

    def tearDown(self):
        tool_events._queued_hashes.clear()
        tool_events.reset_turn_context(self.turn_token)
        for patcher in reversed(self._patches):
            patcher.stop()
        self.env.stop()
        self.tmp.cleanup()

    def queue_records(self):
        path = Path(oversight_queue.HUMAN_QUEUE_PATH)
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def approve_latest(self):
        record = self.queue_records()[-1]
        result = tool_events.resolve_gate_entry(record, approve=True)
        self.assertIn("One-shot token", result)

    def dispatch(self, command):
        return slash_commands.run_runtime_command(command)

    def assert_failed_receipt(self, action):
        records = [
            json.loads(line)
            for line in Path(protection._actions_path()).read_text().splitlines()
            if line
        ]
        failed = records[-1]
        self.assertEqual(failed["event_type"], "protected_action_failed")
        starts = [
            record for record in records
            if record.get("event_type") == "protected_action_started"
            and record.get("execution_id") == failed.get("execution_id")
        ]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["request"]["action"], action)


class ProjectAdapterTests(ProjectAdapterBase):
    def test_project_tool_discovery_is_active_after_adapter_review(self):
        spec = slash_commands._find_command("/project-tool")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.status, "active")

    def test_project_tool_holds_then_executes_once_and_replay_holds(self):
        first = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", first)
        self.assertFalse(self.marker.exists())
        self.approve_latest()

        result = self.dispatch("/project-tool test-project echo one")
        self.assertIn('"one"', result)
        self.assertEqual(self.marker.read_text(), "tool\n")

        tool_events._queued_hashes.clear()
        replay = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", replay)
        self.assertEqual(self.marker.read_text(), "tool\n")

    def test_script_content_drift_does_not_reuse_approval(self):
        first = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", first)
        self.approve_latest()
        script = self.project_root / "tools" / "tool.py"
        script.write_text(_TOOL + "\n# changed after approval\n", encoding="utf-8")
        drifted = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", drifted)
        self.assertFalse(self.marker.exists())

    def test_grouped_project_tool_uses_the_same_adapter(self):
        first = self.dispatch("/projects tool test-project echo grouped")
        self.assertIn("GATED", first)
        self.approve_latest()
        result = self.dispatch("/projects tool test-project echo grouped")
        self.assertIn('"grouped"', result)
        self.assertEqual(self.marker.read_text(), "tool\n")

    def test_stdin_project_tool_binds_input_digest_without_storing_input(self):
        first = self.dispatch("/project-tool test-project stdin '{\"secret\":\"value\"}'")
        self.assertIn("GATED", first)
        queue_text = Path(oversight_queue.HUMAN_QUEUE_PATH).read_text()
        self.assertNotIn("secret", queue_text)
        self.approve_latest()
        result = self.dispatch("/project-tool test-project stdin '{\"secret\":\"value\"}'")
        self.assertIn('"value"', result)
        self.assertEqual(self.marker.read_text(), "stdin\n")
        self.assertNotIn("secret", Path(protection._actions_path()).read_text())

        tool_events._queued_hashes.clear()
        first_false = self.dispatch("/project-tool test-project stdin 'false'")
        self.assertIn("GATED", first_false)
        self.approve_latest()
        false_result = self.dispatch("/project-tool test-project stdin 'false'")
        self.assertIn('"received": false', false_result)
        self.assertEqual(self.marker.read_text(), "stdin\nstdin\n")

    def test_project_declared_slash_command_uses_exact_adapter(self):
        first = self.dispatch("/say-hi alpha")
        self.assertIn("GATED", first)
        self.assertFalse(self.marker.exists())
        self.approve_latest()
        result = self.dispatch("/say-hi alpha")
        self.assertIn("# Project result", result)
        self.assertIn("alpha", result)
        self.assertEqual(self.marker.read_text(), "slash\n")

    def test_argument_drift_does_not_reuse_approval(self):
        first = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", first)
        self.approve_latest()
        drifted = self.dispatch("/project-tool test-project echo two")
        self.assertIn("GATED", drifted)
        self.assertFalse(self.marker.exists())

    def test_manifest_drift_refuses_before_subprocess(self):
        first = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", first)
        self.approve_latest()
        manifest = self.project_root / pr.MANIFEST_FILENAME
        data = json.loads(manifest.read_text())
        data["description"] = "changed after review"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        result = self.dispatch("/project-tool test-project echo one")
        self.assertIn("no project registered", result)
        self.assertFalse(self.marker.exists())

    def test_executable_drift_refuses_inside_callback(self):
        first = self.dispatch("/project-tool test-project echo one")
        self.assertIn("GATED", first)
        self.approve_latest()
        with mock.patch.object(
            pr, "_assert_expected_binding",
            side_effect=pr.ProjectExecutionBindingError("executable drift"),
        ), mock.patch.object(pr.subprocess, "run") as run:
            result = self.dispatch("/project-tool test-project echo one")
        self.assertIn("execution refused", result)
        run.assert_not_called()

    def test_tool_failure_writes_failed_receipt(self):
        first = self.dispatch("/project-tool test-project fail")
        self.assertIn("GATED", first)
        self.approve_latest()
        result = self.dispatch("/project-tool test-project fail")
        self.assertIn("exited with code 7", result)
        self.assert_failed_receipt("project_tool_execute")

    def test_slash_failure_writes_failed_receipt(self):
        first = self.dispatch("/fail-slash")
        self.assertIn("GATED", first)
        self.approve_latest()
        result = self.dispatch("/fail-slash")
        self.assertIn("exited 7", result)
        self.assert_failed_receipt("project_slash_execute")

    def test_unknown_adapter_fails_closed_before_callback(self):
        binding = {
            "kind": "tool", "nexus": "test-project", "name": "opaque",
            "interface": "argv-stdout-json", "manifest_sha256": "sha256:" + "a" * 64,
            "command_digest": "sha256:" + "b" * 64,
            "executable_path": "/usr/bin/python3",
            "executable_identity": "sha256:" + "c" * 64,
            "args_digest": "sha256:" + "d" * 64,
            "selectors": ("project:test-project/tool:opaque",) * 6,
        }
        callback = mock.Mock()
        with self.assertRaises(protection.ProtectionDenied):
            slash_commands._protected_project_effect(
                "opaque_project_execute", binding, callback,
            )
        callback.assert_not_called()
        self.assertEqual(self.queue_records(), [])


if __name__ == "__main__":
    unittest.main()
