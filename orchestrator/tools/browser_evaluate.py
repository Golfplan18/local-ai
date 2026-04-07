"""Send a prompt to a commercial AI via Playwright browser automation.

boot-C-agent interface:
  browser_evaluate(service, task_summary, artifact, evaluation_focus="")

Legacy interface (still accepted):
  browser_evaluate(service, prompt)

Model selection:
  For claude, chatgpt, and gemini, the selected model from
  config/browser-models.json is applied before sending the prompt.
  Run 'python3 config/update-models.py' to change model preferences.
"""

import os
import json

SESSION_DIR = os.path.expanduser("~/local-ai/config/browser-sessions/")
SERVICES_JSON = os.path.expanduser("~/local-ai/config/browser-services.json")
MODELS_JSON = os.path.expanduser("~/local-ai/config/browser-models.json")

# Built-in service configs (always available)
SERVICE_CONFIG = {
    "claude": {
        "url": "https://claude.ai/new",
        "session_file": "claude.json",
        "input_selector": '[data-testid="composer-input"], div[contenteditable="true"]',
        "response_selector": '.font-claude-message, [data-is-streaming="false"]',
    },
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "session_file": "chatgpt.json",
        "input_selector": "#prompt-textarea, textarea",
        "response_selector": ".markdown, .prose",
    },
    "gemini": {
        "url": "https://gemini.google.com/app",
        "session_file": "gemini.json",
        "input_selector": "rich-textarea, textarea",
        "response_selector": ".response-content, model-response",
    },
}

# Merge any additional services from capture-sessions
try:
    if os.path.exists(SERVICES_JSON):
        with open(SERVICES_JSON) as _f:
            _extra = json.load(_f)
        for _key, _cfg in _extra.items():
            if _key not in SERVICE_CONFIG:
                SERVICE_CONFIG[_key] = _cfg
except Exception:
    pass


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
    """Get the selected model info for a service.

    Returns dict with keys: id, name, ui (selectors) or None if no
    model preference is configured for this service.
    """
    prefs = _load_model_prefs()
    svc = prefs.get(service)
    if not svc:
        return None

    selected_id = svc.get("selected")
    if not selected_id:
        return None

    # Find the display name
    model_name = selected_id
    for m in svc.get("available", []):
        if m["id"] == selected_id:
            model_name = m["name"]
            break

    ui = svc.get("ui", {})
    return {"id": selected_id, "name": model_name, "ui": ui}


def _switch_model(page, service: str) -> str | None:
    """Switch to the preferred model on the current page.

    Uses the UI selectors from browser-models.json to click the model
    dropdown and select the preferred model. Returns a status message
    or None if no switch was needed/possible.
    """
    model_info = _get_selected_model(service)
    if not model_info or not model_info.get("ui"):
        return None

    ui = model_info["ui"]
    model_name = model_info["name"]

    # Resolve selector templates — replace {model_name} with actual name
    button_selector = ui.get("model_button", "")
    option_selector = ui.get("model_option", "").replace("{model_name}", model_name)
    close_action = ui.get("close_action", "Escape")

    if not button_selector or not option_selector:
        return None

    try:
        # Click the model selector button (try each selector in the comma list)
        button_selectors = [s.strip() for s in button_selector.split(",")]
        clicked = False
        for sel in button_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            return f"[model switch] Could not find model selector button for {service}"

        # Brief wait for dropdown to appear
        page.wait_for_timeout(1000)

        # Check if the desired model is already selected (look for active/selected state)
        # Try to click the model option
        option_selectors = [s.strip() for s in option_selector.split(",")]
        selected = False
        for sel in option_selectors:
            try:
                opt = page.locator(sel).first
                if opt.is_visible(timeout=3000):
                    opt.click()
                    selected = True
                    break
            except Exception:
                continue

        if not selected:
            # Close the dropdown and proceed with whatever model is active
            page.keyboard.press(close_action)
            return f"[model switch] Model '{model_name}' not found in {service} dropdown — using default"

        # Wait for model switch to take effect
        page.wait_for_timeout(1500)
        return f"[model switch] Switched {service} to {model_name}"

    except Exception as e:
        # If model switching fails, close any open dropdown and continue
        try:
            page.keyboard.press(close_action)
        except Exception:
            pass
        return f"[model switch] Failed for {service}: {str(e)} — using default model"


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


def browser_evaluate(
    service: str,
    prompt: str = "",
    task_summary: str = "",
    artifact: str = "",
    evaluation_focus: str = "",
) -> str:
    """Evaluate via commercial AI browser session.

    Accepts either:
      - Legacy: browser_evaluate(service, prompt)
      - boot-C:  browser_evaluate(service, task_summary=..., artifact=..., evaluation_focus=...)

    For claude, chatgpt, and gemini: automatically switches to the
    preferred model from config/browser-models.json before sending.
    """
    # Resolve final prompt
    if not prompt:
        prompt = _build_prompt(task_summary, artifact, evaluation_focus)
    if not prompt.strip():
        return "[browser_evaluate] No prompt provided."

    config = SERVICE_CONFIG.get(service.lower())
    if not config:
        return f"Unknown service: {service}. Available: {', '.join(SERVICE_CONFIG.keys())}"

    session_path = os.path.join(SESSION_DIR, config["session_file"])
    if not os.path.exists(session_path):
        return (
            f"No saved session for {service}. "
            "Run 'python3 config/capture-sessions.py' to log in and save your session."
        )

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return "Playwright not installed. Run: pip install playwright && playwright install chromium"

    model_status = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=session_path)
            page = context.new_page()
            page.goto(config["url"], timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Switch to preferred model (claude, chatgpt, gemini only)
            svc_key = service.lower()
            if svc_key in ("claude", "chatgpt", "gemini"):
                model_status = _switch_model(page, svc_key)

            # Type prompt
            input_el = page.locator(config["input_selector"]).first
            input_el.click()
            input_el.fill(prompt)
            page.keyboard.press("Enter")

            # Wait for response
            page.wait_for_timeout(3000)
            response_el = page.locator(config["response_selector"]).last
            response_el.wait_for(state="visible", timeout=60000)
            page.wait_for_timeout(2000)
            response_text = response_el.inner_text()

            browser.close()

            result = response_text if response_text else "No response captured."
            if model_status:
                result = f"{model_status}\n\n{result}"
            return result
    except PWTimeout:
        return (
            f"Timeout waiting for {service} response. "
            "The session may have expired — run 'python3 config/capture-sessions.py' to refresh."
        )
    except Exception as e:
        return f"Browser evaluation error: {str(e)}"
