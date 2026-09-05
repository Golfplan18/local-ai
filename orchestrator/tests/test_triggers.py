"""Adversarial tests for the user-authored Trigger surface.

Every test here proves a user-visible behaviour or a stated guarantee — that a
clock trigger cannot be deployed without a written reason, that a selector
pointed at an unwatched directory is refused instead of silently never firing,
that the same bytes fire once, that an approved action changed behind Ora's
back fails closed, and that a week-long outage produces one firing rather than
seven. Helpers and serialization details are deliberately not tested.

Run::

    /opt/homebrew/bin/python3 -m pytest orchestrator/tests/test_triggers.py -q
"""
from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import live_guard  # noqa: E402,F401  — arm the oversight write quarantine

from orchestrator import runtime_hygiene as hygiene  # noqa: E402
from orchestrator import triggers  # noqa: E402
import oversight_queue  # noqa: E402
import system_protection  # noqa: E402
import tool_events  # noqa: E402


def _inline(work):
    """Executor that runs a firing on the calling thread.

    Firings run on their own thread in production so a minutes-long framework
    run cannot hold the deadline lane. Tests assert on the finished record, so
    they run the same code path synchronously rather than racing it.
    """
    work()


class TriggerBase(unittest.TestCase):
    """Redirect the data root; no test touches the live tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.watched = self.root / "watched"
        self.watched.mkdir()
        patcher = mock.patch.object(hygiene._rp, "DATA_DIR_STR", str(self.data))
        patcher.start()
        self.addCleanup(patcher.stop)
        trigger_root = mock.patch.object(
            triggers._rp, "DATA_DIR_STR", str(self.data)
        )
        trigger_root.start()
        self.addCleanup(trigger_root.stop)
        protection_paths = (
            mock.patch.object(
                system_protection, "_actions_path",
                return_value=str(self.root / "actions.jsonl"),
            ),
            mock.patch.object(
                tool_events, "APPROVALS_PATH", str(self.root / "approvals.json"),
            ),
            mock.patch.object(
                tool_events, "GLOBAL_SINK_DEFAULT",
                str(self.root / "tool-events.jsonl"),
            ),
            mock.patch.object(
                oversight_queue, "HUMAN_QUEUE_PATH", str(self.root / "queue.jsonl"),
            ),
        )
        for patcher in protection_paths:
            patcher.start()
            self.addCleanup(patcher.stop)
        tool_events._queued_hashes.clear()
        tool_events._queue_reservations.clear()
        self.addCleanup(tool_events._queued_hashes.clear)
        self.addCleanup(tool_events._queue_reservations.clear)
        turn_token = tool_events.set_turn_context(
            conversation_id="trigger-test", surface="test",
        )
        self.addCleanup(tool_events.reset_turn_context, turn_token)
        roots = mock.patch.object(
            triggers, "_watch_roots", lambda: [str(self.watched.resolve())])
        roots.start()
        self.addCleanup(roots.stop)
        # A fresh interned queue per test — deadline_queue() caches by path.
        self.queue = hygiene.DeadlineQueue(self.data / "runtime-hygiene")
        self.service = triggers.TriggerService(queue=self.queue, executor=_inline)
        triggers._RUNNING.clear()
        self.addCleanup(triggers._RUNNING.clear)

    # -- fixtures -------------------------------------------------------

    def make_project(self, *, script="run.py", script_body="print('{}')",
                     nexus="fixture", interface="argv-stdout-json"):
        """Register a real project whose tool is a real script on disk.

        Registration goes through ``register_project``, so the pointer binds
        the manifest bytes exactly as it does in production — which is what
        makes the drift tests below meaningful rather than staged.
        """
        import project_registry as pr

        project_root = self.root / "project"
        project_root.mkdir(exist_ok=True)
        (project_root / script).write_text(script_body, encoding="utf-8")
        manifest = {
            "nexus": nexus, "name": "Fixture Project", "version": "1.0.0",
            "tools": [{"name": "run",
                       "command": [sys.executable, script],
                       "interface": interface}],
        }
        (project_root / "ora-project.json").write_text(
            json.dumps(manifest), encoding="utf-8")

        pointer_dir = self.data / "projects"
        pointer_dir.mkdir(parents=True, exist_ok=True)
        pr.register_project(str(project_root), pointer_dir=str(pointer_dir))
        self._bind_pointer_dir(pr, str(pointer_dir))
        return project_root, project_root / script

    def _bind_pointer_dir(self, pr, pointer_dir):
        """Point the registry's public reads at this test's pointer dir.

        ``POINTER_DIR`` is a default argument baked at definition time, so
        patching the module constant alone would not reach these callers.
        """
        if getattr(self, "_pointer_bound", False):
            return
        self._pointer_bound = True
        pointer_constant = mock.patch.object(pr, "POINTER_DIR", pointer_dir)
        pointer_constant.start()
        self.addCleanup(pointer_constant.stop)
        real_get, real_list, real_invoke = (
            pr.get_project, pr.list_projects, pr.invoke_project_tool)
        for name, bound in (
            ("get_project",
             lambda nexus, pointer_dir=pointer_dir: real_get(nexus, pointer_dir)),
            ("list_projects",
             lambda pointer_dir=pointer_dir: real_list(pointer_dir)),
            ("invoke_project_tool",
             lambda nexus, tool, pointer_dir=pointer_dir, **kw:
                 real_invoke(nexus, tool, pointer_dir=pointer_dir, **kw)),
        ):
            patcher = mock.patch.object(pr, name, bound)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tool_spec(self, **overrides):
        spec = {
            "trigger_id": "nightly", "name": "Nightly export",
            "cause": "manual", "condition": {},
            "action": {"kind": "project_tool", "nexus": "fixture",
                       "tool": "run", "args": []},
        }
        spec.update(overrides)
        return spec

    def calendar_condition(self, **overrides):
        schedule = {
            "timezone": "America/New_York", "local_time": "07:30",
            "cadence": "daily", "weekdays": [], "start_date": "2026-01-01",
            "missed_policy": "run_once", "grace_seconds": 300,
        }
        schedule.update(overrides)
        return {"schedule": schedule}

    def activate(self, trigger_id):
        review = self.service.activation_review(trigger_id)
        return self.service.activate(
            trigger_id, expected_spec_digest=review["spec_digest"])


# ── The Runtime Principle, enforced rather than asked for ────────────────


class RuntimePrincipleTests(TriggerBase):
    def test_calendar_trigger_is_refused_without_a_written_reason(self):
        self.make_project()
        with self.assertRaises(triggers.TriggerInputRequired) as caught:
            self.service.create(self.tool_spec(
                cause="calendar", condition=self.calendar_condition()))
        self.assertIn("runtime-impossibility", str(caught.exception))

    def test_a_token_reason_is_not_a_reason(self):
        self.make_project()
        with self.assertRaises(triggers.TriggerInputRequired):
            self.service.create(self.tool_spec(
                cause="calendar", condition=self.calendar_condition(),
                runtime_justification="because"))

    def test_calendar_trigger_activates_with_a_substantive_reason(self):
        self.make_project()
        self.service.create(self.tool_spec(
            cause="calendar", condition=self.calendar_condition(),
            runtime_justification=(
                "The upstream provider expires its session credentials on its "
                "own clock and offers no expiry callback, so time is the cause.")))
        state = self.activate("nightly")
        self.assertEqual(state["status"], "active")
        self.assertTrue(state["next_due_at"])
        self.assertIn("only while Ora is running", state["intermittency"])

    def test_non_calendar_triggers_may_not_carry_a_justification(self):
        self.make_project()
        with self.assertRaises(triggers.TriggerInputRequired):
            self.service.create(self.tool_spec(
                runtime_justification=(
                    "a manual trigger has no temporal cause to justify at all")))

    def test_a_literal_command_is_not_an_action(self):
        with self.assertRaises(triggers.TriggerInputRequired) as caught:
            self.service.create(self.tool_spec(
                action={"kind": "command", "argv": ["/bin/sh", "-c", "rm -rf /"]}))
        self.assertIn("ora-project.json", str(caught.exception))


# ── Event surfaces that could never fire are refused, not accepted ───────


class WatchRootTests(TriggerBase):
    def test_selector_outside_a_watched_root_is_refused_with_its_reason(self):
        self.make_project()
        outside = self.root / "elsewhere" / "notes.md"
        outside.parent.mkdir()
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(triggers.TriggerInputRequired) as caught:
            self.service.create(self.tool_spec(
                cause="file_change",
                condition={"path_selectors": [str(outside)]}))
        message = str(caught.exception)
        self.assertIn("not inside a watched root", message)
        self.assertIn(str(self.watched.resolve()), message)

    def test_relative_selector_is_refused(self):
        self.make_project()
        with self.assertRaises(triggers.TriggerInputRequired):
            self.service.create(self.tool_spec(
                cause="file_change", condition={"path_selectors": ["notes.md"]}))

    def test_selector_the_event_lane_ignores_is_refused(self):
        self.make_project()
        hidden = self.watched / ".git" / "config"
        hidden.parent.mkdir()
        hidden.write_text("x", encoding="utf-8")
        with self.assertRaises(triggers.TriggerInputRequired) as caught:
            self.service.create(self.tool_spec(
                cause="file_change", condition={"path_selectors": [str(hidden)]}))
        self.assertIn("can never fire", str(caught.exception))


# ── File-change firing binds exact identities ────────────────────────────


class FileChangeFiringTests(TriggerBase):
    def setUp(self):
        super().setUp()
        self.make_project()
        self.subject = self.watched / "note.md"
        self.subject.write_text("first", encoding="utf-8")
        self.service.create(self.tool_spec(
            cause="file_change",
            condition={"path_selectors": [str(self.watched)]}))
        self.activate("nightly")

    def test_same_bytes_fire_once_and_changed_bytes_fire_again(self):
        first = self.service.dispatch_paths([str(self.subject)])
        self.assertEqual(len(first["fired"]), 1)
        self.assertFalse(first["fired"][0]["duplicate"])

        repeat = self.service.dispatch_paths([str(self.subject)])
        self.assertEqual(repeat["fired"][0]["event_id"],
                         first["fired"][0]["event_id"])
        # A redelivery reports itself as one, rather than overstating the lane.
        self.assertTrue(repeat["fired"][0]["duplicate"])

        self.subject.write_text("second", encoding="utf-8")
        changed = self.service.dispatch_paths([str(self.subject)])
        self.assertNotEqual(changed["fired"][0]["event_id"],
                            first["fired"][0]["event_id"])
        self.assertFalse(changed["fired"][0]["duplicate"])

        firings = self.service.firings("nightly")
        self.assertEqual(len(firings), 2)
        self.assertTrue(all(row["status"] == "completed" for row in firings))

    def test_firing_binds_the_captured_file_identity(self):
        self.service.dispatch_paths([str(self.subject)])
        firing = self.service.firings("nightly")[0]
        bound = firing["source"]["paths"][0]
        self.assertEqual(bound["path"], str(self.subject.resolve()))
        self.assertEqual(bound["sha256"], hygiene.sha256_file(self.subject))
        self.assertTrue(bound["exists"])

    def test_an_unmatched_path_fires_nothing(self):
        other = self.root / "unrelated.md"
        other.write_text("x", encoding="utf-8")
        summary = self.service.dispatch_paths([str(other)])
        self.assertEqual(summary["fired"], [])

    def test_a_paused_trigger_does_not_fire(self):
        self.service.lifecycle("nightly", "pause")
        summary = self.service.dispatch_paths([str(self.subject)])
        self.assertEqual(summary["fired"], [])

        # A matching list view is only a candidate. If the Trigger is edited
        # and reactivated before claim, that old OS event must not substitute
        # the later specification even though the Trigger id still matches.
        self.service.lifecycle("nightly", "resume")
        stale_views = self.service.list_triggers()
        real_fire = self.service._fire

        def replace_before_claim(record, cause, source, **kwargs):
            self.service.lifecycle("nightly", "pause")
            self.service.update("nightly", self.tool_spec(
                cause="file_change",
                condition={"path_selectors": [str(self.watched)]},
                action={"kind": "project_tool", "nexus": "fixture",
                        "tool": "run", "args": ["later-specification"]},
            ))
            self.activate("nightly")
            return real_fire(record, cause, source, **kwargs)

        with (
            mock.patch.object(
                self.service, "list_triggers", return_value=stale_views,
            ),
            mock.patch.object(
                self.service, "_fire", side_effect=replace_before_claim,
            ),
        ):
            stale = self.service.dispatch_paths([str(self.subject)])
        self.assertEqual(stale["fired"], [])
        self.assertEqual(len(stale["errors"]), 1)
        self.assertIn("earlier Trigger specification", stale["errors"][0])
        self.assertEqual(self.service.firings("nightly"), [])


# ── Drift between approval and firing fails closed ───────────────────────


class DriftTests(TriggerBase):
    def test_a_re_registered_manifest_stops_an_approved_firing(self):
        """Approval binds what will run, not merely which name will run.

        A manifest edit alone already breaks the registry's own bytes-bound
        pointer. Re-registering repairs that — and would silently point an
        already-approved Trigger at a different command. This is the case the
        approved action binding exists for.
        """
        import project_registry as pr

        project_root, _script = self.make_project()
        self.service.create(self.tool_spec())
        self.activate("nightly")

        manifest_path = project_root / "ora-project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # An unregistered byte edit makes the Project unavailable at the
        # pre-claim binding check. It raises synchronously and creates no
        # failed-firing fiction because no action was admitted.
        manifest_path.write_text(
            manifest_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(triggers.TriggerConflict,
                                    "no project registered"):
            self.service.run_manual("nightly", request_id="unregistered-edit")
        self.assertEqual(self.service.firings("nightly"), [])

        # Explicit re-registration makes the edited Project valid again, but
        # it still cannot replace the action that activation approved.
        manifest["tools"][0]["command"] = [sys.executable, "other.py"]
        spawned = self.root / "drifted-tool-spawned"
        (project_root / "other.py").write_text(
            f"from pathlib import Path\nPath({str(spawned)!r}).write_text('bad')\n"
            "print('{}')\n",
            encoding="utf-8",
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        pr.register_project(str(project_root),
                            pointer_dir=str(self.data / "projects"))

        with self.assertRaisesRegex(triggers.TriggerConflict,
                                    "action_definition_drifted"):
            self.service.run_manual("nightly", request_id="after-edit")
        self.assertFalse(spawned.exists())
        self.assertEqual(self.service.firings("nightly"), [])

        # Identical manifest/program bytes at a different registered root are
        # still a different execution: cwd and ORA_PROJECT_ROOT both change.
        # Use a command with no script path so the root is the only binding
        # field capable of distinguishing these registrations.
        manifest = {
            "nexus": "root-bound", "name": "Root-bound Project",
            "version": "1.0.0",
            "tools": [{"name": "run", "command": [sys.executable],
                       "interface": "argv-stdout-json"}],
        }
        roots = [self.root / "registered-a", self.root / "registered-b"]
        for root in roots:
            root.mkdir()
            (root / "ora-project.json").write_text(
                json.dumps(manifest), encoding="utf-8",
            )
        pr.register_project(
            str(roots[0]), pointer_dir=str(self.data / "projects"),
        )
        self.service.create(self.tool_spec(
            trigger_id="root-bound", name="Root-bound",
            action={"kind": "project_tool", "nexus": "root-bound",
                    "tool": "run", "args": []},
        ))
        approved = self.activate("root-bound")
        self.assertEqual(
            approved["approved_action_binding"]["project_root"],
            str(roots[0].resolve()),
        )
        pr.register_project(
            str(roots[1]), pointer_dir=str(self.data / "projects"),
        )
        with self.assertRaisesRegex(
            triggers.TriggerConflict, "action_definition_drifted",
        ):
            self.service.run_manual(
                "root-bound", request_id="registered-root-changed",
            )
        self.assertEqual(self.service.firings("root-bound"), [])

        # A future public binding field is automatically authoritative at both
        # the standing-approval boundary and the final subprocess boundary.
        # Underscore-prefixed runtime objects remain deliberately internal.
        standing_record = self.service._require("root-bound")
        live_binding = triggers.resolve_action_binding(
            standing_record["spec"]["action"]
        )
        approved_binding = dict(live_binding)
        approved_binding["future_public_identity"] = "reviewed"
        standing_record["approved_action_binding"] = approved_binding
        changed_binding = dict(live_binding)
        changed_binding["future_public_identity"] = "changed"
        with self.assertRaisesRegex(
            system_protection.ProtectionDenied,
            "no longer matches the Project execution binding",
        ):
            system_protection.authorize_trigger_project_action(
                trigger_record=standing_record,
                binding=changed_binding,
            )

        expected_binding = dict(live_binding)
        expected_binding["future_public_identity"] = "reviewed"
        with mock.patch.object(
            pr.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0, stdout=b"{}", stderr=b"",
            ),
        ) as spawn:
            with self.assertRaisesRegex(
                pr.ProjectExecutionBindingError, "changed after approval",
            ):
                pr.invoke_project_tool(
                    "root-bound", "run", args=[],
                    expected_binding=expected_binding,
                )
        spawn.assert_not_called()

    def test_editing_a_trigger_returns_it_to_draft(self):
        self.make_project(script_body=(
            "import json, sys\n"
            "print(json.dumps({'argument': sys.argv[1]}))\n"
        ))
        held = []
        self.service = triggers.TriggerService(
            queue=self.queue, ledger=self.service.ledger, executor=held.append,
        )
        before = self.tool_spec(action={
            "kind": "project_tool", "nexus": "fixture", "tool": "run",
            "args": ["before-claim-edit"],
        })
        self.service.create(before)
        activated = self.activate("nightly")
        self.assertEqual(activated["status"], "active")
        self.service.run_manual("nightly", request_id="held-before-edit")
        self.assertEqual(len(held), 1)

        self.service.lifecycle("nightly", "pause")
        edited = self.service.update("nightly", self.tool_spec(
            name="Renamed",
            action={
                "kind": "project_tool", "nexus": "fixture", "tool": "run",
                "args": ["after-claim-edit"],
            },
        ))
        self.assertEqual(edited["status"], "draft")
        self.assertIsNone(edited["approved_spec_digest"])
        held.pop()()
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["status"], "completed")
        self.assertIn("before-claim-edit", firing["receipt"]["output_excerpt"])
        self.assertNotIn("after-claim-edit", firing["receipt"]["output_excerpt"])

    def test_activation_refuses_a_stale_digest(self):
        self.make_project()
        self.service.create(self.tool_spec())
        with self.assertRaises(triggers.TriggerConflict) as caught:
            self.service.activate("nightly", expected_spec_digest="sha256:stale")
        self.assertIn("re-read it", str(caught.exception))

    def test_an_active_trigger_cannot_be_edited_in_place(self):
        self.make_project()
        self.service.create(self.tool_spec())
        self.activate("nightly")
        with self.assertRaises(triggers.TriggerConflict):
            self.service.update("nightly", self.tool_spec(name="Sneaky"))


# ── The calendar cause compiles to one persisted deadline ────────────────


class CalendarTests(TriggerBase):
    JUSTIFICATION = (
        "The upstream provider expires credentials on its own clock and offers "
        "no expiry callback, so passage of time is genuinely the cause here.")

    def make_calendar(self, **schedule):
        self.make_project()
        self.service.create(self.tool_spec(
            cause="calendar", condition=self.calendar_condition(**schedule),
            runtime_justification=self.JUSTIFICATION))
        return self.activate("nightly")

    def test_activation_arms_exactly_one_future_deadline(self):
        state = self.make_calendar()
        pending = [record for record in self.queue._load()["deadlines"].values()
                   if record["status"] == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event_type"], triggers.DEADLINE_EVENT_TYPE)
        self.assertGreater(
            hygiene.instant_timestamp(pending[0]["due_at"]),
            datetime.now(timezone.utc).timestamp())
        self.assertEqual(state["armed_deadline_key"], pending[0]["key"])

    def test_pausing_cancels_the_armed_deadline(self):
        self.make_calendar()
        key = self.service.get("nightly")["armed_deadline_key"]
        self.service.lifecycle("nightly", "pause")
        self.assertEqual(self.queue.get(key)["status"], "cancelled")
        self.assertIsNone(self.service.get("nightly")["armed_deadline_key"])

    def test_pause_wins_a_race_against_a_dispatching_deadline(self):
        self.make_calendar()
        armed = self.queue.get(self.service.get("nightly")["armed_deadline_key"])
        self.service.lifecycle("nightly", "pause")
        receipt = self.service.handle_calendar_deadline(armed["payload"])
        self.assertEqual(receipt["outcome"], "stale")
        self.assertEqual(self.service.firings("nightly"), [])

    def test_a_missed_window_under_skip_records_a_skip_not_a_run(self):
        state = self.make_calendar(missed_policy="skip")
        stale = dict(self.queue.get(state["armed_deadline_key"])["payload"])
        stale["scheduled_for"] = hygiene.normalized_instant(
            (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        )
        receipt = self.service.handle_calendar_deadline(stale)
        self.assertEqual(receipt["outcome"], "skipped")
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["receipt"]["outcome"], "skipped")
        self.assertGreater(firing["receipt"]["late_by_seconds"], 60000)

    def test_a_week_long_outage_arms_one_occurrence_not_seven(self):
        state = self.make_calendar(missed_policy="skip")
        stale = dict(self.queue.get(state["armed_deadline_key"])["payload"])
        stale["scheduled_for"] = hygiene.normalized_instant(
            (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        )
        self.service.handle_calendar_deadline(stale)
        pending = [record for record in self.queue._load()["deadlines"].values()
                   if record["status"] == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertGreater(
            hygiene.instant_timestamp(pending[0]["due_at"]),
            datetime.now(timezone.utc).timestamp())

    def test_a_missed_window_under_run_once_runs_and_records_lateness(self):
        state = self.make_calendar(missed_policy="run_once")
        stale = dict(self.queue.get(state["armed_deadline_key"])["payload"])
        stale["scheduled_for"] = hygiene.normalized_instant(
            (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        )
        receipt = self.service.handle_calendar_deadline(stale)
        self.assertEqual(receipt["outcome"], "dispatched")
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["status"], "completed")
        self.assertGreater(firing["receipt"]["late_by_seconds"], 3600)

    def test_a_dst_gap_wall_time_resolves_to_a_real_instant(self):
        schedule = {
            "timezone": "America/New_York", "local_time": "02:30",
            "cadence": "daily", "weekdays": [], "start_date": "2026-01-01",
            "missed_policy": "skip", "grace_seconds": 300,
        }
        before_gap = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
        instant = triggers.next_occurrence(schedule, before_gap)
        # 02:30 does not exist on the spring-forward day; the first real local
        # instant is 03:00 EDT, which is 07:00 UTC.
        self.assertEqual(instant, datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc))

    def test_a_fixed_offset_timezone_is_refused(self):
        self.make_project()
        with self.assertRaises(triggers.TriggerInputRequired) as caught:
            self.service.create(self.tool_spec(
                cause="calendar",
                condition=self.calendar_condition(timezone="UTC+05:00"),
                runtime_justification=self.JUSTIFICATION))
        self.assertIn("IANA", str(caught.exception))

    def test_startup_rearms_active_calendar_triggers(self):
        self.make_calendar()
        key = self.service.get("nightly")["armed_deadline_key"]
        self.queue.cancel(key, reason="simulated loss")
        armed = self.service.arm_active_calendar_triggers()
        self.assertEqual(len(armed), 1)


# ── Completion chaining ──────────────────────────────────────────────────


class CompletionTests(TriggerBase):
    def setUp(self):
        super().setUp()
        self.make_project()
        self.service.create(self.tool_spec(trigger_id="first", name="First"))
        self.activate("first")

    def test_a_completed_firing_activates_its_dependant(self):
        self.service.create(self.tool_spec(
            trigger_id="second", name="Second", cause="trigger_completion",
            condition={"source_trigger_id": "first"}))
        self.activate("second")

        self.service.run_manual("first", request_id="r1")
        child = self.service.firings("second")
        self.assertEqual(len(child), 1)
        self.assertEqual(child[0]["status"], "completed")
        self.assertEqual(child[0]["source"]["source_trigger_id"], "first")

    def test_a_failed_firing_activates_nothing(self):
        self.service.create(self.tool_spec(
            trigger_id="second", name="Second", cause="trigger_completion",
            condition={"source_trigger_id": "first"}))
        self.activate("second")
        with mock.patch.object(triggers, "_execute_action",
                               side_effect=RuntimeError("boom")):
            self.service.run_manual("first", request_id="r1")
        self.assertEqual(self.service.firings("first")[0]["status"], "failed")
        self.assertEqual(self.service.firings("second"), [])

    def test_a_crash_after_source_completion_replays_one_child(self):
        self.service.create(self.tool_spec(
            trigger_id="second", name="Second", cause="trigger_completion",
            condition={"source_trigger_id": "first"}))
        self.activate("second")
        with mock.patch.object(
            self.service, "_dispatch_completion",
            side_effect=RuntimeError("simulated crash before child claim"),
        ):
            self.service.run_manual("first", request_id="r-crash")

        self.assertEqual(self.service.firings("first")[0]["status"], "completed")
        self.assertEqual(self.service.firings("second"), [])

        restarted = triggers.TriggerService(
            queue=self.queue, ledger=self.service.ledger, executor=_inline,
        )
        replayed = restarted.replay_completion_deliveries()
        self.assertEqual(len(replayed), 1)
        self.assertEqual(len(restarted.firings("second")), 1)
        self.assertEqual(restarted.replay_completion_deliveries(), [])
        self.assertEqual(len(restarted.firings("second")), 1)

    def test_completion_replays_after_source_row_is_pruned(self):
        self.service.create(self.tool_spec(
            trigger_id="second", name="Second", cause="trigger_completion",
            condition={"source_trigger_id": "first"}))
        self.activate("second")

        # The source can become terminal before its proof reaches the Trigger
        # store. That gap must run no child and must not expose a false pending
        # completion on the public Trigger view.
        with mock.patch.object(
            self.service, "_persist_completion_proof",
            side_effect=OSError("completion proof store unavailable"),
        ):
            self.service.run_manual("first", request_id="r-pruned")

        source = self.service.firings("first")[0]
        self.assertEqual(source["status"], "completed")
        source_event_id = source["event_id"]
        delivery = self.service._pending_completion_deliveries()[0]
        self.assertNotIn("source_completion", delivery)
        self.assertEqual(self.service.firings("second"), [])
        self.assertEqual(
            self.service.get("second")["pending_completions"], [],
        )
        listed = {
            view["spec"]["trigger_id"]: view
            for view in self.service.list_triggers()
        }
        self.assertEqual(listed["second"]["pending_completions"], [])

        # Startup reads the completed source without holding the Trigger lock,
        # then durably backfills its exact proof before the first child attempt.
        restarted = triggers.TriggerService(
            queue=self.queue, ledger=self.service.ledger, executor=_inline,
        )
        with mock.patch.object(
            restarted, "_deliver_completion",
            side_effect=RuntimeError("simulated crash before child claim"),
        ):
            self.assertEqual(restarted.replay_completion_deliveries(), [])

        delivery = restarted._pending_completion_deliveries()[0]
        self.assertEqual(
            delivery["source_completion"]["event_id"], source_event_id,
        )
        self.assertTrue(delivery["source_completion"]["completed_at"])
        self.assertTrue(triggers._completion_proof_matches_delivery(
            delivery, delivery["source_completion"],
        ))
        retry_view = restarted.get("second")["pending_completions"]
        self.assertEqual(len(retry_view), 1)
        self.assertEqual(retry_view[0]["state"], "pending_retry")
        self.assertEqual(
            retry_view[0]["source_completed_at"],
            delivery["source_completion"]["completed_at"],
        )
        self.assertEqual(restarted.firings("second"), [])

        # Once proof is durable, terminal pruning of the source row cannot
        # orphan the delivery. The later replay runs the child exactly once.
        ledger_module = sys.modules[self.service.ledger.__class__.__module__]
        with mock.patch.object(
            ledger_module, "LEDGER_TERMINAL_RETENTION", 1,
        ):
            for index in range(2):
                event_id = hygiene.event_identity(
                    "prune-fixture", {"index": index},
                )
                self.service.ledger.claim(
                    event_id=event_id, event_type="prune-fixture",
                    subject={"index": index},
                )
                self.service.ledger.transition(
                    event_id, {"claimed"}, "completed",
                    completed_at=triggers._now(),
                )
        self.assertIsNone(self.service.ledger.get(source_event_id))

        self.assertEqual(len(restarted.replay_completion_deliveries()), 1)
        self.assertEqual(len(restarted.firings("second")), 1)
        self.assertEqual(restarted.replay_completion_deliveries(), [])
        self.assertEqual(restarted.get("second")["pending_completions"], [])

        # The persisted delivery names the exact dependent admission. A later
        # pause/edit/reactivate cycle must stay visibly pending instead of
        # running the new action for the old source completion.
        restarted.lifecycle("second", "pause")
        restarted.create(self.tool_spec(
            trigger_id="third", name="Third", cause="trigger_completion",
            condition={"source_trigger_id": "first"},
        ))
        review = restarted.activation_review("third")
        restarted.activate("third", expected_spec_digest=review["spec_digest"])
        with mock.patch.object(
            restarted, "_deliver_completion",
            side_effect=RuntimeError("simulated crash before stale child claim"),
        ):
            restarted.run_manual("first", request_id="r-stale-child")
        pending = restarted._pending_completion_deliveries()
        self.assertEqual(len(pending), 1)
        old_admission = pending[0]["dependent_admission_identity"]
        retry_view = restarted.get("third")["pending_completions"]
        self.assertEqual(len(retry_view), 1)
        self.assertEqual(retry_view[0]["state"], "pending_retry")
        self.assertEqual(set(retry_view[0]), {
            "source_trigger_id", "source_event_id", "source_completed_at",
            "created_at", "state",
        })
        self.assertEqual(
            retry_view[0]["source_completed_at"],
            pending[0]["source_completion"]["completed_at"],
        )
        restarted.lifecycle("third", "pause")
        restarted.update("third", self.tool_spec(
            trigger_id="third", name="Third changed",
            cause="trigger_completion",
            condition={"source_trigger_id": "first"},
            action={"kind": "project_tool", "nexus": "fixture",
                    "tool": "run", "args": ["later-action"]},
        ))
        review = restarted.activation_review("third")
        restarted.activate("third", expected_spec_digest=review["spec_digest"])
        self.assertNotEqual(
            old_admission,
            triggers._admission_identity(restarted._require("third")),
        )
        self.assertEqual(restarted.replay_completion_deliveries(), [])
        self.assertEqual(restarted.firings("third"), [])
        self.assertEqual(len(restarted._pending_completion_deliveries()), 1)
        blocked = restarted.get("third")["pending_completions"]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["state"], "blocked_by_trigger_change")
        self.assertEqual(set(blocked[0]), {
            "source_trigger_id", "source_event_id", "source_completed_at",
            "created_at", "state",
        })
        listed = {
            view["spec"]["trigger_id"]: view
            for view in restarted.list_triggers()
        }
        self.assertEqual(listed["third"]["pending_completions"], blocked)

        import slash_commands
        with mock.patch.object(triggers, "_service", restarted):
            slash_list = slash_commands.run_runtime_command("/trigger list")
            slash_show = slash_commands.run_runtime_command("/trigger show third")
        for rendered in (slash_list, slash_show):
            self.assertIn("Pending completions", rendered)
            self.assertIn("earlier approved version", rendered)
            self.assertIn("did not run the current action", rendered)

    def test_a_direct_completion_cycle_is_refused(self):
        with self.assertRaises(triggers.TriggerConflict) as caught:
            self.service.create(self.tool_spec(
                trigger_id="loop", name="Loop", cause="trigger_completion",
                condition={"source_trigger_id": "loop"}))
        self.assertIn("cycle", str(caught.exception))

    def test_an_indirect_completion_cycle_is_refused(self):
        self.service.create(self.tool_spec(
            trigger_id="second", name="Second", cause="trigger_completion",
            condition={"source_trigger_id": "first"}))
        self.service.create(self.tool_spec(
            trigger_id="third", name="Third", cause="trigger_completion",
            condition={"source_trigger_id": "second"}))
        with self.assertRaises(triggers.TriggerConflict):
            self.service.update("first", self.tool_spec(
                trigger_id="first", name="First", cause="trigger_completion",
                condition={"source_trigger_id": "third"}))


# ── Firing mechanics ─────────────────────────────────────────────────────


class FiringTests(TriggerBase):
    def test_a_manual_firing_runs_the_tool_and_records_its_output(self):
        self.make_project(script_body='print(\'{"ok": true}\')')
        self.service.create(self.tool_spec())
        self.activate("nightly")
        self.service.run_manual("nightly", request_id="r1")
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["status"], "completed")
        self.assertEqual(firing["receipt"]["outcome"], "ran")
        self.assertIn("ok", firing["receipt"]["output_excerpt"])
        records = system_protection.verify_audit()
        self.assertEqual([record["event_type"] for record in records], [
            "protected_action_started", "protected_action_completed",
        ])
        authority = records[0]["request"]["standing_authority"]
        self.assertEqual(authority["kind"], "active_trigger")
        self.assertEqual(authority["trigger_id"], "nightly")
        self.assertEqual(records[1]["execution_id"], records[0]["execution_id"])
        self.assertEqual(tool_events._load_approvals()["standing"], [])

    def test_a_failing_tool_records_the_failure_and_is_not_retried(self):
        self.make_project(script_body="import sys; sys.exit(3)")
        self.service.create(self.tool_spec())
        self.activate("nightly")
        self.service.run_manual("nightly", request_id="r1")
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["status"], "failed")
        self.assertTrue(firing["error"])
        self.assertEqual(len(self.service.firings("nightly")), 1)

    def test_a_draft_trigger_may_be_run_once_before_deployment(self):
        self.make_project()
        self.service.create(self.tool_spec())
        with self.assertRaisesRegex(triggers.TriggerConflict, "queued for approval"):
            self.service.run_manual("nightly", request_id="dry-run")
        self.assertEqual(self.service.firings("nightly"), [])
        queued = [
            json.loads(line)
            for line in (self.root / "queue.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        self.assertEqual(len(queued), 1)
        self.assertIn("One-shot token", tool_events.resolve_gate_entry(
            queued[0], approve=True,
        ))
        self.service.run_manual("nightly", request_id="dry-run")
        self.assertEqual(self.service.firings("nightly")[0]["status"], "completed")
        self.assertEqual([record["event_type"] for record in
                          system_protection.verify_audit()], [
            "protected_action_started", "protected_action_completed",
        ])

    def test_a_retired_trigger_cannot_be_run(self):
        self.make_project()
        self.service.create(self.tool_spec())
        self.service.lifecycle("nightly", "retire")
        with self.assertRaises(triggers.TriggerConflict):
            self.service.run_manual("nightly", request_id="r1")

    def test_an_overlapping_firing_is_skipped_not_run_twice(self):
        self.make_project()
        self.service.create(self.tool_spec())
        self.activate("nightly")
        triggers._RUNNING["nightly"] = "evt-earlier"
        try:
            self.service.run_manual("nightly", request_id="r2")
        finally:
            triggers._RUNNING.pop("nightly", None)
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["receipt"]["outcome"], "skipped")
        self.assertEqual(firing["receipt"]["blocking_event_id"], "evt-earlier")

    def test_an_interrupted_firing_is_terminal_after_restart(self):
        self.make_project()
        self.service.create(self.tool_spec())
        self.activate("nightly")
        # A firing claimed but never finished — what a shutdown leaves behind.
        with mock.patch.object(triggers.TriggerService, "_execute",
                               lambda *args, **kwargs: None):
            self.service.run_manual("nightly", request_id="interrupted")
        in_flight = self.service.firings("nightly")[0]
        self.assertEqual(in_flight["status"], "claimed")
        # The ledger's word is evidence; the panel's word is for a reader.
        self.assertEqual(in_flight["outcome"], "running")
        hygiene.restore_incomplete_events(self.service.ledger)
        firing = self.service.firings("nightly")[0]
        self.assertEqual(firing["status"], "failed")
        self.assertIn("restart recovery", firing["error"])

    @unittest.skipUnless(os.name == "posix", "process-group assertion is POSIX-only")
    def test_timeout_terminates_work_before_the_next_firing(self):
        acknowledged = self.root / "termination-acknowledged"
        descendant_pid = self.root / "descendant.pid"
        descendant_survived = self.root / "descendant-survived"
        descendant_code = (
            "import os, signal, time\n"
            "from pathlib import Path\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"Path({str(descendant_pid)!r}).write_text("
            "str(os.getpid()) + ' ' + str(os.getpgid(0)))\n"
            "time.sleep(2)\n"
            f"Path({str(descendant_survived)!r}).write_text('survived')\n"
            "while True:\n"
            "    time.sleep(1)\n"
        )
        _project, script = self.make_project(script_body=(
            "import signal, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "subprocess.Popen(\n"
            f"    [sys.executable, '-c', {descendant_code!r}],\n"
            "    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,\n"
            "    stderr=subprocess.DEVNULL, close_fds=True,\n"
            ")\n"
            "def stop(*_):\n"
            f"    Path({str(acknowledged)!r}).write_text('stopped')\n"
            "    raise SystemExit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "while True:\n"
            "    time.sleep(0.05)\n"
        ))

        def stop_descendant_if_needed():
            try:
                pid, process_group = (
                    int(value) for value in descendant_pid.read_text(
                        encoding="utf-8",
                    ).split()
                )
                if os.getpgid(pid) == process_group:
                    os.kill(pid, signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError, ValueError):
                pass

        self.addCleanup(stop_descendant_if_needed)
        service = triggers.TriggerService(
            queue=self.queue, ledger=self.service.ledger, executor=_inline,
            firing_timeout_sec=1.0, terminate_actions=True,
        )
        service.create(self.tool_spec())
        review = service.activation_review("nightly")
        service.activate("nightly", expected_spec_digest=review["spec_digest"])

        with mock.patch.dict(os.environ, {"ORA_HOME": str(self.root)}):
            service.run_manual("nightly", request_id="times-out")
            timed_out = service.firings("nightly")[0]
            self.assertEqual(timed_out["status"], "failed")
            self.assertIn("deadline", timed_out["error"])
            self.assertTrue(acknowledged.is_file())
            self.assertNotIn("nightly", triggers._RUNNING)
            child_pid, child_group = (
                int(value) for value in descendant_pid.read_text(
                    encoding="utf-8",
                ).split()
            )
            self.assertNotEqual(child_pid, child_group)
            group_deadline = time.monotonic() + 2
            group_exists = True
            while group_exists and time.monotonic() < group_deadline:
                try:
                    os.killpg(child_group, 0)
                except ProcessLookupError:
                    group_exists = False
                if group_exists:
                    time.sleep(0.02)
            self.assertFalse(group_exists, "timed-out process group survived")
            self.assertFalse(descendant_survived.exists())

            script.write_text('print(\'{"ok": true}\')', encoding="utf-8")
            service.lifecycle("nightly", "pause")
            service.update("nightly", self.tool_spec())
            review = service.activation_review("nightly")
            service.activate("nightly", expected_spec_digest=review["spec_digest"])
            service.run_manual("nightly", request_id="after-timeout")
        latest = service.firings("nightly")[0]
        self.assertEqual(latest["status"], "completed")
        self.assertNotEqual(latest["receipt"]["outcome"], "skipped")

        # The same boundary is the provider write-ahead barrier: the action
        # cannot cross into provider work until the parent's durable callback
        # has succeeded and acknowledged it.
        provider_effect = self.root / "provider-effect"
        durable_contact = self.root / "durable-provider-contact"
        fork_context = triggers.multiprocessing.get_context("fork")

        def contact_then_effect(*_args, on_provider_contact=None, **_kwargs):
            on_provider_contact()
            if not durable_contact.is_file():
                raise AssertionError("provider contact was not durable")
            provider_effect.write_text("contacted", encoding="utf-8")
            return {"outcome": "ran"}

        with (
            mock.patch.object(
                triggers.multiprocessing, "get_context",
                return_value=fork_context,
            ),
            mock.patch.object(
                triggers, "_execute_action", side_effect=contact_then_effect,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "ledger unavailable"):
                triggers._execute_action_with_deadline(
                    {"kind": "email_send"}, {}, prepared=None,
                    on_provider_contact=lambda: (_ for _ in ()).throw(
                        RuntimeError("ledger unavailable")
                    ),
                    timeout_sec=2,
                )
            self.assertFalse(provider_effect.exists())

            def persist_provider_contact():
                durable_contact.write_text("durable", encoding="utf-8")

            receipt = triggers._execute_action_with_deadline(
                {"kind": "email_send"}, {}, prepared=None,
                on_provider_contact=persist_provider_contact,
                timeout_sec=2,
            )
        self.assertEqual(receipt["outcome"], "ran")
        self.assertEqual(provider_effect.read_text(encoding="utf-8"), "contacted")

        # Windows termination is not acknowledged by merely invoking
        # taskkill: its status and every captured descendant must be checked.
        fake_process = SimpleNamespace(
            pid=4242, join=mock.Mock(), is_alive=lambda: False,
        )
        with (
            mock.patch.object(
                triggers, "_uses_posix_process_groups", return_value=False,
            ),
            mock.patch.object(
                triggers, "_windows_process_tree", return_value={4242, 4243},
            ),
            mock.patch.object(
                triggers.subprocess, "run",
                return_value=SimpleNamespace(returncode=1),
            ),
        ):
            with self.assertRaisesRegex(
                triggers.TriggerTerminationUnacknowledged, "failure status",
            ):
                triggers._terminate_action_process(fake_process)
        with (
            mock.patch.object(
                triggers, "_uses_posix_process_groups", return_value=False,
            ),
            mock.patch.object(
                triggers, "_windows_process_tree", return_value={4242, 4243},
            ),
            mock.patch.object(
                triggers.subprocess, "run",
                return_value=SimpleNamespace(returncode=0),
            ),
            mock.patch.object(
                triggers, "_windows_live_processes", return_value={4243},
            ),
        ):
            with self.assertRaisesRegex(
                triggers.TriggerTerminationUnacknowledged,
                "did not acknowledge",
            ):
                triggers._terminate_action_process(fake_process)

        # If termination cannot be proved, the overlap claim stays in place.
        # A later firing is skipped instead of starting beside possibly-live
        # timed-out work.
        with mock.patch.object(
            triggers, "_execute_action_with_deadline",
            side_effect=triggers.TriggerTerminationUnacknowledged(
                "injected live process tree",
            ),
        ):
            stuck = service.run_manual("nightly", request_id="unacknowledged")
        self.assertEqual(triggers._RUNNING["nightly"], stuck["event_id"])
        blocked = service.run_manual("nightly", request_id="blocked-by-stuck")
        blocked_record = next(
            row for row in service.firings("nightly")
            if row["event_id"] == blocked["event_id"]
        )
        self.assertEqual(blocked_record["receipt"]["outcome"], "skipped")
        self.assertEqual(
            blocked_record["receipt"]["blocking_event_id"], stuck["event_id"],
        )

    @unittest.skipUnless(os.name == "posix", "process assertion is POSIX-only")
    def test_parent_callback_error_reaps_work_before_next_firing(self):
        self.make_project(script_body='print(\'{"ok": true}\')')
        service = triggers.TriggerService(
            queue=self.queue, ledger=self.service.ledger, executor=_inline,
            firing_timeout_sec=30.0, terminate_actions=True,
        )
        service.create(self.tool_spec())
        review = service.activation_review("nightly")
        service.activate("nightly", expected_spec_digest=review["spec_digest"])
        child_pid = self.root / "parent-callback-child.pid"
        fork_context = triggers.multiprocessing.get_context("fork")

        def contact_then_wait(*_args, on_provider_contact=None, **_kwargs):
            child_pid.write_text(str(os.getpid()), encoding="utf-8")
            on_provider_contact()
            while True:
                threading.Event().wait(60)

        ledger = service.ledger
        real_transition = ledger.transition

        def fail_parent_callback(event_id, expected, status, **fields):
            if fields.get("provider_contacted"):
                raise RuntimeError("injected parent callback failure")
            return real_transition(event_id, expected, status, **fields)

        with (
            mock.patch.object(
                triggers.multiprocessing, "get_context",
                return_value=fork_context,
            ),
            mock.patch.object(
                triggers, "_execute_action", side_effect=contact_then_wait,
            ),
            mock.patch.object(
                ledger, "transition", side_effect=fail_parent_callback,
            ),
            mock.patch.object(triggers, "TERMINATION_GRACE_SEC", 0.1),
        ):
            service.run_manual("nightly", request_id="callback-error")

        pid = int(child_pid.read_text(encoding="utf-8"))
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertNotIn("nightly", triggers._RUNNING)
        self.assertEqual(service.firings("nightly")[0]["status"], "failed")

        with mock.patch.dict(os.environ, {"ORA_HOME": str(self.root)}):
            service.run_manual("nightly", request_id="after-callback-error")
        latest = service.firings("nightly")[0]
        self.assertEqual(latest["status"], "completed")
        self.assertNotEqual(latest["receipt"]["outcome"], "skipped")


# ── Action resolution ────────────────────────────────────────────────────


class ActionTests(TriggerBase):
    def test_framework_trigger_runs_the_terminal_visual_authority(self):
        result = SimpleNamespace(success=True, final_output="A depends on B.",
                                 execution_id="exec-1", milestones=[])
        action = {"kind": "framework", "input": "Map the dependency",
                  "project_nexus": "fixture"}
        binding = {"framework": "f-analysis", "trigger_id": "nightly"}
        def visual_hook(response, context):
            context["_visual_outcome"] = {
                "state": "failed",
                "stage": "cli_render",
                "reason": "headless render failed",
            }
            return "visual result"

        with mock.patch.object(triggers, "_excerpt", return_value="visual excerpt") as excerpt, \
             mock.patch("milestone_executor.execute_framework", return_value=result) as execute_framework, \
             mock.patch("boot._run_visual_hook", side_effect=visual_hook) as hook, \
             mock.patch("pipeline_trace.start_trace", return_value="/trace/evt-1") as start_trace, \
             mock.patch("pipeline_trace.finalize_manifest") as finalize_manifest, \
             mock.patch("boot.load_routing_config", return_value={}):
            receipt = triggers._execute_action(action, binding)
        start_trace.assert_called_once_with(
            "nightly", raw_input="Map the dependency", conversation_tag="trigger")
        execute_framework.assert_called_once_with(
            "f-analysis", "Map the dependency", {}, project_nexus="fixture",
            trace_dir="/trace/evt-1", conversation_tag="trigger")
        finalize_manifest.assert_called_once_with(
            "/trace/evt-1", kind="trigger-framework", status_hint="error",
            framework_id="f-analysis")
        hook.assert_called_once_with(
            "A depends on B.",
            {
                "cleaned_prompt": "Map the dependency",
                "execution_context": "autonomous",
                "framework_id": "f-analysis",
                "project_nexus": "fixture",
                "trace_dir": "/trace/evt-1",
                "_visual_outcome": {
                    "state": "failed",
                    "stage": "cli_render",
                    "reason": "headless render failed",
                },
            },
        )
        excerpt.assert_called_once_with("visual result")
        self.assertEqual(receipt["outcome"], "ran")
        self.assertEqual(receipt["output_excerpt"], "visual excerpt")
        self.assertEqual(receipt["visual_outcome"]["state"], "failed")

    def test_an_unregistered_project_is_refused_at_authoring_time(self):
        with self.assertRaises(triggers.TriggerConflict) as caught:
            self.service.create(self.tool_spec())
        self.assertIn("no project registered", str(caught.exception))

    def test_a_missing_tool_is_refused_with_the_available_names(self):
        self.make_project()
        with self.assertRaises(triggers.TriggerConflict) as caught:
            self.service.create(self.tool_spec(
                action={"kind": "project_tool", "nexus": "fixture",
                        "tool": "absent", "args": []}))
        self.assertIn("run", str(caught.exception))

    def test_an_internal_pipeline_stage_is_not_a_runnable_framework(self):
        with self.assertRaises(triggers.TriggerConflict):
            self.service.create(self.tool_spec(
                action={"kind": "framework", "framework": "f-analysis",
                        "input": "anything"}))

    def test_the_activation_review_names_what_will_actually_run(self):
        _project_root, script = self.make_project(interface="stdin-stdout-json")
        omitted_spec = self.tool_spec(action={
            "kind": "project_tool", "nexus": "fixture", "tool": "run",
            "args": [],
        })
        self.service.create(omitted_spec)
        omitted = self.service.activation_review("nightly")
        self.assertIn("stdin={}", omitted["will_run"])

        first_spec = self.tool_spec(action={
            "kind": "project_tool", "nexus": "fixture", "tool": "run",
            "args": [], "stdin": {"headline": "First input"},
        })
        self.service.update("nightly", first_spec)
        first = self.service.activation_review("nightly")
        self.assertIn("fixture:run", first["will_run"])
        self.assertIn('stdin={"headline":"First input"}', first["will_run"])
        for key in (
            "manifest_sha256", "command_digest", "executable_identity",
            "script_identity", "args_digest", "interface", "nexus",
            "project_root",
        ):
            self.assertTrue(first["action_binding"][key])
        self.assertEqual(
            first["action_binding"]["project_root"],
            str(_project_root.resolve()),
        )
        self.assertIn(
            f"project:fixture/root:{_project_root.resolve()}",
            first["action_binding"]["selectors"],
        )
        self.assertFalse(any(
            key.startswith("_") for key in first["action_binding"]
        ))

        second_spec = self.tool_spec(action={
            "kind": "project_tool", "nexus": "fixture", "tool": "run",
            "args": [], "stdin": {"headline": "Second input"},
        })
        self.service.update("nightly", second_spec)
        second = self.service.activation_review("nightly")
        self.assertIn('stdin={"headline":"Second input"}', second["will_run"])
        self.assertNotEqual(first["spec_digest"], second["spec_digest"])
        self.assertNotEqual(first["action_binding"]["args_digest"],
                            second["action_binding"]["args_digest"])

        script.write_text("print('{\"changed\": true}')", encoding="utf-8")
        with self.assertRaisesRegex(
                triggers.TriggerConflict, "bound action changed"):
            self.service.activate(
                "nightly", expected_spec_digest=second["spec_digest"])

        import slash_commands
        email_service = mock.Mock()
        email_service.activation_review.return_value = {
            "trigger_id": "email-review",
            "name": "Exact email",
            "spec_digest": "sha256:email-review",
            "cause": "manual",
            "condition": {},
            "will_run": "email via Fastmail with exact action",
            "action_binding": {
                "message_digest": "sha256:message",
                "mime_digest": "sha256:mime",
            },
            "runtime_justification": None,
            "intermittency": "",
        }
        with mock.patch.object(triggers, "_service", email_service):
            email_review = slash_commands.run_runtime_command(
                "/trigger activate email-review")
        self.assertIn("sha256:message", email_review)


# ── Inspection ───────────────────────────────────────────────────────────


class InspectionTests(TriggerBase):
    def test_internal_deadlines_are_counted_not_listed(self):
        self.make_project()
        due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        for index in range(5):
            self.queue.put(f"trace-retention:{index}", due, "trace_retention", {})
        summary = self.service.internal_deadline_summary()
        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["by_event_type"], {"trace_retention": 5})

    def test_a_triggers_own_deadline_is_not_counted_as_internal(self):
        self.make_project()
        self.service.create(self.tool_spec(
            cause="calendar", condition=self.calendar_condition(),
            runtime_justification=(
                "The provider expires credentials on its own clock and offers "
                "no callback, so time is genuinely the cause.")))
        self.activate("nightly")
        self.assertEqual(self.service.internal_deadline_summary()["total"], 0)

    def test_the_listing_carries_each_triggers_own_last_firing(self):
        """The card's "last …" badge must belong to that card's Trigger."""
        self.make_project()
        for trigger_id in ("alpha", "beta"):
            self.service.create(self.tool_spec(
                trigger_id=trigger_id, name=trigger_id.title()))
            self.activate(trigger_id)
        self.service.run_manual("alpha", request_id="only-alpha")

        by_id = {view["spec"]["trigger_id"]: view
                 for view in self.service.list_triggers()}
        self.assertEqual(len(by_id["alpha"]["firings"]), 1)
        self.assertEqual(by_id["alpha"]["firings"][0]["trigger_id"], "alpha")
        self.assertEqual(by_id["beta"]["firings"], [])

    def test_retired_triggers_leave_the_default_listing(self):
        self.make_project()
        self.service.create(self.tool_spec())
        self.service.lifecycle("nightly", "retire")
        self.assertEqual(self.service.list_triggers(), [])
        self.assertEqual(len(self.service.list_triggers(include_retired=True)), 1)

    def test_available_actions_reports_the_watch_roots_it_validates_against(self):
        self.make_project()
        actions = triggers.available_actions()
        self.assertEqual(actions["watch_roots"], [str(self.watched.resolve())])
        self.assertIn("only while Ora is running", actions["intermittency"])


# ── Automation Studio's truthful local-only foundation ─────────────────


class AutomationStudioLocalContractTests(TriggerBase):
    """Existing Trigger routes expose only capabilities the local runner has."""

    def setUp(self):
        super().setUp()
        from server import app as server_app  # noqa: WPS433
        self.client = server_app.app.test_client()
        patcher = mock.patch.object(triggers, "_service", self.service)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.make_project()

    def test_actions_route_exposes_local_authority_and_debug_facts(self):
        payload = self.client.get("/api/triggers/actions").get_json()
        routine = payload["routine"]
        self.assertEqual(routine["execution_target"], "local")
        self.assertFalse(routine["remote_execution_supported"])
        self.assertFalse(routine["wake_from_sleep_supported"])
        self.assertEqual(
            routine["authority"], {"binding": "exact_action_binding"})
        self.assertEqual(routine["debug"], {
            "firing_event_type": triggers.FIRING_EVENT_TYPE,
            "receipt_available": True,
            "error_available": True,
        })
        sleep = routine["active_run_sleep_protection"]
        self.assertEqual(
            sleep["available"], triggers._active_run_sleep_available())
        if sleep["available"]:
            self.assertEqual(sleep["scope"], "active_action_only")
            self.assertEqual(sleep["prevents"], "idle_system_sleep")
            self.assertEqual(sleep["release_boundary"], "action_scope_exit")
        else:
            self.assertIsNone(sleep["scope"])
            self.assertIsNone(sleep["prevents"])
            self.assertIsNone(sleep["release_boundary"])

    def test_existing_trigger_views_carry_the_action_specific_contract(self):
        created = self.client.post(
            "/api/triggers", json=self.tool_spec()).get_json()
        shown = self.client.get("/api/triggers/nightly").get_json()
        review = self.client.get(
            "/api/triggers/nightly/review").get_json()
        listed = self.client.get(
            "/api/triggers").get_json()["triggers"][0]

        expected_authority = {
            "binding": "exact_action_binding",
            "action_kind": "project_tool",
        }
        for view in (created, shown, review, listed):
            self.assertEqual(view["routine"]["execution_target"], "local")
            self.assertEqual(view["routine"]["authority"], expected_authority)
            self.assertFalse(view["routine"]["remote_execution_supported"])
            self.assertFalse(view["routine"]["wake_from_sleep_supported"])


# ── Active action work, and only active action work, holds idle sleep ────


class ActiveRunSleepProtectionTests(TriggerBase):
    class _Guard:
        def __init__(self, events):
            self.events = events
            self.alive = True

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.events.append(("guard", "terminate"))
            self.alive = False

        def kill(self):
            self.events.append(("guard", "kill"))
            self.alive = False

        def wait(self, timeout=None):
            self.events.append(("guard", "wait"))
            return 0

    class _Connection:
        def __init__(self, events, *, fail_provider_callback=False):
            self.events = events
            self.fail_provider_callback = fail_provider_callback
            self.messages = []

        def send(self, message):
            self.events.append(("connection", message[0]))
            if self.fail_provider_callback and message[0] == "provider_contact":
                raise RuntimeError("injected provider callback failure")
            self.messages.append(message)

        def close(self):
            self.events.append(("connection", "close"))

    def _exercise_action_process(self, outcome):
        events = []
        guard = self._Guard(events)
        connection = self._Connection(
            events, fail_provider_callback=(outcome == "provider_callback"))
        launch = {}

        def popen(argv, **kwargs):
            launch["argv"] = argv
            launch["kwargs"] = kwargs
            events.append(("guard", "start"))
            return guard

        def execute(*_args, on_provider_contact=None, **_kwargs):
            self.assertTrue(guard.alive)
            events.append(("action", "work"))
            if outcome == "ordinary_error":
                raise RuntimeError("injected action failure")
            if outcome == "provider_callback":
                on_provider_contact()
            if outcome == "cancellation":
                raise KeyboardInterrupt("injected cancellation")
            return {"outcome": "ran"}

        with (
            mock.patch.object(triggers.sys, "platform", "darwin"),
            mock.patch.object(
                triggers, "_active_run_sleep_available", return_value=True),
            mock.patch.object(
                triggers.subprocess, "Popen", side_effect=popen),
            mock.patch.object(triggers.os, "setsid"),
            mock.patch.object(triggers, "_execute_action", side_effect=execute),
        ):
            triggers._action_process_main(
                connection, {"kind": "framework"}, {})
        return events, guard, connection, launch

    def test_success_holds_sleep_only_around_real_action_work(self):
        events, guard, connection, launch = self._exercise_action_process(
            "success")
        self.assertFalse(guard.alive)
        self.assertEqual(launch["argv"], [
            triggers._MACOS_CAFFEINATE, "-i", "-w", str(os.getpid()),
        ])
        self.assertLess(
            events.index(("guard", "start")),
            events.index(("action", "work")),
        )
        self.assertLess(
            events.index(("action", "work")),
            events.index(("guard", "terminate")),
        )
        self.assertLess(
            events.index(("guard", "wait")),
            events.index(("connection", "result")),
        )
        self.assertEqual(connection.messages, [("result", {"outcome": "ran"})])

    def test_error_callback_and_cancellation_release_before_reporting(self):
        for outcome in ("ordinary_error", "provider_callback", "cancellation"):
            with self.subTest(outcome=outcome):
                events, guard, connection, _launch = (
                    self._exercise_action_process(outcome))
                self.assertFalse(guard.alive)
                self.assertLess(
                    events.index(("guard", "wait")),
                    events.index(("connection", "error")),
                )
                self.assertEqual(connection.messages[-1][0], "error")

    def test_macos_guard_failure_prevents_unprotected_action_work(self):
        for unavailable, launch_error in ((True, None), (False, OSError("no exec"))):
            with self.subTest(unavailable=unavailable):
                events = []
                connection = self._Connection(events)
                execute = mock.Mock(return_value={"outcome": "ran"})
                with (
                    mock.patch.object(triggers.sys, "platform", "darwin"),
                    mock.patch.object(
                        triggers, "_active_run_sleep_available",
                        return_value=not unavailable,
                    ),
                    mock.patch.object(
                        triggers.subprocess, "Popen", side_effect=launch_error,
                    ),
                    mock.patch.object(triggers.os, "setsid"),
                    mock.patch.object(triggers, "_execute_action", execute),
                ):
                    triggers._action_process_main(
                        connection, {"kind": "framework"}, {})
                execute.assert_not_called()
                self.assertEqual(connection.messages[-1][0], "error")
                self.assertIn("sleep protection", connection.messages[-1][1])

    def test_non_macos_does_not_claim_or_start_macos_protection(self):
        with (
            mock.patch.object(triggers.sys, "platform", "linux"),
            mock.patch.object(triggers.subprocess, "Popen") as popen,
        ):
            with triggers._active_run_sleep_protection():
                pass
            routine = triggers._local_routine_descriptor("project_tool")
        popen.assert_not_called()
        self.assertFalse(routine["active_run_sleep_protection"]["available"])
        self.assertFalse(routine["wake_from_sleep_supported"])


# ── Substrate additions ──────────────────────────────────────────────────


class SlashCommandTests(TriggerBase):
    """The keyboard path carries the same guarantees as the panel."""

    JUSTIFICATION = (
        "The upstream feed publishes on its own clock and offers no change "
        "callback, so passage of time is the actual cause.")

    def setUp(self):
        super().setUp()
        import slash_commands
        self.sc = slash_commands
        patcher = mock.patch.object(triggers, "_service", self.service)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.make_project()

    def run_cmd(self, line):
        return self.sc.run_runtime_command(line)

    def test_trigger_is_a_recognized_runtime_command(self):
        self.assertTrue(self.sc.is_runtime_command("/trigger list"))
        self.assertTrue(self.sc.is_runtime_command("/triggers list"))

    def test_create_activate_and_run_from_chat(self):
        created = self.run_cmd(
            '/trigger create --id nightly --name "Nightly" '
            '--tool fixture:run --manual')
        self.assertIn("Created draft Trigger", created)

        review = self.run_cmd("/trigger activate nightly")
        self.assertIn("Approve exactly this specification", review)
        digest = self.service.activation_review("nightly")["spec_digest"]
        self.assertIn(digest, review)

        activated = self.run_cmd(f"/trigger activate nightly --approve {digest}")
        self.assertIn("Activated", activated)
        self.assertEqual(self.service.get("nightly")["status"], "active")

        self.run_cmd("/trigger run nightly")
        self.assertEqual(self.service.firings("nightly")[0]["status"], "completed")

    def test_activation_without_the_digest_only_shows_the_review(self):
        self.run_cmd('/trigger create --id nightly --name "Nightly" '
                     '--tool fixture:run --manual')
        self.run_cmd("/trigger activate nightly")
        self.assertEqual(self.service.get("nightly")["status"], "draft")

    def test_a_daily_trigger_without_a_reason_is_refused_in_chat(self):
        out = self.run_cmd('/trigger create --id nightly --name "Nightly" '
                           '--tool fixture:run --daily 07:30 '
                           '--tz America/New_York')
        self.assertIn("runtime-impossibility", out)
        self.assertEqual(self.service.list_triggers(), [])

    def test_a_weekly_trigger_parses_its_weekdays(self):
        out = self.run_cmd(
            '/trigger create --id weekly --name "Weekly" --tool fixture:run '
            '--weekly "mon,thu 07:30" --tz America/New_York '
            f'--because "{self.JUSTIFICATION}"')
        self.assertIn("Created draft Trigger", out)
        schedule = self.service.get("weekly")["spec"]["condition"]["schedule"]
        self.assertEqual(schedule["cadence"], "weekly")
        self.assertEqual(schedule["weekdays"], [0, 3])

    def test_list_reports_internal_deadlines_without_listing_them(self):
        self.run_cmd('/trigger create --id nightly --name "Nightly" '
                     '--tool fixture:run --manual')
        due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        for index in range(3):
            self.queue.put(f"trace-retention:{index}", due, "trace_retention", {})
        out = self.run_cmd("/trigger list")
        self.assertIn("Nightly", out)
        self.assertIn("3 internal maintenance deadlines", out)
        self.assertNotIn("trace-retention:0", out)

    def test_show_surfaces_the_written_reason_and_the_boundary(self):
        self.run_cmd('/trigger create --id nightly --name "Nightly" '
                     '--tool fixture:run --daily 07:30 --tz America/New_York '
                     f'--because "{self.JUSTIFICATION}"')
        out = self.run_cmd("/trigger show nightly")
        self.assertIn("Why time is the cause", out)
        self.assertIn("only while Ora is running", out)

    def test_a_refused_trigger_reports_why_rather_than_raising(self):
        out = self.run_cmd('/trigger create --id ghost --name "Ghost" '
                           '--tool fixture:absent --manual')
        self.assertIn("has no tool", out)

    def test_help_states_that_a_command_string_is_not_an_action(self):
        out = self.run_cmd("/trigger help")
        self.assertIn("ora-project.json", out)
        self.assertIn("carries a command string", out)


class EndpointTests(TriggerBase):
    """The panel's routes carry the refusals, not just the happy path."""

    def setUp(self):
        super().setUp()
        # Package-qualified, like every other endpoint suite: importing the
        # server as a top-level ``app`` would put server/ on sys.path for the
        # whole run and shadow same-named orchestrator modules.
        from server import app as server_app  # noqa: WPS433
        self.app = server_app.app
        self.client = self.app.test_client()
        patcher = mock.patch.object(triggers, "_service", self.service)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.make_project()

    def test_list_carries_lane_health_and_the_internal_count(self):
        due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        self.queue.put("trace-retention:1", due, "trace_retention", {})
        payload = self.client.get("/api/triggers").get_json()
        self.assertEqual(payload["internal_deadlines"]["total"], 1)
        self.assertIn("lane_health", payload)

    def test_creating_and_activating_through_the_api(self):
        created = self.client.post("/api/triggers", json=self.tool_spec())
        self.assertEqual(created.status_code, 201)
        firing_digest = created.get_json()["spec_digest"]

        review = self.client.get("/api/triggers/nightly/review").get_json()
        self.assertEqual(review["firing_spec_digest"], firing_digest)
        self.assertIn("fixture:run", review["will_run"])

        activated = self.client.post(
            "/api/triggers/nightly/activate",
            json={"spec_digest": review["spec_digest"]},
        )
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(activated.get_json()["status"], "active")

    def test_activation_without_a_digest_is_refused(self):
        self.client.post("/api/triggers", json=self.tool_spec())
        response = self.client.post("/api/triggers/nightly/activate", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("spec_digest", response.get_json()["error"])
        self.assertEqual(self.service.get("nightly")["status"], "draft")

    def test_activation_with_a_stale_digest_is_refused(self):
        self.client.post("/api/triggers", json=self.tool_spec())
        response = self.client.post(
            "/api/triggers/nightly/activate", json={"spec_digest": "sha256:old"})
        self.assertEqual(response.status_code, 409)

    def test_a_calendar_trigger_without_a_reason_is_a_400(self):
        response = self.client.post("/api/triggers", json=self.tool_spec(
            cause="calendar", condition=self.calendar_condition()))
        self.assertEqual(response.status_code, 400)
        self.assertIn("runtime-impossibility", response.get_json()["error"])

    def test_actions_route_lists_what_a_trigger_may_point_at(self):
        payload = self.client.get("/api/triggers/actions").get_json()
        self.assertIn("project_tools", payload)
        self.assertIn("watch_roots", payload)

    def test_manual_run_is_accepted_and_recorded(self):
        self.client.post("/api/triggers", json=self.tool_spec())
        response = self.client.post("/api/triggers/nightly/run", json={})
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.get_json()["event_id"])

    def test_an_unknown_trigger_is_a_conflict_not_a_crash(self):
        response = self.client.get("/api/triggers/absent")
        self.assertEqual(response.status_code, 409)


class SubstrateTests(TriggerBase):
    def test_list_events_filters_by_type(self):
        ledger = self.service.ledger
        ledger.claim(event_id="evt-a", event_type="trigger_firing",
                     subject={"n": 1})
        ledger.claim(event_id="evt-b", event_type="other", subject={"n": 2})
        rows = ledger.list_events(event_type="trigger_firing")
        self.assertEqual([row["event_id"] for row in rows], ["evt-a"])

    def test_pending_counts_ignores_finished_records(self):
        due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.queue.put("a", due, "trace_retention", {})
        self.queue.put("b", due, "trace_retention", {})
        self.queue.cancel("b", reason="test")
        self.assertEqual(self.queue.pending_counts(), {"trace_retention": 1})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
