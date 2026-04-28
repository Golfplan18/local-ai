"""G5 overflow: evaluate via commercial AI API.

boot-C-agent interface:
  api_evaluate(task_summary, artifact, evaluation_focus="")

Routes to the active gear5_api_primary endpoint in endpoints.json.
Falls back to gear5_api_overflow if primary fails.
"""

import os
import json


ENDPOINTS_JSON = os.path.expanduser("~/ora/config/endpoints.json")


def _load_endpoints() -> dict:
    try:
        with open(ENDPOINTS_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


def _build_prompt(task_summary: str, artifact: str, evaluation_focus: str) -> str:
    parts = []
    if task_summary:
        parts.append(f"Task: {task_summary}")
    if artifact:
        parts.append(f"\n{artifact}")
    if evaluation_focus:
        parts.append(f"\nEvaluation focus: {evaluation_focus}")
    return "\n".join(parts)


def _call_gemini(prompt: str, model: str) -> str:
    try:
        import keyring
        key = os.environ.get("GEMINI_API_KEY", "") or keyring.get_password("ora", "gemini-api-key") or ""
    except Exception:
        key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return "[api_evaluate] No Gemini API key found. Store via: keyring set ora gemini-api-key"
    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model=model or "models/gemini-2.5-flash", contents=prompt)
        return response.text
    except Exception as e:
        return f"[api_evaluate/gemini] {e}"


def _call_openai(prompt: str, model: str) -> str:
    try:
        import keyring
        key = os.environ.get("OPENAI_API_KEY", "") or keyring.get_password("ora", "openai-api-key") or ""
    except Exception:
        key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return "[api_evaluate] No OpenAI API key found."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model or "gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[api_evaluate/openai] {e}"


def _call_claude(prompt: str, model: str) -> str:
    try:
        import keyring
        key = os.environ.get("ANTHROPIC_API_KEY", "") or keyring.get_password("ora", "anthropic-api-key") or ""
    except Exception:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return "[api_evaluate] No Anthropic API key found."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model or "claude-opus-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        return f"[api_evaluate/claude] {e}"


def _call_endpoint(endpoint: dict, prompt: str) -> str:
    service = endpoint.get("service", "")
    model = endpoint.get("model", "")
    if service == "gemini":
        return _call_gemini(prompt, model)
    if service == "openai":
        return _call_openai(prompt, model)
    if service == "claude":
        return _call_claude(prompt, model)
    return f"[api_evaluate] Unsupported service: {service}"


def api_evaluate(
    task_summary: str,
    artifact: str,
    evaluation_focus: str = "",
) -> str:
    """Evaluate via commercial AI API (G5 overflow).

    Tries gear5_api_primary first, then gear5_api_overflow.
    """
    prompt = _build_prompt(task_summary, artifact, evaluation_focus)
    if not prompt.strip():
        return "[api_evaluate] No content to evaluate."

    config = _load_endpoints()
    routing = config.get("routing", {})
    endpoints_by_name = {e["name"]: e for e in config.get("endpoints", [])}

    primary_name = routing.get("gear5_api_primary")
    overflow_name = routing.get("gear5_api_overflow")

    errors = []

    for ep_name in [primary_name, overflow_name]:
        if not ep_name:
            continue
        ep = endpoints_by_name.get(ep_name)
        if not ep:
            continue
        if ep.get("status") != "active":
            errors.append(f"{ep_name}: inactive")
            continue
        result = _call_endpoint(ep, prompt)
        if not result.startswith("[api_evaluate"):
            return result
        errors.append(f"{ep_name}: {result}")

    return (
        "[api_evaluate] All G5 API endpoints failed or unavailable. "
        f"Errors: {'; '.join(errors)}. Falling back to G4 local-only."
    )
