"""OpenAI image API integration.

Fulfills the ``image_generates`` capability slot defined in
``~/ora/config/capabilities.json`` (slot contract §3.1 of
``Reference — Capability Invocation Contracts.md``) by calling OpenAI's
image-generation endpoint with the ``gpt-image-1`` model:

  * ``image_generates`` → gpt-image-1 (provider ``openai-gpt-image-1``)
    via ``/v1/images/generations``. Per §5.8.1 of the MSI Image Style
    Specification, ``openai-gpt-image-1`` is the OpenAI-side
    ``image_generates`` binding. gpt-image-1 always returns base64,
    rejects ``response_format``, and uses its own size enum (1024×1024,
    1024×1536, 1536×1024, ``auto``).

DALL-E 2 and DALL-E 3 bindings were removed 2026-05-12 in line with
OpenAI's same-day deprecation announcement for both models. The
``image_edits`` slot — previously served here by DALL-E 2 — is still
defined in ``capabilities.json`` and fulfilled by ``local-diffusers``
(preferred) and ``replicate`` (fallback) per ``routing-config.json``.
The MSI publication never invoked ``image_edits``.

Authentication
--------------

API key is read at call time from the macOS Keychain via the
``keyring`` library, matching the pattern already used by
``orchestrator/boot.py`` and ``server/server.py``: service ``"ora"``,
username ``"openai-api-key"``.

The Visual Intelligence Implementation Plan §11.13 describes the
service-name format as ``ora-[provider]`` (i.e. ``ora-openai``), but
the actually-existing keychain entry on this machine — and every
existing callsite — uses the ``("ora", "openai-api-key")`` shape. We
follow the existing usage so no key migration is required.

A ``$OPENAI_API_KEY`` environment variable, if set, takes precedence
over the keychain — same priority as the existing callers.

Error mapping
-------------

OpenAI error responses are translated to the slot's declared
``common_errors`` codes (per ``capabilities.json`` and §3.1 of the
contracts spec):

  * Content-policy rejections → ``prompt_rejected``.
  * Rate limit + quota exhaustion → ``quota_exceeded``.
  * Authentication failures, missing keys, missing SDK,
    network-level outages, model-not-found → ``model_unavailable``.

Errors surface as ``CapabilityError`` instances with the slot-level
code so the caller (``capability_registry.invoke``) re-raises them
verbatim and the UI can present the documented fix path.

Module-load registration
------------------------

Importing this module registers ``dispatch_image_generates`` against
``image_generates`` on a registry instance. The registration helper
accepts an explicit ``registry`` argument so tests can drive a fresh
registry; calling ``register_with_default_registry()`` with no
arguments lazily loads the standard registry from ``~/ora/config/``
via ``capability_registry.load_registry``.
"""
from __future__ import annotations

import os
from typing import Any

# capability_registry is the sibling module under ~/ora/orchestrator/.
# Import is by module name (orchestrator/ is on the path when boot.py
# or the test harness loads this file).
from capability_registry import CapabilityError, CapabilityRegistry, load_registry


# ---------------------------------------------------------------------------
# Provider identifier — recorded in routing-config.json's
# `slots.image_generates.preferred` and
# `slots.image_generates_cartoon.preferred` fields, and the same string
# we hand to `registry.register_provider`.
# ---------------------------------------------------------------------------

PROVIDER_IMAGE_GENERATES = "openai-gpt-image-1"

# OpenAI model id as currently published on the images endpoint.
MODEL_IMAGE_GENERATES = "gpt-image-1"

# Aspect-ratio → gpt-image-1 size string. The model accepts square,
# portrait, landscape, or "auto". The slot contract's five-value enum
# collapses onto these three concrete sizes (landscape 16:9 and 4:3
# both round to 1536×1024; portrait likewise).
_ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "4:3": "1536x1024",   # nearest available landscape
    "3:4": "1024x1536",   # nearest available portrait
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Resolve the OpenAI API key from env or keychain.

    Returns ``None`` when no key is configured. The dispatch function
    converts a missing key into a ``model_unavailable`` CapabilityError
    so the caller surfaces the fix-path UX from §3.1's common errors.
    """
    key = os.environ.get("OPENAI_API_KEY") or ""
    if key:
        return key
    try:
        import keyring  # imported lazily so tests can stub
        return keyring.get_password("ora", "openai-api-key") or None
    except Exception:
        return None


def _get_client():
    """Return an instantiated ``openai.OpenAI`` client.

    Raises ``CapabilityError(model_unavailable)`` when either the SDK
    is missing or the key is unconfigured. Callers should let this
    bubble — ``invoke()`` re-raises CapabilityError verbatim.
    """
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise CapabilityError(
            "model_unavailable",
            "openai Python SDK not installed (pip install openai). "
            "Configure a provider via Framework — API Key Acquisition.md.",
        ) from exc

    key = _get_api_key()
    if not key:
        raise CapabilityError(
            "model_unavailable",
            "No OpenAI API key configured. Set $OPENAI_API_KEY or store "
            "via keyring service='ora', username='openai-api-key'. "
            "See Framework — API Key Acquisition.md.",
        )
    return OpenAI(api_key=key)


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

def _translate_openai_error(exc: Exception, slot: str) -> CapabilityError:
    """Translate an OpenAI SDK exception into a slot-level CapabilityError.

    Mapping (per §3.1 common_errors):

      * ``BadRequestError`` with ``code in {"content_policy_violation",
        "moderation_blocked"}`` or message containing "safety system" /
        "content policy" → ``prompt_rejected``.
      * ``RateLimitError`` → ``quota_exceeded``.
      * ``AuthenticationError`` / ``PermissionDeniedError`` /
        ``NotFoundError`` (model 404) → ``model_unavailable``.
      * ``APIConnectionError`` / ``APITimeoutError`` →
        ``model_unavailable``.
      * Anything else → ``model_unavailable`` with the original message
        preserved so debugging is still possible.
    """
    name = type(exc).__name__
    message = str(exc) or name
    msg_lower = message.lower()

    # Content policy. The OpenAI SDK reports policy violations as a
    # BadRequestError with body.error.code in a known set; we also
    # match the human-readable phrases as a defensive fallback.
    code = None
    body = getattr(exc, "body", None) or {}
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict):
            code = err.get("code")
    if code in {"content_policy_violation", "moderation_blocked"} or any(
        token in msg_lower
        for token in (
            "content policy",
            "safety system",
            "your request was rejected",
            "moderation",
        )
    ):
        return CapabilityError(
            "prompt_rejected",
            f"OpenAI content policy blocked the prompt: {message}",
            slot=slot,
        )

    if name == "RateLimitError" or "rate limit" in msg_lower or "quota" in msg_lower:
        return CapabilityError(
            "quota_exceeded",
            f"OpenAI rate limit / quota exceeded: {message}",
            slot=slot,
        )

    # Default — auth, missing model, network — all roll up to
    # model_unavailable per §3.1's common_errors taxonomy.
    return CapabilityError(
        "model_unavailable",
        f"OpenAI {name}: {message}",
        slot=slot,
    )


# ---------------------------------------------------------------------------
# image_generates — gpt-image-1
# ---------------------------------------------------------------------------

def dispatch_image_generates(inputs: dict) -> bytes:
    """Fulfill the ``image_generates`` slot via gpt-image-1.

    Per slot contract §3.1:

      * Required: ``prompt`` (text).
      * Optional: ``style`` (text), ``aspect_ratio`` (enum).
      * Output: image bytes.

    The handler accepts the validated input dict as ``inputs``
    (``capability_registry.invoke`` validates and fills defaults
    before dispatching).

    Returns the raw PNG bytes of the first generated image.
    """
    prompt = inputs.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise CapabilityError(
            "missing_required_input",
            "image_generates requires a non-empty 'prompt' string.",
            slot="image_generates",
        )

    style_hint = inputs.get("style")  # may be None
    aspect_ratio = inputs.get("aspect_ratio") or "1:1"

    # The slot contract describes ``style`` as a free-form text hint
    # appended to the prompt.
    composed_prompt = prompt.strip()
    if style_hint and isinstance(style_hint, str) and style_hint.strip():
        composed_prompt = f"{composed_prompt}, in the style of {style_hint.strip()}"

    # gpt-image-1 always returns base64 and rejects an explicit
    # ``response_format`` parameter.
    size = _ASPECT_TO_SIZE.get(aspect_ratio, "1024x1024")
    # Quality locked to medium per Image Spec §5.8.1 publisher direction
    # 2026-05-13: web-only display, no high-resolution need. Medium
    # renders the cross-hatch detail that carries the Nast register
    # signature; high (~4× cost) doesn't read differently on a column
    # at web viewing distances; low loses the engraved feel. Server-
    # side default is "auto" which usually picks medium, but locking it
    # makes billing predictable and prevents the dispatcher from drifting
    # if OpenAI changes the auto-tier default.
    request_kwargs: dict[str, Any] = {
        "model": MODEL_IMAGE_GENERATES,
        "prompt": composed_prompt,
        "size": size,
        "n": 1,
        "quality": "medium",
    }

    client = _get_client()
    try:
        response = client.images.generate(**request_kwargs)
    except CapabilityError:
        raise
    except Exception as exc:  # OpenAI SDK exceptions or bare HTTPError
        raise _translate_openai_error(exc, slot="image_generates") from exc

    # response.data is a list of Image objects with .b64_json
    data = getattr(response, "data", None) or []
    if not data:
        raise CapabilityError(
            "model_unavailable",
            "OpenAI returned an empty image set for image_generates.",
            slot="image_generates",
        )
    first = data[0]
    b64 = getattr(first, "b64_json", None)
    if not b64:
        raise CapabilityError(
            "model_unavailable",
            "OpenAI image_generates response missing b64_json.",
            slot="image_generates",
        )
    import base64
    return base64.b64decode(b64)


# ---------------------------------------------------------------------------
# Slot fulfillment registration
# ---------------------------------------------------------------------------

def register(registry: CapabilityRegistry) -> None:
    """Bind the gpt-image-1 dispatcher to both image-generation slots.

    Called by ``register_with_default_registry()`` and exposed
    directly so tests can register against a fresh registry instance
    without pulling in the standard config files.

    Per the 2026-05-12 slot-separation architecture, gpt-image-1 serves
    both ``image_generates`` (general — news photos, illustration
    filler, data-viz illustration fallback) and ``image_generates_cartoon``
    (Hector cartoons, preferred over the LoRA for image quality with
    the LoRA as the spec-compliant fallback). The same dispatcher
    handles both slots — gpt-image-1 doesn't care which slot routed it
    a prompt; the cascade behavior differs per slot routing-config.
    """
    registry.register_provider(
        "image_generates",
        PROVIDER_IMAGE_GENERATES,
        dispatch_image_generates,
    )
    registry.register_provider(
        "image_generates_cartoon",
        PROVIDER_IMAGE_GENERATES,
        dispatch_image_generates,
    )


_default_registered = False


def register_with_default_registry() -> CapabilityRegistry:
    """Lazy-register this provider against the standard registry.

    Idempotent: subsequent calls return the already-loaded registry
    without re-binding. Returns the registry so callers can invoke
    immediately (``register_with_default_registry().invoke(...)``).
    """
    global _default_registered
    registry = load_registry()
    if not _default_registered:
        register(registry)
        _default_registered = True
    return registry
