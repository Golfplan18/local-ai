#!/usr/bin/env python3
"""Update AI Service Model Preferences

View, change, and auto-detect which models each browser AI service offers.

Usage:
    python3 update-models.py              # interactive selection
    python3 update-models.py --show       # show current selections
    python3 update-models.py --refresh    # auto-detect models from live service UIs
    python3 update-models.py --refresh --headless   # same, but no visible browser

Run --refresh whenever a service releases new models. The script opens each
service, scrapes the model dropdown, and updates the registry automatically.
New models are added, missing models are moved to the retired list.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

WORKSPACE = os.path.expanduser("~/ora/")
MODELS_JSON = os.path.join(WORKSPACE, "config/browser-models.json")
SESSION_DIR = os.path.join(WORKSPACE, "config/browser-sessions/")

SERVICE_NAMES = {
    "claude":     "Claude",
    "chatgpt":    "ChatGPT",
    "gemini":     "Gemini",
    "perplexity": "Perplexity",
    "mistral":    "Mistral",
    "copilot":    "Copilot",
    "deepseek":   "DeepSeek",
    "grok":       "Grok",
    "poe":        "Poe",
    "huggingchat":"HuggingChat",
    "meta_ai":    "Meta AI",
    "cohere":     "Cohere",
}

SERVICE_URLS = {
    "claude":     "https://claude.ai/new",
    "chatgpt":    "https://chatgpt.com/",
    "gemini":     "https://gemini.google.com/app",
    "perplexity": "https://www.perplexity.ai/",
    "mistral":    "https://chat.mistral.ai/chat",
    "copilot":    "https://copilot.microsoft.com/",
    "deepseek":   "https://chat.deepseek.com/",
    "grok":       "https://grok.com/",
    "poe":        "https://poe.com/",
    "huggingchat":"https://huggingface.co/chat/",
    "meta_ai":    "https://www.meta.ai/",
    "cohere":     "https://coral.cohere.com/",
}

# ── Noise filters ─────────────────────────────────────────────────────────
# Strings that appear in dropdowns but aren't model names.
NOISE_PATTERNS = [
    r"^$",                       # empty
    r"^search",                  # search boxes
    r"^try\b",                   # "Try asking..."
    r"^upgrade",                 # "Upgrade to Pro"
    r"^subscribe",
    r"^learn more",
    r"^see all",
    r"^more models",
    r"^browse",
    r"^close",
    r"^back$",
    r"^cancel$",
    r"^done$",
    r"^temporary",               # "Temporary chat"
    r"^customize",
    r"^settings",
    r"^new chat",
    r"^\d+$",                    # bare numbers
    r"^[•·▸►]",                 # bullet chars
]
_noise_re = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]

# Minimum length for a model name
MIN_MODEL_NAME_LEN = 2
# Maximum length — anything longer is a description, not a model name
MAX_MODEL_NAME_LEN = 50


def _is_noise(text: str) -> bool:
    """Return True if text is UI chrome rather than a model name."""
    text = text.strip()
    if len(text) < MIN_MODEL_NAME_LEN or len(text) > MAX_MODEL_NAME_LEN:
        return True
    for pat in _noise_re:
        if pat.search(text):
            return True
    return False


def _name_to_id(name: str, service: str) -> str:
    """Generate a stable model ID from a display name.

    Examples:
        'Claude Opus 4.6'  → 'claude-opus-4-6'
        'GPT-5.4 Thinking' → 'gpt-5.4-thinking'
        '3.1 Pro'          → 'gemini-3.1-pro'
    """
    cleaned = name.strip()
    # For Gemini, display names like '3.1 Pro' need the prefix
    if service == "gemini" and not cleaned.lower().startswith("gemini"):
        cleaned = f"gemini-{cleaned}"
    # Normalize to ID format
    model_id = cleaned.lower()
    model_id = re.sub(r"[^a-z0-9._-]", "-", model_id)
    model_id = re.sub(r"-+", "-", model_id)
    model_id = model_id.strip("-")
    return model_id


# ── File I/O ──────────────────────────────────────────────────────────────

def load_models() -> dict:
    """Load the model registry."""
    try:
        with open(MODELS_JSON) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  Model registry not found at {MODELS_JSON}")
        print("  Run capture-sessions.py first to set up your services.")
        sys.exit(1)


def save_models(data: dict):
    """Save the model registry."""
    with open(MODELS_JSON, "w") as f:
        json.dump(data, f, indent=2)


# ── Display ───────────────────────────────────────────────────────────────

def _service_keys(data: dict) -> list:
    """Return service keys present in the model registry, in a stable order."""
    # Preferred display order: big-3 first, then alphabetical remainder
    preferred = ["claude", "chatgpt", "gemini"]
    rest = sorted(k for k in data if k not in preferred and k != "_note")
    return [k for k in preferred if k in data] + rest


def show_selections(data: dict):
    """Display current model selections."""
    print("\n  Current Model Selections:\n")
    for key in _service_keys(data):
        svc = data.get(key)
        if not svc:
            continue
        display = SERVICE_NAMES.get(key, key)
        selected = svc.get("selected", "none")
        # Find the display name for the selected model
        name = selected
        for m in svc.get("available", []):
            if m["id"] == selected:
                name = m["name"]
                break
        has_session = os.path.exists(os.path.join(SESSION_DIR, f"{key}.json"))
        status = "✓" if has_session else "✗ no session"
        updated = svc.get("last_updated", "unknown")

        n_available = len(svc.get("available", []))
        n_retired = len(svc.get("retired", []))
        retired_note = f"  ({n_retired} retired)" if n_retired else ""

        print(f"    {status} {display:12s}  model: {name:25s}  [{n_available} available{retired_note}]  (updated: {updated})")
    print()


def show_full_list(data: dict):
    """Show all models including retired ones."""
    for key in _service_keys(data):
        svc = data.get(key)
        if not svc:
            continue
        display = SERVICE_NAMES.get(key, key)
        print(f"\n  {display}:")

        available = svc.get("available", [])
        retired = svc.get("retired", [])
        selected = svc.get("selected", "")

        if available:
            print("    Available:")
            for m in available:
                current = " ← selected" if m["id"] == selected else ""
                tier = f"({m.get('tier', '?')})"
                print(f"      • {m['name']:25s} {tier:15s}{current}")

        if retired:
            print("    Retired:")
            for m in retired:
                date = m.get("retired_date", "")
                print(f"      ✗ {m['name']:25s} (removed {date})")
    print()


# ── Auto-discovery ────────────────────────────────────────────────────────

def _scrape_model_dropdown(page, ui_config: dict) -> list[str]:
    """Click the model selector and scrape all option texts."""
    button_selector = ui_config.get("model_button", "")
    list_selector = ui_config.get("model_list_selector", "")
    close_action = ui_config.get("close_action", "Escape")

    if not button_selector or not list_selector:
        return []

    # Click the model selector button
    button_selectors = [s.strip() for s in button_selector.split(",")]
    clicked = False
    for sel in button_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=5000):
                btn.click()
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        return []

    # Wait for dropdown to appear
    page.wait_for_timeout(2000)

    # Scrape all visible option texts
    names = []
    list_selectors = [s.strip() for s in list_selector.split(",")]
    for sel in list_selectors:
        try:
            elements = page.locator(sel).all()
            for el in elements:
                try:
                    if el.is_visible(timeout=1000):
                        text = el.inner_text(timeout=2000).strip()
                        # Take only the first line (some options have descriptions below)
                        first_line = text.split("\n")[0].strip()
                        if first_line and first_line not in names:
                            names.append(first_line)
                except Exception:
                    continue
        except Exception:
            continue

    # Close the dropdown
    try:
        page.keyboard.press(close_action)
    except Exception:
        pass

    return names


def _diff_models(current_available: list, scraped_names: list, service: str) -> tuple[list, list, list]:
    """Compare scraped model names against current registry.

    Returns (new_models, still_available, retired_models) where:
      - new_models: list of dicts for models found in dropdown but not in registry
      - still_available: list of dicts for models found in both
      - retired_models: list of dicts for models in registry but not in dropdown
    """
    # Build lookup of current models by name (case-insensitive)
    current_by_name = {}
    current_by_id = {}
    for m in current_available:
        current_by_name[m["name"].lower()] = m
        current_by_id[m["id"]] = m

    # Filter noise from scraped names
    clean_names = [n for n in scraped_names if not _is_noise(n)]

    # Classify each scraped name
    matched_ids = set()
    new_models = []
    still_available = []

    for name in clean_names:
        name_lower = name.lower()
        gen_id = _name_to_id(name, service)

        # Check if this matches an existing model (by name or generated ID)
        matched = current_by_name.get(name_lower) or current_by_id.get(gen_id)

        # Also try fuzzy: check if scraped name is contained in any known name or vice versa
        if not matched:
            for m in current_available:
                if (name_lower in m["name"].lower() or
                        m["name"].lower() in name_lower):
                    matched = m
                    break

        if matched:
            matched_ids.add(matched["id"])
            still_available.append(matched)
        else:
            new_models.append({
                "id": gen_id,
                "name": name,
                "tier": "unknown",
            })

    # Models in registry but not found in dropdown → retired
    retired_models = []
    for m in current_available:
        if m["id"] not in matched_ids:
            retired_models.append(m)

    return new_models, still_available, retired_models


def auto_refresh(headless: bool = True):
    """Auto-detect available models by scraping each service's UI."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed. Run: pip install playwright && playwright install chromium")
        return

    data = load_models()
    today = datetime.now().strftime("%Y-%m-%d")
    total_new = 0
    total_retired = 0

    print("""
  ╔══════════════════════════════════════════════════════════════╗
  ║           Auto-Detect Model Updates                         ║
  ╠══════════════════════════════════════════════════════════════╣
  ║  Opening each service to scan model dropdowns...            ║
  ╚══════════════════════════════════════════════════════════════╝
""")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        for key in _service_keys(data):
            svc = data.get(key)
            if not svc:
                continue

            display = SERVICE_NAMES.get(key, key)
            session_path = os.path.join(SESSION_DIR, f"{key}.json")

            if not os.path.exists(session_path):
                print(f"  ⊘ {display:12s}  skipped — no session file")
                continue

            ui = svc.get("ui", {})
            if not ui.get("model_button") or not ui.get("model_list_selector"):
                print(f"  ⊘ {display:12s}  skipped — no UI selectors configured")
                continue

            url = SERVICE_URLS.get(key, "")
            if not url:
                continue

            print(f"  ◎ {display:12s}  scanning...", end="", flush=True)

            try:
                context = browser.new_context(storage_state=session_path)
                page = context.new_page()
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)

                # Extra wait for dynamic UI to settle
                page.wait_for_timeout(3000)

                scraped = _scrape_model_dropdown(page, ui)
                context.close()

                if not scraped:
                    print(f"  no models found in dropdown (UI may have changed)")
                    continue

                # Diff against current list
                current_available = svc.get("available", [])
                new_models, still_available, newly_retired = _diff_models(
                    current_available, scraped, key
                )

                # Update the registry
                # Keep still-available models in their original order, append new ones
                svc["available"] = still_available + new_models

                # Move retired models to the retired list
                existing_retired = svc.get("retired", [])
                existing_retired_ids = {m["id"] for m in existing_retired}
                for m in newly_retired:
                    if m["id"] not in existing_retired_ids:
                        m["retired_date"] = today
                        existing_retired.append(m)
                svc["retired"] = existing_retired

                # If the selected model was retired, fall back to first available
                selected = svc.get("selected", "")
                available_ids = {m["id"] for m in svc["available"]}
                if selected not in available_ids and svc["available"]:
                    old_name = selected
                    svc["selected"] = svc["available"][0]["id"]
                    new_name = svc["available"][0]["name"]
                    print(f"\n    ⚠  Selected model retired — switched to {new_name}")

                svc["last_updated"] = today
                total_new += len(new_models)
                total_retired += len(newly_retired)

                # Report
                parts = []
                if new_models:
                    names = ", ".join(m["name"] for m in new_models)
                    parts.append(f"+{len(new_models)} new ({names})")
                if newly_retired:
                    names = ", ".join(m["name"] for m in newly_retired)
                    parts.append(f"-{len(newly_retired)} retired ({names})")
                if not parts:
                    parts.append("no changes")

                found_count = len(still_available) + len(new_models)
                print(f"  found {found_count} models — {'; '.join(parts)}")

            except Exception as e:
                print(f"  error: {str(e)[:80]}")
                continue

        browser.close()

    # Mark unknown tiers for user review if any new models were found
    if total_new > 0:
        print(f"\n  ℹ  {total_new} new model(s) added with tier 'unknown'.")
        print("     Run update-models.py interactively to set tiers (free / paid / free+paid).")

    # Save
    save_models(data)
    print()
    show_selections(data)
    print(f"  Saved to config/browser-models.json")
    print(f"  Summary: {total_new} added, {total_retired} retired\n")


# ── Interactive mode ──────────────────────────────────────────────────────

def select_model(data: dict, service: str):
    """Interactive model selection for a service."""
    svc = data.get(service)
    if not svc:
        print(f"  Service '{service}' not in model registry.")
        return

    display = SERVICE_NAMES.get(service, service)
    available = svc.get("available", [])
    retired = svc.get("retired", [])
    selected = svc.get("selected", "")

    print(f"\n  Available {display} models:\n")
    for i, model in enumerate(available, 1):
        current = " ← current" if model["id"] == selected else ""
        tier_label = f"({model['tier']})" if model.get("tier") else ""
        print(f"    {i}. {model['name']:25s} {tier_label:15s}{current}")

    if retired:
        print(f"\n  Retired models (no longer in {display}'s dropdown):")
        for model in retired:
            date = model.get("retired_date", "?")
            print(f"    ✗ {model['name']:25s} (removed {date})")

    print(f"\n    0. Keep current selection")
    print()

    try:
        choice = input(f"  Select model [0-{len(available)}]: ").strip()
        if not choice or choice == "0":
            print("  No change.")
            return

        idx = int(choice) - 1
        if 0 <= idx < len(available):
            model = available[idx]
            svc["selected"] = model["id"]
            svc["last_updated"] = datetime.now().strftime("%Y-%m-%d")
            print(f"  → {display} set to {model['name']}")
        else:
            print("  Invalid selection.")
    except (ValueError, EOFError):
        print("  No change.")


def set_tier(data: dict, service: str):
    """Set the tier for models with 'unknown' tier."""
    svc = data.get(service)
    if not svc:
        return

    display = SERVICE_NAMES.get(service, service)
    unknowns = [m for m in svc.get("available", []) if m.get("tier") == "unknown"]
    if not unknowns:
        print(f"  No unknown tiers in {display}.")
        return

    print(f"\n  Set tiers for {display} models:\n")
    for m in unknowns:
        print(f"    {m['name']}")
        tier = input("    Tier [free/paid/free+paid]: ").strip().lower()
        if tier in ("free", "paid", "free+paid"):
            m["tier"] = tier
            print(f"    → {tier}")
        else:
            print(f"    → keeping 'unknown'")
    print()


def restore_model(data: dict, service: str):
    """Move a retired model back to the available list."""
    svc = data.get(service)
    if not svc:
        return

    display = SERVICE_NAMES.get(service, service)
    retired = svc.get("retired", [])
    if not retired:
        print(f"  No retired models in {display}.")
        return

    print(f"\n  Retired {display} models:\n")
    for i, model in enumerate(retired, 1):
        date = model.get("retired_date", "?")
        print(f"    {i}. {model['name']:25s} (removed {date})")

    try:
        choice = int(input(f"\n  Restore [1-{len(retired)}, 0 to cancel]: ").strip())
        if choice == 0:
            return
        idx = choice - 1
        if 0 <= idx < len(retired):
            model = retired.pop(idx)
            model.pop("retired_date", None)
            svc["available"].append(model)
            svc["last_updated"] = datetime.now().strftime("%Y-%m-%d")
            print(f"  Restored {model['name']} to available list")
    except (ValueError, IndexError):
        print("  Cancelled.")


def add_model(data: dict, service: str):
    """Manually add a new model to a service's available list."""
    svc = data.get(service)
    if not svc:
        print(f"  Service '{service}' not in model registry.")
        return

    display = SERVICE_NAMES.get(service, service)
    print(f"\n  Add a model to {display}:")
    model_name = input("  Display name (as it appears in dropdown): ").strip()
    if not model_name:
        print("  Cancelled.")
        return

    model_id = _name_to_id(model_name, service)
    tier = input("  Tier [free/paid/free+paid]: ").strip() or "unknown"

    # Check for duplicates
    for m in svc.get("available", []):
        if m["id"] == model_id:
            print(f"  Model '{model_id}' already exists.")
            return

    svc["available"].append({"id": model_id, "name": model_name, "tier": tier})
    svc["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    print(f"  Added {model_name} ({model_id}) to {display}")


def remove_model(data: dict, service: str):
    """Remove a model from a service's available list."""
    svc = data.get(service)
    if not svc:
        return

    display = SERVICE_NAMES.get(service, service)
    available = svc.get("available", [])

    print(f"\n  Remove a model from {display}:\n")
    for i, model in enumerate(available, 1):
        print(f"    {i}. {model['name']}")

    try:
        choice = int(input(f"\n  Remove [1-{len(available)}, 0 to cancel]: ").strip())
        if choice == 0:
            return
        idx = choice - 1
        if 0 <= idx < len(available):
            removed = available.pop(idx)
            if svc.get("selected") == removed["id"]:
                svc["selected"] = available[0]["id"] if available else ""
            svc["last_updated"] = datetime.now().strftime("%Y-%m-%d")
            print(f"  Removed {removed['name']}")
    except (ValueError, IndexError):
        print("  Cancelled.")


def interactive_mode(data: dict):
    """Main interactive loop."""
    show_selections(data)
    valid_services = set(_service_keys(data))

    while True:
        svc_list = " / ".join(_service_keys(data))
        print("  Commands:")
        print(f"    <service>                  — change model ({svc_list})")
        print("    list                       — show all models including retired")
        print("    tier <service>             — set tier for new models")
        print("    restore <service>          — restore a retired model")
        print("    add <service>              — manually add a model")
        print("    remove <service>           — remove a model")
        print("    show                       — show current selections")
        print("    done                       — save and exit")
        print()

        try:
            cmd = input("  > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if cmd in ("done", "exit", "quit", "q", ""):
            break
        elif cmd == "show":
            show_selections(data)
        elif cmd == "list":
            show_full_list(data)
        elif cmd in valid_services:
            select_model(data, cmd)
        elif cmd.startswith("tier "):
            service = cmd.split()[1] if len(cmd.split()) > 1 else ""
            if service in valid_services:
                set_tier(data, service)
            else:
                print(f"  Unknown service: {service}")
        elif cmd.startswith("restore "):
            service = cmd.split()[1] if len(cmd.split()) > 1 else ""
            if service in valid_services:
                restore_model(data, service)
            else:
                print(f"  Unknown service: {service}")
        elif cmd.startswith("add "):
            service = cmd.split()[1] if len(cmd.split()) > 1 else ""
            if service in valid_services:
                add_model(data, service)
            else:
                print(f"  Unknown service: {service}")
        elif cmd.startswith("remove "):
            service = cmd.split()[1] if len(cmd.split()) > 1 else ""
            if service in valid_services:
                remove_model(data, service)
            else:
                print(f"  Unknown service: {service}")
        else:
            print(f"  Unknown command: {cmd}")

    save_models(data)
    print("\n  Saved to config/browser-models.json\n")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--show" in sys.argv:
        data = load_models()
        if "--all" in sys.argv:
            show_full_list(data)
        else:
            show_selections(data)
    elif "--refresh" in sys.argv:
        headless = "--headless" in sys.argv
        auto_refresh(headless=headless)
    else:
        data = load_models()
        interactive_mode(data)
