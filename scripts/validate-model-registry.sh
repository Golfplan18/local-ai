#!/bin/bash
# validate-model-registry.sh — Validates model registry (endpoints.json).
# Checks slot assignments, capability gaps, and endpoint reachability.

set -uo pipefail

ORA_DIR="${HOME}/ora"
CONFIG_DIR="${ORA_DIR}/config"

# Find Python: Homebrew (macOS), then system python3
if [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    echo "ERROR: python3 not found. Install Python 3.10+ first." >&2
    exit 1
fi

echo "=== Model Registry Validation ==="

$PYTHON << 'PYEOF'
import json
import os
import urllib.request
import sys

config_path = os.path.expanduser("~/ora/config/endpoints.json")

with open(config_path) as f:
    config = json.load(f)

endpoints = {ep["name"]: ep for ep in config["endpoints"]}
slots = config.get("slot_assignments", {})
errors = []
warnings = []

# Check all slot assignments have available models
print("\n--- Slot Assignments ---")
required_slots = ["sidebar", "step1_cleanup", "breadth", "depth", "evaluator", "consolidator", "rag_planner"]
for slot in required_slots:
    if slot not in slots:
        errors.append(f"Missing slot assignment: {slot}")
        print(f"  {slot}: MISSING")
    elif slots[slot] not in endpoints:
        errors.append(f"Slot '{slot}' assigned to unknown endpoint: {slots[slot]}")
        print(f"  {slot}: {slots[slot]} (UNKNOWN ENDPOINT)")
    else:
        ep = endpoints[slots[slot]]
        status = ep.get("status", "unknown")
        print(f"  {slot}: {slots[slot]} ({status})")
        if status != "active":
            warnings.append(f"Slot '{slot}' assigned to inactive endpoint: {slots[slot]}")

# Check capability fields present
print("\n--- Capability Flags ---")
for name, ep in endpoints.items():
    missing = []
    for field in ["tool_access", "file_system_access", "web_access", "retrieval_approach"]:
        if field not in ep:
            missing.append(field)
    if missing:
        warnings.append(f"Endpoint '{name}' missing capability fields: {', '.join(missing)}")
        print(f"  {name}: MISSING {', '.join(missing)}")
    else:
        approach = ep["retrieval_approach"]
        fs = "fs" if ep["file_system_access"] else "no-fs"
        tools = "tools" if ep["tool_access"] else "no-tools"
        print(f"  {name}: {approach} ({fs}, {tools})")

# Check local model endpoints reachable
print("\n--- Endpoint Reachability ---")
for name, ep in endpoints.items():
    if ep["type"] == "local" and ep.get("status") == "active":
        # Local models served via MLX on default port
        try:
            req = urllib.request.Request("http://localhost:8080/v1/models", method="GET")
            req.add_header("Connection", "close")
            urllib.request.urlopen(req, timeout=3)
            print(f"  {name}: REACHABLE (localhost:8080)")
        except Exception:
            print(f"  {name}: NOT RUNNING (localhost:8080)")
            # Not an error — models may not be loaded yet

# Hardware tier detection
print("\n--- Hardware Tier ---")
import subprocess
result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
if result.returncode == 0:
    ram_bytes = int(result.stdout.strip())
    ram_gb = ram_bytes / (1024**3)
    print(f"  Total RAM: {ram_gb:.0f} GB")

    local_active = [ep for ep in config["endpoints"] if ep["type"] == "local" and ep.get("status") == "active"]
    total_model_ram = sum(ep.get("ram_required_gb", 0) for ep in local_active)
    print(f"  Active local models: {len(local_active)} (total RAM: {total_model_ram} GB)")

    if len(local_active) == 0:
        tier = "Tier 1 (no local model)"
    elif len(local_active) == 1:
        tier = "Tier 2 (single local model)"
    elif total_model_ram < ram_gb * 0.8:
        tier = "Tier 4 (full local stack)"
    else:
        tier = "Tier 3 (constrained local stack)"
    print(f"  Hardware tier: {tier}")

# Summary
print("\n--- Summary ---")
if errors:
    print(f"ERRORS: {len(errors)}")
    for e in errors:
        print(f"  ✗ {e}")
if warnings:
    print(f"WARNINGS: {len(warnings)}")
    for w in warnings:
        print(f"  ⚠ {w}")
if not errors and not warnings:
    print("All checks passed.")

sys.exit(1 if errors else 0)
PYEOF
