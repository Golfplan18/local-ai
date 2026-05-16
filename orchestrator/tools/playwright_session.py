"""Playwright-based browser session manager for commercial AI services.

Uses persistent browser profiles (not storage_state) so that passkeys,
saved passwords, OAuth tokens, and all other browser credentials survive
across sessions — exactly like a real browser.

Each service gets its own profile directory under ~/ora/config/browser-profiles/.
First login: user logs in however they want (passkey, password, magic link).
Subsequent launches: the profile remembers everything.

Two execution paths live here:

1. **PlaywrightSession** — one-shot per-call usage (originally written for the
   browser_evaluate boot-C tool and for the auth/MFA bootstrap). Each call
   launches its own Chrome, runs the dispatch, and shuts down. Safe for a
   single dispatch at a time per service; *not* safe for parallel calls
   against the same profile directory because Chrome holds an exclusive
   lock on ``user_data_dir``.

2. **dispatch_via_worker** — the hot path used by the chat pipeline. A
   single worker thread per service owns a long-lived Playwright context
   for the lifetime of the server. Other threads submit prompts through a
   queue; the worker processes them FIFO, opening a fresh page per dispatch
   and closing it when done. This eliminates the profile-lock contention
   that hits parallel ``launch_persistent_context`` calls, keeps Playwright
   sync API on a single thread (its only supported mode), and still allows
   cross-service parallelism (e.g. Claude + ChatGPT workers run independently).
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import threading
import time

import keyring
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

PROFILE_DIR = os.path.expanduser("~/ora/config/browser-profiles/")
KEYRING_NAMESPACE = "ora-browser"


def _type_multiline(page, text: str) -> None:
    """Type a possibly-multiline prompt into a focused contenteditable.

    ``page.keyboard.type`` sends an "Enter" key event for every ``\\n``
    in the string, which chat UIs (claude.ai, chatgpt.com, etc.) interpret
    as "submit." That submits a partial prompt and triggers the model on
    incomplete input — the exact failure mode we hit on the Gear-4
    reviser/consolidator prompts, which contain section headers separated
    by blank lines.

    Workaround: split on ``\\n``, type each segment as plain text, and
    press ``Shift+Enter`` between segments. ``Shift+Enter`` is the
    universal "insert line break, do not submit" convention. Empty
    segments (from consecutive newlines) still emit the Shift+Enter so
    the visual line spacing is preserved.

    No per-character delay: at 5ms × 10K chars we'd spend 50 seconds at
    the keyboard, during which the SPA can re-render the input,
    blur the focus, or run a debounce that misorders characters. Native
    keyboard.type with delay=0 is fast and reliable.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line:
            page.keyboard.type(line)
        if i < len(lines) - 1:
            page.keyboard.press("Shift+Enter")


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

        Closes any tabs Chrome restored from the prior session and opens a
        fresh page on the service's new-chat URL. Without this, a restored
        tab sitting on an old conversation would persist past the goto()
        because SPAs like claude.ai don't always honor mid-route navigation.
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

        # Close every tab Chrome restored from the prior session, then open a
        # single fresh page. This prevents a stale conversation tab from being
        # the active page when send_prompt fires.
        for p in list(self._context.pages):
            try:
                p.close()
            except Exception:
                pass
        self.page = self._context.new_page()

        target_url = self.config.get("new_chat_url") or self.config["url"]
        self.page.goto(target_url, timeout=30000)
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
        """Type a prompt, submit it, and return the response text.

        Always navigates to ``new_chat_url`` (falling back to ``url``) before
        typing, so each dispatch goes into a fresh conversation thread rather
        than appending to whatever conversation was last open in this browser
        context. Without this guard, prompts accumulate in one thread, the
        context window bloats, and subsequent dispatches hang waiting for the
        page to settle.
        """
        page = self.page

        fresh_url = self.config.get("new_chat_url") or self.config.get("url")
        if fresh_url:
            try:
                page.goto(fresh_url, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeout:
                    pass
                page.wait_for_timeout(500)  # let the SPA settle the input
            except Exception:
                pass  # fall through; the input lookup below will retry

        # Find the input element
        input_el = self._find_element(self.config["input_selector"])
        if not input_el:
            raise RuntimeError(f"Input not found: {self.config['input_selector']}")

        # Determine input type
        tag = input_el.evaluate("el => el.tagName.toLowerCase()")
        is_ce = input_el.evaluate("el => el.contentEditable === 'true'")

        # Count existing responses for baseline
        baseline = self._count_responses()

        if tag in ("input", "textarea"):
            input_el.fill(prompt)
        else:
            # Contenteditable — split on '\n' and use Shift+Enter between
            # lines so newlines don't trigger premature submit. See
            # ``_type_multiline`` docstring for rationale.
            input_el.click()
            _type_multiline(page, prompt)

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

    def _wait_for_response(self, baseline: int, timeout: int = 300) -> str:
        """Poll for the model's response. Returns when generation completes.

        Uses the explicit ``response_streaming_selector`` (when configured)
        as the authoritative done signal; falls back to a long-window
        text-stability check. See ``_ServiceWorker._wait_for_response`` for
        the design rationale — this mirrors that logic for the one-shot
        path used by the auth/MFA bootstrap.
        """
        page = self.page
        sel = self.config.get("response_selector", "")
        streaming_sel = self.config.get("response_streaming_selector", "")
        # 90s of no change; see _ServiceWorker._wait_for_response for
        # rationale (reasoning-model preamble pauses).
        STABILITY_POLLS = 45
        POLL_MS = 2000

        last_text = ""
        stable_polls = 0
        ever_streamed = False
        deadline = time.time() + timeout

        while time.time() < deadline:
            page.wait_for_timeout(POLL_MS)

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

            if streaming_sel:
                still_streaming = False
                for s in streaming_sel.split(","):
                    try:
                        if page.locator(s.strip()).count() > 0:
                            still_streaming = True
                            break
                    except Exception:
                        continue
                if still_streaming:
                    ever_streamed = True
                    last_text = text
                    stable_polls = 0
                    continue
                if ever_streamed and text.strip():
                    return text.strip()
                if text.strip():
                    last_text = text
                continue

            if not text.strip():
                continue
            if text == last_text:
                stable_polls += 1
                if stable_polls >= STABILITY_POLLS:
                    return text.strip()
            else:
                stable_polls = 0
                last_text = text

        if last_text.strip():
            return last_text.strip()
        raise RuntimeError(f"No response from {self.service} within {timeout}s")


# ────────────────────────────────────────────────────────────────────────────
# Worker-thread dispatcher (hot path used by the chat pipeline)
# ────────────────────────────────────────────────────────────────────────────


class _ServiceWorker:
    """Owns Playwright + a persistent context for ONE service, in ONE thread.

    The worker thread is the only thread that ever calls into the Playwright
    sync API for this service. Other threads submit dispatch requests through
    a queue and wait for the response. The worker processes requests FIFO,
    opening a fresh page per dispatch and closing it when done.
    """

    def __init__(self, service: str, config: dict, headless: bool = False):
        self.service = service
        self.config = config
        self.profile_path = os.path.join(PROFILE_DIR, service)
        self.headless = headless
        self._in_q: queue.Queue = queue.Queue()
        self._started = threading.Event()
        self._start_error: BaseException | None = None
        self._shutdown_done = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"browser-{service}", daemon=True
        )
        self._thread.start()
        self._started.wait(timeout=90)
        if self._start_error is not None:
            raise self._start_error
        if not self._started.is_set():
            raise RuntimeError(f"browser worker for '{service}' did not initialize in 90s")

    def _run(self):
        pw = None
        context = None
        try:
            os.makedirs(self.profile_path, exist_ok=True)
            pw = sync_playwright().start()
            context = pw.chromium.launch_persistent_context(
                user_data_dir=self.profile_path,
                channel="chrome",
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            # Close every tab Chrome restored from the prior run.
            for p in list(context.pages):
                try:
                    p.close()
                except Exception:
                    pass
        except BaseException as e:
            self._start_error = e
            self._started.set()
            return

        self._started.set()

        try:
            while True:
                req = self._in_q.get()
                if req is None:
                    break
                prompt, reply_q, model_info = req
                try:
                    result = self._handle(context, prompt, model_info)
                    reply_q.put(("ok", result))
                except BaseException as e:
                    reply_q.put(("err", e))
        finally:
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if pw is not None:
                    pw.stop()
            except Exception:
                pass
            self._shutdown_done.set()

    # ── Per-dispatch flow ──────────────────────────────────────────────

    def _handle(self, context, prompt: str, model_info) -> str:
        page = context.new_page()
        try:
            new_url = self.config.get("new_chat_url") or self.config.get("url")
            if new_url:
                self._goto_with_retry(page, new_url)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeout:
                    pass
                page.wait_for_timeout(500)

            if not self._is_logged_in(page):
                raise RuntimeError(
                    f"service '{self.service}' is not logged in; "
                    f"run the auth bootstrap before dispatching prompts"
                )

            model_status = None
            if model_info and model_info.get("ui"):
                model_status = self._switch_model(page, model_info)

            response = self._send_and_wait(page, prompt)
            if model_status:
                return f"{model_status}\n\n{response}"
            return response
        finally:
            try:
                page.close()
            except Exception:
                pass

    def _goto_with_retry(self, page, url: str, attempts: int = 3) -> None:
        """Navigate with exponential backoff on HTTP and timeout failures.

        Anti-bot systems (notably ChatGPT's ``?temporary-chat=true``)
        sporadically return ``net::ERR_HTTP_RESPONSE_CODE_FAILURE`` to
        automated navigation when the worker has issued several
        requests in rapid succession. A single retry with a short pause
        usually clears the throttle. We try up to ``attempts`` times with
        backoff before letting the original exception escape so the
        caller's contingency path can fire.

        Backoff schedule: 0s (first attempt), 5s, 15s. Total worst-case
        added latency before falling out: ~20s, which is acceptable
        against the alternative of a degraded step.
        """
        delays = [0, 5, 15][:attempts]
        last_exc = None
        for i, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                page.goto(url, timeout=30000)
                return
            except Exception as e:
                last_exc = e
                msg = str(e)
                # Only retry on transient navigation failures. Don't retry
                # on TargetClosedError or auth failures — those won't recover.
                if (
                    "ERR_HTTP_RESPONSE_CODE_FAILURE" not in msg
                    and "ERR_CONNECTION_RESET" not in msg
                    and "ERR_NETWORK_CHANGED" not in msg
                    and "Timeout" not in msg
                    and "timed out" not in msg.lower()
                ):
                    raise
        # All attempts failed — re-raise the last exception so the worker's
        # contingency layer sees the real failure shape.
        if last_exc is not None:
            raise last_exc

    def _is_logged_in(self, page) -> bool:
        indicator = self.config.get("logged_in_indicator")
        if not indicator:
            return True
        for sel in indicator.split(","):
            try:
                el = page.locator(sel.strip()).first
                if el.is_visible(timeout=5000):
                    return True
            except Exception:
                continue
        return False

    def _switch_model(self, page, model_info: dict) -> str | None:
        ui = model_info["ui"]
        model_name = model_info["name"]
        button_selector = ui.get("model_button", "")
        option_selector = ui.get("model_option", "").replace("{model_name}", model_name)
        close_action = ui.get("close_action", "Escape")
        if not button_selector or not option_selector:
            return None
        try:
            clicked = False
            for sel in button_selector.split(","):
                try:
                    btn = page.locator(sel.strip()).first
                    if btn.is_visible(timeout=3000):
                        btn.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                return f"[model switch] selector button not found for {self.service}"
            page.wait_for_timeout(1000)
            for sel in option_selector.split(","):
                try:
                    opt = page.locator(sel.strip()).first
                    if opt.is_visible(timeout=3000):
                        opt.click()
                        page.wait_for_timeout(1500)
                        return f"[model switch] {self.service} → {model_name}"
                except Exception:
                    continue
            page.keyboard.press(close_action)
            return f"[model switch] '{model_name}' not in {self.service} dropdown — using default"
        except Exception as e:
            try:
                page.keyboard.press(close_action)
            except Exception:
                pass
            return f"[model switch] {self.service} failed: {e} — using default"

    def _send_and_wait(self, page, prompt: str) -> str:
        input_sel = self.config["input_selector"]
        input_el = None
        for sel in input_sel.split(","):
            try:
                el = page.locator(sel.strip()).first
                if el.is_visible(timeout=5000):
                    input_el = el
                    break
            except Exception:
                continue
        if input_el is None:
            raise RuntimeError(f"input not found: {input_sel}")

        tag = input_el.evaluate("el => el.tagName.toLowerCase()")
        is_ce = input_el.evaluate("el => el.contentEditable === 'true'")

        baseline = self._count_responses(page)

        if tag in ("input", "textarea"):
            # Plain inputs/textareas accept fill() — sets value atomically,
            # no per-character keyboard events, no newline-submit hazard.
            input_el.fill(prompt)
        else:
            # Contenteditable (claude.ai ProseMirror, chatgpt.com ProseMirror,
            # etc.). page.keyboard.type would send an Enter key event for
            # every '\n', which most chat UIs catch as "submit" — that
            # submits a partial prompt. Split on newlines and use
            # Shift+Enter between segments (universal "soft return").
            input_el.click()
            _type_multiline(page, prompt)

        page.wait_for_timeout(500)

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
            input_el.press("Enter")

        return self._wait_for_response(page, baseline)

    def _count_responses(self, page) -> int:
        sel = self.config.get("response_selector", "")
        for s in sel.split(","):
            try:
                count = page.locator(s.strip()).count()
                if count > 0:
                    return count
            except Exception:
                continue
        return 0

    def _wait_for_response(self, page, baseline: int, timeout: int = 300) -> str:
        """Poll for the model's response and return when generation completes.

        Completion detection has two layers:

        1. **Streaming indicator (authoritative).** If the service config
           defines ``response_streaming_selector`` (e.g. Claude's
           ``[data-is-streaming="true"]``, ChatGPT's visible stop button),
           treat "no element matches the streaming selector" as the
           definitive done signal. This avoids the failure mode where a
           model pauses mid-stream for >10s while reasoning and a
           text-stability heuristic prematurely declares completion,
           grabbing a half-finished response.

        2. **Stability fallback.** When the streaming selector is not
           configured for this service, fall back to "text unchanged for
           STABILITY_POLLS consecutive polls." The window is generous
           (30s) so that thinking pauses don't trigger early exit.

        Streaming must be observed at least once before we'll accept
        "not streaming" as completion — otherwise a fresh page (with no
        streaming indicator yet present) would be misread as already done.
        """
        sel = self.config.get("response_selector", "")
        streaming_sel = self.config.get("response_streaming_selector", "")
        # 90s of no change before fallback declares done. The previous 30s
        # window was too tight for reasoning models — GPT-5 and Claude
        # Extended Thinking emit a "Thought for a second" preamble within
        # the first seconds, then pause silently for 30-60s while the
        # reasoning chain runs, then emit the real response. The old
        # window declared completion during the reasoning pause, capturing
        # only the preamble (~90 chars). 90s covers typical reasoning
        # latencies without leaving the worker idle indefinitely.
        STABILITY_POLLS = 45  # 45 × 2s = 90s of no change
        POLL_MS = 2000

        last_text = ""
        stable_polls = 0
        ever_streamed = False
        deadline = time.time() + timeout

        while time.time() < deadline:
            page.wait_for_timeout(POLL_MS)

            # Read current candidate text from the last response element.
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

            if streaming_sel:
                # Authoritative: ask the page whether it's still streaming.
                still_streaming = False
                for s in streaming_sel.split(","):
                    try:
                        if page.locator(s.strip()).count() > 0:
                            still_streaming = True
                            break
                    except Exception:
                        continue
                if still_streaming:
                    ever_streamed = True
                    last_text = text
                    stable_polls = 0
                    continue
                # Not streaming. Only trust this as "complete" once we've
                # actually seen streaming happen (otherwise a fresh page
                # before the model has started looks identical to "done").
                if ever_streamed and text.strip():
                    return text.strip()
                # Haven't seen streaming yet — keep polling so the model
                # has time to actually start.
                if text.strip():
                    last_text = text
                continue

            # No streaming selector configured — fall back to text-stability
            # with a generous window.
            if not text.strip():
                continue
            if text == last_text:
                stable_polls += 1
                if stable_polls >= STABILITY_POLLS:
                    return text.strip()
            else:
                stable_polls = 0
                last_text = text

        if last_text.strip():
            return last_text.strip()
        raise RuntimeError(f"no response from {self.service} within {timeout}s")

    # ── Public submit / shutdown ───────────────────────────────────────

    def submit(self, prompt: str, model_info: dict | None = None, timeout: float = 420) -> str:
        # Outer timeout must outlast _wait_for_response (300s) plus setup
        # overhead (goto, auth check, model switch). 420s = 7min gives the
        # inner wait its full 300s plus 2min of slack for the rest.
        reply_q: queue.Queue = queue.Queue()
        self._in_q.put((prompt, reply_q, model_info))
        kind, payload = reply_q.get(timeout=timeout)
        if kind == "err":
            if isinstance(payload, BaseException):
                raise payload
            raise RuntimeError(str(payload))
        return payload

    def shutdown(self, join_timeout: float = 10.0):
        try:
            self._in_q.put(None)
        except Exception:
            pass
        self._thread.join(timeout=join_timeout)


# Module-level registry of service workers (one worker thread per service).
_WORKERS: dict[str, _ServiceWorker] = {}
_WORKERS_LOCK = threading.Lock()


def get_worker(service: str, config: dict, headless: bool = False) -> _ServiceWorker:
    """Get or create the singleton worker for a service. Lazy-init on first use."""
    with _WORKERS_LOCK:
        worker = _WORKERS.get(service)
        if worker is not None and worker._thread.is_alive():
            return worker
        # Either no worker yet, or the previous one died. Make a new one.
        if worker is not None:
            try:
                worker.shutdown(join_timeout=2)
            except Exception:
                pass
        worker = _ServiceWorker(service, config, headless=headless)
        _WORKERS[service] = worker
        return worker


def dispatch_via_worker(
    service: str,
    prompt: str,
    config: dict,
    model_info: dict | None = None,
    headless: bool = False,
    timeout: float = 420,
) -> str:
    """Submit a prompt to the service's worker and wait for the response.

    This is the hot path used by the chat pipeline. Safe to call concurrently:
    different services run in parallel; same-service calls serialize through
    the worker's queue.
    """
    worker = get_worker(service, config, headless=headless)
    return worker.submit(prompt, model_info=model_info, timeout=timeout)


def shutdown_all_workers():
    """Tear down every service worker. Called at server exit via atexit."""
    with _WORKERS_LOCK:
        workers = list(_WORKERS.values())
        _WORKERS.clear()
    for w in workers:
        try:
            w.shutdown(join_timeout=5)
        except Exception:
            pass


atexit.register(shutdown_all_workers)
