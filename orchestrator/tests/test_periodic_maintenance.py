"""Tests for periodic_maintenance task_1 — orphan report + incremental sync.

task_1_orphan_cleanup must NOT delete orphan rows row-by-row and must NOT
full-rebuild the graph DB (the pre-2026-06-12 flow churned ~1M engram rows
weekly). It reports dangling targets and delegates reconciliation to
RelationshipGraph.sync_from_vault().

Unit tests use a FakeGraph that records calls; the integration test runs a
real RelationshipGraph against a temp vault + temp DB. The live vault and
~/ora/data/relationship-graph.db are never touched.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import orchestrator.tools.periodic_maintenance as pm
from orchestrator.tools.periodic_maintenance import task_1_orphan_cleanup


EMPTY_SYNC_STATS = {
    "notes_scanned": 0, "sources_in_yaml": 0,
    "rows_added": 0, "rows_removed": 0, "sources_removed": 0, "errors": [],
}


class FakeGraph:
    """Records which RelationshipGraph methods task_1 invokes."""

    def __init__(self, orphans=None, sync_stats=None,
                 find_raises=None, sync_raises=None):
        self.orphans = orphans or []
        self.sync_stats = sync_stats or dict(EMPTY_SYNC_STATS)
        self.find_raises = find_raises
        self.sync_raises = sync_raises
        self.calls = []

    def find_orphan_targets(self):
        self.calls.append("find_orphan_targets")
        if self.find_raises:
            raise self.find_raises
        return self.orphans

    def sync_from_vault(self):
        self.calls.append("sync_from_vault")
        if self.sync_raises:
            raise self.sync_raises
        return self.sync_stats

    def remove_orphans(self, orphans=None):
        self.calls.append("remove_orphans")
        return 0

    def build_from_vault(self):
        self.calls.append("build_from_vault")
        return {}


class Task1TestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="periodic-maint-test-")
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(self.vault)
        with open(os.path.join(self.vault, "Real Note.md"), "w") as f:
            f.write("---\ntype: note\n---\n\nBody.\n")
        self._patch = mock.patch.object(pm, "VAULT_PATH", self.vault)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTask1Wiring(Task1TestBase):
    def test_no_orphans_runs_sync_only(self):
        graph = FakeGraph()
        result = task_1_orphan_cleanup(graph=graph)
        self.assertTrue(result.success)
        self.assertEqual(graph.calls, ["find_orphan_targets", "sync_from_vault"])
        self.assertEqual(result.stats["orphans_found"], 0)
        self.assertEqual(result.alerts, [])

    def test_never_deletes_or_rebuilds(self):
        orphans = [{"source": f"S{i}", "target": f"T{i}", "type": "supports"}
                   for i in range(50)]
        graph = FakeGraph(orphans=orphans)
        task_1_orphan_cleanup(graph=graph)
        self.assertNotIn("remove_orphans", graph.calls)
        self.assertNotIn("build_from_vault", graph.calls)

    def test_orphans_reported_with_alert_above_threshold(self):
        orphans = [{"source": f"S{i}", "target": f"T{i}", "type": "supports"}
                   for i in range(11)]
        result = task_1_orphan_cleanup(graph=FakeGraph(orphans=orphans))
        self.assertEqual(result.stats["orphans_found"], 11)
        self.assertEqual(len(result.alerts), 1)
        self.assertIn("dangling", result.alerts[0])

    def test_no_alert_at_or_below_threshold(self):
        orphans = [{"source": f"S{i}", "target": f"T{i}", "type": "supports"}
                   for i in range(10)]
        result = task_1_orphan_cleanup(graph=FakeGraph(orphans=orphans))
        self.assertEqual(result.alerts, [])

    def test_potentially_resolved_counts_case_space_matches(self):
        orphans = [
            {"source": "A", "target": "real note", "type": "supports"},
            {"source": "A", "target": "RealNote", "type": "supports"},
            {"source": "A", "target": "Truly Gone", "type": "supports"},
        ]
        result = task_1_orphan_cleanup(graph=FakeGraph(orphans=orphans))
        self.assertEqual(result.stats["potentially_resolved"], 2)

    def test_sync_stats_surface_in_result(self):
        stats = dict(EMPTY_SYNC_STATS, rows_added=3, rows_removed=7,
                     sources_removed=2)
        result = task_1_orphan_cleanup(graph=FakeGraph(sync_stats=stats))
        self.assertEqual(result.stats["rows_added"], 3)
        self.assertEqual(result.stats["rows_removed"], 7)
        self.assertEqual(result.stats["sources_removed"], 2)
        self.assertIn("added 3", result.message)
        self.assertIn("removed 7", result.message)

    def test_find_failure_fails_task(self):
        graph = FakeGraph(find_raises=RuntimeError("boom"))
        result = task_1_orphan_cleanup(graph=graph)
        self.assertFalse(result.success)
        self.assertIn("Error finding orphans", result.message)

    def test_sync_failure_fails_task(self):
        graph = FakeGraph(sync_raises=RuntimeError("disk full"))
        result = task_1_orphan_cleanup(graph=graph)
        self.assertFalse(result.success)
        self.assertIn("Error syncing", result.message)


class TestTask1Integration(Task1TestBase):
    """End-to-end against a real RelationshipGraph on a temp vault."""

    def _write(self, relpath, fm_body):
        path = os.path.join(self.vault, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(fm_body)

    def test_end_state_reports_dangling_and_removes_stale(self):
        from orchestrator.tools.relationship_graph import RelationshipGraph

        self._write("NoteA.md", (
            "---\nrelationships:\n"
            "- type: extends\n  target: DeletedNote\n  confidence: medium\n"
            "---\n\nBody.\n"))
        engram_path = "Engrams/2024-01-01_claim.md"
        self._write(engram_path, (
            "---\nrelationships:\n"
            "- type: supports\n  target: Anger impairs reasoning capacity\n"
            "  confidence: high\n"
            "---\n\nBody.\n"))

        graph = RelationshipGraph(
            db_path=os.path.join(self.tmp, "graph.db"), vault_path=self.vault)
        try:
            graph.build_from_vault()
            # Engram note deleted out-of-band (e.g. Obsidian).
            os.remove(os.path.join(self.vault, engram_path))

            result = task_1_orphan_cleanup(graph=graph)

            self.assertTrue(result.success)
            # Dangling note ref + the now-stale engram row both reported.
            self.assertEqual(result.stats["orphans_found"], 2)
            # Sync removed the stale engram source...
            self.assertEqual(result.stats["sources_removed"], 1)
            rows = set(graph.conn.execute(
                "SELECT source, target FROM relationships"))
            # ...but the dangling YAML-backed reference is preserved
            # (vault canonical — deleting it here would churn).
            self.assertEqual(rows, {("NoteA", "DeletedNote")})
        finally:
            graph.close()

    def test_engram_rows_are_not_churned(self):
        from orchestrator.tools.relationship_graph import RelationshipGraph

        # Engram one targets engram two by its claim sentence (= H1).
        self._write("Engrams/2024-01-01_claim.md", (
            "---\nrelationships:\n"
            "- type: supports\n  target: A claim sentence target\n"
            "  confidence: high\n"
            "---\n\n# Claim one stands first\n"))
        self._write("Engrams/2024-01-02_target.md", (
            "---\ntype: engram\n"
            "---\n\n# A claim sentence target\n"))
        graph = RelationshipGraph(
            db_path=os.path.join(self.tmp, "graph.db"), vault_path=self.vault)
        try:
            graph.build_from_vault()
            result = task_1_orphan_cleanup(graph=graph)
            self.assertTrue(result.success)
            self.assertEqual(result.stats["orphans_found"], 0)
            self.assertEqual(result.stats["rows_added"], 0)
            self.assertEqual(result.stats["rows_removed"], 0)
            # The stored row is stem-keyed (claim resolved at build time).
            rows = set(graph.conn.execute(
                "SELECT source, target FROM relationships"))
            self.assertEqual(
                rows, {("2024-01-01_claim", "2024-01-02_target")})
        finally:
            graph.close()


class TestRunWeekly(unittest.TestCase):
    def test_run_weekly_smoke(self):
        tmp = tempfile.mkdtemp(prefix="periodic-maint-weekly-")
        vault = os.path.join(tmp, "vault")
        os.makedirs(vault)
        try:
            with mock.patch.object(pm, "VAULT_PATH", vault), \
                 mock.patch.object(pm, "DATA_DIR", os.path.join(tmp, "data")), \
                 mock.patch.object(pm, "LOG_DIR", os.path.join(tmp, "logs")), \
                 mock.patch("orchestrator.tools.relationship_graph.RelationshipGraph",
                            return_value=FakeGraph()):
                run = pm.run_weekly()
            self.assertEqual(run.frequency, "weekly")
            self.assertEqual(len(run.tasks), 1)
            self.assertTrue(run.tasks[0].success)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
