"""OpenAI image API integration (WP-7.3.2a).

Fulfills the ``image_generates`` and ``image_edits`` capability slots
defined in ``~/ora/config/capabilities.json`` (slot contracts §3.1 and
§3.2 of ``Reference — Capability Invocation Contracts.md``) by calling
OpenAI's image endpoints:

  * ``image_generates`` → DALL-E 3 ``/v1/images/generations``.
  * ``image_edits``    → DALL-E 2 ``/v1/images/edits`` (DALL-E 3 does
    not support image editing as of 2026-04).

Authentication
--------------

API key is read at call time from the macOS Keychain via the
``keyring`` library, matching the pattern already used by
``orchestrator/boot.py``, ``orchestrator/tools/api_evaluate.py``, and
``server/server.py``: service ``"ora"``, username ``"openai-api-key"``.

The Visual Intelligence Implementation Plan §11.13 describes the
service-name format as ``ora-[provider]`` (i.e. ``ora-openai``), but
the actually-existing keychain entry on this machine — and every
existing callsite — uses the ``("ora", "openai-api-key")`` shape. We
follow the existing usage so no key migration is required; the spec
discrepancy is flagged in this WP's report for resolution by WP-7.3.5
(API key acquisition flow extension).

A ``$OPENAI_API_KEY`` environment variable, if set, takes precedence
over the keychain — same priority as the existing callers.

Error mapping
-------------

OpenAI error responses are translated to the slot's declared
``common_errors`` codes (per ``capabilities.json`` and §3.1 / §3.2 of
the contracts spec):

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
``image_generates`` and ``dispatch_image_edits`` against ``image_edits``
on a registry instance. The registration helper accepts an explicit
``registry`` argument so tests can drive a fresh registry; calling
``register_with_default_registry()`` with no arguments lazily loads
the standard registry from ``~/ora/config/`` via
``capability_registry.load_registry``.
"""
from __future__ import annotations

import io
import os
from typing import Any

# capability_registry is the sibling module under ~/ora/orchestrator/.
# Import is by module name (orchestrator/ is on the path when boot.py
# or the test harness loads this file).
from capability_registry import CapabilityError, CapabilityRegistry, load_registry


# ---------------------------------------------------------------------------
# Provider identifiers — these are the strings recorded in
# routing-config.json's `slots.image_generates.preferred` /
# `slots.image_edits.preferred` fields, and the same strings we hand to
# `registry.register_provider`.
# ---------------------------------------------------------------------------

PROVIDER_IMAGE_GENERATES = "openai-dalle3"
PROVIDER_IMAGE_EDITS = "openai-dalle2"

# OpenAI model IDs as currently published on the images endpoints. The
# image edits endpoint accepts dall-e-2; image generations supports
# dall-e-3 (preferred) and dall-e-2 (legacy).
MODEL_IMAGE_GENERATES = "dall-e-3"
MODEL_IMAGE_EDITS = "dall-e-2"

# Aspect-ratio → DALL-E 3 size string. DALL-E 3 only accepts three
# explicit sizes; anything else has to round to the nearest. The slot
# contract enum is {"1:1", "16:9", "9:16", "4:3", "3:4"}.
_ASPECT_TO_DALLE3_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:3": "1792x1024",   # nearest available landscape
    "3:4": "1024x1792",   # nearest available portrait
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Resolve the OpenAI API key from env or keychain.

    Returns ``None`` when no key is configured. The dispatch functions
    convert a missing key into a ``model_unavailable`` CapabilityError
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

    Mapping (per §3.1 / §3.2 common_errors):

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
# image_generates — DALL-E 3
# ---------------------------------------------------------------------------

def dispatch_image_generates(inputs: dict) -> bytes:
    """Fulfill the ``image_generates`` slot via DALL-E 3.

    Per slot contract §3.1:

      * Required: ``prompt`` (text).
      * Optional: ``style`` (text), ``aspect_ratio`` (enum).
      * Output: image bytes.

    The handler accepts the validated input dict as ``inputs``
    (``capability_registry.invoke`` validates and fills defaults
    before dispatching). Returns the raw PNG bytes of the first
    generated image.
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
    size = _ASPECT_TO_DALLE3_SIZE.get(aspect_ratio, "1024x1024")

    # The slot contract describes ``style`` as a free-form text hint
    # appended to the prompt. DALL-E 3 also has a separate ``style``
    # parameter accepting only ``"vivid"`` or ``"natural"`` — we don't
    # plumb that into the slot contract; the user controls vividness
    # through the prompt text itself.
    composed_prompt = prompt.strip()
    if style_hint and isinstance(style_hint, str) and style_hint.strip():
        composed_prompt = f"{composed_prompt}, in the style of {style_hint.strip()}"

    client = _get_client()
    try:
        response = client.images.generate(
            model=MODEL_IMAGE_GENERATES,
            prompt=composed_prompt,
            size=size,
            n=1,
            response_format="b64_json",
        )
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
# image_edits — DALL-E 2
# ---------------------------------------------------------------------------

def _coerce_to_png_bytes(value: Any, *, field_name: str, slot: str) -> bytes:
    """Coerce an input that's either bytes or a path-like to bytes.

    The slot contract types are ``image-ref`` and ``mask`` — both
    abstract handles that the canvas resolves into either a file path
    or a raw byte payload before calling the dispatcher. We accept
    either form here so we don't constrain the upstream resolver.
    """
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if hasattr(value, "read"):
        # File-like object.
        return value.read()
    if isinstance(value, str) and os.path.exists(value):
        with open(value, "rb") as f:
            return f.read()
    raise CapabilityError(
        "missing_required_input",
        f"image_edits {field_name} must be bytes, a file-like object, "
        f"or a path to an existing file (got {type(value).__name__}).",
        slot=slot,
    )


def dispatch_image_edits(inputs: dict) -> bytes:
    """Fulfill the ``image_edits`` slot via DALL-E 2.

    Per slot contract §3.2:

      * Required: ``image`` (image-ref), ``mask`` (mask), ``prompt`` (text).
      * Optional: ``strength`` (float 0.0–1.0, default 0.75).
      * Output: image bytes.

    The slot ``strength`` parameter is recorded but not transmitted —
    the DALL-E 2 edits endpoint does not accept a strength / denoising
    parameter; it inpaints the masked region wholesale based on the
    prompt. Stability and Replicate (sub-WPs b/c) honor strength.
    """
    raw_image = inputs.get("image")
    raw_mask = inputs.get("mask")
    prompt = inputs.get("prompt")

    if not raw_image:
        raise CapabilityError(
            "no_image_selected",
            "image_edits requires an 'image' (image-ref).",
            slot="image_edits",
        )
    if not raw_mask:
        raise CapabilityError(
            "no_mask_drawn",
            "image_edits requires a 'mask'. Draw a mask first.",
            slot="image_edits",
        )
    if not isinstance(prompt, str) or not prompt.strip():
        raise CapabilityError(
            "missing_required_input",
            "image_edits requires a non-empty 'prompt' string.",
            slot="image_edits",
        )

    image_bytes = _coerce_to_png_bytes(raw_image, field_name="'image'", slot="image_edits")
    mask_bytes = _coerce_to_png_bytes(raw_mask, field_name="'mask'", slot="image_edits")

    client = _get_client()
    try:
        response = client.images.edit(
            model=MODEL_IMAGE_EDITS,
            image=("image.png", io.BytesIO(image_bytes), "image/png"),
            mask=("mask.png", io.BytesIO(mask_bytes), "image/png"),
            prompt=prompt.strip(),
            n=1,
            size="1024x1024",
            response_format="b64_json",
        )
    except CapabilityError:
        raise
    except Exception as exc:
        raise _translate_openai_error(exc, slot="image_edits") from exc

    data = getattr(response, "data", None) or []
    if not data:
        raise CapabilityError(
            "model_unavailable",
            "OpenAI returned an empty image set for image_edits.",
            slot="image_edits",
        )
    first = data[0]
    b64 = getattr(first, "b64_json", None)
    if not b64:
        raise CapabilityError(
            "model_unavailable",
            "OpenAI image_edits response missing b64_json.",
            slot="image_edits",
        )
    import base64
    return base64.b64decode(b64)


# ---------------------------------------------------------------------------
# Slot fulfillment registration
# ---------------------------------------------------------------------------

def register(registry: CapabilityRegistry) -> None:
    """Bind both dispatchers to ``registry``.

    Called by ``register_with_default_registry()`` and exposed
    directly so tests can register against a fresh registry instance
    without pulling in the standard config files.
    """
    registry.register_provider(
        "image_generates",
        PROVIDER_IMAGE_GENERATES,
        dispatch_image_generates,
    )
    registry.register_provider(
        "image_edits",
        PROVIDER_IMAGE_EDITS,
        dispatch_image_edits,
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
