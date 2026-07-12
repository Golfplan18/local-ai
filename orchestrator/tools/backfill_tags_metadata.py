"""One-time `tags` metadata backfill for the live knowledge collection.

Why: `provenance.py` carries a 0.6 retrieval-weight penalty for the
`superseded` tag and rag_engine's ranker reads `metadata["tags"]` — but
zero records in the live knowledge collection carry a `tags` key (the
2026-05-29 embedder migration re-embedded content without the list-typed
tag metadata), so the penalty and the engram `archived`-tag filtering
have been dormant since. knowledge_index has composed `tags` into new
records all along; only the already-indexed corpus is missing it.

What it does: for every record, re-reads the source file's YAML
frontmatter, composes fresh metadata via knowledge_index's canonical
`_compose_chroma_metadata`, but merges in ONLY the `tags` key and the
`tag_<name>` filterable-tag booleans (never type/nexus/relationships/etc)
and pushes metadata-only `collection.update` batches — the same pattern
as the resolvers' refresh_chromadb, batched for 150k records. No
re-embedding.

Scope is deliberately narrow, not "recompose everything": project tools
(e.g. MSI's index_msi_news.py) index into this same collection via
`index_file(..., meta_overrides=...)`, injecting type/nexus/tags fields
the source file's own frontmatter never carries (confirmed against the
live MSI News mirror — its files have no Ora-schema tags key at all).
Recomposing the FULL metadata dict from bare frontmatter for such a
record would blank out its type/nexus and flip every tag_<name> boolean
to False, silently breaking that project's RAG exclude_tags scoping and
provenance-weight lookup for every affected record, permanently (those
records are indexed once and never re-touched). Restricting the merge to
tags-only avoids corrupting type/nexus; on top of that, a record whose
recomputed tags list is empty AND whose existing record already carries a
non-empty `type` is skipped entirely — that combination is the signature
of a meta_overrides-indexed record this backfill cannot faithfully
reproduce from the bare file alone.

Idempotent: a second run finds every merge a no-op and writes nothing.
Records whose source file no longer exists are counted and left alone
(loudly reported, never deleted — stale-entry cleanup is not this tool's
job).

Usage:
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tools/backfill_tags_metadata.py [--dry-run] [--batch-size 500]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.expanduser("~/ora"))

CHROMADB_PATH = os.path.expanduser(
    os.environ.get("ORA_CHROMADB_PATH", "~/ora/chromadb"))
COLLECTION_NAME = "knowledge"
DEFAULT_BATCH_SIZE = 500


def backfill_collection(col, *, batch_size: int = DEFAULT_BATCH_SIZE,
                        dry_run: bool = False, log=print) -> dict:
    """Refresh tags-related metadata for every record in ``col``.

    Merges in only `tags` + `tag_<name>` booleans (see module docstring
    for why the merge is scoped this narrowly). Returns stats: total,
    updated, unchanged, missing_file, parse_errors, skipped_override_indexed.
    """
    from orchestrator.tools.knowledge_index import (
        _parse_frontmatter,
        _compose_chroma_metadata,
        _FILTERABLE_TAGS,
    )

    tag_keys = {"tags"} | {f"tag_{t}" for t in _FILTERABLE_TAGS}

    stats = {"total": 0, "updated": 0, "unchanged": 0,
             "missing_file": 0, "parse_errors": 0,
             "skipped_override_indexed": 0}

    # Snapshot all ids first so paging is unaffected by our own updates.
    all_ids: list[str] = []
    offset = 0
    while True:
        page = col.get(limit=batch_size, offset=offset, include=[])
        ids = page.get("ids") or []
        if not ids:
            break
        all_ids.extend(ids)
        offset += len(ids)
    stats["total"] = len(all_ids)
    log(f"{len(all_ids)} records in collection")
    live_count = col.count()
    if len(set(all_ids)) != live_count:
        # offset/limit paging assumes stable ordering across calls; this is
        # a cheap after-the-fact cross-check, not a guarantee — a mismatch
        # here means the id snapshot likely missed or duplicated records
        # (e.g. concurrent writes from the live server during the scan).
        log(f"  WARNING: snapshot collected {len(set(all_ids))} distinct "
            f"ids but collection.count()={live_count} — the id snapshot "
            f"may be incomplete (concurrent writes during paging?); "
            f"re-run once no other process is indexing.")

    composed_cache: dict[str, dict | None] = {}

    def _composed_for(path: str) -> dict | None:
        if path in composed_cache:
            return composed_cache[path]
        composed: dict | None = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                meta, _body = _parse_frontmatter(content)
                composed = _compose_chroma_metadata(path, meta)
            except Exception as e:
                stats["parse_errors"] += 1
                log(f"  parse error for {path}: {e}")
                composed = None
        composed_cache[path] = composed
        return composed

    for i in range(0, len(all_ids), batch_size):
        chunk_ids = all_ids[i:i + batch_size]
        page = col.get(ids=chunk_ids, include=["metadatas"])
        update_ids: list[str] = []
        update_metas: list[dict] = []
        for rec_id, existing in zip(page.get("ids") or [],
                                    page.get("metadatas") or []):
            existing = existing or {}
            path = existing.get("path") or rec_id
            if not os.path.exists(path):
                stats["missing_file"] += 1
                continue
            composed = _composed_for(path)
            if composed is None:
                continue

            composed_tags_only = {k: v for k, v in composed.items()
                                  if k in tag_keys}
            # Signature of a meta_overrides-indexed record (e.g. an MSI
            # article): the bare file has no tags of its own, but the
            # existing record already has a real type — recomposing from
            # the file alone would wipe that record's tag_<name> booleans
            # (built from meta_overrides, not the file). Leave it untouched
            # rather than corrupt it.
            if not composed_tags_only.get("tags") and existing.get("type"):
                stats["skipped_override_indexed"] += 1
                continue

            merged = {**existing, **composed_tags_only}
            if merged == existing:
                stats["unchanged"] += 1
                continue
            update_ids.append(rec_id)
            update_metas.append(merged)

        if update_ids and not dry_run:
            try:
                col.update(ids=update_ids, metadatas=update_metas)
            except Exception as e:
                # Matches the existing resolvers' refresh_chromadb pattern:
                # one bad batch must not abort a multi-hundred-batch run
                # with no summary. This batch's records stay un-backfilled
                # (idempotent — a re-run will retry them) but every other
                # batch keeps going.
                stats.setdefault("batch_errors", 0)
                stats["batch_errors"] += 1
                log(f"  batch {i // batch_size + 1}: chromadb update "
                    f"error, skipping this batch ({len(update_ids)} "
                    f"records): {e}")
                continue
        stats["updated"] += len(update_ids)
        if update_ids:
            log(f"  batch {i // batch_size + 1}: "
                f"{'would update' if dry_run else 'updated'} "
                f"{len(update_ids)} records")

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = ap.parse_args()

    import chromadb
    from orchestrator.embedding import get_collection

    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    col = get_collection(client, COLLECTION_NAME)

    stats = backfill_collection(
        col, batch_size=args.batch_size, dry_run=args.dry_run)

    print("\n=== Backfill summary ===")
    for k, v in stats.items():
        print(f"  {k:15} {v:>8}")
    if args.dry_run:
        print("\nDRY RUN — no metadata written.")


if __name__ == "__main__":
    main()
