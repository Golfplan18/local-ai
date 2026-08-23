"""Tests for oversight_daemon — live event/deadline lanes and manual sweeps.

Covers the live runtime's startup, persisted deadlines, watchdog recovery,
and the manual maintenance surface. Retired interval lanes are intentionally
not represented here.

Run::

    /opt/homebrew/bin/python3 -m pytest orchestrator/tests/test_oversight_daemon.py -q
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import oversight_daemon as od  # noqa: E402
from orchestrator import runtime_hygiene  # noqa: E402


class RuntimePathTests(unittest.TestCase):
    def test_default_vault_path_delegates_to_shared_resolver(self):
        target = Path("/tmp/redirected-oversight-vault")
        with mock.patch.object(od._rp, "vault_dir", return_value=target):
            self.assertEqual(od._vault_path(), str(target))

    def test_scan_pruning_is_separator_independent(self):
        dirs = ["Archive", ".obsidian", "Sessions", "Projects", "Notes"]
        od._prune_scan_dirs(dirs)
        self.assertEqual(dirs, ["Projects", "Notes"])

    def test_runtime_health_reads_actual_blocking_lanes(self):
        daemon = od.OversightDaemon()
        alive = mock.MagicMock()
        alive.is_alive.return_value = True
        daemon._running = True
        daemon._event_thread = alive
        daemon._deadline_thread = alive
        with mock.patch.object(od, "_daemon", daemon):
            health = od.runtime_health()
        self.assertEqual(
            {k: health[k] for k in ("running", "event_lane", "deadline_lane")},
            {"running": True, "event_lane": True, "deadline_lane": True},
        )
        # Liveness alone cannot distinguish a healthy lane from one the
        # watchdog keeps resurrecting, so the contract also carries restart
        # counts. A never-restarted daemon reports them empty.
        self.assertEqual(health["lane_restarts"], {})
        self.assertEqual(health["lane_restart_at"], {})

    def test_runtime_health_reports_watchdog_restart_counts(self):
        daemon = od.OversightDaemon()
        alive = mock.MagicMock()
        alive.is_alive.return_value = True
        daemon._running = True
        daemon._event_thread = alive
        daemon._deadline_thread = alive
        daemon._record_restart("event_lane")
        daemon._record_restart("event_lane")
        with mock.patch.object(od, "_daemon", daemon):
            health = od.runtime_health()
        # Alive AND repeatedly restarted — the crash-loop shape that went
        # unreported for 2,257 event-lane deaths before 2026-08-16.
        self.assertTrue(health["event_lane"])
        self.assertEqual(health["lane_restarts"]["event_lane"], 2)
        self.assertIn("event_lane", health["lane_restart_at"])

    def test_runtime_health_when_stopped_carries_empty_restart_maps(self):
        with mock.patch.object(od, "_daemon", None):
            health = od.runtime_health()
        self.assertFalse(health["running"])
        self.assertEqual(health["lane_restarts"], {})
        self.assertEqual(health["lane_restart_at"], {})

    def test_startup_recovers_exact_retention_intents_before_lanes_start(self):
        daemon = od.OversightDaemon()
        queue = mock.MagicMock()
        thread = mock.MagicMock()
        with (
            mock.patch.dict(
                "sys.modules", {"oversight_router": mock.MagicMock()},
            ),
            mock.patch.object(runtime_hygiene, "deadline_queue", return_value=queue),
            mock.patch.object(
                runtime_hygiene, "recover_retention_intents",
                return_value={"registered": ["intent-a"], "failed": []},
            ) as recover,
            mock.patch.object(daemon, "_ensure_daily_note_deadline") as daily,
            mock.patch.object(od.threading, "Thread", return_value=thread),
        ):
            daemon.start()
        recover.assert_called_once_with(queue=queue)
        daily.assert_called_once_with()
        self.assertEqual(thread.start.call_count, 4)

    def test_run_once_keeps_manual_maintenance_paths(self):
        daemon = od.OversightDaemon()
        with mock.patch("oversight_events.emit"), mock.patch.multiple(
            daemon,
            _run_ped_watcher=mock.DEFAULT,
            _run_corpus_watcher=mock.DEFAULT,
            _run_workflow_spec_sweeper=mock.DEFAULT,
            _run_revisit_sweeper=mock.DEFAULT,
            _run_retention_sweeper=mock.DEFAULT,
            _run_maintenance_scheduler=mock.DEFAULT,
            _run_resources_watcher=mock.DEFAULT,
        ) as runners:
            daemon.run_once()
        self.assertTrue(all(r.call_count == 1 for r in runners.values()))

    def test_daily_deadline_uses_persisted_day_and_chains_missed_day(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        completed = mock.MagicMock(success=True, message="wrote exact day")
        with mock.patch(
            "orchestrator.tools.daily_note.task_daily_note",
            return_value=completed,
        ) as task:
            receipt = daemon._handle_daily_note_deadline({
                "completed_date": "2026-07-19",
                "timezone": "America/Los_Angeles",
            })
        task.assert_called_once_with(date_str="2026-07-19")
        self.assertEqual(receipt["completed_date"], "2026-07-19")
        args = daemon._deadline_queue.put.call_args.args
        self.assertTrue(args[0].startswith("daily-note-v2:2026-07-20:"))
        self.assertEqual(args[2], "daily_note")
        self.assertEqual(args[3], {
            "completed_date": "2026-07-20",
            "timezone": "America/Los_Angeles",
        })

    def test_failed_daily_deadline_still_chains_distinct_next_day(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        failed = mock.MagicMock(success=False, message="bounded failure")
        with mock.patch(
            "orchestrator.tools.daily_note.task_daily_note", return_value=failed,
        ), self.assertRaisesRegex(RuntimeError, "bounded failure"):
            daemon._handle_daily_note_deadline({
                "completed_date": "2026-07-19",
                "timezone": "America/Los_Angeles",
            })
        self.assertTrue(
            daemon._deadline_queue.put.call_args.args[0].startswith(
                "daily-note-v2:2026-07-20:"
            )
        )

    def test_legacy_daily_deadline_resolves_named_zone_before_chaining(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        completed = mock.MagicMock(success=True, message="legacy completed")
        with (
            mock.patch.object(
                od, "_local_timezone_name", return_value="America/Los_Angeles",
            ),
            mock.patch(
                "orchestrator.tools.daily_note.task_daily_note",
                return_value=completed,
            ),
        ):
            daemon._handle_daily_note_deadline({"completed_date": "2026-07-19"})
        self.assertEqual(
            daemon._deadline_queue.put.call_args.args[3]["timezone"],
            "America/Los_Angeles",
        )

    def test_pending_fixed_offset_deadline_is_atomically_replaced(self):
        daemon = od.OversightDaemon()
        daemon._deadline_queue = mock.MagicMock()
        daemon._deadline_queue.get.return_value = {
            "key": "daily-note:2026-03-08", "status": "pending",
        }
        daemon._ensure_daily_note_deadline(
            "2026-03-08", timezone_name="America/Los_Angeles",
        )
        daemon._deadline_queue.cancel.assert_called_once_with(
            "daily-note:2026-03-08",
            reason=("migrated from fixed-offset calendar deadline to "
                    "named timezone America/Los_Angeles"),
        )
        args = daemon._deadline_queue.put.call_args.args
        self.assertEqual(args[1], "2026-03-09T00:00:00-07:00")
        self.assertEqual(args[3]["timezone"], "America/Los_Angeles")

    def test_calendar_deadline_recomputes_both_dst_transitions(self):
        cases = {
            "2026-03-07": "2026-03-08T00:00:00-08:00",
            "2026-03-08": "2026-03-09T00:00:00-07:00",
            "2026-10-31": "2026-11-01T00:00:00-07:00",
            "2026-11-01": "2026-11-02T00:00:00-08:00",
        }
        for completed, expected in cases.items():
            with self.subTest(completed=completed):
                self.assertEqual(
                    od._calendar_midnight_after(
                        completed, "America/Los_Angeles",
                    ).isoformat(),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
