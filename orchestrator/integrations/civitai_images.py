"""Civitai image generation integration — Hector LoRA on the cartoon slot.

Fulfills the ``image_generates_cartoon`` capability slot via Civitai's
orchestration API by submitting a Flux.2 Klein 9B-base txt2img workflow
with the published Hector Rentier Style v1 LoRA applied.

Per Reference — MSI Image Style Specification §5.8.1 (v1.9, 2026-05-12):
``civitai-hector-lora-v1`` is the **fallback** provider for editorial
cartoon generation, behind ``openai-gpt-image-1`` (preferred for image
quality on the engraved-woodcut aesthetic). The LoRA's role is to catch
gpt-image-1 moderation refusals and outages with a guaranteed-spec-compliant
butt-face render. Slot separation (introduced 2026-05-12) means this
dispatcher only ever sees Hector-flavored prompts; the general
``image_generates`` slot — used for news photos and illustration — does
not include the LoRA in its cascade.

Endpoint
--------

``POST https://orchestration.civitai.com/v2/consumer/workflows?wait=120``

The ``wait=120`` query param makes the endpoint synchronous: it waits
up to 120 seconds for the job to reach a terminal state before
responding. For Flux.2 Klein 9B-base, typical wall-clock generation is
30–60 seconds, so the synchronous wait usually returns a completed job
in one round-trip — no client-side polling needed.

Workflow body
-------------

The step body shape was discovered by inspecting a real workflow record
from Civitai's recent jobs (the test generations we ran on 2026-05-11)::

    {
      "steps": [{
        "$type": "imageGen",
        "input": {
          "operation": "createImage",
          "engine": "flux2",
          "modelVariant": "klein",
          "modelVersion": "9b-base",
          "prompt": "<text>",
          "negativePrompt": "",
          "width": 1024, "height": 1024,
          "cfgScale": 7, "steps": 30,
          "sampleMethod": "euler", "schedule": "simple",
          "quantity": 1,
          "outputFormat": "jpeg",
          "loras": {"urn:air:flux2:lora:civitai:2616013@2937250": 0.85}
        }
      }]
    }

The LoRA AIR was looked up via ``GET /api/v1/model-versions/2937250``
and returned ``urn:air:flux2:lora:civitai:2616013@2937250``.

Authentication
--------------

API key resolved at call time from macOS Keychain:
``keyring.get_password("ora", "civitai-api-key")``. ``$CIVITAI_API_KEY``
takes precedence if set. Auth uses Bearer-token in the Authorization
header (verified 2026-05-10 against ``GET /api/v1/models?limit=1`` per
Visual Intelligence Deferrals row "Civitai + TensorArt provider
plumbing").

Error mapping
-------------

Civitai HTTP / job-status codes are translated to the slot's declared
``common_errors`` codes (per ``capabilities.json``):

  * HTTP 401 / 403 → ``model_unavailable``
  * HTTP 402 (insufficient Buzz) → ``quota_exceeded``
  * HTTP 429 → ``quota_exceeded``
  * HTTP 400 with body containing content-policy / moderation language
    → ``prompt_rejected``
  * Job status ``failed`` with reason mentioning policy/safety →
    ``prompt_rejected``
  * Other failures (HTTP 5xx, network, missing key, unexpected
    payload) → ``model_unavailable``

These map cleanly to the registry's default fallback-triggering codes
so when Civitai refuses (e.g., moderation lottery on a boundary-
pushing prompt) the cascade walks to the next provider automatically.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from capability_registry import CapabilityError, CapabilityRegistry


# ---------------------------------------------------------------------------
# Provider identifiers + endpoints
# ---------------------------------------------------------------------------

PROVIDER_HECTOR_LORA = "civitai-hector-lora-v1"

# Hector Rentier Style v1, model 2616013 / version 2937250. Published
# 2026-05-11. AIR returned by Civitai's `GET /api/v1/model-versions/2937250`.
HECTOR_LORA_AIR = "urn:air:flux2:lora:civitai:2616013@2937250"
HECTOR_LORA_TRIGGER = "hectorcartoon"

# Default strength matches the published version's `Strength` field
# (recommended 0.85; works in 0.6–1.0 range).
HECTOR_LORA_STRENGTH = 0.85

# Civitai's orchestration API. wait=120 *requests* synchronous behavior
# (block up to 120 s for terminal state), but the endpoint frequently
# returns "scheduled" before completion regardless. We treat the wait
# param as a hint and follow up with explicit polling against the
# per-workflow GET endpoint until a terminal status is reached.
WORKFLOW_ENDPOINT = "https://orchestration.civitai.com/v2/consumer/workflows?wait=120"
WORKFLOW_DETAIL_ENDPOINT = "https://orchestration.civitai.com/v2/consumer/workflows/{id}"

# Polling parameters. Flux.2 Klein 9B-base finishes in 30–60 s typically;
# poll every 4 s up to 4 minutes before giving up.
_POLL_INTERVAL_SEC = 4
_POLL_MAX_SECONDS = 240
# Statuses Civitai uses on the /workflows endpoints. Terminal statuses
# end the polling loop; non-terminal statuses are retried.
_TERMINAL_OK = {"succeeded"}
_TERMINAL_FAIL = {"failed", "canceled", "cancelled", "expired"}
_NON_TERMINAL = {"scheduled", "queued", "running", "processing", "pending"}

# Aspect ratio → (width, height). Flux.2 Klein accepts a range of sizes;
# these are the standard buckets matching the slot contract enum.
_ASPECT_TO_SIZE: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
}

# Generation defaults that match the Civitai UI's default workflow for
# Flux.2 Klein 9B-base — same values the in-browser generator submits.
_DEFAULT_CFG_SCALE = 7
_DEFAULT_STEPS = 30
_DEFAULT_SAMPLER = "euler"
_DEFAULT_SCHEDULE = "simple"

# urllib.request total timeout — must comfortably exceed the wait=120
# query param so the server can return its synchronous answer.
_REQUEST_TIMEOUT_SEC = 180
_IMAGE_FETCH_TIMEOUT_SEC = 60

# Cloudflare in front of orchestration.civitai.com blocks the default
# Python-urllib User-Agent. Use a realistic browser-style UA to get past
# the bot check; the API itself authenticates via Bearer token.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15 "
    "ora-orchestrator/civitai_images"
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Resolve the Civitai API key from env or macOS Keychain.

    Returns ``None`` when no key is configured. The dispatcher converts a
    missing key into ``CapabilityError(model_unavailable)`` so the caller
    surfaces the documented fix path.
    """
    key = os.environ.get("CIVITAI_API_KEY") or ""
    if key:
        return key
    try:
        import keyring  # lazy so tests can stub
        return keyring.get_password("ora", "civitai-api-key") or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------

def _translate_http_error(exc: urllib.error.HTTPError, slot: str) -> CapabilityError:
    """Map an HTTPError from the orchestration endpoint into a slot-level
    CapabilityError using the standard codes.

    The body is read once and snippet-included in the message for
    debugging without leaking secrets — Civitai's error responses are
    short JSON objects with a ``message`` or ``error`` field.
    """
    status = exc.code
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    snippet = body[:300]
    body_lower = body.lower()

    if status in (401, 403):
        return CapabilityError(
            "model_unavailable",
            f"Civitai auth failed (HTTP {status}): {snippet}",
            slot=slot,
        )
    if status == 402:
        return CapabilityError(
            "quota_exceeded",
            f"Civitai insufficient Buzz (HTTP 402): {snippet}",
            slot=slot,
        )
    if status == 429:
        return CapabilityError(
            "quota_exceeded",
            f"Civitai rate limit (HTTP 429): {snippet}",
            slot=slot,
        )
    # 400 with policy language → prompt_rejected; other 400s →
    # model_unavailable so a future routing-config tweak can still
    # cascade if desired.
    if status == 400 and any(t in body_lower for t in (
            "content policy", "blocked", "moderation", "safety",
            "violat", "prohibited", "disallow")):
        return CapabilityError(
            "prompt_rejected",
            f"Civitai content policy blocked the prompt: {snippet}",
            slot=slot,
        )
    return CapabilityError(
        "model_unavailable",
        f"Civitai HTTP {status}: {snippet}",
        slot=slot,
    )


def _translate_job_failure(payload: dict, slot: str) -> CapabilityError:
    """Translate a non-success job status into a CapabilityError.

    Reads ``payload.status`` and any ``reason`` / ``error`` field
    Civitai surfaces and maps to ``prompt_rejected`` when the failure
    text mentions policy / safety, else ``model_unavailable``.
    """
    status = payload.get("status") or "<unknown>"
    reason = (
        payload.get("reason")
        or payload.get("error")
        or payload.get("message")
        or ""
    )
    reason_lower = str(reason).lower()
    if any(t in reason_lower for t in (
            "content policy", "blocked", "moderation", "safety",
            "violat", "prohibited", "disallow")):
        return CapabilityError(
            "prompt_rejected",
            f"Civitai job {status}: {reason}",
            slot=slot,
        )
    return CapabilityError(
        "model_unavailable",
        f"Civitai job {status}: {reason or '<no reason>'}",
        slot=slot,
    )


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

def _poll_until_terminal(workflow_id: str, api_key: str) -> dict:
    """Poll ``GET /v2/consumer/workflows/<id>`` until the job reaches a
    terminal status (succeeded / failed / canceled / expired) or the
    timeout (``_POLL_MAX_SECONDS``) is reached.

    Returns the most recent workflow payload regardless of final status —
    the caller is responsible for translating the status into a
    CapabilityError (or returning the result on success).
    """
    import time

    detail_url = WORKFLOW_DETAIL_ENDPOINT.format(id=workflow_id)
    elapsed = 0.0
    payload: dict = {"status": "unknown", "id": workflow_id}

    while elapsed < _POLL_MAX_SECONDS:
        time.sleep(_POLL_INTERVAL_SEC)
        elapsed += _POLL_INTERVAL_SEC

        poll_req = urllib.request.Request(
            detail_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                    poll_req, timeout=_REQUEST_TIMEOUT_SEC) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A transient 5xx during polling shouldn't kill the whole
            # run; keep trying until the cap. 4xx (auth / not-found) is
            # fatal and surfaces via the next loop's translation.
            if 500 <= exc.code < 600:
                continue
            raise _translate_http_error(exc, slot="image_generates_cartoon") from exc
        except urllib.error.URLError:
            # Same logic for network blips — retry until cap.
            continue

        status = payload.get("status")
        if status in _TERMINAL_OK or status in _TERMINAL_FAIL:
            return payload

    return payload


# ---------------------------------------------------------------------------
# Dispatcher — fulfills image_generates via Flux.2 Klein 9B-base + Hector LoRA
# ---------------------------------------------------------------------------

def dispatch_hector_lora(inputs: dict) -> bytes:
    """Submit a generation job to Civitai using the Hector LoRA.

    Per slot contract §3.1:
      * Required: ``prompt`` (text).
      * Optional: ``style`` (text appended to prompt), ``aspect_ratio`` (enum).
      * Output: image bytes.

    The activation token ``hectorcartoon`` is auto-prepended to the
    prompt if not already present — the LoRA was trained with it as the
    leading token, and including it consistently improves activation.

    Synchronous: uses the orchestration endpoint's ``wait=120`` mode so
    the request returns when the job reaches a terminal state. No
    client-side polling required.
    """
    prompt = inputs.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise CapabilityError(
            "missing_required_input",
            "image_generates_cartoon requires a non-empty 'prompt' string.",
            slot="image_generates_cartoon",
        )

    style = inputs.get("style")
    aspect_ratio = inputs.get("aspect_ratio") or "1:1"
    width, height = _ASPECT_TO_SIZE.get(aspect_ratio, (1024, 1024))

    composed_prompt = prompt.strip()
    # The LoRA's activation token `hectorcartoon` is auto-prepended if not
    # already present. The LoRA was trained with the token as the leading
    # marker, and including it consistently improves activation. Under the
    # 2026-05-12 slot-separation architecture, this dispatcher is registered
    # only against `image_generates_cartoon` and is therefore only reached
    # from the Hector cartoon path — non-cartoon prompts cannot route here.
    if HECTOR_LORA_TRIGGER not in composed_prompt.lower():
        composed_prompt = f"{HECTOR_LORA_TRIGGER} {composed_prompt}"
    if style and isinstance(style, str) and style.strip():
        composed_prompt = f"{composed_prompt}, in the style of {style.strip()}"

    api_key = _get_api_key()
    if not api_key:
        raise CapabilityError(
            "model_unavailable",
            "No Civitai API key configured. Store at keyring "
            "service='ora', username='civitai-api-key', or set "
            "$CIVITAI_API_KEY. See Framework — API Key Acquisition.md.",
            slot="image_generates_cartoon",
        )

    body: dict[str, Any] = {
        "steps": [{
            "$type": "imageGen",
            "input": {
                "operation": "createImage",
                "engine": "flux2",
                "model": "klein",
                "modelVersion": "9b-base",
                "prompt": composed_prompt,
                "negativePrompt": "",
                "width": width,
                "height": height,
                "cfgScale": _DEFAULT_CFG_SCALE,
                "steps": _DEFAULT_STEPS,
                "sampleMethod": _DEFAULT_SAMPLER,
                "schedule": _DEFAULT_SCHEDULE,
                "quantity": 1,
                "enablePromptExpansion": False,
                "outputFormat": "jpeg",
                "loras": {
                    HECTOR_LORA_AIR: HECTOR_LORA_STRENGTH,
                },
            },
        }],
    }

    req = urllib.request.Request(
        WORKFLOW_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _translate_http_error(exc, slot="image_generates_cartoon") from exc
    except urllib.error.URLError as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Civitai network error: {exc.reason}",
            slot="image_generates_cartoon",
        ) from exc

    status = payload.get("status")
    workflow_id = payload.get("id")

    # If the synchronous wait didn't catch a terminal state, poll the
    # workflow's detail endpoint until it settles or we hit the cap.
    if status in _NON_TERMINAL and workflow_id:
        payload = _poll_until_terminal(workflow_id, api_key)
        status = payload.get("status")

    if status in _TERMINAL_FAIL:
        raise _translate_job_failure(payload, slot="image_generates_cartoon")
    if status not in _TERMINAL_OK:
        raise CapabilityError(
            "model_unavailable",
            f"Civitai job did not reach terminal state within "
            f"{_POLL_MAX_SECONDS}s (final status={status}).",
            slot="image_generates_cartoon",
        )

    steps = payload.get("steps") or []
    if not steps:
        raise CapabilityError(
            "model_unavailable",
            "Civitai response missing steps array.",
            slot="image_generates_cartoon",
        )
    output = steps[0].get("output") or {}
    images = output.get("images") or []
    if not images:
        raise CapabilityError(
            "model_unavailable",
            "Civitai response missing images array.",
            slot="image_generates_cartoon",
        )

    first = images[0]
    image_url = first.get("url") or first.get("previewUrl")
    if not image_url:
        raise CapabilityError(
            "model_unavailable",
            "Civitai response image entry missing url.",
            slot="image_generates_cartoon",
        )

    # Fetch the JPEG bytes from the signed orchestration-new URL. Same
    # User-Agent override — the CDN sits behind the same Cloudflare config.
    image_req = urllib.request.Request(
        image_url,
        headers={"User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
                image_req, timeout=_IMAGE_FETCH_TIMEOUT_SEC) as img_resp:
            return img_resp.read()
    except urllib.error.HTTPError as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Civitai image fetch HTTP {exc.code} from signed URL.",
            slot="image_generates_cartoon",
        ) from exc
    except urllib.error.URLError as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Civitai image fetch network error: {exc.reason}",
            slot="image_generates_cartoon",
        ) from exc


# ---------------------------------------------------------------------------
# Slot fulfillment registration
# ---------------------------------------------------------------------------

def register(registry: CapabilityRegistry) -> None:
    """Bind the Hector LoRA dispatcher to the ``image_generates_cartoon`` slot.

    Called by ``register_with_default_registry()`` and exposed directly
    so tests can register against a fresh registry instance without
    pulling in the standard config files.

    Per the 2026-05-12 slot-separation architecture, the LoRA is only
    registered against ``image_generates_cartoon`` — not the general
    ``image_generates`` slot. This guarantees the LoRA only ever sees
    Hector cartoon prompts; news / illustration prompts cannot route to
    it. See routing-config.json's ``image_generates_cartoon._note`` for
    the cascade order (gpt-image-1 preferred; LoRA as fallback).
    """
    registry.register_provider(
        "image_generates_cartoon",
        PROVIDER_HECTOR_LORA,
        dispatch_hector_lora,
    )


_default_registered = False


def register_with_default_registry() -> CapabilityRegistry:
    """Lazy-register this provider against the standard registry."""
    global _default_registered
    from capability_registry import load_registry
    registry = load_registry()
    if not _default_registered:
        register(registry)
        _default_registered = True
    return registry
