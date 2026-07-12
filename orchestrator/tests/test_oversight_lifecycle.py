"""Conversation-lifecycle coverage for durable oversight derivatives."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
ROOT = ORCH.parent
for value in (str(ORCH), str(ROOT)):
    if value not in sys.path:
        sys.path.insert(0, value)

import live_guard  # noqa: E402,F401
import oversight_actions as actions  # noqa: E402
import oversight_events as events  # noqa: E402
import oversight_queue as oversight_queue  # noqa: E402
import oversight_relationships as relationships  # noqa: E402
import oversight_router as router  # noqa: E402
import redefinition_handler  # noqa: E402
import resolution_chain  # noqa: E402
import tool_events  # noqa: E402
from oversight_context import OversightContextBundle  # noqa: E402
from ped_parser import parse_ped_file  # noqa: E402


PED_TEXT = """---
nexus:
  - project
type: PED
---

# Project

## Decision Log

### User-authored entry
Never remove this paragraph.
"""


class OversightLifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ora-oversight-life-")
        self.root = Path(self.temp.name)
        self.ped = self.root / "project.md"
        self.ped.write_text(PED_TEXT, encoding="utf-8")
        self.manifest = self.root / "conversation-ped-derivatives.json"
        self.counters = self.root / "revise-counters.json"
        self.events_log = self.root / "events.jsonl"
        self.actions_log = self.root / "actions.jsonl"
        self.router_log = self.root / "router.jsonl"
        self.queue_log = self.root / "human-queue.jsonl"
        self.patchers = [
            mock.patch.object(actions, "PED_DERIVATIVES_PATH", str(self.manifest)),
            mock.patch.object(actions, "REVISE_COUNTERS_PATH", str(self.counters)),
            mock.patch.object(actions, "ACTIONS_LOG_PATH", str(self.actions_log)),
            mock.patch.object(actions, "HUMAN_QUEUE_PATH", str(self.queue_log)),
            mock.patch.object(
                oversight_queue, "HUMAN_QUEUE_PATH", str(self.queue_log),
            ),
            mock.patch.object(events, "EVENT_LOG_PATH", str(self.events_log)),
            mock.patch.object(relationships, "EVENTS_LOG_PATH", str(self.events_log)),
            mock.patch.object(relationships, "ACTIONS_LOG_PATH", str(self.actions_log)),
            mock.patch.object(router, "ROUTER_LOG_PATH", str(self.router_log)),
        ]
        for patcher in self.patchers:
            patcher.start()
        self._clear_oversight_contexts()

    def tearDown(self):
        self._clear_oversight_contexts()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    @staticmethod
    def _clear_oversight_contexts() -> None:
        for module_name in ("oversight_events", "orchestrator.oversight_events"):
            module = sys.modules.get(module_name)
            if module is not None:
                module.clear_stealth_context()
                module.clear_conversation_id_context()

    @staticmethod
    def bundle(event: dict) -> OversightContextBundle:
        return OversightContextBundle(
            event=event,
            event_class="project-level",
            project_level_locks={},
        )


class TestStealthOversightSuppression(OversightLifecycleTestCase):
    def test_explicit_stealth_event_skips_bus_log_without_thread_local(self):
        with mock.patch.object(events, "_handlers", []):
            emitted = events.emit({
                "event_type": "MilestoneClaimed",
                "conversation_id": "explicit-stealth",
                "tag": "stealth",
            })
        self.assertTrue(emitted["stealth"])
        self.assertFalse(self.events_log.exists())

    def test_apply_verdict_suppresses_every_durable_side_effect(self):
        event = {
            "event_type": "MilestoneClaimed",
            "project_nexus": "project",
            "milestone_text": "Secret milestone",
            "conversation_id": "stealth-conversation",
            "stealth": True,
        }
        original = self.ped.read_text(encoding="utf-8")
        with mock.patch("ped_watcher.load_ped_path", return_value=str(self.ped)):
            result = actions.apply_verdict(
                event,
                self.bundle(event),
                "PC-Milestone",
                {"verdict": "REVISE", "reasoning": "secret correction"},
            )
        self.assertEqual(result["action"], "stealth_suppressed")
        self.assertEqual(self.ped.read_text(encoding="utf-8"), original)
        for path in (
            self.manifest, self.counters, self.actions_log, self.queue_log,
        ):
            self.assertFalse(path.exists(), f"Stealth created {path}")

    def test_router_suppresses_before_context_model_or_parent_fanout(self):
        event = {
            "event_type": "MilestoneClaimed",
            "project_nexus": "project",
            "conversation_id": "stealth-conversation",
            "stealth": True,
        }
        with mock.patch.object(router, "load_context") as load_context, \
                mock.patch.object(router, "_maybe_fan_out_to_parent") as fanout:
            result = router.process_event(event, live=True)
        self.assertEqual(result["action"], "stealth_suppressed")
        load_context.assert_not_called()
        fanout.assert_not_called()
        self.assertFalse(self.router_log.exists())

    def test_parent_fanout_is_suppressed_for_explicit_stealth_event(self):
        event = {
            "event_type": "MilestoneBlocked",
            "project_nexus": "child",
            "conversation_id": "stealth-conversation",
            "stealth": True,
        }
        with mock.patch.object(relationships, "load_ped_path") as load_path:
            self.assertIsNone(relationships.notify_parent(event, "parent"))
        load_path.assert_not_called()
        self.assertFalse(self.events_log.exists())

    def test_existing_queue_is_not_mutated_from_stealth_handler_context(self):
        record = {
            "id": "entry-1",
            "name": "Original",
            "queued_at": "2026-01-01T00:00:00+00:00",
            "event": {"event_type": "MilestoneBlocked"},
        }
        original = json.dumps(record) + "\n"
        self.queue_log.write_text(original, encoding="utf-8")
        with events.lifecycle_context_scope(
            stealth=True, conversation_id="stealth-queue",
        ):
            self.assertFalse(oversight_queue.rename("entry-1", "Changed"))
            self.assertFalse(oversight_queue.remove_by_id("entry-1"))
        self.assertEqual(self.queue_log.read_text(encoding="utf-8"), original)

    def test_redefinition_and_resolution_commits_are_ephemeral_in_stealth(self):
        with events.lifecycle_context_scope(
            stealth=True, conversation_id="stealth-resolution",
        ), mock.patch.object(
            redefinition_handler, "list_pending_escalations",
        ) as pending, mock.patch.object(
            resolution_chain, "_commit_approve_as_proposed",
        ) as commit:
            result = redefinition_handler.approve_redefinition(0)
            message = resolution_chain.continue_resolution(
                resolution_chain.ContinuationContext("queue", ""),
                [], "1", conversation_id="stealth-resolution",
            )
        self.assertFalse(result.success)
        self.assertIn("Stealth", result.error)
        pending.assert_not_called()
        commit.assert_not_called()
        self.assertIn("suppressed in Stealth", message)


class TestLifecycleContextScope(OversightLifecycleTestCase):
    def test_scope_restores_oversight_and_tool_context_after_exception(self):
        import orchestrator.oversight_events as package_events
        import orchestrator.tool_events as package_tools

        events.set_stealth_context(False)
        events.set_conversation_id_context("prior-top")
        package_events.set_stealth_context(True)
        package_events.set_conversation_id_context("prior-package")
        top_token = tool_events.set_turn_context(
            conversation_id="prior-tool-top", surface="prior",
        )
        package_token = package_tools.set_turn_context(
            conversation_id="prior-tool-package", surface="prior",
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                with events.lifecycle_context_scope(
                    stealth=True,
                    conversation_id="current",
                    tool_context={"trace_dir": "/tmp/current", "surface": "chat"},
                ):
                    self.assertEqual(events._get_conversation_id_context(), "current")
                    self.assertEqual(
                        package_events._get_conversation_id_context(), "current",
                    )
                    self.assertTrue(events._is_stealth_context())
                    self.assertTrue(package_events._is_stealth_context())
                    self.assertEqual(
                        tool_events.get_turn_context()["conversation_id"], "current",
                    )
                    self.assertEqual(
                        package_tools.get_turn_context()["conversation_id"], "current",
                    )
                    # Legacy inner setters still exist in the server while the
                    # wrapper lands. Their ignored tokens must not defeat the
                    # outer scope's exact restoration.
                    events.set_stealth_context(False)
                    events.set_conversation_id_context("inner-oversight")
                    tool_events.set_turn_context(
                        conversation_id="inner-tool", surface="inner",
                    )
                    raise RuntimeError("stop")

            self.assertFalse(events._is_stealth_context())
            self.assertEqual(events._get_conversation_id_context(), "prior-top")
            self.assertTrue(package_events._is_stealth_context())
            self.assertEqual(
                package_events._get_conversation_id_context(), "prior-package",
            )
            self.assertEqual(
                tool_events.get_turn_context()["conversation_id"], "prior-tool-top",
            )
            self.assertEqual(
                package_tools.get_turn_context()["conversation_id"],
                "prior-tool-package",
            )
        finally:
            tool_events.reset_turn_context(top_token)
            package_tools.reset_turn_context(package_token)


class TestManagedPedDerivatives(OversightLifecycleTestCase):
    def append(self, conversation_id: str, text: str, *, tag: str = "") -> str:
        record: dict = {}
        derivative_id = actions.append_managed_decision_log_entry(
            str(self.ped),
            text,
            {
                "event_type": "MilestoneClaimed",
                "conversation_id": conversation_id,
                "tag": tag,
            },
            kind="test",
            action_record=record,
        )
        self.assertIsNotNone(derivative_id, record)
        return str(derivative_id)

    def test_standard_block_has_exact_markers_and_delete_is_surgical(self):
        derivative_id = self.append("conversation-a", "Conversation A text\n\n")
        self.append("conversation-b", "Conversation B text\n\n")
        before = self.ped.read_text(encoding="utf-8")
        self.assertIn(
            f"ora:oversight-derivative:start id={derivative_id}", before,
        )
        self.assertIn(
            f"ora:oversight-derivative:end id={derivative_id}", before,
        )
        parsed = parse_ped_file(str(self.ped))
        self.assertTrue(parsed.decision_log)
        self.assertTrue(all(
            "ora:oversight-derivative" not in entry.raw_text
            for entry in parsed.decision_log
        ))

        event = {
            "conversation_id": "conversation-a",
            "project_nexus": "project",
            "milestone_id": "m1",
        }
        key = actions._revise_key(event)
        actions._save_revise_counters({key: 2}, event)
        report = actions.purge_conversation_ped_derivatives(
            "conversation-a", discover_root=self.root,
        )
        after = self.ped.read_text(encoding="utf-8")
        self.assertEqual(report["manifest_entries"], 1)
        self.assertEqual(report["ped_blocks"], 1)
        self.assertEqual(report["counter_entries"], 1)
        self.assertEqual(report["errors"], [])
        self.assertNotIn("Conversation A text", after)
        self.assertIn("Conversation B text", after)
        self.assertIn("Never remove this paragraph.", after)
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["derivatives"]), 1)
        self.assertEqual(
            payload["derivatives"][0]["conversation_id"], "conversation-b",
        )

    def test_private_sidecar_round_trip_never_loses_reversible_text(self):
        derivative_id = self.append(
            "private-conversation", "Private decision text\n\n", tag="private",
        )
        self.assertNotIn(
            "Private decision text", self.ped.read_text(encoding="utf-8"),
        )
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        entry = payload["derivatives"][0]
        self.assertEqual(entry["derivative_id"], derivative_id)
        self.assertEqual(entry["entry_text"], "Private decision text\n\n")
        self.assertFalse(entry["visible"])

        restored = actions.set_conversation_ped_derivatives_private(
            "private-conversation", False,
        )
        self.assertEqual(restored["errors"], [])
        self.assertIn(str(self.ped), restored["requires_reindex"])
        self.assertIn(
            "Private decision text", self.ped.read_text(encoding="utf-8"),
        )

        hidden = actions.set_conversation_ped_derivatives_private(
            "private-conversation", True,
        )
        self.assertEqual(hidden["errors"], [])
        self.assertIn(str(self.ped), hidden["requires_reindex"])
        self.assertNotIn(
            "Private decision text", self.ped.read_text(encoding="utf-8"),
        )
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(payload["derivatives"][0]["entry_text"],
                         "Private decision text\n\n")
        self.assertFalse(payload["derivatives"][0]["visible"])

    def test_first_turn_private_context_never_writes_visible_ped_text(self):
        import boot

        token = boot.set_conversation_tag_context("private")
        try:
            derivative_id = actions.append_managed_decision_log_entry(
                str(self.ped),
                "First-turn private text\n\n",
                {"conversation_id": "private-first-turn"},
                kind="test_first_turn",
                action_record={},
            )
        finally:
            boot.reset_conversation_tag_context(token)
        self.assertIsNotNone(derivative_id)
        self.assertNotIn(
            "First-turn private text", self.ped.read_text(encoding="utf-8"),
        )
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(payload["derivatives"][0]["entry_text"],
                         "First-turn private text\n\n")
        self.assertFalse(payload["derivatives"][0]["visible"])

    def test_unterminated_marker_fails_loudly_without_rewriting(self):
        derivative_id = self.append("conversation-a", "Owned text\n\n")
        broken = self.ped.read_text(encoding="utf-8").replace(
            f"<!-- ora:oversight-derivative:end id={derivative_id} -->", "",
        )
        self.ped.write_text(broken, encoding="utf-8")
        report = actions.purge_conversation_ped_derivatives("conversation-a")
        self.assertTrue(report["errors"])
        self.assertEqual(report["failed_paths"], [str(self.ped)])
        self.assertIn(str(self.ped), report["requires_reindex"])
        self.assertIn("Owned text", self.ped.read_text(encoding="utf-8"))
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["derivatives"]), 1)

    def test_concurrent_appends_share_manifest_and_ped_locks(self):
        def append(index: int) -> str | None:
            return actions.append_managed_decision_log_entry(
                str(self.ped),
                f"Concurrent entry {index}\n\n",
                {"conversation_id": f"conversation-{index}", "tag": ""},
                kind="test_concurrent",
                action_record={},
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            derivative_ids = list(pool.map(append, range(12)))
        self.assertTrue(all(derivative_ids))
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["derivatives"]), 12)
        content = self.ped.read_text(encoding="utf-8")
        self.assertEqual(content.count("ora:oversight-derivative:start"), 12)
        for index in range(12):
            self.assertIn(f"Concurrent entry {index}", content)

    def test_privacy_transition_resolves_a_moved_registered_ped(self):
        record: dict = {}
        actions.append_managed_decision_log_entry(
            str(self.ped),
            "Move-aware entry\n\n",
            {
                "conversation_id": "conversation-moved",
                "project_nexus": "project",
                "tag": "",
            },
            kind="test_moved",
            action_record=record,
        )
        moved = self.root / "project-moved.md"
        self.ped.rename(moved)
        with mock.patch("ped_watcher.load_ped_path", return_value=str(moved)):
            report = actions.set_conversation_ped_derivatives_private(
                "conversation-moved", True,
            )
        self.assertEqual(report["errors"], [])
        self.assertNotIn("Move-aware entry", moved.read_text(encoding="utf-8"))
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(payload["derivatives"][0]["ped_path"], str(moved))

    def test_privacy_recovers_unmanifested_owned_block_before_hiding(self):
        self.append("conversation-recovered", "Recover this text\n\n")
        self.manifest.unlink()
        hidden = actions.set_conversation_ped_derivatives_private(
            "conversation-recovered", True, discover_root=self.root,
        )
        self.assertEqual(hidden["errors"], [])
        self.assertNotIn("Recover this text", self.ped.read_text(encoding="utf-8"))
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["derivatives"]), 1)
        self.assertEqual(
            payload["derivatives"][0]["kind"], "recovered_marker_block",
        )
        self.assertIn("Recover this text", payload["derivatives"][0]["entry_text"])
        restored = actions.set_conversation_ped_derivatives_private(
            "conversation-recovered", False,
        )
        self.assertEqual(restored["errors"], [])
        self.assertIn("Recover this text", self.ped.read_text(encoding="utf-8"))

    def test_privacy_reports_failed_markdown_paths_structurally(self):
        self.append("conversation-broken-private", "Owned private text\n\n")
        content = self.ped.read_text(encoding="utf-8")
        self.ped.write_text(
            content.replace("<!-- ora:oversight-derivative:end", "<!-- broken:end"),
            encoding="utf-8",
        )
        report = actions.set_conversation_ped_derivatives_private(
            "conversation-broken-private", True,
        )
        self.assertTrue(report["errors"])
        self.assertEqual(report["failed_paths"], [str(self.ped)])
        self.assertIn(str(self.ped), report["requires_reindex"])

    def test_corrupt_manifest_cannot_authorize_external_ped_mutation_or_reindex(self):
        with tempfile.TemporaryDirectory(prefix="ora-external-ped-") as outside:
            external = Path(outside) / "external.md"
            external.write_text(PED_TEXT + "\nExternal secret.\n", encoding="utf-8")
            original = external.read_text(encoding="utf-8")
            payload = {
                "version": 1,
                "derivatives": [{
                    "derivative_id": "a" * 32,
                    "conversation_id": "conversation-external",
                    "owner_key": actions._owner_key("conversation-external"),
                    "ped_path": str(external),
                    "project_nexus": "",
                    "kind": "corrupt",
                    "entry_text": "External secret.\n",
                    "visible": True,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }],
            }
            self.manifest.write_text(json.dumps(payload), encoding="utf-8")

            privacy = actions.set_conversation_ped_derivatives_private(
                "conversation-external", True, discover_root=self.root,
            )
            self.assertTrue(privacy["errors"])
            self.assertEqual(privacy["failed_paths"], [str(external)])
            self.assertNotIn(str(external), privacy["requires_reindex"])
            self.assertEqual(external.read_text(encoding="utf-8"), original)

            purge = actions.purge_conversation_ped_derivatives(
                "conversation-external", discover_root=self.root,
            )
            self.assertTrue(purge["errors"])
            self.assertEqual(purge["failed_paths"], [str(external)])
            self.assertNotIn(str(external), purge["requires_reindex"])
            self.assertEqual(external.read_text(encoding="utf-8"), original)
            retained = json.loads(self.manifest.read_text(encoding="utf-8"))
            self.assertEqual(len(retained["derivatives"]), 1)

    def test_manifest_final_symlink_is_rejected_inside_trusted_root(self):
        with tempfile.TemporaryDirectory(prefix="ora-symlink-target-") as outside:
            external = Path(outside) / "target.md"
            external.write_text(PED_TEXT, encoding="utf-8")
            link = self.root / "linked.md"
            link.symlink_to(external)
            payload = {
                "version": 1,
                "derivatives": [{
                    "derivative_id": "b" * 32,
                    "conversation_id": "conversation-symlink",
                    "owner_key": actions._owner_key("conversation-symlink"),
                    "ped_path": str(link),
                    "project_nexus": "",
                    "kind": "corrupt",
                    "entry_text": "Never write this.\n",
                    "visible": True,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }],
            }
            self.manifest.write_text(json.dumps(payload), encoding="utf-8")
            report = actions.set_conversation_ped_derivatives_private(
                "conversation-symlink", True, discover_root=self.root,
            )
            self.assertTrue(report["errors"])
            self.assertIn(str(link), report["failed_paths"])
            self.assertNotIn(str(link), report["requires_reindex"])
            self.assertEqual(external.read_text(encoding="utf-8"), PED_TEXT)

    def test_trusted_root_itself_may_be_a_symlink(self):
        real_root = self.root / "real-vault"
        real_root.mkdir()
        ped = real_root / "inside.md"
        ped.write_text(PED_TEXT, encoding="utf-8")
        actions.append_managed_decision_log_entry(
            str(ped), "Inside trusted root.\n\n",
            {"conversation_id": "conversation-root-link", "tag": ""},
            kind="test_root_link", action_record={},
        )
        root_link = self.root / "vault-link"
        root_link.symlink_to(real_root, target_is_directory=True)
        report = actions.purge_conversation_ped_derivatives(
            "conversation-root-link", discover_root=root_link,
        )
        self.assertEqual(report["errors"], [])
        self.assertNotIn("Inside trusted root.", ped.read_text(encoding="utf-8"))


class TestParentOwnershipPropagation(OversightLifecycleTestCase):
    def test_parent_synthesized_event_action_and_ped_keep_conversation_id(self):
        child_ped = self.root / "child.md"
        child_ped.write_text(PED_TEXT, encoding="utf-8")

        def locate(nexus: str):
            return str(self.ped if nexus == "parent" else child_ped)

        child_event = {
            "event_type": "MilestoneBlocked",
            "project_nexus": "child",
            "block_reason": "input missing",
            "conversation_id": "conversation-parent-source",
            "tag": "",
        }
        with mock.patch.object(relationships, "load_ped_path", side_effect=locate):
            synthesized = relationships.notify_parent(child_event, "parent")
        self.assertIsNotNone(synthesized)
        self.assertEqual(
            synthesized["conversation_id"], "conversation-parent-source",
        )
        event_record = json.loads(self.events_log.read_text().splitlines()[0])
        action_record = json.loads(self.actions_log.read_text().splitlines()[0])
        self.assertEqual(
            event_record["conversation_id"], "conversation-parent-source",
        )
        self.assertEqual(
            action_record["conversation_id"], "conversation-parent-source",
        )
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["derivatives"][0]["conversation_id"],
            "conversation-parent-source",
        )
        self.assertEqual(
            manifest["derivatives"][0]["kind"], "parent_project_fanout",
        )

    def test_parent_fanout_preserves_explicit_private_tag_in_sidecar(self):
        child_ped = self.root / "child-private.md"
        child_ped.write_text(PED_TEXT, encoding="utf-8")

        def locate(nexus: str):
            return str(self.ped if nexus == "parent" else child_ped)

        with mock.patch.object(relationships, "load_ped_path", side_effect=locate):
            synthesized = relationships.notify_parent({
                "event_type": "MilestoneBlocked",
                "project_nexus": "child",
                "block_reason": "private reason",
                "conversation_id": "private-parent-source",
                "tag": "private",
            }, "parent")
        self.assertEqual(synthesized["conversation_tag"], "private")
        self.assertNotIn(
            "private reason", self.ped.read_text(encoding="utf-8"),
        )
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertIn("private reason", payload["derivatives"][0]["entry_text"])
        self.assertFalse(payload["derivatives"][0]["visible"])


if __name__ == "__main__":
    unittest.main()
