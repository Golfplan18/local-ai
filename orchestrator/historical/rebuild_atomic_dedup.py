"""Rebuild the ChromaDB `atomic_dedup` collection from vault engram notes.

The dedup collection is a derived index — the vault engram files are
canonical — so dropping and rebuilding it is always safe. Rebuild when:

  * the embedder changes (the collection's persisted embedding function
    must match the canonical one in `orchestrator.embedding`, or every
    open/query fails with an embedding-function conflict);
  * engrams have been created outside phase5 (runtime promotion via
    `orchestrator/tools/engram_promotion.py` does NOT register in this
    collection, so a periodic rebuild keeps phase5's dedup aware of
    promoted engrams);
  * engrams have been deleted (e.g. the Refusal Leak junk purge) and
    their embeddings must leave the index.

v2 (2026-07-10): embeds through the canonical embedding function bound
by `orchestrator.embedding.get_or_create_collection` (no hardcoded
model, no direct Ollama calls), resolves the physical collection name
through the same config, and walks the vault RECURSIVELY (the v1 glob
missed `Engrams/Historical Atomics/<YYYY>/`).

CLI:

    /opt/homebrew/bin/python3 -m orchestrator.historical.rebuild_atomic_dedup
    /opt/homebrew/bin/python3 -m orchestrator.historical.rebuild_atomic_dedup --keep-existing
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import chromadb
import yaml


VAULT_ROOT = "/Users/oracle/Documents/vault/Engrams"
CHROMA_PATH = "/Users/oracle/ora/chromadb"
COLLECTION = "atomic_dedup"

# Documents are truncated to this length before embedding — dedup
# matching happens on the claim + opening body, not the full note.
MAX_EMBED_CHARS = 4000

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
    return f"{title}\n\n{body}".strip()[:MAX_EMBED_CHARS]


def metadata_for(fm: dict, title: str, path: Path) -> dict:
    meta = {
        "title": title,
        "vault_path": str(path),
        "source_chat": fm.get("source_chat") or "",
        "source_platform": fm.get("source_platform") or "",
        "when": (fm.get("date created") or fm.get("processed_at") or "")
                and str(fm.get("date created") or fm.get("processed_at")),
        "seen_count": int(fm.get("seen_count", 1) or 1),
    }
    # ChromaDB requires str/int/float/bool only, no None
    return {k: v for k, v in meta.items() if v not in (None, "")}


def _open_fresh_collection(drop_existing: bool):
    """Open the dedup collection bound to the CANONICAL embedder.

    On drop, both the resolved physical name and the bare legacy name
    are removed — a pre-migration collection may exist under either.
    """
    from orchestrator.embedding import (
        get_or_create_collection,
        resolve_collection,
    )
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    if drop_existing:
        for name in {resolve_collection(COLLECTION), COLLECTION}:
            try:
                client.delete_collection(name)
                print(f"dropped collection {name!r}", flush=True)
            except Exception:
                pass
    col = get_or_create_collection(client, COLLECTION)
    print(f"opened {COLLECTION!r} (physical: "
          f"{resolve_collection(COLLECTION)!r}), count={col.count()}",
          flush=True)
    return col


def rebuild(
    *,
    drop_existing: bool = True,
    max_workers: int = 8,
    batch_size: int = 100,
) -> dict:
    col = _open_fresh_collection(drop_existing)

    # Build set of already-present ids for resume.
    have: set[str] = set()
    try:
        offset = 0
        total = col.count()
        while offset < total:
            page = col.get(limit=5000, offset=offset, include=[])
            if not page["ids"]:
                break
            have.update(page["ids"])
            offset += len(page["ids"])
    except Exception:
        pass
    print(f"existing in collection: {len(have)}", flush=True)

    # Walk the vault RECURSIVELY — Historical Atomics live in
    # per-year subdirectories.
    paths = sorted(Path(VAULT_ROOT).rglob("*.md"))
    todo = [p for p in paths if stable_id(p) not in have]
    print(f"vault notes: {len(paths)}, to embed: {len(todo)}", flush=True)
    if not todo:
        return {"vault_notes": len(paths), "embedded": 0,
                "final_count": col.count()}

    t0 = time.time()
    processed = 0
    errors = 0
    pending: list[tuple[str, str, dict]] = []   # (id, doc, meta)

    def flush_batch() -> None:
        nonlocal errors
        if not pending:
            return
        try:
            # Embedding happens inside the collection's bound embedding
            # function — no model or endpoint is named here.
            col.upsert(
                ids=[r[0] for r in pending],
                documents=[r[1] for r in pending],
                metadatas=[r[2] for r in pending],
            )
        except Exception as e:
            print(f"  upsert failed for batch of {len(pending)}: "
                  f"{str(e)[:200]}", flush=True)
            errors += len(pending)
        pending.clear()

    def _parse(p: Path):
        try:
            fm, title, body = parse_note(p)
        except Exception as e:
            return None, f"parse: {e}"
        text = embedding_text(title, body)
        if len(text.strip()) < 30:
            return None, "skip:short"
        return (stable_id(p), text, metadata_for(fm, title, p)), ""

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_parse, p): p for p in todo}
        for fut in as_completed(futures):
            rec, err = fut.result()
            if err:
                if not err.startswith("skip:"):
                    errors += 1
                continue
            pending.append(rec)
            processed += 1
            if len(pending) >= batch_size:
                flush_batch()
            if processed % 2000 == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0.0
                eta = (len(todo) - processed) / rate if rate > 0 else 0
                print(f"  [{processed}/{len(todo)}] errors={errors} "
                      f"rate={rate:.1f}/s eta={int(eta / 60)}m "
                      f"count={col.count()}", flush=True)
    flush_batch()
    summary = {"vault_notes": len(paths), "embedded": processed,
               "errors": errors, "final_count": col.count(),
               "duration_secs": time.time() - t0}
    print(f"DONE — {summary}", flush=True)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--keep-existing", action="store_true",
                   help="Don't drop the existing collection first")
    p.add_argument("--max-workers", type=int, default=8)
    args = p.parse_args()
    rebuild(drop_existing=not args.keep_existing,
            max_workers=args.max_workers)
    sys.exit(0)
