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

import hashlib
import os
import shutil
import sqlite3
import threading
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import yaml

from orchestrator.tools.relationship_graph import (
    RelationshipGraph,
    read_relationship_snapshot,
)
from orchestrator.tools.relationship_discovery import (
    discover_relationships,
    update_note_relationships,
)


def write_note(vault_path: str, relpath: str, relationships=None, body="Body.",
               tags=None):
    """Write a vault note with YAML frontmatter."""
    path = os.path.join(vault_path, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fm = {"type": "note"}
    if tags is not None:
        fm["tags"] = tags
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


class TestReadOnlyRelationshipSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="relgraph-snapshot-test-")
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(self.vault)
        write_note(self.vault, "NoteA.md")
        self.db_path = os.path.join(self.tmp, "snapshot.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _database(self, *, updated_at: str, complete: str = "1"):
        graph = RelationshipGraph(db_path=self.db_path, vault_path=self.vault)
        graph.sync_from_vault()
        graph.close()
        connection = sqlite3.connect(self.db_path)
        connection.executescript("""
            INSERT INTO relationships (source, target, type, confidence)
            VALUES ('NoteA', 'NoteB', 'supports', 'high');
        """)
        connection.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            [("last_update_at", updated_at),
             ("last_update_complete", complete),
             ("vault_markdown_inventory_sha256",
              hashlib.sha256(b"NoteA.md\0").hexdigest())],
        )
        connection.commit()
        connection.close()

    def test_reads_typed_fresh_snapshot_without_mutating_database(self):
        updated_at = (
            datetime.now(timezone.utc) + timedelta(seconds=2)
        ).isoformat(timespec="microseconds")
        self._database(updated_at=updated_at)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES ('NoteB', 'NoteA', 'extends', 'medium')"
        )
        connection.executemany(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES (?, ?, 'supports', 'low')",
            [(f"IrrelevantSource{index}", f"IrrelevantTarget{index}")
             for index in range(500)],
        )
        source_plan = " ".join(
            str(part)
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT source, target, type, confidence "
                "FROM relationships WHERE source IN (?, ?)",
                ("NoteA", "NoteB"),
            )
            for part in row
        )
        target_plan = " ".join(
            str(part)
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT source, target, type, confidence "
                "FROM relationships WHERE target IN (?, ?)",
                ("NoteA", "NoteB"),
            )
            for part in row
        )
        connection.commit()
        connection.close()
        self.assertIn("idx_source", source_plan)
        self.assertIn("idx_target", target_plan)
        before = os.stat(self.db_path)
        before_names = set(os.listdir(self.tmp))
        real_connect = sqlite3.connect

        statements = []
        edge_fetchall = []

        class TrackingCursor:
            def __init__(self, cursor, sql):
                self._cursor = cursor
                self._sql = sql

            def __iter__(self):
                return iter(self._cursor)

            def fetchall(self):
                if "FROM relationships" in self._sql:
                    edge_fetchall.append(self._sql)
                return self._cursor.fetchall()

        class TrackingConnection:
            def __init__(self, connection):
                self._connection = connection

            def execute(self, sql, parameters=()):
                statements.append(" ".join(sql.split()))
                return TrackingCursor(
                    self._connection.execute(sql, parameters), sql,
                )

            def close(self):
                self._connection.close()

        with mock.patch(
            "orchestrator.tools.relationship_graph.sqlite3.connect",
            side_effect=lambda *args, **kwargs: TrackingConnection(
                real_connect(*args, **kwargs)
            ),
        ) as connect:
            snapshot = read_relationship_snapshot(
                {"NoteA", "NoteB"}, db_path=self.db_path,
                vault_path=self.vault,
            )
            empty_snapshot = read_relationship_snapshot(
                set(), db_path=self.db_path, vault_path=self.vault,
            )

        after = os.stat(self.db_path)
        self.assertEqual(snapshot["state"], "fresh")
        self.assertEqual(snapshot["items"]["NoteA"]["summaries"], [
            {"type": "is-extended-by", "direction": "incoming",
             "confidence": "medium", "count": 1,
             "original_type": "extends"},
            {"type": "supports", "direction": "outgoing",
             "confidence": "high", "count": 1},
        ])
        self.assertEqual(snapshot["items"]["NoteB"]["summaries"], [
            {"type": "extends", "direction": "outgoing",
             "confidence": "medium", "count": 1},
            {"type": "is-supported-by", "direction": "incoming",
             "confidence": "high", "count": 1,
             "original_type": "supports"},
        ])
        self.assertEqual(empty_snapshot["state"], "fresh")
        self.assertEqual(empty_snapshot["items"], {})
        self.assertNotIn("IrrelevantSource0", str(snapshot))
        relationship_reads = [
            statement for statement in statements
            if "FROM relationships" in statement
        ]
        self.assertEqual(len(relationship_reads), 2)
        self.assertTrue(all(
            "WHERE source IN (?, ?)" in statement
            or "WHERE target IN (?, ?)" in statement
            for statement in relationship_reads
        ))
        self.assertTrue(any(
            "WHERE source IN" in sql for sql in relationship_reads
        ))
        self.assertTrue(any(
            "WHERE target IN" in sql for sql in relationship_reads
        ))
        self.assertEqual(edge_fetchall, [])
        uri = connect.call_args.args[0]
        self.assertIn("mode=ro", uri)
        self.assertTrue(connect.call_args.kwargs["uri"])
        self.assertEqual((after.st_size, after.st_mtime_ns),
                         (before.st_size, before.st_mtime_ns))
        self.assertEqual(set(os.listdir(self.tmp)), before_names)

    def test_reports_stale_when_markdown_is_newer(self):
        self._database(updated_at="2020-01-01T00:00:00+00:00")
        write_note(self.vault, "NoteA.md", body="Changed after observation")

        snapshot = read_relationship_snapshot(
            {"NoteA"}, db_path=self.db_path, vault_path=self.vault,
        )

        self.assertEqual(snapshot["state"], "stale")
        self.assertIn("changed after", snapshot["reason"])

    def test_reports_incomplete_without_complete_update_evidence(self):
        self._database(
            updated_at=datetime.now(timezone.utc).isoformat(), complete="0",
        )

        snapshot = read_relationship_snapshot(
            {"NoteA"}, db_path=self.db_path, vault_path=self.vault,
        )

        self.assertEqual(snapshot["state"], "incomplete")
        self.assertIn("not proven complete", snapshot["reason"])

    def test_missing_database_is_unavailable_and_not_created(self):
        db_path = os.path.join(self.tmp, "missing", "graph.db")

        snapshot = read_relationship_snapshot(
            {"NoteA"}, db_path=db_path, vault_path=self.vault,
        )

        self.assertEqual(snapshot["state"], "unavailable")
        self.assertFalse(os.path.exists(os.path.dirname(db_path)))

    def test_full_sync_uses_start_watermark_and_direct_mutators_invalidate_it(self):
        graph = RelationshipGraph(
            db_path=os.path.join(self.tmp, "writer.db"), vault_path=self.vault,
        )
        self.addCleanup(graph.close)
        scan_started_at = []
        original_scan = graph._scan_vault_relationships

        def observe_scan(errors):
            scan_started_at.append(datetime.now(timezone.utc))
            return original_scan(errors)

        with mock.patch.object(
            graph, "_scan_vault_relationships", side_effect=observe_scan,
        ):
            result = graph.sync_from_vault()

        self.assertEqual(result["errors"], [])
        metadata = dict(graph.conn.execute("SELECT key, value FROM metadata"))
        watermark = datetime.fromisoformat(metadata["last_update_at"])
        self.assertLessEqual(watermark, scan_started_at[0])
        self.assertEqual(metadata["last_update_complete"], "1")
        snapshot = read_relationship_snapshot(
            {"NoteA"}, db_path=graph.db_path, vault_path=self.vault,
        )
        self.assertEqual(snapshot["state"], "fresh")

        note_a = os.path.join(self.vault, "NoteA.md")
        renamed_note = os.path.join(self.vault, "RenamedNoteA.md")
        note_mtime = os.stat(note_a).st_mtime_ns
        os.rename(note_a, renamed_note)
        self.assertEqual(os.stat(renamed_note).st_mtime_ns, note_mtime)
        snapshot = read_relationship_snapshot(
            {"NoteA"}, db_path=graph.db_path, vault_path=self.vault,
        )
        self.assertEqual(snapshot["state"], "stale")
        self.assertIn("inventory changed", snapshot["reason"])

        graph.add_relationships("DirectSource", [{
            "type": "supports", "target": "NoteA", "confidence": "high",
        }])
        metadata = dict(graph.conn.execute("SELECT key, value FROM metadata"))
        self.assertEqual(metadata["last_update_complete"], "0")
        self.assertEqual(metadata["last_update_at"], watermark.isoformat(
            timespec="microseconds"
        ))

        graph.sync_from_vault()
        metadata = dict(graph.conn.execute("SELECT key, value FROM metadata"))
        self.assertEqual(metadata["last_update_complete"], "1")

        graph.remove_orphans([])
        metadata = dict(graph.conn.execute("SELECT key, value FROM metadata"))
        self.assertEqual(metadata["last_update_complete"], "0")

    def test_vault_traversal_errors_make_sync_and_snapshot_incomplete(self):
        def denied_walk(path, *, onerror=None):
            if onerror is not None:
                onerror(PermissionError(13, "denied", str(path)))
            return iter(())

        graph = RelationshipGraph(
            db_path=os.path.join(self.tmp, "writer.db"), vault_path=self.vault,
        )
        self.addCleanup(graph.close)
        with mock.patch(
            "orchestrator.tools.relationship_graph.os.walk",
            side_effect=denied_walk,
        ):
            result = graph.sync_from_vault()

        self.assertTrue(result["errors"])
        metadata = dict(graph.conn.execute("SELECT key, value FROM metadata"))
        self.assertEqual(metadata["last_update_complete"], "0")

        updated_at = (
            datetime.now(timezone.utc) + timedelta(seconds=2)
        ).isoformat(timespec="microseconds")
        self._database(updated_at=updated_at)
        with mock.patch(
            "orchestrator.tools.relationship_graph.os.walk",
            side_effect=denied_walk,
        ):
            snapshot = read_relationship_snapshot(
                {"NoteA"}, db_path=self.db_path, vault_path=self.vault,
            )

        self.assertEqual(snapshot["state"], "incomplete")
        self.assertIn("directories could not be inspected", snapshot["reason"])


class TestPerFileRelationshipRefresh(RelationshipGraphTestBase):
    def snapshot(self):
        return read_relationship_snapshot({"NoteA", ENGRAM_ONE},
                                          db_path=self.db_path, vault_path=self.vault)

    def test_create_modify_rename_delete_repair_referrers_and_duplicate_claims(self):
        self.graph.sync_from_vault()
        second = os.path.join(self.vault, f"Engrams/{ENGRAM_TWO}.md")
        renamed = os.path.join(self.vault, "Engrams/earlier.md")
        os.rename(second, renamed)
        self.graph.refresh_paths({second, renamed})
        self.assertIn((ENGRAM_ONE, "earlier", "analogous-to", "medium"), self.all_rows())
        duplicate = write_note(self.vault, "Engrams/000-earliest.md", body=engram_body(CLAIM))
        self.graph.refresh_paths({duplicate})
        self.assertIn((ENGRAM_ONE, "000-earliest", "analogous-to", "medium"), self.all_rows())
        os.unlink(duplicate)
        self.graph.refresh_paths({duplicate})
        self.assertIn((ENGRAM_ONE, "earlier", "analogous-to", "medium"), self.all_rows())
        write_note(self.vault, "Engrams/earlier.md", body=engram_body("Changed claim"))
        self.graph.refresh_paths({renamed})
        self.assertIn((ENGRAM_ONE, CLAIM, "analogous-to", "medium"), self.all_rows())
        title = write_note(self.vault, CLAIM + ".md")
        self.graph.refresh_paths({title})
        self.assertIn((ENGRAM_ONE, CLAIM, "analogous-to", "medium"), self.all_rows())
        os.unlink(os.path.join(self.vault, "NoteA.md"))
        self.graph.refresh_paths({os.path.join(self.vault, "NoteA.md")})
        self.assertFalse(any(row[0] == "NoteA" for row in self.all_rows()))
        self.assertEqual(self.snapshot()["state"], "fresh")

    def test_unchanged_and_timestamp_only_bytes_are_not_reparsed(self):
        self.graph.sync_from_vault()
        with mock.patch.object(self.graph, "_parse_frontmatter_text", wraps=self.graph._parse_frontmatter_text) as parse:
            self.assertEqual(self.graph.sync_from_vault()["files_hashed"], 0)
            note = os.path.join(self.vault, "NoteA.md")
            observed = os.stat(note)
            os.utime(note, ns=(observed.st_atime_ns, observed.st_mtime_ns + 1000000))
            result = self.graph.sync_from_vault()
            self.assertEqual(result["files_hashed"], 1)
            self.assertEqual(result["files_parsed"], 0)
            self.graph.refresh_paths({note})
            renamed = os.path.join(self.vault, "Renamed.md")
            os.rename(note, renamed)
            self.graph.refresh_paths({note, renamed})
            self.assertEqual(parse.call_count, 0)

    def test_same_stem_union_survives_one_supplier_deletion(self):
        extra = write_note(self.vault, "Nested/NoteA.md", [
            {"type": "supports", "target": "NoteB", "confidence": "low"},
            {"type": "requires", "target": "NoteB", "confidence": "medium"}])
        self.graph.sync_from_vault()
        os.unlink(os.path.join(self.vault, "NoteA.md"))
        self.graph.refresh_paths({os.path.join(self.vault, "NoteA.md")})
        self.assertEqual({row for row in self.all_rows() if row[0] == "NoteA"}, {
            ("NoteA", "NoteB", "supports", "low"), ("NoteA", "NoteB", "requires", "medium")})
        os.unlink(extra)
        self.graph.refresh_paths({os.path.dirname(extra)})
        self.assertFalse(any(row[0] == "NoteA" for row in self.all_rows()))

    def test_single_event_cannot_conceal_unrelated_missed_work(self):
        self.graph.sync_from_vault()
        write_note(self.vault, "NoteB.md", [{"target": "NoteA", "type": "requires"}])
        self.graph.refresh_paths({os.path.join(self.vault, "NoteA.md")})
        self.assertEqual(self.snapshot()["state"], "stale")
        result = self.graph.sync_from_vault()
        self.assertEqual(result["files_parsed"], 1)
        self.assertIn(("NoteB", "NoteA", "requires", "medium"), self.all_rows())
        self.assertEqual(self.snapshot()["state"], "fresh")

    def test_parse_and_traversal_errors_preserve_old_rows_and_incomplete_reason(self):
        self.graph.sync_from_vault()
        before = self.all_rows()
        note = os.path.join(self.vault, "NoteA.md")
        with open(note, "w") as handle:
            handle.write("---\nrelationships: [\n---\n")
        self.assertTrue(self.graph.refresh_paths({note})["errors"])
        self.assertEqual(self.all_rows(), before)
        self.graph.refresh_paths({os.path.join(self.vault, "NoteB.md")})
        self.assertEqual(self.snapshot()["state"], "incomplete")
        def denied(path, *, onerror=None):
            onerror(PermissionError("fixture directory denied"))
            return iter(())
        with mock.patch("orchestrator.tools.relationship_graph.os.walk", side_effect=denied):
            self.assertTrue(self.graph.sync_from_vault()["errors"])
        self.assertEqual(self.all_rows(), before)
        write_note(self.vault, "NoteA.md")
        self.graph.sync_from_vault()
        self.assertEqual(self.snapshot()["state"], "fresh")

    def test_restart_resumes_cancelled_finite_batches_without_reparsing(self):
        stop = threading.Event()
        original = self.graph._refresh_files
        def refresh(*args, **kwargs):
            result = original(*args, **kwargs)
            stop.set()
            return result
        with mock.patch.object(self.graph, "_refresh_files", side_effect=refresh):
            partial = self.graph.catch_up_from_vault(stop_event=stop, batch_size=1)
        self.assertTrue(partial["cancelled"])
        self.assertEqual(partial["files_parsed"], 1)
        self.graph.close()
        self.graph = RelationshipGraph(db_path=self.db_path, vault_path=self.vault)
        result = self.graph.catch_up_from_vault(batch_size=1)
        self.assertEqual(result["files_parsed"], 3)
        self.assertEqual(result["errors"], [])
        self.assertEqual(self.snapshot()["state"], "fresh")

    def test_racing_parse_and_interrupted_transaction_cannot_replace_newer_truth(self):
        self.graph.sync_from_vault()
        before = self.all_rows()
        note = write_note(self.vault, "NoteA.md", [{"target": "NoteB", "type": "requires"}])
        parse = self.graph._parse_frontmatter_text
        def race(content, path, errors):
            result = parse(content, path, errors)
            write_note(self.vault, "NoteA.md", [{"target": "NoteB", "type": "produces"}])
            return result
        with mock.patch.object(self.graph, "_parse_frontmatter_text", side_effect=race):
            self.assertTrue(self.graph.refresh_paths({note})["errors"])
        self.assertEqual(self.all_rows(), before)
        with mock.patch.object(self.graph, "_reconcile_cached_rows", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.graph.refresh_paths({note})
        self.assertEqual(self.all_rows(), before)
        self.graph.sync_from_vault()
        self.assertIn(("NoteA", "NoteB", "produces", "medium"), self.all_rows())

    def test_newer_event_between_startup_batches_wins_and_direct_invalidation_stays(self):
        self.graph.sync_from_vault()
        other = RelationshipGraph(db_path=self.db_path, vault_path=self.vault)
        self.addCleanup(other.close)
        calls = []
        def boundary():
            if not calls:
                calls.append(True)
                note = write_note(self.vault, "NoteA.md", [{"target": "NoteB", "type": "requires"}])
                other.refresh_paths({note})
            return False
        result = self.graph.catch_up_from_vault(stop_event=mock.Mock(is_set=boundary), batch_size=1)
        self.assertEqual(result["errors"], [])
        self.assertIn(("NoteA", "NoteB", "requires", "medium"), self.all_rows())
        calls.clear()
        def invalidate():
            if not calls:
                calls.append(True)
                other.remove_orphans([])
            return False
        result = self.graph.catch_up_from_vault(stop_event=mock.Mock(is_set=invalidate), batch_size=1)
        self.assertTrue(result["errors"])
        self.assertEqual(self.snapshot()["state"], "incomplete")
        self.graph.sync_from_vault()
        self.assertEqual(self.snapshot()["state"], "fresh")

    def test_canonical_repair_restores_deleted_and_removes_direct_rows_without_parse(self):
        self.graph.sync_from_vault()
        expected = self.all_rows()
        self.graph.conn.execute("DELETE FROM relationships WHERE source = 'NoteA'")
        self.graph.conn.commit()
        self.graph.add_relationships("Noncanonical", [{"target": "NoteB", "type": "supports"}])
        result = self.graph.sync_from_vault()
        self.assertEqual(result["files_parsed"], 0)
        self.assertEqual(self.all_rows(), expected)
        self.graph.conn.execute("UPDATE metadata SET value = 'future' WHERE key = 'relationship_cache_version'")
        self.graph.conn.commit()
        self.assertEqual(self.snapshot()["state"], "incomplete")
        self.graph.build_from_vault()
        self.assertEqual(self.all_rows(), expected)
        self.assertEqual(self.snapshot()["state"], "fresh")
        self.graph.conn.execute("UPDATE relationship_files SET declarations = 'broken' WHERE path = 'NoteA.md'")
        self.graph.conn.commit()
        self.assertEqual(self.snapshot()["state"], "unavailable")
        self.graph.sync_from_vault()
        self.assertEqual(self.all_rows(), expected)
        self.assertEqual(self.snapshot()["state"], "fresh")


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
        write_note(self.vault, "Archive/Archived.md",
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

    def test_preserves_and_reports_existing_link_to_archived_target(self):
        write_note(self.vault, "ArchivedTarget.md", tags=["archived"])
        write_note(self.vault, "LegacySource.md", [
            {"type": "supports", "target": "ArchivedTarget", "confidence": "high"},
        ])

        result = self.graph.build_from_vault()

        self.assertIn(
            ("LegacySource", "ArchivedTarget", "supports", "high"),
            self.all_rows(),
        )
        self.assertEqual(result["archived_target_links"], [{
            "source": "LegacySource",
            "target": "ArchivedTarget",
            "type": "supports",
            "confidence": "high",
        }])


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

    def test_sync_flags_archived_target_without_removing_edge(self):
        write_note(self.vault, "ArchivedTarget.md", tags=["archived"])
        write_note(self.vault, "LegacySource.md", [
            {"type": "extends", "target": "ArchivedTarget"},
        ])

        stats = self.graph.sync_from_vault()

        self.assertEqual(len(stats["archived_target_links"]), 1)
        self.assertIn(
            ("LegacySource", "ArchivedTarget", "extends", "medium"),
            self.all_rows(),
        )


class TestArchivedTargetPolicy(RelationshipGraphTestBase):
    def setUp(self):
        super().setUp()
        write_note(self.vault, "ArchivedTarget.md", tags=["archived"])

    def test_direct_graph_mutation_blocks_archived_target(self):
        with self.assertLogs(
            "orchestrator.tools.relationship_graph", level="WARNING"
        ) as logs:
            result = self.graph.add_relationships("NewSource", [
                {"type": "supports", "target": "ArchivedTarget"},
                {"type": "supports", "target": "NoteB"},
            ])

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["blocked"], [{
            "source": "NewSource",
            "target": "ArchivedTarget",
            "type": "supports",
        }])
        self.assertNotIn(
            ("NewSource", "ArchivedTarget", "supports", "medium"),
            self.all_rows(),
        )
        self.assertIn(
            ("NewSource", "NoteB", "supports", "medium"),
            self.all_rows(),
        )
        self.assertIn("blocked new relationship", "\n".join(logs.output))

    def test_existing_archived_target_edges_are_reported_not_deleted(self):
        self.graph.conn.execute(
            "INSERT INTO relationships (source, target, type, confidence) "
            "VALUES (?, ?, ?, ?)",
            ("LegacySource", "ArchivedTarget", "qualifies", "low"),
        )
        self.graph.conn.commit()

        report = self.graph.find_archived_target_links()

        self.assertEqual(report, [{
            "source": "LegacySource",
            "target": "ArchivedTarget",
            "type": "qualifies",
            "confidence": "low",
        }])
        self.assertIn(
            ("LegacySource", "ArchivedTarget", "qualifies", "low"),
            self.all_rows(),
        )

    def test_lookup_failure_is_loud_and_fails_open(self):
        real_open = open

        def fail_one(path, *args, **kwargs):
            if str(path).endswith("ArchivedTarget.md"):
                raise PermissionError("fixture denied")
            return real_open(path, *args, **kwargs)

        with self.assertLogs(
            "orchestrator.tools.relationship_graph", level="WARNING"
        ) as logs, mock.patch(
            "orchestrator.tools.relationship_graph.open", side_effect=fail_one,
            create=True,
        ):
            result = self.graph.add_relationships("NewSource", [{
                "type": "supports",
                "target": "ArchivedTarget",
            }])

        self.assertEqual(result["added"], 1)
        self.assertTrue(result["errors"])
        self.assertIn("failed open", "\n".join(logs.output))
        self.assertIn(
            ("NewSource", "ArchivedTarget", "supports", "medium"),
            self.all_rows(),
        )

    def test_unterminated_target_frontmatter_is_loud_and_fails_open(self):
        broken = os.path.join(self.vault, "BrokenTarget.md")
        with open(broken, "w", encoding="utf-8") as stream:
            stream.write("---\ntags: [archived]\n# BrokenTarget\n")

        with self.assertLogs(
            "orchestrator.tools.relationship_graph", level="WARNING"
        ) as logs:
            result = self.graph.add_relationships("NewSource", [{
                "type": "supports",
                "target": "BrokenTarget",
            }])

        self.assertEqual(result["added"], 1)
        self.assertTrue(result["errors"])
        self.assertIn("unterminated YAML frontmatter", "\n".join(logs.output))

    def test_targeted_lookup_does_not_read_unrelated_regular_notes(self):
        unrelated = write_note(self.vault, "Unrelated.md", tags=["archived"])
        real_open = open

        def reject_unrelated(path, *args, **kwargs):
            if os.fspath(path) == unrelated:
                raise AssertionError("unrelated note was parsed")
            return real_open(path, *args, **kwargs)

        with mock.patch(
            "orchestrator.tools.relationship_graph.open",
            side_effect=reject_unrelated,
            create=True,
        ):
            result = self.graph.add_relationships("NewSource", [{
                "type": "supports",
                "target": "NoteB",
            }])

        self.assertEqual(result["added"], 1)

    def test_discovery_does_not_propose_archived_wikilink_target(self):
        source = write_note(
            self.vault,
            "DiscoverySource.md",
            body="Archived [[ArchivedTarget]] supports active [[NoteB]].",
        )

        relationships = discover_relationships(source, self.vault)

        self.assertNotIn("ArchivedTarget", {r["target"] for r in relationships})
        self.assertIn("NoteB", {r["target"] for r in relationships})

    def test_yaml_mutation_blocks_new_but_preserves_existing_archived_edge(self):
        source = write_note(self.vault, "YamlSource.md", [
            {"type": "qualifies", "target": "ArchivedTarget"},
        ])

        modified = update_note_relationships(source, [
            {"type": "supports", "target": "ArchivedTarget"},
            {"type": "supports", "target": "NoteB"},
        ], vault_path=self.vault)

        self.assertTrue(modified)
        with open(source, "r") as fh:
            fm = yaml.safe_load(fh.read().split("---", 2)[1])
        relationships = fm["relationships"]
        self.assertIn(
            {"type": "qualifies", "target": "ArchivedTarget"},
            relationships,
        )
        self.assertNotIn(
            {"type": "supports", "target": "ArchivedTarget"},
            relationships,
        )
        self.assertIn(
            {"type": "supports", "target": "NoteB"},
            relationships,
        )

    def test_exhaustive_audit_recognizes_legacy_engram_claim_identity(self):
        archived_claim = "An archived claim remains inspectable"
        write_note(
            self.vault,
            "Engrams/2024-01-09_archived-claim.md",
            body=engram_body(archived_claim),
            tags=["archived"],
        )

        archived_targets, errors = self.graph.scan_archived_targets(self.vault)

        self.assertEqual(errors, [])
        self.assertIn(archived_claim, archived_targets)

    def test_direct_mutation_blocks_archived_legacy_claim_identity(self):
        archived_claim = "An archived claim cannot receive a new edge"
        write_note(
            self.vault,
            "Engrams/2024-01-11_archived-claim.md",
            body=engram_body(archived_claim),
            tags=["archived"],
        )

        result = self.graph.add_relationships("NewSource", [{
            "type": "supports",
            "target": archived_claim,
        }])

        self.assertEqual(result["added"], 0)
        self.assertEqual(result["blocked"][0]["target"], archived_claim)

    def test_real_title_takes_precedence_over_same_archived_engram_claim(self):
        write_note(self.vault, "Shared Identity.md")
        write_note(
            self.vault,
            "Engrams/2024-01-10_archived-imposter.md",
            body=engram_body("Shared Identity"),
            tags=["archived"],
        )

        result = self.graph.add_relationships("NewSource", [{
            "type": "supports",
            "target": "Shared Identity",
        }])

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["blocked"], [])


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
