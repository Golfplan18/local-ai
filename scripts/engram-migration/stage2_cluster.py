#!/usr/bin/env python3
"""Stage 2 — cluster pass 1 over the existing atomic embeddings.

ONE-TIME MIGRATION TOOL. Delete this directory once the engram permanent-note
migration has landed; nothing in the running system imports it.

Reads the embeddings already present in the ChromaDB atomics collection (no
API calls, no re-embedding) and groups near-duplicate notes so Stage 3 can
process one unit per concept instead of one unit per note.

Leader clustering, NOT connected components. Measured on this corpus:
connected-components at 0.75 chains 42,677 notes into a single blob, because
dense topical regions link transitively. Leader clustering caps the largest
cluster at ~204 by assigning each note to the densest unclaimed seed within
threshold, never transitively.

Threshold 0.75 is calibrated, not guessed: known same-concept families (the
68 productivity-wage-gap notes) have median internal similarity 0.60 and p95
0.80; random pairs sit at median 0.25, p99 0.49. 0.75 sits above the random
tail and captures the tight core of a real family. It deliberately does NOT
catch cross-domain restatements -- those are invisible to embeddings and are
recovered by the lexical second pass in Stage 8, after generalization.

Output: units.jsonl (one JSON object per unit) plus sharded batches for
Stage 3. Every note on disk appears in exactly one unit.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

DEFAULT_THRESHOLD = 0.75
DEFAULT_BATCH = 60          # units per Stage 3 shard
DEFAULT_MAX_UNIT = 12       # members per unit before splitting
DEFAULT_SHARD_CHARS = 120_000   # ~30k tokens of source per model call


def load_embeddings(chroma_path: str, collection: str, cache_dir: Path):
    """Pull embeddings + metadata, caching to disk so reruns are instant."""
    emb_p, meta_p = cache_dir / "emb.npy", cache_dir / "meta.json"
    if emb_p.exists() and meta_p.exists():
        print(f"[stage2] using cached embeddings at {cache_dir}", flush=True)
        return np.load(emb_p, mmap_mode="r"), json.loads(meta_p.read_text())

    import chromadb
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_path)
    col = client.get_collection(collection)
    total = col.count()
    print(f"[stage2] pulling {total:,} embeddings from {collection}", flush=True)
    chunks, meta = [], []
    off, B = 0, 2000
    while off < total:
        g = col.get(limit=B, offset=off, include=["embeddings", "metadatas"])
        e = g.get("embeddings")
        if e is None or len(e) == 0:
            break
        chunks.append(np.asarray(e, dtype=np.float32))
        meta.extend(g.get("metadatas") or [])
        off += len(e)
    X = np.vstack(chunks)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)
    np.save(emb_p, X)
    meta_p.write_text(json.dumps(
        [{"t": (m or {}).get("title", ""), "p": (m or {}).get("vault_path", "")} for m in meta]))
    return np.load(emb_p, mmap_mode="r"), json.loads(meta_p.read_text())


def build_edges(X, threshold: float, cache: Path):
    """Upper-triangle pairs at/above threshold. Cached; chunked matmul."""
    p = cache / f"edges_{threshold:.2f}.npz"
    if p.exists():
        d = np.load(p)
        print(f"[stage2] using cached edges ({len(d['sim']):,})", flush=True)
        return d["src"], d["dst"]
    n = X.shape[0]
    Xf = np.asarray(X, dtype=np.float32)
    src, dst = [], []
    CH = 2048
    for s in range(0, n, CH):
        e = min(s + CH, n)
        S = Xf[s:e] @ Xf.T
        for r in range(e - s):
            S[r, s + r] = -1.0
        ii, jj = np.where(S >= threshold)
        keep = (ii + s) < jj
        ii, jj = ii[keep], jj[keep]
        if len(ii):
            src.append((ii + s).astype(np.int32))
            dst.append(jj.astype(np.int32))
        if s % 20480 == 0:
            print(f"[stage2]   {e:,}/{n:,}", flush=True)
    src = np.concatenate(src) if src else np.array([], dtype=np.int32)
    dst = np.concatenate(dst) if dst else np.array([], dtype=np.int32)
    np.savez_compressed(p, src=src, dst=dst, sim=np.zeros(len(src), dtype=np.float32))
    return src, dst


def leader_cluster(src, dst, n: int, alive: set[int]):
    """Assign each note to the densest unclaimed seed within threshold.

    Non-transitive by construction: a note joins a leader's cluster, and a
    cluster never absorbs another cluster's members. This is what prevents
    the chain-collapse that connected components suffers at this threshold.
    """
    adj = defaultdict(list)
    for a, b in zip(src, dst):
        a, b = int(a), int(b)
        if a in alive and b in alive:
            adj[a].append(b)
            adj[b].append(a)
    assigned: dict[int, int] = {}
    clusters: list[list[int]] = []
    for lead in sorted(adj.keys(), key=lambda i: -len(adj[i])):
        if lead in assigned:
            continue
        members = [lead]
        assigned[lead] = lead
        for nb in adj[lead]:
            if nb not in assigned:
                assigned[nb] = lead
                members.append(nb)
        clusters.append(members)
    singles = [i for i in sorted(alive) if i not in assigned]
    return clusters, singles


def read_note(path: Path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    parts = txt.split("---", 2)
    if len(parts) < 3:
        return None
    fm, body = parts[1], parts[2]
    m = re.search(r"^# (.+)$", body, re.M)
    if not m:
        return None
    tags = re.findall(
        r"^\s*-\s+(fact|principle|causal|definition|analogy|evaluative|"
        r"ai_synthesis|ai_framework|ai_evidence)\s*$", fm, re.M)
    side = re.search(r"^source_side:\s*(\w+)", fm, re.M)
    return {
        "file": path.name,
        "title": m.group(1).strip(),
        "body": body[m.end():].split("## Source")[0].strip()[:900],
        "type": tags[0] if tags else "",
        "side": side.group(1) if side else "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engrams", default=str(Path.home() / "engram-work" / "Engrams"))
    ap.add_argument("--chromadb", default=str(Path.home() / "ora" / "chromadb"))
    ap.add_argument("--collection", default="atomic_dedup_qwen_qwen3_embedding_8b")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--out", required=True, help="output directory for units + shards")
    ap.add_argument("--cache", default=None, help="embedding/edge cache dir (default: <out>/cache)")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--shard-chars", type=int, default=DEFAULT_SHARD_CHARS,
                    help="pack shards to this many source characters")
    ap.add_argument("--max-unit", type=int, default=DEFAULT_MAX_UNIT,
                    help="split clusters larger than this into sub-units "
                         "sharing a parent_id (bounded work per model call)")
    args = ap.parse_args()

    engrams = Path(args.engrams)
    if not engrams.is_dir():
        print(f"[stage2] ERROR: {engrams} is not a directory", file=sys.stderr)
        return 2
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache) if args.cache else out / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    X, meta = load_embeddings(args.chromadb, args.collection, cache)
    n = X.shape[0]

    on_disk = {p for p in os.listdir(engrams) if p.endswith(".md")}
    idx_to_file: dict[int, str] = {}
    for i, m in enumerate(meta):
        b = os.path.basename(m.get("p", "") or "")
        if b in on_disk and b not in idx_to_file.values():
            idx_to_file[i] = b
    alive = set(idx_to_file)
    print(f"[stage2] chroma records={n:,}  resolving to a note on disk={len(alive):,}  "
          f"orphans={n - len(alive):,}", flush=True)

    src, dst = build_edges(X, args.threshold, cache)
    clusters, singles = leader_cluster(src, dst, n, alive)
    sizes = [len(c) for c in clusters]
    print(f"[stage2] threshold={args.threshold}  clusters={len(clusters):,}  "
          f"clustered notes={sum(sizes):,}  singletons={len(singles):,}  "
          f"largest cluster={max(sizes) if sizes else 0}", flush=True)

    # notes covered by a cluster are never also emitted as singletons
    covered = {i for c in clusters for i in c}
    assert not (covered & set(singles)), "a note landed in both a cluster and the singleton list"
    assert covered | set(singles) == alive, "every on-disk note must appear in exactly one unit"

    # Oversized clusters are split into bounded sub-units. Asking one model
    # call to enumerate the distinct claims across 204 notes is where facets
    # get silently dropped -- and a dropped facet is unrecoverable, since the
    # members are deleted once merged. Sub-units share a parent_id so Stage 5
    # rejoins their claim lists into a single concept note.
    units, skipped, split_parents = [], 0, 0
    for k, members in enumerate(clusters + [[s] for s in singles]):
        notes = []
        for i in members:
            rec = read_note(engrams / idx_to_file[i])
            if rec:
                notes.append(rec)
        if not notes:
            skipped += 1
            continue
        parent = f"u{k:06d}"
        if len(notes) <= args.max_unit:
            units.append({"unit_id": parent, "parent_id": parent,
                          "size": len(notes), "members": notes})
            continue
        split_parents += 1
        for part, s in enumerate(range(0, len(notes), args.max_unit)):
            chunk = notes[s:s + args.max_unit]
            units.append({"unit_id": f"{parent}.{part:02d}", "parent_id": parent,
                          "size": len(chunk), "members": chunk})

    with (out / "units.jsonl").open("w") as fh:
        for u in units:
            fh.write(json.dumps(u) + "\n")

    # Pack shards by CONTENT SIZE, not unit count. Units are emitted largest
    # cluster first, so fixed-count shards put every big cluster in the first
    # few files -- shard 0 came out at 270k tokens while late shards of pure
    # singletons were trivial. Size-packing keeps every model call comparable.
    shard_dir = out / "shards"; shard_dir.mkdir(exist_ok=True)
    shards, cur, cur_chars = [], [], 0
    for u in units:
        c = sum(len(m["title"]) + len(m["body"]) for m in u["members"])
        if cur and cur_chars + c > args.shard_chars:
            shards.append(cur); cur, cur_chars = [], 0
        cur.append(u); cur_chars += c
    if cur:
        shards.append(cur)
    for k, sh in enumerate(shards):
        (shard_dir / f"shard_{k:04d}.json").write_text(json.dumps(sh, indent=1))
    packed = [sum(len(m["title"]) + len(m["body"]) for u in sh for m in u["members"])
              for sh in shards]
    print(f"[stage2] shards={len(shards):,}  units/shard: min={min(len(s) for s in shards)} "
          f"max={max(len(s) for s in shards)}  chars/shard: max={max(packed):,}")

    print(f"[stage2] oversized clusters split into sub-units: {split_parents:,}")
    multi = sum(1 for u in units if u["size"] > 1)
    absorbed = sum(u["size"] - 1 for u in units)
    print(f"[stage2] units={len(units):,}  multi-note units={multi:,}  "
          f"notes absorbed into a unit={absorbed:,}  unreadable notes skipped={skipped:,}")
    print(f"[stage2] wrote {out/'units.jsonl'} and {len(shards):,} shards -> {shard_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
