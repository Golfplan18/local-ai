#!/usr/bin/env python3
"""Build a bge-m3 ChromaDB collection from MSI articles on the Mac.

Reads MSI's published-article markdown files from a local directory
(the canonical source — committed to the MSI repo and deployed to the
server via msi-deploy.sh), composes the same embed text + metadata
shape that news_index.py uses, batches them through Ollama bge-m3 on
the Mac (~10K tokens/sec), and writes the result into a separate
ChromaDB at /tmp/msi-bge-m3-chromadb/.

The output ChromaDB is intentionally NOT inside ~/ora/chromadb/ — it's
a temporary, self-contained instance whose only purpose is to be
rsynced to the server and merged into the server's main ChromaDB by
the companion import-msi-bge-m3.py script.

Cutover sequence (after this script finishes):
    1. rsync -av /tmp/msi-bge-m3-chromadb/ cloud-ora:/tmp/msi-bge-m3-chromadb/
    2. ssh cloud-ora "cd ~/ora && git pull"     (pulls embedding.py + chromadb.json refactor)
    3. ssh cloud-ora "ollama pull bge-m3"
    4. ssh cloud-ora "~/ora/.venv/bin/python3 ~/ora/scripts/import-msi-bge-m3.py"
    5. Edit server's ~/ora/config/chromadb.json: set embedder=bge-m3, dim=1024,
       and the msi_news_articles physical name to msi_news_articles_v2.
    6. Re-embed the small msi_conversations collection in place on server.
    7. Restart the server orchestrator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Pull in news_index.py's helpers verbatim so the v2 embed text and metadata
# are byte-identical to what production indexing would have produced on its
# own. Avoids semantic drift between this one-time migration and the
# steady-state indexing path.
MSI_TOOLS_DIR = os.path.expanduser("~/sites/mainstreetindependent/ora-project/tools")
sys.path.insert(0, MSI_TOOLS_DIR)
# Also reach into the ora orchestrator (for collection-name translation).
sys.path.insert(0, os.path.expanduser("~/ora"))

from news_index import (  # noqa: E402
    _build_embed_text,
    _compose_chroma_metadata,
    _parse_frontmatter,
)

DEFAULT_ARTICLES_DIR = os.path.expanduser(
    "~/sites/mainstreetindependent/src/content/articles"
)
DEFAULT_OUTPUT_CHROMADB = "/tmp/msi-bge-m3-chromadb"
DEFAULT_COLLECTION_PHYSICAL = "msi_news_articles_v2"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Ollama batch embedding (same pattern as re-embed-local.py)
# ---------------------------------------------------------------------------


def ollama_embed_batch(
    texts: list[str],
    *,
    model: str,
    url: str,
    timeout: float = 120.0,
    attempts: int = 3,
) -> list[list[float]]:
    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                f"{url}/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                raise RuntimeError(
                    f"Ollama returned {len(embeddings) if isinstance(embeddings, list) else 'no'} "
                    f"embeddings for {len(texts)} inputs"
                )
            return embeddings
        except Exception as e:
            last_err = e
            if attempt < attempts:
                wait = attempt * 2
                print(
                    f"  [warn] Ollama batch failed (attempt {attempt}/{attempts}): {e}; retrying in {wait}s",
                    file=sys.stderr, flush=True,
                )
                time.sleep(wait)
    assert last_err is not None
    raise last_err


def assert_target_embedder_available(model: str, url: str) -> None:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        raise SystemExit(f"FATAL: Cannot reach Ollama at {url}: {e}")
    names = [m.get("name", "") for m in data.get("models", []) or []]
    if not any(model in n for n in names):
        raise SystemExit(f"FATAL: '{model}' not pulled. Run: ollama pull {model}")


# ---------------------------------------------------------------------------
# Walk articles directory
# ---------------------------------------------------------------------------


def walk_articles(articles_dir: str) -> list[str]:
    """Return a sorted list of absolute .md file paths."""
    md_files: list[str] = []
    for root, _dirs, files in os.walk(articles_dir):
        for f in files:
            if f.endswith(".md") and not f.startswith("."):
                md_files.append(os.path.abspath(os.path.join(root, f)))
    return sorted(md_files)


def read_article(path: str) -> tuple[dict, str] | None:
    """Read + parse one article. Returns (frontmatter_dict, body_text) or
    None if the file is unreadable / too small to embed.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None
    if len(content.strip()) < 50:
        return None
    return _parse_frontmatter(content)


# ---------------------------------------------------------------------------
# Build collection
# ---------------------------------------------------------------------------


def build(
    *,
    articles_dir: str,
    output_chromadb_path: str,
    collection_physical: str,
    target_model: str,
    target_dim: int,
    ollama_url: str,
    batch_size: int,
) -> dict:
    import chromadb
    from chromadb.utils import embedding_functions

    print(f"\n=== MSI article re-embed → {collection_physical} (bge-m3) ===", file=sys.stderr, flush=True)
    print(f"  articles dir: {articles_dir}", file=sys.stderr, flush=True)
    print(f"  output ChromaDB: {output_chromadb_path}", file=sys.stderr, flush=True)

    md_files = walk_articles(articles_dir)
    print(f"  found {len(md_files)} .md files", file=sys.stderr, flush=True)

    client = chromadb.PersistentClient(path=output_chromadb_path)
    target_embed_fn = embedding_functions.OllamaEmbeddingFunction(
        url=ollama_url,
        model_name=target_model,
    )
    # Idempotent: re-runs against an existing target collection upsert,
    # they don't error.
    try:
        target = client.get_collection(
            name=collection_physical,
            embedding_function=target_embed_fn,
        )
        existing = target.count()
        print(f"  target exists with {existing} docs (resuming/upserting)", file=sys.stderr, flush=True)
    except Exception:
        target = client.create_collection(
            name=collection_physical,
            metadata={"hnsw:space": "cosine"},
            embedding_function=target_embed_fn,
        )
        print(f"  target created fresh", file=sys.stderr, flush=True)

    started_at = time.time()
    indexed = 0
    skipped_unreadable = 0
    skipped_empty_embed = 0

    # Process in batches of `batch_size` files at a time.
    for batch_start in range(0, len(md_files), batch_size):
        batch_paths = md_files[batch_start : batch_start + batch_size]
        batch_ids: list[str] = []
        batch_docs: list[str] = []
        batch_metas: list[dict] = []

        for path in batch_paths:
            parsed = read_article(path)
            if parsed is None:
                skipped_unreadable += 1
                continue
            meta_dict, body = parsed
            embed_text = _build_embed_text(meta_dict, body)
            if not embed_text or not embed_text.strip():
                skipped_empty_embed += 1
                continue
            chroma_meta = _compose_chroma_metadata(path, meta_dict)
            batch_ids.append(path)  # doc id = absolute file path (same convention as news_index.py)
            batch_docs.append(embed_text)
            batch_metas.append(chroma_meta)

        if not batch_ids:
            continue

        try:
            embeddings = ollama_embed_batch(
                batch_docs, model=target_model, url=ollama_url
            )
        except Exception as e:
            print(f"  FATAL embed batch failed at offset {batch_start}: {e}", file=sys.stderr, flush=True)
            raise

        for vec in embeddings:
            if len(vec) != target_dim:
                raise SystemExit(
                    f"FATAL: bge-m3 returned vector dim {len(vec)}, expected {target_dim}"
                )

        target.upsert(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch_docs,
            metadatas=batch_metas,
        )
        indexed += len(batch_ids)

        if (batch_start // batch_size) % 10 == 0:
            elapsed = time.time() - started_at
            rate = indexed / elapsed if elapsed > 0 else 0
            pct = (batch_start + len(batch_paths)) / len(md_files) * 100 if md_files else 100
            print(
                f"  progress: {indexed}/{len(md_files)} ({pct:.1f}%)  rate: {rate:.1f} docs/sec",
                file=sys.stderr, flush=True,
            )

    final_count = target.count()
    elapsed = time.time() - started_at
    report = {
        "articles_dir": articles_dir,
        "output_chromadb_path": output_chromadb_path,
        "collection_physical": collection_physical,
        "target_model": target_model,
        "files_walked": len(md_files),
        "indexed": indexed,
        "skipped_unreadable": skipped_unreadable,
        "skipped_empty_embed": skipped_empty_embed,
        "target_final_count": final_count,
        "elapsed_seconds": round(elapsed, 1),
    }
    print(
        f"  DONE: files={len(md_files)} indexed={indexed} unreadable={skipped_unreadable} "
        f"empty={skipped_empty_embed} final={final_count} ({elapsed:.0f}s)",
        file=sys.stderr, flush=True,
    )
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--articles-dir", default=DEFAULT_ARTICLES_DIR)
    p.add_argument("--output-chromadb-path", default=DEFAULT_OUTPUT_CHROMADB)
    p.add_argument("--collection-physical", default=DEFAULT_COLLECTION_PHYSICAL)
    p.add_argument("--target-embedder", default="bge-m3")
    p.add_argument("--target-dim", type=int, default=1024)
    p.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--dry-run", action="store_true", help="Walk files and report counts; don't embed")
    args = p.parse_args()

    if not os.path.isdir(args.articles_dir):
        print(f"FATAL: articles dir not found: {args.articles_dir}", file=sys.stderr)
        return 2

    if args.dry_run:
        files = walk_articles(args.articles_dir)
        print(f"DRY RUN: {len(files)} .md files in {args.articles_dir}")
        return 0

    assert_target_embedder_available(args.target_embedder, args.ollama_url)

    try:
        report = build(
            articles_dir=args.articles_dir,
            output_chromadb_path=args.output_chromadb_path,
            collection_physical=args.collection_physical,
            target_model=args.target_embedder,
            target_dim=args.target_dim,
            ollama_url=args.ollama_url,
            batch_size=args.batch_size,
        )
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    print("\n=== REPORT ===")
    print(json.dumps(report, indent=2))

    # Cutover instructions
    print(
        f"""
=== NEXT STEPS (cutover) ===
1. rsync the intermediate ChromaDB to the server:
   rsync -av --progress {args.output_chromadb_path}/ cloud-ora:{args.output_chromadb_path}/

2. Bring the server's Ora code current (pulls embedding.py refactor + chromadb.json):
   ssh cloud-ora "cd ~/ora && git pull origin main"

3. Pull bge-m3 on the server:
   ssh cloud-ora "ollama pull {args.target_embedder}"

4. Run the import companion to copy the v2 collection into the server's main ChromaDB:
   ssh cloud-ora "~/ora/.venv/bin/python3 ~/ora/scripts/import-msi-bge-m3.py \\
       --source {args.output_chromadb_path} --collection {args.collection_physical}"

5. Edit the server's ~/ora/config/chromadb.json:
   - embedder.model: "{args.target_embedder}"
   - embedder.dim: {args.target_dim}
   - collections.msi_news_articles: "{args.collection_physical}"
   (and similarly for the other logical names if they have v2 collections on the server.)

6. Re-embed the small msi_conversations collection in place on server (separate step).

7. Restart the server orchestrator. MSI's news_index lookups now query bge-m3.
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
