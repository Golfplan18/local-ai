"""Tests for oversight_queue.py — managed Paused queue + Operating aggregator.

Covers:
  - list_paused with empty file, with legacy entries (no id/name), with
    new-shape entries
  - Stable id synthesis from queued_at + event_type + project_nexus
  - add_entry: writes record, applies AI naming (mocked), template fallback
  - rename, mark_engagement, link_discussion, remove_by_id, find_raw_index_by_id
  - list_operating: re-eval queue + active elicitations
"""
from __future__ import annotations

import json
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


def _patch_paths(test_case: unittest.TestCase, tmpdir: str) -> dict:
    paths = {
        "data_dir": os.path.join(tmpdir, "oversight"),
        "queue": os.path.join(tmpdir, "oversight/human-queue.jsonl"),
        "reeval": os.path.join(tmpdir, "oversight/reeval-queue.jsonl"),
        "sessions": os.path.join(tmpdir, "sessions"),
    }
    os.makedirs(paths["data_dir"], exist_ok=True)
    os.makedirs(paths["sessions"], exist_ok=True)
    import oversight_queue
    import oversight_actions
    test_case._patches = [
        mock.patch.object(oversight_queue, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
        mock.patch.object(oversight_queue, "REEVAL_QUEUE_PATH", paths["reeval"]),
        mock.patch.object(oversight_queue, "SESSIONS_ROOT", paths["sessions"]),
        mock.patch.object(oversight_queue, "HUMAN_QUEUE_PATH", paths["queue"]),
        mock.patch.object(oversight_actions, "HUMAN_QUEUE_PATH", paths["queue"]),
        mock.patch.object(oversight_actions, "OVERSIGHT_DATA_DIR", paths["data_dir"]),
    ]
    for p in test_case._patches:
        p.start()
    return paths


# ---------- list_paused ----------

class TestListPaused(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-oq-")
        self.paths = _patch_paths(self, self.tmp)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_file(self):
        from oversight_queue import list_paused
        self.assertEqual(list_paused(), [])

    def test_legacy_entries_get_synthesized_id_and_template_name(self):
        from oversight_queue import list_paused
        with open(self.paths["queue"], "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"event_type": "MilestoneClaimed", "project_nexus": "p1"},
                "verdict": {"verdict": "ESCALATE", "reasoning": "test reasoning"},
                "redefinition": True,
            }) + "\n")
        entries = list_paused()
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertTrue(e.id)  # synthesized
        self.assertEqual(len(e.id), 16)
        self.assertIn("Redefinition", e.name)
        self.assertIn("p1", e.name)
        self.assertEqual(e.engagement, "unseen")

    def test_synthesized_id_is_stable(self):
        # Same record should yield same id on repeated reads
        from oversight_queue import list_paused
        with open(self.paths["queue"], "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"event_type": "MilestoneBlocked", "project_nexus": "p2"},
                "verdict": {},
                "redefinition": False,
            }) + "\n")
        ids_1 = [e.id for e in list_paused()]
        ids_2 = [e.id for e in list_paused()]
        self.assertEqual(ids_1, ids_2)

    def test_sorted_oldest_first(self):
        from oversight_queue import list_paused
        with open(self.paths["queue"], "w") as f:
            f.write(json.dumps({
                "queued_at": "2026-05-04T15:00:00+00:00",
                "event": {"event_type": "MilestoneClaimed", "project_nexus": "p3"},
                "verdict": {},
            }) + "\n")
            f.write(json.dumps({
                "queued_at": "2026-05-04T09:00:00+00:00",
                "event": {"event_type": "MilestoneClaimed", "project_nexus": "p1"},
                "verdict": {},
            }) + "\n")
            f.write(json.dumps({
                "queued_at": "2026-05-04T12:00:00+00:00",
                "event": {"event_type": "MilestoneClaimed", "project_nexus": "p2"},
                "verdict": {},
            }) + "\n")
        entries = list_paused()
        self.assertEqual([e.queued_at for e in entries], [
            "2026-05-04T09:00:00+00:00",
            "2026-05-04T12:00:00+00:00",
            "2026-05-04T15:00:00+00:00",
        ])


# ---------- add_entry ----------

class TestAddEntry(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-add-")
        self.paths = _patch_paths(self, self.tmp)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_entry_falls_back_to_template_when_naming_returns_empty(self):
        # Force _generate_name to return the template (simulates no-endpoint
        # path or model-failure path).
        import oversight_queue
        from oversight_queue import add_entry, list_paused
        with mock.patch.object(
            oversight_queue, "_generate_name",
            return_value="Redefinition: alpha",
        ):
            record = {
                "event": {"event_type": "MilestoneClaimed", "project_nexus": "alpha"},
                "verdict": {"reasoning": "milestone reveals problem"},
                "redefinition": True,
            }
            entry = add_entry(record, config={})
        self.assertTrue(entry.id)
        self.assertEqual(entry.name, "Redefinition: alpha")
        all_entries = list_paused()
        self.assertEqual(len(all_entries), 1)
        self.assertEqual(all_entries[0].id, entry.id)

    def test_add_entry_uses_ai_name_when_summarizer_returns(self):
        # Force _generate_name to return a substantive AI-generated name.
        import oversight_queue
        from oversight_queue import add_entry
        with mock.patch.object(
            oversight_queue, "_generate_name",
            return_value="Customer adoption metrics aren't predictive",
        ):
            record = {
                "event": {"event_type": "MilestoneClaimed", "project_nexus": "alpha"},
                "verdict": {"reasoning": "..."},
                "redefinition": True,
            }
            entry = add_entry(record, config={"endpoints": [{"name": "fake"}]})
        self.assertIn("adoption", entry.name)


# ---------- rename / engagement / link_discussion / remove ----------

class TestQueueMutations(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-mut-")
        self.paths = _patch_paths(self, self.tmp)
        import oversight_queue
        from oversight_queue import add_entry
        self._naming_patch = mock.patch.object(
            oversight_queue, "_generate_name", return_value="Redefinition: alpha",
        )
        self._naming_patch.start()
        self.entry = add_entry({
            "event": {"event_type": "MilestoneClaimed", "project_nexus": "alpha"},
            "verdict": {},
            "redefinition": True,
        }, config={})

    def tearDown(self):
        self._naming_patch.stop()
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rename(self):
        from oversight_queue import rename, list_paused
        self.assertTrue(rename(self.entry.id, "My better name"))
        entries = list_paused()
        self.assertEqual(entries[0].name, "My better name")

    def test_rename_blank_rejected(self):
        from oversight_queue import rename
        self.assertFalse(rename(self.entry.id, "   "))

    def test_rename_unknown_id(self):
        from oversight_queue import rename
        self.assertFalse(rename("nonexistent", "Whatever"))

    def test_mark_engagement(self):
        from oversight_queue import mark_engagement, list_paused
        self.assertTrue(mark_engagement(self.entry.id, "seen"))
        self.assertEqual(list_paused()[0].engagement, "seen")
        self.assertFalse(mark_engagement(self.entry.id, "bogus"))

    def test_link_discussion(self):
        from oversight_queue import link_discussion, list_paused
        self.assertTrue(link_discussion(self.entry.id, "resolve-abc123"))
        e = list_paused()[0]
        self.assertEqual(e.discussion_conversation_id, "resolve-abc123")
        self.assertEqual(e.engagement, "discussing")

    def test_remove_by_id(self):
        from oversight_queue import remove_by_id, list_paused
        self.assertTrue(remove_by_id(self.entry.id))
        self.assertEqual(list_paused(), [])

    def test_find_raw_index_by_id_returns_position(self):
        from oversight_queue import find_raw_index_by_id, add_entry
        # Add second entry — naming is already mocked via setUp's patch
        e2 = add_entry({
            "event": {"event_type": "MilestoneClaimed", "project_nexus": "beta"},
            "verdict": {},
        }, config={})
        idx1 = find_raw_index_by_id(self.entry.id)
        idx2 = find_raw_index_by_id(e2.id)
        self.assertEqual(idx1, 0)
        self.assertEqual(idx2, 1)


# ---------- list_operating ----------

class TestListOperating(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ora-op-")
        self.paths = _patch_paths(self, self.tmp)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_operating_includes_reeval_entries(self):
        # Seed a re-eval queue
        with open(self.paths["reeval"], "w") as f:
            f.write(json.dumps({
                "task_id": "reeval-alpha-abc",
                "task_type": "redefinition_reevaluation",
                "project_nexus": "alpha",
                "queued_at": "2026-05-04T12:00:00+00:00",
            }) + "\n")
        from oversight_queue import list_operating
        items = list_operating()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "reeval")
        self.assertIn("alpha", items[0].name)

    def test_operating_includes_active_elicitations(self):
        # Seed a fake conversation with an elicitation marker on the last
        # assistant turn
        conv_dir = os.path.join(self.paths["sessions"], "conv-elicit-1")
        os.makedirs(conv_dir, exist_ok=True)
        env = {
            "conversation_id": "conv-elicit-1",
            "display_name": "C-Design session",
            "tag": "",
            "created": "2026-05-04T11:00:00+00:00",
            "messages": [
                {"role": "user", "content": "/framework cff", "timestamp": "..."},
                {
                    "role": "assistant",
                    "content": (
                        "What workflow is this for?\n\n"
                        "<!-- ora-framework: cff/C-Design/eliciting -->"
                    ),
                    "timestamp": "2026-05-04T11:01:00+00:00",
                },
            ],
        }
        with open(os.path.join(conv_dir, "conversation.json"), "w") as f:
            json.dump(env, f)
        from oversight_queue import list_operating
        items = list_operating()
        kinds = [i.kind for i in items]
        self.assertIn("elicitation", kinds)
        elicit = next(i for i in items if i.kind == "elicitation")
        self.assertEqual(elicit.framework_id, "cff")
        self.assertEqual(elicit.mode, "C-Design")
        self.assertEqual(elicit.conversation_id, "conv-elicit-1")

    def test_operating_is_empty_when_no_sources(self):
        from oversight_queue import list_operating
        self.assertEqual(list_operating(), [])


if __name__ == "__main__":
    unittest.main()
