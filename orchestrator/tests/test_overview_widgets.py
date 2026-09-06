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
        vault_patch = mock.patch.object(widgets.operation_matrix, "vault_root", return_value=Path(self.tmp.name))
        vault_patch.start()
        self.addCleanup(vault_patch.stop)

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
        self.assertEqual(by_id["project-priority"]["count"], 2)
        for item in by_id["project-priority"]["items"]:
            self.assertEqual(item["actions"], [
                "open_project", "open_project_files", "open_project_dialogues", "open_project_knowledge",
            ])
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
        self.assertEqual(note["actions"], ["read_note", "open_note"])
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
                if source["source_id"] == "matrix-tasks":
                    self.assertTrue(required_item_fields <= set(item))
                else:
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
        self.assertEqual(by_id["matrix-tasks"]["state"], "unavailable")
        self.assertIsNone(by_id["matrix-tasks"]["count"])
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

    def test_task_source_shares_one_project_inventory_and_matrix_pass(self):
        matrix_dir = Path(self.tmp.name) / "Matrix"
        matrix_dir.mkdir()
        for nexus, body in (("zeta", "## Tasks\n- [ ] Same\n- [x] Same ✅ 2025-01-01\n"),
                            ("alpha", "## Practices\nKeep\n")):
            (matrix_dir / f"Historical {nexus}.md").write_text(f"---\nnexus: [{nexus}]\nproject_type: [passion]\n---\n{body}")
        records = [{"nexus": "zeta", "name": "Zeta", "folder_name": "Zeta", "priority": 0, "status": "active"},
                   {"nexus": "alpha", "name": "Alpha", "folder_name": "Alpha", "priority": 1, "status": "active"},
                   {"nexus": "missing", "name": "Missing", "folder_name": "Missing", "priority": 2, "status": "active"}]
        with mock.patch.object(widgets.operation_matrix, "resolve_matrix_snapshots", wraps=widgets.operation_matrix.resolve_matrix_snapshots) as resolver:
            sources, calls = self._load(projects=records)
        calls["project"].assert_called_once()
        resolver.assert_called_once()
        by_id = self._by_id(sources)
        source = by_id["matrix-tasks"]
        self.assertEqual(list(widgets.SOURCE_ORDER), ["project-priority", "oversight", "triggers", "daily-note", "matrix-tasks"])
        self.assertEqual([row["scope"]["project_nexus"] for row in source["items"]], ["zeta", "alpha", "missing"])
        self.assertEqual([row["counts"]["total"] for row in source["items"]], [2, 0, None])
        self.assertEqual(source["count"], 2)
        self.assertEqual(source["state"], "partial")
        self.assertEqual(source["error"]["code"], "task_source_incomplete")
        self.assertIn("Known task counts", source["error"]["message"])
        self.assertEqual(source["items"][1]["state"], "empty")
        self.assertEqual(source["items"][2]["actions"], ["open_project"])

        def skipped_project(*, skipped_authority):
            skipped_authority.append("broken.json")
            return records[:2]

        sources, _ = self._load(project_side_effect=skipped_project)
        by_id = self._by_id(sources)
        source = by_id["matrix-tasks"]
        self.assertEqual([group["state"] for group in source["items"]], ["ready", "empty"])
        self.assertEqual(source["count"], 2)
        self.assertEqual(source["state"], "partial")
        self.assertEqual(source["error"], by_id["project-priority"]["error"])
        self.assertEqual(source["error"], {"code": "project_records_skipped", "message": "Unreadable project records: broken.json"})
        # A duplicate claim disables only that Matrix, not healthy project groups.
        (matrix_dir / "Duplicate.md").write_text((matrix_dir / "Historical zeta.md").read_text())
        sources, _ = self._load(projects=records)
        groups = self._by_id(sources)["matrix-tasks"]["items"]
        self.assertEqual([group["state"] for group in groups], ["unavailable", "empty", "unavailable"])
        self.assertEqual(groups[1]["counts"]["total"], 0)

    def test_task_source_known_counts_preserve_readonly_and_opaque_content(self):
        matrix_dir = Path(self.tmp.name) / "Matrix"
        matrix_dir.mkdir()
        (matrix_dir / "Odd.md").write_text("---\nnexus: [odd]\nproject_type: passion\n---\n## Tasks\n- [ ] Keep\n<!-- unknown metadata -->\n")
        sources, _ = self._load(projects=[{"nexus": "odd", "name": "Odd", "folder_name": "Odd", "status": "active"}])
        source = self._by_id(sources)["matrix-tasks"]
        group = source["items"][0]
        self.assertEqual(source["count"], 1)
        self.assertEqual(group["state"], "read-only")
        self.assertFalse(group["editable"])
        self.assertIn("<!-- unknown metadata -->", group["source_text"])


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

    def test_revalidates_completed_day_after_obsidian_refusal_before_fallback(self):
        self._note()
        stack, runner, generator = self._launch_context(result=self._completed(1))
        with (
            stack,
            mock.patch.object(
                self.overview,
                "completed_daily_note_day",
                side_effect=[self.day, "2026-09-01"],
            ),
        ):
            response = self.client.post(self.endpoint, json={"id": self.identity})

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["outcome"], "stale")
        self.assertIn(self.day, payload["message"])
        self.assertIn("2026-09-01", payload["message"])
        self.assertIn("Reopen Overview", payload["message"])
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

    def test_signal_terminated_handoffs_are_uncertain(self):
        note = self._note()
        original = note.read_bytes()

        stack, runner, generator = self._launch_context(result=self._completed(-9))
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})
        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertEqual(payload["application"], "obsidian")
        self.assertIn("No other application was tried", payload["message"])
        runner.assert_called_once()
        generator.assert_not_called()

        stack, runner, generator = self._launch_context(
            side_effect=[self._completed(1), self._completed(-9)],
        )
        with stack:
            response = self.client.post(self.endpoint, json={"id": self.identity})
        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload["outcome"], "uncertain")
        self.assertEqual(payload["application"], "default_markdown")
        self.assertIn("cannot tell whether the fallback received it", payload["message"])
        self.assertEqual(runner.call_count, 2)
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


class DailyNoteReadRouteTests(unittest.TestCase):
    endpoint = "/api/overview/daily-note/read"
    day = "2026-08-31"
    identity = f"daily-note:{day}"
    setUp = DailyNoteOpenRouteTests.setUp

    def _note(self, content=None):
        note = self.daily_root / f"{self.day}.md"
        if content is None:
            content = f"---\ntype: daily-note\ndate: {self.day}\n---\n\n# Synthetic Daily Note\n\nBody only.\n".encode()
        note.write_bytes(content)
        return note

    def _get(self, **kwargs):
        return self.client.get(self.endpoint, query_string={"id": self.identity}, **kwargs)

    def _assert_refused(self, response, status=409):
        self.assertEqual(response.status_code, status)
        self.assertEqual(set(response.get_json()), {"error"})
        self.assertNotIn(str(self.daily_root), response.get_data(as_text=True))
        self.assertNotIn("private synthetic", response.get_data(as_text=True))

    def test_reads_only_matching_frontmatter_body_without_mutation_or_launch(self):
        for newline, date_text in (("\n", self.day), ("\r\n", f'"{self.day}"')):
            with self.subTest(newline=newline):
                body = newline + "# Synthetic note" + newline + "private synthetic ü" + newline
                original = (newline.join(["---", "type: daily-note", f"date: {date_text}", "---", ""]) + body).encode()
                note = self._note(original)
                before = note.stat()
                with (
                    mock.patch.object(self.server.subprocess, "run") as launch,
                    mock.patch.object(self.overview.daily_note, "generate") as generate,
                    mock.patch.object(Path, "write_text", side_effect=AssertionError("read must not write")),
                    mock.patch.object(Path, "write_bytes", side_effect=AssertionError("read must not write")),
                    mock.patch.object(os, "replace", side_effect=AssertionError("read must not replace")),
                ):
                    response = self._get(headers={"Origin": "http://localhost"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {
                    "id": self.identity, "source": "daily-note", "text": body,
                })
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(note.read_bytes(), original)
                self.assertEqual(note.stat().st_mtime_ns, before.st_mtime_ns)
                launch.assert_not_called()
                generate.assert_not_called()

    def test_exact_identity_query_body_origin_and_method_boundary_before_file_access(self):
        with mock.patch.object(self.overview, "read_daily_note") as reader:
            for query, body in (
                ({}, None), ({"id": "daily-note:2026-02-30"}, None),
                ({"id": "daily-note:2026-8-31"}, None),
                ({"id": f" {self.identity}"}, None),
                ({"id": "daily-note:/tmp/private.md"}, None),
                ({"id": self.identity, "path": "/tmp/private.md"}, None),
                ([("id", self.identity), ("id", self.identity)], None),
                ({"id": self.identity}, b"{}"),
            ):
                with self.subTest(query=query, body=body):
                    self._assert_refused(self.client.get(self.endpoint, query_string=query, data=body), 400)
            hostile = self._get(headers={"Origin": "https://attacker.example"})
            self.assertEqual(hostile.status_code, 403)
            for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                with self.subTest(method=method):
                    self.assertEqual(self.client.open(self.endpoint, method=method).status_code, 405)
            with mock.patch.object(self.overview, "completed_daily_note_day", return_value="2026-09-01"):
                self._assert_refused(self._get())
            reader.assert_not_called()

    def test_missing_unsafe_and_unreadable_notes_never_disclose_content(self):
        self._assert_refused(self._get(), 404)
        target = self.daily_root / f"{self.day}.md"
        target.mkdir()
        self._assert_refused(self._get())
        target.rmdir()
        secret = Path(self.tmp.name) / "private.md"
        secret.write_text("private synthetic outside body", encoding="utf-8")
        target.symlink_to(secret)
        self._assert_refused(self._get())
        target.unlink()
        self._note()
        with mock.patch.object(os, "open", side_effect=PermissionError(str(secret))):
            self._assert_refused(self._get())
        actual_root = self.daily_root.with_name("actual-notes")
        self.daily_root.rename(actual_root)
        self.daily_root.symlink_to(actual_root, target_is_directory=True)
        self._assert_refused(self._get())

    def test_invalid_utf8_and_untrusted_or_mismatched_frontmatter_are_refused(self):
        contents = [
            b"\xffprivate synthetic", b"# Missing frontmatter\nprivate synthetic",
            b"---\ntype: daily-note\ndate: 2026-08-31\nprivate synthetic",
            b"---\n[broken: yaml\n---\nprivate synthetic",
            b"---\n- daily-note\n---\nprivate synthetic",
            b"---\ntype: other\ndate: 2026-08-31\n---\nprivate synthetic",
            b"---\ntype: daily-note\ndate: 2026-08-30\n---\nprivate synthetic",
            b"---\ntype: daily-note\ndate: [2026-08-31]\n---\nprivate synthetic",
            b"---\n!!python/object/apply:os.system [echo forbidden]\n---\nprivate synthetic",
        ]
        for content in contents:
            with self.subTest(content=content[:50]):
                self._note(content)
                self._assert_refused(self._get())

    def test_exact_four_mib_limit_keeps_oversize_preview_and_external_open_usable(self):
        header = f"---\ntype: daily-note\ndate: {self.day}\n---\n".encode()
        limit = self.overview.DAILY_NOTE_READ_MAX_BYTES
        note = self._note(header + b"x" * (limit - len(header)))
        accepted = self._get()
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(len(accepted.get_json()["text"].encode()), limit - len(header))
        note.write_bytes(note.read_bytes() + b"x")
        refused = self._get()
        self._assert_refused(refused)
        self.assertIn("4 MiB", refused.get_json()["error"])
        self.assertIn("Open externally", refused.get_json()["error"])
        projection = self.overview._daily_note_source("synthetic", self.day)
        self.assertEqual(projection["items"][0]["actions"], ["read_note", "open_note"])
        self.assertTrue(projection["items"][0]["text"])
        with (
            mock.patch.object(self.server.sys, "platform", "darwin"),
            mock.patch.object(self.server.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as launch,
        ):
            opened = self.client.post("/api/overview/daily-note/open", json={"id": self.identity})
        self.assertEqual(opened.status_code, 200)
        launch.assert_called_once()

    def test_rejects_file_or_directory_swaps_before_opening_the_descriptor(self):
        real_open = os.open
        for swap in ("file_link", "file_replacement", "directory_link"):
            with self.subTest(swap=swap):
                note = self._note()
                replacement = Path(self.tmp.name) / "replacement.md"
                replacement.write_bytes(note.read_bytes().replace(b"Body only.", b"private synthetic"))
                actual_root = self.daily_root.with_name("held-notes")
                swapped = False

                def opening(path, flags, **kwargs):
                    nonlocal swapped
                    if not swapped and ("dir_fd" in kwargs if swap != "directory_link" else Path(path) == self.daily_root):
                        swapped = True
                        if swap == "file_link":
                            note.unlink()
                            note.symlink_to(replacement)
                        elif swap == "file_replacement":
                            replacement.replace(note)
                        else:
                            self.daily_root.rename(actual_root)
                            self.daily_root.symlink_to(actual_root, target_is_directory=True)
                    return real_open(path, flags, **kwargs)

                with mock.patch.object(os, "open", side_effect=opening):
                    self._assert_refused(self._get())
                if swap == "directory_link":
                    self.daily_root.unlink()
                    actual_root.rename(self.daily_root)
                elif swap == "file_link":
                    note.unlink()

    def test_changes_during_read_and_midnight_rollover_withhold_the_body(self):
        real_fdopen = os.fdopen
        for change in ("replace", "modify", "delete"):
            with self.subTest(change=change):
                note = self._note()
                original = note.read_bytes()

                def stream_open(*args, **kwargs):
                    stream = real_fdopen(*args, **kwargs)
                    actual_read = stream.read

                    def changed_read(size):
                        data = actual_read(size)
                        if change == "replace":
                            replacement = note.with_name("replacement.md")
                            replacement.write_bytes(original)
                            replacement.replace(note)
                        elif change == "modify":
                            before = note.stat()
                            note.write_bytes(original.replace(b"Body", b"Edit"))
                            os.utime(note, ns=(before.st_atime_ns, before.st_mtime_ns + 1))
                        else:
                            note.unlink()
                        return data

                    stream.read = changed_read
                    return stream

                with mock.patch.object(os, "fdopen", side_effect=stream_open):
                    self._assert_refused(self._get())
        self._note()
        with mock.patch.object(self.overview, "completed_daily_note_day", side_effect=[self.day, "2026-09-01"]):
            self._assert_refused(self._get())


if __name__ == "__main__":
    unittest.main()
