#!/usr/bin/env python3
"""Fail if model-refresh runtime activity dirtied tracked seed files."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WATCHED = [
    "config/model-catalog.json",
    "config/model-registry.json",
    "config/routing-config.json",
    "config/configurations/free.json",
    "config/configurations/budget.json",
    "config/configurations/premium.json",
    "data/model-catalog-changes.jsonl",
    "data/model-registry-discrepancies.jsonl",
]


def main() -> int:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", *WATCHED],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "git status failed", file=sys.stderr)
        return result.returncode
    dirty = [line for line in result.stdout.splitlines() if line.strip()]
    if dirty:
        print("Model refresh dirtied tracked seed files:")
        for line in dirty:
            print(f"  {line}")
        print("\nLive refreshes should write under data/runtime/.")
        print("Use scripts/promote-runtime-model-state.py --apply only for intentional seed updates.")
        return 1
    print("Model refresh seed-file drift: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
