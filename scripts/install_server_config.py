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
# Writing slots (breadth / depth / evaluator) carry a free-model fallback
# chain driven by the `premium` bucket ordering: when the primary free
# model rate-limits, the bucket walk falls through to the next free model;
# paid models sit at the bottom of the chain as a safety net so the chain
# can never exhaust. Throughput-first ordering (fastest free model first).
#
# MSI's article generator on the server uses `invoke_chat()` against the
# slot routing below; the older `claude_invoke.py` path (Mac-only, shells
# out to Claude Code) is bypassed on the server because Claude Code isn't
# installed there. See cloud-Ora plan phase (c-finalize / e).
PREMIUM_BUCKET_CHAIN = [
    "arcee-ai/trinity-large-thinking:free",      # primary — ~100 tok/s
    "deepseek/deepseek-v4-flash:free",           # backup 1 — ~35 tok/s
    "nvidia/nemotron-3-super-120b-a12b:free",    # backup 2
    "minimax/minimax-m2.5:free",                 # backup 3
    "openrouter/free",                            # managed free-pool auto-router
]
# NOTE: No paid safety net on the writing-slot chain. If every free
# option exhausts simultaneously, the call fails (task marked failed,
# backfill loop continues) — but no token charges. This is a deliberate
# cost-protection choice after a runaway-process incident. Daily
# ora-audit-models.py cron monitors that every model above is still in
# the OpenRouter catalog and still actually free.

# Endpoint entries to synthesize into routing-config.json::endpoints[] if
# missing (some of the free models above are in the catalog but not yet in
# the endpoints[] list of a fresh routing-config). Mirrors the shape of
# existing OpenRouter-routed endpoint entries.
NEW_FREE_ENDPOINTS = [
    ("arcee-ai/trinity-large-thinking:free", "Arcee: Trinity Large Thinking (free)", "arcee"),
    ("deepseek/deepseek-v4-flash:free",      "DeepSeek: V4 Flash (free)",            "deepseek"),
    ("minimax/minimax-m2.5:free",            "MiniMax: M2.5 (free)",                 "minimax"),
]

SERVER_SLOT_ASSIGNMENTS = {
    # Utility slots — NOTE these are still on a paid (cheap) model. Audit
    # script flags them; running a long backfill on these costs a few
    # cents per article in aggregate. Consider replacing with a free
    # alternative if backfill scale makes that material.
    "sidebar":        "qwen/qwen3.6-35b-a3b",
    "step1_cleanup":  "qwen/qwen3.6-35b-a3b",
    "classification": "qwen/qwen3.6-35b-a3b",
    "rag_planner":    "qwen/qwen3.6-35b-a3b",
    # Writing slots — free-only via PREMIUM_BUCKET_CHAIN fallback walk.
    "breadth":        PREMIUM_BUCKET_CHAIN[0],
    "depth":          PREMIUM_BUCKET_CHAIN[0],
    "evaluator":      PREMIUM_BUCKET_CHAIN[0],
    "consolidator":   PREMIUM_BUCKET_CHAIN[0],
}
SERVER_DEFAULT_ENDPOINT = PREMIUM_BUCKET_CHAIN[0]
SERVER_GEAR4_OVERRIDES = {
    "depth":   {"enabled": True, "endpoint": PREMIUM_BUCKET_CHAIN[0]},
    "breadth": {"enabled": True, "endpoint": PREMIUM_BUCKET_CHAIN[0]},
}


def _synthesize_missing_endpoints(cfg: dict) -> int:
    """Add minimal endpoint entries for NEW_FREE_ENDPOINTS members that are
    not already in cfg['endpoints'][]. Returns the count added. Idempotent.
    """
    existing_ids = {e.get("id") for e in cfg.get("endpoints", [])}
    added = 0
    for model_id, display, family in NEW_FREE_ENDPOINTS:
        if model_id in existing_ids:
            continue
        cfg.setdefault("endpoints", []).append({
            "id": model_id,
            "type": "api",
            "service": "openrouter",
            "model_id": model_id,
            "display_name": display,
            "provider": "openrouter",
            "training_family": family,
            "tier": "premium",
            "status": "active",
            "enabled": True,
            "credential_key": "ora/openrouter-api-key",
            "capabilities": {
                "tool_access": False,
                "file_system_access": False,
                "web_access": False,
                "retrieval_approach": "pre-assembled",
            },
            "vision_capable": False,
            "model": model_id,
            "_auto_synthesized": True,
        })
        added += 1
    return added


def log(msg: str) -> None:
    print(f"[install-server-config] {msg}", file=sys.stderr)


def main() -> int:
    if not ROUTING_CONFIG.exists():
        log(f"✗ {ROUTING_CONFIG} not found. Did the git clone complete?")
        return 1

    with open(ROUTING_CONFIG) as f:
        cfg = json.load(f)

    # Synthesize any missing free-model endpoints before the validation pass
    # so a clean install doesn't fail on the trinity chain not yet existing
    # in endpoints[].
    added = _synthesize_missing_endpoints(cfg)
    if added:
        log(f"  ✓ Synthesized {added} missing free-model endpoint entries")

    endpoint_ids = {e.get("id") for e in cfg.get("endpoints", []) if e.get("id")}
    needed_ids = (
        set(SERVER_SLOT_ASSIGNMENTS.values())
        | {SERVER_DEFAULT_ENDPOINT}
        | set(PREMIUM_BUCKET_CHAIN)
    )
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

    # Reorder the `premium` bucket so the bucket-walk fallback delivers the
    # trinity-first free-model chain (writing slots resolve into this bucket
    # for their fallback behavior — see PREMIUM_BUCKET_CHAIN definition).
    cfg.setdefault("buckets", {})["premium"] = list(PREMIUM_BUCKET_CHAIN)

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
