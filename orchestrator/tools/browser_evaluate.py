"""Send a prompt to a commercial AI via browser automation.

Primary channel: Playwright with persistent sessions
  — opens headless Chromium, restores saved session state.
  — auto-re-authenticates from keyring credentials if session expired.
  — switches to headed mode for MFA challenges.

Fallback channel: Chrome extension (Ora Browser Bridge)
  — uses the user's authenticated Chrome sessions directly.
  — optional, for when Playwright is unavailable.

boot-C-agent interface:
  browser_evaluate(service, task_summary, artifact, evaluation_focus="")

Legacy interface (still accepted):
  browser_evaluate(service, prompt)

Model selection:
  For claude, chatgpt, and gemini, the selected model from
  config/browser-models.json is applied before sending the prompt.
  Run 'python3 config/update-models.py' to change model preferences.

First-time setup:
  python3 config/browser-setup.py            # all services
  python3 config/browser-setup.py --service claude  # one service
"""

from __future__ import annotations

import os
import json

SERVICES_JSON = os.path.expanduser("~/ora/config/browser-services.json")
MODELS_JSON = os.path.expanduser("~/ora/config/browser-models.json")

# ── Service config loading ─────────────────────────────────────────────────

# Load from enriched config file (primary source)
SERVICE_CONFIG: dict = {}
try:
    if os.path.exists(SERVICES_JSON):
        with open(SERVICES_JSON) as _f:
            SERVICE_CONFIG = json.load(_f)
except Exception:
    pass

# Built-in fallback for the big three (if JSON missing/corrupt)
if not SERVICE_CONFIG:
    SERVICE_CONFIG = {
        "claude": {
            "url": "https://claude.ai/new",
            "session_file": "claude.json",
            "input_selector": '[data-testid="composer-input"], div.ProseMirror[contenteditable="true"]',
            "send_selector": 'button[aria-label="Send Message"], button[data-testid="send-button"]',
            "response_selector": '.font-claude-message, [data-is-streaming="false"]',
            "logged_in_indicator": '[data-testid="composer-input"], div.ProseMirror',
        },
        "chatgpt": {
            "url": "https://chatgpt.com/",
            "session_file": "chatgpt.json",
            "input_selector": '#prompt-textarea, div.ProseMirror[contenteditable="true"]',
            "send_selector": 'button[data-testid="send-button"], button[aria-label="Send prompt"]',
            "response_selector": ".markdown, .prose",
            "logged_in_indicator": "#prompt-textarea, div.ProseMirror",
        },
        "gemini": {
            "url": "https://gemini.google.com/app",
            "session_file": "gemini.json",
            "input_selector": ".ql-editor, rich-textarea div[contenteditable='true']",
            "send_selector": 'button[aria-label="Send message"]',
            "response_selector": ".response-content, model-response, .message-content",
            "logged_in_indicator": ".ql-editor, rich-textarea",
        },
    }


def _load_model_prefs() -> dict:
    """Load model preferences from browser-models.json."""
    try:
        if os.path.exists(MODELS_JSON):
            with open(MODELS_JSON) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_selected_model(service: str) -> dict | None:
    """Get the selected model info for a service."""
    prefs = _load_model_prefs()
    svc = prefs.get(service)
    if not svc:
        return None

    selected_id = svc.get("selected")
    if not selected_id:
        return None

    model_name = selected_id
    for m in svc.get("available", []):
        if m["id"] == selected_id:
            model_name = m["name"]
            break

    ui = svc.get("ui", {})
    return {"id": selected_id, "name": model_name, "ui": ui}


def _build_prompt(task_summary: str, artifact: str, evaluation_focus: str) -> str:
    """Construct an evaluation prompt from boot-C tool parameters."""
    parts = []
    if task_summary:
        parts.append(f"Task: {task_summary}")
    if artifact:
        parts.append(f"\n{artifact}")
    if evaluation_focus:
        parts.append(f"\nEvaluation focus: {evaluation_focus}")
    return "\n".join(parts)


def _switch_model(page, service: str) -> str | None:
    """Switch to the preferred model on the current page."""
    model_info = _get_selected_model(service)
    if not model_info or not model_info.get("ui"):
        return None

    ui = model_info["ui"]
    model_name = model_info["name"]

    button_selector = ui.get("model_button", "")
    option_selector = ui.get("model_option", "").replace("{model_name}", model_name)
    close_action = ui.get("close_action", "Escape")

    if not button_selector or not option_selector:
        return None

    try:
        for sel in button_selector.split(","):
            try:
                btn = page.locator(sel.strip()).first
                if btn.is_visible(timeout=3000):
                    btn.click()
                    break
            except Exception:
                continue
        else:
            return f"[model switch] Could not find model selector button for {service}"

        page.wait_for_timeout(1000)

        for sel in option_selector.split(","):
            try:
                opt = page.locator(sel.strip()).first
                if opt.is_visible(timeout=3000):
                    opt.click()
                    page.wait_for_timeout(1500)
                    return f"[model switch] Switched {service} to {model_name}"
            except Exception:
                continue

        page.keyboard.press(close_action)
        return f"[model switch] Model '{model_name}' not found in {service} dropdown — using default"

    except Exception as e:
        try:
            page.keyboard.press(close_action)
        except Exception:
            pass
        return f"[model switch] Failed for {service}: {str(e)} — using default model"


# ── Playwright Channel (primary) ──────────────────────────────────────────

def _try_playwright_session(service: str, prompt: str, config: dict) -> str | None:
    """Evaluate via Playwright with persistent sessions and auto-re-auth."""
    try:
        from playwright_session import PlaywrightSession
    except ImportError:
        # Try relative import path
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from playwright_session import PlaywrightSession

    session = PlaywrightSession(service, config)
    try:
        session.launch(headless=False)

        if not session.ensure_authenticated():
            return None  # Fall through to extension

        # Model switching
        model_status = _switch_model(session.page, service)

        response = session.send_prompt(prompt)
        session.save_session()

        if model_status:
            response = f"{model_status}\n\n{response}"
        return response
    except Exception as e:
        return f"Playwright session error ({service}): {e}"
    finally:
        session.close()


# ── Extension Channel (fallback) ──────────────────────────────────────────

def _try_extension(service: str, prompt: str, config: dict) -> str | None:
    """Try evaluating via the Chrome extension bridge (fallback)."""
    # Path 1: in-process bridge (when running inside the server)
    try:
        from extension_bridge import evaluate as ext_evaluate, is_connected
        if is_connected():
            result = ext_evaluate(service, prompt, config, timeout=300)
            return result
    except ImportError:
        pass

    # Path 2: HTTP to server (when running standalone)
    try:
        import urllib.request
        status_resp = urllib.request.urlopen(
            "http://localhost:5000/api/extension/status", timeout=2
        )
        status = json.loads(status_resp.read())
        if not status.get("connected"):
            return None

        req_data = json.dumps({
            "service": service,
            "prompt": prompt,
            "config": config,
            "timeout": 300,
        }).encode()
        req = urllib.request.Request(
            "http://localhost:5000/api/extension/evaluate",
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=310)
        result = json.loads(resp.read())
        if result.get("response"):
            return result["response"]
        return None
    except Exception:
        return None


# ── Public API ──────────────────────────────────────────────────────────────

def browser_evaluate(
    service: str,
    prompt: str = "",
    task_summary: str = "",
    artifact: str = "",
    evaluation_focus: str = "",
) -> str:
    """Evaluate via commercial AI browser session.

    Tries Playwright with persistent sessions first (auto-re-auth from
    keyring). Falls back to Chrome extension if Playwright fails.

    Accepts either:
      - Legacy: browser_evaluate(service, prompt)
      - boot-C:  browser_evaluate(service, task_summary=..., artifact=..., evaluation_focus=...)
    """
    if not prompt:
        prompt = _build_prompt(task_summary, artifact, evaluation_focus)
    if not prompt.strip():
        return "[browser_evaluate] No prompt provided."

    config = SERVICE_CONFIG.get(service.lower())
    if not config:
        return f"Unknown service: {service}. Available: {', '.join(SERVICE_CONFIG.keys())}"

    # Per-service channel preference: "playwright" (default) or "extension".
    # Set via the `prefer_channel` field in browser-services.json when a
    # service has chronic Playwright selector drift and the extension bridge
    # is the more reliable path for that provider.
    prefer = config.get("prefer_channel", "playwright")

    if prefer == "extension":
        ext_result = _try_extension(service.lower(), prompt, config)
        if ext_result is not None:
            return ext_result
        pw_result = _try_playwright_session(service.lower(), prompt, config)
        if pw_result is not None:
            return pw_result
    else:
        pw_result = _try_playwright_session(service.lower(), prompt, config)
        if pw_result is not None:
            return pw_result
        ext_result = _try_extension(service.lower(), prompt, config)
        if ext_result is not None:
            return ext_result

    return (
        f"No browser channel available for {service}. "
        "Run 'python3 config/browser-setup.py' to set up browser sessions."
    )
