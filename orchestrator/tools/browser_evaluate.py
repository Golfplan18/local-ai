"""Send a prompt to a commercial AI via Playwright browser automation.

boot-C-agent interface:
  browser_evaluate(service, task_summary, artifact, evaluation_focus="")

Legacy interface (still accepted):
  browser_evaluate(service, prompt)
"""

import os
import json

SESSION_DIR = os.path.expanduser("~/local-ai/config/browser-sessions/")
SERVICES_JSON = os.path.expanduser("~/local-ai/config/browser-services.json")

# Built-in service configs (always available)
SERVICE_CONFIG = {
    "claude": {
        "url": "https://claude.ai/new",
        "session_file": "claude.json",
        "input_selector": '[data-testid="composer-input"], div[contenteditable="true"]',
        "response_selector": '.font-claude-message, [data-is-streaming="false"]',
    },
    "chatgpt": {
        "url": "https://chat.openai.com/",
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
            "Run the Browser Evaluation Setup Framework to log in and save your session."
        )

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return "Playwright not installed. Run: pip install playwright && playwright install chromium"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=session_path)
            page = context.new_page()
            page.goto(config["url"], timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

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
            return response_text if response_text else "No response captured."
    except PWTimeout:
        return (
            f"Timeout waiting for {service} response. "
            "The session may have expired — re-run the Browser Evaluation Setup Framework."
        )
    except Exception as e:
        return f"Browser evaluation error: {str(e)}"
