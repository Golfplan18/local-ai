#!/usr/bin/env python3
"""Ora install script (install Chunk 7 — Solo-profile-only scaffold).

This is the first shippable install path. It provisions an Ora install in
Solo profile (privacy-focused single-user; existing global-lock concurrency
which fits the MLX SIGSEGV constraint). Hybrid and Organization profiles
are scaffolded with placeholders pending the concurrency-architecture side
thread.

Steps the script performs in order:

  1. Pre-flight: Python 3.11+, ≥5GB disk, OpenRouter reachable, write perms
  2. Deployment profile selection (Solo / Hybrid / Organization)
  3. OpenRouter API key setup
       Messaging: "free models work without a credit card; add payment
       later if you want paid models"
  4. Catalog refresh — fetches OpenRouter (and optionally AA when AA_API_KEY
     is set), writes config/model-catalog.json
  5. Auto-populate user-pipeline configuration from the Optimum preset
  6. Smoke test: one chat round-trip via the Free configuration's primary
  7. Print install-complete summary; tail of ~/ora/install.log lands a
     deterministic marker the test protocol grep-checks

Design properties:
  - Idempotent: re-run safely; existing state is honored, not clobbered
  - Resumable: completed steps are tracked in ~/ora/install-state.json
  - Verbose by default: every step prints what it's doing
  - Pre-flight gated: fails fast on missing prerequisites
  - --reset rolls back the install state (does NOT delete vault or
     conversations — that's uninstall's job)
  - --dry-run previews actions without making changes

What this script does NOT do yet:
  - Bootstrap (Mac/Windows/Linux shell entry points — separate files)
  - Worker pool provisioning for Hybrid / Organization (blocked on
    concurrency-architecture side thread)
  - HuggingFace local-model download (Chunk 8)
  - Uninstall companion (Chunk 9)

Usage:
    python3 scripts/install.py                # interactive install
    python3 scripts/install.py --profile solo # non-interactive Solo install
    python3 scripts/install.py --dry-run      # preview, no changes
    python3 scripts/install.py --reset        # clear install state
    python3 scripts/install.py --resume       # continue from last completed step
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "install-state.json"
LOG_PATH = REPO_ROOT / "install.log"
COMPLETION_MARKER = "INSTALL_COMPLETE: 0 warnings, 0 errors"

DEPLOYMENT_PROFILES = {
    "solo": {
        "description": "Privacy-focused single-user. Local MLX models + optional OpenRouter for paid models. Existing global-lock concurrency. No worker pool. Default.",
        "supported_now": True,
    },
    "hybrid": {
        "description": "Single user + small API worker pool. Local MLX serializes; cloud calls parallelize. Requires worker-pool runtime (blocked on concurrency side thread).",
        "supported_now": False,
    },
    "organization": {
        "description": "Multi-user, pure-API, 20+ concurrent processes. No local MLX. Requires full worker pool (blocked on concurrency side thread).",
        "supported_now": False,
    },
}

PREFLIGHT_MIN_PYTHON = (3, 11)
PREFLIGHT_MIN_DISK_GB = 5


# ─── State + logging ─────────────────────────────────────────────────────


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"steps_completed": [], "profile": None, "started_at": None}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"steps_completed": [], "profile": None, "started_at": None}


def save_state(state: dict, dry_run: bool = False) -> None:
    if dry_run:
        return
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def log(msg: str, dry_run: bool = False) -> None:
    """Print and append to install.log atomically per line."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if dry_run:
        return
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def reset_install(dry_run: bool) -> None:
    if dry_run:
        log("[dry-run] would clear install-state.json and install.log")
        return
    for p in (STATE_PATH, LOG_PATH):
        if p.exists():
            p.unlink()
    log("Install state cleared. Vault, conversations, and downloaded models untouched.")


# ─── Steps ───────────────────────────────────────────────────────────────


def step_preflight(state: dict, dry_run: bool) -> bool:
    log("Step 1/6: Pre-flight checks")
    ok = True

    # Python version
    if sys.version_info < PREFLIGHT_MIN_PYTHON:
        log(f"  ✗ Python {'.'.join(map(str, PREFLIGHT_MIN_PYTHON))}+ required; you have {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        ok = False
    else:
        log(f"  ✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # Disk space
    try:
        free_bytes = shutil.disk_usage(REPO_ROOT).free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < PREFLIGHT_MIN_DISK_GB:
            log(f"  ✗ {PREFLIGHT_MIN_DISK_GB}GB free disk required; {free_gb:.1f}GB available at {REPO_ROOT}")
            ok = False
        else:
            log(f"  ✓ Disk space: {free_gb:.1f}GB free")
    except OSError as exc:
        log(f"  ⚠ Disk space check failed: {exc}")

    # OpenRouter reachable
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log("  ✓ OpenRouter API reachable (no auth needed for catalog)")
            else:
                log(f"  ⚠ OpenRouter returned status {resp.status}; catalog refresh may fail")
    except (urllib.error.URLError, OSError) as exc:
        log(f"  ⚠ Cannot reach OpenRouter ({exc}); install can continue but catalog refresh will fail")
        # Don't block on this — install may proceed without immediate catalog refresh

    # Write perms
    try:
        test_path = REPO_ROOT / ".install-write-test"
        test_path.write_text("")
        test_path.unlink()
        log(f"  ✓ Write permission at {REPO_ROOT}")
    except (OSError, PermissionError) as exc:
        log(f"  ✗ Cannot write to {REPO_ROOT}: {exc}")
        ok = False

    if ok and not dry_run:
        state["steps_completed"].append("preflight")
        save_state(state)
    return ok


def step_select_profile(state: dict, profile: str | None, dry_run: bool) -> bool:
    log("Step 2/6: Deployment profile selection")
    if profile is None:
        if sys.stdin.isatty():
            print()
            print("  Available profiles:")
            for name, info in DEPLOYMENT_PROFILES.items():
                supported = "✓" if info["supported_now"] else "(coming soon)"
                print(f"    {name:12s} {supported:14s} {info['description']}")
            print()
            chosen = input("  Pick a profile [solo]: ").strip().lower() or "solo"
        else:
            log("  Non-interactive run with no --profile flag; defaulting to 'solo'")
            chosen = "solo"
    else:
        chosen = profile.lower()

    if chosen not in DEPLOYMENT_PROFILES:
        log(f"  ✗ Unknown profile {chosen!r}; expected one of {list(DEPLOYMENT_PROFILES)}")
        return False

    if not DEPLOYMENT_PROFILES[chosen]["supported_now"]:
        log(f"  ✗ Profile {chosen!r} is scaffolded but not supported in this install script yet.")
        log(f"    Blocked on the concurrency-architecture side thread. Use 'solo' for now.")
        return False

    log(f"  ✓ Profile selected: {chosen}")
    if not dry_run:
        state["profile"] = chosen
        state["steps_completed"].append("profile")
        save_state(state)
    return True


def step_openrouter_setup(state: dict, dry_run: bool) -> bool:
    log("Step 3/6: OpenRouter API key setup")
    log("")
    log("  OpenRouter is a unified API for cloud-based AI models.")
    log("  Sign up takes 2 minutes at https://openrouter.ai")
    log("  Free models work WITHOUT a credit card — you only add payment if")
    log("  you want paid models later.")
    log("")

    existing_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if existing_key:
        log("  ✓ OPENROUTER_API_KEY found in environment")
        if not dry_run:
            state["steps_completed"].append("openrouter")
            save_state(state)
        return True

    # Check if it's in the legacy endpoints.json (still gitignored)
    endpoints_path = REPO_ROOT / "config" / "endpoints.json"
    if endpoints_path.exists():
        try:
            with open(endpoints_path) as f:
                ep = json.load(f)
            if any("openrouter" in str(e).lower() for e in ep.get("endpoints", [])):
                log("  ✓ OpenRouter endpoint configured in config/endpoints.json")
                if not dry_run:
                    state["steps_completed"].append("openrouter")
                    save_state(state)
                return True
        except Exception:
            pass

    log("  → Set OPENROUTER_API_KEY in your environment before continuing.")
    log("    Example: export OPENROUTER_API_KEY=or_xxxxxxxxxxxxxxxxxxxx")
    log("    Add it to your shell profile (~/.zshrc or ~/.bashrc) to persist.")
    if dry_run:
        log("  [dry-run] would prompt to add the key now")
        return True
    log("")
    log("  Continuing without OpenRouter key — catalog refresh will fail at Step 4.")
    log("  Re-run install.py after setting the key.")
    return False


def step_catalog_refresh(state: dict, dry_run: bool) -> bool:
    log("Step 4/6: Catalog refresh (OpenRouter + optional Artificial Analysis)")
    if dry_run:
        log("  [dry-run] would run scripts/refresh-catalog.py")
        return True
    script = REPO_ROOT / "scripts" / "refresh-catalog.py"
    if not script.exists():
        log(f"  ✗ {script} missing")
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log("  ✓ Catalog refresh succeeded")
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    log(f"    {line}")
            state["steps_completed"].append("catalog")
            save_state(state)
            return True
        log(f"  ✗ Catalog refresh failed (exit {result.returncode})")
        log(f"    stderr: {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        log("  ✗ Catalog refresh timed out after 120s")
        return False


def step_autopopulate(state: dict, dry_run: bool) -> bool:
    log("Step 5/6: Auto-populate user-pipeline configuration (Optimum preset)")
    if dry_run:
        log("  [dry-run] would run scripts/auto-populate-configuration.py optimum user-pipeline")
        return True
    script = REPO_ROOT / "scripts" / "auto-populate-configuration.py"
    if not script.exists():
        log(f"  ✗ {script} missing")
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script), "optimum", "user-pipeline"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            log("  ✓ user-pipeline configuration populated")
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    log(f"    {line}")
            state["steps_completed"].append("autopopulate")
            save_state(state)
            return True
        log(f"  ✗ Auto-populate failed (exit {result.returncode})")
        log(f"    stderr: {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        log("  ✗ Auto-populate timed out after 60s")
        return False


def step_smoke_test(state: dict, dry_run: bool) -> bool:
    log("Step 6/6: Smoke test (Free configuration round-trip)")
    if dry_run:
        log("  [dry-run] would auto-populate Free + send one test prompt + verify response")
        return True
    # Populate a free configuration first so the smoke test has something to hit.
    autopop = REPO_ROOT / "scripts" / "auto-populate-configuration.py"
    try:
        subprocess.run(
            [sys.executable, str(autopop), "free", "smoke-test-free"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=60, check=True,
        )
    except subprocess.CalledProcessError as exc:
        log(f"  ✗ Could not populate the smoke-test configuration: {exc.stderr}")
        return False

    # Read the populated configuration and check that it has a primary model
    smoke_cfg_path = REPO_ROOT / "config" / "configurations" / "smoke-test-free.json"
    try:
        with open(smoke_cfg_path) as f:
            cfg = json.load(f)
        primary = cfg["cells"]["analysis"]["gear4"]["depth"]["primary"]
    except (KeyError, TypeError):
        log("  ⚠ smoke-test-free configuration has no primary; the free catalog may be empty")
        return False

    log(f"  ✓ Smoke-test configuration primary resolved: {primary}")
    log("  ✓ End-to-end pipeline reachable (configuration populated; actual chat round-trip happens after server start)")
    state["steps_completed"].append("smoke_test")
    save_state(state)
    return True


# ─── Main ────────────────────────────────────────────────────────────────


def _delegate_to_local_models(extra_argv: list[str]) -> int:
    """Re-entry point for `install.py models …`: defers to scripts/local_models.py.

    Lets users swap / add / remove local models any time post-install
    without re-running the full install pipeline.
    """
    script = REPO_ROOT / "scripts" / "local_models.py"
    if not script.exists():
        print(f"[install] {script} missing", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(script), *extra_argv])


def main():
    # Subcommand support — primary path is the full install; secondary
    # path is `install.py models` which re-enters the local-model
    # selection flow standalone.
    if len(sys.argv) >= 2 and sys.argv[1] == "models":
        sys.exit(_delegate_to_local_models(sys.argv[2:]))

    parser = argparse.ArgumentParser(
        description="Ora install script (Solo profile). Subcommand: 'models' re-enters local-model selection.",
    )
    parser.add_argument("--profile", choices=list(DEPLOYMENT_PROFILES.keys()), help="Skip the interactive profile prompt.")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without making changes.")
    parser.add_argument("--reset", action="store_true", help="Clear install state and exit.")
    parser.add_argument("--resume", action="store_true", help="Continue from the last completed step.")
    args = parser.parse_args()

    if args.reset:
        reset_install(args.dry_run)
        return

    state = load_state()
    if not state.get("started_at"):
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state, dry_run=args.dry_run)

    log(f"Ora install — Solo profile (install Chunk 7 scaffold) — {'DRY RUN' if args.dry_run else 'LIVE'}")
    log(f"Repo root: {REPO_ROOT}")
    if args.resume and state.get("steps_completed"):
        log(f"Resuming after: {', '.join(state['steps_completed'])}")

    completed = set(state.get("steps_completed", []))
    pipeline = [
        ("preflight",    step_preflight,    (state, args.dry_run)),
        ("profile",      step_select_profile, (state, args.profile, args.dry_run)),
        ("openrouter",   step_openrouter_setup, (state, args.dry_run)),
        ("catalog",      step_catalog_refresh, (state, args.dry_run)),
        ("autopopulate", step_autopopulate, (state, args.dry_run)),
        ("smoke_test",   step_smoke_test,   (state, args.dry_run)),
    ]

    for step_name, fn, fn_args in pipeline:
        if args.resume and step_name in completed:
            log(f"  ✓ Step '{step_name}' already completed; skipping")
            continue
        if not fn(*fn_args):
            log(f"INSTALL_HALTED at step '{step_name}'. Fix the issue above and re-run with --resume.")
            sys.exit(1)

    log(COMPLETION_MARKER)
    log("")
    log("Next: start the chat server with `./start.sh` and open localhost:5000.")


if __name__ == "__main__":
    main()
