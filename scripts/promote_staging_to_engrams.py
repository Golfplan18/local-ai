#!/usr/bin/env python3
"""promote_staging_to_engrams.py — one-time backlog promotion CLI.

Thin wrapper over orchestrator.tools.engram_promotion. Promotes notes the
runtime pipeline left in ~/ora/data/extraction-staging/ into vault engrams (the
same operation the runtime pipeline now runs as its final step).

  python3 scripts/promote_staging_to_engrams.py --dry-run [--sample N]
  python3 scripts/promote_staging_to_engrams.py [--limit N]
"""
from __future__ import annotations

import argparse
import os
import sys

ORA_HOME = os.environ.get("ORA_HOME") or os.path.expanduser("~/ora")
if ORA_HOME not in sys.path:
    sys.path.insert(0, ORA_HOME)

from orchestrator.tools.engram_promotion import promote_staging_dir, STAGING_DIR


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="preview only; write nothing")
    ap.add_argument("--sample", type=int, default=0, help="with --dry-run, preview N notes")
    ap.add_argument("--limit", type=int, default=0, help="promote at most N notes")
    a = ap.parse_args()
    total = len([f for f in os.listdir(STAGING_DIR) if f.endswith(".md")]) \
        if os.path.isdir(STAGING_DIR) else 0
    limit = a.sample if (a.dry_run and a.sample) else a.limit
    print(f"staging notes: {total} total; "
          f"{'previewing' if a.dry_run else 'promoting'} "
          f"{limit or total}")
    res = promote_staging_dir(index=not a.dry_run, dry_run=a.dry_run, limit=limit)
    for i, r in enumerate(res["results"], 1):
        if a.dry_run:
            print("\n" + "=" * 96)
            print(f"[{i}] {os.path.basename(r['src'])}  ->  Engrams/{os.path.basename(r['dest'])}")
            print("-" * 96)
            print(r["preview"])
        else:
            print(f"[{i}] -> Engrams/{os.path.basename(r['dest'])}"
                  f"{'' if r.get('indexed') else '  (index skipped)'}")
    print(f"\n{'previewed' if a.dry_run else 'promoted'} {res['promoted']} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
