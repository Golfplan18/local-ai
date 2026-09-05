"""Focused behavior tests for the renderer-neutral Overview source adapter."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
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
            mock.patch.object(
                widgets.operation_matrix, "list_active_project_meta", project_reader,
            ),
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
                "nexus": "zeta", "name": "Zeta", "is_default": False,
                "status": "active", "priority": 0,
                "last_accessed_at": "2026-08-31T09:00:00+00:00",
            },
            {
                "nexus": "alpha", "name": "Alpha", "is_default": False,
                "status": "active", "priority": None,
                "last_accessed_at": "2026-08-30T09:00:00+00:00",
            },
        ]

        def active_projects(*, skipped_authority):
            skipped_authority.append("broken.json")
            return projects

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
            project_side_effect=active_projects, paused=paused, operating=operating,
            trigger_records=trigger_records,
        )
        self.assertEqual(
            [source["source_id"] for source in sources], list(widgets.SOURCE_ORDER)
        )
        by_id = self._by_id(sources)
        self.assertEqual(
            [item["item_id"] for item in by_id["project-priority"]["items"]],
            ["project:zeta", "project:alpha"],
        )
        self.assertTrue(all(
            item["state"] == "active"
            for item in by_id["project-priority"]["items"]
        ))
        self.assertEqual(by_id["project-priority"]["state"], "partial")
        self.assertEqual(
            by_id["project-priority"]["error"]["code"],
            "project_records_skipped",
        )
        self.assertEqual(
            [item["item_id"] for item in by_id["oversight"]["items"]],
            ["paused:pause-1", "operating:run-1"],
        )
        self.assertEqual(
            by_id["oversight"]["items"][0]["scope"], {"project_nexus": "zeta"}
        )
        trigger = by_id["triggers"]["items"][0]
        self.assertEqual(trigger["scope"], {"project_nexus": "zeta"})
        self.assertEqual(trigger["actions"], [
            "open_scheduled", "run", "pause", "retire",
        ])
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
        calls["project"].assert_called_once()
        self.assertEqual(
            calls["project"].call_args.kwargs["skipped_authority"],
            ["broken.json"],
        )

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
        self.assertEqual(trigger["actions"], [
            "open_scheduled", "inspect", "review", "run", "retire",
        ])
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


class DailyNoteOpenRouteTests(unittest.TestCase):
    endpoint = "/api/overview/daily-note/open"
    day = "2026-08-31"
    identity = f"daily-note:{day}"

    def setUp(self):
        import orchestrator.overview_widgets as overview_module
        import server.app as server_app

        self.overview = overview_module
        self.server = server_app
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.daily_root = Path(self.tmp.name) / "Daily Notes # 100% ? ü"
        self.daily_root.mkdir()
        self.client = server_app.app.test_client()

        day_patch = mock.patch.object(
            overview_module, "completed_daily_note_day", return_value=self.day,
        )
        root_patch = mock.patch.object(
            overview_module.daily_note, "daily_dir", return_value=str(self.daily_root),
        )
        day_patch.start()
        root_patch.start()
        self.addCleanup(day_patch.stop)
        self.addCleanup(root_patch.stop)

    @staticmethod
    def _completed(returncode):
        return SimpleNamespace(returncode=returncode, stdout="", stderr="")

    def _note(self):
        note = self.daily_root / f"{self.day}.md"
        note.write_bytes(b"private synthetic note bytes\n# kept exactly\n")
        return note

    def _launch_context(self, *, result=None, side_effect=None, platform="darwin"):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(self.server.sys, "platform", platform))
        runner = stack.enter_context(mock.patch.object(
            self.server.subprocess,
            "run",
            return_value=result,
            side_effect=side_effect,
        ))
        generator = stack.enter_context(mock.patch.object(
            self.overview.daily_note,
            "generate",
            side_effect=AssertionError("external open must not generate a note"),
        ))
        return stack, runner, generator

    def test_sends_exact_fully_encoded_obsidian_request_without_changing_note(self):
        note = self._note()
        original = note.read_bytes()
        stack, runner, generator = self._launch_context(result=self._completed(0))
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "ok": True,
            "identity": self.identity,
            "application": "obsidian",
            "outcome": "sent",
            "message": "Open request sent to Obsidian.",
        })
        expected_uri = "obsidian://open?path=" + quote(str(note), safe="")
        runner.assert_called_once_with(
            ["/usr/bin/open", "-a", "Obsidian", expected_uri],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertIn("%2F", expected_uri)
        self.assertIn("%20", expected_uri)
        self.assertIn("%23", expected_uri)
        self.assertIn("%25", expected_uri)
        self.assertIn("%3F", expected_uri)
        self.assertIn("%C3%BC", expected_uri)
        self.assertEqual(note.read_bytes(), original)
        generator.assert_not_called()

    def test_rejects_non_exact_json_and_hostile_origin_before_launch(self):
        self._note()
        stack, runner, generator = self._launch_context(result=self._completed(0))
        with stack:
            invalid_requests = [
                self.client.post(self.endpoint, json={}),
                self.client.post(
                    self.endpoint,
                    json={"id": self.identity, "path": "/tmp/not-authority.md"},
                ),
                self.client.post(self.endpoint, json={"id": "daily-note:2026-02-30"}),
                self.client.post(self.endpoint, json={"id": "daily-note:/tmp/note.md"}),
                self.client.post(self.endpoint, json={"id": f" {self.identity}"}),
                self.client.post(
                    self.endpoint + "?path=/tmp/not-authority.md",
                    json={"id": self.identity},
                ),
                self.client.post(
                    self.endpoint, data="{", content_type="application/json",
                ),
            ]
            hostile = self.client.post(
                self.endpoint,
                json={"id": self.identity},
                headers={"Origin": "https://attacker.example"},
            )

        for response in invalid_requests:
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["outcome"], "input_error")
        self.assertEqual(hostile.status_code, 403)
        self.assertIn("cross-origin", hostile.get_data(as_text=True))
        runner.assert_not_called()
        generator.assert_not_called()

    def test_refuses_stale_identity_after_completed_day_changes(self):
        self._note()
        stack, runner, generator = self._launch_context(result=self._completed(0))
        with (
            stack,
            mock.patch.object(
                self.overview, "completed_daily_note_day", return_value="2026-09-01",
            ),
        ):
            response = self.client.post(self.endpoint, json={"id": self.identity})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["outcome"], "stale")
        self.assertIn(self.day, payload["message"])
        self.assertIn("2026-09-01", payload["message"])
        self.assertIn("Reopen Overview", payload["message"])
        runner.assert_not_called()
        generator.assert_not_called()

    def test_refuses_missing_nonregular_and_symlink_paths_before_launch(self):
        cases = ("missing", "nonregular_target", "symlink_target",
                 "non_directory_root", "symlink_root")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                container = Path(tmp)
                root = container / "Daily Notes"
                if case == "non_directory_root":
                    root.write_text("not a directory", encoding="utf-8")
                elif case == "symlink_root":
                    actual_root = container / "actual-notes"
                    actual_root.mkdir()
                    (actual_root / f"{self.day}.md").write_text(
                        "synthetic", encoding="utf-8",
                    )
                    root.symlink_to(actual_root, target_is_directory=True)
                else:
                    root.mkdir()
                    target = root / f"{self.day}.md"
                    if case == "nonregular_target":
                        target.mkdir()
                    elif case == "symlink_target":
                        actual = container / "actual.md"
                        actual.write_text("synthetic", encoding="utf-8")
                        target.symlink_to(actual)

                stack, runner, generator = self._launch_context(
                    result=self._completed(0),
                )
                with (
                    stack,
                    mock.patch.object(
                        self.overview.daily_note, "daily_dir", return_value=str(root),
                    ),
                ):
                    response = self.client.post(
                        self.endpoint, json={"id": self.identity},
                    )

                self.assertEqual(response.status_code, 404 if case == "missing" else 409)
                self.assertEqual(
                    response.get_json()["outcome"],
                    "missing" if case == "missing" else "failed",
                )
                runner.assert_not_called()
                generator.assert_not_called()

    def test_revalidates_after_obsidian_refusal_and_will_not_fallback_to_deleted_note(self):
        note = self._note()

        def refuse_then_delete(*_args, **_kwargs):
            note.unlink()
            return self._completed(1)

        stack, runner, generator = self._launch_context(side_effect=refuse_then_delete)
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["outcome"], "missing")
        runner.assert_called_once()
        generator.assert_not_called()

    def test_definite_obsidian_refusal_uses_default_markdown_application(self):
        note = self._note()
        original = note.read_bytes()
        stack, runner, generator = self._launch_context(
            side_effect=[self._completed(1), self._completed(0)],
        )
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["identity"], self.identity)
        self.assertEqual(payload["application"], "default_markdown")
        self.assertEqual(payload["outcome"], "fallback_sent")
        self.assertIn("Obsidian could not accept", payload["message"])
        self.assertIn("Open request sent", payload["message"])
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[1].args[0], ["/usr/bin/open", str(note)])
        self.assertEqual(runner.call_args_list[1].kwargs, {
            "capture_output": True,
            "text": True,
            "timeout": 5,
            "check": False,
        })
        self.assertEqual(note.read_bytes(), original)
        generator.assert_not_called()

    def test_launch_failures_are_bounded_and_visible(self):
        note = self._note()
        original = note.read_bytes()
        scenarios = (
            (OSError("open unavailable"), 1, "obsidian"),
            ([self._completed(1), self._completed(2)], 2, "default_markdown"),
        )
        for side_effect, call_count, application in scenarios:
            with self.subTest(application=application):
                stack, runner, generator = self._launch_context(side_effect=side_effect)
                with stack:
                    response = self.client.post(
                        self.endpoint, json={"id": self.identity},
                    )
                self.assertEqual(response.status_code, 502)
                payload = response.get_json()
                self.assertEqual(payload["outcome"], "failed")
                self.assertEqual(payload["application"], application)
                self.assertNotIn("open unavailable", payload["message"])
                self.assertEqual(runner.call_count, call_count)
                generator.assert_not_called()
        self.assertEqual(note.read_bytes(), original)

    def test_timeouts_report_uncertainty_without_unapproved_duplicate_dispatch(self):
        note = self._note()
        original = note.read_bytes()
        timeout = self.server.subprocess.TimeoutExpired(
            ["/usr/bin/open", "-a", "Obsidian"], 5,
        )
        stack, runner, generator = self._launch_context(side_effect=timeout)
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})

        self.assertEqual(response.status_code, 504)
        payload = response.get_json()
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertEqual(payload["application"], "obsidian")
        self.assertIn("No other application was tried", payload["message"])
        runner.assert_called_once()
        generator.assert_not_called()
        self.assertEqual(note.read_bytes(), original)

    def test_fallback_timeout_is_uncertain_and_unsupported_hosts_do_not_launch(self):
        note = self._note()
        original = note.read_bytes()
        timeout = self.server.subprocess.TimeoutExpired(
            ["/usr/bin/open", str(note)], 5,
        )
        stack, runner, generator = self._launch_context(
            side_effect=[self._completed(1), timeout],
        )
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.get_json()["outcome"], "uncertain")
        self.assertEqual(response.get_json()["application"], "default_markdown")
        self.assertEqual(runner.call_count, 2)
        generator.assert_not_called()

        stack, runner, generator = self._launch_context(
            result=self._completed(0), platform="linux",
        )
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.get_json()["outcome"], "unsupported")
        runner.assert_not_called()
        generator.assert_not_called()
        self.assertEqual(note.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
