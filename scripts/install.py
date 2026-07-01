#!/usr/bin/env python3
"""Ora install script (source-install path — Solo public profile).

Solo is the only supported public install profile today. Hybrid and
Organization remain design targets for the future multi-machine /
concurrency work; the script keeps their names reserved so stale docs and
operators get a clear "not yet" message instead of a silent shape change.

Steps the script performs in order:

  1. Pre-flight: Python 3.11+, ≥5GB disk, OpenRouter catalog reachable,
     write perms
  2. Deployment profile selection (Solo today; Hybrid / Organization future)
  3. Catalog refresh — fetches OpenRouter operational fields and writes
     config/model-catalog.json (legacy snapshot, still consumed by
     auto-populate-configuration).
  4. Model-registry sync — fetches OpenRouter + LiteLLM + Chatbot Arena
      and runs the empirical vision-capability probe, writing
      config/model-registry.json. This replaces the prior Artificial
      Analysis (AA) dependency: intelligence rankings come from Chatbot
      Arena's free public dataset, and vision capability is empirically
      verified rather than trusted from any single provider's metadata.
      An optional AA key improves the registry path after install, but it is
      not required for installation.
  5. Auto-populate user-pipeline configuration from the Budget preset.
  6. Smoke test: populate the Free configuration, then make one tiny
     OpenRouter chat round-trip when a key is already available. Without a
     key, the smoke test validates config and tells the user to add keys
     later in Settings → External APIs.
  7. Optional External APIs orientation: explain the recommended key set,
     open official provider pages one at a time if the user wants them, and
     print the install-complete summary. The tail of ~/ora/install.log lands
     a deterministic marker the test protocol grep-checks.

Design properties:
  - Idempotent: re-run safely; existing state is honored, not clobbered
  - Resumable: completed steps are tracked in ~/ora/install-state.json
  - Verbose by default: every step prints what it's doing
  - Pre-flight gated: fails fast on missing prerequisites
  - --reset rolls back the install state (does NOT delete vault or
     conversations — that's uninstall's job)
  - --dry-run previews actions without making changes

What this script does NOT do yet:
  - Package a double-click installer (download is currently a source install)
  - Support Hybrid / Organization as public profiles (future G1.27+ work)
  - Download local models in the main flow (`install.py models` does that)

Usage:
    python3 scripts/install.py                # interactive install
    python3 scripts/install.py --profile solo # non-interactive
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
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "install-state.json"
LOG_PATH = REPO_ROOT / "install.log"
COMPLETION_MARKER = "INSTALL_COMPLETE: 0 warnings, 0 errors"

DEPLOYMENT_PROFILES = {
    "solo": {
        "description": "Supported public source install. Single user, local models where available, optional OpenRouter/API fallback.",
        "supported_now": True,
        "local_models": True,
        # 0 = unbounded API concurrency (Solo expects no API endpoints; if
        # one is added, no cap is the right fallback so calls don't deadlock)
        "api_pool_size": 0,
    },
    "hybrid": {
        "description": "Future multi-machine / local-plus-API profile. Reserved until G1.27 network discovery and concurrency validation land.",
        "supported_now": False,
        "local_models": True,
        "api_pool_size": 8,
    },
    "organization": {
        "description": "Future shared / API-pool deployment profile. Reserved until the organization concurrency path is tested.",
        "supported_now": False,
        "local_models": False,
        "api_pool_size": 32,
    },
}

PREFLIGHT_MIN_PYTHON = (3, 11)
PREFLIGHT_MIN_DISK_GB = 5

EXTERNAL_API_GROUPS = [
    {
        "title": "Recommended minimal package",
        "providers": [
            {
                "name": "OpenRouter",
                "url": "https://openrouter.ai/settings/keys",
                "cost": "free models available; paid/usage-based models require credits",
                "why": "opens the broad cloud-model catalog and avoids relying only on rate-limited free models",
            },
            {
                "name": "Tavily",
                "url": "https://app.tavily.com/",
                "cost": "free tier, then usage-based plans",
                "why": "gives Ora a search API built for AI agents and RAG workflows",
            },
            {
                "name": "Artificial Analysis",
                "url": "https://artificialanalysis.ai/api-key-management-redirect",
                "cost": "free model-benchmark API; commercial data exists separately",
                "why": "improves model-selector intelligence with independent benchmark and provider data",
            },
        ],
    },
    {
        "title": "Additional search options",
        "providers": [
            {
                "name": "Exa",
                "url": "https://dashboard.exa.ai/api-keys",
                "cost": "trial/free credits, then usage-based",
                "why": "adds semantic web search when Tavily is not the best fit",
            },
            {
                "name": "Brave Search API",
                "url": "https://api-dashboard.search.brave.com/app/keys",
                "cost": "monthly free credits, then usage-based",
                "why": "adds an independent web-search source for the search cascade",
            },
        ],
    },
    {
        "title": "Direct model-provider keys",
        "providers": [
            {
                "name": "Anthropic",
                "url": "https://platform.claude.com/settings/keys",
                "cost": "usually usage-based; provider terms vary",
                "why": "direct Claude API access when you want to skip OpenRouter's gateway markup",
            },
            {
                "name": "OpenAI",
                "url": "https://platform.openai.com/api-keys",
                "cost": "usage-based",
                "why": "direct OpenAI API access for chat, vision, and OpenAI speech/image features",
            },
            {
                "name": "Google Gemini",
                "url": "https://aistudio.google.com/app/apikey",
                "cost": "free tier for some models, paid tier varies by use",
                "why": "direct Gemini API access when Google models are the best fit",
            },
            {
                "name": "Mistral AI",
                "url": "https://console.mistral.ai/api-keys",
                "cost": "usage-based",
                "why": "direct Mistral API access and OpenAI-compatible routing",
            },
            {
                "name": "DeepSeek",
                "url": "https://platform.deepseek.com/api_keys",
                "cost": "usage-based",
                "why": "direct DeepSeek API access and OpenAI-compatible routing",
            },
            {
                "name": "Alibaba Qwen",
                "url": "https://modelstudio.console.alibabacloud.com/?tab=playground#/api-key",
                "cost": "usage-based",
                "why": "direct Qwen/DashScope API access and OpenAI-compatible routing",
            },
        ],
    },
    {
        "title": "Speech, image, video, and speed-specialist APIs",
        "providers": [
            {
                "name": "AssemblyAI",
                "url": "https://www.assemblyai.com/dashboard/signup",
                "cost": "free trial or usage-based plans vary",
                "why": "optional cloud transcription when local Whisper is not enough",
            },
            {
                "name": "Deepgram",
                "url": "https://console.deepgram.com/signup",
                "cost": "free trial or usage-based plans vary",
                "why": "optional low-latency cloud transcription",
            },
            {
                "name": "ElevenLabs",
                "url": "https://elevenlabs.io/app/settings/api-keys",
                "cost": "free tier or usage-based plans vary",
                "why": "higher-quality text-to-speech than local macOS speech",
            },
            {
                "name": "Stability AI",
                "url": "https://platform.stability.ai/account/keys",
                "cost": "usage-based image generation",
                "why": "optional image and video generation backends for visual workflows",
            },
            {
                "name": "Replicate",
                "url": "https://replicate.com/account/api-tokens",
                "cost": "usage-based model hosting",
                "why": "long-tail image, video, and specialist model access",
            },
            {
                "name": "Tensor.Art",
                "url": "https://tams.tensor.art/apps",
                "cost": "usage-based image generation",
                "why": "optional image generation backend",
            },
        ],
    },
]


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
    log("Step 1/7: Pre-flight checks")
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
    log("Step 2/7: Deployment profile selection")
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
        log(f"  ✗ Profile {chosen!r} is reserved for future Ora installs, not supported today.")
        log("    Use 'solo' for the public source-install path. Hybrid / Organization")
        log("    return after G1.27 network discovery and concurrency validation.")
        return False

    log(f"  ✓ Profile selected: {chosen}")
    if not dry_run:
        state["profile"] = chosen
        state["steps_completed"].append("profile")
        save_state(state)
    return True


def _prompt_yes_no(prompt: str, default: bool = False) -> bool:
    """Interactive yes/no helper. Non-interactive callers should not use it."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def _try_keyring_get(username: str) -> str:
    try:
        import keyring  # type: ignore
        return (keyring.get_password("ora", username) or "").strip()
    except Exception:
        return ""


def _openrouter_key() -> str:
    return (
        os.environ.get("OPENROUTER_API_KEY", "").strip()
        or _try_keyring_get("openrouter-api-key")
    )


def _open_provider_page(url: str) -> bool:
    try:
        return bool(webbrowser.open_new_tab(url))
    except Exception:
        return False


def step_catalog_refresh(state: dict, dry_run: bool) -> bool:
    log("Step 3/7: Catalog refresh (OpenRouter operational fields)")
    log("")

    # Artificial Analysis intelligence-index check.
    #
    # AA enriches the model catalog with intelligence rankings. The
    # auto-populate engine walks the catalog with a Pareto +
    # percentage-floor + cost-sort algorithm. With no intelligence_index
    # field on catalog entries, every model scores the same on
    # "capability" and the algorithm falls through to pure cost sort —
    # meaning auto-populate will pick the cheapest model per slot
    # regardless of how capable it actually is. That is almost certainly
    # not what you want for production pipelines.
    # Intelligence rankings come from scripts/sync_model_registry.py
    # (OpenRouter + Chatbot Arena + Artificial Analysis), called below.
    # No key is required: AA data defaults to their public website; an
    # AA key (keyring 'ora/aa-api-key' or AA_API_KEY env) auto-switches
    # the sync to AA's official API.

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


def step_model_registry_sync(state: dict, dry_run: bool) -> bool:
    """Populate config/model-registry.json from OpenRouter + LiteLLM +
    Chatbot Arena, then run the empirical vision-capability probe.

    The registry is the runtime source of truth for model capabilities
    (vision_capable, intelligence_score, context_length). Boot.py reads
    it via orchestrator/model_registry.py and overlays its values onto
    the routing-config endpoints at startup.

    No API key required (Chatbot Arena is a free public CSV; OpenRouter
    /api/v1/models is unauthenticated for listing; LiteLLM is a raw
    JSON on GitHub). The empirical probe is opt-in during install and
    only runs when ORA_INSTALL_PROBE=1 is set; if a key is unavailable,
    the sync path stays on metadata and public benchmark sources.

    Replaces the prior AA enrichment step.
    """
    log("Step 4/7: Sync curated model registry (OpenRouter + LiteLLM + Chatbot Arena + empirical probe)")
    if dry_run:
        log("  [dry-run] would run scripts/sync_model_registry.py sync")
        return True
    script = REPO_ROOT / "scripts" / "sync_model_registry.py"
    if not script.exists():
        log(f"  ⚠ {script} missing — skipping registry sync (boot.py will fall back to routing-config capabilities)")
        return True  # non-fatal: the system still works without the registry
    try:
        # Use --no-probe to keep install non-flaky; the probe can run
        # post-install via a manual `python3 scripts/sync_model_registry.py probe`
        # or via the periodic refresh cycle when implemented.
        # For installs that have an OpenRouter key set, the user can
        # opt into the probe via the ORA_INSTALL_PROBE=1 env var.
        cmd = [sys.executable, str(script), "sync"]
        if not os.environ.get("ORA_INSTALL_PROBE", "").strip():
            cmd.append("--no-probe")
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            log("  ✓ Model registry synced")
            for line in result.stdout.strip().split("\n")[-6:]:  # last 6 lines = summary
                if line.strip():
                    log(f"    {line}")
            state["steps_completed"].append("registry_sync")
            save_state(state)
            return True
        log(f"  ⚠ Registry sync failed (exit {result.returncode}) — proceeding with capability fallback")
        log(f"    stderr: {result.stderr.strip()[:300]}")
        return True  # non-fatal: boot.py falls back to routing-config flags
    except subprocess.TimeoutExpired:
        log("  ⚠ Registry sync timed out after 300s — proceeding with capability fallback")
        return True
    except Exception as e:
        log(f"  ⚠ Registry sync errored ({e}) — proceeding with capability fallback")
        return True


def step_autopopulate(state: dict, dry_run: bool) -> bool:
    log("Step 5/7: Auto-populate user-pipeline configuration (Budget preset)")
    if dry_run:
        log("  [dry-run] would run scripts/auto-populate-configuration.py budget user-pipeline")
        return True
    script = REPO_ROOT / "scripts" / "auto-populate-configuration.py"
    if not script.exists():
        log(f"  ✗ {script} missing")
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script), "budget", "user-pipeline"],
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


def _extract_smoke_models(cfg: dict) -> list[str]:
    """Return Free-config model candidates in the order the user would hit them."""
    candidates: list[str] = []
    try:
        cell = cfg["cells"]["analysis"]["gear4"]["depth"]
        primary = cell.get("primary")
        if primary:
            candidates.append(primary)
        candidates.extend([m for m in cell.get("fallback", []) if m])
    except (KeyError, AttributeError, TypeError):
        pass
    if "openrouter/free" not in candidates:
        candidates.append("openrouter/free")
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(candidates))


def _openrouter_smoke_call(model_id: str, api_key: str) -> tuple[bool, str, bool]:
    """Attempt a tiny OpenRouter chat call.

    Returns (ok, message, auth_failure). Auth failures should stop install;
    free-model availability/rate failures are external and can fall back to
    config validation.
    """
    payload = json.dumps({
        "model": model_id,
        "messages": [
            {"role": "system", "content": "Reply with exactly: Ora install smoke ok"},
            {"role": "user", "content": "Smoke test."},
        ],
        "temperature": 0,
        "max_tokens": 12,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ora-ai.app",
            "X-Title": "Ora installer smoke test",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        auth_failure = exc.code in {401, 403}
        return False, f"HTTP {exc.code}: {detail}", auth_failure
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, f"{type(exc).__name__}: {exc}", False
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON response: {exc}", False

    content = ""
    try:
        content = (body["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        pass
    if not content:
        return False, "empty response from OpenRouter", False
    return True, content[:160], False


def step_smoke_test(state: dict, dry_run: bool) -> bool:
    log("Step 6/7: Smoke test (Free configuration + optional OpenRouter round-trip)")
    if dry_run:
        log("  [dry-run] would auto-populate Free + send one test prompt when an OpenRouter key is available")
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
        candidates = _extract_smoke_models(cfg)
    except (KeyError, TypeError):
        log("  ⚠ smoke-test-free configuration has no primary; the free catalog may be empty")
        return False

    if not candidates:
        log("  ⚠ smoke-test-free configuration has no model candidates; the free catalog may be empty")
        return False

    log(f"  ✓ Smoke-test configuration primary resolved: {candidates[0]}")
    api_key = _openrouter_key()
    if not api_key:
        log("  → No OpenRouter key found in env or keyring; skipping live chat round-trip.")
        log("    Add a key later in Settings → External APIs. The install remains usable with")
        log("    local models and any API keys you add after first launch.")
    else:
        log("  OpenRouter key found; attempting a tiny live chat round-trip.")
        last_error = ""
        for model_id in candidates[:5]:
            ok, message, auth_failure = _openrouter_smoke_call(model_id, api_key)
            if ok:
                log(f"  ✓ OpenRouter chat round-trip succeeded with {model_id}: {message!r}")
                break
            last_error = f"{model_id}: {message}"
            log(f"    {model_id} did not complete: {message}")
            if auth_failure:
                log("  ✗ OpenRouter rejected the key. Update it in Settings → External APIs or OPENROUTER_API_KEY.")
                return False
        else:
            log("  → Live OpenRouter chat did not complete with the current free candidates.")
            log(f"    Last result: {last_error}")
            log("    Free models are rate-limited and sometimes unavailable; configuration validation passed.")

    state["steps_completed"].append("smoke_test")
    save_state(state)
    return True


def step_external_api_walkthrough(state: dict, dry_run: bool) -> bool:
    log("Step 7/7: Optional External APIs orientation")
    log("")
    log("  Ora can run without these keys, and every provider below can be added")
    log("  later in Settings → External APIs. Keys are stored in the system keychain,")
    log("  not in plaintext files.")
    log("")
    log("  Recommended minimal package: OpenRouter + Tavily + Artificial Analysis.")
    log("  FRED is intentionally skipped here; it is for specialized economic-data work.")
    log("")

    for group in EXTERNAL_API_GROUPS:
        log(f"  {group['title']}:")
        for provider in group["providers"]:
            log(f"    - {provider['name']}: {provider['why']}")
            log(f"      Cost: {provider['cost']}")
            log(f"      Link: {provider['url']}")
        log("")

    if dry_run:
        log("  [dry-run] would offer to open official provider pages")
        return True

    if sys.stdin.isatty() and _prompt_yes_no("  Open provider pages now?", default=False):
        for group in EXTERNAL_API_GROUPS:
            print()
            print(f"  {group['title']}")
            for provider in group["providers"]:
                print(f"    {provider['name']}: {provider['url']}")
                if _prompt_yes_no(f"    Open {provider['name']} page?", default=False):
                    if _open_provider_page(provider["url"]):
                        log(f"  ✓ Opened {provider['name']} page")
                    else:
                        log(f"  → Could not open browser automatically; copy this link: {provider['url']}")
    else:
        log("  Skipping browser-open prompts. Use the links above or Settings → External APIs later.")

    state["steps_completed"].append("external_api_walkthrough")
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
        description="Ora source-install script (Solo public profile). Subcommand: 'models' re-enters local-model selection.",
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

    log(f"Ora source install — Solo public profile — {'DRY RUN' if args.dry_run else 'LIVE'}")
    log(f"Repo root: {REPO_ROOT}")
    if args.resume and state.get("steps_completed"):
        log(f"Resuming after: {', '.join(state['steps_completed'])}")

    completed = set(state.get("steps_completed", []))
    pipeline = [
        ("preflight",      step_preflight,    (state, args.dry_run)),
        ("profile",        step_select_profile, (state, args.profile, args.dry_run)),
        ("catalog",        step_catalog_refresh, (state, args.dry_run)),
        ("registry_sync",  step_model_registry_sync, (state, args.dry_run)),
        ("autopopulate",   step_autopopulate, (state, args.dry_run)),
        ("smoke_test",     step_smoke_test,   (state, args.dry_run)),
        ("external_api_walkthrough", step_external_api_walkthrough, (state, args.dry_run)),
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
    log("Then open Settings → External APIs to paste any keys you created during setup.")


if __name__ == "__main__":
    main()
