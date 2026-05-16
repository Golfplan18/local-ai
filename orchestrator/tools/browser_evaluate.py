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
import sys
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
except Exception as _svc_load_err:
    # JSON parse failure or unexpected disk error. Without a log the
    # process silently falls back to the small built-in three-service
    # config below — every Playwright dispatch then runs against a
    # truncated service catalogue with no signal that the on-disk
    # config exists but is unreadable.
    print(
        f"[browser_evaluate] Failed to load {SERVICES_JSON}: "
        f"{_svc_load_err}. Using built-in fallback config.",
        file=sys.stderr, flush=True,
    )

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
    except Exception as exc:
        # Empty prefs means every browser dispatch falls back to the
        # service's default model with no warning. Log so the
        # mis-configuration is visible.
        print(
            f"[browser_evaluate] Failed to load {MODELS_JSON}: {exc}. "
            f"Falling back to each service's default model.",
            file=sys.stderr, flush=True,
        )
    return {}


def _get_selected_model(service: str) -> dict | None:
    """Get the selected model info for a service.

    Resolution order:
      1. If ``selected_family`` is set on the service, pick the first model in
         ``available`` whose ``name`` contains the family string (case-insensitive).
         Use that model; this lets the picker auto-track version bumps within a
         family like "Claude Opus" without re-pinning the exact id.
      2. Otherwise fall back to the exact pinned ``selected`` id.
    """
    prefs = _load_model_prefs()
    svc = prefs.get(service)
    if not svc:
        return None

    ui = svc.get("ui", {})
    available = svc.get("available", [])

    family = (svc.get("selected_family") or "").strip()
    if family:
        needle = family.lower()
        for m in available:
            if needle in m.get("name", "").lower():
                return {"id": m["id"], "name": m["name"], "ui": ui}

    selected_id = svc.get("selected")
    if not selected_id:
        return None

    model_name = selected_id
    for m in available:
        if m["id"] == selected_id:
            model_name = m["name"]
            break

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


# ── Playwright Channel (primary) ──────────────────────────────────────────

def _try_playwright_session(service: str, prompt: str, config: dict) -> str | None:
    """Evaluate via Playwright through the per-service worker thread.

    The worker owns one long-lived persistent context per service. Each
    submit() opens a fresh page (tab), runs the dispatch, and closes the
    page — but the underlying Chrome instance stays alive across calls.
    This avoids ``user_data_dir`` lock contention that hits parallel
    ``launch_persistent_context`` calls against the same profile.

    Auth/MFA is not handled here. If the worker reports "not logged in",
    we fall through to the extension channel (and the user can run the
    one-shot ``PlaywrightSession`` flow to bootstrap auth).
    """
    try:
        from playwright_session import dispatch_via_worker
    except ImportError:
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from playwright_session import dispatch_via_worker

    model_info = _get_selected_model(service)

    try:
        return dispatch_via_worker(
            service,
            prompt,
            config,
            model_info=model_info,
            headless=False,
            timeout=420,  # outlasts the worker's internal 300s wait_for_response
        )
    except Exception as e:
        msg = str(e)
        if "not logged in" in msg.lower():
            return None  # fall through to extension; auth bootstrap needed
        return f"Playwright session error ({service}): {msg}"


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
