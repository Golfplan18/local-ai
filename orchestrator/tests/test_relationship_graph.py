"""Tests for relationship_graph — claim-target resolution, orphan
classification, and incremental sync.

Everything runs against a temp vault + temp SQLite DB; the real vault and
~/ora/data/relationship-graph.db are never touched.

The load-bearing behaviors under test:
  - Engram relationships are statement-keyed in YAML (targets are claim
    sentences = the target engram's H1). At scan time these resolve to
    filename stems, so the compiled index is uniformly note-keyed and
    traversal/inverse lookups work across engrams.
  - find_orphan_targets treats a target as valid if it is a note title OR
    a current engram claim — dangling references of either kind surface.
  - remove_orphans accepts a precomputed orphan list (no recompute).
  - sync_from_vault reconciles the DB with vault YAML by writing diffs only
    and converges (including migrating pre-resolution claim-keyed rows).
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


def engram_body(claim: str) -> str:
    return f"# {claim}\n\n- supporting bullet\n"


# Engram two's H1 — the claim that engram one's YAML targets.
CLAIM = "Anger impairs reasoning capacity and judgment quality"
CLAIM_ONE = "Claim one anchors the test fixture chain"
ENGRAM_ONE = "2024-01-01_claim-one"
ENGRAM_TWO = "2024-01-02_claim-two"


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
        # Engram one targets engram two by claim sentence + a note by title.
        write_note(self.vault, f"Engrams/{ENGRAM_ONE}.md", [
            {"type": "analogous-to", "target": CLAIM, "confidence": "medium"},
            {"type": "supports", "target": "NoteB", "confidence": "high"},
        ], body=engram_body(CLAIM_ONE))
        write_note(self.vault, f"Engrams/{ENGRAM_TWO}.md",
                   body=engram_body(CLAIM))

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
        self.assertIn((ENGRAM_ONE, "NoteB", "supports", "high"), rows)

    def test_claim_target_resolves_to_stem(self):
        result = self.graph.build_from_vault()
        rows = self.all_rows()
        # The claim-sentence target became the target engram's filename stem.
        self.assertIn((ENGRAM_ONE, ENGRAM_TWO, "analogous-to", "medium"), rows)
        self.assertNotIn((ENGRAM_ONE, CLAIM, "analogous-to", "medium"), rows)
        self.assertEqual(result["resolution"]["resolved_targets"], 1)
        self.assertEqual(result["resolution"]["claims_indexed"], 2)

    def test_unresolved_claim_target_kept_verbatim(self):
        write_note(self.vault, "Engrams/2024-01-03_claim-three.md", [
            {"type": "supports", "target": "A claim no engram asserts"},
        ], body=engram_body("Claim three stands alone"))
        self.graph.build_from_vault()
        self.assertIn(
            ("2024-01-03_claim-three", "A claim no engram asserts",
             "supports", "medium"),
            self.all_rows())

    def test_duplicate_h1_resolves_to_earliest_stem(self):
        # Two engrams asserting the same claim: the lexicographically
        # smallest stem (= earliest date prefix) wins, deterministically.
        write_note(self.vault, "Engrams/2024-05-09_claim-two-dup.md",
                   body=engram_body(CLAIM))
        result = self.graph.build_from_vault()
        self.assertEqual(result["resolution"]["duplicate_claims"], 1)
        rows = self.all_rows()
        self.assertIn((ENGRAM_ONE, ENGRAM_TWO, "analogous-to", "medium"), rows)
        self.assertNotIn(
            (ENGRAM_ONE, "2024-05-09_claim-two-dup", "analogous-to", "medium"),
            rows)

    def test_title_match_takes_precedence_over_claim(self):
        # An engram whose H1 happens to equal a real note's title must not
        # hijack targets that already resolve as note titles.
        write_note(self.vault, "Engrams/2024-01-04_imposter.md",
                   body=engram_body("NoteB"))
        self.graph.build_from_vault()
        rows = self.all_rows()
        self.assertIn(("NoteA", "NoteB", "supports", "high"), rows)
        self.assertNotIn(("NoteA", "2024-01-04_imposter", "supports", "high"), rows)

    def test_resolution_key_collision_dedup(self):
        # A note declaring both the claim sentence and the stem it resolves
        # to collapses to one row with the better confidence.
        write_note(self.vault, "NoteC.md", [
            {"type": "supports", "target": CLAIM, "confidence": "medium"},
            {"type": "supports", "target": ENGRAM_TWO, "confidence": "high"},
        ])
        self.graph.build_from_vault()
        rows = [r for r in self.all_rows() if r[0] == "NoteC"]
        self.assertEqual(rows, [("NoteC", ENGRAM_TWO, "supports", "high")])

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


class TestTraversal(RelationshipGraphTestBase):
    def test_multi_hop_traversal_across_engrams(self):
        # Resolution makes engram→engram links walkable: claim-one →
        # claim-two → claim-five only connects if targets are stems.
        claim_five = "Multi hop chains terminate at claim five"
        write_note(self.vault, f"Engrams/{ENGRAM_TWO}.md", [
            {"type": "extends", "target": claim_five, "confidence": "high"},
        ], body=engram_body(CLAIM))
        write_note(self.vault, "Engrams/2024-01-05_claim-five.md",
                   body=engram_body(claim_five))
        self.graph.build_from_vault()
        connected = self.graph.get_connected(ENGRAM_ONE, depth=2)
        notes = {c["note"] for c in connected}
        self.assertIn(ENGRAM_TWO, notes)
        self.assertIn("2024-01-05_claim-five", notes)

    def test_inverse_lookup_finds_engram_referrers(self):
        self.graph.build_from_vault()
        incoming = self.graph.get_inverse_relationships(ENGRAM_TWO)
        self.assertEqual(
            [(r["source"], r["original_type"]) for r in incoming],
            [(ENGRAM_ONE, "analogous-to")])


class TestFindOrphanTargets(RelationshipGraphTestBase):
    def test_flags_dangling_note_reference(self):
        self.graph.build_from_vault()
        orphans = self.graph.find_orphan_targets()
        self.assertEqual(orphans, [
            {"source": "NoteA", "target": "DeletedNote", "type": "extends"}])

    def test_resolved_claim_targets_are_not_orphans(self):
        self.graph.build_from_vault()
        orphan_sources = {o["source"] for o in self.graph.find_orphan_targets()}
        self.assertNotIn(ENGRAM_ONE, orphan_sources)

    def test_claim_keyed_rows_recognized_premigration(self):
        # A pre-resolution DB still holds claim-sentence targets; they are
        # valid (the claim's engram exists), not orphans.
        self.graph.conn.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES (?, ?, ?, ?)",
            (ENGRAM_ONE, CLAIM, "analogous-to", "medium"))
        self.graph.conn.commit()
        self.assertEqual(self.graph.find_orphan_targets(), [])

    def test_flags_dangling_claim(self):
        self.graph.conn.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES (?, ?, ?, ?)",
            (ENGRAM_ONE, "A claim whose engram is gone", "supports", "medium"))
        self.graph.conn.commit()
        targets = {o["target"] for o in self.graph.find_orphan_targets()}
        self.assertIn("A claim whose engram is gone", targets)

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
        self.assertIn((ENGRAM_ONE, ENGRAM_TWO, "analogous-to", "medium"), rows)

    def test_computes_orphans_when_not_given(self):
        self.graph.build_from_vault()
        removed = self.graph.remove_orphans()
        self.assertEqual(removed, 1)
        self.assertNotIn(("NoteA", "DeletedNote", "extends", "medium"),
                         self.all_rows())

    def test_engram_rows_survive_cleanup(self):
        self.graph.build_from_vault()
        before = {r for r in self.all_rows() if r[0] == ENGRAM_ONE}
        self.graph.remove_orphans()
        after = {r for r in self.all_rows() if r[0] == ENGRAM_ONE}
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
        self.assertEqual(stats["resolution"]["resolved_targets"], 1)

    def test_migrates_claim_keyed_rows_to_stems(self):
        # Simulate a pre-resolution DB: claim-sentence target on disk.
        self.graph.conn.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES (?, ?, ?, ?)",
            (ENGRAM_ONE, CLAIM, "analogous-to", "medium"))
        self.graph.conn.commit()
        self.graph.sync_from_vault()
        rows = self.all_rows()
        self.assertIn((ENGRAM_ONE, ENGRAM_TWO, "analogous-to", "medium"), rows)
        self.assertNotIn((ENGRAM_ONE, CLAIM, "analogous-to", "medium"), rows)
        # And converges: second run is a no-op.
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 0)
        self.assertEqual(stats["rows_removed"], 0)

    def test_deleting_target_engram_reverts_rows_to_claim_text(self):
        # When the target engram disappears, the claim can no longer
        # resolve: the row reverts to the verbatim claim sentence and
        # surfaces as a dangling target.
        self.graph.build_from_vault()
        os.remove(os.path.join(self.vault, f"Engrams/{ENGRAM_TWO}.md"))
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 1)
        self.assertEqual(stats["rows_removed"], 1)
        rows = self.all_rows()
        self.assertIn((ENGRAM_ONE, CLAIM, "analogous-to", "medium"), rows)
        self.assertNotIn((ENGRAM_ONE, ENGRAM_TWO, "analogous-to", "medium"), rows)
        targets = {o["target"] for o in self.graph.find_orphan_targets()}
        self.assertIn(CLAIM, targets)

    def test_picks_up_new_note(self):
        self.graph.build_from_vault()
        write_note(self.vault, "NoteC.md", [{"type": "extends", "target": "NoteA"}])
        stats = self.graph.sync_from_vault()
        self.assertEqual(stats["rows_added"], 1)
        self.assertEqual(stats["rows_removed"], 0)
        self.assertIn(("NoteC", "NoteA", "extends", "medium"), self.all_rows())

    def test_removes_rows_for_deleted_source(self):
        self.graph.build_from_vault()
        os.remove(os.path.join(self.vault, f"Engrams/{ENGRAM_ONE}.md"))
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
        self.assertEqual({r[0] for r in self.all_rows()}, {ENGRAM_ONE})

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


class TestFrontmatterLiteralDelimiter(unittest.TestCase):
    """A literal '---' inside a quoted YAML scalar must not truncate the
    frontmatter. Incident 2026-07-02: "Framework — MSI Malcolm Little King
    Spinner" carried a `supersedes` value quoting another note's '---'
    delimiter; the bare-substring terminator search cut the YAML mid-value,
    yaml.safe_load raised "found unexpected end of stream", and the note went
    invisible to the relationship-graph scanner."""

    # '---' appears mid-line inside a double-quoted scalar, ahead of the real
    # terminator. A '# ' YAML comment sits just after it to catch an H1
    # extractor that stops at the wrong place.
    NOTE = (
        "---\n"
        "type: framework\n"
        'supersedes: "MSI Malcolm Little King Spinner `---` legacy spec"\n'
        "# a yaml comment after the inline delimiter\n"
        "relationships:\n"
        "  - type: supersedes\n"
        "    target: Legacy Spinner\n"
        "    confidence: high\n"
        "---\n"
        "\n"
        "# Malcolm Little King Spinner\n"
        "\n"
        "Body.\n"
    )

    def test_relationships_parsed_despite_inline_delimiter(self):
        errors = []
        rows = RelationshipGraph._parse_relationships_text(
            self.NOTE, "Spinner.md", errors)
        self.assertEqual(errors, [])
        self.assertIn(("Legacy Spinner", "supersedes", "high"), rows)

    def test_h1_found_past_the_real_terminator(self):
        # The H1 is the body heading — never the '# ' YAML comment that lives
        # inside the frontmatter, after the inline '---'.
        self.assertEqual(
            RelationshipGraph._extract_h1(self.NOTE),
            "Malcolm Little King Spinner")

    def test_line_starting_with_dashes_inside_scalar_is_not_a_terminator(self):
        # A quoted scalar whose continuation line *starts* with '---' (but is
        # not a bare '---' line) would fool even a naive '\\n---' search; only
        # the line-anchored terminator skips it and reaches the real closer.
        note = (
            "---\n"
            'note: "first line\n'
            '---but still the quoted value"\n'
            "relationships:\n"
            "  - type: supports\n"
            "    target: NoteB\n"
            "---\n"
            "# Title\n"
        )
        errors = []
        rows = RelationshipGraph._parse_relationships_text(note, "n.md", errors)
        self.assertEqual(errors, [])
        self.assertIn(("NoteB", "supports", "medium"), rows)


class TestFrontmatterLiteralDelimiterScan(RelationshipGraphTestBase):
    def test_note_with_inline_delimiter_is_indexed_not_dropped(self):
        # End-to-end: a real vault note carrying an inline '---' in a quoted
        # scalar is scanned, parsed, and its relationship indexed — not
        # silently dropped with a parse error.
        path = os.path.join(self.vault, "Spinner.md")
        with open(path, "w") as f:
            f.write(
                "---\n"
                "type: framework\n"
                'supersedes: "quotes another note\'s `---` delimiter"\n'
                "relationships:\n"
                "  - type: supports\n"
                "    target: NoteB\n"
                "    confidence: high\n"
                "---\n\n# Spinner\n\nBody.\n"
            )
        result = self.graph.build_from_vault()
        self.assertEqual(result["errors"], [])
        self.assertIn(("Spinner", "NoteB", "supports", "high"), self.all_rows())


if __name__ == "__main__":
    unittest.main()
