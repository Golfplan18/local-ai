"""Tests for workflow_spec_sweeper — stale-registration handling.

Covers the log-once-then-deregister behavior for workflows whose spec file
has vanished from disk (e.g. a smoke test registered a temp directory that
was later deleted): the drift event fires on the first missing sweep only,
subsequent misses are silent, and after the miss limit the watcher
deregisters itself by archiving the pointer file. A spec that reappears
resets the counter. Real drift on an existing spec (missing corpus
template, missing frameworks) is unaffected and still emits every sweep.
"""
import json
import os
import sys
import tempfile
import unittest
from textwrap import dedent
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
if os.path.dirname(__file__) not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

import corpus_watcher  # noqa: E402
import workflow_spec_sweeper  # noqa: E402
from oversight_sandbox import redirect_oversight_logs  # noqa: E402


MINIMAL_SPEC = dedent("""\
    ---
    type: framework
    tags: [workflow-spec]
    workflow_id: test-workflow
    workflow: Test Workflow
    ---

    # Test Workflow

    Body text.
    """)


class SweeperTestBase(unittest.TestCase):
    def setUp(self):
        redirect_oversight_logs(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self._tmp.name, "oversight")
        os.makedirs(self.data_dir)
        self.heartbeat = os.path.join(self.data_dir, "workflow-spec-sweeper-heartbeat.json")
        self._patches = [
            mock.patch.object(corpus_watcher, "OVERSIGHT_DATA_DIR", self.data_dir),
            mock.patch.object(workflow_spec_sweeper, "OVERSIGHT_DATA_DIR", self.data_dir),
            mock.patch.object(workflow_spec_sweeper, "HEARTBEAT_FILE", self.heartbeat),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._tmp.cleanup)
        for p in self._patches:
            self.addCleanup(p.stop)
        self.events = []

    def emit(self, event):
        self.events.append(event)

    def register(self, workflow_id="test-workflow", spec_path=None):
        corpus_watcher.write_workflow_pointer(
            workflow_id=workflow_id,
            project_nexus="test_project",
            workflow_spec_path=spec_path or os.path.join(self._tmp.name, "gone", "workflow-spec.md"),
            corpus_template_path="",
            corpus_instance_directory="",
        )

    def write_spec(self, filename="workflow-spec.md", content=MINIMAL_SPEC):
        path = os.path.join(self._tmp.name, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    def event_types(self):
        return [e["event_type"] if isinstance(e, dict) else e.event_type for e in self.events]


class TestMissingSpecLogOnce(SweeperTestBase):
    def test_first_missing_sweep_emits_drift_event(self):
        self.register()
        reports = workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(len(reports), 1)
        self.assertTrue(reports[0].spec_file_missing)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])

    def test_second_missing_sweep_is_silent(self):
        self.register()
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])
        state = workflow_spec_sweeper._load_missing_spec_state("test-workflow")
        self.assertEqual(state["consecutive_misses"], 2)

    def test_third_missing_sweep_deregisters(self):
        self.register()
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowWatcherDeregistered"],
        )
        # Pointer archived, workflow no longer listed, state cleaned up
        pointer = corpus_watcher.workflow_pointer_path("test-workflow")
        self.assertFalse(os.path.isfile(pointer))
        self.assertTrue(os.path.isfile(pointer + ".deregistered"))
        self.assertEqual(corpus_watcher.list_known_workflows(), [])
        self.assertIsNone(workflow_spec_sweeper._load_missing_spec_state("test-workflow"))

    def test_deregistration_event_carries_forensics(self):
        self.register()
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        evt = self.events[-1]
        self.assertEqual(evt["event_type"], "WorkflowWatcherDeregistered")
        self.assertEqual(evt["workflow_id"], "test-workflow")
        self.assertEqual(evt["project_nexus"], "test_project")
        self.assertEqual(evt["consecutive_misses"], 3)
        self.assertIn("workflow-pointer.json.deregistered", evt["pointer_tombstone"])

    def test_fourth_sweep_after_deregistration_does_nothing(self):
        self.register()
        for _ in range(4):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(len(self.events), 2)

    def test_miss_limit_env_override(self):
        self.register()
        with mock.patch.dict(os.environ, {"ORA_WORKFLOW_SWEEPER_MISSING_SPEC_SWEEPS": "5"}):
            for _ in range(4):
                workflow_spec_sweeper.sweep(emit_event=self.emit)
            self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowWatcherDeregistered"],
        )


class TestSpecReappears(SweeperTestBase):
    def test_reappearing_spec_resets_miss_counter(self):
        spec_path = os.path.join(self._tmp.name, "workflow-spec.md")
        self.register(spec_path=spec_path)
        # Two missing sweeps — one event, counter at 2
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        # Spec comes back (vault sync restored it)
        with open(spec_path, "w") as f:
            f.write(MINIMAL_SPEC)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertIsNone(workflow_spec_sweeper._load_missing_spec_state("test-workflow"))
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        # Goes missing again — the drift event fires afresh
        os.remove(spec_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowSpecDrift"],
        )


class TestRealDriftUnaffected(SweeperTestBase):
    def test_existing_spec_with_missing_template_emits_every_sweep(self):
        spec_path = self.write_spec()
        corpus_watcher.write_workflow_pointer(
            workflow_id="test-workflow",
            project_nexus="test_project",
            workflow_spec_path=spec_path,
            corpus_template_path=os.path.join(self._tmp.name, "missing-template.md"),
            corpus_instance_directory="",
        )
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowSpecDrift"],
        )
        # Never deregistered — the spec itself is present
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        self.assertIsNone(workflow_spec_sweeper._load_missing_spec_state("test-workflow"))


if __name__ == "__main__":
    unittest.main()
