"""Rebuild the configured atomic-dedup collection from canonical engrams.

The vault is authoritative and Chroma is derived.  Recovery therefore writes
only to an explicit Chroma directory.  By default that directory must be
inactive (neither the active store nor one of its parents/children).  The
``--normal-runtime`` escape hatch permits the exact active directory for the
intentional maintenance case; it never permits a parent or child directory.

IDs retain the established filename-only hash for compatibility with existing
atomic writers and in-flight recovery output.  Because that scheme can collide
when two directories contain the same basename, the complete source plan is
audited before Chroma is opened; any duplicate ID aborts the rebuild without a
write.  ``--keep-existing`` is a verified resume mode: stored document and
metadata payloads must match the source plan exactly.

CLI::

    python -m orchestrator.historical.rebuild_atomic_dedup \
        --chromadb-path /path/to/inactive-chromadb \
        --expected-source-count 122118
    python -m orchestrator.historical.rebuild_atomic_dedup \
        --chromadb-path /path/to/inactive-chromadb \
        --expected-source-count 122118 --keep-existing
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import chromadb
import yaml

from orchestrator import runtime_paths as _rp

VAULT_ROOT = str(_rp.vault_dir() / "Engrams")
# Kept as a public compatibility constant.  Recovery callers must pass an
# explicit target to ``rebuild``; the CLI also requires --chromadb-path.
CHROMA_PATH = str(_rp.chromadb_dir())
# Logical name: the embedding layer resolves the configured physical name.
COLLECTION = "atomics"

MAX_EMBED_CHARS = 4000
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


class RebuildError(RuntimeError):
    """The source snapshot or recovery target is unsafe/inconsistent."""


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    identity: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class AtomicRecord:
    row_id: str
    document: str
    metadata: dict[str, str | int | float | bool]


@dataclass(frozen=True)
class RebuildPlan:
    vault_root: Path
    source_count: int
    skipped_short: int
    unique_ids: int
    records: tuple[AtomicRecord, ...]


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().absolute()


def _path_overlap(left: Path, right: Path) -> bool:
    left_real = Path(os.path.realpath(left))
    right_real = Path(os.path.realpath(right))
    if left_real == right_real:
        return True
    try:
        left_real.relative_to(right_real)
        return True
    except ValueError:
        pass
    try:
        right_real.relative_to(left_real)
        return True
    except ValueError:
        return False


def _directory_identity(path: Path) -> tuple[int, int, int, int, int]:
    value = path.lstat()
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        raise RebuildError(f"path is not a non-symlink directory: {path}")
    return (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


def validate_chromadb_target(
    chromadb_path: str | Path,
    *,
    allow_active_runtime: bool = False,
) -> Path:
    """Reject a symlink root, then canonicalize ambient ancestor aliases."""
    target = _absolute(chromadb_path)
    active = _absolute(_rp.chromadb_dir())
    if target.is_symlink():
        raise RebuildError(f"Chroma target must not be a symlink: {target}")
    if not target.is_dir():
        raise RebuildError(
            f"Chroma target must be an existing directory: {target}"
        )
    # Canonicalize ambient OS aliases (macOS /var -> /private/var) only after
    # rejecting a symlink at the declared root itself.  Source-tree symlinks
    # are rejected separately during discovery.
    target = target.resolve(strict=True)
    active = active.resolve(strict=False)
    target_real = Path(os.path.realpath(target))
    active_real = Path(os.path.realpath(active))
    if _path_overlap(target, active):
        if not (allow_active_runtime and target_real == active_real):
            raise RebuildError(
                "refusing Chroma target that equals or overlaps the active "
                f"store: target={target}, active={active}"
            )
    return target


def _source_identity(path: Path) -> tuple[int, int, int, int, int]:
    try:
        value = path.lstat()
    except OSError as exc:
        raise RebuildError(f"cannot stat source file {path}: {exc}") from exc
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise RebuildError(
            f"source is not a non-symlink regular file: {path}"
        )
    return (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


def _validate_source_root(vault_root: str | Path) -> Path:
    root = _absolute(vault_root)
    if root.is_symlink():
        raise RebuildError(f"vault source root must not be a symlink: {root}")
    if not root.is_dir():
        raise RebuildError(f"vault source root is not a directory: {root}")
    return root.resolve(strict=True)


def discover_sources(vault_root: str | Path) -> tuple[Path, tuple[SourceSnapshot, ...]]:
    """Discover one complete, no-symlink Markdown corpus snapshot."""
    root = _validate_source_root(vault_root)
    paths: list[Path] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        for directory in directories:
            candidate = Path(current) / directory
            if candidate.is_symlink():
                raise RebuildError(
                    f"vault source contains a symlink directory: {candidate}"
                )
        for filename in filenames:
            candidate = Path(current) / filename
            if candidate.is_symlink():
                raise RebuildError(
                    f"vault source contains a symlink file: {candidate}"
                )
            if filename.endswith(".md"):
                paths.append(candidate)
    snapshots = tuple(
        SourceSnapshot(_absolute(path), _source_identity(path))
        for path in sorted(paths, key=lambda item: str(item))
    )
    return root, snapshots


def _read_text_snapshot(source: SourceSnapshot) -> str:
    """Strictly read the exact regular-file identity discovered earlier."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(source.path, flags)
    except OSError as exc:
        raise RebuildError(
            f"cannot securely open source file {source.path}: {exc}"
        ) from exc
    try:
        before = os.fstat(fd)
        before_identity = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        )
        if not stat.S_ISREG(before.st_mode) or before_identity != source.identity:
            raise RebuildError(
                f"source changed after discovery: {source.path}"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        after_identity = (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
    finally:
        os.close(fd)
    if after_identity != source.identity:
        raise RebuildError(f"source changed during read: {source.path}")
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RebuildError(
            f"source is not valid UTF-8: {source.path}: {exc}"
        ) from exc


def parse_note_text(path: Path, text: str) -> tuple[dict[str, Any], str, str]:
    """Return strictly parsed ``(frontmatter, title, body)``."""
    match = _FRONTMATTER_RE.match(text)
    if text.startswith("---\n") and match is None:
        raise RebuildError(f"unterminated YAML frontmatter: {path}")
    if match is None:
        frontmatter: dict[str, Any] = {}
        body = text
    else:
        try:
            loaded = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise RebuildError(f"invalid YAML frontmatter in {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise RebuildError(f"YAML frontmatter is not a mapping: {path}")
        frontmatter = loaded
        body = text[match.end():]
    title = path.stem
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break
    return frontmatter, title, body


def parse_note(path: Path) -> tuple[dict[str, Any], str, str]:
    """Compatibility helper with strict UTF-8 and same-file validation."""
    source = SourceSnapshot(_absolute(path), _source_identity(_absolute(path)))
    return parse_note_text(source.path, _read_text_snapshot(source))


def normalized_vault_relative_path(path: Path, vault_root: str | Path) -> str:
    root = _absolute(vault_root)
    candidate = _absolute(path)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise RebuildError(f"source escapes vault root: {candidate}") from exc
    normalized = unicodedata.normalize("NFC", relative.as_posix())
    if not normalized or normalized == "." or normalized.startswith("../"):
        raise RebuildError(f"invalid vault-relative source path: {candidate}")
    return normalized


def stable_id(path: Path, vault_root: str | Path = VAULT_ROOT) -> str:
    """Established deterministic filename ID (``vault_root`` is compat-only)."""
    del vault_root
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:14]
    return f"atomic-{digest}"


def legacy_stable_id(path: Path) -> str:
    """Compatibility alias for callers that named the established ID scheme."""
    return stable_id(path)


def embedding_text(title: str, body: str) -> str:
    return f"{title}\n\n{body}".strip()[:MAX_EMBED_CHARS]


def metadata_for(
    fm: dict[str, Any], title: str, path: Path,
) -> dict[str, str | int | float | bool]:
    meta: dict[str, Any] = {
        "title": title,
        # Preserve the established absolute-path payload consumed by Phase 5.
        "vault_path": str(path),
        "source_chat": fm.get("source_chat") or "",
        "source_platform": fm.get("source_platform") or "",
        "when": (fm.get("date created") or fm.get("processed_at") or "")
        and str(fm.get("date created") or fm.get("processed_at")),
        "seen_count": int(fm.get("seen_count", 1) or 1),
    }
    return {key: value for key, value in meta.items() if value not in (None, "")}


def build_rebuild_plan(
    vault_root: str | Path = VAULT_ROOT,
    *,
    max_workers: int = 8,
) -> RebuildPlan:
    """Materialize and revalidate an immutable source-derived record plan."""
    if max_workers < 1:
        raise RebuildError("max_workers must be positive")
    root, sources = discover_sources(vault_root)
    records_by_path: dict[Path, AtomicRecord | None] = {}

    def parse(source: SourceSnapshot) -> AtomicRecord | None:
        text = _read_text_snapshot(source)
        fm, title, body = parse_note_text(source.path, text)
        document = embedding_text(title, body)
        if len(document.strip()) < 30:
            return None
        return AtomicRecord(
            stable_id(source.path, root),
            document,
            metadata_for(fm, title, source.path),
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(parse, source): source for source in sources}
        try:
            for future in as_completed(futures):
                source = futures[future]
                records_by_path[source.path] = future.result()
        except Exception:
            for future in futures:
                future.cancel()
            raise

    # Re-discovery detects additions, removals, symlink substitutions, and any
    # identity change before the first Chroma write.  Planned content remains
    # materialized, so later source changes cannot produce a mixed snapshot.
    _, after = discover_sources(root)
    if after != sources:
        raise RebuildError("vault source corpus changed while building the plan")

    ordered = tuple(
        record for source in sources
        if (record := records_by_path[source.path]) is not None
    )
    id_paths: dict[str, list[Path]] = {}
    for source in sources:
        record = records_by_path[source.path]
        if record is not None:
            id_paths.setdefault(record.row_id, []).append(source.path)
    duplicates = {
        row_id: paths for row_id, paths in id_paths.items() if len(paths) > 1
    }
    if duplicates:
        row_id, paths = sorted(duplicates.items())[0]
        rendered = ", ".join(str(path) for path in paths[:4])
        raise RebuildError(
            "filename-derived atomic ID collision before Chroma open: "
            f"{row_id} <- {rendered}"
        )
    return RebuildPlan(
        vault_root=root,
        source_count=len(sources),
        skipped_short=len(sources) - len(ordered),
        unique_ids=len(id_paths),
        records=ordered,
    )


def _collection_names(client: Any) -> set[str]:
    names: set[str] = set()
    for item in client.list_collections():
        name = item if isinstance(item, str) else getattr(item, "name", None)
        if not isinstance(name, str) or not name:
            raise RebuildError(f"unexpected Chroma collection descriptor: {item!r}")
        names.add(name)
    return names


def _open_collection(
    chromadb_path: Path,
    drop_existing: bool,
    *,
    expected_target_identity: tuple[int, int, int, int, int],
):
    from orchestrator.embedding import get_or_create_collection, resolve_collection

    if chromadb_path.is_symlink():
        raise RebuildError(f"Chroma target became a symlink: {chromadb_path}")
    if _directory_identity(chromadb_path) != expected_target_identity:
        raise RebuildError("Chroma target changed between validation and open")
    client = chromadb.PersistentClient(path=str(chromadb_path))
    if drop_existing:
        existing_names = _collection_names(client)
        for name in {resolve_collection(COLLECTION), COLLECTION} & existing_names:
            try:
                client.delete_collection(name)
            except Exception as exc:
                raise RebuildError(
                    f"failed to drop existing collection {name!r}: {exc}"
                ) from exc
            print(f"dropped collection {name!r}", flush=True)
    try:
        collection = get_or_create_collection(client, COLLECTION)
    except Exception as exc:
        raise RebuildError(f"failed to open {COLLECTION!r}: {exc}") from exc
    print(
        f"opened {COLLECTION!r} (physical: {resolve_collection(COLLECTION)!r}), "
        f"count={collection.count()}",
        flush=True,
    )
    return collection


def _existing_records(collection: Any) -> dict[str, tuple[str, dict[str, Any]]]:
    rows: dict[str, tuple[str, dict[str, Any]]] = {}
    offset = 0
    total = collection.count()
    while offset < total:
        try:
            page = collection.get(
                limit=5000,
                offset=offset,
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            raise RebuildError(f"failed reading existing collection: {exc}") from exc
        ids = page.get("ids") or []
        documents = page.get("documents") or []
        metadatas = page.get("metadatas") or []
        if not ids:
            raise RebuildError(
                "existing collection pagination ended before reported count"
            )
        if len(ids) != len(documents) or len(ids) != len(metadatas):
            raise RebuildError("existing collection returned incomplete payloads")
        for row_id, document, metadata in zip(ids, documents, metadatas):
            if row_id in rows:
                raise RebuildError(f"duplicate existing row ID: {row_id}")
            if not isinstance(document, str) or not isinstance(metadata, dict):
                raise RebuildError(f"invalid existing payload for row {row_id}")
            rows[row_id] = (document, metadata)
        offset += len(ids)
    if len(rows) != total:
        raise RebuildError(
            f"existing collection count changed during read: {total} -> {len(rows)}"
        )
    return rows


def _resume_partition(
    plan: RebuildPlan,
    existing: dict[str, tuple[str, dict[str, Any]]],
) -> tuple[list[AtomicRecord], int]:
    planned = {record.row_id: record for record in plan.records}
    extras = set(existing) - set(planned)
    if extras:
        raise RebuildError(
            "--keep-existing found rows outside the current source plan"
            "; use replacement rebuild to remove stale rows"
        )
    todo: list[AtomicRecord] = []
    verified = 0
    for record in plan.records:
        stored = existing.get(record.row_id)
        if stored is None:
            todo.append(record)
            continue
        if (
            stored[0] != record.document
            or not _metadata_equal_typed(stored[1], record.metadata)
        ):
            raise RebuildError(
                "--keep-existing payload mismatch for row "
                f"{record.row_id}; replacement rebuild is required"
            )
        verified += 1
    return todo, verified


def _metadata_equal_typed(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.keys() != right.keys():
        return False
    return all(
        type(left[key]) is type(right[key]) and left[key] == right[key]
        for key in left
    )


def _upsert_batch(collection: Any, batch: Sequence[AtomicRecord]) -> None:
    try:
        collection.upsert(
            ids=[record.row_id for record in batch],
            documents=[record.document for record in batch],
            metadatas=[record.metadata for record in batch],
        )
    except Exception as exc:
        raise RebuildError(
            f"upsert failed for batch of {len(batch)} records: {exc}"
        ) from exc


def rebuild(
    *,
    chromadb_path: str | Path,
    expected_source_count: int,
    vault_root: str | Path = VAULT_ROOT,
    drop_existing: bool = True,
    max_workers: int = 8,
    batch_size: int = 100,
    allow_active_runtime: bool = False,
) -> dict[str, Any]:
    """Build a verified source snapshot into an explicit Chroma target."""
    if batch_size < 1:
        raise RebuildError("batch_size must be positive")
    if expected_source_count < 1:
        raise RebuildError("expected_source_count must be positive")
    target = validate_chromadb_target(
        chromadb_path, allow_active_runtime=allow_active_runtime,
    )
    target_identity = _directory_identity(target)
    plan = build_rebuild_plan(vault_root, max_workers=max_workers)
    if plan.source_count != expected_source_count:
        raise RebuildError(
            "vault source count does not match the explicit recovery precondition: "
            f"expected={expected_source_count}, actual={plan.source_count}"
        )
    print(
        f"vault notes: {plan.source_count}, eligible: {len(plan.records)}, "
        f"skipped short: {plan.skipped_short}",
        flush=True,
    )
    collection = _open_collection(
        target,
        drop_existing,
        expected_target_identity=target_identity,
    )
    existing = _existing_records(collection)
    todo, verified_existing = _resume_partition(plan, existing)
    print(
        f"verified existing: {verified_existing}, to embed: {len(todo)}",
        flush=True,
    )

    started = time.time()
    for index in range(0, len(todo), batch_size):
        batch = todo[index:index + batch_size]
        _upsert_batch(collection, batch)
        processed = index + len(batch)
        if processed % 2000 == 0 or processed == len(todo):
            elapsed = time.time() - started
            rate = processed / elapsed if elapsed > 0 else 0.0
            print(
                f"  [{processed}/{len(todo)}] rate={rate:.1f}/s "
                f"count={collection.count()}",
                flush=True,
            )

    final_count = collection.count()
    if final_count != len(plan.records):
        raise RebuildError(
            "final collection count does not match the source plan: "
            f"expected={len(plan.records)}, actual={final_count}"
        )
    summary: dict[str, Any] = {
        "vault_notes": plan.source_count,
        "expected_source_count": expected_source_count,
        "eligible_records": len(plan.records),
        "skipped_short": plan.skipped_short,
        "embedded": len(todo),
        "verified_existing": verified_existing,
        "id_audit": {
            "scheme": "filename-sha256-14",
            "eligible_records": len(plan.records),
            "unique_ids": plan.unique_ids,
            "duplicate_ids": 0,
        },
        "errors": 0,
        "final_count": final_count,
        "duration_secs": time.time() - started,
        "chromadb_path": str(target),
    }
    print(f"DONE — {summary}", flush=True)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chromadb-path",
        required=True,
        help="Explicit Chroma directory; must be inactive unless --normal-runtime",
    )
    parser.add_argument("--vault-root", default=VAULT_ROOT)
    parser.add_argument(
        "--expected-source-count",
        required=True,
        type=int,
        help="Required source-count precondition checked before Chroma is opened",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Verified resume only; every existing payload must match exactly",
    )
    parser.add_argument(
        "--normal-runtime",
        action="store_true",
        help="Permit the exact active Chroma directory for intentional maintenance",
    )
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rebuild(
            chromadb_path=args.chromadb_path,
            expected_source_count=args.expected_source_count,
            vault_root=args.vault_root,
            drop_existing=not args.keep_existing,
            max_workers=args.max_workers,
            batch_size=args.batch_size,
            allow_active_runtime=args.normal_runtime,
        )
    except RebuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
