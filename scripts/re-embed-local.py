#!/usr/bin/env python3
"""Parallel-collection re-embed for Ora's ChromaDB.

Reads documents from existing (v1) collections, re-embeds them via a new
embedder model (e.g. bge-m3) using Ollama's batch /api/embed endpoint, and
writes the resulting vectors + docs + metadata into new (v2) collections in
the same ChromaDB instance. The v1 collections stay untouched and keep
serving queries until the orchestrator cuts over.

Usage:
    re-embed-local.py \\
        --target-embedder bge-m3 \\
        --target-dim 1024 \\
        --suffix _v2 \\
        --collections knowledge,conversations,atomics,conversations_incognito

    --dry-run                   Report doc counts per collection, don't write
    --resume-from COLLECTION    Resume after a crash for one specific collection
    --batch-size 32             Docs per Ollama /api/embed call (default 32)
    --fetch-size 1000           Docs per ChromaDB.get() page (default 1000)
    --checkpoint-every 1000     Docs between checkpoint writes (default 1000)

Cutover sequence:
    1. ollama pull <target-embedder>
    2. Run this script. v1 collections still active.
    3. Verify v2 counts match v1 counts.
    4. Edit ~/ora/config/chromadb.json: switch embedder + collection physical
       names to the v2 set. Restart orchestrator. Live on new embedder.
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

# Reach into the ora orchestrator so we share embedding.py's logical->physical
# collection translation. Logical names are used throughout this script.
sys.path.insert(0, os.path.expanduser("~/ora"))

from orchestrator.embedding import COLLECTIONS, resolve_collection  # noqa: E402

DEFAULT_CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_CHECKPOINT_FILE = "/tmp/re-embed-local.checkpoint.json"


# ---------------------------------------------------------------------------
# Ollama batch embedding via /api/embed
# ---------------------------------------------------------------------------


def ollama_embed_batch(
    texts: list[str],
    *,
    model: str,
    url: str,
    timeout: float = 120.0,
    attempts: int = 3,
) -> list[list[float]]:
    """Call Ollama /api/embed with a batch of texts. Returns one vector per
    text in the same order. Retries up to `attempts` times with linear
    backoff on transient errors.
    """
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
                print(f"  [warn] Ollama embed batch failed (attempt {attempt}/{attempts}): {e}; retrying in {wait}s", file=sys.stderr, flush=True)
                time.sleep(wait)
    assert last_err is not None
    raise last_err


def assert_target_embedder_available(model: str, url: str) -> None:
    """Verify Ollama is up and the target embedder has been pulled."""
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        raise SystemExit(f"FATAL: Cannot reach Ollama at {url}: {e}\nTry: ollama serve")
    names = [m.get("name", "") for m in data.get("models", []) or []]
    if not any(model in n for n in names):
        raise SystemExit(
            f"FATAL: Target embedder '{model}' not pulled.\n"
            f"Run: ollama pull {model}"
        )


# ---------------------------------------------------------------------------
# Checkpoint file
# ---------------------------------------------------------------------------


def load_checkpoint(path: str) -> dict:
    """Returns a dict mapping logical_collection -> {last_id_idx, total_ids, target_physical}.
    Missing or unreadable returns empty dict.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


def save_checkpoint(path: str, data: dict) -> None:
    tmp = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Re-embed a single collection
# ---------------------------------------------------------------------------


def reembed_collection(
    client,
    *,
    logical_name: str,
    source_physical: str,
    target_physical: str,
    target_model: str,
    target_dim: int,
    ollama_url: str,
    batch_size: int,
    fetch_size: int,
    checkpoint_file: str,
    resume_from_idx: int | None,
) -> dict:
    """Re-embed one collection. Returns a per-collection report dict."""
    from chromadb.utils import embedding_functions

    print(f"\n=== {logical_name}: {source_physical}  ->  {target_physical} ===", file=sys.stderr, flush=True)

    # Open source. embedding_function is None — we only call .get(), which
    # doesn't need to embed.
    try:
        source = client.get_collection(name=source_physical)
    except Exception:
        # Source doesn't exist (e.g. conversations-incognito on a system
        # that hasn't used incognito chat yet). Skip with a warning rather
        # than fataling — post-cutover, get_or_create_collection will
        # create a fresh bge-m3-bound collection on first use.
        print(f"  SKIP: source '{source_physical}' does not exist", file=sys.stderr, flush=True)
        return {
            "logical_name": logical_name,
            "source_physical": source_physical,
            "target_physical": target_physical,
            "source_count": 0,
            "target_count": 0,
            "docs_processed": 0,
            "docs_skipped_empty": 0,
            "elapsed_seconds": 0.0,
            "match": True,
            "skipped": True,
        }

    source_count = source.count()
    print(f"  source count: {source_count}", file=sys.stderr, flush=True)

    # Open or create target. Bind the new embedding_function so post-cutover
    # query_texts() calls embed through bge-m3.
    target_embed_fn = embedding_functions.OllamaEmbeddingFunction(
        url=ollama_url,
        model_name=target_model,
    )
    try:
        target = client.get_collection(
            name=target_physical,
            embedding_function=target_embed_fn,
        )
        target_existing_count = target.count()
        print(f"  target exists with {target_existing_count} docs (resuming)", file=sys.stderr, flush=True)
    except Exception:
        target = client.create_collection(
            name=target_physical,
            metadata={"hnsw:space": "cosine"},
            embedding_function=target_embed_fn,
        )
        target_existing_count = 0
        print(f"  target created fresh", file=sys.stderr, flush=True)

    # Fetch all ids first, sort, then iterate by id slices. This gives us a
    # stable iteration order across resume runs (ChromaDB's get() without
    # ids is not guaranteed-ordered, so paginating by offset is fragile).
    print(f"  fetching id list...", file=sys.stderr, flush=True)
    all_ids_resp = source.get(include=[])
    all_ids: list[str] = sorted(all_ids_resp.get("ids") or [])
    print(f"  total ids: {len(all_ids)}", file=sys.stderr, flush=True)

    start_idx = resume_from_idx if resume_from_idx is not None else 0
    if start_idx > 0:
        print(f"  resuming from idx {start_idx}", file=sys.stderr, flush=True)

    started_at = time.time()
    docs_processed = 0
    docs_skipped_empty = 0
    last_checkpoint_at = start_idx

    idx = start_idx
    while idx < len(all_ids):
        # Fetch a page of ids from source.
        page_ids = all_ids[idx : idx + fetch_size]
        page = source.get(ids=page_ids, include=["documents", "metadatas"])
        # CRITICAL: chromadb's get(ids=[...]) returns rows in STORAGE order,
        # NOT in the requested `page_ids` order. ids/documents/metadatas in the
        # response are aligned with each OTHER, so we must zip the RETURNED ids
        # (page.get("ids")) with the returned docs/metas — never `page_ids`.
        # Zipping page_ids here welds each id to another row's doc+meta, which
        # silently corrupted the v2 collections in the 2026-05-29 migration
        # (id↔payload misalignment; doc+meta stayed mutually consistent).
        page_ret_ids: list[str] = page.get("ids") or []
        page_docs: list[str] = page.get("documents") or []
        page_metas: list[dict] = page.get("metadatas") or []
        # Filter out empty docs — Ollama embed errors on empty strings.
        keep_ids: list[str] = []
        keep_docs: list[str] = []
        keep_metas: list[dict] = []
        for pid, pdoc, pmeta in zip(page_ret_ids, page_docs, page_metas):
            if not pdoc or not str(pdoc).strip():
                docs_skipped_empty += 1
                continue
            keep_ids.append(pid)
            keep_docs.append(str(pdoc))
            keep_metas.append(pmeta if isinstance(pmeta, dict) else {})

        # Embed in sub-batches of `batch_size` per Ollama call.
        all_embeddings: list[list[float]] = []
        for sub_start in range(0, len(keep_docs), batch_size):
            sub = keep_docs[sub_start : sub_start + batch_size]
            sub_embeddings = ollama_embed_batch(
                sub, model=target_model, url=ollama_url
            )
            for vec in sub_embeddings:
                if len(vec) != target_dim:
                    raise SystemExit(
                        f"FATAL: Ollama returned vector of dim {len(vec)}, "
                        f"expected {target_dim} for model {target_model}"
                    )
            all_embeddings.extend(sub_embeddings)

        if keep_ids:
            # Upsert into target. ChromaDB's add() refuses duplicate ids; use
            # upsert() so a resumed run can re-process the same page safely.
            target.upsert(
                ids=keep_ids,
                embeddings=all_embeddings,
                documents=keep_docs,
                metadatas=keep_metas,
            )
            docs_processed += len(keep_ids)

        idx += len(page_ids)

        # Checkpoint every N docs.
        if idx - last_checkpoint_at >= 1000:
            ckpt = load_checkpoint(checkpoint_file)
            ckpt[logical_name] = {
                "last_id_idx": idx,
                "total_ids": len(all_ids),
                "target_physical": target_physical,
                "target_model": target_model,
                "updated_at": time.time(),
            }
            save_checkpoint(checkpoint_file, ckpt)
            last_checkpoint_at = idx
            elapsed = time.time() - started_at
            rate = docs_processed / elapsed if elapsed > 0 else 0
            pct = (idx / len(all_ids)) * 100 if all_ids else 100
            print(f"  progress: {idx}/{len(all_ids)} ({pct:.1f}%)  rate: {rate:.1f} docs/sec", file=sys.stderr, flush=True)

    # Final verify
    target_final_count = target.count()
    elapsed = time.time() - started_at
    report = {
        "logical_name": logical_name,
        "source_physical": source_physical,
        "target_physical": target_physical,
        "source_count": source_count,
        "target_count": target_final_count,
        "docs_processed": docs_processed,
        "docs_skipped_empty": docs_skipped_empty,
        "elapsed_seconds": round(elapsed, 1),
        "match": target_final_count == source_count - docs_skipped_empty,
    }

    # Clear this collection's checkpoint on success.
    if report["match"]:
        ckpt = load_checkpoint(checkpoint_file)
        ckpt.pop(logical_name, None)
        save_checkpoint(checkpoint_file, ckpt)

    print(
        f"  DONE: source={source_count} target={target_final_count} "
        f"skipped_empty={docs_skipped_empty} match={report['match']} "
        f"({elapsed:.0f}s)",
        file=sys.stderr,
        flush=True,
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
    p.add_argument("--target-embedder", required=True, help="Target Ollama embedding model (e.g. bge-m3)")
    p.add_argument("--target-dim", type=int, required=True, help="Expected vector dimension for the target embedder (e.g. 1024)")
    p.add_argument("--suffix", default="_v2", help="Appended to physical collection names for the target (default _v2)")
    p.add_argument(
        "--collections",
        default=",".join(COLLECTIONS.keys()),
        help=f"Comma-separated logical collection names to re-embed (default: all in chromadb.json: {','.join(COLLECTIONS.keys())})",
    )
    p.add_argument("--batch-size", type=int, default=32, help="Docs per Ollama /api/embed call")
    p.add_argument("--fetch-size", type=int, default=1000, help="Docs per ChromaDB get() page")
    p.add_argument("--chromadb-path", default=DEFAULT_CHROMADB_PATH)
    p.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    p.add_argument("--checkpoint-file", default=DEFAULT_CHECKPOINT_FILE)
    p.add_argument(
        "--resume-from",
        help="<logical_name>[,<start_idx>] — resume one collection from the given id index (default: read from checkpoint file)",
    )
    p.add_argument("--dry-run", action="store_true", help="Report source counts only, don't write")
    args = p.parse_args()

    try:
        import chromadb
    except ImportError:
        print("FATAL: chromadb not installed. Run: pip3 install chromadb", file=sys.stderr)
        return 1

    # Validate target embedder is reachable + pulled.
    if not args.dry_run:
        assert_target_embedder_available(args.target_embedder, args.ollama_url)

    requested_logical = [c.strip() for c in args.collections.split(",") if c.strip()]
    for logical in requested_logical:
        if logical not in COLLECTIONS:
            print(f"WARNING: '{logical}' not in chromadb.json COLLECTIONS map; will pass through as physical name", file=sys.stderr)

    client = chromadb.PersistentClient(path=args.chromadb_path)

    if args.dry_run:
        print("DRY RUN — source counts only, no writes\n")
        total = 0
        for logical in requested_logical:
            phys_src = resolve_collection(logical)
            phys_tgt = f"{phys_src}{args.suffix}"
            try:
                src = client.get_collection(name=phys_src)
                count = src.count()
                total += count
                print(f"  {logical}: source={phys_src} count={count}  -> target={phys_tgt}")
            except Exception:
                print(f"  {logical}: source={phys_src} (does not exist; would skip)")
        print(f"\nTotal docs to re-embed: {total}")
        return 0

    # Parse --resume-from
    resume_logical: str | None = None
    resume_idx: int | None = None
    if args.resume_from:
        parts = args.resume_from.split(",", 1)
        resume_logical = parts[0].strip()
        if len(parts) == 2 and parts[1].strip():
            resume_idx = int(parts[1].strip())
        else:
            ckpt = load_checkpoint(args.checkpoint_file)
            resume_idx = (ckpt.get(resume_logical) or {}).get("last_id_idx")
            if resume_idx is None:
                print(f"FATAL: No checkpoint found for '{resume_logical}' in {args.checkpoint_file}", file=sys.stderr)
                return 1

    reports: list[dict] = []
    for logical in requested_logical:
        phys_src = resolve_collection(logical)
        phys_tgt = f"{phys_src}{args.suffix}"
        # Auto-resume if checkpoint exists for this collection and no explicit resume_from passed.
        auto_resume_idx: int | None = None
        if args.resume_from is None:
            ckpt = load_checkpoint(args.checkpoint_file)
            entry = ckpt.get(logical)
            if entry:
                auto_resume_idx = entry.get("last_id_idx")
                print(f"[auto-resume] {logical}: checkpoint at idx {auto_resume_idx}", file=sys.stderr)

        start_idx = resume_idx if logical == resume_logical else auto_resume_idx
        try:
            report = reembed_collection(
                client,
                logical_name=logical,
                source_physical=phys_src,
                target_physical=phys_tgt,
                target_model=args.target_embedder,
                target_dim=args.target_dim,
                ollama_url=args.ollama_url,
                batch_size=args.batch_size,
                fetch_size=args.fetch_size,
                checkpoint_file=args.checkpoint_file,
                resume_from_idx=start_idx,
            )
        except SystemExit:
            raise
        except Exception as e:
            print(f"FATAL during {logical}: {e}", file=sys.stderr)
            return 2
        reports.append(report)

    # Final report
    print("\n=== FINAL REPORT ===")
    print(json.dumps(reports, indent=2))
    all_match = all(r["match"] for r in reports)
    print(f"\nAll collections match: {all_match}")
    return 0 if all_match else 3


if __name__ == "__main__":
    sys.exit(main())
