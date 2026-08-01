"""model_dispatch.py — public-facing model invocation API for projects.

Project tools that need to invoke a model with a system + user prompt
call ``invoke_chat`` rather than reaching into ``boot.call_model``
directly. This keeps Ora's internal model invocation an implementation
detail and gives project tools a stable, well-documented seam.

The function uses Ora's existing routing (endpoint slots from
``~/ora/config/routing-config.json``), so the publisher's model preferences
control which model authors articles, runs analysis, etc. Projects
declare their preferred slot in the call (default: ``breadth``, which
is typically a high-context generative model like Hermes-4-70B).

Per Reference — Ora Project Plugin Convention.md §5, this module is
project-agnostic. Nothing here references any specific project. MSI's
article_generator.py is the reference consumer.
"""
from __future__ import annotations

import json
from typing import Optional


class ModelDispatchError(Exception):
    """Raised when invoke_chat cannot complete a model call.

    The .reason attribute carries a stable code:
      - "no_endpoints_config" — routing-config.json could not be loaded
      - "no_slot_endpoint"    — no endpoint registered against the slot
      - "model_error"         — the model call returned an error string
      - "import_error"        — Ora's boot module isn't importable
    """

    def __init__(self, reason: str, message: str, *, slot: Optional[str] = None,
                 detail: Optional[str] = None):
        super().__init__(message)
        self.reason = reason
        self.slot = slot
        self.detail = detail


def invoke_chat(
    system_prompt: str,
    user_prompt: str,
    *,
    slot: str = "breadth",
    extra_messages: Optional[list[dict]] = None,
    context: str = "interactive",
    config_name: Optional[str] = None,
) -> str:
    """Invoke a model via Ora's existing routing infrastructure.

    Loads the endpoints config, resolves the requested slot to a concrete
    endpoint (per the publisher's routing preferences), builds a chat
    messages list (system + user, plus any ``extra_messages`` appended
    between them), and calls Ora's ``boot.call_model``. Returns the
    model's text response.

    Args:
      system_prompt: the model's system prompt (authoring instructions, etc.).
      user_prompt:   the model's user prompt (the task input).
      slot:          which endpoint slot to use ("breadth", "depth",
                     "sidebar", "consolidator", "evaluator",
                     "step1_cleanup", "classification"). Default
                     "breadth" — high-context generative work like
                     article authoring.
      extra_messages: optional list of additional messages to insert
                     between the system and user messages (e.g.,
                     few-shot examples).
      config_name:   exact resolved Model Profile/configuration. When supplied,
                     endpoint resolution fails closed rather than falling back
                     to the globally active profile.

    Returns:
      The model's text response (stripped of any leading/trailing
      whitespace).

    Raises:
      ModelDispatchError with .reason set to a stable code (see class
      docstring for the enumeration). Callers should catch this and
      surface it; do not let it propagate to a chat UI as an unhandled
      exception.
    """
    try:
        from orchestrator.boot import call_model, load_routing_config, get_slot_endpoint
    except ImportError as e:  # pragma: no cover — paranoid guard
        raise ModelDispatchError(
            "import_error",
            f"Cannot import Ora's model dispatch (boot.py): {e}. "
            f"Verify ORA_HOME is on sys.path.",
        ) from e

    try:
        config = load_routing_config()
    except Exception as e:
        raise ModelDispatchError(
            "no_endpoints_config",
            f"Could not load endpoints config: {e}.",
        ) from e

    endpoint = get_slot_endpoint(
        config, slot, context=context, config_name=config_name,
    )
    if not endpoint:
        raise ModelDispatchError(
            "no_slot_endpoint",
            f"No endpoint is registered for slot {slot!r} (context={context!r}) "
            f"in ~/ora/config/routing-config.json. Configure one or pass a "
            f"different slot. Common slots: breadth, depth, sidebar.",
            slot=slot,
        )

    messages = [{"role": "system", "content": system_prompt}]
    if extra_messages:
        messages.extend(extra_messages)
    messages.append({"role": "user", "content": user_prompt})

    response = call_model(messages, endpoint)
    if not isinstance(response, str):
        raise ModelDispatchError(
            "model_error",
            f"Model returned non-string response: {type(response).__name__}",
            slot=slot,
        )

    # Ora's call_model returns "[Error ...]" strings on failure; treat
    # those as dispatch errors so callers don't accidentally save them
    # as article output.
    stripped = response.strip()
    if stripped.startswith("[Error") or stripped.startswith("[MLX model not found"):
        raise ModelDispatchError(
            "model_error",
            f"Model call failed: {stripped[:300]}",
            slot=slot,
            detail=stripped,
        )

    return stripped


def get_slot_info(
    slot: str = "breadth",
    *,
    context: str = "interactive",
    config_name: Optional[str] = None,
) -> dict:
    """Inspect what endpoint the given slot would resolve to.

    Returns a dict with at least ``name``, ``model_name``, ``type``, and
    ``service`` keys. Returns an empty dict if no endpoint is registered.
    Useful for project tools that want to log which model is about to
    author an article before they spend the call.

    ``context`` matches :func:`invoke_chat`'s parameter — pass
    ``autonomous`` to mirror an unattended-pipeline resolution.
    """
    try:
        from orchestrator.boot import load_routing_config, get_slot_endpoint
    except ImportError:
        return {}
    try:
        config = load_routing_config()
    except Exception:
        return {}
    endpoint = get_slot_endpoint(
        config, slot, context=context, config_name=config_name,
    ) or {}
    return {
        k: endpoint.get(k)
        for k in ("name", "model_name", "model", "type", "service", "role")
        if endpoint.get(k) is not None
    }


__all__ = [
    "ModelDispatchError",
    "invoke_chat",
    "get_slot_info",
]
