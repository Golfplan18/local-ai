"""Phase 3 — ChromaDB metadata refresh

After phase3_provenance_migration.py applies provenance-modifier tags
to engram YAML files, this script pushes the updated `tags` metadata
into the ChromaDB `knowledge` collection so the new tags flow through
to retrieval.

Uses collection.update() — does NOT re-embed. Fast.

Strategy: walk every engram, re-build the metadata dict via
knowledge_index._compose_chroma_metadata(), and call update() in
batches. ChromaDB matches on `path` (which is the chromadb id).

Idempotent: running twice produces the same metadata.
"""

from __future__ import annotations

import os
import sys
import glob

ENGRAMS_DIR = os.path.expanduser("~/Documents/vault/Engrams")
CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")
COLLECTION_NAME = "knowledge"
BATCH_SIZE = 500


def main():
    sys.path.insert(0, "/Users/oracle/ora")

    from orchestrator.tools.knowledge_index import (
        _parse_frontmatter,
        _compose_chroma_metadata,
    )
    from orchestrator.embedding import get_or_create_collection
    import chromadb

    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    col = get_or_create_collection(client, COLLECTION_NAME)
    print(f"Collection {COLLECTION_NAME}: {col.count()} documents")

    files = sorted(glob.glob(os.path.join(ENGRAMS_DIR, "*.md")))
    print(f"Walking {len(files)} engrams...")

    batch_ids: list[str] = []
    batch_metas: list[dict] = []
    total_updated = 0
    skipped = 0
    errors = 0

    def flush():
        nonlocal total_updated, batch_ids, batch_metas
        if not batch_ids:
            return
        try:
            col.update(ids=batch_ids, metadatas=batch_metas)
            total_updated += len(batch_ids)
        except Exception as e:
            print(f"BATCH UPDATE ERROR ({len(batch_ids)} ids): {e}", file=sys.stderr)
        batch_ids = []
        batch_metas = []

    for i, path in enumerate(files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            meta, _body = _parse_frontmatter(content)
            chroma_meta = _compose_chroma_metadata(path, meta)
            batch_ids.append(path)
            batch_metas.append(chroma_meta)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"PARSE ERROR on {path}: {e}", file=sys.stderr)
            continue

        if len(batch_ids) >= BATCH_SIZE:
            flush()

        if (i + 1) % 10000 == 0:
            print(f"  ... {i+1}/{len(files)} processed, {total_updated} updated")

    flush()

    print(f"\n=== Summary ===")
    print(f"  total scanned:  {len(files)}")
    print(f"  updated:        {total_updated}")
    print(f"  skipped:        {skipped}")
    print(f"  errors:         {errors}")


if __name__ == "__main__":
    main()
