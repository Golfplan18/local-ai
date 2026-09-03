"""Focused behavior tests for the renderer-neutral Overview source adapter."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))

import overview_widgets as widgets  # noqa: E402


FIXED_NOW = datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc)


class OverviewWidgetSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.daily_root = Path(self.tmp.name) / "Daily Notes"
        self.daily_root.mkdir()
        self.queue_path = Path(self.tmp.name) / "human-queue.jsonl"
        self.reeval_path = Path(self.tmp.name) / "reeval-queue.jsonl"
        self.sessions_root = Path(self.tmp.name) / "sessions"
        self.sessions_root.mkdir()

    def _load(
        self,
        *,
        projects=None,
        paused=None,
        operating=None,
        trigger_records=None,
        project_side_effect=None,
        paused_side_effect=None,
        operating_side_effect=None,
        trigger_side_effect=None,
    ):
        project_reader = mock.Mock(
            side_effect=project_side_effect,
            return_value=[] if projects is None else projects,
        )
        paused_reader = mock.Mock(
            side_effect=paused_side_effect,
            return_value=[] if paused is None else paused,
        )
        operating_reader = mock.Mock(
            side_effect=operating_side_effect,
            return_value=[] if operating is None else operating,
        )
        trigger_reader = mock.Mock(
            side_effect=trigger_side_effect,
            return_value=[] if trigger_records is None else trigger_records,
        )
        service = SimpleNamespace(list_triggers=trigger_reader)
        with (
            mock.patch.object(widgets.project_meta, "list_project_meta", project_reader),
            mock.patch.object(widgets.oversight_queue, "list_paused", paused_reader),
            mock.patch.object(widgets.oversight_queue, "list_operating", operating_reader),
            mock.patch.object(
                widgets.oversight_queue, "_queue_path", return_value=str(self.queue_path),
            ),
            mock.patch.object(
                widgets.oversight_queue, "_reeval_path", return_value=str(self.reeval_path),
            ),
            mock.patch.object(
                widgets.oversight_queue, "SESSIONS_ROOT", str(self.sessions_root),
            ),
            mock.patch.object(widgets.triggers, "TriggerService", return_value=service),
            mock.patch.object(widgets.daily_note, "daily_dir", return_value=str(self.daily_root)),
            mock.patch.object(
                widgets.daily_note, "generate",
                side_effect=AssertionError("read adapter must not generate a note"),
            ),
        ):
            result = widgets.load_overview_widget_sources(observed_at=FIXED_NOW)
        return result, {
            "project": project_reader,
            "paused": paused_reader,
            "operating": operating_reader,
            "triggers": trigger_reader,
        }

    @staticmethod
    def _by_id(sources):
        return {source["source_id"]: source for source in sources}

    def test_normalizes_all_sources_and_preserves_project_order(self):
        projects = [
            {
                "nexus": "commons", "name": "Commons", "is_default": True,
                "status": "active", "priority": None, "last_accessed_at": None,
            },
            {
                "nexus": "zeta", "name": "Zeta", "is_default": False,
                "status": "active", "priority": 0,
                "last_accessed_at": "2026-08-31T09:00:00+00:00",
            },
            {
                "nexus": "alpha", "name": "Alpha", "is_default": False,
                "status": "inactive", "priority": 1,
                "last_accessed_at": "2026-08-30T09:00:00+00:00",
            },
        ]
        paused = [SimpleNamespace(
            id="pause-1", name="Review evidence", queued_at="2026-08-31T08:00:00+00:00",
            forced_reason="Needs a decision", event={"project_nexus": "zeta"},
            verdict={}, context_summary={}, discussion_conversation_id="discussion-1",
        )]
        operating = [SimpleNamespace(
            id="run-1", name="Elicitation: PEF", started_at="2026-08-31T10:00:00+00:00",
            project_nexus="alpha", framework_id="pef", mode="PE-Iterate",
            conversation_id="conversation-1", detail={},
        )]
        trigger_records = [{
            "spec": {
                "trigger_id": "morning-brief", "name": "Morning brief",
                "cause": "calendar",
                "action": {"kind": "project_tool", "nexus": "zeta"},
            },
            "status": "active",
            "created_at": "2026-08-01T00:00:00+00:00",
            "activated_at": "2026-08-02T00:00:00+00:00",
            "next_due_at": "2026-09-02T15:00:00+00:00",
            "firings": [{"outcome": "completed", "finished_at": "2026-09-01T15:00:00+00:00"}],
        }]
        (self.daily_root / "2026-08-31.md").write_text(
            """---
type: daily-note
date: 2026-08-31
---

# 2026-08-31 (Monday)

[[2026-08-30]] · [[2026-09-01]]

## Dialogues

- Overview planning
""",
            encoding="utf-8",
        )

        sources, calls = self._load(
            projects=projects, paused=paused, operating=operating,
            trigger_records=trigger_records,
        )
        self.assertEqual(
            [source["source_id"] for source in sources], list(widgets.SOURCE_ORDER)
        )
        by_id = self._by_id(sources)
        self.assertEqual(
            [item["item_id"] for item in by_id["project-priority"]["items"]],
            ["project:commons", "project:zeta", "project:alpha"],
        )
        self.assertEqual(by_id["project-priority"]["items"][2]["state"], "inactive")
        self.assertEqual(
            [item["item_id"] for item in by_id["oversight"]["items"]],
            ["paused:pause-1", "operating:run-1"],
        )
        self.assertEqual(
            by_id["oversight"]["items"][0]["scope"], {"project_nexus": "zeta"}
        )
        trigger = by_id["triggers"]["items"][0]
        self.assertEqual(trigger["scope"], {"project_nexus": "zeta"})
        self.assertEqual(trigger["actions"], ["run", "pause", "retire"])
        self.assertEqual(trigger["time"], "2026-09-02T15:00:00+00:00")
        note = by_id["daily-note"]["items"][0]
        self.assertEqual(note["item_id"], "daily-note:2026-08-31")
        self.assertIn("Dialogues", note["text"])
        self.assertEqual(note["actions"], ["open_note"])
        self.assertEqual(
            by_id["daily-note"]["freshness"],
            {
                "observed_at": "2026-09-01T12:30:00+00:00",
                "last_success_at": "2026-09-01T12:30:00+00:00",
            },
        )
        calls["project"].assert_called_once_with(skipped_authority=[])

        required_item_fields = {
            "source_id", "item_id", "title", "text", "state", "count",
            "time", "scope", "actions",
        }
        for source in sources:
            for item in source["items"]:
                self.assertEqual(set(item), required_item_fields)

    def test_one_failed_source_does_not_block_the_others(self):
        operating = [SimpleNamespace(
            id="run-2", name="Re-evaluation", started_at="2026-08-31T10:00:00+00:00",
            project_nexus="zeta", framework_id="", mode="",
            conversation_id="", detail={"display_name": "Project review"},
        )]
        sources, _calls = self._load(
            project_side_effect=OSError("project pointers unreadable"),
            paused_side_effect=OSError("paused queue unreadable"),
            operating=operating,
            trigger_side_effect=OSError("trigger store unreadable"),
        )
        by_id = self._by_id(sources)

        self.assertEqual(by_id["project-priority"]["state"], "unavailable")
        self.assertFalse(by_id["project-priority"]["available"])
        self.assertEqual(by_id["project-priority"]["freshness"]["last_success_at"], None)
        self.assertEqual(by_id["oversight"]["state"], "partial")
        self.assertTrue(by_id["oversight"]["available"])
        self.assertEqual(
            [item["item_id"] for item in by_id["oversight"]["items"]],
            ["operating:run-2"],
        )
        self.assertEqual(by_id["triggers"]["state"], "unavailable")
        self.assertEqual(by_id["daily-note"]["state"], "missing")
        self.assertEqual(by_id["daily-note"]["count"], 0)
        self.assertEqual(
            by_id["daily-note"]["items"][0]["state"], "missing"
        )

    def test_malformed_paused_file_reports_partial_and_keeps_operating_lane(self):
        self.queue_path.write_text("{not-json}\n", encoding="utf-8")
        operating = [SimpleNamespace(
            id="run-3", name="Project review", started_at="2026-08-31T10:00:00+00:00",
            project_nexus="zeta", framework_id="pef", mode="PE-Iterate",
            conversation_id="conversation-3", detail={}, kind="elicitation",
        )]

        sources, _calls = self._load(operating=operating)
        source = self._by_id(sources)["oversight"]

        self.assertEqual(source["state"], "partial")
        self.assertTrue(source["available"])
        self.assertEqual(
            [item["item_id"] for item in source["items"]], ["operating:run-3"],
        )
        self.assertEqual(source["error"]["code"], "oversight_source_incomplete")
        self.assertIn("Paused queue returned 0 of 1 stored records", source["error"]["message"])

    def test_unavailable_oversight_paths_are_not_reported_as_empty(self):
        self.queue_path.mkdir()
        self.reeval_path.mkdir()
        self.sessions_root.rmdir()
        self.sessions_root.write_text("not a directory", encoding="utf-8")

        sources, _calls = self._load()
        source = self._by_id(sources)["oversight"]

        self.assertEqual(source["state"], "unavailable")
        self.assertFalse(source["available"])
        self.assertEqual(source["freshness"]["last_success_at"], None)
        self.assertEqual(source["items"], [])
        self.assertIn("Paused queue is not a regular file", source["error"]["message"])
        self.assertIn("Operating sessions source is not a directory", source["error"]["message"])

    def test_oversight_stat_access_failures_are_unavailable(self):
        original_stat = Path.stat
        blocked = {self.queue_path, self.reeval_path, self.sessions_root}

        def deny_source_stat(path, *args, **kwargs):
            if path in blocked:
                raise PermissionError(f"access denied: {path}")
            return original_stat(path, *args, **kwargs)

        with mock.patch.object(Path, "stat", autospec=True, side_effect=deny_source_stat):
            sources, _calls = self._load()
        source = self._by_id(sources)["oversight"]

        self.assertEqual(source["state"], "unavailable")
        self.assertFalse(source["available"])
        self.assertEqual(source["freshness"]["last_success_at"], None)
        self.assertEqual(source["items"], [])
        self.assertIn("Paused queue is unreadable", source["error"]["message"])
        self.assertIn(
            "Operating re-evaluation queue is unreadable",
            source["error"]["message"],
        )
        self.assertIn(
            "Operating sessions source is unreadable",
            source["error"]["message"],
        )

    def test_skipped_project_authority_is_reported_as_partial(self):
        def project_reader(*, skipped_authority):
            skipped_authority.extend(("broken.json", "unreadable.json"))
            return [{
                "nexus": "commons", "name": "Commons", "is_default": True,
                "status": "active", "priority": None,
            }]

        sources, _calls = self._load(project_side_effect=project_reader)
        source = self._by_id(sources)["project-priority"]
        self.assertEqual(source["state"], "partial")
        self.assertTrue(source["available"])
        self.assertEqual(source["count"], 1)
        self.assertEqual(source["error"]["code"], "project_records_skipped")
        self.assertIn("broken.json", source["error"]["message"])

    def test_daily_note_refuses_non_regular_target(self):
        (self.daily_root / "2026-08-31.md").mkdir()
        sources, _calls = self._load()
        source = self._by_id(sources)["daily-note"]
        self.assertEqual(source["state"], "unavailable")
        self.assertFalse(source["available"])
        self.assertEqual(source["items"], [])
        self.assertEqual(source["error"]["code"], "daily_note_source_unavailable")

    def test_daily_note_stat_access_failure_is_unavailable(self):
        target = self.daily_root / "2026-08-31.md"
        original_lstat = Path.lstat

        def deny_target_lstat(path, *args, **kwargs):
            if path == target:
                raise PermissionError(f"access denied: {path}")
            return original_lstat(path, *args, **kwargs)

        with mock.patch.object(Path, "lstat", autospec=True, side_effect=deny_target_lstat):
            sources, _calls = self._load()
        source = self._by_id(sources)["daily-note"]

        self.assertEqual(source["state"], "unavailable")
        self.assertFalse(source["available"])
        self.assertEqual(source["freshness"]["last_success_at"], None)
        self.assertEqual(source["items"], [])
        self.assertEqual(source["error"]["code"], "daily_note_source_unavailable")
        self.assertIn("access denied", source["error"]["message"])

    def test_email_trigger_advertises_only_actions_valid_for_its_state(self):
        trigger_records = [{
            "spec": {
                "trigger_id": "draft-email", "name": "Draft email",
                "cause": "manual", "action": {"kind": "email_send"},
            },
            "status": "draft", "created_at": "2026-09-01T09:00:00+00:00",
            "firings": [],
        }]
        sources, _calls = self._load(trigger_records=trigger_records)
        trigger = self._by_id(sources)["triggers"]["items"][0]
        self.assertEqual(trigger["actions"], ["inspect", "review", "run", "retire"])
        self.assertEqual(trigger["text"], "manual · email send")


class OverviewRouteTests(unittest.TestCase):
    def test_get_route_returns_adapter_sources_and_rejects_post(self):
        import orchestrator.overview_widgets as overview_module
        import server.app as server_app

        expected = [{
            "source_id": "project-priority",
            "title": "Project priority",
            "state": "empty",
            "count": 0,
            "available": True,
            "freshness": {
                "observed_at": "2026-09-01T12:30:00+00:00",
                "last_success_at": None,
            },
            "error": None,
            "items": [],
        }]
        with mock.patch.object(
            overview_module, "load_overview_widget_sources", return_value=expected,
        ) as loader:
            client = server_app.app.test_client()
            response = client.get("/api/overview")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"sources": expected})
        loader.assert_called_once_with()
        self.assertEqual(client.post("/api/overview").status_code, 405)


if __name__ == "__main__":
    unittest.main()
