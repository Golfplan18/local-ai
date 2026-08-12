#!/usr/bin/env python3
"""Stage 5 runner — write permanent notes, unattended and resumable.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

WHY A SCRIPT AND NOT AN AGENT WORKFLOW
--------------------------------------
Two reasons, both measured.

1. Coupling. A Workflow only runs while a chat session drives it, so progress
   stops when the session ends. This stage is ~1,600 batches; it needs to survive
   session boundaries, which means a process with a manifest.

2. Token burn. The agent pilot cost 4,475 tokens per unit. A batch of units in
   one agent context re-sends the agent's own accumulated output on every turn,
   so cost grows quadratically in the batch. A stateless call pays input + output
   once. Measured content is ~74 input + ~375 output tokens per unit; batching 20
   units per call and caching the system prompt brings the real figure to ~460
   tokens per unit -- a ~10x reduction, and the difference between ~30M tokens
   and ~283M.

   (The pilot's 4,475 also over-stated the corpus: units are ordered
   largest-first so the pilot exercises the hard facet-absorption cases, and
   units with 8+ members are only 2.7% of the corpus. Never extrapolate cost
   from the head of that ordering.)

BACKENDS
--------
Reuses the existing abstraction in orchestrator/historical/cleanup_backends.py:
  claude-cli   billed to the Claude subscription, no API key
  ora-slots    the publisher's own routing / local models
  openrouter   explicit OpenRouter route
  api          metered Anthropic API
Model choice belongs to the backend and the publisher's routing config, not here.

RESUME
------
One result file per batch, plus a manifest. The worklist is derived from what is
absent on disk, so an interrupted run costs only the batches in flight. Re-invoke
with the same arguments to continue; there is no separate resume flag.
"""
from __future__ import annotations

import argparse
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

DEFAULT_BATCH = 20
DEFAULT_WORKERS = 8
# Heavy tier: this stage is the one irreplaceable judgement in the migration.
# Haiku paraphrases where it is asked to transform (measured on 300 identical
# notes), so the tier hint must stay heavy regardless of backend.
MODEL_HINT = "claude-opus-4-6"

_FENCE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_lock = threading.Lock()


def load_prompt(path: Path) -> str:
    txt = path.read_text(encoding="utf-8")
    # Strip the markdown title line; the rest is the specification.
    return txt.strip()


def build_user(units: list[dict]) -> str:
    """One compact JSON payload. Member bodies are excluded by design -- see
    stage5_build.py; titles carry the claims and Stage 3 already lifted the
    specifics."""
    slim = [{
        "unit_id": u["unit_id"],
        "member_titles": u["member_titles"],
        "specifics": (u.get("specifics") or [])[:25],
    } for u in units]
    return (
        "Write ONE permanent note per unit, following the specification exactly.\n\n"
        "Return ONLY a JSON array, no prose and no code fence. One object per "
        "unit, preserving unit_id verbatim, with keys: unit_id, verdict, "
        "standard_concept, new_title, new_body, facets_absorbed, note.\n\n"
        "Set verdict to KEEP normally, or ARCHIVE if raising the claim's level "
        "would only produce a platitude.\n\n"
        + json.dumps(slim, ensure_ascii=False)
    )


def parse_batch(text: str, expect: list[str]) -> tuple[list[dict], str]:
    raw = text.strip()
    m = _FENCE.search(raw)
    if m:
        raw = m.group(1)
    if not raw.startswith("["):
        i, j = raw.find("["), raw.rfind("]")
        if i >= 0 and j > i:
            raw = raw[i:j + 1]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"json: {e}"
    if not isinstance(parsed, list):
        return [], "not a list"
    keep = [r for r in parsed if isinstance(r, dict) and r.get("unit_id")]
    missing = set(expect) - {r["unit_id"] for r in keep}
    return keep, (f"missing {len(missing)} of {len(expect)} units" if missing else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    ap.add_argument("--prompt", default=str(Path(__file__).with_name("stage5_prompt.md")))
    ap.add_argument("--backend", default="claude-cli",
                    choices=("api", "claude-cli", "ora-slots", "openrouter"))
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH,
                    help="units per model call — the main cost lever")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--limit", type=int, default=0, help="stop after N batches")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the worklist and one rendered payload, call nothing")
    args = ap.parse_args()

    M = Path(args.migration)
    outdir = M / "stage5"
    outdir.mkdir(parents=True, exist_ok=True)
    system = load_prompt(Path(args.prompt))

    # Worklist: every KEEP unit not already present in stage5 output.
    units: list[dict] = []
    for p in sorted((M / "stage5_shards").glob("shard_*.json")):
        units.extend(json.loads(p.read_text()))
    have: set[str] = set()
    for p in outdir.glob("result_*.json"):
        try:
            for r in json.loads(p.read_text()):
                if isinstance(r, dict) and r.get("unit_id"):
                    have.add(r["unit_id"])
        except Exception:
            continue
    todo = [u for u in units if u["unit_id"] not in have]
    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    if args.limit:
        batches = batches[:args.limit]

    est_in = sum(len(build_user(b)) for b in batches[:5]) / max(1, len(batches[:5])) / 4
    print(f"[stage5] units total={len(units):,} done={len(have):,} todo={len(todo):,}")
    print(f"[stage5] batches={len(batches):,} of {args.batch}  workers={args.workers}  "
          f"backend={args.backend}")
    print(f"[stage5] ~{est_in:.0f} input tokens per batch payload + "
          f"{len(system)//4:,} system (cacheable)")
    if not batches:
        print("[stage5] nothing to do")
        return 0
    if args.dry_run:
        print("\n--- sample payload (first batch, truncated) ---")
        print(build_user(batches[0])[:1200])
        return 0

    from orchestrator.historical.cleanup_backends import build_client
    client = build_client(args.backend)

    start = time.monotonic()
    agg = {"ok": 0, "failed": 0, "units": 0, "in": 0, "out": 0, "cost": 0.0}

    def run(idx: int, batch: list[dict]) -> None:
        # Batch index is derived from the first unit_id so a resumed run with a
        # different --batch cannot overwrite an earlier run's file.
        name = f"result_{batch[0]['unit_id'].replace('.', '_')}.json"
        dest = outdir / name
        if dest.exists():
            return
        res = client.call(system=system, user=build_user(batch),
                          model=MODEL_HINT, max_tokens=8192, temperature=0.0)
        with _lock:
            agg["in"] += getattr(res, "input_tokens", 0) or 0
            agg["out"] += getattr(res, "output_tokens", 0) or 0
            agg["cost"] += getattr(res, "cost_usd", 0.0) or 0.0
        if getattr(res, "error", ""):
            with _lock:
                agg["failed"] += 1
            return
        recs, err = parse_batch(res.text, [u["unit_id"] for u in batch])
        if not recs:
            with _lock:
                agg["failed"] += 1
            print(f"[stage5] batch {idx} unusable: {err}", file=sys.stderr)
            return
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(recs, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dest)          # atomic: a killed run never leaves half a file
        with _lock:
            agg["ok"] += 1
            agg["units"] += len(recs)
            if err:
                print(f"[stage5] batch {idx} partial: {err}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run, i, b): i for i, b in enumerate(batches)}
        done = 0
        for f in as_completed(futs):
            f.result()
            done += 1
            if done % 20 == 0 or done == len(batches):
                el = time.monotonic() - start
                rate = done / max(0.1, el)
                eta = (len(batches) - done) / max(1e-6, rate) / 60
                per = (agg["in"] + agg["out"]) / max(1, agg["units"])
                print(f"[stage5] {done:,}/{len(batches):,} batches  "
                      f"{agg['units']:,} units  {el/60:.0f}m elapsed  ETA {eta:.0f}m  "
                      f"{per:.0f} tok/unit  ${agg['cost']:.2f}", flush=True)

    print(f"[stage5] done: {agg['ok']:,} batches ok, {agg['failed']:,} failed, "
          f"{agg['units']:,} units written")
    print(f"[stage5] tokens in={agg['in']:,} out={agg['out']:,} "
          f"({(agg['in']+agg['out'])/max(1,agg['units']):.0f} per unit)  "
          f"cost=${agg['cost']:.2f}")
    print(f"[stage5] re-run the same command to retry failures and continue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
