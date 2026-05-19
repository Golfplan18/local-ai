#!/usr/bin/env python3
"""
scripts/verify-configuration-equivalence.py

Validates that the migrated configurations in config/configurations/ would
resolve to the same primary endpoint as the live Router does today for the
corresponding pipeline context.

For each (pipeline, slot, gear) tuple:
  - Call live Router.resolve_endpoint(slot, gear, context)
  - Compare the returned endpoint's canonical id to the primary in the new
    configuration file

Exits 0 on full equivalence, 1 if any mismatches.

Run:
    /opt/homebrew/bin/python3 scripts/verify-configuration-equivalence.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from orchestrator.router import Router

ROUTING_CONFIG = REPO_ROOT / "config" / "routing-config.json"
CONFIG_DIR = REPO_ROOT / "config" / "configurations"

# (pipeline_name, config_filename, slot, gear, cell_path)
CHECKS = [
    ("interactive", "user-pipeline.json", "step1_cleanup", 1, ["utility", "step1_cleanup"]),
    ("interactive", "user-pipeline.json", "classification", 1, ["utility", "classification"]),
    ("interactive", "user-pipeline.json", "rag_planner", 1, ["utility", "rag_planner"]),
    ("interactive", "user-pipeline.json", "depth", 4, ["analysis", "gear4", "depth"]),
    ("interactive", "user-pipeline.json", "breadth", 4, ["analysis", "gear4", "breadth"]),
    ("interactive", "user-pipeline.json", "depth", 3, ["analysis", "gear3", "depth"]),
    ("interactive", "user-pipeline.json", "consolidation", 4, ["post_analysis", "consolidation"]),
    ("interactive", "user-pipeline.json", "verification", 4, ["post_analysis", "verification"]),
    # agent pipeline
    ("agent", "background-default.json", "step1_cleanup", 1, ["utility", "step1_cleanup"]),
    ("agent", "background-default.json", "classification", 1, ["utility", "classification"]),
    ("agent", "background-default.json", "rag_planner", 1, ["utility", "rag_planner"]),
    ("agent", "background-default.json", "depth", 4, ["analysis", "gear4", "depth"]),
    ("agent", "background-default.json", "breadth", 4, ["analysis", "gear4", "breadth"]),
    ("agent", "background-default.json", "consolidation", 4, ["post_analysis", "consolidation"]),
    ("agent", "background-default.json", "verification", 4, ["post_analysis", "verification"]),
]


def lookup_id(endpoint):
    """Same id rule as the migration script (raw endpoint id, no canonicalization)."""
    return endpoint.get("id", "")


def cell_at(cfg, path):
    cur = cfg["cells"]
    for k in path:
        cur = cur.get(k)
        if cur is None:
            return None
    return cur


def main():
    router = Router(config_path=str(ROUTING_CONFIG))
    print(f"Loaded Router from {ROUTING_CONFIG}")

    configs = {}
    for fname in ("user-pipeline.json", "background-default.json"):
        path = CONFIG_DIR / fname
        with open(path) as f:
            configs[fname] = json.load(f)

    mismatches = []
    matches = 0
    for context, fname, slot, gear, cell_path in CHECKS:
        live_ep = router.resolve_endpoint(slot=slot, gear=gear, context=context)
        live_id = lookup_id(live_ep) if live_ep else None

        cfg = configs[fname]
        cell = cell_at(cfg, cell_path)
        config_primary = cell["primary"] if cell else None

        match = live_id == config_primary
        if match:
            matches += 1
            print(f"  ✓ {context:12s} {'.'.join(cell_path):40s} → {config_primary}")
        else:
            mismatches.append((context, cell_path, live_id, config_primary))
            print(f"  ✗ {context:12s} {'.'.join(cell_path):40s} → live={live_id!r}, config={config_primary!r}")

    print()
    print(f"Result: {matches}/{len(CHECKS)} matches")
    if mismatches:
        print(f"        {len(mismatches)} mismatches")
        sys.exit(1)
    print("Migration is behavior-equivalent to live Router. ✓")


if __name__ == "__main__":
    main()
