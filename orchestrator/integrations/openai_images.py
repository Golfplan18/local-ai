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
``orchestrator/boot.py`` and ``server/app.py``: service ``"ora"``,
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
arguments loads a standard registry from ``~/ora/config/`` via
``capability_registry.load_registry`` and registers against it. That
loader builds a new registry per call, so every call registers.
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

PROVIDER_IMAGE_GENERATES = "openai-image-direct"

# Historical alias retained for any callers that still reference the
# pre-2026-05-22 provider id (`openai-gpt-image-1`). The dispatcher no
# longer assumes a model id — see dispatch_image_generates below.
PROVIDER_IMAGE_GENERATES_LEGACY = "openai-gpt-image-1"

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
            "Configure a provider via Framework — API Key Setup.md.",
        ) from exc

    key = _get_api_key()
    if not key:
        raise CapabilityError(
            "model_unavailable",
            "No OpenAI API key configured. Set $OPENAI_API_KEY or store "
            "via keyring service='ora', username='openai-api-key'. "
            "See Framework — API Key Setup.md.",
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

    # Model id is required input — provided by the caller (typically the
    # capability_registry from the slot's chain entry). No hardcoded
    # fallback: a missing model id is a configuration bug, not something
    # to paper over with a silent default. Publisher direction 2026-05-22.
    model_id = inputs.get("model") or inputs.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise CapabilityError(
            "missing_required_input",
            "image_generates requires a non-empty 'model' input. "
            "The slot chain entry must encode the OpenAI model id; "
            "no default is assumed.",
            slot="image_generates",
        )
    model_id = model_id.strip()

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
    # Per OpenAI docs (2026-05-22 publisher research), transparent PNG
    # output requires THREE things in concert:
    #   1. background="transparent"
    #   2. output_format="png" (or "webp"); JPEG is incompatible
    #   3. a model that supports transparent backgrounds — gpt-image-1.5
    #      does; gpt-image-2 and gpt-image-2-2026-04-21 do NOT
    # All three are non-negotiable. If any is missing, OpenAI returns
    # opaque RGB and no amount of prompt engineering can recover the
    # alpha channel.
    request_kwargs: dict[str, Any] = {
        "model": model_id,
        "prompt": composed_prompt,
        "size": size,
        "n": 1,
        "quality": "medium",
        "background": "transparent",
        "output_format": "png",
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

# OpenAI image models that the slot config may name. The chain entry
# format is `openai:<model_id>` — see _make_handler. Adding a new model
# here makes it routable; the dispatcher itself is model-agnostic.
#
# Transparency support per OpenAI docs (2026-05-22):
#   - gpt-image-1   — supports background=transparent
#   - gpt-image-1.5 — supports background=transparent  (preferred)
#   - gpt-image-2   — does NOT support transparent backgrounds
#   - gpt-image-2-2026-04-21 — does NOT support transparent backgrounds
#
# Per publisher direction 2026-05-22, MSI uses gpt-image-1.5 for any
# image work. gpt-image-1 is explicitly excluded from MSI's slot chains
# at the routing-config level — the model is registered here as a
# generic Ora capability but MSI's preferred + fallback chains do not
# reference it.
OPENAI_IMAGE_MODELS = (
    "gpt-image-1",
    "gpt-image-1.5",
    "gpt-image-2",
    "gpt-image-2-2026-04-21",
)


def _make_handler(model_id: str):
    """Create a slot handler that injects the model id into inputs.

    Each registered provider is a closure that knows its specific model
    id; the chain walker treats them as distinct providers.
    """
    def _handler(inputs: dict) -> bytes:
        # Don't mutate caller's dict; merge model id into a fresh copy.
        merged = dict(inputs)
        merged.setdefault("model", model_id)
        return dispatch_image_generates(merged)
    return _handler


def register(registry: CapabilityRegistry) -> None:
    """Register one provider per OpenAI image model on both image-gen slots.

    Provider id format: ``openai:<model_id>``. The capability registry's
    chain walker picks providers by id, so the slot config can route to
    a specific model by listing ``openai:gpt-image-1.5`` as preferred (or
    in fallback).

    Called by ``register_with_default_registry()`` and exposed directly
    so tests can register against a fresh registry instance.
    """
    for model_id in OPENAI_IMAGE_MODELS:
        pid = f"openai:{model_id}"
        handler = _make_handler(model_id)
        for slot in ("image_generates", "image_generates_cartoon"):
            if registry.has_slot(slot):
                try:
                    registry.register_provider(slot, pid, handler)
                except Exception:
                    # Idempotent: re-register failures are silent so
                    # the broader registration pass continues.
                    pass


def register_with_default_registry() -> CapabilityRegistry:
    """Register this provider against a freshly loaded standard registry.

    ``load_registry()`` constructs a NEW ``CapabilityRegistry`` on every
    call — it does not memoise — so ``register()`` must run against each
    one. A module-level "already registered" latch here would leave the
    second and every later caller holding a registry with none of this
    module's providers bound.

    Safe to call repeatedly: ``register()`` is idempotent per registry
    object (re-binding a provider id replaces its handler and never
    duplicates the slot's provider list).

    Returns the registry so callers can invoke immediately
    (``register_with_default_registry().invoke(...)``).
    """
    registry = load_registry()
    register(registry)
    return registry
