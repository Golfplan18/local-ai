"""Tests for maintenance_scheduler — vault-doc-governed periodic maintenance.

All filesystem paths are redirected into a tempdir; the underlying
periodic_maintenance task functions are mocked (the real ones scan the
live vault).

Run::

    /opt/homebrew/bin/python3 -m unittest orchestrator.tests.test_maintenance_scheduler -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import maintenance_scheduler as ms  # noqa: E402

DAY = 86400


def _doc(maintenance_yaml: str) -> str:
    return f"---\ntype: reference\nmaintenance:\n{maintenance_yaml}---\n\n# Body\n"


class SchedulerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.vault = root / "vault"
        self.data = root / "data"
        self.oversight = self.data / "oversight"
        self.vault.mkdir()
        self.data.mkdir()
        self.doc = self.vault / ms.CONTROL_DOC_NAME

        self.patches = [
            mock.patch.object(ms, "DATA_DIR", str(self.data)),
            mock.patch.object(ms, "OVERSIGHT_DATA_DIR", str(self.oversight)),
            mock.patch.object(ms, "STATE_FILE", str(self.data / "maintenance-state.json")),
            mock.patch.object(ms, "RESULTS_FILE", str(self.data / "maintenance-results.jsonl")),
            mock.patch.object(ms, "HEARTBEAT_FILE",
                              str(self.oversight / "maintenance-scheduler-heartbeat.json")),
            mock.patch.object(ms, "control_doc_path", lambda: str(self.doc)),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches:
            self.addCleanup(p.stop)


class LoadConfigTests(SchedulerBase):
    def test_defaults_when_doc_missing(self):
        self.assertEqual(ms.load_config(), ms.DEFAULT_CONFIG)

    def test_doc_overrides_cadence(self):
        self.doc.write_text(_doc("  orphan_cleanup: monthly\n  archive_cleanup: monthly\n"))
        cfg = ms.load_config()
        self.assertEqual(cfg["orphan_cleanup"], "monthly")
        self.assertEqual(cfg["archive_cleanup"], "monthly")
        self.assertEqual(cfg["vault_health"], "monthly")  # untouched default

    def test_off_disables_task(self):
        self.doc.write_text(_doc("  orphan_cleanup: off\n"))
        self.assertEqual(ms.load_config()["orphan_cleanup"], "off")

    def test_unknown_cadence_falls_back(self):
        self.doc.write_text(_doc("  orphan_cleanup: fortnightly\n"))
        self.assertEqual(ms.load_config()["orphan_cleanup"], "weekly")

    def test_unknown_task_ignored(self):
        self.doc.write_text(_doc("  reticulate_splines: daily\n"))
        self.assertEqual(ms.load_config(), ms.DEFAULT_CONFIG)

    def test_malformed_yaml_falls_back(self):
        self.doc.write_text("---\nmaintenance: [unclosed\n---\nbody\n")
        self.assertEqual(ms.load_config(), ms.DEFAULT_CONFIG)

    def test_no_frontmatter_falls_back(self):
        self.doc.write_text("# Just a heading\n")
        self.assertEqual(ms.load_config(), ms.DEFAULT_CONFIG)


class DueTasksTests(SchedulerBase):
    def test_never_run_is_due(self):
        due = ms.due_tasks({"orphan_cleanup": "weekly"}, {})
        self.assertEqual(due, ["orphan_cleanup"])

    def test_recent_run_not_due(self):
        state = {"orphan_cleanup": datetime.now(timezone.utc).isoformat()}
        self.assertEqual(ms.due_tasks({"orphan_cleanup": "weekly"}, state), [])

    def test_stale_run_due(self):
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        self.assertEqual(
            ms.due_tasks({"orphan_cleanup": "weekly"}, {"orphan_cleanup": old}),
            ["orphan_cleanup"])

    def test_monthly_window(self):
        old20 = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        old30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.assertEqual(ms.due_tasks({"vault_health": "monthly"}, {"vault_health": old20}), [])
        self.assertEqual(ms.due_tasks({"vault_health": "monthly"}, {"vault_health": old30}),
                         ["vault_health"])

    def test_off_never_due(self):
        self.assertEqual(ms.due_tasks({"archive_cleanup": "off"}, {}), [])

    def test_corrupt_stamp_is_due(self):
        self.assertEqual(
            ms.due_tasks({"orphan_cleanup": "weekly"}, {"orphan_cleanup": "not-a-date"}),
            ["orphan_cleanup"])


class _FakeResult:
    def __init__(self, success=True, message="ok"):
        self.success = success
        self.message = message
        self.stats = {"n": 1}
        self.alerts = []
        self.duration_seconds = 0.5


class SweepTests(SchedulerBase):
    def _mock_pm(self, success=True):
        fake_pm = mock.MagicMock()
        for fn_name in ms.TASK_FUNCTIONS.values():
            setattr(fake_pm, fn_name, mock.MagicMock(return_value=_FakeResult(success)))
        return mock.patch.dict(sys.modules, {
            "orchestrator.tools.periodic_maintenance": fake_pm,
            "orchestrator": mock.MagicMock(tools=mock.MagicMock(periodic_maintenance=fake_pm)),
            "orchestrator.tools": mock.MagicMock(periodic_maintenance=fake_pm),
        }), fake_pm

    def test_dry_run_reports_without_running(self):
        summary = ms.sweep(dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertIn("orphan_cleanup", summary["due"])
        self.assertEqual(summary["ran"], [])
        self.assertFalse((self.data / "maintenance-state.json").exists())

    def test_sweep_runs_due_tasks_and_stamps(self):
        patcher, fake_pm = self._mock_pm()
        with patcher:
            summary = ms.sweep()
        self.assertEqual(set(summary["ran"]),
                         {"orphan_cleanup", "vault_health", "graph_density"})
        self.assertNotIn("archive_cleanup", summary["ran"])  # off by default
        state = json.loads((self.data / "maintenance-state.json").read_text())
        self.assertIn("orphan_cleanup", state)
        results = (self.data / "maintenance-results.jsonl").read_text().strip().split("\n")
        self.assertEqual(len(results), 3)
        self.assertTrue((self.oversight / "maintenance-scheduler-heartbeat.json").exists())

    def test_second_sweep_runs_nothing(self):
        patcher, fake_pm = self._mock_pm()
        with patcher:
            ms.sweep()
            summary2 = ms.sweep()
        self.assertEqual(summary2["due"], [])
        self.assertEqual(summary2["ran"], [])

    def test_failure_still_stamps_and_logs(self):
        patcher, fake_pm = self._mock_pm(success=False)
        with patcher:
            summary = ms.sweep()
        self.assertEqual(summary["ran"], [])
        self.assertEqual(set(summary["failed"]),
                         {"orphan_cleanup", "vault_health", "graph_density"})
        state = json.loads((self.data / "maintenance-state.json").read_text())
        self.assertIn("orphan_cleanup", state)  # no hourly retry-hammering

    def test_task_exception_is_contained(self):
        patcher, fake_pm = self._mock_pm()
        fake_pm.task_1_orphan_cleanup.side_effect = RuntimeError("boom")
        with patcher:
            summary = ms.sweep()
        self.assertIn("orphan_cleanup", summary["failed"])
        self.assertEqual(set(summary["ran"]), {"vault_health", "graph_density"})

    def test_control_doc_off_respected_in_sweep(self):
        self.doc.write_text(_doc(
            "  orphan_cleanup: off\n  vault_health: off\n  graph_density: off\n"))
        patcher, fake_pm = self._mock_pm()
        with patcher:
            summary = ms.sweep()
        self.assertEqual(summary["due"], [])
        fake_pm.task_1_orphan_cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
