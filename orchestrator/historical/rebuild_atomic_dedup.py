"""Rebuild the ChromaDB `atomic_dedup` collection from vault atomic notes.

The HNSW index of `atomic_dedup` was destroyed by a runaway sparse-file
issue. SQLite still claims 122k entries but `get` raises InternalError.
This script:

  1. Drops the broken collection.
  2. Creates a fresh `atomic_dedup` collection.
  3. Walks ~/Documents/vault/Engrams/*.md, embeds each via Ollama
     nomic-embed-text, and bulk-adds with stable ids.

Idempotent: skip files whose stable id is already present in the new
collection (resume from interruption).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import chromadb
import yaml


VAULT_ROOT = "/Users/oracle/Documents/vault/Engrams"
CHROMA_PATH = "/Users/oracle/ora/chromadb"
COLLECTION = "atomic_dedup"


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_note(path: Path) -> tuple[dict, str, str]:
    """Return (frontmatter, title, body)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, path.stem, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[m.end():]
    title = path.stem
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            break
    return fm, title, body


def stable_id(path: Path) -> str:
    """Deterministic id from filename — survives content edits."""
    h = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:14]
    return f"atomic-{h}"


def embedding_text(title: str, body: str) -> str:
    return f"{title}\n\n{body}".strip()


def embed_via_ollama(text: str, *, timeout: int = 60) -> list[float]:
    payload = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["embedding"]


def metadata_for(fm: dict, title: str, path: Path) -> dict:
    meta = {
        "title": title,
        "vault_path": str(path),
        "note_type": (
            (fm.get("tags") or [None, None])[1]
            if isinstance(fm.get("tags"), list) and len(fm.get("tags") or []) > 1
            else ""
        ),
        "source_side": fm.get("source_side") or "",
        "source_chat": fm.get("source_chat") or "",
        "source_path": fm.get("source_path") or "",
        "source_format": fm.get("source_format") or "",
        "source_label": fm.get("source_label") or "",
        "source_platform": fm.get("source_platform") or "",
        "chain_id": fm.get("chain_id") or "",
        "when": (fm.get("date created") or fm.get("processed_at") or "") and str(fm.get("date created") or fm.get("processed_at")),
        "seen_count": int(fm.get("seen_count", 1) or 1),
    }
    # ChromaDB requires str/int/float/bool only, no None
    return {k: v for k, v in meta.items() if v not in (None, "")}


def process_one(path_str: str) -> tuple[str, list[float] | None, str, dict, str]:
    """Returns (id, embedding, document, metadata, error)."""
    p = Path(path_str)
    try:
        fm, title, body = parse_note(p)
    except Exception as e:
        return ("", None, "", {}, f"parse: {e}")
    text = embedding_text(title, body)
    if len(text.strip()) < 30:
        return ("", None, "", {}, "skip:short")
    try:
        emb = embed_via_ollama(text)
    except Exception as e:
        return ("", None, "", {}, f"embed: {e}")
    return (stable_id(p), emb, text, metadata_for(fm, title, p), "")


def rebuild(
    *,
    drop_existing: bool = True,
    max_workers: int = 16,
    batch_size: int = 500,
) -> None:
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    if drop_existing:
        try:
            client.delete_collection(COLLECTION)
            print(f"dropped existing {COLLECTION}", flush=True)
        except Exception as e:
            print(f"delete attempt: {e}", flush=True)

    col = client.get_or_create_collection(COLLECTION)
    print(f"created {COLLECTION}, count={col.count()}", flush=True)

    # Build set of already-present ids for resume
    have = set()
    try:
        offset = 0
        while offset < col.count():
            page = col.get(limit=5000, offset=offset)
            have.update(page["ids"] or [])
            if not page["ids"]:
                break
            offset += len(page["ids"])
    except Exception:
        pass
    print(f"existing in fresh collection: {len(have)}", flush=True)

    # Walk vault
    paths = sorted(Path(VAULT_ROOT).glob("*.md"))
    todo = [str(p) for p in paths if stable_id(p) not in have]
    print(f"vault notes: {len(paths)}, to embed: {len(todo)}", flush=True)
    if not todo:
        return

    t0 = time.time()
    pending: list[tuple] = []  # (id, emb, doc, meta)
    processed = 0
    errors = 0

    def flush_batch():
        if not pending:
            return
        ids = [r[0] for r in pending]
        embs = [r[1] for r in pending]
        docs = [r[2] for r in pending]
        metas = [r[3] for r in pending]
        try:
            col.add(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        except Exception as e:
            print(f"  add failed for batch of {len(pending)}: {e}", flush=True)
        pending.clear()

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, p): p for p in todo}
        for fut in as_completed(futures):
            try:
                rid, emb, doc, meta, err = fut.result()
            except Exception as e:
                err = f"executor: {e}"
                rid = emb = doc = meta = None
            if err:
                if not err.startswith("skip:"):
                    errors += 1
                continue
            pending.append((rid, emb, doc, meta))
            if len(pending) >= batch_size:
                flush_batch()
            processed += 1
            if processed % 1000 == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0.0
                eta = (len(todo) - processed) / rate if rate > 0 else 0
                print(
                    f"  [{processed}/{len(todo)}] errors={errors} "
                    f"rate={rate:.1f}/s eta={int(eta/60)}m count={col.count()}",
                    flush=True,
                )
    flush_batch()
    print(f"DONE — processed={processed}, errors={errors}, final_count={col.count()}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--keep-existing", action="store_true",
                   help="Don't drop the existing collection first")
    p.add_argument("--max-workers", type=int, default=16)
    args = p.parse_args()
    rebuild(drop_existing=not args.keep_existing, max_workers=args.max_workers)
