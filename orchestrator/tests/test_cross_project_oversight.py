"""Tests for cross-project oversight (orchestrator/oversight_relationships.py).

Covers:
  - Parent lookup from child PED frontmatter (positive, negative, missing)
  - should_fan_out filter (event types, drift filter, recursion guard)
  - notify_parent: appends Decision Log entry to parent PED + emits audit
    record + does not crash when parent PED missing
  - Router fan-out: events with parent surface on parent's PED; events
    without parent are silent; fan-out audit records are skipped on re-entry
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from textwrap import dedent
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = os.path.dirname(HERE)
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)


# Sample PEDs — both parent and child
PARENT_PED = dedent("""\
    ---
    nexus:
      - parent_proj
    type: PED
    iteration: 1
    ---

    # Problem Evolution Document — parent_proj

    ## Mission

    - **Resolution Statement:** Parent goal achieved.

    ## Excluded Outcomes

    *(none)*

    ## Constraints

    *(none)*

    ## Active Milestones

    - [ ] Sub-project X delivers its initial draft

    ## Decision Log

    """)


CHILD_PED = dedent("""\
    ---
    nexus:
      - child_proj
    type: PED
    iteration: 1
    parent_nexus: parent_proj
    spawned_from_milestone: Sub-project X delivers its initial draft
    ---

    # Problem Evolution Document — child_proj

    ## Mission

    - **Resolution Statement:** Child sub-goal complete.

    ## Active Milestones

    - [ ] Initial draft is complete

    ## Decision Log

    """)


CHILD_PED_NO_PARENT = dedent("""\
    ---
    nexus:
      - orphan_proj
    type: PED
    iteration: 1
    ---

    # Problem Evolution Document — orphan_proj

    ## Mission

    - **Resolution Statement:** Standalone goal.

    ## Active Milestones

    - [ ] Something is done

    ## Decision Log

    """)


def _patch_oversight_paths(test_case: unittest.TestCase, tmpdir: str):
    """Redirect all oversight paths to a tempdir for test isolation.

    Patches PED registry path (used by ped_watcher.load_ped_path), events log,
    actions log, and human queue. Returns a dict of paths.
    """
    paths = {
        "data_dir": os.path.join(tmpdir, "oversight"),
        "events_log": os.path.join(tmpdir, "oversight/events.jsonl"),
        "actions_log": os.path.join(tmpdir, "oversight/actions.jsonl"),
    }
    os.makedirs(paths["data_dir"], exist_ok=True)

    import oversight_relationships
    import oversight_actions
    import ped_watcher

    test_case._patches = [
        mock.patch.object(oversight_relationships, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
        mock.patch.object(oversight_relationships, "EVENTS_LOG_PATH", paths["events_log"]),
        mock.patch.object(oversight_relationships, "ACTIONS_LOG_PATH", paths["actions_log"]),
        mock.patch.object(oversight_actions, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
        mock.patch.object(ped_watcher, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
    ]
    for p in test_case._patches:
        p.start()
    return paths


# ---------- Parent lookup ----------

class TestGetParentNexus(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-xproj-test-")
        _patch_oversight_paths(self, self.tmp)

        # Write the child PED and register it
        self.child_ped_path = os.path.join(self.tmp, "child-ped.md")
        with open(self.child_ped_path, "w") as f:
            f.write(CHILD_PED)
        from ped_watcher import write_ped_pointer
        write_ped_pointer("child_proj", self.child_ped_path)

        # Write an orphan PED and register it
        self.orphan_ped_path = os.path.join(self.tmp, "orphan-ped.md")
        with open(self.orphan_ped_path, "w") as f:
            f.write(CHILD_PED_NO_PARENT)
        write_ped_pointer("orphan_proj", self.orphan_ped_path)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolves_parent_from_child_frontmatter(self):
        from oversight_relationships import get_parent_nexus
        self.assertEqual(get_parent_nexus("child_proj"), "parent_proj")

    def test_returns_none_for_orphan(self):
        from oversight_relationships import get_parent_nexus
        self.assertIsNone(get_parent_nexus("orphan_proj"))

    def test_returns_none_for_unregistered_project(self):
        from oversight_relationships import get_parent_nexus
        self.assertIsNone(get_parent_nexus("does_not_exist"))

    def test_returns_none_for_empty_input(self):
        from oversight_relationships import get_parent_nexus
        self.assertIsNone(get_parent_nexus(""))
        self.assertIsNone(get_parent_nexus(None))  # type: ignore

    def test_resolves_spawned_from_milestone(self):
        from oversight_relationships import get_spawned_from_milestone
        self.assertIn("initial draft", get_spawned_from_milestone("child_proj") or "")


# ---------- should_fan_out ----------

class TestShouldFanOut(unittest.TestCase):

    def test_fan_out_event_types(self):
        from oversight_relationships import should_fan_out
        for et in ["MilestoneClaimed", "MilestoneBlocked", "FrameworkComplete",
                   "RedefinitionEvidence"]:
            self.assertTrue(should_fan_out({"event_type": et, "project_nexus": "x"}))

    def test_milestone_complete_only_when_drift_detected(self):
        from oversight_relationships import should_fan_out
        self.assertFalse(should_fan_out({
            "event_type": "MilestoneComplete",
            "drift_status": "IN_SCOPE",
            "project_nexus": "x",
        }))
        self.assertTrue(should_fan_out({
            "event_type": "MilestoneComplete",
            "drift_status": "DRIFT_DETECTED",
            "project_nexus": "x",
        }))

    def test_workflow_level_events_skip_fan_out(self):
        from oversight_relationships import should_fan_out
        for et in ["CorpusSectionPopulated", "OFFRendered", "CorpusValidated"]:
            self.assertFalse(should_fan_out({"event_type": et, "workflow_id": "w"}))

    def test_synthesized_fan_out_records_skip_recursion(self):
        from oversight_relationships import (
            should_fan_out, FAN_OUT_META_KEY, FAN_OUT_META_VALUE,
        )
        synthesized = {
            "event_type": "ChildMilestoneClaimed",
            "project_nexus": "parent",
            FAN_OUT_META_KEY: FAN_OUT_META_VALUE,
        }
        self.assertFalse(should_fan_out(synthesized))


# ---------- notify_parent ----------

class TestNotifyParent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-xproj-notify-")
        _patch_oversight_paths(self, self.tmp)

        self.parent_ped_path = os.path.join(self.tmp, "parent-ped.md")
        with open(self.parent_ped_path, "w") as f:
            f.write(PARENT_PED)
        self.child_ped_path = os.path.join(self.tmp, "child-ped.md")
        with open(self.child_ped_path, "w") as f:
            f.write(CHILD_PED)

        from ped_watcher import write_ped_pointer
        write_ped_pointer("parent_proj", self.parent_ped_path)
        write_ped_pointer("child_proj", self.child_ped_path)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_appends_decision_log_entry_to_parent(self):
        from oversight_relationships import notify_parent
        child_event = {
            "event_type": "MilestoneClaimed",
            "project_nexus": "child_proj",
            "milestone_text": "Initial draft is complete",
            "claimer": "user",
        }
        synthesized = notify_parent(child_event, "parent_proj")
        self.assertIsNotNone(synthesized)
        self.assertEqual(synthesized["event_type"], "ChildMilestoneClaimed")
        self.assertEqual(synthesized["child_nexus"], "child_proj")

        with open(self.parent_ped_path) as f:
            content = f.read()
        self.assertIn("Child Project Update: child_proj", content)
        self.assertIn("MilestoneClaimed", content)
        self.assertIn("Initial draft is complete", content)
        self.assertIn("Spawned from parent milestone", content)

    def test_synthesized_event_carries_fan_out_meta(self):
        from oversight_relationships import (
            notify_parent, FAN_OUT_META_KEY, FAN_OUT_META_VALUE,
        )
        child_event = {
            "event_type": "MilestoneClaimed",
            "project_nexus": "child_proj",
        }
        synthesized = notify_parent(child_event, "parent_proj")
        self.assertEqual(synthesized[FAN_OUT_META_KEY], FAN_OUT_META_VALUE)

    def test_returns_none_for_non_fan_out_event(self):
        from oversight_relationships import notify_parent
        non_fan_event = {
            "event_type": "FrameworkStarted",  # not in fan-out set
            "project_nexus": "child_proj",
        }
        self.assertIsNone(notify_parent(non_fan_event, "parent_proj"))

    def test_returns_none_when_parent_ped_missing(self):
        from oversight_relationships import notify_parent
        # Parent registered to a non-existent path
        from ped_watcher import write_ped_pointer
        bogus_path = os.path.join(self.tmp, "does-not-exist.md")
        write_ped_pointer("ghost_parent", bogus_path)
        result = notify_parent(
            {"event_type": "MilestoneClaimed", "project_nexus": "child_proj"},
            "ghost_parent",
        )
        self.assertIsNone(result)

    def test_emits_audit_records_to_events_and_actions_logs(self):
        from oversight_relationships import (
            notify_parent, EVENTS_LOG_PATH, ACTIONS_LOG_PATH,
        )
        child_event = {
            "event_type": "MilestoneBlocked",
            "project_nexus": "child_proj",
            "block_reason": "missing input",
        }
        notify_parent(child_event, "parent_proj")

        with open(EVENTS_LOG_PATH) as f:
            events = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "ChildMilestoneBlocked")
        self.assertEqual(events[0]["child_block_reason"], "missing input")

        with open(ACTIONS_LOG_PATH) as f:
            actions = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "fan_out_to_parent")


# ---------- Router fan-out integration ----------

class TestRouterFanOut(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-xproj-router-")
        _patch_oversight_paths(self, self.tmp)

        # Also patch the router log path so it lands in tmp
        self.router_log = os.path.join(self.tmp, "oversight/router.jsonl")
        import oversight_router
        self._patches.append(
            mock.patch.object(oversight_router, "ROUTER_LOG_PATH", self.router_log)
        )
        self._patches[-1].start()

        # Set up parent + child PEDs
        self.parent_ped_path = os.path.join(self.tmp, "parent-ped.md")
        with open(self.parent_ped_path, "w") as f:
            f.write(PARENT_PED)
        self.child_ped_path = os.path.join(self.tmp, "child-ped.md")
        with open(self.child_ped_path, "w") as f:
            f.write(CHILD_PED)
        self.orphan_ped_path = os.path.join(self.tmp, "orphan-ped.md")
        with open(self.orphan_ped_path, "w") as f:
            f.write(CHILD_PED_NO_PARENT)

        from ped_watcher import write_ped_pointer
        write_ped_pointer("parent_proj", self.parent_ped_path)
        write_ped_pointer("child_proj", self.child_ped_path)
        write_ped_pointer("orphan_proj", self.orphan_ped_path)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_child_event_appears_on_parent_decision_log(self):
        from oversight_router import process_event
        process_event({
            "event_type": "MilestoneClaimed",
            "project_nexus": "child_proj",
            "milestone_text": "Initial draft is complete",
        }, live=False)
        with open(self.parent_ped_path) as f:
            content = f.read()
        self.assertIn("Child Project Update: child_proj", content)

    def test_orphan_event_does_not_appear_anywhere(self):
        from oversight_router import process_event
        process_event({
            "event_type": "MilestoneClaimed",
            "project_nexus": "orphan_proj",
            "milestone_text": "Something is done",
        }, live=False)
        # Parent PED is unchanged from the seed
        with open(self.parent_ped_path) as f:
            self.assertNotIn("Child Project Update", f.read())

    def test_fan_out_audit_records_skip_re_processing(self):
        # Fire an event for the child; the router fans out; the synthesized
        # ChildMilestoneClaimed audit record lands in events.jsonl. If a
        # consumer re-feeds it back to the router (e.g., the durable replay
        # path on restart), the router must NOT re-fan or re-invoke PC.
        from oversight_router import process_event
        from oversight_relationships import EVENTS_LOG_PATH, FAN_OUT_META_KEY, FAN_OUT_META_VALUE

        process_event({
            "event_type": "MilestoneClaimed",
            "project_nexus": "child_proj",
            "milestone_text": "Initial draft is complete",
        }, live=False)

        # Read the synthesized fan-out event from the events log
        with open(EVENTS_LOG_PATH) as f:
            events = [json.loads(line) for line in f if line.strip()]
        synthesized = next(e for e in events if e.get(FAN_OUT_META_KEY) == FAN_OUT_META_VALUE)

        # Re-feed it
        action = process_event(synthesized, live=False)
        self.assertEqual(action["action"], "fan_out_audit_only")

        # Parent PED should have exactly ONE entry (the original fan-out),
        # not two (which would happen if the synthesized event re-fanned).
        with open(self.parent_ped_path) as f:
            content = f.read()
        self.assertEqual(content.count("Child Project Update: child_proj"), 1)


if __name__ == "__main__":
    unittest.main()
