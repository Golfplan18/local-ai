"""Playwright-based browser session manager for commercial AI services.

Uses persistent browser profiles (not storage_state) so that passkeys,
saved passwords, OAuth tokens, and all other browser credentials survive
across sessions — exactly like a real browser.

Each service gets its own profile directory under ~/ora/config/browser-profiles/.
First login: user logs in however they want (passkey, password, magic link).
Subsequent launches: the profile remembers everything.

Usage from browser_evaluate.py:
    session = PlaywrightSession(service, config)
    session.launch()
    if session.ensure_authenticated():
        response = session.send_prompt(prompt)
    session.close()
"""

from __future__ import annotations

import json
import os
import time

import keyring
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE_DIR = os.path.expanduser("~/ora/config/browser-profiles/")
KEYRING_NAMESPACE = "ora-browser"


class PlaywrightSession:
    """Manages a single Playwright browser session for one AI service."""

    def __init__(self, service: str, config: dict):
        self.service = service
        self.config = config
        self.profile_path = os.path.join(PROFILE_DIR, service)
        self._pw = None
        self._context = None  # persistent context IS the browser
        self.page = None
        self._headless = True

    # ── Lifecycle ──────────────────────────────────────────────────────

    def launch(self, headless: bool = False) -> None:
        """Start Playwright with a persistent browser profile.

        Always runs headed by default — Cloudflare and other bot detection
        services block headless browsers.
        """
        self._headless = headless
        os.makedirs(self.profile_path, exist_ok=True)
        self._pw = sync_playwright().start()

        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_path,
            channel="chrome",
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )

        # Use existing page or create one
        if self._context.pages:
            self.page = self._context.pages[0]
        else:
            self.page = self._context.new_page()

        self.page.goto(self.config["url"], timeout=30000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass  # Some SPAs never reach networkidle

    def close(self) -> None:
        """Shut down the persistent context (profile auto-saved on disk)."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._context = None
        self.page = None
        self._pw = None

    # ── Authentication ─────────────────────────────────────────────────

    def is_logged_in(self) -> bool:
        """Check if the logged-in UI is visible (vs a login wall)."""
        indicator = self.config.get("logged_in_indicator")
        if not indicator:
            return True  # No indicator configured — assume logged in

        for sel in indicator.split(","):
            try:
                el = self.page.locator(sel.strip()).first
                if el.is_visible(timeout=5000):
                    return True
            except Exception:
                continue
        return False

    def _get_credentials(self) -> tuple[str | None, str | None]:
        """Retrieve stored credentials from keyring."""
        username = keyring.get_password(KEYRING_NAMESPACE, f"{self.service}-username")
        password = keyring.get_password(KEYRING_NAMESPACE, f"{self.service}-password")
        return username, password

    def authenticate(self) -> bool:
        """Auto-login using stored credentials. Returns True on success."""
        username, password = self._get_credentials()
        if not username or not password:
            return False

        login_selectors = self.config.get("login_selectors", {})
        if not login_selectors:
            return False

        login_url = self.config.get("login_url")
        if login_url:
            self.page.goto(login_url, timeout=30000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                pass

        # Fill username
        username_sel = login_selectors.get("username", "")
        for sel in username_sel.split(","):
            try:
                el = self.page.locator(sel.strip()).first
                if el.is_visible(timeout=3000):
                    el.fill(username)
                    break
            except Exception:
                continue

        # Some login flows have a "Next" step between username and password
        submit_sel = login_selectors.get("submit", "")
        for sel in submit_sel.split(","):
            try:
                btn = self.page.locator(sel.strip()).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    self.page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

        # Fill password
        password_sel = login_selectors.get("password", "")
        for sel in password_sel.split(","):
            try:
                el = self.page.locator(sel.strip()).first
                if el.is_visible(timeout=5000):
                    el.fill(password)
                    break
            except Exception:
                continue

        # Submit
        for sel in submit_sel.split(","):
            try:
                btn = self.page.locator(sel.strip()).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    break
            except Exception:
                continue

        # Wait for navigation
        self.page.wait_for_timeout(5000)

        # Navigate to the service URL to check
        self.page.goto(self.config["url"], timeout=30000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

        return self.is_logged_in()

    def handle_mfa(self) -> bool:
        """Relaunch in headed mode for manual login/MFA completion."""
        if self._headless:
            # Close headless, relaunch headed (same profile)
            if self._context:
                self._context.close()
            if self._pw:
                self._pw.stop()

            self._headless = False
            self._pw = sync_playwright().start()
            self._context = self._pw.chromium.launch_persistent_context(
                user_data_dir=self.profile_path,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )

            if self._context.pages:
                self.page = self._context.pages[0]
            else:
                self.page = self._context.new_page()

            self.page.goto(self.config["url"], timeout=30000)

        print(f"\n[ora] Login required for {self.service}.")
        print(f"[ora] Complete the login in the browser window.")
        print(f"[ora] Waiting up to 120 seconds...\n")

        deadline = time.time() + 120
        while time.time() < deadline:
            if self.is_logged_in():
                return True
            self.page.wait_for_timeout(2000)

        print(f"[ora] Login timeout for {self.service}.")
        return False

    def ensure_authenticated(self) -> bool:
        """Full authentication flow: check -> auto-login -> manual fallback."""
        if self.is_logged_in():
            return True
        if self.authenticate():
            return True
        return self.handle_mfa()

    # ── Prompt interaction ─────────────────────────────────────────────

    def send_prompt(self, prompt: str) -> str:
        """Type a prompt, submit it, and return the response text."""
        page = self.page

        # Find the input element
        input_el = self._find_element(self.config["input_selector"])
        if not input_el:
            raise RuntimeError(f"Input not found: {self.config['input_selector']}")

        # Determine input type
        tag = input_el.evaluate("el => el.tagName.toLowerCase()")
        is_ce = input_el.evaluate("el => el.contentEditable === 'true'")

        # Count existing responses for baseline
        baseline = self._count_responses()

        if is_ce:
            # Contenteditable: real keyboard input triggers all framework events
            input_el.click()
            page.keyboard.type(prompt, delay=5)
        elif tag in ("input", "textarea"):
            input_el.fill(prompt)
        else:
            input_el.click()
            page.keyboard.type(prompt, delay=5)

        page.wait_for_timeout(500)

        # Click send button
        send_sel = self.config.get("send_selector", "")
        sent = False
        for sel in send_sel.split(","):
            try:
                btn = page.locator(sel.strip()).first
                if btn.is_visible(timeout=3000) and btn.is_enabled(timeout=1000):
                    btn.click()
                    sent = True
                    break
            except Exception:
                continue

        if not sent:
            # Fallback: press Enter
            input_el.press("Enter")

        # Wait for response
        return self._wait_for_response(baseline)

    def _find_element(self, selector_list: str):
        """Find the first visible element from a comma-separated selector list."""
        for sel in selector_list.split(","):
            try:
                el = self.page.locator(sel.strip()).first
                if el.is_visible(timeout=3000):
                    return el
            except Exception:
                continue
        return None

    def _count_responses(self) -> int:
        """Count existing response elements for baseline comparison."""
        sel = self.config.get("response_selector", "")
        for s in sel.split(","):
            try:
                count = self.page.locator(s.strip()).count()
                if count > 0:
                    return count
            except Exception:
                continue
        return 0

    def _wait_for_response(self, baseline: int, timeout: int = 120) -> str:
        """Poll for a new response element to stabilize."""
        page = self.page
        sel = self.config.get("response_selector", "")
        last_text = ""
        stable_count = 0
        deadline = time.time() + timeout

        while time.time() < deadline:
            page.wait_for_timeout(2000)

            text = ""
            for s in sel.split(","):
                try:
                    elements = page.locator(s.strip())
                    total = elements.count()
                    if total > baseline:
                        text = elements.nth(total - 1).inner_text(timeout=5000)
                        if text.strip():
                            break
                except Exception:
                    continue

            if text.strip():
                if text == last_text:
                    stable_count += 1
                    if stable_count >= 3:
                        return text.strip()
                else:
                    stable_count = 0
                    last_text = text

        if last_text.strip():
            return last_text.strip()
        raise RuntimeError(f"No response from {self.service} within {timeout}s")
