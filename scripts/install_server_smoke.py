#!/usr/bin/env python3
"""scripts/install_server_smoke.py — verify a server install is functional.

Invoked by scripts/install-server.sh as the final step. Confirms:

  1. routing-config.json loads via boot.load_routing_config().
  2. Every slot in slot_assignments resolves to an actual endpoint dict.
  3. No slot points at a local-mlx-* model (would mean the install
     rewrite skipped it).
  4. OPENROUTER_API_KEY (and ANTHROPIC_API_KEY if present) are reachable
     in the environment.
  5. ChromaDB can be imported (RAG path).

Exits non-zero on any failure. Prints a short per-step report.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
ORCHESTRATOR = WORKSPACE / "orchestrator"

# Make orchestrator/ importable so we can call into boot.py.
sys.path.insert(0, str(ORCHESTRATOR))


def log(msg: str) -> None:
    print(f"[smoke] {msg}", file=sys.stderr)


def step(name: str, fn) -> bool:
    try:
        fn()
        log(f"  ✓ {name}")
        return True
    except Exception as exc:
        log(f"  ✗ {name}: {exc}")
        return False


def check_routing_config_loads():
    from boot import load_routing_config  # noqa: WPS433
    rc = load_routing_config()
    assert "endpoints" in rc and rc["endpoints"], "endpoints[] empty"
    assert "slot_assignments" in rc and rc["slot_assignments"], "slot_assignments missing"
    # Stash on a side dict the next step can read.
    globals()["_rc"] = rc


def check_slots_resolve():
    rc = globals()["_rc"]
    endpoints_by_id = {e["id"]: e for e in rc["endpoints"] if "id" in e}
    bad = []
    for slot, model_id in rc["slot_assignments"].items():
        if model_id not in endpoints_by_id:
            bad.append((slot, model_id, "not in endpoints[]"))
            continue
        ep = endpoints_by_id[model_id]
        if not ep.get("enabled", True):
            bad.append((slot, model_id, "endpoint disabled"))
            continue
        if ep.get("status") not in (None, "active"):
            bad.append((slot, model_id, f"endpoint status={ep.get('status')}"))
    if bad:
        raise AssertionError(f"slot resolution issues: {bad}")


def check_no_local_models():
    rc = globals()["_rc"]
    bad = [(slot, mid) for slot, mid in rc["slot_assignments"].items()
           if mid.startswith("local-mlx-") or mid.startswith("local-ollama-")]
    if bad:
        raise AssertionError(f"slots still point at local models: {bad}")


def check_api_keys_present():
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise AssertionError(
            "OPENROUTER_API_KEY not in env — source ~/.config/ora-server.env "
            "or run with --skip-key if you've configured a different keychain"
        )


def check_chromadb_importable():
    import chromadb  # noqa: F401, WPS433


def main() -> int:
    log("Smoke testing server install …")
    ok = True
    ok &= step("routing-config.json loads",         check_routing_config_loads)
    ok &= step("every slot resolves to an endpoint", check_slots_resolve)
    ok &= step("no slot references a local model",   check_no_local_models)
    ok &= step("OPENROUTER_API_KEY in environment",  check_api_keys_present)
    ok &= step("chromadb is importable",             check_chromadb_importable)

    if ok:
        rc = globals()["_rc"]
        log("")
        log("Server install verified. Active slot assignments:")
        for slot, ep_id in rc["slot_assignments"].items():
            log(f"  {slot:14s} → {ep_id}")
        return 0
    else:
        log("")
        log("Smoke test FAILED. See above. The install is not ready for use.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
