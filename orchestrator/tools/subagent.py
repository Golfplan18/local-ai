"""Subagent spawner — isolated model calls with fresh context.
Subagents cannot spawn additional subagents (recursion guard)."""

from __future__ import annotations

import json
import os
import sys
import time

WORKSPACE = os.path.expanduser("~/local-ai/")
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))


def spawn_subagent(system_prompt: str, user_prompt: str,
                   model_slot: str = None, timeout: int = 120) -> str:
    """Spawn an isolated model call with a fresh context.

    Args:
        system_prompt: System prompt for the subagent.
        user_prompt: The task/question for the subagent.
        model_slot: Model slot to use (small/breadth/depth). Defaults to smallest.
        timeout: Max seconds to wait for response.

    Returns:
        The model's response text, or an error message.
    """
    try:
        from boot import load_endpoints, get_slot_endpoint, get_active_endpoint, call_model
    except ImportError as e:
        return f"[subagent] Import error: {e}"

    config = load_endpoints()

    # Select endpoint: specified slot, or smallest available
    endpoint = None
    if model_slot:
        endpoint = get_slot_endpoint(config, model_slot)
    if endpoint is None:
        # Try small, then breadth, then default
        for slot in ("small", "breadth", "depth"):
            endpoint = get_slot_endpoint(config, slot)
            if endpoint:
                break
    if endpoint is None:
        endpoint = get_active_endpoint(config)
    if endpoint is None:
        return "[subagent] No model endpoint available."

    messages = [
        {"role": "system", "content": system_prompt + "\n\n[NOTE: You are running as a subagent. The spawn_subagent tool is not available to you. Complete your task within this context.]"},
        {"role": "user", "content": user_prompt},
    ]

    try:
        import threading
        result = [None]
        error = [None]

        def _call():
            try:
                result[0] = call_model(messages, endpoint)
            except Exception as e:
                error[0] = str(e)

        thread = threading.Thread(target=_call)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return f"[subagent] Timed out after {timeout} seconds. The task may be too complex for a single subagent call."

        if error[0]:
            return f"[subagent] Model error: {error[0]}"

        return result[0] or "[subagent] Empty response from model."

    except Exception as e:
        return f"[subagent] {e}"
