"""
relationship_graph.py — Compiled Relationship Graph Index

Builds and queries an in-memory graph index from vault YAML frontmatter relationships.
Follows the canonical-to-compiled pattern: YAML frontmatter is the source of truth;
the compiled graph index is regenerated from YAML for fast traversal.

The graph is stored as a SQLite adjacency table for persistence across sessions.
If the index corrupts, rebuild from markdown with --rebuild.

Usage:
    from orchestrator.tools.relationship_graph import RelationshipGraph

    graph = RelationshipGraph()
    graph.build_from_vault()  # Full rebuild from YAML

    # Query
    related = graph.get_relationships("Note Title", types=["supports", "extends"])
    inverse = graph.get_inverse_relationships("Note Title", types=["supports"])
"""

from __future__ import annotations

import os
import re
import sqlite3
import yaml
from pathlib import Path


# Vault folders whose notes use statement-keyed relationship targets:
# engram/atomic notes reference other notes by their claim sentence
# ("Anger impairs reasoning capacity and judgment quality"), not by
# filename stem. The claim IS the note's H1 heading, so at scan time the
# walk builds a claim→stem map from these folders and resolves such
# targets to filename stems — the compiled index is uniformly note-keyed.
# Claims that resolve to no engram are reported as dangling targets.
STATEMENT_KEYED_DIRS = frozenset({"Engrams"})

# Directories excluded from every vault walk (sources, titles, orphan checks).
EXCLUDED_DIRS = frozenset({"Old AI Working Files", ".trash"})


# YAML frontmatter is terminated by a line that is exactly '---' (optionally
# trailing whitespace), NOT by the first bare '---' substring. A valid quoted
# scalar may legally contain a literal '---' (e.g. a `supersedes` value that
# quotes another note's delimiter); a substring search truncates the block
# mid-value, yaml.safe_load then raises "found unexpected end of stream", and
# the note silently drops out of the scan. Line-anchor the terminator.
# (Incident 2026-07-02: "Framework — MSI Malcolm Little King Spinner".)
_FRONTMATTER_TERMINATOR = re.compile(r"^---[ \t\r]*$", re.MULTILINE)


def _frontmatter_end(content: str) -> int:
    """Index of the closing frontmatter delimiter line for content that starts
    with '---', or -1 when there is no closing delimiter line. Line-anchored so
    a literal '---' inside a quoted scalar can't truncate the block early."""
    m = _FRONTMATTER_TERMINATOR.search(content, 3)
    return m.start() if m else -1


# Inverse relationship lookup
INVERSE_MAP = {
    "supports": "is-supported-by",
    "contradicts": "contradicted-by",
    "qualifies": "is-qualified-by",
    "extends": "is-extended-by",
    "supersedes": "is-superseded-by",
    "analogous-to": "analogous-to",
    "derived-from": "produces-derivative",
    "enables": "is-enabled-by",
    "requires": "is-required-by",
    "produces": "is-produced-by",
    "precedes": "follows",
    "parent": "child",
    "child": "parent",
}


class RelationshipGraph:
    """In-memory + SQLite relationship graph built from vault YAML."""

    def __init__(self, db_path: str = None, vault_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser("~/ora/data/relationship-graph.db")
        if vault_path is None:
            vault_path = os.path.expanduser("~/Documents/vault")

        self.db_path = db_path
        self.vault_path = vault_path

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with schema."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                confidence TEXT NOT NULL DEFAULT 'medium',
                UNIQUE(source, target, type)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source ON relationships(source)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_target ON relationships(target)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_type ON relationships(type)
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.conn.commit()

    def _walk_vault_md(self):
        """Yield (root, filename) for every vault .md file, applying the
        standard exclusions (hidden dirs, EXCLUDED_DIRS)."""
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in EXCLUDED_DIRS]
            for filename in files:
                if filename.endswith(".md"):
                    yield root, filename

    @staticmethod
    def _parse_relationships_text(content: str, filepath: str,
                                  errors: list[str]) -> set[tuple]:
        """Extract (target, type, confidence) tuples from a note's YAML
        frontmatter (already-read file content). Returns an empty set when
        the note has none.

        All three fields are coerced to str: YAML parses numeric confidences
        (engram similarity scores like 0.861) as floats and bare dates as
        date objects, but the columns have TEXT affinity — comparing what
        YAML yields against what SQLite returns must be type-stable or
        sync_from_vault never converges."""
        rows = set()
        try:
            if not content.startswith("---"):
                return rows
            end = _frontmatter_end(content)
            if end == -1:
                return rows
            fm = yaml.safe_load(content[3:end]) or {}

            relationships = fm.get("relationships", [])
            if not relationships or not isinstance(relationships, list):
                return rows

            for rel in relationships:
                if not isinstance(rel, dict):
                    continue
                rtype = rel.get("type", "")
                target = rel.get("target", "")
                confidence = rel.get("confidence", "medium")
                if rtype and target:
                    rows.add((str(target), str(rtype), str(confidence)))
        except Exception as e:
            errors.append(f"{filepath}: {e}")
        return rows

    @staticmethod
    def _extract_h1(content: str) -> str | None:
        """First H1 heading of a note, skipping the YAML frontmatter block
        (whose comment lines also start with '#'). For engrams the H1 IS the
        claim sentence — the key other engrams' relationships target."""
        body_start = 0
        if content.startswith("---"):
            end = _frontmatter_end(content)
            if end != -1:
                body_start = content.find("\n", end)
                if body_start == -1:
                    return None
        for line in content[body_start:].splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    _CONF_RANK = {"high": 3, "medium": 2, "low": 1}

    @classmethod
    def _better_confidence(cls, a: str, b: str) -> str:
        """Deterministically resolve two confidence values declared for the
        same (source, target, type) key: higher rank wins, lexicographic
        tiebreak for values outside the high/medium/low scale. Without a
        deterministic rule the stored value flip-flops between runs (set
        iteration order is hash-randomized) and sync never converges."""
        return a if (cls._CONF_RANK.get(a, 0), a) >= (cls._CONF_RANK.get(b, 0), b) else b

    def _scan_vault_relationships(self, errors: list[str]) -> tuple[dict, int, dict]:
        """One vault pass → ({source_title: {(target, type, confidence)}},
        notes_scanned, resolution_stats). Notes without relationships are
        not in the dict.

        Claim-target resolution: engram relationships reference other
        engrams by claim sentence (the target engram's H1), not by filename.
        The walk collects a claim→filename-stem map from STATEMENT_KEYED_DIRS
        notes; targets are then resolved to stems so the compiled index is
        uniformly note-keyed (traversal, inverse lookups, and orphan checks
        all key on filename stems). Precedence: a target that is already a
        vault note title stays as-is; only otherwise is the claim map
        consulted. Unresolved claims are kept verbatim (and will surface as
        dangling targets in find_orphan_targets). Duplicate H1s resolve to
        the lexicographically smallest stem — date-prefixed engram names
        make that the earliest extraction — so resolution is deterministic.

        Duplicate (target, type) declarations — within one note, across
        same-stem files, or created by resolution itself (a claim target and
        its stem declared side by side) — collapse to a single triple via
        _better_confidence, matching the UNIQUE(source, target, type)
        constraint."""
        raw: list[tuple[str, set[tuple]]] = []
        claim_to_stem: dict[str, str] = {}
        titles: set[str] = set()
        duplicate_claims = 0
        notes_scanned = 0

        for root, filename in self._walk_vault_md():
            source_title = filename[:-3]
            titles.add(source_title)
            notes_scanned += 1
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r") as f:
                    content = f.read()
            except Exception as e:
                errors.append(f"{filepath}: {e}")
                continue

            if os.path.basename(root) in STATEMENT_KEYED_DIRS:
                h1 = self._extract_h1(content)
                if h1:
                    existing = claim_to_stem.get(h1)
                    if existing is None:
                        claim_to_stem[h1] = source_title
                    else:
                        duplicate_claims += 1
                        if source_title < existing:
                            claim_to_stem[h1] = source_title

            rows = self._parse_relationships_text(content, filepath, errors)
            if rows:
                raw.append((source_title, rows))

        # Resolution pass — needs the complete claim map and title set,
        # so it runs after the walk.
        desired_kv: dict[str, dict[tuple, str]] = {}
        resolved_targets = 0
        for source_title, rows in raw:
            kv = desired_kv.setdefault(source_title, {})
            for target, rtype, confidence in rows:
                if target not in titles:
                    stem = claim_to_stem.get(target)
                    if stem is not None:
                        target = stem
                        resolved_targets += 1
                key = (target, rtype)
                if key in kv:
                    kv[key] = self._better_confidence(kv[key], confidence)
                else:
                    kv[key] = confidence
        desired = {
            source: {(t, ty, c) for (t, ty), c in kv.items()}
            for source, kv in desired_kv.items()
        }
        resolution = {
            "claims_indexed": len(claim_to_stem),
            "resolved_targets": resolved_targets,
            "duplicate_claims": duplicate_claims,
        }
        return desired, notes_scanned, resolution

    def build_from_vault(self) -> dict:
        """
        Full rebuild: scan all vault notes, extract relationships from YAML,
        populate the graph index.

        Returns stats dict.
        """
        # Clear existing data
        self.conn.execute("DELETE FROM relationships")

        errors: list[str] = []
        desired, notes_scanned, resolution = self._scan_vault_relationships(errors)

        relationships_indexed = 0
        for source_title, rows in desired.items():
            for target, rtype, confidence in rows:
                try:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO relationships (source, target, type, confidence) VALUES (?, ?, ?, ?)",
                        (source_title, target, rtype, confidence)
                    )
                    relationships_indexed += 1
                except sqlite3.Error as e:
                    errors.append(f"{source_title}: {e}")

        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_rebuild', datetime('now'))"
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('notes_scanned', ?)",
            (str(notes_scanned),)
        )
        self.conn.commit()

        return {
            "notes_scanned": notes_scanned,
            "relationships_indexed": relationships_indexed,
            "resolution": resolution,
            "errors": errors
        }

    def sync_from_vault(self) -> dict:
        """
        Incremental reconcile: make the relationships table match current
        vault YAML by writing only the differences. Unlike build_from_vault
        (which deletes every row and re-inserts ~all of them — heavy write
        churn on a large DB even when nothing changed), this adds rows that
        are new in YAML, removes rows no longer backed by any live note's
        YAML, and updates rows whose confidence changed. Safe to run on a
        schedule.

        Returns stats dict.
        """
        errors: list[str] = []
        desired, notes_scanned, resolution = self._scan_vault_relationships(errors)

        db_sources = {row[0] for row in self.conn.execute(
            "SELECT DISTINCT source FROM relationships")}

        rows_added = 0
        rows_removed = 0
        sources_removed = 0

        for source, want in desired.items():
            current = {(r[0], r[1], r[2]) for r in self.conn.execute(
                "SELECT target, type, confidence FROM relationships WHERE source = ?",
                (source,))}
            if want == current:
                continue
            # UNIQUE(source, target, type) — a confidence-only change shows
            # up in both diffs; INSERT OR REPLACE applies it, so only delete
            # rows whose (target, type) key is gone from YAML entirely.
            want_keys = {(t, ty) for t, ty, _ in want}
            for target, rtype, confidence in want - current:
                self.conn.execute(
                    "INSERT OR REPLACE INTO relationships (source, target, type, confidence) VALUES (?, ?, ?, ?)",
                    (source, target, rtype, confidence))
                rows_added += 1
            for target, rtype, confidence in current - want:
                if (target, rtype) in want_keys:
                    continue
                self.conn.execute(
                    "DELETE FROM relationships WHERE source = ? AND target = ? AND type = ?",
                    (source, target, rtype))
                rows_removed += 1

        # Sources present in the DB but absent from YAML: the note was
        # deleted, or its YAML no longer declares any relationships.
        for source in db_sources - set(desired):
            cur = self.conn.execute(
                "DELETE FROM relationships WHERE source = ?", (source,))
            rows_removed += cur.rowcount
            sources_removed += 1

        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_sync', datetime('now'))"
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('notes_scanned', ?)",
            (str(notes_scanned),)
        )
        self.conn.commit()

        return {
            "notes_scanned": notes_scanned,
            "sources_in_yaml": len(desired),
            "rows_added": rows_added,
            "rows_removed": rows_removed,
            "sources_removed": sources_removed,
            "resolution": resolution,
            "errors": errors
        }

    def add_relationships(self, source: str, relationships: list[dict]):
        """Add relationships for a single note (incremental update)."""
        for rel in relationships:
            try:
                self.conn.execute(
                    "INSERT OR REPLACE INTO relationships (source, target, type, confidence) VALUES (?, ?, ?, ?)",
                    (source, str(rel["target"]), str(rel["type"]),
                     str(rel.get("confidence", "medium")))
                )
            except sqlite3.Error:
                pass
        self.conn.commit()

    def get_relationships(self, note_title: str, types: list[str] = None,
                          confidence_min: str = None) -> list[dict]:
        """
        Get all outgoing relationships from a note.
        Optionally filter by relationship types and minimum confidence.
        """
        query = "SELECT target, type, confidence FROM relationships WHERE source = ?"
        params = [note_title]

        if types:
            placeholders = ",".join("?" * len(types))
            query += f" AND type IN ({placeholders})"
            params.extend(types)

        if confidence_min:
            conf_order = {"high": 3, "medium": 2, "low": 1}
            min_val = conf_order.get(confidence_min, 0)
            confs = [c for c, v in conf_order.items() if v >= min_val]
            placeholders = ",".join("?" * len(confs))
            query += f" AND confidence IN ({placeholders})"
            params.extend(confs)

        cursor = self.conn.execute(query, params)
        return [{"target": row[0], "type": row[1], "confidence": row[2]}
                for row in cursor.fetchall()]

    def get_inverse_relationships(self, note_title: str, types: list[str] = None) -> list[dict]:
        """
        Get all notes that have relationships pointing TO this note.
        Returns inverse-typed relationships (e.g., if A supports B, returns
        {source: A, type: is-supported-by} when querying for B).
        """
        query = "SELECT source, type, confidence FROM relationships WHERE target = ?"
        params = [note_title]

        if types:
            placeholders = ",".join("?" * len(types))
            query += f" AND type IN ({placeholders})"
            params.extend(types)

        cursor = self.conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            inverse_type = INVERSE_MAP.get(row[1], f"inverse-{row[1]}")
            results.append({
                "source": row[0],
                "type": inverse_type,
                "original_type": row[1],
                "confidence": row[2]
            })
        return results

    def get_connected(self, note_title: str, depth: int = 1,
                      types: list[str] = None) -> list[dict]:
        """
        Get all notes connected to this note up to N hops.
        Follows both outgoing and incoming (inverse) relationships.
        """
        visited = set()
        results = []

        def traverse(title, current_depth):
            if current_depth > depth or title in visited:
                return
            visited.add(title)

            # Outgoing
            for rel in self.get_relationships(title, types=types):
                if rel["target"] not in visited:
                    results.append({
                        "note": rel["target"],
                        "relationship": rel["type"],
                        "direction": "outgoing",
                        "confidence": rel["confidence"],
                        "depth": current_depth
                    })
                    traverse(rel["target"], current_depth + 1)

            # Incoming (inverse)
            for rel in self.get_inverse_relationships(title, types=types):
                if rel["source"] not in visited:
                    results.append({
                        "note": rel["source"],
                        "relationship": rel["type"],
                        "direction": "incoming",
                        "confidence": rel["confidence"],
                        "depth": current_depth
                    })
                    traverse(rel["source"], current_depth + 1)

        traverse(note_title, 1)
        return results

    def find_orphan_targets(self) -> list[dict]:
        """
        Find relationship targets that resolve to nothing in the vault.
        Used by the orphan cleanup maintenance task.

        A target is valid if it is a vault note's filename stem OR a current
        engram claim (the H1 of a STATEMENT_KEYED_DIRS note) — the latter
        covers both rows the sync hasn't resolved to stems yet and YAML
        claim references awaiting resolution. Everything else is a dangling
        reference: a deleted/renamed note, or a claim whose engram no longer
        exists.
        """
        valid_titles = set()
        valid_claims = set()
        for root, f in self._walk_vault_md():
            title = f[:-3]
            valid_titles.add(title)
            if os.path.basename(root) in STATEMENT_KEYED_DIRS:
                try:
                    with open(os.path.join(root, f), "r") as fh:
                        h1 = self._extract_h1(fh.read())
                    if h1:
                        valid_claims.add(h1)
                except Exception:
                    pass

        cur = self.conn.cursor()
        cur.execute("DROP TABLE IF EXISTS temp._valid_targets")
        cur.execute("CREATE TEMP TABLE _valid_targets (target TEXT PRIMARY KEY)")
        cur.executemany("INSERT OR IGNORE INTO _valid_targets VALUES (?)",
                        ((t,) for t in valid_titles))
        cur.executemany("INSERT OR IGNORE INTO _valid_targets VALUES (?)",
                        ((c,) for c in valid_claims))

        try:
            rows = cur.execute("""
                SELECT DISTINCT source, target, type FROM relationships
                WHERE target NOT IN (SELECT target FROM _valid_targets)
            """).fetchall()
        finally:
            cur.execute("DROP TABLE IF EXISTS temp._valid_targets")

        return [{"source": r[0], "target": r[1], "type": r[2]} for r in rows]

    def remove_orphans(self, orphans: list[dict] | None = None) -> int:
        """
        Remove relationships pointing to non-existent notes. Returns count removed.

        Pass a precomputed find_orphan_targets() result to avoid recomputing
        the vault walk; with no argument, computes it internally.

        Note: a row that is still declared in a live note's YAML will be
        re-created by the next sync/rebuild (the vault is canonical) — durable
        removal requires fixing the YAML.
        """
        if orphans is None:
            orphans = self.find_orphan_targets()
        self.conn.executemany(
            "DELETE FROM relationships WHERE source = ? AND target = ? AND type = ?",
            ((o["source"], o["target"], o["type"]) for o in orphans)
        )
        self.conn.commit()
        return len(orphans)

    def stats(self) -> dict:
        """Get graph statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        by_type = {}
        for row in self.conn.execute("SELECT type, COUNT(*) FROM relationships GROUP BY type"):
            by_type[row[0]] = row[1]
        by_confidence = {}
        for row in self.conn.execute("SELECT confidence, COUNT(*) FROM relationships GROUP BY confidence"):
            by_confidence[row[0]] = row[1]
        unique_sources = self.conn.execute("SELECT COUNT(DISTINCT source) FROM relationships").fetchone()[0]
        unique_targets = self.conn.execute("SELECT COUNT(DISTINCT target) FROM relationships").fetchone()[0]

        last_rebuild = self.conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_rebuild'"
        ).fetchone()
        last_sync = self.conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_sync'"
        ).fetchone()

        return {
            "total_relationships": total,
            "by_type": by_type,
            "by_confidence": by_confidence,
            "unique_sources": unique_sources,
            "unique_targets": unique_targets,
            "last_rebuild": last_rebuild[0] if last_rebuild else None,
            "last_sync": last_sync[0] if last_sync else None
        }

    def close(self):
        """Close the database connection."""
        self.conn.close()


if __name__ == "__main__":
    import sys
    import json

    graph = RelationshipGraph()

    if len(sys.argv) < 2:
        print("Usage: relationship_graph.py <command> [args]")
        print("Commands:")
        print("  rebuild              — Full rebuild from vault YAML")
        print("  sync                 — Incremental reconcile with vault YAML (diff-only writes)")
        print("  query <note_title>   — Show relationships for a note")
        print("  connected <title> [depth] — Show connected notes")
        print("  orphans              — Find orphan targets")
        print("  cleanup              — Remove orphan relationships")
        print("  stats                — Show graph statistics")
        sys.exit(1)

    command = sys.argv[1]

    if command == "rebuild":
        print("Rebuilding relationship graph from vault YAML...")
        result = graph.build_from_vault()
        print(f"Notes scanned: {result['notes_scanned']}")
        print(f"Relationships indexed: {result['relationships_indexed']}")
        res = result['resolution']
        print(f"Claim targets resolved to stems: {res['resolved_targets']} "
              f"({res['claims_indexed']} claims indexed, "
              f"{res['duplicate_claims']} duplicate claims)")
        if result['errors']:
            print(f"Errors: {len(result['errors'])}")
            for err in result['errors'][:10]:
                print(f"  {err}")

    elif command == "sync":
        print("Syncing relationship graph with vault YAML (incremental)...")
        result = graph.sync_from_vault()
        print(f"Notes scanned: {result['notes_scanned']}")
        print(f"Rows added: {result['rows_added']}")
        print(f"Rows removed: {result['rows_removed']} "
              f"(of which {result['sources_removed']} whole sources)")
        res = result['resolution']
        print(f"Claim targets resolved to stems: {res['resolved_targets']} "
              f"({res['claims_indexed']} claims indexed, "
              f"{res['duplicate_claims']} duplicate claims)")
        if result['errors']:
            print(f"Errors: {len(result['errors'])}")
            for err in result['errors'][:10]:
                print(f"  {err}")

    elif command == "query":
        if len(sys.argv) < 3:
            print("Usage: relationship_graph.py query <note_title>")
            sys.exit(1)
        title = sys.argv[2]
        rels = graph.get_relationships(title)
        inv = graph.get_inverse_relationships(title)
        print(f"Outgoing relationships from '{title}':")
        for r in rels:
            print(f"  → {r['type']} → \"{r['target']}\" ({r['confidence']})")
        print(f"\nIncoming relationships to '{title}':")
        for r in inv:
            print(f"  ← {r['type']} ← \"{r['source']}\" ({r['confidence']})")

    elif command == "connected":
        if len(sys.argv) < 3:
            print("Usage: relationship_graph.py connected <note_title> [depth]")
            sys.exit(1)
        title = sys.argv[2]
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        connected = graph.get_connected(title, depth=depth)
        print(f"Notes connected to '{title}' (depth {depth}):")
        for c in connected:
            direction = "→" if c["direction"] == "outgoing" else "←"
            print(f"  {direction} {c['relationship']} {direction} \"{c['note']}\" "
                  f"({c['confidence']}, depth {c['depth']})")

    elif command == "orphans":
        orphans = graph.find_orphan_targets()
        if orphans:
            print(f"Found {len(orphans)} orphan relationship targets:")
            for o in orphans:
                print(f"  {o['source']} → {o['type']} → \"{o['target']}\" (missing)")
        else:
            print("No orphan targets found.")

    elif command == "cleanup":
        removed = graph.remove_orphans()
        print(f"Removed {removed} orphan relationships.")

    elif command == "stats":
        s = graph.stats()
        print(f"Total relationships: {s['total_relationships']}")
        print(f"Unique sources: {s['unique_sources']}")
        print(f"Unique targets: {s['unique_targets']}")
        print(f"Last rebuild: {s['last_rebuild']}")
        print(f"Last sync: {s['last_sync']}")
        print("By type:")
        for t, c in sorted(s['by_type'].items()):
            print(f"  {t}: {c}")
        print("By confidence:")
        for conf, c in sorted(s['by_confidence'].items()):
            print(f"  {conf}: {c}")

    graph.close()
