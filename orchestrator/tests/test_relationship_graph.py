"""Tests for relationship_graph — orphan classification and incremental sync.

Everything runs against a temp vault + temp SQLite DB; the real vault and
~/ora/data/relationship-graph.db are never touched.

The load-bearing behaviors under test:
  - find_orphan_targets exempts statement-keyed sources (Engrams/), whose
    targets are claim sentences, not note filenames — without the exemption
    every engram row classifies as an orphan.
  - remove_orphans accepts a precomputed orphan list (no recompute).
  - sync_from_vault reconciles the DB with vault YAML by writing diffs only,
    replacing the weekly delete-everything + full-rebuild churn.
"""

import os
import shutil
import tempfile
import unittest

import yaml

from orchestrator.tools.relationship_graph import RelationshipGraph


def write_note(vault_path: str, relpath: str, relationships=None, body="Body."):
    """Write a vault note with YAML frontmatter."""
    path = os.path.join(vault_path, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fm = {"type": "note"}
    if relationships is not None:
        fm["relationships"] = relationships
    content = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body + "\n"
    with open(path, "w") as f:
        f.write(content)
    return path


CLAIM = "Anger impairs reasoning capacity and judgment quality"


class RelationshipGraphTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="relgraph-test-")
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(self.vault)
        self.db_path = os.path.join(self.tmp, "graph.db")

        # A regular note with one resolvable and one dangling target.
        write_note(self.vault, "NoteA.md", [
            {"type": "supports", "target": "NoteB", "confidence": "high"},
            {"type": "extends", "target": "DeletedNote", "confidence": "medium"},
        ])
        write_note(self.vault, "NoteB.md")
        # An engram: statement-keyed targets plus one note-title target.
        self.engram_name = "2024-01-01_claim-one"
        write_note(self.vault, f"Engrams/{self.engram_name}.md", [
            {"type": "analogous-to", "target": CLAIM, "confidence": "medium"},
            {"type": "supports", "target": "NoteB", "confidence": "high"},
        ])

        self.graph = RelationshipGraph(db_path=self.db_path, vault_path=self.vault)

    def tearDown(self):
        self.graph.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def all_rows(self):
        return set(self.graph.conn.execute(
            "SELECT source, target, type, confidence FROM relationships"))


class TestBuildFromVault(RelationshipGraphTestBase):
    def test_indexes_all_relationships(self):
        result = self.graph.build_from_vault()
        self.assertEqual(result["relationships_indexed"], 4)
        self.assertEqual(result["errors"], [])
        rows = self.all_rows()
        self.assertIn(("NoteA", "NoteB", "supports", "high"), rows)
        self.assertIn(("NoteA", "DeletedNote", "extends", "medium"), rows)
        self.assertIn((self.engram_name, CLAIM, "analogous-to", "medium"), rows)

    def test_excludes_trash_and_archived_dirs(self):
        write_note(self.vault, ".trash/Trashed.md",
                   [{"type": "supports", "target": "NoteB"}])
        write_note(self.vault, "Old AI Working Files/Archived.md",
                   [{"type": "supports", "target": "NoteB"}])
        self.graph.build_from_vault()
        sources = {r[0] for r in self.all_rows()}
        self.assertNotIn("Trashed", sources)
        self.assertNotIn("Archived", sources)

    def test_duplicate_stems_union(self):
        # Two files with the same stem in different folders both contribute.
        write_note(self.vault, "NoteD.md", [{"type": "supports", "target": "NoteB"}])
        write_note(self.vault, "sub/NoteD.md", [{"type": "extends", "target": "NoteB"}])
        self.graph.build_from_vault()
        types = {r[2] for r in self.all_rows() if r[0] == "NoteD"}
        self.assertEqual(types, {"supports", "extends"})


class TestFindOrphanTargets(RelationshipGraphTestBase):
    def test_flags_dangling_note_reference(self):
        self.graph.build_from_vault()
        orphans = self.graph.find_orphan_targets()
        self.assertEqual(orphans, [
            {"source": "NoteA", "target": "DeletedNote", "type": "extends"}])

    def test_exempts_statement_keyed_sources(self):
        self.graph.build_from_vault()
        orphan_sources = {o["source"] for o in self.graph.find_orphan_targets()}
        self.assertNotIn(self.engram_name, orphan_sources)

    def test_flags_rows_from_deleted_statement_source(self):
        # Rows whose engram source file no longer exists lose the exemption:
        # they are genuinely stale, not statement-keyed-by-design.
        self.graph.build_from_vault()
        self.graph.add_relationships("2020-05-05_gone-engram", [
            {"type": "supports", "target": "Some claim that was extracted"}])
        orphans = self.graph.find_orphan_targets()
        self.assertIn(
            {"source": "2020-05-05_gone-engram",
             "target": "Some claim that was extracted", "type": "supports"},
            orphans)

    def test_trashed_note_is_not_a_valid_target(self):
        write_note(self.vault, ".trash/Ghost.md")
        write_note(self.vault, "NoteC.md", [{"type": "supports", "target": "Ghost"}])
        self.graph.build_from_vault()
        targets = {o["target"] for o in self.graph.find_orphan_targets()}
        self.assertIn("Ghost", targets)


class TestRemoveOrphans(RelationshipGraphTestBase):
    def test_accepts_precomputed_list(self):
        self.graph.build_from_vault()
        removed = self.graph.remove_orphans(
            [{"source": "NoteA", "target": "DeletedNote", "type": "extends"}])
        self.assertEqual(removed, 1)
        rows = self.all_rows()
        self.assertNotIn(("NoteA", "DeletedNote", "extends", "medium"), rows)
        # Untouched rows survive.
        self.assertIn(("NoteA", "NoteB", "supports", "high"), rows)
        self.assertIn((self.engram_name, CLAIM, "analogous-to", "medium"), rows)

    def test_computes_orphans_when_not_given(self):
        self.graph.build_from_vault()
        removed = self.graph.remove_orphans()
        self.assertEqual(removed, 1)
        self.assertNotIn(("NoteA", "DeletedNote", "extends", "medium"),
                         self.all_rows())

    def test_engram_rows_survive_cleanup(self):
        self.graph.build_from_vault()
        before = {r for r in self.all_rows() if r[0] == self.engram_name}
        self.graph.remove_orphans()
        after = {r for r in self.all_rows() if r[0] == self.engram_name}
        self.assertEqual(before, after)


class TestSyncFromVault(RelationshipGraphTestBase):
    def test_noop_when_nothing_changed(self):
        self.graph.build_from_vault()
        before = self.all_rows()
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 0)
        self.assertEqual(stats["rows_removed"], 0)
        self.assertEqual(stats["sources_removed"], 0)
        self.assertEqual(self.all_rows(), before)

    def test_populates_empty_db(self):
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 4)
        self.assertEqual(len(self.all_rows()), 4)

    def test_picks_up_new_note(self):
        self.graph.build_from_vault()
        write_note(self.vault, "NoteC.md", [{"type": "extends", "target": "NoteA"}])
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 1)
        self.assertEqual(stats["rows_removed"], 0)
        self.assertIn(("NoteC", "NoteA", "extends", "medium"), self.all_rows())

    def test_removes_rows_for_deleted_source(self):
        self.graph.build_from_vault()
        os.remove(os.path.join(self.vault, f"Engrams/{self.engram_name}.md"))
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["sources_removed"], 1)
        self.assertEqual(stats["rows_removed"], 2)
        self.assertEqual({r[0] for r in self.all_rows()}, {"NoteA"})

    def test_removes_rows_when_yaml_drops_relationship(self):
        self.graph.build_from_vault()
        write_note(self.vault, "NoteA.md", [
            {"type": "supports", "target": "NoteB", "confidence": "high"}])
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 0)
        self.assertEqual(stats["rows_removed"], 1)
        self.assertNotIn(("NoteA", "DeletedNote", "extends", "medium"),
                         self.all_rows())

    def test_removes_rows_when_yaml_relationships_emptied(self):
        self.graph.build_from_vault()
        write_note(self.vault, "NoteA.md")  # no relationships key at all
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_removed"], 2)
        self.assertEqual({r[0] for r in self.all_rows()}, {self.engram_name})

    def test_confidence_change_updates_in_place(self):
        self.graph.build_from_vault()
        write_note(self.vault, "NoteA.md", [
            {"type": "supports", "target": "NoteB", "confidence": "low"},
            {"type": "extends", "target": "DeletedNote", "confidence": "medium"},
        ])
        before_count = len(self.all_rows())
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 1)   # the INSERT OR REPLACE
        self.assertEqual(stats["rows_removed"], 0)  # no spurious delete
        self.assertEqual(len(self.all_rows()), before_count)
        self.assertIn(("NoteA", "NoteB", "supports", "low"), self.all_rows())

    def test_restores_externally_deleted_rows(self):
        # Rows still declared in YAML always converge back (vault canonical).
        self.graph.build_from_vault()
        self.graph.conn.execute(
            "DELETE FROM relationships WHERE source = 'NoteA'")
        self.graph.conn.commit()
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 2)
        self.assertIn(("NoteA", "NoteB", "supports", "high"), self.all_rows())

    def test_stamps_last_sync_metadata(self):
        self.graph.sync_from_vault()
        self.assertIsNotNone(self.graph.stats()["last_sync"])

    def test_numeric_confidence_converges(self):
        # Engram similarity scores are numeric in YAML (confidence: 0.861).
        # YAML yields a float; the TEXT-affinity column returns a string —
        # without str() coercion at parse time every such row re-adds on
        # every sync, forever.
        write_note(self.vault, "NoteE.md", [
            {"type": "parallels", "target": "NoteB", "confidence": 0.861}])
        self.graph.build_from_vault()
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 0)
        self.assertEqual(stats["rows_removed"], 0)
        self.assertIn(("NoteE", "NoteB", "parallels", "0.861"), self.all_rows())

    def test_date_target_converges(self):
        # A bare date target (target: 2025-04-11) parses as datetime.date.
        path = os.path.join(self.vault, "NoteF.md")
        with open(path, "w") as f:
            f.write("---\nrelationships:\n"
                    "- type: precedes\n  target: 2025-04-11\n"
                    "---\n\nBody.\n")
        self.graph.build_from_vault()
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 0)
        targets = {r[1] for r in self.all_rows() if r[0] == "NoteF"}
        self.assertEqual(targets, {"2025-04-11"})

    def test_conflicting_duplicate_confidence_resolves_deterministically(self):
        # The same (target, type) declared twice with different confidences
        # must collapse to one row with a deterministic winner — otherwise
        # the stored value flip-flops with set iteration order and sync
        # churns the row on every run.
        write_note(self.vault, "NoteG.md", [
            {"type": "supports", "target": "NoteB", "confidence": "medium"},
            {"type": "supports", "target": "NoteB", "confidence": "high"},
        ])
        self.graph.build_from_vault()
        self.assertIn(("NoteG", "NoteB", "supports", "high"), self.all_rows())
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 0)
        self.assertEqual(stats["rows_removed"], 0)


if __name__ == "__main__":
    unittest.main()
