#!/usr/bin/env python3
"""Quarantine the test-era thin runtime engrams with paired index cleanup.

Dry-run is the default. ``--apply`` moves only notes matching the exact
three-line body emitted by the retired deterministic Pass-B template, removes
their single-record knowledge embeddings, and removes compiled relationship
rows where the quarantined filename stem is either source or target.

The broader ``source_platform: ora-local`` marker is deliberately insufficient:
it is also carried by a small set of rich historical extractions that this
cleanup must preserve.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


ORA_HOME = Path(os.environ.get("ORA_HOME") or "~/ora").expanduser().resolve()
if str(ORA_HOME) not in sys.path:
    sys.path.insert(0, str(ORA_HOME))

from orchestrator import runtime_paths as _rp  # noqa: E402


_SOURCE_LINE = re.compile(r"^- Source: extracted from session [0-9a-f]{6}$")
_ORA_LOCAL_LINE = re.compile(
    r"^source_platform:[ \t]*ora-local[ \t]*$", re.MULTILINE
)


def _frontmatter_and_body(path: Path, text: str | None = None) -> tuple[dict, str]:
    text = text if text is not None else path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError(f"unterminated frontmatter: {path}")
    parsed = yaml.safe_load(text[4:end]) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"frontmatter is not a mapping: {path}")
    return parsed, text[end + 4:].lstrip("\n")


def is_thin_runtime_engram(path: Path) -> bool:
    """Exact retired-template signature; rich ora-local notes return False."""
    try:
        text = path.read_text(encoding="utf-8")
        if not _ORA_LOCAL_LINE.search(text):
            return False
        frontmatter, body = _frontmatter_and_body(path, text)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        print(f"[engram-quarantine] candidate read failed open: {exc}", file=sys.stderr)
        return False
    if frontmatter.get("source_platform") != "ora-local":
        return False
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) != 3 or not lines[0].startswith("# "):
        return False
    title = lines[0][2:].strip()
    return lines[1] == f"- {title}" and bool(_SOURCE_LINE.fullmatch(lines[2]))


def discover_candidates(engrams_dir: Path) -> list[Path]:
    paths: list[Path]
    rg = shutil.which("rg")
    if rg:
        try:
            completed = subprocess.run(
                [
                    rg, "-l", "--null", "--glob", "*.md",
                    r"^source_platform:[ \t]*ora-local[ \t]*$",
                    str(engrams_dir),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if completed.returncode not in (0, 1):
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    completed.args,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )
            paths = [
                Path(raw.decode("utf-8")).resolve()
                for raw in completed.stdout.split(b"\0")
                if raw
            ]
        except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
            print(
                f"[engram-quarantine] rg prefilter failed; falling back to "
                f"filesystem scan: {exc}",
                file=sys.stderr,
            )
            paths = list(engrams_dir.glob("*.md"))
    else:
        paths = list(engrams_dir.glob("*.md"))
    root = engrams_dir.resolve()
    candidates = []
    for path in paths:
        lexical = path.absolute()
        if lexical.is_symlink():
            print(
                f"[engram-quarantine] symlink candidate ignored: {lexical}",
                file=sys.stderr,
            )
            continue
        try:
            resolved = lexical.resolve(strict=True)
            contained = os.path.commonpath([str(root), str(resolved)]) == str(root)
        except (OSError, ValueError):
            contained = False
        if not contained or resolved.parent != root or not resolved.is_file():
            continue
        if is_thin_runtime_engram(resolved):
            candidates.append(resolved)
    return sorted(candidates)


def _delete_chroma_records(paths: list[Path], chromadb_path: Path) -> dict:
    from orchestrator.tools.knowledge_index import get_knowledge_collection

    collection = get_knowledge_collection(chromadb_path)
    ids = [str(path) for path in paths]
    found = 0
    deleted = 0
    missing = 0
    batch_size = 250
    for start in range(0, len(ids), batch_size):
        batch = ids[start:start + batch_size]
        result = collection.get(ids=batch, include=[])
        present = list(result.get("ids") or [])
        found += len(present)
        missing += len(batch) - len(present)
        if present:
            collection.delete(ids=present)
            deleted += len(present)
    return {"found": found, "deleted": deleted, "missing": missing}


def _delete_graph_rows(titles: list[str], graph_db: Path) -> dict:
    from orchestrator.tools.relationship_graph import invalidate_relationship_coverage

    connection = sqlite3.connect(graph_db)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TEMP TABLE quarantine_titles (title TEXT PRIMARY KEY)"
        )
        connection.executemany(
            "INSERT OR IGNORE INTO quarantine_titles VALUES (?)",
            ((title,) for title in titles),
        )
        predicate = (
            "source IN (SELECT title FROM quarantine_titles) OR "
            "target IN (SELECT title FROM quarantine_titles)"
        )
        before = connection.execute(
            f"SELECT COUNT(*) FROM relationships WHERE {predicate}"
        ).fetchone()[0]
        cursor = connection.execute(
            f"DELETE FROM relationships WHERE {predicate}"
        )
        invalidate_relationship_coverage(connection, "quarantine graph cleanup requires canonical repair")
        connection.commit()
        return {"matched": before, "deleted": cursor.rowcount}
    finally:
        connection.close()


def _preflight_indexes(chromadb_path: Path, graph_db: Path) -> None:
    """Refuse physical moves unless both paired stores are writable/openable."""
    from orchestrator.tools.knowledge_index import get_knowledge_collection

    collection = get_knowledge_collection(chromadb_path)
    collection.count()
    if not graph_db.is_file():
        raise FileNotFoundError(f"relationship graph database not found: {graph_db}")
    uri = f"file:{graph_db}?mode=rw"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("SELECT 1 FROM relationships LIMIT 1").fetchone()
    finally:
        connection.close()


def _move_with_rollback(paths: list[Path], quarantine_dir: Path) -> list[Path]:
    archive_root = quarantine_dir.parent
    if archive_root.is_symlink() or quarantine_dir.is_symlink():
        raise ValueError(f"refusing symlinked quarantine destination: {quarantine_dir}")
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_resolved = archive_root.resolve(strict=True)
    if quarantine_dir.exists():
        quarantine_resolved = quarantine_dir.resolve(strict=True)
        if quarantine_resolved.parent != archive_resolved:
            raise ValueError(f"quarantine destination escaped Archive: {quarantine_dir}")
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    destinations = [quarantine_dir / path.name for path in paths]
    collisions = [str(path) for path in destinations if path.exists()]
    if collisions:
        raise FileExistsError(
            f"quarantine destination already contains {len(collisions)} candidates; "
            f"first: {collisions[0]}"
        )
    moved: list[tuple[Path, Path]] = []
    try:
        for source, destination in zip(paths, destinations):
            source.rename(destination)
            moved.append((source, destination))
    except Exception:
        for source, destination in reversed(moved):
            destination.rename(source)
        raise
    return destinations


def _write_manifest(path: Path | None, result: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def execute(
    *,
    vault_root: Path,
    chromadb_path: Path,
    graph_db: Path,
    apply: bool,
    expected_count: int | None,
    manifest_path: Path | None = None,
) -> dict:
    vault_root = vault_root.expanduser().resolve()
    engrams_dir = vault_root / "Engrams"
    quarantine_dir = vault_root / "Archive" / "Test-era Ora-local Engrams"
    archive_root = quarantine_dir.parent
    if archive_root.is_symlink() or quarantine_dir.is_symlink():
        raise ValueError(f"refusing symlinked quarantine destination: {quarantine_dir}")
    if archive_root.exists():
        archive_resolved = archive_root.resolve(strict=True)
        if os.path.commonpath([str(vault_root), str(archive_resolved)]) != str(vault_root):
            raise ValueError(f"Archive root escaped vault: {archive_root}")
    if apply and expected_count is None:
        raise ValueError("--expected-count is required for --apply")
    active_candidates = discover_candidates(engrams_dir)
    quarantined_candidates = (
        discover_candidates(quarantine_dir) if quarantine_dir.is_dir() else []
    )
    active_names = {path.name for path in active_candidates}
    quarantined_names = {path.name for path in quarantined_candidates}
    duplicate_names = active_names & quarantined_names
    if duplicate_names:
        raise RuntimeError(
            "candidate exists in both active and quarantine locations: "
            + sorted(duplicate_names)[0]
        )
    candidate_names = sorted(active_names | quarantined_names)
    original_paths = [engrams_dir.resolve() / name for name in candidate_names]
    if expected_count is not None and len(candidate_names) != expected_count:
        raise RuntimeError(
            f"candidate count changed: expected {expected_count}, found {len(candidate_names)}"
        )

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "applied": apply,
        "phase": "dry_run" if not apply else "planned",
        "vault_root": str(vault_root),
        "candidate_count": len(candidate_names),
        "active_candidate_count": len(active_candidates),
        "already_quarantined_count": len(quarantined_candidates),
        "quarantine_dir": str(quarantine_dir),
        "candidates": [str(path) for path in original_paths],
        "chroma": {"found": 0, "deleted": 0, "missing": 0},
        "graph": {"matched": 0, "deleted": 0},
    }
    if not apply:
        _write_manifest(manifest_path, result)
        return result

    _write_manifest(manifest_path, result)
    try:
        _preflight_indexes(chromadb_path, graph_db)
        _move_with_rollback(active_candidates, quarantine_dir)
        result["phase"] = "files_moved"
        _write_manifest(manifest_path, result)
        result["chroma"] = _delete_chroma_records(original_paths, chromadb_path)
        result["phase"] = "chroma_deleted"
        _write_manifest(manifest_path, result)
        result["graph"] = _delete_graph_rows(
            [path.stem for path in original_paths], graph_db
        )
        result["phase"] = "complete"
        _write_manifest(manifest_path, result)
        return result
    except Exception as exc:
        result["phase"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        _write_manifest(manifest_path, result)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform moves and paired deletions")
    parser.add_argument("--expected-count", type=int, default=None)
    parser.add_argument("--vault-root", type=Path, default=_rp.VAULT)
    parser.add_argument("--chromadb-path", type=Path, default=_rp.ORA_HOME / "chromadb")
    parser.add_argument(
        "--graph-db", type=Path,
        default=_rp.DATA_DIR / "relationship-graph.db",
    )
    parser.add_argument(
        "--manifest", type=Path,
        default=_rp.DATA_DIR / "thin-engram-quarantine-manifest.json",
    )
    args = parser.parse_args()
    try:
        result = execute(
            vault_root=args.vault_root,
            chromadb_path=args.chromadb_path.expanduser().resolve(),
            graph_db=args.graph_db.expanduser().resolve(),
            apply=args.apply,
            expected_count=args.expected_count,
            manifest_path=args.manifest.expanduser().resolve(),
        )
    except Exception as exc:
        print(
            f"[engram-quarantine] failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    _write_manifest(args.manifest.expanduser().resolve(), result)
    action = "quarantined" if args.apply else "would quarantine"
    print(f"{action} {result['candidate_count']} thin runtime engrams")
    if args.apply:
        print(
            f"Chroma deleted {result['chroma']['deleted']} records; "
            f"graph deleted {result['graph']['deleted']} rows"
        )
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
