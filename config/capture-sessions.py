#!/usr/bin/env python3
"""Capture AI Service Browser Sessions

Launches a visible browser. The user logs into their AI accounts.
The script detects which services are active and saves session state
for each one. Cross-platform — works on macOS, Linux, and Windows.

Usage:
    python3 capture-sessions.py            # interactive mode
    python3 capture-sessions.py --list     # show supported services
    python3 capture-sessions.py --check    # check existing sessions
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

WORKSPACE = os.path.expanduser("~/local-ai/")
SESSION_DIR = os.path.join(WORKSPACE, "config/browser-sessions/")
ENDPOINTS_JSON = os.path.join(WORKSPACE, "config/endpoints.json")

# ── Service Registry ───────────────────────────────────────────────────────
# Each entry: url patterns to detect, cookie domains to capture,
# display name, and the URL to show the user for login.

SERVICE_REGISTRY = {
    "claude": {
        "name": "Claude",
        "provider": "Anthropic",
        "login_url": "https://claude.ai/login",
        "detect_urls": ["claude.ai"],
        "cookie_domains": [".claude.ai", "claude.ai", ".anthropic.com", "anthropic.com"],
        "input_selector": '[data-testid="composer-input"], div[contenteditable="true"]',
        "response_selector": '.font-claude-message, [data-is-streaming="false"]',
        "tier": "free+paid",
    },
    "chatgpt": {
        "name": "ChatGPT",
        "provider": "OpenAI",
        "login_url": "https://chatgpt.com/",
        "detect_urls": ["chatgpt.com", "chat.openai.com"],
        "cookie_domains": [".openai.com", "openai.com", "chat.openai.com",
                           ".chatgpt.com", "chatgpt.com"],
        "input_selector": "#prompt-textarea, textarea",
        "response_selector": ".markdown, .prose",
        "tier": "free+paid",
    },
    "gemini": {
        "name": "Gemini",
        "provider": "Google",
        "login_url": "https://gemini.google.com/app",
        "detect_urls": ["gemini.google.com"],
        "cookie_domains": [".google.com", "google.com", "gemini.google.com"],
        "input_selector": "rich-textarea, textarea",
        "response_selector": ".response-content, model-response",
        "tier": "free+paid",
    },
    "perplexity": {
        "name": "Perplexity",
        "provider": "Perplexity AI",
        "login_url": "https://www.perplexity.ai/",
        "detect_urls": ["perplexity.ai"],
        "cookie_domains": [".perplexity.ai", "perplexity.ai", "www.perplexity.ai"],
        "input_selector": "textarea",
        "response_selector": ".prose, .markdown",
        "tier": "free+paid",
    },
    "mistral": {
        "name": "Mistral / Le Chat",
        "provider": "Mistral AI",
        "login_url": "https://chat.mistral.ai/chat",
        "detect_urls": ["chat.mistral.ai", "mistral.ai"],
        "cookie_domains": [".mistral.ai", "mistral.ai", "chat.mistral.ai"],
        "input_selector": "textarea",
        "response_selector": ".prose, .markdown",
        "tier": "free+paid",
    },
    "copilot": {
        "name": "Copilot",
        "provider": "Microsoft",
        "login_url": "https://copilot.microsoft.com/",
        "detect_urls": ["copilot.microsoft.com"],
        "cookie_domains": [".microsoft.com", "microsoft.com",
                           "copilot.microsoft.com", ".bing.com"],
        "input_selector": "textarea, #searchbox",
        "response_selector": ".ac-textBlock, .content",
        "tier": "free+paid",
    },
    "deepseek": {
        "name": "DeepSeek",
        "provider": "DeepSeek",
        "login_url": "https://chat.deepseek.com/",
        "detect_urls": ["chat.deepseek.com"],
        "cookie_domains": [".deepseek.com", "deepseek.com", "chat.deepseek.com"],
        "input_selector": "textarea",
        "response_selector": ".markdown, .prose",
        "tier": "free+paid",
    },
    "grok": {
        "name": "Grok",
        "provider": "xAI",
        "login_url": "https://grok.com/",
        "detect_urls": ["grok.com", "x.com/i/grok"],
        "cookie_domains": [".grok.com", "grok.com", ".x.com", "x.com"],
        "input_selector": "textarea",
        "response_selector": ".markdown, .message-content",
        "tier": "free+paid",
    },
    "poe": {
        "name": "Poe",
        "provider": "Quora",
        "login_url": "https://poe.com/",
        "detect_urls": ["poe.com"],
        "cookie_domains": [".poe.com", "poe.com"],
        "input_selector": "textarea",
        "response_selector": ".markdown, .prose",
        "tier": "free+paid",
    },
    "huggingchat": {
        "name": "HuggingChat",
        "provider": "Hugging Face",
        "login_url": "https://huggingface.co/chat/",
        "detect_urls": ["huggingface.co/chat"],
        "cookie_domains": [".huggingface.co", "huggingface.co"],
        "input_selector": "textarea",
        "response_selector": ".prose, .markdown",
        "tier": "free",
    },
    "meta_ai": {
        "name": "Meta AI",
        "provider": "Meta",
        "login_url": "https://www.meta.ai/",
        "detect_urls": ["meta.ai"],
        "cookie_domains": [".meta.ai", "meta.ai", "www.meta.ai"],
        "input_selector": "textarea",
        "response_selector": ".markdown, .prose",
        "tier": "free",
    },
    "cohere": {
        "name": "Coral (Cohere)",
        "provider": "Cohere",
        "login_url": "https://coral.cohere.com/",
        "detect_urls": ["coral.cohere.com"],
        "cookie_domains": [".cohere.com", "cohere.com", "coral.cohere.com"],
        "input_selector": "textarea",
        "response_selector": ".markdown, .prose",
        "tier": "free+paid",
    },
}


def _detect_service_from_url(url: str) -> str | None:
    """Match a URL to a service key from the registry."""
    for key, svc in SERVICE_REGISTRY.items():
        for pattern in svc["detect_urls"]:
            if pattern in url:
                return key
    return None


def _filter_cookies(all_cookies: list, domains: list) -> list:
    """Filter cookies to only those matching the service's domains."""
    filtered = []
    for cookie in all_cookies:
        cookie_domain = cookie.get("domain", "")
        for domain in domains:
            if cookie_domain == domain or cookie_domain.endswith(domain):
                filtered.append(cookie)
                break
    return filtered


def show_services():
    """Print the list of supported services."""
    print("\n  Supported AI Services:\n")
    for key, svc in SERVICE_REGISTRY.items():
        print(f"    {svc['name']:20s}  {svc['provider']:15s}  {svc['login_url']}")
    print()


def check_sessions():
    """Check which sessions already exist and are non-empty."""
    print("\n  Existing Sessions:\n")
    for key, svc in SERVICE_REGISTRY.items():
        path = os.path.join(SESSION_DIR, f"{key}.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                n_cookies = len(data.get("cookies", []))
                print(f"    ✓ {svc['name']:20s}  {n_cookies} cookies")
            except Exception:
                print(f"    ✗ {svc['name']:20s}  (corrupt file)")
        else:
            print(f"    - {svc['name']:20s}  (not configured)")
    print()


def capture_sessions():
    """Main interactive session capture flow."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n  Playwright is not installed. Installing now...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright

    os.makedirs(SESSION_DIR, exist_ok=True)

    print("""
  ╔══════════════════════════════════════════════════════════════╗
  ║           AI Service Session Capture                        ║
  ╠══════════════════════════════════════════════════════════════╣
  ║                                                              ║
  ║  A browser window will open. Log into ALL of your AI         ║
  ║  accounts — open a new tab for each service.                 ║
  ║                                                              ║
  ║  Supported services:                                         ║""")

    for key, svc in SERVICE_REGISTRY.items():
        print(f"  ║    • {svc['name']:18s} → {svc['login_url']:35s} ║")

    print("""  ║                                                              ║
  ║  Log into as many as you like. Skip any you don't use.       ║
  ║  When you're logged into everything, come back here           ║
  ║  and press Enter.                                             ║
  ║                                                              ║
  ╚══════════════════════════════════════════════════════════════╝
""")

    input("  Press Enter to open the browser...")

    detected = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # Open a start page with instructions
        page = context.new_page()
        page.set_content("""
        <html><body style="font-family: -apple-system, system-ui, sans-serif;
            max-width: 600px; margin: 60px auto; color: #333;">
        <h1>Log into your AI accounts</h1>
        <p>Open a new tab for each service and log in.
           When you're done, go back to the terminal and press Enter.</p>
        <h3>Quick links:</h3>
        <ul style="line-height: 2;">
        """ + "\n".join(
            f'<li><a href="{svc["login_url"]}" target="_blank">{svc["name"]}</a> — {svc["provider"]}</li>'
            for svc in SERVICE_REGISTRY.values()
        ) + """
        </ul>
        <p style="color: #888; margin-top: 40px;">
            This window will close automatically after capture.</p>
        </body></html>
        """)

        print("\n  Browser is open. Log into your AI accounts now.")
        print("  Open a new tab for each service.\n")
        input("  When you're logged into everything, press Enter to capture sessions... ")

        # Scan all open pages for detected services
        print("\n  Scanning tabs...\n")
        all_cookies = context.cookies()

        for pg in context.pages:
            url = pg.url
            service_key = _detect_service_from_url(url)
            if service_key and service_key not in detected:
                svc = SERVICE_REGISTRY[service_key]
                service_cookies = _filter_cookies(all_cookies, svc["cookie_domains"])
                if service_cookies:
                    detected[service_key] = {
                        "cookies": service_cookies,
                        "origins": [],
                    }
                    print(f"    ✓ Detected {svc['name']:18s} ({len(service_cookies)} cookies)")
                else:
                    print(f"    ? Detected {svc['name']:18s} tab but no cookies — may not be logged in")

        # Also check cookies for services whose tabs may have been closed
        for key, svc in SERVICE_REGISTRY.items():
            if key in detected:
                continue
            service_cookies = _filter_cookies(all_cookies, svc["cookie_domains"])
            if service_cookies:
                detected[key] = {
                    "cookies": service_cookies,
                    "origins": [],
                }
                print(f"    ✓ Found {svc['name']:18s} cookies ({len(service_cookies)} cookies, tab closed)")

        browser.close()

    if not detected:
        print("\n  No AI service sessions detected.")
        print("  Make sure you logged in and the pages fully loaded.\n")
        return

    # Save session files
    print(f"\n  Saving {len(detected)} session(s)...\n")
    saved = []
    for key, session_data in detected.items():
        svc = SERVICE_REGISTRY[key]
        path = os.path.join(SESSION_DIR, f"{key}.json")
        with open(path, "w") as f:
            json.dump(session_data, f, indent=2)
        saved.append(key)
        print(f"    Saved: {path}")

    # Update endpoints.json
    _update_endpoints(saved)

    # Update browser_evaluate service config
    _update_service_config(saved)

    print(f"""
  ╔══════════════════════════════════════════════════════════════╗
  ║  Done! Captured {len(saved):2d} service(s):{"":32s}║""")
    for key in saved:
        svc = SERVICE_REGISTRY[key]
        print(f"  ║    ✓ {svc['name']:53s}║")
    print("""  ║                                                              ║
  ║  Sessions saved to config/browser-sessions/                  ║
  ║  Endpoints registered in config/endpoints.json               ║
  ║                                                              ║
  ║  Re-run this script any time to refresh expired sessions.    ║
  ╚══════════════════════════════════════════════════════════════╝
""")


def _update_endpoints(saved_keys: list):
    """Add or update browser endpoints in endpoints.json."""
    if not os.path.exists(ENDPOINTS_JSON):
        print("    [warning] endpoints.json not found — skipping endpoint registration")
        return

    try:
        with open(ENDPOINTS_JSON) as f:
            config = json.load(f)
    except Exception as e:
        print(f"    [warning] Could not read endpoints.json: {e}")
        return

    endpoints = config.get("endpoints", [])
    existing_names = {ep.get("name") for ep in endpoints}
    today = datetime.now().strftime("%Y-%m-%d")

    for key in saved_keys:
        svc = SERVICE_REGISTRY[key]
        ep_name = f"{key}-browser"

        if ep_name in existing_names:
            # Update existing endpoint
            for ep in endpoints:
                if ep.get("name") == ep_name:
                    ep["status"] = "active"
                    ep["verified"] = today
                    break
            print(f"    Updated endpoint: {ep_name}")
        else:
            # Add new endpoint
            endpoints.append({
                "name": ep_name,
                "type": "browser",
                "service": key,
                "session_path": f"config/browser-sessions/{key}.json",
                "role": "gear5-commercial",
                "status": "active",
                "verified": today,
            })
            print(f"    Added endpoint: {ep_name}")

    config["endpoints"] = endpoints
    with open(ENDPOINTS_JSON, "w") as f:
        json.dump(config, f, indent=2)


def _update_service_config(saved_keys: list):
    """Write an extended service config that browser_evaluate can load."""
    config_path = os.path.join(WORKSPACE, "config/browser-services.json")
    services = {}
    for key in saved_keys:
        svc = SERVICE_REGISTRY[key]
        services[key] = {
            "url": svc["login_url"].replace("/login", "/new").replace("/chat", "/"),
            "session_file": f"{key}.json",
            "input_selector": svc["input_selector"],
            "response_selector": svc["response_selector"],
        }
    with open(config_path, "w") as f:
        json.dump(services, f, indent=2)


if __name__ == "__main__":
    if "--list" in sys.argv:
        show_services()
    elif "--check" in sys.argv:
        check_sessions()
    else:
        capture_sessions()
