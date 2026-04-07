#!/usr/bin/env python3
"""Update AI Service Model Preferences

View and change which model each browser AI service uses.
No browser needed — just picks from the known model list.

Usage:
    python3 update-models.py              # interactive selection
    python3 update-models.py --show       # show current selections
    python3 update-models.py --discover   # open browser to check for new models

Run this whenever a service releases new models and you want to switch.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

WORKSPACE = os.path.expanduser("~/local-ai/")
MODELS_JSON = os.path.join(WORKSPACE, "config/browser-models.json")
SESSION_DIR = os.path.join(WORKSPACE, "config/browser-sessions/")

SERVICE_NAMES = {
    "claude": "Claude",
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
}


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


def show_selections(data: dict):
    """Display current model selections."""
    print("\n  Current Model Selections:\n")
    for key in ("claude", "chatgpt", "gemini"):
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
        print(f"    {status} {display:12s}  model: {name:20s}  (updated: {updated})")
    print()


def select_model(data: dict, service: str):
    """Interactive model selection for a service."""
    svc = data.get(service)
    if not svc:
        print(f"  Service '{service}' not in model registry.")
        return

    display = SERVICE_NAMES.get(service, service)
    available = svc.get("available", [])
    selected = svc.get("selected", "")

    print(f"\n  Available {display} models:\n")
    for i, model in enumerate(available, 1):
        current = " ← current" if model["id"] == selected else ""
        tier_label = f"({model['tier']})" if model.get("tier") else ""
        print(f"    {i}. {model['name']:25s} {tier_label:15s}{current}")

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


def add_model(data: dict, service: str):
    """Manually add a new model to a service's available list."""
    svc = data.get(service)
    if not svc:
        print(f"  Service '{service}' not in model registry.")
        return

    display = SERVICE_NAMES.get(service, service)
    print(f"\n  Add a model to {display}:")
    model_id = input("  Model ID (e.g., 'gpt-5'): ").strip()
    model_name = input("  Display name (e.g., 'GPT-5'): ").strip()
    tier = input("  Tier [free/paid/free+paid]: ").strip() or "free+paid"

    if not model_id or not model_name:
        print("  Cancelled.")
        return

    # Check for duplicates
    for m in svc.get("available", []):
        if m["id"] == model_id:
            print(f"  Model '{model_id}' already exists.")
            return

    svc["available"].append({"id": model_id, "name": model_name, "tier": tier})
    svc["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    print(f"  Added {model_name} to {display}")


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

    while True:
        print("  Commands:")
        print("    claude / chatgpt / gemini  — change model for a service")
        print("    add <service>              — add a new model to a service")
        print("    remove <service>           — remove a model from a service")
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
        elif cmd in ("claude", "chatgpt", "gemini"):
            select_model(data, cmd)
        elif cmd.startswith("add "):
            service = cmd.split()[1] if len(cmd.split()) > 1 else ""
            if service in ("claude", "chatgpt", "gemini"):
                add_model(data, service)
            else:
                print(f"  Unknown service: {service}")
        elif cmd.startswith("remove "):
            service = cmd.split()[1] if len(cmd.split()) > 1 else ""
            if service in ("claude", "chatgpt", "gemini"):
                remove_model(data, service)
            else:
                print(f"  Unknown service: {service}")
        else:
            print(f"  Unknown command: {cmd}")

    save_models(data)
    print("\n  Saved to config/browser-models.json\n")


def discover_models():
    """Open browser to visually check for new models at each service."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed. Run: pip install playwright && playwright install chromium")
        return

    data = load_models()
    print("""
  Opening each service to check for new models.
  When the page loads, look at the model selector/dropdown.
  Note any new models you see, then close the tab.
  After checking all services, you'll be able to add new models.
""")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        for key in ("claude", "chatgpt", "gemini"):
            svc = data.get(key, {})
            session_path = os.path.join(SESSION_DIR, f"{key}.json")
            if not os.path.exists(session_path):
                print(f"  Skipping {SERVICE_NAMES[key]} — no session file")
                continue

            context = browser.new_context(storage_state=session_path)
            page = context.new_page()

            urls = {"claude": "https://claude.ai/new", "chatgpt": "https://chatgpt.com/",
                    "gemini": "https://gemini.google.com/app"}
            print(f"  Opening {SERVICE_NAMES[key]}...")
            page.goto(urls[key], timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            input(f"  Check {SERVICE_NAMES[key]}'s model list. Press Enter when done...")
            context.close()

        browser.close()

    print("\n  Now add any new models you found:\n")
    for key in ("claude", "chatgpt", "gemini"):
        resp = input(f"  Add new models to {SERVICE_NAMES[key]}? [y/N]: ").strip().lower()
        if resp == "y":
            while True:
                add_model(data, key)
                more = input("  Add another? [y/N]: ").strip().lower()
                if more != "y":
                    break

    save_models(data)
    print("\n  Saved to config/browser-models.json\n")
    show_selections(data)


if __name__ == "__main__":
    if "--show" in sys.argv:
        data = load_models()
        show_selections(data)
    elif "--discover" in sys.argv:
        discover_models()
    else:
        data = load_models()
        interactive_mode(data)
