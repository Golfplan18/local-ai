"""Google Gemini Generative Language API integration (MSI §5.8.1 Slot 2).

Fulfills the ``image_generates`` capability slot via Gemini 2.5 Flash
Image (formerly nicknamed "Nano Banana"). Per the MSI Image Style
Specification §5.8.1 lock-in (2026-05-10), this provider is the
designated Slot 2 fallback when Slot 1 (``openai-gpt-image-1``) returns
a content-policy rejection. The two-tier rotation (Slot 1 → Slot 2)
covers the publication's reliability requirement during the LoRA-
training window; Slots 3 + 4 (TensorArt, Civitai) are intentionally
out-of-scope for this thread (the LoRA training thread is expected to
demote Slot 1 within 1–2 weeks).

Endpoint
--------

``POST https://generativelanguage.googleapis.com/v1beta/models/``
``gemini-2.5-flash-image:generateContent?key=<api-key>``

The Generative Language API takes the key as a ``?key=`` query
parameter — not a Bearer header. Verified working 2026-05-10 via
raw urllib in the parent thread. The endpoint accepts a JSON body of
the shape ``{"contents": [{"parts": [{"text": "<prompt>"}]}]}`` and
returns base64-encoded PNG bytes inside ``candidates[0].content.parts[].
inlineData.data``.

Authentication
--------------

Canonical keychain pattern matching every other API key Ora stores:
service ``ora``, account ``gemini-api-key``. ``$GEMINI_API_KEY`` as an
env override (used in tests / CI). Missing key surfaces
``model_unavailable`` pointing at ``Framework — API Key Acquisition.md``.

Error taxonomy
--------------

Errors map to the slot's declared ``common_errors`` codes per
``capabilities.json`` (matching the stability + openai_images taxonomy
so the capability dispatch fallback logic recognizes errors uniformly
across providers):

  * HTTP 401 / 403 (auth)                 → ``model_unavailable``.
  * HTTP 429 (rate / quota)               → ``quota_exceeded``.
  * HTTP 400 with safety keywords          → ``prompt_rejected``.
  * HTTP 400 generic                       → ``handler_failed``.
  * HTTP 5xx + ``URLError`` network failure → ``model_unavailable``.
  * HTTP 200 with ``promptFeedback.blockReason`` set → ``prompt_rejected``.
  * HTTP 200 with empty ``candidates``    → ``prompt_rejected``
    (Gemini returns an empty 200 on silent safety filter rejection
    rather than a 400 — observed in the parent thread).
  * HTTP 200 with ``finishReason`` in SAFETY/BLOCKED/PROHIBITED_CONTENT
    → ``prompt_rejected``.

The ``prompt_rejected`` mapping is what enables the §5.8.1 Slot-1 →
Slot-2 chain: when ``openai-gpt-image-1`` raises ``prompt_rejected``,
the capability dispatch layer falls through to this provider.

Aspect ratio
------------

The basic ``generateContent`` endpoint does not accept an explicit
size / aspect parameter — framing is a prompt hint. We append a short
one-liner cue to the prompt when ``aspect_ratio`` is non-square. The
slot contract enum is ``{"1:1", "16:9", "9:16", "4:3", "3:4"}``;
square gets no hint.

Public API
----------

* ``dispatch_image_generates(inputs: dict) -> bytes`` — registry-shaped
  handler.
* ``register(registry)`` — bind the dispatcher to ``image_generates``
  under provider id ``"gemini-2.5-flash-image"`` (matching the
  ``models.json`` id so ``routing-config.json`` can reference it
  directly — same convention as ``openai_images.py``).

Test posture
------------

Live network calls are out-of-scope for the unit suite. The shipped
tests mock ``urllib.request.urlopen`` and exercise the dispatch +
error-translation logic. A live integration test is gated behind
``ORA_LIVE_GEMINI_IMAGES=1`` per the stability / openai pattern.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Capability registry import is done lazily inside helpers to avoid a
# circular import if anything in capability_registry ever pre-loads
# integrations. Same pattern as stability.py.


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Provider id matches the ``models.json`` entry's id ("gemini-2.5-flash-image"),
# so ``routing-config.json`` can reference this provider by the same
# string the user sees in the V3 Settings → Models panel. Mirrors the
# convention in openai_images.py (provider_id = model id).
PROVIDER_ID = "gemini-2.5-flash-image"

# Canonical keychain pattern (matches user_settings.py + boot.py):
#   service = "ora", account = "<provider>-api-key"
KEYRING_SERVICE = "ora"
KEYRING_ACCOUNT = "gemini-api-key"
ENV_OVERRIDE = "GEMINI_API_KEY"

API_HOST = "https://generativelanguage.googleapis.com"
GENERATE_ENDPOINT = "/v1beta/models/gemini-2.5-flash-image:generateContent"

# Cloudflare friendliness — same stable UA the stability + replicate
# integrations send so we land at Google's actual auth layer if the
# request ever fronts Cloudflare (it currently doesn't; the consistency
# is cheap insurance).
_USER_AGENT = "ora/1.0 (+https://github.com/ora-commons/ora)"

# Aspect-ratio hint appended to the prompt. Gemini's generateContent
# endpoint does not expose a size or aspect parameter — framing is
# purely a prompt-engineering signal.
_ASPECT_HINTS: dict[str, str] = {
    "16:9": "Compose as a wide landscape image (16:9 aspect ratio).",
    "9:16": "Compose as a tall portrait image (9:16 aspect ratio).",
    "4:3": "Compose as a landscape image (4:3 aspect ratio).",
    "3:4": "Compose as a portrait image (3:4 aspect ratio).",
}

# Gemini finish-reason values that indicate a safety / policy block
# (rather than a normal STOP). Case-insensitive comparison at the
# inspection site. The exact set is documented at
# https://ai.google.dev/api/rest/v1beta/Candidate#FinishReason.
_SAFETY_FINISH_REASONS = {"SAFETY", "BLOCKED", "PROHIBITED_CONTENT", "RECITATION"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def _capability_error(code: str, message: str, slot: str | None = None):
    """Construct ``CapabilityError`` lazily.

    Lazy import so this module can be imported in environments that
    don't have the orchestrator on ``sys.path`` (tools, ad-hoc tests).
    """
    from capability_registry import CapabilityError  # noqa: WPS433
    return CapabilityError(code, message, slot=slot)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Resolve the Gemini API key from env or keychain.

    Raises ``CapabilityError(model_unavailable)`` with a fix-path
    pointer to the API Key Acquisition framework when no key is stored.
    Matches the §11.13 acquisition flow used by the other integrations.
    """
    env_key = (os.environ.get(ENV_OVERRIDE) or "").strip()
    if env_key:
        return env_key
    try:
        import keyring  # noqa: WPS433
    except ImportError:
        raise _capability_error(
            "model_unavailable",
            "Gemini provider requires the `keyring` library. "
            "Install via `pip install keyring`.",
            slot="image_generates",
        )
    key = (keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) or "").strip()
    if not key:
        raise _capability_error(
            "model_unavailable",
            "No Gemini API key found in Keychain "
            f"(service='{KEYRING_SERVICE}', account='{KEYRING_ACCOUNT}'). "
            "Configure via the conversational walkthrough in "
            "`Framework — API Key Acquisition.md` (Layer 2). "
            "Or store directly: "
            f"`keyring set {KEYRING_SERVICE} {KEYRING_ACCOUNT}`.",
            slot="image_generates",
        )
    return key


# ---------------------------------------------------------------------------
# HTTP-error translation
# ---------------------------------------------------------------------------

def _translate_http_error(exc: urllib.error.HTTPError, slot: str | None):
    """Map a Gemini HTTP error to the slot's ``common_errors`` taxonomy.

    Gemini's error body shape is
    ``{"error": {"code": int, "message": str, "status": str, ...}}``.
    We pull ``message`` for the user-visible detail.
    """
    status = exc.code
    detail = ""
    try:
        raw = exc.read()
        try:
            decoded = json.loads(raw.decode("utf-8", errors="replace"))
            err = (decoded or {}).get("error") or {}
            detail = err.get("message") or decoded.get("message", "") or str(decoded)
        except (json.JSONDecodeError, ValueError):
            detail = raw.decode("utf-8", errors="replace")[:500]
    except Exception:  # pragma: no cover — exhausted body read
        detail = exc.reason or ""

    detail_lc = (detail or "").lower()

    if status in (401, 403):
        return _capability_error(
            "model_unavailable",
            f"Gemini rejected the API key (HTTP {status}). "
            "Re-run the API Key Acquisition flow. "
            f"Server detail: {detail}",
            slot=slot,
        )

    if status == 429:
        return _capability_error(
            "quota_exceeded",
            f"Gemini rate limit / quota exceeded (HTTP 429): {detail}",
            slot=slot,
        )

    if status == 400:
        # Gemini occasionally returns safety-related blocks as a 400.
        # Match a generous set of keywords; the slot's prompt_rejected
        # code is what fires the §5.8.1 Slot-2 fallback chain — better
        # to err toward classifying as policy than to misroute.
        if any(
            token in detail_lc
            for token in (
                "safety",
                "blocked",
                "prompt was blocked",
                "safety_violations",
                "harm",
                "policy",
            )
        ):
            return _capability_error(
                "prompt_rejected",
                f"Gemini safety filter blocked the prompt: {detail}",
                slot=slot,
            )
        return _capability_error(
            "handler_failed",
            f"Gemini HTTP 400: {detail}",
            slot=slot,
        )

    if 500 <= status < 600:
        return _capability_error(
            "model_unavailable",
            f"Gemini server error (HTTP {status}): {detail}",
            slot=slot,
        )

    return _capability_error(
        "handler_failed",
        f"Gemini HTTP {status}: {detail}",
        slot=slot,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _extract_inline_image_bytes(payload: dict, slot: str) -> bytes:
    """Walk a Gemini ``generateContent`` response → image bytes.

    The same response may carry multiple parts; the first part with
    ``inlineData`` is the image. ``promptFeedback.blockReason`` and a
    ``finishReason`` in the safety set both indicate a policy block —
    surfaced as ``prompt_rejected`` so the Slot-2 fallback chain fires.
    An empty candidates list with no block reason is treated as a
    silent safety rejection (observed in the parent thread on
    boundary-pushing prompts).
    """
    # Prompt-level block.
    prompt_feedback = payload.get("promptFeedback") or payload.get("prompt_feedback") or {}
    block_reason = prompt_feedback.get("blockReason") or prompt_feedback.get("block_reason")
    if block_reason:
        raise _capability_error(
            "prompt_rejected",
            f"Gemini blocked the prompt (blockReason={block_reason}).",
            slot=slot,
        )

    candidates = payload.get("candidates") or []
    if not candidates:
        # No candidates and no block reason = silent rejection.
        raise _capability_error(
            "prompt_rejected",
            "Gemini returned no candidates (no image generated; most "
            "likely a silent safety filter rejection — Slot-2 fallback "
            "should advance to the next provider).",
            slot=slot,
        )

    first = candidates[0] or {}
    finish_reason = (first.get("finishReason") or first.get("finish_reason") or "").upper()
    parts = ((first.get("content") or {}).get("parts")) or []

    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data") or {}
        data = inline.get("data")
        if data:
            try:
                return base64.b64decode(data)
            except (ValueError, base64.binascii.Error) as exc:
                raise _capability_error(
                    "handler_failed",
                    f"Gemini response inlineData was not valid base64: {exc}",
                    slot=slot,
                ) from exc

    # No inlineData in any part. If the finish reason indicates a
    # safety block, surface prompt_rejected so the fallback chain fires.
    if finish_reason in _SAFETY_FINISH_REASONS:
        raise _capability_error(
            "prompt_rejected",
            f"Gemini blocked the response (finishReason={finish_reason}).",
            slot=slot,
        )

    raise _capability_error(
        "handler_failed",
        f"Gemini response carried no inlineData "
        f"(finishReason={finish_reason or 'unknown'}).",
        slot=slot,
    )


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def dispatch_image_generates(inputs: dict) -> bytes:
    """Fulfill ``image_generates`` via Gemini 2.5 Flash Image.

    Per slot contract §3.1:

      * Required: ``prompt`` (text).
      * Optional: ``style`` (text), ``aspect_ratio`` (enum).
      * Output: image bytes.

    Style + aspect ratio are composed into the prompt text (Gemini's
    basic endpoint exposes neither as a structured parameter). Returns
    raw PNG bytes; raises ``CapabilityError`` with a slot-level code
    on any failure.
    """
    prompt = inputs.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise _capability_error(
            "missing_required_input",
            "image_generates requires a non-empty 'prompt' string.",
            slot="image_generates",
        )

    style_hint = inputs.get("style")
    aspect_ratio = inputs.get("aspect_ratio") or "1:1"

    composed = prompt.strip()
    if isinstance(style_hint, str) and style_hint.strip():
        composed = f"{composed}, in the style of {style_hint.strip()}"
    ratio_hint = _ASPECT_HINTS.get(aspect_ratio)
    if ratio_hint:
        composed = f"{composed}. {ratio_hint}"

    api_key = _get_api_key()
    # urlencode the key so a stray `+` / `&` in a developer-provided key
    # doesn't break the request URL.
    url = (
        f"{API_HOST}{GENERATE_ENDPOINT}"
        f"?key={urllib.parse.quote(api_key, safe='')}"
    )

    body = json.dumps(
        {"contents": [{"parts": [{"text": composed}]}]}
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise _translate_http_error(exc, slot="image_generates") from exc
    except urllib.error.URLError as exc:
        raise _capability_error(
            "model_unavailable",
            f"Network error reaching Gemini: {exc.reason}",
            slot="image_generates",
        ) from exc

    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise _capability_error(
            "handler_failed",
            f"Gemini response was not valid JSON: {exc}",
            slot="image_generates",
        ) from exc

    return _extract_inline_image_bytes(payload, slot="image_generates")


# ---------------------------------------------------------------------------
# Slot fulfillment registration
# ---------------------------------------------------------------------------

def register(registry) -> list[str]:
    """Bind ``dispatch_image_generates`` to the image-generation slots
    under provider id ``"gemini-2.5-flash-image"``.

    Per Image Spec §5.8.1 v2.0 (slot-inheritance, 2026-05-13), the
    cartoon slot inherits its chain from ``image_generates`` and
    appends the Hector LoRA. For the inherited chain to actually reach
    Gemini at runtime, Gemini has to register against both slots — the
    materialized chain only includes providers that are actually
    registered against the destination slot.

    Returns the list of slot names actually registered (matches the
    stability.py / replicate.py return convention so boot-time code can
    log which slots came online).
    """
    registered: list[str] = []
    for slot in ("image_generates", "image_generates_cartoon"):
        if registry.has_slot(slot):
            registry.register_provider(slot, PROVIDER_ID, dispatch_image_generates)
            registered.append(slot)
    return registered
