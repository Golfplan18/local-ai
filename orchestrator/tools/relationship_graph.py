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

import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
import yaml
from datetime import datetime, timezone
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
EXCLUDED_DIRS = frozenset({"Archive", ".trash"})


# YAML frontmatter is terminated by a line that is exactly '---' (optionally
# trailing whitespace), NOT by the first bare '---' substring. A valid quoted
# scalar may legally contain a literal '---' (e.g. a `supersedes` value that
# quotes another note's delimiter); a substring search truncates the block
# mid-value, yaml.safe_load then raises "found unexpected end of stream", and
# the note silently drops out of the scan. Line-anchor the terminator.
# (Incident 2026-07-02: "Framework — MSI Malcolm Little King Spinner".)
_FRONTMATTER_TERMINATOR = re.compile(r"^---[ \t\r]*$", re.MULTILINE)

_LOG = logging.getLogger(__name__)
_CACHE_VERSION = "1"
_OBSERVATION_LIMIT = (
    "Freshness compares observed file identity, size and timestamps; a change "
    "preserving all observed state needs a file event or an explicit rebuild."
)


def _file_state(path: Path) -> str:
    observed = path.stat()
    if not stat.S_ISREG(observed.st_mode):
        raise OSError(f"not a regular Markdown file: {path}")
    return json.dumps([observed.st_dev, observed.st_ino, observed.st_size,
                       observed.st_mtime_ns, observed.st_ctime_ns])


def _eligible_relative(path: Path, vault: Path) -> str | None:
    try:
        candidate = path.parent.resolve() / path.name
        relative = candidate.relative_to(vault.resolve())
        path.resolve().relative_to(vault.resolve())
    except (ValueError, OSError):
        return None
    if any(part.startswith(".") or part in EXCLUDED_DIRS
           or part == "__pycache__" for part in relative.parts):
        return None
    return relative.as_posix()


def _stat_inventory(vault: Path) -> tuple[dict[str, str], list[str]]:
    """Observe eligible paths without reading canonical Markdown bytes."""
    states: dict[str, str] = {}
    errors: list[str] = []
    if not vault.is_dir():
        return states, ["vault relationship authority is unavailable"]

    def failed(error):
        errors.append(f"canonical relationship directories could not be inspected: {error}")

    for root, dirs, files in os.walk(vault, onerror=failed):
        dirs[:] = [name for name in dirs if not name.startswith(".")
                   and name not in EXCLUDED_DIRS and name != "__pycache__"]
        for name in files:
            path = Path(root, name)
            relative = _eligible_relative(path, vault)
            if not name.endswith(".md") or relative is None:
                continue
            try:
                states[relative] = _file_state(path)
            except OSError as error:
                errors.append(f"canonical relationship note could not be inspected: {error}")
    return states, errors


def invalidate_relationship_coverage(connection, reason="relationship rows require canonical repair"):
    """Invalidate within an existing graph writer transaction, including SQL tools."""
    connection.executemany(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        [("last_update_complete", "0"), ("last_update_reason", reason)])
    connection.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES "
        "('relationship_invalidation', CAST(COALESCE((SELECT value FROM metadata "
        "WHERE key = 'relationship_invalidation'), '0') AS INTEGER) + 1)")


def _valid_cache_entry(path, entry) -> bool:
    try:
        state = json.loads(entry["state"])
        declarations = json.loads(entry["declarations"])
        return (
            isinstance(path, str) and entry["stem"] == Path(path).stem
            and isinstance(state, list) and len(state) == 5
            and all(type(value) is int for value in state)
            and bool(re.fullmatch(r"[a-f0-9]{64}", entry["digest"]))
            and (entry["claim"] is None or isinstance(entry["claim"], str))
            and entry["archived"] in (0, 1)
            and isinstance(declarations, list)
            and all(isinstance(row, list) and len(row) == 3
                    and all(isinstance(value, str) for value in row) for row in declarations)
        )
    except (TypeError, ValueError, KeyError):
        return False


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


def _snapshot_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _markdown_inventory_digest(relative_paths) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(relative_paths):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def read_relationship_snapshot(
    identities,
    *,
    db_path: str | os.PathLike | None = None,
    vault_path: str | os.PathLike | None = None,
) -> dict:
    """Return typed relationship summaries from SQLite opened truly read-only.

    The result distinguishes availability of the compiled rows from evidence
    that they represent the complete, current Markdown authority.  It never
    constructs :class:`RelationshipGraph`, creates paths, switches journal
    mode, initializes schema, or writes bookkeeping.
    """

    wanted = {str(identity).strip() for identity in identities if str(identity).strip()}
    if db_path is None or vault_path is None:
        from orchestrator import runtime_paths as rp
        if db_path is None:
            db_path = Path(rp.DATA_DIR_STR) / "relationship-graph.db"
        if vault_path is None:
            vault_path = rp.vault_dir()
    database = Path(db_path).expanduser().resolve()
    vault = Path(vault_path).expanduser().resolve()
    unavailable = {
        "state": "unavailable",
        "updated_at": None,
        "reason": "relationship snapshot is unavailable",
        "items": {},
        "edges": [],
        "observation_limit": _OBSERVATION_LIMIT,
    }
    try:
        # SQLite may create WAL sidecars even for mode=ro. A settled database
        # without sidecars can be read immutably; refuse that snapshot if a
        # writer starts or checkpoints while it is being read.
        wal = Path(str(database) + "-wal")
        shm = Path(str(database) + "-shm")
        immutable = not wal.exists() and not shm.exists()
        if not immutable and not (wal.exists() and shm.exists()):
            return unavailable
        database_state = _file_state(database)
        connection = sqlite3.connect(
            f"{database.as_uri()}?mode=ro" + ("&immutable=1" if immutable else ""), uri=True,
        )
    except (OSError, sqlite3.Error):
        return unavailable

    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        if not {"relationships", "metadata"}.issubset(tables):
            unavailable["reason"] = "relationship snapshot schema is unavailable"
            return unavailable
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(relationships)")
        }
        if not {"source", "target", "type", "confidence"}.issubset(columns):
            unavailable["reason"] = "relationship snapshot schema is incompatible"
            return unavailable
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        cache_states = None
        if ("relationship_files" in tables
                and metadata.get("relationship_cache_version") == _CACHE_VERSION):
            cache_states = {}
            for row in connection.execute(
                "SELECT path, stem, state, digest, claim, archived, declarations FROM relationship_files"
            ):
                entry = dict(zip(("stem", "state", "digest", "claim", "archived", "declarations"), row[1:]))
                if not _valid_cache_entry(row[0], entry):
                    raise ValueError("invalid relationship file cache")
                cache_states[row[0]] = entry["state"]
        edges = set()
        summaries: dict[str, dict[tuple[str, str, str, str | None], int]] = {
            identity: {} for identity in wanted
        }
        ordered_wanted = sorted(wanted)
        if ordered_wanted:
            placeholders = ", ".join("?" for _ in ordered_wanted)
            for source, target, relation_type, confidence in connection.execute(
                "SELECT source, target, type, confidence FROM relationships "
                f"WHERE source IN ({placeholders})",
                ordered_wanted,
            ):
                edges.add((source, target, str(relation_type), str(confidence or "")))
                relation_type = str(relation_type)
                confidence = str(confidence or "")
                key = (relation_type, "outgoing", confidence, None)
                summaries[source][key] = summaries[source].get(key, 0) + 1
            for source, target, relation_type, confidence in connection.execute(
                "SELECT source, target, type, confidence FROM relationships "
                f"WHERE target IN ({placeholders})",
                ordered_wanted,
            ):
                edges.add((source, target, str(relation_type), str(confidence or "")))
                relation_type = str(relation_type)
                confidence = str(confidence or "")
                inverse = INVERSE_MAP.get(relation_type, relation_type)
                key = (inverse, "incoming", confidence, relation_type)
                summaries[target][key] = summaries[target].get(key, 0) + 1
    except (sqlite3.Error, ValueError):
        unavailable["reason"] = "relationship snapshot could not be read"
        return unavailable
    finally:
        connection.close()

    if immutable:
        try:
            if wal.exists() or shm.exists() or _file_state(database) != database_state:
                unavailable["reason"] = "relationship snapshot changed while being read"
                return unavailable
        except OSError:
            return unavailable

    updated_raw = metadata.get("last_update_at")
    updated_at = _snapshot_timestamp(updated_raw)
    state = "fresh"
    reason = None
    if (
        updated_at is None
        or metadata.get("last_update_complete") != "1"
        or cache_states is None
    ):
        state = "incomplete"
        reason = metadata.get("last_update_reason") or (
            "the latest relationship index update is not proven complete")
    else:
        inventory, inspection_errors = _stat_inventory(vault)
        if inspection_errors:
            state = "incomplete"
            reason = inspection_errors[0]
        elif inventory.keys() != cache_states.keys():
            state = "stale"
            reason = "canonical relationship note inventory changed after the latest complete index update"
        elif inventory != cache_states:
            state = "stale"
            reason = "canonical relationship notes changed after the latest complete index update"

    items = {}
    for identity in sorted(wanted):
        typed = [
            {
                "type": relation_type,
                "direction": direction,
                "confidence": confidence,
                "count": count,
                **({"original_type": original} if original else {}),
            }
            for (relation_type, direction, confidence, original), count
            in sorted(summaries[identity].items())
        ]
        items[identity] = {
            "state": state,
            "updated_at": updated_raw,
            "reason": reason,
            "summaries": typed,
        }
    return {
        "state": state,
        "updated_at": updated_raw,
        "reason": reason,
        "items": items,
        "edges": [dict(zip(("source", "target", "type", "confidence"), edge))
                  for edge in sorted(edges)],
        "observation_limit": _OBSERVATION_LIMIT,
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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS relationship_files (
                path TEXT PRIMARY KEY,
                stem TEXT NOT NULL,
                state TEXT NOT NULL,
                digest TEXT NOT NULL,
                claim TEXT,
                archived INTEGER NOT NULL,
                declarations TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def _stamp_update_metadata(
        self, coverage_started_at: datetime, errors: list[str],
        inventory_digest: str,
    ) -> None:
        """Record one full YAML reconciliation's conservative coverage."""

        complete = not errors
        updated_at = coverage_started_at.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("last_update_at", updated_at),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("last_update_complete", "1" if complete else "0"),
        )
        if complete:
            self.conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("vault_markdown_inventory_sha256", inventory_digest),
            )

    def _mark_update_incomplete(self, reason="relationship rows require canonical repair") -> None:
        """Invalidate completeness inside the caller's current transaction."""
        invalidate_relationship_coverage(self.conn, reason)

    def _walk_vault_md(self, errors: list[str] | None = None):
        """Yield (root, filename) for every vault .md file, applying the
        standard exclusions (hidden dirs, EXCLUDED_DIRS)."""

        def record_walk_error(error: OSError) -> None:
            message = f"{getattr(error, 'filename', None) or self.vault_path}: {error}"
            if errors is not None:
                errors.append(message)
            else:
                _LOG.warning("relationship graph vault traversal failed: %s", message)

        if not os.path.isdir(self.vault_path):
            record_walk_error(OSError("vault relationship authority is unavailable"))
            return
        for root, dirs, files in os.walk(
            self.vault_path, onerror=record_walk_error,
        ):
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in EXCLUDED_DIRS]
            for filename in files:
                if filename.endswith(".md"):
                    yield root, filename

    @staticmethod
    def _parse_frontmatter_text(content: str, filepath: str,
                                errors: list[str]) -> dict:
        """Parse a note's YAML frontmatter, reporting rather than hiding
        malformed or unreadable metadata.

        An empty mapping is also the fail-open result: callers enforcing
        archived-target policy must not mistake a lookup failure for proof
        that the target is archived.
        """
        try:
            if not content.startswith("---"):
                return {}
            end = _frontmatter_end(content)
            if end == -1:
                errors.append(f"{filepath}: unterminated YAML frontmatter")
                return {}
            fm = yaml.safe_load(content[3:end]) or {}
            if not isinstance(fm, dict):
                errors.append(f"{filepath}: YAML frontmatter is not a mapping")
                return {}
            return fm
        except Exception as exc:
            errors.append(f"{filepath}: {exc}")
            return {}

    @staticmethod
    def _relationships_from_frontmatter(fm: dict) -> set[tuple]:
        """Extract normalized relationship triples from parsed YAML."""
        rows = set()
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
        return rows

    @classmethod
    def _parse_relationships_text(cls, content: str, filepath: str,
                                  errors: list[str]) -> set[tuple]:
        """Extract (target, type, confidence) tuples from a note's YAML
        frontmatter (already-read file content). Returns an empty set when
        the note has none.

        All three fields are coerced to str: YAML parses numeric confidences
        (engram similarity scores like 0.861) as floats and bare dates as
        date objects, but the columns have TEXT affinity — comparing what
        YAML yields against what SQLite returns must be type-stable or
        sync_from_vault never converges."""
        fm = cls._parse_frontmatter_text(content, filepath, errors)
        return cls._relationships_from_frontmatter(fm)

    @staticmethod
    def _is_archived_frontmatter(fm: dict) -> bool:
        """Whether an active note carries the controlled ``archived`` tag.

        Archive-directory placement is deliberately not considered here:
        those paths are excluded from the active graph and retain the normal
        missing/orphan behavior.
        """
        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        return isinstance(tags, list) and "archived" in tags

    @classmethod
    def scan_archived_targets(
        cls,
        vault_path: str,
        target_identities: set[str] | None = None,
        *,
        resolve_statement_claims: bool = False,
        known_paths: dict[str, list[str]] | None = None,
    ) -> tuple[set[str], list[str]]:
        """Return active relationship target identities tagged archived.

        Filename stems are the normal graph identity. Engram H1 claims are
        included as compatibility identities for pre-resolution graph rows.
        When ``target_identities`` is provided, ordinary notes are parsed only
        when their filename stem is one of those proposed targets. Canonical
        runtime graph targets are filename stems, so statement-claim fallback
        is opt-in and reserved for explicit compatibility audits. Omitting the
        set retains the exhaustive scan used by audit/report commands.

        Lookup errors are returned and logged loudly; the partial result is
        intentionally used so callers fail open for identities they could not
        inspect rather than blocking all relationship creation.
        """
        requested = (
            {str(identity) for identity in target_identities}
            if target_identities is not None
            else None
        )
        archived_stems: set[str] = set()
        archived_statement_stems: set[str] = set()
        titles: set[str] = set()
        claim_to_stem: dict[str, str] = {}
        errors: list[str] = []

        if not os.path.isdir(vault_path):
            errors.append(f"{vault_path}: vault root is not a directory")

        def record_walk_error(exc: OSError) -> None:
            errors.append(f"{getattr(exc, 'filename', vault_path)}: {exc}")

        entries: list[tuple[str, str, bool]] = []
        if requested is not None and known_paths is not None:
            titles.update(known_paths)
            for title in requested:
                for filepath in known_paths.get(title, []):
                    entries.append((
                        title,
                        filepath,
                        os.path.basename(os.path.dirname(filepath))
                        in STATEMENT_KEYED_DIRS,
                    ))
        else:
            for root, dirs, files in os.walk(vault_path, onerror=record_walk_error):
                dirs[:] = [d for d in dirs if not d.startswith(".")
                           and d not in EXCLUDED_DIRS]
                for filename in files:
                    if not filename.endswith(".md"):
                        continue
                    title = filename[:-3]
                    titles.add(title)
                    filepath = os.path.join(root, filename)
                    statement_keyed = os.path.basename(root) in STATEMENT_KEYED_DIRS
                    entries.append((title, filepath, statement_keyed))

        if requested is None:
            unresolved_claims = None
        elif resolve_statement_claims:
            unresolved_claims = requested - titles
        else:
            unresolved_claims = set()
        for title, filepath, statement_keyed in entries:
            if (
                requested is not None
                and title not in requested
                and not (statement_keyed and unresolved_claims)
            ):
                continue
            try:
                with open(filepath, "r") as fh:
                    content = fh.read()
            except Exception as exc:
                errors.append(f"{filepath}: {exc}")
                continue
            h1 = cls._extract_h1(content) if statement_keyed else None
            if (
                requested is not None
                and title not in requested
                and h1 not in unresolved_claims
            ):
                continue
            fm = cls._parse_frontmatter_text(content, filepath, errors)
            is_archived = cls._is_archived_frontmatter(fm)
            if (requested is None or title in requested) and is_archived:
                archived_stems.add(title)
            if h1 and (requested is None or h1 in unresolved_claims):
                existing = claim_to_stem.get(h1)
                if existing is None or title < existing:
                    claim_to_stem[h1] = title
                if is_archived:
                    archived_statement_stems.add(title)

        archived = set(archived_stems)
        for claim, stem in claim_to_stem.items():
            # Match graph resolution precedence: a real filename title wins
            # over an identically-worded engram claim.
            if claim not in titles and stem in archived_statement_stems:
                archived.add(claim)

        for error in errors:
            _LOG.warning(
                "archived-target lookup failed open; relationships remain "
                "allowed for unresolved identities: %s", error)
        return archived, errors

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

    def _scan_vault_relationships(
        self, errors: list[str]
    ) -> tuple[dict, int, dict, list[dict], str]:
        """Compile cached declarations → ({source_title: {(target, type, confidence)}},
        notes_scanned, resolution_stats). Notes without relationships are
        not in the dict.

        No Markdown is read here. Engram relationships reference other
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
        archived_titles: set[str] = set()
        titles: set[str] = set()
        duplicate_claims = 0
        notes_scanned = 0
        relative_paths: list[str] = []

        for path, entry in self._cached_files().items():
            source_title = entry["stem"]
            titles.add(source_title)
            notes_scanned += 1
            relative_paths.append(path)
            if entry["archived"]:
                archived_titles.add(source_title)
            if Path(path).parent.name in STATEMENT_KEYED_DIRS:
                h1 = entry["claim"]
                if h1:
                    existing = claim_to_stem.get(h1)
                    if existing is None:
                        claim_to_stem[h1] = source_title
                    else:
                        duplicate_claims += 1
                        if source_title < existing:
                            claim_to_stem[h1] = source_title

            rows = {tuple(row) for row in json.loads(entry["declarations"])}
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
        archived_target_links = [
            {
                "source": source,
                "target": target,
                "type": rtype,
                "confidence": confidence,
            }
            for source, rows in desired.items()
            for target, rtype, confidence in rows
            if target in archived_titles
        ]
        resolution = {
            "claims_indexed": len(claim_to_stem),
            "resolved_targets": resolved_targets,
            "duplicate_claims": duplicate_claims,
        }
        archived_target_links.sort(
            key=lambda row: (row["source"], row["target"], row["type"])
        )
        return (
            desired,
            notes_scanned,
            resolution,
            archived_target_links,
            _markdown_inventory_digest(relative_paths),
        )

    def build_from_vault(self) -> dict:
        """
        Full rebuild: scan all vault notes, extract relationships from YAML,
        populate the graph index.

        Returns stats dict.
        """
        return self.catch_up_from_vault(verify_content=True)

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
        return self.catch_up_from_vault()

    def _reconcile_cached_rows(self, *, sources: set[str] | None = None) -> dict:
        """Repair compiled rows in the caller's immediate transaction."""
        errors: list[str] = []
        desired, notes_scanned, resolution, archived_target_links, inventory_digest = (
            self._scan_vault_relationships(errors)
        )

        db_sources = {row[0] for row in self.conn.execute(
            "SELECT DISTINCT source FROM relationships")}
        if sources is not None:
            desired = {source: rows for source, rows in desired.items()
                       if source in sources}
            db_sources &= sources

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
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('notes_scanned', ?)",
            (str(notes_scanned),)
        )
        return {
            "notes_scanned": notes_scanned,
            "sources_in_yaml": len(desired),
            "rows_added": rows_added,
            "rows_removed": rows_removed,
            "sources_removed": sources_removed,
            "resolution": resolution,
            "archived_target_links": archived_target_links,
            "errors": errors
        }

    def _cached_files(self) -> dict[str, dict]:
        columns = ("stem", "state", "digest", "claim", "archived", "declarations")
        entries = {row[0]: dict(zip(columns, row[1:])) for row in self.conn.execute(
            "SELECT path, stem, state, digest, claim, archived, declarations "
            "FROM relationship_files ORDER BY path")}
        # Invalid derivatives are not reusable parses. Canonical repair reads
        # those paths again; an unreadable authority keeps coverage incomplete.
        return {path: entry for path, entry in entries.items()
                if _valid_cache_entry(path, entry)}

    @staticmethod
    def _affected_sources(before, after, selected) -> set[str]:
        identities = set()
        sources = set()
        for records in (before, after):
            for path in selected:
                entry = records.get(path)
                if entry:
                    sources.add(entry["stem"])
                    identities.add(entry["stem"])
                    if Path(path).parent.name in STATEMENT_KEYED_DIRS and entry["claim"]:
                        identities.add(entry["claim"])
        for records in (before, after):
            for entry in records.values():
                if any(row[0] in identities for row in json.loads(entry["declarations"])):
                    sources.add(entry["stem"])
        return sources

    def _failed_refresh(self, error) -> None:
        self.conn.rollback()
        try:
            self._mark_update_incomplete(f"relationship refresh failed: {error}")
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            _LOG.exception("relationship refresh failure could not be recorded")

    def _metadata(self) -> dict:
        return dict(self.conn.execute("SELECT key, value FROM metadata"))

    def _set_metadata(self, **values) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ((key, str(value)) for key, value in values.items()))

    def _refresh_files(self, paths, *, verify_content=False, allow_missing=True) -> dict:
        """Read candidates under writer ordering; retain old parses on errors."""
        cached = self._cached_files()
        reusable = {entry["digest"]: entry for entry in cached.values()}
        errors = []
        parsed = hashed = 0
        missing = []
        for relative in sorted(set(paths)):
            path = Path(self.vault_path, relative)
            if _eligible_relative(path, Path(self.vault_path)) is None:
                # An old entry that has become an escaping symlink is unknown.
                errors.append(f"{relative}: relationship authority is unavailable")
                continue
            try:
                before = _file_state(path)
            except FileNotFoundError:
                if allow_missing:
                    missing.append(relative)
                continue
            except OSError as exc:
                errors.append(f"{relative}: {exc}")
                continue
            old = cached.get(relative)
            if old and old["state"] == before and not verify_content:
                continue
            try:
                with open(path, "rb") as handle:
                    content = handle.read()
                hashed += 1
                digest = hashlib.sha256(content).hexdigest()
                reuse = reusable.get(digest)
                if reuse:
                    entry = dict(reuse)
                else:
                    text = content.decode("utf-8")
                    parse_errors = []
                    fm = self._parse_frontmatter_text(text, relative, parse_errors)
                    parsed += 1
                    if parse_errors:
                        errors.extend(parse_errors)
                        continue
                    entry = {
                        "digest": digest, "claim": self._extract_h1(text),
                        "archived": int(self._is_archived_frontmatter(fm)),
                        "declarations": json.dumps(sorted(self._relationships_from_frontmatter(fm))),
                    }
                    reusable[digest] = entry
                if _file_state(path) != before:
                    errors.append(f"{relative}: changed during relationship refresh")
                    continue
                self.conn.execute(
                    "INSERT OR REPLACE INTO relationship_files "
                    "(path, stem, state, digest, claim, archived, declarations) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (relative, path.stem, before, digest, entry["claim"],
                     entry["archived"], entry["declarations"]))
            except (OSError, UnicodeError) as exc:
                errors.append(f"{relative}: {exc}")
        for relative in missing:
            # Recheck: an event may have recreated the file during this batch.
            try:
                Path(self.vault_path, relative).stat()
            except FileNotFoundError:
                self.conn.execute("DELETE FROM relationship_files WHERE path = ?", (relative,))
            except OSError as exc:
                errors.append(f"{relative}: {exc}")
            else:
                errors.append(f"{relative}: recreated during relationship refresh")
        return {"errors": errors, "files_parsed": parsed, "files_hashed": hashed}

    def refresh_paths(self, paths) -> dict:
        """Apply one finite coalesced event; never certify older incomplete work."""
        vault = Path(self.vault_path).resolve()
        selected = set()
        errors = []
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            metadata = self._metadata()
            if metadata.get("relationship_cache_version") not in (None, _CACHE_VERSION):
                self._mark_update_incomplete("relationship cache format needs canonical repair")
                self.conn.commit()
                return {"errors": ["relationship cache format needs canonical repair"]}
            cached = self._cached_files()
            for raw in paths:
                raw_path = Path(raw)
                path = raw_path.parent.resolve() / raw_path.name
                relative = _eligible_relative(path, vault)
                if relative is None:
                    continue
                if path.suffix == ".md":
                    selected.add(relative)
                else:
                    selected.update(name for name in cached
                                    if relative == "." or name.startswith(relative + "/"))
                    if path.is_dir():
                        subtree, subtree_errors = _stat_inventory(path)
                        errors.extend(subtree_errors)
                        selected.update((path / name).relative_to(vault).as_posix()
                                        for name in subtree)
            result = self._refresh_files(selected, verify_content=True,
                                         allow_missing=not errors)
            errors.extend(result["errors"])
            self._set_metadata(relationship_cache_version=_CACHE_VERSION)
            # Resolve every cached referrer after identity/claim changes. Do
            # not erase unrelated legacy rows before baseline coverage exists.
            sources = self._affected_sources(cached, self._cached_files(), selected)
            result.update(self._reconcile_cached_rows(sources=sources))
            result["errors"] = errors
            if errors:
                self._mark_update_incomplete(errors[0])
            elif metadata.get("last_update_complete") == "1":
                self._set_metadata(last_update_at=datetime.now(timezone.utc).isoformat())
            else:
                self._set_metadata(last_update_complete="0")
            self.conn.commit()
            return result
        except BaseException as exc:
            self._failed_refresh(exc)
            raise

    def catch_up_from_vault(self, stop_event=None, batch_size=128, *, verify_content=False) -> dict:
        """One stat inventory, finite cancellable batches, and a final comparison.

        Each batch observes candidates after acquiring SQLite's writer lock,
        so an older startup inventory cannot overwrite a newer event parse.
        """
        if batch_size < 1:
            raise ValueError("relationship batch size must be positive")
        started = datetime.now(timezone.utc)
        inventory, errors = _stat_inventory(Path(self.vault_path))
        totals = {"files_parsed": 0, "files_hashed": 0, "rows_added": 0,
                  "rows_removed": 0, "sources_removed": 0}
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            metadata = self._metadata()
            if metadata.get("relationship_cache_version") not in (None, _CACHE_VERSION):
                self.conn.execute("DELETE FROM relationship_files")
            cached = self._cached_files()
            invalidation = metadata.get("relationship_invalidation", "0")
            self._set_metadata(relationship_cache_version=_CACHE_VERSION,
                               last_update_complete="0",
                               last_update_reason="relationship catch-up is incomplete")
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        candidates = sorted(set(inventory) | set(cached))
        cancelled = False
        for start in range(0, len(candidates), batch_size):
            if stop_event is not None and stop_event.is_set():
                errors.append("relationship catch-up was cancelled")
                cancelled = True
                break
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                before_batch = self._cached_files()
                selected = candidates[start:start + batch_size]
                result = self._refresh_files(selected,
                                             verify_content=verify_content,
                                             allow_missing=not errors)
                errors.extend(result["errors"])
                for key in ("files_parsed", "files_hashed"):
                    totals[key] += result[key]
                sources = self._affected_sources(before_batch, self._cached_files(), selected)
                result = self._reconcile_cached_rows(sources=sources)
                for key in ("rows_added", "rows_removed", "sources_removed"):
                    totals[key] += result[key]
                self.conn.commit()
            except BaseException as exc:
                self._failed_refresh(exc)
                raise
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            final_inventory, final_errors = _stat_inventory(Path(self.vault_path))
            errors.extend(final_errors)
            states = {path: entry["state"] for path, entry in self._cached_files().items()}
            if states != final_inventory:
                errors.append("canonical relationship state changed during catch-up")
            metadata = self._metadata()
            if metadata.get("relationship_invalidation", "0") != invalidation:
                errors.append(metadata.get("last_update_reason") or "relationship rows invalidated during catch-up")
            # Only complete canonical coverage can remove unbacked direct or
            # legacy rows. On unknown files retain usable old relationships.
            result = self._reconcile_cached_rows(sources=set() if errors else None)
            for key in ("rows_added", "rows_removed", "sources_removed"):
                totals[key] += result[key]
            if errors:
                self._mark_update_incomplete(errors[0])
            else:
                self._stamp_update_metadata(started, [], _markdown_inventory_digest(states))
                self._set_metadata(last_update_reason="", last_sync=started.isoformat())
                if verify_content:
                    self._set_metadata(last_rebuild=started.isoformat())
            self.conn.commit()
            return {**result, **totals, "errors": errors, "cancelled": cancelled,
                    "relationships_indexed": self.conn.execute(
                        "SELECT COUNT(*) FROM relationships").fetchone()[0]}
        except BaseException as exc:
            self._failed_refresh(exc)
            raise

    def add_relationships(self, source: str, relationships: list[dict]) -> dict:
        """Add allowed relationships for a single note.

        New links to active notes carrying the controlled ``archived`` tag
        are blocked. Lookup failures are loud but fail open. Existing graph
        rows are never removed by this mutation path.
        """
        proposed_targets = {str(rel["target"]) for rel in relationships}
        archived_targets, lookup_errors = self.scan_archived_targets(
            self.vault_path,
            proposed_targets,
            resolve_statement_claims=True,
        )
        added = 0
        blocked: list[dict] = []
        errors: list[str] = list(lookup_errors)
        self._mark_update_incomplete()
        for rel in relationships:
            target = str(rel["target"])
            if target in archived_targets:
                blocked.append({
                    "source": source,
                    "target": target,
                    "type": str(rel["type"]),
                })
                _LOG.warning(
                    "blocked new relationship to archived target: %s -> %s (%s)",
                    source, target, rel["type"]
                )
                continue
            try:
                self.conn.execute(
                    "INSERT OR REPLACE INTO relationships (source, target, type, confidence) VALUES (?, ?, ?, ?)",
                    (source, target, str(rel["type"]),
                     str(rel.get("confidence", "medium")))
                )
                added += 1
            except sqlite3.Error as exc:
                message = f"{source} -> {target}: {exc}"
                errors.append(message)
                _LOG.error("relationship graph insert failed: %s", message)
        self.conn.commit()
        return {"added": added, "blocked": blocked, "errors": errors}

    def find_archived_target_links(self) -> list[dict]:
        """Report existing graph edges to archived targets without mutation."""
        archived_targets, _ = self.scan_archived_targets(self.vault_path)
        if not archived_targets:
            return []

        cur = self.conn.cursor()
        cur.execute("DROP TABLE IF EXISTS temp._archived_targets")
        cur.execute(
            "CREATE TEMP TABLE _archived_targets (target TEXT PRIMARY KEY)"
        )
        cur.executemany(
            "INSERT OR IGNORE INTO _archived_targets VALUES (?)",
            ((target,) for target in archived_targets),
        )
        try:
            rows = cur.execute("""
                SELECT source, target, type, confidence FROM relationships
                WHERE target IN (SELECT target FROM _archived_targets)
                ORDER BY source, target, type
            """).fetchall()
        finally:
            cur.execute("DROP TABLE IF EXISTS temp._archived_targets")
        return [
            {
                "source": row[0],
                "target": row[1],
                "type": row[2],
                "confidence": row[3],
            }
            for row in rows
        ]

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
        self._mark_update_incomplete()
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
        print("  archived-links        — Report links to archived targets")
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
        if result['archived_target_links']:
            print("Links to archived targets: "
                  f"{len(result['archived_target_links'])} (preserved)")

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
        if result['archived_target_links']:
            print("Links to archived targets: "
                  f"{len(result['archived_target_links'])} (preserved)")

    elif command == "archived-links":
        links = graph.find_archived_target_links()
        print(json.dumps(links, indent=2))

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
