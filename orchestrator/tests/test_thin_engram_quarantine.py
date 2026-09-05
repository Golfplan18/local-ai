"""Tests for the exact test-era engram quarantine signature."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[2] / "scripts" / "quarantine_thin_runtime_engrams.py"
SPEC = importlib.util.spec_from_file_location("thin_engram_quarantine", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def _note(body: str, *, source_platform: str = "ora-local") -> str:
    return (
        "---\n"
        "type: engram\n"
        "tags: [atomic, fact]\n"
        f"source_platform: {source_platform}\n"
        "---\n\n"
        f"{body}\n"
    )


class ThinEngramQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engrams = self.root / "Engrams"
        self.engrams.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name: str, body: str, **kwargs) -> Path:
        path = self.engrams / name
        path.write_text(_note(body, **kwargs), encoding="utf-8")
        return path

    def test_graph_cleanup_invalidates_incremental_freshness_and_reconciliation_restores_canonical_truth(self):
        from orchestrator.tools.relationship_graph import RelationshipGraph, read_relationship_snapshot
        source = self.engrams / "Source.md"
        source.write_text("---\nrelationships:\n  - target: Target\n    type: supports\n---\n# Source\n")
        self._write("Target.md", "# Target")
        graph = RelationshipGraph(db_path=str(self.root / "graph.db"), vault_path=str(self.root))
        self.addCleanup(graph.close)
        graph.sync_from_vault()
        before = set(graph.conn.execute("SELECT source, target, type, confidence FROM relationships"))
        result = module._delete_graph_rows(["Target"], self.root / "graph.db")
        self.assertEqual(result, {"matched": 1, "deleted": 1})
        def snapshot():
            return read_relationship_snapshot({"Source"}, db_path=graph.db_path, vault_path=self.root)
        self.assertEqual(snapshot()["state"], "incomplete")
        self.assertIn("quarantine", snapshot()["reason"])
        result = graph.sync_from_vault()
        self.assertEqual(result["files_parsed"], 0)
        self.assertEqual(snapshot()["state"], "fresh")
        self.assertEqual(set(graph.conn.execute("SELECT source, target, type, confidence FROM relationships")), before)

    def test_exact_retired_template_is_candidate(self):
        path = self._write(
            "thin.md",
            "# A claim has a concrete consequence\n\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
        )
        self.assertTrue(module.is_thin_runtime_engram(path))

    def test_rich_historical_ora_local_note_is_preserved(self):
        path = self._write(
            "rich.md",
            "# A claim has a concrete consequence\n\n"
            "- Claim: A claim has a concrete consequence.\n"
            "- Evidence: The source records two independent observations.\n"
            "- Boundary: The claim does not apply outside the observed domain.",
        )
        self.assertFalse(module.is_thin_runtime_engram(path))

    def test_non_ora_local_note_is_preserved(self):
        path = self._write(
            "external.md",
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
            source_platform="claude-export",
        )
        self.assertFalse(module.is_thin_runtime_engram(path))

    def test_dry_run_discovers_without_moving(self):
        path = self._write(
            "thin.md",
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
        )
        result = module.execute(
            vault_root=self.root,
            chromadb_path=self.root / "chroma",
            graph_db=self.root / "graph.db",
            apply=False,
            expected_count=1,
        )
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(path.exists())
        self.assertFalse((self.root / "Archive").exists())

    def test_apply_moves_exact_candidate_and_pairs_index_cleanup(self):
        path = self._write(
            "thin.md",
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
        ).resolve()

        with mock.patch.object(
            module, "_preflight_indexes",
        ) as preflight, mock.patch.object(
            module, "_delete_chroma_records",
            return_value={"found": 1, "deleted": 1, "missing": 0},
        ) as chroma, mock.patch.object(
            module, "_delete_graph_rows",
            return_value={"matched": 3, "deleted": 3},
        ) as graph:
            result = module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=1,
            )

        destination = (
            self.root / "Archive" / "Test-era Ora-local Engrams" / "thin.md"
        )
        self.assertFalse(path.exists())
        self.assertTrue(destination.exists())
        preflight.assert_called_once_with(
            self.root / "chroma", self.root / "graph.db"
        )
        chroma.assert_called_once_with([path], self.root / "chroma")
        graph.assert_called_once_with(["thin"], self.root / "graph.db")
        self.assertEqual(result["chroma"]["deleted"], 1)
        self.assertEqual(result["graph"]["deleted"], 3)

    def test_symlink_candidate_outside_engrams_is_ignored(self):
        outside = self.root / "outside.md"
        outside.write_text(_note(
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3"
        ), encoding="utf-8")
        (self.engrams / "linked.md").symlink_to(outside)

        self.assertEqual(module.discover_candidates(self.engrams), [])
        self.assertTrue(outside.exists())

    def test_apply_requires_expected_population_guard(self):
        with self.assertRaisesRegex(ValueError, "expected-count"):
            module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=None,
            )

    def test_symlinked_quarantine_destination_is_rejected(self):
        self._write(
            "thin.md",
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
        )
        archive = self.root / "Archive"
        outside = self.root / "outside"
        archive.mkdir()
        outside.mkdir()
        (archive / "Test-era Ora-local Engrams").symlink_to(
            outside, target_is_directory=True
        )

        with self.assertRaisesRegex(ValueError, "symlinked quarantine"):
            module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=1,
            )

        self.assertTrue((self.engrams / "thin.md").exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_chroma_failure_after_move_is_manifested_and_resumable(self):
        self._write(
            "thin.md",
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
        )
        manifest = self.root / "manifest.json"

        with mock.patch.object(module, "_preflight_indexes"), \
             mock.patch.object(
                 module, "_delete_chroma_records", side_effect=RuntimeError("chroma down")
             ), self.assertRaises(RuntimeError):
            module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=1,
                manifest_path=manifest,
            )

        failed = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(failed["phase"], "failed")
        self.assertEqual(failed["active_candidate_count"], 1)

        with mock.patch.object(module, "_preflight_indexes"), \
             mock.patch.object(
                 module, "_delete_chroma_records",
                 return_value={"found": 0, "deleted": 0, "missing": 1},
             ), mock.patch.object(
                 module, "_delete_graph_rows",
                 return_value={"matched": 1, "deleted": 1},
             ):
            resumed = module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=1,
                manifest_path=manifest,
            )

        self.assertEqual(resumed["phase"], "complete")
        self.assertEqual(resumed["active_candidate_count"], 0)
        self.assertEqual(resumed["already_quarantined_count"], 1)

    def test_graph_failure_after_chroma_is_manifested_and_resumable(self):
        self._write(
            "thin.md",
            "# A claim has a concrete consequence\n"
            "- A claim has a concrete consequence\n"
            "- Source: extracted from session a1b2c3",
        )
        manifest = self.root / "manifest.json"

        with mock.patch.object(module, "_preflight_indexes"), \
             mock.patch.object(
                 module, "_delete_chroma_records",
                 return_value={"found": 1, "deleted": 1, "missing": 0},
             ), mock.patch.object(
                 module, "_delete_graph_rows", side_effect=RuntimeError("graph locked")
             ), self.assertRaises(RuntimeError):
            module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=1,
                manifest_path=manifest,
            )

        failed = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(failed["phase"], "failed")
        self.assertEqual(failed["chroma"]["deleted"], 1)

        with mock.patch.object(module, "_preflight_indexes"), \
             mock.patch.object(
                 module, "_delete_chroma_records",
                 return_value={"found": 0, "deleted": 0, "missing": 1},
             ), mock.patch.object(
                 module, "_delete_graph_rows",
                 return_value={"matched": 1, "deleted": 1},
             ):
            resumed = module.execute(
                vault_root=self.root,
                chromadb_path=self.root / "chroma",
                graph_db=self.root / "graph.db",
                apply=True,
                expected_count=1,
                manifest_path=manifest,
            )

        self.assertEqual(resumed["phase"], "complete")
        self.assertEqual(resumed["graph"]["deleted"], 1)


if __name__ == "__main__":
    unittest.main()
