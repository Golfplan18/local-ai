#!/usr/bin/env python3
"""scripts/install_server_config.py — rewrite routing-config.json for server use.

Invoked by scripts/install-server.sh during a cloud / server install.
Server installs run API-only (no local MLX models), so all slots must
point at API endpoints. This script:

  1. Reads config/routing-config.json (must exist — clone the repo first).
  2. Confirms every needed API endpoint id is present in the endpoints[]
     list (so the rewrite doesn't dangle a slot at a missing model).
  3. Overwrites slot_assignments to API-only picks:
       - utility slots (sidebar, step1_cleanup, rag_planner, classification)
         → anthropic-api-haiku (cheap, low-latency)
       - workhorse slots (breadth, depth, evaluator, consolidator)
         → anthropic-api-sonnet-4-5 (analysis quality, vision-capable)
  4. Overwrites default_endpoint to anthropic-api-sonnet-4-5.
  5. Writes a backup at config/routing-config.json.pre-server-install
     unless one already exists.

Idempotent — re-runnable.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
ROUTING_CONFIG = WORKSPACE / "config" / "routing-config.json"
BACKUP = WORKSPACE / "config" / "routing-config.json.pre-server-install"

# Picks chosen for cheap continuous publication routed through OpenRouter.
# Using OpenRouter for everything means the server only needs ONE API key
# (OPENROUTER_API_KEY); direct anthropic-api / openai-api endpoints would
# require additional per-provider keys for no operational benefit.
#
# MSI's article generator picks its own model via the MSI_AUTHOR_MODEL env
# var (Sonnet forward, Haiku backfill) — independent of these slot picks,
# which drive only the gear pipeline (cleanup, classification, eval, etc.).
SERVER_SLOT_ASSIGNMENTS = {
    "sidebar":        "qwen/qwen3.6-35b-a3b",
    "step1_cleanup":  "qwen/qwen3.6-35b-a3b",
    "classification": "qwen/qwen3.6-35b-a3b",
    "rag_planner":    "qwen/qwen3.6-35b-a3b",
    "breadth":        "qwen/qwen3.6-plus",
    "depth":          "qwen/qwen3.6-plus",
    "evaluator":      "qwen/qwen3.6-plus",
    "consolidator":   "qwen/qwen3.6-plus",
}
SERVER_DEFAULT_ENDPOINT = "qwen/qwen3.6-plus"
SERVER_GEAR4_OVERRIDES = {
    "depth":   {"enabled": True, "endpoint": "qwen/qwen3.6-plus"},
    "breadth": {"enabled": True, "endpoint": "qwen/qwen3.6-plus"},
}


def log(msg: str) -> None:
    print(f"[install-server-config] {msg}", file=sys.stderr)


def main() -> int:
    if not ROUTING_CONFIG.exists():
        log(f"✗ {ROUTING_CONFIG} not found. Did the git clone complete?")
        return 1

    with open(ROUTING_CONFIG) as f:
        cfg = json.load(f)

    endpoint_ids = {e.get("id") for e in cfg.get("endpoints", []) if e.get("id")}
    needed_ids = set(SERVER_SLOT_ASSIGNMENTS.values()) | {SERVER_DEFAULT_ENDPOINT}
    missing = needed_ids - endpoint_ids
    if missing:
        log(f"✗ routing-config.json::endpoints[] is missing: {sorted(missing)}")
        log("  Run 'python scripts/refresh-catalog.py' first, or pick "
            "different endpoints below in SERVER_SLOT_ASSIGNMENTS.")
        return 2

    # Backup once.
    if not BACKUP.exists():
        shutil.copy2(ROUTING_CONFIG, BACKUP)
        log(f"  ✓ Backed up original to {BACKUP.name}")
    else:
        log(f"  ✓ Backup already at {BACKUP.name} (kept)")

    # Apply server-flavor overrides.
    cfg["slot_assignments"] = SERVER_SLOT_ASSIGNMENTS
    cfg["default_endpoint"] = SERVER_DEFAULT_ENDPOINT
    cfg["gear4_overrides"]  = SERVER_GEAR4_OVERRIDES

    # operational_context — keep "api" available everywhere on the server;
    # remove "local" so any code that still walks transports doesn't try
    # to pick a local model that doesn't exist on this host.
    cfg["operational_context"] = {
        "interactive": ["api"],
        "autonomous":  ["api"],
        "agent":       ["api"],
    }

    # Marker so a future install / sync can detect this file is server-flavor.
    cfg.setdefault("_schema_notes", {})
    cfg["_schema_notes"]["server_install_overrides_applied"] = (
        "Slot assignments + default_endpoint + gear4_overrides + "
        "operational_context were rewritten to API-only picks by "
        "scripts/install-server.sh. The original Mac-flavor file is "
        "backed up at routing-config.json.pre-server-install. To revert, "
        "swap the backup back in place and re-run the orchestrator."
    )

    with open(ROUTING_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)

    log(f"  ✓ Rewrote {ROUTING_CONFIG.name}")
    log("    slot_assignments → API-only picks:")
    for slot, ep in SERVER_SLOT_ASSIGNMENTS.items():
        log(f"      {slot:14s} → {ep}")
    log(f"    default_endpoint → {SERVER_DEFAULT_ENDPOINT}")
    log("    operational_context → api-only on all contexts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
