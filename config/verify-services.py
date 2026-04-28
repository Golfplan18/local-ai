#!/usr/bin/env python3
"""Verify each browser-automation service by sending a trivial test prompt.

Reports pass/fail per service, identifying which selectors need tuning.

Run:
    python3 ~/ora/config/verify-services.py               # all services
    python3 ~/ora/config/verify-services.py --service claude
    python3 ~/ora/config/verify-services.py --json        # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

WORKSPACE = Path(os.path.expanduser("~/ora"))
sys.path.insert(0, str(WORKSPACE / "orchestrator" / "tools"))

from browser_evaluate import browser_evaluate, SERVICE_CONFIG  # noqa: E402

TEST_PROMPT = (
    "Reply with the single word OK and absolutely nothing else. "
    "No punctuation, no explanation."
)
PASS_SUBSTR = "OK"


def verify(service: str) -> dict:
    start = time.time()
    try:
        response = browser_evaluate(service=service, prompt=TEST_PROMPT)
    except Exception as e:
        return {
            "service": service,
            "status": "exception",
            "message": str(e)[:200],
            "elapsed_s": round(time.time() - start, 1),
        }
    elapsed = round(time.time() - start, 1)

    if not response:
        return {"service": service, "status": "empty", "response": "", "elapsed_s": elapsed}
    if response.startswith("["):
        # Diagnostic messages from browser_evaluate itself (session issues,
        # channel failures, unknown service, etc.)
        return {
            "service": service,
            "status": "diagnostic",
            "response": response[:200],
            "elapsed_s": elapsed,
        }
    if PASS_SUBSTR in response.upper():
        return {
            "service": service,
            "status": "ok",
            "response": response[:80],
            "elapsed_s": elapsed,
        }
    return {
        "service": service,
        "status": "unexpected",
        "response": response[:200],
        "elapsed_s": elapsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser-automation services.")
    parser.add_argument("--service", help="Verify only this named service")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of human-readable output")
    args = parser.parse_args()

    services = [args.service] if args.service else sorted(SERVICE_CONFIG.keys())

    results = []
    for s in services:
        if not args.json:
            print(f"[verify] {s:14s} ...", end=" ", flush=True)
        r = verify(s)
        results.append(r)
        if not args.json:
            preview = r.get("response") or r.get("message") or ""
            print(f"{r['status']:12s} ({r['elapsed_s']}s)  {preview[:60]}")

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    # Summary
    ok = [r for r in results if r["status"] == "ok"]
    fail = [r for r in results if r["status"] != "ok"]
    print("\n── Summary ──")
    print(f"OK: {len(ok)} / {len(results)}")
    if fail:
        print("Failed (selector tuning or channel switch likely needed):")
        for r in fail:
            preview = r.get("response") or r.get("message") or ""
            print(f"  {r['service']:14s} {r['status']:12s} {preview[:120]}")
        print("\nTip: for a service with chronic Playwright selector drift, add")
        print('  "prefer_channel": "extension"  to its entry in browser-services.json')
        print("to route it through the Chrome extension bridge instead.")

    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
