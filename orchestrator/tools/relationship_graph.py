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

    def build_from_vault(self) -> dict:
        """
        Full rebuild: scan all vault notes, extract relationships from YAML,
        populate the graph index.

        Returns stats dict.
        """
        # Clear existing data
        self.conn.execute("DELETE FROM relationships")

        notes_scanned = 0
        relationships_indexed = 0
        errors = []

        for root, dirs, files in os.walk(self.vault_path):
            # Skip hidden directories and non-content directories
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d != "Old AI Working Files"
                       and d != ".trash"]
            for filename in files:
                if not filename.endswith(".md"):
                    continue

                filepath = os.path.join(root, filename)
                source_title = filename[:-3]  # Remove .md
                notes_scanned += 1

                try:
                    with open(filepath, "r") as f:
                        content = f.read()

                    # Parse YAML frontmatter
                    if not content.startswith("---"):
                        continue
                    end = content.find("---", 3)
                    if end == -1:
                        continue
                    fm = yaml.safe_load(content[3:end]) or {}

                    relationships = fm.get("relationships", [])
                    if not relationships or not isinstance(relationships, list):
                        continue

                    for rel in relationships:
                        if not isinstance(rel, dict):
                            continue
                        rtype = rel.get("type", "")
                        target = rel.get("target", "")
                        confidence = rel.get("confidence", "medium")

                        if not rtype or not target:
                            continue

                        try:
                            self.conn.execute(
                                "INSERT OR REPLACE INTO relationships (source, target, type, confidence) VALUES (?, ?, ?, ?)",
                                (source_title, target, rtype, confidence)
                            )
                            relationships_indexed += 1
                        except sqlite3.Error as e:
                            errors.append(f"{source_title}: {e}")

                except Exception as e:
                    errors.append(f"{filepath}: {e}")

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
            "errors": errors
        }

    def add_relationships(self, source: str, relationships: list[dict]):
        """Add relationships for a single note (incremental update)."""
        for rel in relationships:
            try:
                self.conn.execute(
                    "INSERT OR REPLACE INTO relationships (source, target, type, confidence) VALUES (?, ?, ?, ?)",
                    (source, rel["target"], rel["type"], rel.get("confidence", "medium"))
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
        Find relationship targets that don't correspond to existing vault files.
        Used by the orphan cleanup maintenance task.
        """
        # Get all valid note titles
        valid_titles = set()
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d != "Old AI Working Files"]
            for f in files:
                if f.endswith(".md"):
                    valid_titles.add(f[:-3])

        cursor = self.conn.execute(
            "SELECT DISTINCT source, target, type FROM relationships"
        )
        orphans = []
        for row in cursor.fetchall():
            if row[1] not in valid_titles:
                orphans.append({
                    "source": row[0],
                    "target": row[1],
                    "type": row[2]
                })
        return orphans

    def remove_orphans(self) -> int:
        """Remove relationships pointing to non-existent notes. Returns count removed."""
        orphans = self.find_orphan_targets()
        for orphan in orphans:
            self.conn.execute(
                "DELETE FROM relationships WHERE source = ? AND target = ? AND type = ?",
                (orphan["source"], orphan["target"], orphan["type"])
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

        return {
            "total_relationships": total,
            "by_type": by_type,
            "by_confidence": by_confidence,
            "unique_sources": unique_sources,
            "unique_targets": unique_targets,
            "last_rebuild": last_rebuild[0] if last_rebuild else None
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
        print("By type:")
        for t, c in sorted(s['by_type'].items()):
            print(f"  {t}: {c}")
        print("By confidence:")
        for conf, c in sorted(s['by_confidence'].items()):
            print(f"  {conf}: {c}")

    graph.close()
