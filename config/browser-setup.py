#!/usr/bin/env python3
"""First-time browser session setup for Ora.

Opens a visible browser for each AI service so the user can log in
manually. Uses persistent browser profiles so passkeys, saved passwords,
and OAuth tokens all work — exactly like a real browser.

Each service gets its own profile directory under
~/ora/config/browser-profiles/<service>/

Usage:
  python3 config/browser-setup.py                     # set up all services
  python3 config/browser-setup.py --service claude     # one service only
  python3 config/browser-setup.py --check              # check session validity
  python3 config/browser-setup.py --list               # list services + status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import getpass

import keyring
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

SERVICES_JSON = os.path.expanduser("~/ora/config/browser-services.json")
PROFILE_DIR = os.path.expanduser("~/ora/config/browser-profiles/")
KEYRING_NAMESPACE = "ora-browser"


def load_services() -> dict:
    with open(SERVICES_JSON) as f:
        return json.load(f)


def check_session(service: str, config: dict) -> bool:
    """Headless check: is the saved session still valid?"""
    profile_path = os.path.join(PROFILE_DIR, service)
    if not os.path.exists(profile_path):
        return False

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(config["url"], timeout=20000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PWTimeout:
                pass

            indicator = config.get("logged_in_indicator", "")
            for sel in indicator.split(","):
                try:
                    el = page.locator(sel.strip()).first
                    if el.is_visible(timeout=5000):
                        context.close()
                        return True
                except Exception:
                    continue

            context.close()
            return False
    except Exception:
        return False


def setup_service(service: str, config: dict) -> bool:
    """Open headed browser for manual login using persistent profile."""
    profile_path = os.path.join(PROFILE_DIR, service)
    os.makedirs(profile_path, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Check if already logged in from a previous setup
        page.goto(config["url"], timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PWTimeout:
            pass

        indicator = config.get("logged_in_indicator", "")
        already_in = False
        for sel in indicator.split(","):
            try:
                el = page.locator(sel.strip()).first
                if el.is_visible(timeout=3000):
                    already_in = True
                    break
            except Exception:
                continue

        if already_in:
            print(f"  Already logged in to {service}.")
        else:
            # Navigate to login page
            login_url = config.get("login_url", config["url"])
            page.goto(login_url, timeout=30000)

            print(f"  Log into {service} in the browser window.")
            print(f"  Use passkey, password, magic link — whatever works.")
            print(f"  Polling for login (up to 3 minutes)...")

            for i in range(90):  # 3 minutes
                import time
                time.sleep(2)
                # Navigate to main URL to check login status
                try:
                    page.goto(config["url"], timeout=15000)
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PWTimeout:
                    pass
                except Exception:
                    pass

                for sel in indicator.split(","):
                    try:
                        el = page.locator(sel.strip()).first
                        if el.is_visible(timeout=2000):
                            print(f"  Login detected!")
                            already_in = True
                            break
                    except Exception:
                        continue
                if already_in:
                    break

                if i % 15 == 14:
                    print(f"  Still waiting... ({(i+1)*2}s)")

                # Go back to login page if not logged in yet
                if not already_in:
                    try:
                        page.go_back()
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

            if not already_in:
                print(f"  Timeout — could not detect login for {service}.")
                print(f"  Profile saved anyway — credentials may still work on next launch.")

        context.close()
        print(f"  Profile saved to {profile_path}")

    # Offer to save credentials
    existing_user = keyring.get_password(KEYRING_NAMESPACE, f"{service}-username")
    if existing_user:
        print(f"  Credentials already stored (username: {existing_user})")
        update = input("  Update stored credentials? [y/N] ").strip().lower()
        if update != "y":
            return True

    save_creds = input("  Save credentials to keyring for auto-login? [y/N] ").strip().lower()
    if save_creds == "y":
        username = input("  Username/email: ").strip()
        password = getpass.getpass("  Password: ")
        if username and password:
            keyring.set_password(KEYRING_NAMESPACE, f"{service}-username", username)
            keyring.set_password(KEYRING_NAMESPACE, f"{service}-password", password)
            print(f"  Credentials saved to keyring.")
        else:
            print(f"  Skipped — empty username or password.")

    return True


def list_services(services: dict) -> None:
    """Print all services with their session status."""
    print(f"\n{'Service':<15} {'Has Profile':<15} {'Has Credentials'}")
    print("-" * 45)
    for name in sorted(services.keys()):
        profile_path = os.path.join(PROFILE_DIR, name)
        has_profile = "yes" if os.path.exists(profile_path) else "no"
        has_creds = "yes" if keyring.get_password(KEYRING_NAMESPACE, f"{name}-username") else "no"
        print(f"{name:<15} {has_profile:<15} {has_creds}")
    print()


def check_all(services: dict) -> None:
    """Check session validity for all services."""
    print(f"\nChecking sessions (headless)...\n")
    for name, config in sorted(services.items()):
        profile_path = os.path.join(PROFILE_DIR, name)
        if not os.path.exists(profile_path):
            print(f"  {name:<15} no profile")
            continue
        print(f"  {name:<15} checking...", end="", flush=True)
        valid = check_session(name, config)
        print(f"\r  {name:<15} {'valid' if valid else 'EXPIRED'}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Set up browser sessions for Ora")
    parser.add_argument("--service", "-s", help="Set up a specific service only")
    parser.add_argument("--check", action="store_true", help="Check session validity")
    parser.add_argument("--list", action="store_true", help="List services and status")
    args = parser.parse_args()

    services = load_services()

    if args.list:
        list_services(services)
        return

    if args.check:
        check_all(services)
        return

    # Setup mode
    if args.service:
        name = args.service.lower()
        if name not in services:
            print(f"Unknown service: {name}")
            print(f"Available: {', '.join(sorted(services.keys()))}")
            sys.exit(1)
        targets = {name: services[name]}
    else:
        targets = services

    print(f"\nOra Browser Setup — {len(targets)} service(s)\n")
    print("A browser window will open for each service.")
    print("Log in using whatever method works — passkey, password, magic link.")
    print("The browser will remember your login for future use.\n")

    for name, config in targets.items():
        print(f"[{name}]")
        try:
            setup_service(name, config)
        except Exception as e:
            print(f"  Error: {e}")
        print()

    print("Setup complete.")


if __name__ == "__main__":
    main()
