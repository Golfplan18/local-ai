#!/usr/bin/env python3
"""Stage 5 input builder — pack KEEP units into shards for the Opus writer.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Each shard entry carries only what Stage 5 needs and nothing more:

  member_titles  the claim each source note made -- these ARE the facets
  specifics      verbatim entities Stage 3 pulled from the member bodies

Member BODIES are deliberately excluded. Twelve titles run ~400 tokens, about the
same as any brief built from the bodies, so paying for the bodies buys nothing --
and Stage 3 already lifted the one thing bodies carry that titles do not, which
is the concrete specifics.

Also reports which Stage 3 shards are missing or unparseable so they can be
re-run before Stage 5 starts; a lost shard is 100-300 units silently absent from
the output rather than a visible failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_SHARD_UNITS = 40


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    ap.add_argument("--units-per-shard", type=int, default=DEFAULT_SHARD_UNITS)
    ap.add_argument("--limit", type=int, default=0, help="pilot: cap total units")
    ap.add_argument("--out-name", default="stage5_shards")
    args = ap.parse_args()
    M = Path(args.migration)

    n_shards = len(list((M / "shards").glob("shard_*.json")))
    titles: dict[str, list[str]] = {}
    sizes: dict[str, int] = {}
    for p in sorted((M / "shards").glob("shard_*.json")):
        for u in json.loads(p.read_text()):
            titles[u["unit_id"]] = [m["title"] for m in u["members"]]
            sizes[u["unit_id"]] = u["size"]

    broken = []
    tri: dict[str, dict] = {}
    for i in range(n_shards):
        p = M / "stage3" / f"result_{i:04d}.json"
        if not p.exists():
            broken.append(i)
            continue
        try:
            recs = json.loads(p.read_text())
        except Exception:
            broken.append(i)
            continue
        for r in (recs if isinstance(recs, list) else recs.get("results", [])):
            if r.get("unit_id"):
                tri[r["unit_id"]] = r
    if broken:
        print(f"[stage5-build] WARNING: {len(broken)} Stage 3 shards missing/unparseable: "
              f"{broken}", file=sys.stderr)
        print(f"[stage5-build] re-run those before trusting the output "
              f"({sum(1 for u in titles if u not in tri):,} units currently untriaged)",
              file=sys.stderr)

    keeps = [u for u, r in tri.items() if r.get("verdict") == "KEEP" and u in titles]
    # Largest units first: facet absorption is where the value and the risk are,
    # so a pilot that reads the head of this list exercises the hard cases.
    keeps.sort(key=lambda u: -sizes.get(u, 1))
    if args.limit:
        keeps = keeps[:args.limit]

    units = [{
        "unit_id": u,
        "size": sizes.get(u, 1),
        "member_files": tri[u].get("member_files") or [],
        "member_titles": titles[u],
        "specifics": tri[u].get("specifics") or [],
    } for u in keeps]

    out = M / args.out_name
    out.mkdir(parents=True, exist_ok=True)
    for p in out.glob("shard_*.json"):
        p.unlink()
    k = 0
    for s in range(0, len(units), args.units_per_shard):
        (out / f"shard_{k:04d}.json").write_text(
            json.dumps(units[s:s + args.units_per_shard], indent=1))
        k += 1
    multi = sum(1 for u in units if u["size"] > 1)
    chars = sum(len(t) for u in units for t in u["member_titles"])
    print(f"[stage5-build] KEEP units: {len(units):,} ({multi:,} multi-member)")
    print(f"[stage5-build] title text: {chars:,} chars (~{chars//4:,} tokens) — "
          f"bodies excluded by design")
    print(f"[stage5-build] wrote {k:,} shards of {args.units_per_shard} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
