#!/usr/bin/env python3
"""Rewrite every merged note from the FULL text of its own source notes.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Replaces stage5_run.py, which implemented the approach that failed. Every choice
here is a measurement, not a preference:

  FULL SOURCE TEXT, never extracts. The previous pass received member titles plus
  a list of "specifics" mined from the bodies -- isolated keywords, bare dates,
  filename debris. It assembled those fragments into fluent Instance lines, and a
  50-note audit found every edited note needed its evidence line changed. The
  qualifying clauses that carry the claims ("despite the dual mandate of price
  stability and full employment", "without any elected official casting a vote")
  live in the bodies, so a writer that never saw the bodies could not keep them.
  56% of notes lost at least one claim.

  BATCH 1. Blind-judged on 8 notes with 2 judges: Opus met the owner's bar 16/16
  at batch 1 and 12/16 at batch 8. Batching costs about a quarter of the quality.
  --batch is available for measuring, but 1 is the measured default.

  OPUS. Same test: Sonnet 2/16 and Haiku 0/16 at batch 8. Tier and batch are
  confounded in those two numbers, so batch-1 figures for the cheaper tiers may be
  better -- but nothing below Opus has yet met the bar.

  SHARDING, so N independent processes cannot collide. Resume works by checking
  which output files exist, which means two processes sharing a worklist would both
  claim the same undone note. --shard k/N partitions deterministically by a hash of
  the note filename, so eight terminals, eight machines, or eight sessions can each
  take a slice with no coordination and no overlap.

  ONE OUTPUT FILE PER NOTE. 64k small files rather than shard-sized aggregates:
  resume is an existence check, a killed process loses at most the calls in flight,
  and no two writers ever touch the same file.

Dry run by default. --apply performs the model calls and writes results. Nothing
here modifies the vault; stage7 does that, from these results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ORA_HOME = os.environ.get("ORA_HOME", str(Path.home() / "ora"))
if ORA_HOME not in sys.path:
    sys.path.insert(0, ORA_HOME)

ARCHIVE_SUBDIR = "Archive/Engram Absorbed Sources 2026-08"
MODEL_HINT = "claude-opus-4-6"

_ABSORBED = re.compile(r"^absorbed_from:\s*\n((?:[ \t]*-[ \t]+\S.*\n)+)", re.M)
_H1 = re.compile(r"^#\s+(.+)$", re.M)
_FENCE = re.compile(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", re.DOTALL)
_lock = threading.Lock()


def body_of(text: str) -> str:
    parts = text.split("---", 2)
    s = parts[2] if len(parts) > 2 else text
    return re.sub(r"\n##\s+Source\b.*$", "", s, flags=re.S).strip()


def absorbed_of(text: str) -> list[str]:
    m = _ABSORBED.search(text)
    if not m:
        return []
    return [ln.strip().lstrip("-").strip().strip("'\"")
            for ln in m.group(1).splitlines() if ln.strip()]


def shard_of(name: str, n: int) -> int:
    """Deterministic, stable across processes and runs. Not Python's hash(),
    which is salted per interpreter and would reshard on every launch."""
    return int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], 16) % n


def parse_reply(text: str) -> dict | None:
    raw = (text or "").strip()
    m = _FENCE.search(raw)
    if m:
        raw = m.group(1)
    if not raw.startswith(("{", "[")):
        i = min([x for x in (raw.find("{"), raw.find("[")) if x >= 0] or [-1])
        j = max(raw.rfind("}"), raw.rfind("]"))
        if i < 0 or j <= i:
            return None
        raw = raw[i:j + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def build_user(units: list[dict]) -> str:
    """Full source text. No extracts, no truncation of the claims themselves."""
    payload = [{
        "note_id": u["note_id"],
        "current_note": u["current_note"],
        "originals": [{"file": o["file"], "full_text": o["full_text"]} for o in u["originals"]],
    } for u in units]
    n = len(units)
    return (
        f"Rewrite {'this note' if n == 1 else f'each of these {n} notes'} from the "
        f"full text of its own source notes.\n\n"
        "`current_note` is the previous attempt. It is evidence of a failure mode, "
        "NOT a draft to edit — write fresh from the sources.\n\n"
        "Return ONLY a JSON object: {\"notes\": [{\"note_id\": ..., \"verdict\": "
        "\"KEEP\"|\"SPLIT\"|\"ARCHIVE\", \"title\": ..., \"body\": ..., "
        "\"conversion\": ..., \"domain_bound\": true|false, \"split_second_note\": "
        "{\"title\": ..., \"body\": ...}}]}\n\n"
        "`body` is the bullet lines, each starting \"- \". Use SPLIT when the "
        "sources carry two claims one note would have to fudge — 20% of "
        "multi-source groups do, and 8% actually contradict each other; put the "
        "second claim in split_second_note. Use ARCHIVE only when the general form "
        "would be a truism.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", default=str(Path.home() / "engram-work"))
    ap.add_argument("--out", default=None, help="default <vault>/.migration/rewrite")
    ap.add_argument("--prompt", default=str(Path(__file__).with_name("rewrite_prompt.md")))
    ap.add_argument("--backend", default="claude-cli",
                    choices=("api", "claude-cli", "ora-slots", "openrouter"))
    ap.add_argument("--batch", type=int, default=1,
                    help="notes per model call. 1 is measured-optimal; 8 costs ~25%% "
                         "of quality. Raise only to re-measure.")
    ap.add_argument("--workers", type=int, default=8,
                    help="concurrent calls. Pure throughput, no quality effect — "
                         "the real ceiling is the provider's rate limit.")
    ap.add_argument("--shard", default=None, metavar="K/N",
                    help="process only shard K of N (0-indexed). Lets N independent "
                         "processes run with no coordination and no overlap.")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true", help="make the calls (default: dry run)")
    args = ap.parse_args()

    vault = Path(args.vault)
    engrams = vault / "Engrams"
    archive = vault / ARCHIVE_SUBDIR
    outdir = Path(args.out) if args.out else vault / ".migration" / "rewrite"
    for p in (engrams, archive):
        if not p.is_dir():
            print(f"[rewrite] missing {p}", file=sys.stderr)
            return 2
    outdir.mkdir(parents=True, exist_ok=True)
    system = Path(args.prompt).read_text(encoding="utf-8")

    shard_k = shard_n = None
    if args.shard:
        try:
            shard_k, shard_n = (int(x) for x in args.shard.split("/"))
            assert 0 <= shard_k < shard_n
        except Exception:
            print("[rewrite] --shard must look like 3/8 with 0 <= K < N", file=sys.stderr)
            return 2

    print("[rewrite] indexing archived source notes...", flush=True)
    arch: dict[str, str] = {}
    for p in archive.glob("*.md"):
        arch[p.name] = body_of(p.read_text(encoding="utf-8", errors="replace"))
    print(f"[rewrite]   {len(arch):,} originals")

    units: list[dict] = []
    skipped_no_src = 0
    for p in sorted(engrams.glob("*.md")):
        if shard_n is not None and shard_of(p.name, shard_n) != shard_k:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if "migration: permanent-note" not in text:
            continue
        dest = outdir / (p.stem + ".json")
        if dest.exists():
            continue
        srcs = [{"file": fn, "full_text": arch[fn]} for fn in absorbed_of(text) if fn in arch]
        if not srcs:
            skipped_no_src += 1
            continue
        units.append({"note_id": p.stem, "dest": dest,
                      "current_note": body_of(text), "originals": srcs})
    if args.limit:
        units = units[:args.limit]

    batches = [units[i:i + args.batch] for i in range(0, len(units), args.batch)]
    src_chars = sum(len(o["full_text"]) for u in units for o in u["originals"])
    already = len(list(outdir.glob("*.json")))
    print(f"[rewrite] shard={args.shard or 'all'}  todo={len(units):,}  "
          f"already done={already:,}  no-sources={skipped_no_src:,}")
    print(f"[rewrite] batch={args.batch} workers={args.workers} backend={args.backend}")
    print(f"[rewrite] source text {src_chars/1e6:.1f}M chars (~{src_chars//4:,} tok) "
          f"+ {len(system)//4:,} tok system per call (cacheable)")
    if not units:
        print("[rewrite] nothing to do")
        return 0
    if not args.apply:
        print("\n[rewrite] DRY RUN. Sample payload (truncated):\n")
        print(build_user(batches[0])[:1200])
        print(f"\n[rewrite] re-run with --apply to make {len(batches):,} calls")
        return 0

    from orchestrator.historical.cleanup_backends import build_client
    client = build_client(args.backend)
    agg = {"ok": 0, "failed": 0, "notes": 0, "split": 0, "archive": 0,
           "in": 0, "out": 0, "cost": 0.0}
    start = time.monotonic()

    def run(batch: list[dict]) -> None:
        res = client.call(system=system, user=build_user(batch),
                          model=MODEL_HINT, max_tokens=4096 * len(batch),
                          temperature=0.0)
        with _lock:
            agg["in"] += getattr(res, "input_tokens", 0) or 0
            agg["out"] += getattr(res, "output_tokens", 0) or 0
            agg["cost"] += getattr(res, "cost_usd", 0.0) or 0.0
        if getattr(res, "error", ""):
            with _lock:
                agg["failed"] += 1
            return
        parsed = parse_reply(res.text)
        recs = (parsed or {}).get("notes") if isinstance(parsed, dict) else parsed
        if not isinstance(recs, list) or not recs:
            with _lock:
                agg["failed"] += 1
            print(f"[rewrite] unusable reply for {batch[0]['note_id'][:48]}", file=sys.stderr)
            return
        by_id = {u["note_id"]: u for u in batch}
        for rec in recs:
            u = by_id.get(rec.get("note_id"))
            if not u or not rec.get("title"):
                continue
            rec["source_files"] = [o["file"] for o in u["originals"]]
            tmp = u["dest"].with_suffix(".tmp")
            tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(u["dest"])
            with _lock:
                agg["notes"] += 1
                if rec.get("verdict") == "SPLIT":
                    agg["split"] += 1
                elif rec.get("verdict") == "ARCHIVE":
                    agg["archive"] += 1
        with _lock:
            agg["ok"] += 1

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run, b) for b in batches]
        done = 0
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:
                with _lock:
                    agg["failed"] += 1
                print(f"[rewrite] worker error: {type(e).__name__}: {e}", file=sys.stderr)
            done += 1
            if done % 25 == 0 or done == len(batches):
                el = time.monotonic() - start
                rate = done / max(0.1, el)
                eta = (len(batches) - done) / max(1e-6, rate) / 3600
                per = (agg["in"] + agg["out"]) / max(1, agg["notes"])
                print(f"[rewrite] {done:,}/{len(batches):,}  notes={agg['notes']:,}  "
                      f"{el/60:.0f}m  ETA {eta:.1f}h  {per:.0f} tok/note  "
                      f"${agg['cost']:.2f}  fail={agg['failed']}", flush=True)

    el = time.monotonic() - start
    print(f"\n[rewrite] done in {el/3600:.2f}h — {agg['ok']:,} calls ok, "
          f"{agg['failed']:,} failed, {agg['notes']:,} notes written")
    print(f"[rewrite]   SPLIT={agg['split']:,}  ARCHIVE={agg['archive']:,}")
    print(f"[rewrite]   tokens in={agg['in']:,} out={agg['out']:,} "
          f"({(agg['in']+agg['out'])/max(1,agg['notes']):.0f}/note)  cost=${agg['cost']:.2f}")
    print("[rewrite] re-run the same command to retry failures and continue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
