#!/usr/bin/env python3
"""Server-side companion to borrow-msi-corpus.py.

Reads the bge-m3 MSI collection from an intermediate ChromaDB on disk
(typically /tmp/msi-bge-m3-chromadb/ after rsync from Mac) and upserts
its docs + embeddings + metadata into the server's main ChromaDB
(~/ora/chromadb/). Pure data copy — no embedding happens here, which is
why this runs fine on the server's slow CPU.

Run on the server side of the cutover, after:
    rsync -av /tmp/msi-bge-m3-chromadb/ cloud-ora:/tmp/msi-bge-m3-chromadb/
    cd ~/ora && git pull origin main
    ollama pull bge-m3

Then this script + the chromadb.json flip + restart land MSI on bge-m3.

Usage:
    ~/ora/.venv/bin/python3 ~/ora/scripts/import-msi-bge-m3.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time

DEFAULT_SOURCE_CHROMADB = "/tmp/msi-bge-m3-chromadb"
DEFAULT_TARGET_CHROMADB = os.path.expanduser("~/ora/chromadb")
DEFAULT_COLLECTION_PHYSICAL = "msi_news_articles_v2"
DEFAULT_TARGET_EMBEDDER = "bge-m3"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_BATCH_SIZE = 500


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default=DEFAULT_SOURCE_CHROMADB, help="Intermediate ChromaDB path (default %(default)s)")
    p.add_argument("--target", default=DEFAULT_TARGET_CHROMADB, help="Server main ChromaDB path (default %(default)s)")
    p.add_argument("--collection", default=DEFAULT_COLLECTION_PHYSICAL, help="Collection physical name to import (default %(default)s)")
    p.add_argument("--target-embedder", default=DEFAULT_TARGET_EMBEDDER, help="Embedder name bound to target collection so future queries embed correctly (default %(default)s)")
    p.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Docs per upsert call (default %(default)s)")
    args = p.parse_args()

    if not os.path.isdir(args.source):
        print(f"FATAL: source ChromaDB not found at {args.source}", file=sys.stderr)
        return 2

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError as e:
        print(f"FATAL: chromadb not importable: {e}", file=sys.stderr)
        return 1

    # Source: read-only. Don't bind an embedding_function — we use .get()
    # which doesn't need one.
    src_client = chromadb.PersistentClient(path=args.source)
    try:
        source_col = src_client.get_collection(name=args.collection)
    except Exception as e:
        print(f"FATAL: source collection '{args.collection}' not in {args.source}: {e}", file=sys.stderr)
        return 2
    source_count = source_col.count()
    print(f"source: {args.source}::{args.collection} count={source_count}", file=sys.stderr, flush=True)

    # Target: bind the bge-m3 embedding_function so post-cutover query_texts()
    # calls embed correctly.
    tgt_client = chromadb.PersistentClient(path=args.target)
    target_embed_fn = embedding_functions.OllamaEmbeddingFunction(
        url=args.ollama_url,
        model_name=args.target_embedder,
    )
    try:
        target_col = tgt_client.get_collection(
            name=args.collection,
            embedding_function=target_embed_fn,
        )
        existing = target_col.count()
        print(f"target exists with {existing} docs (will upsert)", file=sys.stderr, flush=True)
    except Exception:
        target_col = tgt_client.create_collection(
            name=args.collection,
            metadata={"hnsw:space": "cosine"},
            embedding_function=target_embed_fn,
        )
        print(f"target created fresh", file=sys.stderr, flush=True)

    started = time.time()
    moved = 0
    # Iterate by id slices for stability across resume.
    all_ids_resp = source_col.get(include=[])
    all_ids = sorted(all_ids_resp.get("ids") or [])
    print(f"total source ids: {len(all_ids)}", file=sys.stderr, flush=True)

    for batch_start in range(0, len(all_ids), args.batch_size):
        batch_ids = all_ids[batch_start : batch_start + args.batch_size]
        batch = source_col.get(
            ids=batch_ids,
            include=["embeddings", "documents", "metadatas"],
        )
        # ChromaDB returns embeddings as a numpy array; `arr or []` raises
        # "truth value of an array is ambiguous". Use explicit None checks.
        embeddings = batch.get("embeddings")
        embeddings = embeddings if embeddings is not None else []
        documents = batch.get("documents")
        documents = documents if documents is not None else []
        metadatas = batch.get("metadatas")
        metadatas = metadatas if metadatas is not None else []
        if not (len(embeddings) == len(batch_ids) == len(documents) == len(metadatas)):
            print(
                f"  WARN: batch shape mismatch at offset {batch_start} "
                f"ids={len(batch_ids)} emb={len(embeddings)} docs={len(documents)} metas={len(metadatas)}",
                file=sys.stderr, flush=True,
            )
        target_col.upsert(
            ids=batch_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        moved += len(batch_ids)
        if (batch_start // args.batch_size) % 5 == 0:
            elapsed = time.time() - started
            rate = moved / elapsed if elapsed > 0 else 0
            print(f"  progress: {moved}/{len(all_ids)} ({rate:.0f} docs/sec)", file=sys.stderr, flush=True)

    final = target_col.count()
    elapsed = time.time() - started
    print(
        f"DONE: source={source_count} moved={moved} target_final={final} elapsed={elapsed:.1f}s",
        file=sys.stderr, flush=True,
    )
    return 0 if final >= source_count else 3


if __name__ == "__main__":
    sys.exit(main())
