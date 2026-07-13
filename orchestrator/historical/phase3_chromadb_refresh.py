"""Phase 3 — ChromaDB metadata refresh

After phase3_provenance_migration.py applies provenance-modifier tags
to engram YAML files, this script pushes the updated `tags` metadata
into the ChromaDB `knowledge` collection so the new tags flow through
to retrieval.

Uses metadata-only collection.update() calls — does NOT re-embed.

Strategy: walk every engram, re-build the metadata dict via
knowledge_index._compose_chroma_metadata(), build one collection-wide
path-to-record-ids index, and update every record whose `path` metadata
matches the source file. This covers both legacy single-record files and
HCP files stored under multiple chunk ids.

Idempotent: running twice produces the same metadata.
"""

from __future__ import annotations

import os
import sys
import glob

ENGRAMS_DIR = os.path.expanduser("~/Documents/vault/Engrams")
CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")
COLLECTION_NAME = "knowledge"


def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    from orchestrator.tools.knowledge_index import (
        _parse_frontmatter,
        _compose_chroma_metadata,
        build_path_id_index,
        update_file_metadata,
    )
    from orchestrator.embedding import get_or_create_collection
    import chromadb

    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    col = get_or_create_collection(client, COLLECTION_NAME)
    print(f"Collection {COLLECTION_NAME}: {col.count()} records")
    id_index = build_path_id_index(col)

    files = sorted(glob.glob(os.path.join(ENGRAMS_DIR, "*.md")))
    print(f"Walking {len(files)} engram source files...")

    total_updated = 0
    updated_files = 0
    never_indexed = 0
    errors = 0

    for i, path in enumerate(files):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            meta, _body = _parse_frontmatter(content)
            chroma_meta = _compose_chroma_metadata(path, meta)
            record_count = update_file_metadata(
                col, path, chroma_meta, id_index=id_index)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"METADATA UPDATE ERROR on {path}: {e}", file=sys.stderr)
            continue

        if record_count == 0:
            never_indexed += 1
        else:
            updated_files += 1
            total_updated += record_count

        if (i + 1) % 10000 == 0:
            print(f"  ... {i+1}/{len(files)} source files processed, "
                  f"{total_updated} records updated")

    print(f"\n=== Summary ===")
    print(f"  source files scanned:             {len(files)}")
    print(f"  source files updated:             {updated_files}")
    print(f"  ChromaDB records updated:         {total_updated}")
    print(f"  source files never indexed:       {never_indexed}")
    print(f"  source files with update errors:  {errors}")

    return {
        "source_files_scanned": len(files),
        "updated_files": updated_files,
        "updated_records": total_updated,
        "never_indexed_files": never_indexed,
        "errors": errors,
    }


if __name__ == "__main__":
    main()
