#!/usr/bin/env python3
"""Promote ignored runtime model state into checked-in seed files.

Normal refreshes should not use this. It exists for maintainer moments where the
current runtime snapshot should become the repository's default seed state.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "data" / "runtime" / "config"

PAIRS = [
    (RUNTIME / "model-registry.json", ROOT / "config" / "model-registry.json"),
    (RUNTIME / "model-catalog.json", ROOT / "config" / "model-catalog.json"),
    (RUNTIME / "routing-config.json", ROOT / "config" / "routing-config.json"),
    (
        RUNTIME / "configurations" / "free.json",
        ROOT / "config" / "configurations" / "free.json",
    ),
    (
        RUNTIME / "configurations" / "budget.json",
        ROOT / "config" / "configurations" / "budget.json",
    ),
    (
        RUNTIME / "configurations" / "premium.json",
        ROOT / "config" / "configurations" / "premium.json",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="copy runtime files into config/")
    args = parser.parse_args()

    missing = [src for src, _ in PAIRS if not src.exists()]
    if missing:
        print("Cannot promote; missing runtime file(s):")
        for path in missing:
            print(f"  {path}")
        return 1

    print("Runtime model-state promotion plan:")
    for src, dst in PAIRS:
        print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to copy these seed files.")
        return 0

    for src, dst in PAIRS:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    print("\nPromoted runtime model state into seed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
