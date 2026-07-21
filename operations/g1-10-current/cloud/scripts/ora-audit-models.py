#!/usr/bin/env python3
"""Audit the OpenRouter pricing of every model our writing slots can hit.

Reads ~/ora/config/routing-config.json, queries OpenRouter's /models API,
and for each configured model:
  - confirms it is still present in the catalog
  - confirms its pricing.prompt and pricing.completion are both 0

If anything has changed, writes ~/ora-cost-alert.flag with a summary so
the Mac-side sync picks it up and surfaces it to the user, and exits non-
zero so the daily audit emits a failure record.

Run at the exact daily audit deadline. OpenRouter exposes no authenticated
catalog-change callback; this read-only query is the recorded runtime-
impossibility exception. The 30-second cost of one GET is negligible.

Models that legitimately don't appear in the /models endpoint (like
managed routers, e.g. `openrouter/free`) are tracked in EXPECTED_ABSENT.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROUTING_CONFIG = Path.home() / "ora" / "config" / "routing-config.json"
ENV_FILE       = Path.home() / ".config" / "ora-server.env"
ALERT_FILE     = Path.home() / "cloud-outbox" / "ora-cost-alert.flag"
LOG_FILE       = Path.home() / "ora-audit-models.log"

# Routers / aggregate entries that legitimately don't appear in /models —
# they're routing endpoints, not concrete model identifiers.
EXPECTED_ABSENT = {"openrouter/free", "openrouter/auto"}

API_URL = "https://openrouter.ai/api/v1/models"


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end="")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except OSError:
        pass


def load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def fetch_models(api_key: str) -> list[dict]:
    req = urllib.request.Request(API_URL, headers={
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "ora-cost-audit/1.0",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body.get("data", [])


def configured_models(rc: dict) -> set[str]:
    """Every model id reachable through writing-slot routing."""
    out: set[str] = set()
    out.update(rc.get("slot_assignments", {}).values())
    out.add(rc.get("default_endpoint", ""))
    for name, bucket in (rc.get("buckets") or {}).items():
        # audit every writing AND utility bucket — cost-protection policy says zero-cost
        if name in ("premium", "fast") and isinstance(bucket, list):
            out.update(bucket)
    out.discard("")
    return out


def is_free(model_entry: dict) -> bool:
    """OpenRouter prices come as strings ('0' or '0.000001'). Both must be 0."""
    pricing = model_entry.get("pricing") or {}
    for key in ("prompt", "completion"):
        try:
            v = float(pricing.get(key, 0))
        except (TypeError, ValueError):
            return False
        if v != 0.0:
            return False
    return True


def main() -> int:
    if not ROUTING_CONFIG.is_file():
        log(f"FATAL: routing-config.json missing at {ROUTING_CONFIG}")
        return 2

    api_key = load_api_key()
    if not api_key:
        log("FATAL: OPENROUTER_API_KEY not in env or ora-server.env")
        return 2

    rc = json.loads(ROUTING_CONFIG.read_text())
    targets = configured_models(rc)
    log(f"auditing {len(targets)} model(s) against OpenRouter catalog")

    try:
        catalog = fetch_models(api_key)
    except Exception as e:
        log(f"FATAL: catalog fetch failed: {type(e).__name__}: {e}")
        return 2

    by_id = {m.get("id"): m for m in catalog if m.get("id")}

    problems: list[str] = []
    for mid in sorted(targets):
        if mid in EXPECTED_ABSENT:
            log(f"  ✓ {mid} (router; expected absent from /models)")
            continue
        entry = by_id.get(mid)
        if entry is None:
            problems.append(f"NOT IN CATALOG: {mid}")
            log(f"  ✗ {mid} — removed from OpenRouter catalog")
            continue
        if not is_free(entry):
            pricing = entry.get("pricing") or {}
            problems.append(
                f"NO LONGER FREE: {mid} "
                f"(prompt={pricing.get('prompt')}, "
                f"completion={pricing.get('completion')})"
            )
            log(f"  ✗ {mid} — pricing changed: {pricing}")
            continue
        log(f"  ✓ {mid} (free)")

    if problems:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ALERT_FILE.write_text(
            f"COST ALERT — {ts}\n"
            + "\n".join(problems)
            + "\n\n"
            + "Action: edit ~/ora/config/routing-config.json::buckets.premium "
            + "to remove or replace the affected models. Backfill orchestrator "
            + "should be paused until resolved.\n"
        )
        log(f"WROTE {ALERT_FILE} — {len(problems)} issue(s)")
        return 1

    # Clean run — remove any stale alert
    if ALERT_FILE.exists():
        ALERT_FILE.unlink()
        log("cleared stale alert flag")
    log("all configured models verified free")
    return 0


if __name__ == "__main__":
    sys.exit(main())
