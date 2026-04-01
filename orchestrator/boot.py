#!/usr/bin/env python3
"""
Local AI Orchestrator — boot.py
Implements the detect→execute→inject agentic loop.
All behavioral decisions live in boot.md. This file is mechanical plumbing.
"""

import os
import sys
import json
import re

# Paths
WORKSPACE = os.path.expanduser("~/local-ai/")
BOOT_MD = os.path.join(WORKSPACE, "boot/boot.md")
ENDPOINTS_JSON = os.path.join(WORKSPACE, "config/endpoints.json")
TOOLS_DIR = os.path.join(WORKSPACE, "orchestrator/tools/")

sys.path.insert(0, TOOLS_DIR)

# Tool imports with graceful fallback
TOOLS_AVAILABLE = True
try:
    from web_search import web_search
    from file_ops import file_read, file_write
    from knowledge_search import knowledge_search
    from browser_open import browser_open
    from credential_store import credential_store
    from browser_evaluate import browser_evaluate
    from api_evaluate import api_evaluate
except ImportError as e:
    print(f"[WARNING] Tool import failed: {e}")
    TOOLS_AVAILABLE = False


def _extract_final_response(raw: str) -> str:
    """Extract the final channel content from gpt-oss style responses.
    Falls back to full text if no channel markers are present."""
    if "<|channel|>final<|message|>" in raw:
        part = raw.split("<|channel|>final<|message|>", 1)[1]
        # Strip trailing special tokens
        for tok in ["<|end|>", "<|return|>", "<|endoftext|>"]:
            part = part.split(tok)[0]
        return part.strip()
    # Strip any channel/message tokens and return remaining text
    import re
    cleaned = re.sub(r'<\|[^|]+\|>', '', raw)
    return cleaned.strip() or raw.strip()


def load_boot_md() -> str:
    try:
        with open(BOOT_MD, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a helpful AI assistant. You have no special tools in this session."


def load_endpoints() -> dict:
    try:
        with open(ENDPOINTS_JSON, "r") as f:
            return json.load(f)
    except Exception:
        return {"endpoints": [], "default_endpoint": None}


def get_active_endpoint(config: dict) -> dict | None:
    """Legacy single-endpoint selector. Returns the breadth slot endpoint if slot_assignments
    are configured, otherwise falls back to default_endpoint."""
    slot = config.get("slot_assignments", {}).get("breadth")
    endpoints = config.get("endpoints", [])
    if slot:
        for e in endpoints:
            if e.get("name") == slot:
                return e
    default = config.get("default_endpoint")
    active = [e for e in endpoints if e.get("status") == "active"]
    if not active:
        return None
    if default:
        for e in active:
            if e.get("name") == default:
                return e
    return active[0]


def get_slot_endpoint(config: dict, slot: str) -> dict | None:
    """Return the endpoint assigned to a named slot (sidebar, breadth, depth, evaluator, etc.)."""
    slot_assignments = config.get("slot_assignments", {})
    model_id = slot_assignments.get(slot)
    if not model_id:
        return get_active_endpoint(config)
    endpoints = config.get("endpoints", [])
    for e in endpoints:
        if e.get("name") == model_id:
            return e
    return get_active_endpoint(config)


def call_model(messages: list, endpoint: dict) -> str:
    """Route to appropriate endpoint type."""
    etype = endpoint.get("type", "")
    
    if etype == "api":
        return call_api_endpoint(messages, endpoint)
    elif etype == "local":
        return call_local_endpoint(messages, endpoint)
    elif etype == "browser":
        return call_browser_endpoint(messages, endpoint)
    else:
        return f"[Error] Unknown endpoint type: {etype}"


def call_api_endpoint(messages: list, endpoint: dict) -> str:
    service = endpoint.get("service", "")
    model = endpoint.get("model", "")
    
    if service == "claude":
        try:
            import anthropic
            key = endpoint.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("local-ai", "anthropic-api-key") or ""
            client = anthropic.Anthropic(api_key=key)
            # Separate system from messages
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            conv = [m for m in messages if m["role"] != "system"]
            resp = client.messages.create(
                model=model or "claude-opus-4-6",
                max_tokens=4096,
                system=system_msg,
                messages=conv
            )
            return resp.content[0].text
        except Exception as e:
            return f"[Error calling Claude API: {e}]"
    
    elif service == "openai":
        try:
            from openai import OpenAI
            key = endpoint.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("local-ai", "openai-api-key") or ""
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model=model or "gpt-4o",
                messages=messages,
                max_tokens=4096
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[Error calling OpenAI API: {e}]"
    
    return f"[Error] Unsupported API service: {service}"


def call_local_endpoint(messages: list, endpoint: dict) -> str:
    url = endpoint.get("url", "http://localhost:11434")
    engine = endpoint.get("engine", "ollama")
    model = endpoint.get("model", "")
    
    if engine == "ollama":
        try:
            import urllib.request
            payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
            req = urllib.request.Request(
                f"{url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "[No response]")
        except Exception as e:
            return f"[Error calling local model: {e}]"
    
    elif engine == "mlx":
        try:
            from mlx_lm import load, generate as mlx_generate
            model_obj, tokenizer = load(model)
            # Use chat template if available, otherwise build manually
            if hasattr(tokenizer, "apply_chat_template"):
                conv = [m for m in messages if m["role"] != "system"]
                system = next((m["content"] for m in messages if m["role"] == "system"), None)
                if system:
                    conv = [{"role": "system", "content": system}] + conv
                prompt = tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
            else:
                parts = []
                for m in messages:
                    if m["role"] == "system":    parts.append(f"<|system|>\n{m['content']}")
                    elif m["role"] == "user":    parts.append(f"<|user|>\n{m['content']}")
                    elif m["role"] == "assistant": parts.append(f"<|assistant|>\n{m['content']}")
                parts.append("<|assistant|>")
                prompt = "\n".join(parts)
            raw = mlx_generate(model_obj, tokenizer, prompt=prompt, max_tokens=2048, verbose=False)
            return _extract_final_response(raw)
        except Exception as e:
            return f"[Error calling MLX model: {e}]"
    
    return f"[Error] Unsupported engine: {engine}"


def call_browser_endpoint(messages: list, endpoint: dict) -> str:
    # For browser endpoints, take the last user message
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    service = endpoint.get("service", "claude")
    if TOOLS_AVAILABLE:
        return browser_evaluate(service, last_user)
    return "[Error] browser_evaluate tool not available"


def parse_tool_calls(text: str) -> list[dict]:
    """Extract all <tool_call> blocks from model output."""
    pattern = r'<tool_call>\s*<n>(.*?)</n>\s*<parameters>(.*?)</parameters>\s*</tool_call>'
    matches = re.findall(pattern, text, re.DOTALL)
    calls = []
    for name, params_str in matches:
        try:
            params = json.loads(params_str.strip())
        except json.JSONDecodeError:
            params = {"raw": params_str.strip()}
        calls.append({"name": name.strip(), "parameters": params})
    return calls


def _code_execute(code: str, timeout: int = 30) -> str:
    """Sandboxed Python execution (no network)."""
    if not code.strip():
        return "[code_execute] No code provided."
    import subprocess, sys
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "no_proxy": "*", "http_proxy": "", "https_proxy": ""},
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err:
            return f"{out}\n[stderr] {err}".strip()
        return out or "[code_execute] (no output)"
    except subprocess.TimeoutExpired:
        return f"[code_execute] Timeout after {timeout}s"
    except Exception as e:
        return f"[code_execute] {e}"


def _continuity_save(session_summary: str) -> str:
    """Write a session continuity file to ~/Documents/conversations/."""
    if not session_summary.strip():
        return "[continuity_save] No summary provided."
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.expanduser(f"~/Documents/conversations/continuity_{ts}.md")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(f"# Session Continuity — {ts}\n\n{session_summary}\n")
        return f"[continuity_save] Saved to {path}"
    except Exception as e:
        return f"[continuity_save] {e}"


def _queue_read() -> str:
    """Read the next task from config/task-queue.md."""
    queue_path = os.path.join(WORKSPACE, "config/task-queue.md")
    if not os.path.exists(queue_path):
        return "[queue_read] No task queue found at config/task-queue.md"
    try:
        with open(queue_path) as f:
            content = f.read()
        # Return the first non-empty, non-header line that looks like a task
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- [ ]"):
                return line
        return "[queue_read] No pending tasks in queue."
    except Exception as e:
        return f"[queue_read] {e}"


def execute_tool(name: str, params: dict) -> str:
    """Dispatch tool call to implementation."""
    if not TOOLS_AVAILABLE:
        return f"[Tools unavailable — import failed at startup]"
    
    try:
        if name == "web_search":
            return web_search(params.get("query", ""), params.get("max_results", 5))
        elif name == "file_read":
            return file_read(params.get("path", ""))
        elif name == "file_write":
            return file_write(params.get("path", ""), params.get("content", ""))
        elif name == "knowledge_search":
            return knowledge_search(
                params.get("query", ""),
                params.get("collection", "knowledge"),
                params.get("n_results", 5)
            )
        elif name == "browser_open":
            return browser_open(params.get("url", ""))
        elif name == "credential_store":
            return credential_store(
                params.get("action", "retrieve"),
                params.get("service", ""),
                params.get("username", ""),
                params.get("value")
            )
        elif name == "browser_evaluate":
            return browser_evaluate(
                params.get("service", "claude"),
                prompt=params.get("prompt", ""),
                task_summary=params.get("task_summary", ""),
                artifact=params.get("artifact", ""),
                evaluation_focus=params.get("evaluation_focus", ""),
            )
        elif name == "api_evaluate":
            return api_evaluate(
                task_summary=params.get("task_summary", ""),
                artifact=params.get("artifact", ""),
                evaluation_focus=params.get("evaluation_focus", ""),
            )
        elif name == "code_execute":
            return _code_execute(params.get("code", ""), params.get("timeout", 30))
        elif name == "continuity_save":
            return _continuity_save(params.get("session_summary", ""))
        elif name == "queue_read":
            return _queue_read()
        else:
            return f"[Unknown tool: {name}]"
    except Exception as e:
        return f"[Tool error — {name}: {e}]"


def strip_tool_calls(text: str) -> str:
    """Remove tool call XML from text for display."""
    pattern = r'<tool_call>.*?</tool_call>'
    return re.sub(pattern, '', text, flags=re.DOTALL).strip()


def run_agentic_loop(user_input: str, history: list = None) -> str:
    """Main agentic loop: receive → call model → detect tools → execute → inject → repeat."""
    config = load_endpoints()
    endpoint = get_active_endpoint(config)
    
    messages = history or []
    
    # Inject system prompt from boot.md if not already present
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": load_boot_md()})
    
    messages.append({"role": "user", "content": user_input})
    
    MAX_ITERATIONS = 10
    for iteration in range(MAX_ITERATIONS):
        if endpoint is None:
            return ("[No AI endpoints configured. Add a commercial AI connection or "
                    "install a local model.\n"
                    "To add a connection, run the Browser Evaluation Setup Framework.")
        
        response = call_model(messages, endpoint)
        tool_calls = parse_tool_calls(response)
        
        if not tool_calls:
            # No tool calls — deliver final response
            return strip_tool_calls(response)
        
        # Execute all tool calls in this response
        tool_results = []
        for tc in tool_calls:
            result = execute_tool(tc["name"], tc["parameters"])
            tool_results.append(f"[Tool: {tc['name']}]\n{result}")
        
        # Inject: add model response + tool results to history, then continue
        messages.append({"role": "assistant", "content": response})
        tool_result_text = "\n\n".join(tool_results)
        messages.append({"role": "user", "content": f"[Tool results]\n{tool_result_text}"})
    
    # Max iterations reached
    return strip_tool_calls(response)


def main():
    """Interactive terminal interface."""
    print("Local AI — Terminal Interface")
    print("Type your message and press Enter. Ctrl+C to exit.")
    print()
    
    config = load_endpoints()
    endpoint = get_active_endpoint(config)
    if endpoint:
        print(f"Active endpoint: {endpoint.get('name', 'unknown')}")
    else:
        print("WARNING: No active endpoints configured.")
    print()
    
    history = []
    
    # Add system prompt once
    history.append({"role": "system", "content": load_boot_md()})
    
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye.")
                break
            
            response = run_agentic_loop(user_input, history)
            print(f"\nAI: {response}\n")
            
            # Update history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": response})
        
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"[Error: {e}]")


if __name__ == "__main__":
    main()
