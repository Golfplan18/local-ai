"""Tests for workflow_spec_sweeper — stale-registration handling + drift dedup.

Covers the log-once-then-deregister behavior for workflows whose spec file
has vanished from disk, the two deregistration gates (consecutive-miss count
AND minimum elapsed time), the tombstone-restore self-heal, signature-deduped
emission for persistent drift on an existing spec, observation-only sweeps
(no emitter → no persistence), episode binding to the pointer's registered_at,
and resilience to corrupt sidecar state.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
            # Pin the user-facing tunables so suite results don't depend on
            # ambient shell exports. MIN_SEC=0 keeps the count gate testable
            # without time travel; the gate itself has dedicated tests.
            mock.patch.dict(os.environ, {
                "ORA_WORKFLOW_SWEEPER_MISSING_SPEC_SWEEPS": "3",
                "ORA_WORKFLOW_SWEEPER_MISSING_SPEC_MIN_SEC": "0",
            }),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._tmp.cleanup)
        for p in self._patches:
            self.addCleanup(p.stop)
        self.events = []

    def emit(self, event):
        self.events.append(event)

    def register(self, workflow_id="test-workflow", spec_path=None, template_path=""):
        corpus_watcher.write_workflow_pointer(
            workflow_id=workflow_id,
            project_nexus="test_project",
            workflow_spec_path=spec_path if spec_path is not None
            else os.path.join(self._tmp.name, "gone", "workflow-spec.md"),
            corpus_template_path=template_path,
            corpus_instance_directory="",
        )

    def write_spec(self, filename="workflow-spec.md", content=MINIMAL_SPEC):
        path = os.path.join(self._tmp.name, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    def event_types(self):
        return [e["event_type"] if isinstance(e, dict) else e.event_type for e in self.events]

    def read_state(self, workflow_id="test-workflow"):
        path = workflow_spec_sweeper._sweeper_state_path(workflow_id)
        if not os.path.isfile(path):
            return None
        with open(path) as f:
            return json.load(f)


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
        state = self.read_state()
        self.assertEqual(state["consecutive_misses"], 2)
        self.assertTrue(state["drift_emitted"])

    def test_third_missing_sweep_deregisters(self):
        self.register()
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowWatcherDeregistered"],
        )
        pointer = corpus_watcher.workflow_pointer_path("test-workflow")
        self.assertFalse(os.path.isfile(pointer))
        self.assertTrue(os.path.isfile(pointer + ".deregistered"))
        self.assertEqual(corpus_watcher.list_known_workflows(), [])
        self.assertIsNone(self.read_state())

    def test_deregistration_event_carries_forensics(self):
        self.register()
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        evt = self.events[-1]
        self.assertEqual(evt["event_type"], "WorkflowWatcherDeregistered")
        self.assertEqual(evt["workflow_id"], "test-workflow")
        self.assertEqual(evt["project_nexus"], "test_project")
        self.assertEqual(evt["consecutive_misses"], 3)
        self.assertTrue(evt["first_missed_at"])
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

    def test_elapsed_time_gate_blocks_rapid_deregistration(self):
        """Back-to-back sweeps (CLI runs, concurrent sessions) can satisfy the
        count gate in seconds but must not deregister before the elapsed-time
        gate — the wall-clock grace window — is met."""
        self.register()
        with mock.patch.dict(os.environ, {"ORA_WORKFLOW_SWEEPER_MISSING_SPEC_MIN_SEC": "3600"}):
            for _ in range(5):
                workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        self.assertEqual(self.read_state()["consecutive_misses"], 5)

    def test_elapsed_time_gate_allows_deregistration_once_window_passed(self):
        self.register()
        with mock.patch.dict(os.environ, {"ORA_WORKFLOW_SWEEPER_MISSING_SPEC_MIN_SEC": "600"}):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
            # Backdate the episode start past the window.
            state = self.read_state()
            state["first_missed_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=700)
            ).isoformat()
            workflow_spec_sweeper._save_sweeper_state("test-workflow", state)
            workflow_spec_sweeper.sweep(emit_event=self.emit)
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowWatcherDeregistered"],
        )


class TestSelfHeal(SweeperTestBase):
    def test_reappearing_spec_resets_miss_counter(self):
        spec_path = os.path.join(self._tmp.name, "workflow-spec.md")
        self.register(spec_path=spec_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        # Spec comes back (vault sync restored it) → healthy sweep clears state
        with open(spec_path, "w") as f:
            f.write(MINIMAL_SPEC)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertIsNone(self.read_state())
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        # Goes missing again — a fresh episode emits afresh
        os.remove(spec_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowSpecDrift"],
        )

    def test_tombstone_restored_when_spec_reappears(self):
        """The self-heal for a false-positive drop lives in the sweeper: the
        next sweep after the spec reappears restores the archived pointer —
        no daemon restart, no dependency on the vault scan roots."""
        spec_path = os.path.join(self._tmp.name, "workflow-spec.md")
        self.register(spec_path=spec_path)
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(corpus_watcher.list_known_workflows(), [])
        with open(spec_path, "w") as f:
            f.write(MINIMAL_SPEC)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowWatcherDeregistered", "WorkflowWatcherReregistered"],
        )
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        pointer = corpus_watcher.load_workflow_pointer("test-workflow")
        self.assertEqual(pointer["workflow_spec_path"], spec_path)
        self.assertFalse(os.path.isfile(
            corpus_watcher.workflow_pointer_path("test-workflow") + ".deregistered"))
        # Healthy from then on — no further events
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(len(self.events), 3)

    def test_tombstone_not_restored_while_spec_still_missing(self):
        self.register()
        for _ in range(4):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(corpus_watcher.list_known_workflows(), [])
        self.assertTrue(os.path.isfile(
            corpus_watcher.workflow_pointer_path("test-workflow") + ".deregistered"))

    def test_tombstone_left_alone_when_workflow_reregistered_independently(self):
        spec_path = os.path.join(self._tmp.name, "workflow-spec.md")
        self.register(spec_path=spec_path)
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        # Manual/programmatic re-registration writes a fresh pointer
        with open(spec_path, "w") as f:
            f.write(MINIMAL_SPEC)
        self.register(spec_path=spec_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertNotIn("WorkflowWatcherReregistered", self.event_types())
        self.assertTrue(os.path.isfile(
            corpus_watcher.workflow_pointer_path("test-workflow") + ".deregistered"))
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])


class TestEpisodeBinding(SweeperTestBase):
    def test_stale_state_discarded_on_reregistration(self):
        """Sidecar state recorded against an older registration must not be
        inherited — a re-registered workflow starts a fresh episode with the
        full grace window and its own first-detection drift event."""
        self.register()
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.read_state()["consecutive_misses"], 2)
        # Re-register (new registered_at), spec still missing
        self.register()
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(
            self.event_types(),
            ["WorkflowSpecDrift", "WorkflowSpecDrift"],
        )
        self.assertEqual(self.read_state()["consecutive_misses"], 1)
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])


class TestObservationOnlyMode(SweeperTestBase):
    def test_no_emitter_sweep_is_read_only(self):
        """sweep(None) must never consume the grace window, mark emission
        state, deregister, or even write the heartbeat — an emitter-less run
        only reports."""
        self.register()
        reports = workflow_spec_sweeper.sweep()
        workflow_spec_sweeper.sweep()
        self.assertIsNone(self.read_state())
        self.assertEqual(len(reports), 1)
        self.assertFalse(os.path.isfile(self.heartbeat))
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        # The first emitter-bearing sweep is still the first detection
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])
        self.assertEqual(self.read_state()["consecutive_misses"], 1)

    def test_emitter_sweep_writes_heartbeat(self):
        self.register()
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertTrue(os.path.isfile(self.heartbeat))


class TestPersistentDriftDedup(SweeperTestBase):
    def test_existing_spec_with_missing_template_emits_once(self):
        spec_path = self.write_spec()
        self.register(
            spec_path=spec_path,
            template_path=os.path.join(self._tmp.name, "missing-template.md"),
        )
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])
        # Never deregistered — the spec itself is present
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        self.assertTrue(self.read_state()["last_issue_signature"])

    def test_changed_issue_set_emits_again(self):
        spec_path = self.write_spec()
        self.register(
            spec_path=spec_path,
            template_path=os.path.join(self._tmp.name, "missing-template.md"),
        )
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(len(self.events), 1)
        # The drift changes shape: different missing template path, same
        # registration (preserve registered_at so the episode binding holds).
        pointer_path = corpus_watcher.workflow_pointer_path("test-workflow")
        with open(pointer_path) as f:
            pointer = json.load(f)
        pointer["corpus_template_path"] = os.path.join(self._tmp.name, "other-template.md")
        with open(pointer_path, "w") as f:
            json.dump(pointer, f, indent=2)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift", "WorkflowSpecDrift"])

    def test_resolved_drift_clears_state_and_reemits_on_recurrence(self):
        spec_path = self.write_spec()
        template_path = os.path.join(self._tmp.name, "template.md")
        self.register(spec_path=spec_path, template_path=template_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(len(self.events), 1)
        # Template appears → healthy → state cleared
        with open(template_path, "w") as f:
            f.write("# Template\n")
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertIsNone(self.read_state())
        # Template vanishes again → same signature, but it's a new episode
        os.remove(template_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift", "WorkflowSpecDrift"])

    def test_corpus_only_registration_emits_nothing_and_never_deregisters(self):
        """A deliberately blank spec path is a tolerated configuration
        (corpus_watcher treats the spec as optional) — the spec sweeper has no
        jurisdiction, so it must emit NO drift event (no severe WorkflowSpecDrift
        routed to Process Coherence) and must never auto-deregister."""
        self.register(spec_path="")
        for _ in range(4):
            reports = workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.events, [])
        self.assertEqual(reports[0].issues, [])
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])

    def test_drift_then_blink_then_single_miss_does_not_bypass_gates(self):
        """Regression: a persistent-drift signature and a missing-spec episode
        must never coexist in the sidecar. If they did, a later single miss
        would inherit stale counters and deregister on the first miss with the
        gates bypassed and the fresh drift event suppressed."""
        spec_path = self.write_spec()
        template_path = os.path.join(self._tmp.name, "missing-template.md")
        self.register(spec_path=spec_path, template_path=template_path)
        # Persistent drift S (missing template) — logs once.
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        # Spec blinks missing for two sweeps (accumulates a missing episode).
        os.remove(spec_path)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        # Spec returns with the SAME drift S.
        self.write_spec()
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        state = self.read_state()
        # The sidecar must now hold a drift-only record — no missing-spec keys.
        for k in ("consecutive_misses", "first_missed_at", "drift_emitted"):
            self.assertNotIn(k, state)
        # A single later miss starts a fresh episode: it emits a first-detection
        # drift and does NOT deregister on that one miss.
        os.remove(spec_path)
        events_before = len(self.events)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        self.assertEqual(self.read_state()["consecutive_misses"], 1)
        self.assertEqual(self.event_types()[events_before:], ["WorkflowSpecDrift"])


class TestResilience(SweeperTestBase):
    def test_corrupt_state_file_does_not_abort_sweep(self):
        """Wrong-shape (but valid) JSON in one workflow's sidecar must not
        crash the sweep or starve the workflows sorted after it."""
        self.register(workflow_id="a-workflow")
        self.register(workflow_id="b-workflow")
        with open(workflow_spec_sweeper._sweeper_state_path("a-workflow"), "w") as f:
            f.write('[1, 2, 3]')
        reports = workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(len(reports), 2)
        # Both emitted: corrupt state discards to a fresh episode for a-workflow
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift", "WorkflowSpecDrift"])
        self.assertEqual(self.read_state("a-workflow")["consecutive_misses"], 1)
        self.assertEqual(self.read_state("b-workflow")["consecutive_misses"], 1)

    def test_non_numeric_miss_count_resets_episode(self):
        self.register()
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        state = self.read_state()
        state["consecutive_misses"] = "two"
        workflow_spec_sweeper._save_sweeper_state("test-workflow", state)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.read_state()["consecutive_misses"], 1)
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])

    def test_state_write_failure_degrades_to_silence(self):
        """If the sidecar can't be persisted, the sweeper stays silent (no
        per-sweep flood, no deregistration) until persistence recovers."""
        self.register()
        workflow_dir = os.path.dirname(
            corpus_watcher.workflow_pointer_path("test-workflow"))
        os.chmod(workflow_dir, 0o555)
        self.addCleanup(os.chmod, workflow_dir, 0o755)
        for _ in range(3):
            workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.events, [])
        self.assertEqual(corpus_watcher.list_known_workflows(), ["test-workflow"])
        # Persistence recovers → normal first-detection emission
        os.chmod(workflow_dir, 0o755)
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertEqual(self.event_types(), ["WorkflowSpecDrift"])

    def test_transient_emit_failure_retries_first_detection(self):
        """A missing-spec first-detection event whose emit fails is retried
        next sweep (drift_emitted is only set on a successful emit), not
        marked done and lost — while the miss counter still advances."""
        self.register()
        boom = [True]

        def flaky_emit(event):
            self.events.append(event)
            if boom[0]:
                boom[0] = False
                raise OSError("events.jsonl append failed")

        workflow_spec_sweeper.sweep(emit_event=flaky_emit)
        # The first emit attempt raised → drift_emitted stayed False, retryable
        self.assertFalse(self.read_state()["drift_emitted"])
        self.assertEqual(self.read_state()["consecutive_misses"], 1)
        # Next sweep re-attempts and succeeds
        workflow_spec_sweeper.sweep(emit_event=flaky_emit)
        self.assertTrue(self.read_state()["drift_emitted"])
        self.assertEqual(self.read_state()["consecutive_misses"], 2)

    def test_malformed_tombstone_does_not_abort_sweep(self):
        """An unreadable/wrong-shape tombstone must not abort tombstone recheck
        or the sweep for healthy workflows sorted after it."""
        # A tombstone dir with invalid UTF-8 bytes, sorted before the healthy wf
        bad_dir = os.path.join(self.data_dir, "aaa-bad")
        os.makedirs(bad_dir)
        with open(os.path.join(bad_dir, "workflow-pointer.json.deregistered"), "wb") as f:
            f.write(b"\xff\xfe{not json")
        self.register(workflow_id="zzz-healthy")
        reports = workflow_spec_sweeper.sweep(emit_event=self.emit)
        ids = [r.workflow_id for r in reports]
        self.assertIn("zzz-healthy", ids)

    def test_pointer_with_invalid_utf8_does_not_abort_sweep(self):
        """A pointer file the loader can't decode must not starve later
        workflows: the pointer read is inside the per-workflow guard."""
        bad_dir = os.path.join(self.data_dir, "aaa-badptr")
        os.makedirs(bad_dir)
        with open(os.path.join(bad_dir, "workflow-pointer.json"), "wb") as f:
            f.write(b"\xff\xfe\x00garbage")
        self.register(workflow_id="zzz-healthy")
        reports = workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertIn("zzz-healthy", [r.workflow_id for r in reports])

    def test_legacy_sidecar_is_cleaned_up(self):
        """An orphaned pre-rename missing-spec-state.json is removed once the
        sweeper next persists state for that workflow."""
        self.register()
        legacy = os.path.join(
            os.path.dirname(corpus_watcher.workflow_pointer_path("test-workflow")),
            "missing-spec-state.json")
        with open(legacy, "w") as f:
            f.write('{"consecutive_misses": 99}')
        workflow_spec_sweeper.sweep(emit_event=self.emit)
        self.assertFalse(os.path.isfile(legacy))


if __name__ == "__main__":
    unittest.main()
