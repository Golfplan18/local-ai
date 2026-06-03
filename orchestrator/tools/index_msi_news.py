#!/usr/bin/env python3
"""Index the MSI News mirror into the Ora `knowledge` collection.

`~/Documents/vault/MSI News/` is a one-way `rsync -az --delete` mirror of
the cloud MSI pipeline's `cloud-outbox/msi-news/` (launchd job
`com.cloud-ora.sync`, every 15 min). Its on-disk .md files do NOT carry
Ora schema frontmatter, and any local stamp would be reverted on the next
sync. So this indexer FORCES the schema at index time via
`knowledge_index.index_file`'s `meta_overrides`, without modifying files:

    type  : resource                  -> provenance weight 0.8 (Ora YAML Schema)
    nexus : [main-street-independent]  -> MSI namespace marker (Tagging Schema §D)
    tags  : [news, main-street-independent, msi-news]
            -> §A genre + namespace tag + the `msi-news` scoping tag,
               registered in knowledge_index._FILTERABLE_TAGS so a mode's
               `### exclude_tags` RAG profile can scope MSI news in/out of
               the knowledge lane. (Default: included, at weight 0.8.)

A knowledge_v2 doc persists once written, regardless of later file
reverts. This module is the runtime indexing path for MSI news: called by
the post-rsync hook in ~/cloud-ora-sync/sync.py (index exactly what the
sync changed — no separate cron, per the Runtime Principle), and runnable
standalone for the initial catch-up over the existing mirror.

Usage:
    python3 -m orchestrator.tools.index_msi_news              # index new files in the folder
    python3 -m orchestrator.tools.index_msi_news --force      # re-index the whole folder
    python3 -m orchestrator.tools.index_msi_news [--force] PATH [PATH ...]   # specific files
"""
from __future__ import annotations

import glob
import os
import sys
from typing import Optional

from orchestrator.tools.knowledge_index import index_file

VAULT = os.environ.get("ORA_VAULT") or os.path.expanduser("~/Documents/vault")
MSI_NEWS = os.path.join(VAULT, "MSI News")
CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")

# Forced Ora-schema metadata for every MSI News article. Single source of
# truth for the MSI knowledge-RAG identity.
MSI_META_OVERRIDES = {
    "type": "resource",
    "nexus": ["main-street-independent"],
    "tags": ["news", "main-street-independent", "msi-news"],
}


def _collection():
    import chromadb
    from orchestrator.embedding import get_or_create_collection
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    return get_or_create_collection(client, "knowledge")


def index_msi_news(
    paths: Optional[list[str]] = None,
    *,
    force: bool = False,
    collection=None,
) -> dict[str, int]:
    """Index MSI News articles into knowledge_v2 with forced MSI metadata.

    paths defaults to every .md in the MSI News mirror. Returns the
    {indexed, skipped, errors} stats dict. Files shorter than 50 chars or
    unreadable are skipped/counted by index_file.
    """
    col = collection if collection is not None else _collection()
    if paths is None:
        paths = sorted(glob.glob(os.path.join(MSI_NEWS, "*.md")))
    stats = {"indexed": 0, "skipped": 0, "errors": 0}
    for p in paths:
        try:
            index_file(col, p, stats,
                       meta_overrides=MSI_META_OVERRIDES, force=force)
        except Exception as e:
            stats["errors"] += 1
            print(f"  ERROR indexing {os.path.basename(p)}: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
    return stats


def remove_paths(paths: list[str], *, collection=None) -> int:
    """Delete the given files' docs from knowledge_v2 (id = absolute path).

    Used by the sync hook to drop articles that the rsync `--delete`
    removed from the mirror, so knowledge_v2 doesn't retain orphans.
    Returns the count of ids requested for deletion.
    """
    col = collection if collection is not None else _collection()
    ids = [os.path.abspath(p) for p in paths]
    if ids:
        try:
            col.delete(ids=ids)
        except Exception as e:
            print(f"  remove error: {type(e).__name__}: {e}", file=sys.stderr)
    return len(ids)


def main(argv: list[str]) -> None:
    force = "--force" in argv
    paths = [a for a in argv if a != "--force"] or None
    col = _collection()
    stats = index_msi_news(paths, force=force, collection=col)
    print(f"MSI index done: {stats}")
    print(f"knowledge_v2 total: {col.count()}")


if __name__ == "__main__":
    main(sys.argv[1:])
