"""Stability AI provider integration (WP-7.3.2b).

Fulfills three capability slots via the Stability AI REST API at
``https://api.stability.ai``:

  * ``image_generates``  — SD3 Large text-to-image (default).
  * ``image_outpaints``  — Outpaint endpoint (extends image in cardinal
    directions).
  * ``image_upscales``   — Conservative upscale endpoint (the cheapest
    sync upscaler; faster than the creative tier).

Default model: **SD3 Large** (``stability-sd3-large``). Rationale —
- SDXL (``stable-diffusion-xl-1024-v1-0``) is the legacy 1024-px
  workhorse; well-priced (~$0.04/image) but lower fidelity on text
  rendering and complex multi-subject prompts.
- SD3 Large is Stability's current premier text-to-image. Better text
  rendering, better multi-subject coherence, ~$0.065/image at 1024×1024.
  Sweet spot for a default.
- Flux (Black Forest Labs) is hosted on Stability but isn't a Stability
  model. Replicate is a better aggregator path for Flux variants.

§11.13 of the Visual Intelligence Implementation Plan defines the
auth pattern: keyring service-name ``ora-stability``, account
``api-key``. Missing key surfaces ``model_unavailable`` pointing at
``Framework — API Key Acquisition.md``.

Errors are mapped to the slot's declared ``common_errors`` codes per
``capabilities.json`` so callers see consistent error taxonomies
regardless of which provider fulfilled the slot.

Public API:
  * ``dispatch_image_generates(prompt, style=None, aspect_ratio=None, **kwargs) -> bytes``
  * ``dispatch_image_outpaints(image, directions, prompt, aspect_ratio=None, **kwargs) -> bytes``
  * ``dispatch_image_upscales(image, scale_factor=2.0, **kwargs) -> bytes``
  * ``register(registry)``      — bind the dispatchers to a
    ``CapabilityRegistry`` under provider id ``"stability"``.
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable

# Capability registry import — done lazily inside register() to avoid
# circular imports if anything in capability_registry ever wants to
# pre-load integrations.

PROVIDER_ID = "stability"
KEYRING_SERVICE = "ora-stability"
KEYRING_ACCOUNT = "api-key"

API_HOST = "https://api.stability.ai"
GENERATE_ENDPOINT = "/v2beta/stable-image/generate/sd3"
OUTPAINT_ENDPOINT = "/v2beta/stable-image/edit/outpaint"
UPSCALE_ENDPOINT = "/v2beta/stable-image/upscale/conservative"

DEFAULT_MODEL = "sd3-large"  # SD3 Large is the default; sd3-medium / sd3-large-turbo also live behind /v2beta/stable-image/generate/sd3

# Aspect-ratio mapping. Stability's v2beta API accepts an enumerated
# list; these match the slot contract's optional_inputs.aspect_ratio
# enum_values exactly.
ASPECT_RATIOS = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
    "3:4": "3:4",
}

VALID_DIRECTIONS = {"top", "bottom", "left", "right"}


# ---------------------------------------------------------------------------
# Errors — all raised as CapabilityError with codes drawn from each
# slot's ``common_errors`` list in ``~/ora/config/capabilities.json``.
# ---------------------------------------------------------------------------

def _capability_error(code: str, message: str, slot: str | None = None):
    """Construct the registry's ``CapabilityError`` lazily.

    Done lazily so this module can be imported even from environments
    that don't have the orchestrator on ``sys.path`` (tests, tools).
    """
    from capability_registry import CapabilityError  # noqa: WPS433
    return CapabilityError(code, message, slot=slot)


def _get_api_key() -> str:
    """Pull the Stability API key from the macOS Keychain.

    Raises ``CapabilityError(model_unavailable)`` with a fix-path
    pointer to the API Key Acquisition framework when no key is stored.
    Matches the §11.13 acquisition flow.
    """
    try:
        import keyring  # noqa: WPS433
    except ImportError:
        raise _capability_error(
            "model_unavailable",
            "Stability provider requires the `keyring` library. "
            "Install via `pip install keyring`.",
        )

    key = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    if not key:
        raise _capability_error(
            "model_unavailable",
            "No Stability AI API key found in Keychain "
            f"(service='{KEYRING_SERVICE}', account='{KEYRING_ACCOUNT}'). "
            "Configure via the conversational walkthrough in "
            "`Framework — API Key Acquisition.md` (Layer 2). "
            "Or store directly: "
            f"`keyring set {KEYRING_SERVICE} {KEYRING_ACCOUNT}`.",
        )
    return key


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _multipart_request(
    endpoint: str,
    fields: dict[str, Any],
    files: dict[str, tuple[str, bytes, str]] | None = None,
    timeout: float = 120.0,
    api_key: str | None = None,
    slot: str | None = None,
) -> bytes:
    """POST a multipart/form-data request to a Stability endpoint.

    ``fields`` maps form-field names to string-coercible values.
    ``files`` maps form-field names to ``(filename, bytes, content_type)``.

    Returns raw response bytes (image PNG/JPEG payload). Translates
    common HTTP status codes to ``CapabilityError`` with appropriate
    slot-level error codes.
    """
    boundary = f"----oraform{uuid.uuid4().hex}"
    body = io.BytesIO()
    eol = b"\r\n"

    for name, value in fields.items():
        if value is None:
            continue
        body.write(f"--{boundary}".encode())
        body.write(eol)
        body.write(
            f'Content-Disposition: form-data; name="{name}"'.encode()
        )
        body.write(eol)
        body.write(eol)
        body.write(str(value).encode())
        body.write(eol)

    for name, (filename, payload, content_type) in (files or {}).items():
        body.write(f"--{boundary}".encode())
        body.write(eol)
        body.write(
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"'.encode()
        )
        body.write(eol)
        body.write(f"Content-Type: {content_type}".encode())
        body.write(eol)
        body.write(eol)
        body.write(payload)
        body.write(eol)

    body.write(f"--{boundary}--".encode())
    body.write(eol)
    payload = body.getvalue()

    key = api_key or _get_api_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "image/*",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }

    request = urllib.request.Request(
        f"{API_HOST}{endpoint}",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise _translate_http_error(exc, slot=slot) from exc
    except urllib.error.URLError as exc:
        raise _capability_error(
            "model_unavailable",
            f"Network error reaching Stability AI: {exc.reason}",
            slot=slot,
        ) from exc


def _translate_http_error(exc: urllib.error.HTTPError, slot: str | None):
    """Map Stability HTTP errors to the slot's ``common_errors`` taxonomy.

    Stability returns JSON bodies like
    ``{"name": "content_moderation", "errors": ["..."]}`` on 4xx. We
    parse and route to the slot's declared codes; unknown shapes fall
    back to ``handler_failed``.
    """
    status = exc.code
    detail = ""
    body_name = ""
    try:
        raw = exc.read()
        try:
            decoded = json.loads(raw.decode("utf-8", errors="replace"))
            body_name = (decoded.get("name") or "").lower()
            errors_list = decoded.get("errors") or []
            detail = "; ".join(str(e) for e in errors_list) or decoded.get(
                "message", ""
            )
        except (json.JSONDecodeError, ValueError):
            detail = raw.decode("utf-8", errors="replace")[:500]
    except Exception:  # pragma: no cover — exhausted body read
        detail = exc.reason or ""

    # 401/403 — authentication problems → model_unavailable
    if status in (401, 403):
        return _capability_error(
            "model_unavailable",
            "Stability rejected the API key (HTTP "
            f"{status}). Re-run the API Key Acquisition flow. "
            f"Server detail: {detail}",
            slot=slot,
        )

    # 429 — rate limit → quota_exceeded (only declared on
    # image_generates; for the others we fall back to handler_failed
    # but still surface the rate-limit fact in the message).
    if status == 429:
        if slot == "image_generates":
            return _capability_error(
                "quota_exceeded",
                f"Stability rate limit hit. Server detail: {detail}",
                slot=slot,
            )
        return _capability_error(
            "handler_failed",
            f"Stability rate limit hit (HTTP 429). {detail}",
            slot=slot,
        )

    # 400 — bad request. Stability uses these names on the body:
    #   content_moderation       → prompt_rejected
    #   invalid_prompts          → prompt_rejected
    #   payload_too_large        → image_too_large
    #   image_too_large          → image_too_large
    #   image_too_small          → image_too_small
    if status == 400:
        if "moderation" in body_name or "moderation" in detail.lower() or "prompt" in body_name:
            if slot == "image_generates":
                return _capability_error(
                    "prompt_rejected",
                    f"Stability moderation rejected the prompt. {detail}",
                    slot=slot,
                )
        if "too_large" in body_name or "too large" in detail.lower():
            if slot in ("image_outpaints", "image_upscales"):
                return _capability_error(
                    "image_too_large",
                    f"Stability says image too large. {detail}",
                    slot=slot,
                )
        if "too_small" in body_name or "too small" in detail.lower():
            if slot == "image_upscales":
                return _capability_error(
                    "image_too_small",
                    f"Stability says image too small. {detail}",
                    slot=slot,
                )

    # 413 — payload too large
    if status == 413 and slot in ("image_outpaints", "image_upscales"):
        return _capability_error(
            "image_too_large",
            f"Stability rejected payload as too large. {detail}",
            slot=slot,
        )

    # Fallback: handler_failed with full detail.
    return _capability_error(
        "handler_failed",
        f"Stability returned HTTP {status} ({body_name or 'unknown'}): {detail}",
        slot=slot,
    )


# ---------------------------------------------------------------------------
# Image input normalization. The slot contracts pass ``image`` as a
# canvas object id (``image-ref``), but in the absence of the canvas
# wiring (WP-7.5) we accept three forms here so test harnesses and
# direct callers can supply data:
#   * ``bytes``                              — raw image bytes
#   * a ``str`` / ``Path`` to a file         — read from disk
#   * a dict with key ``"bytes"``            — for canvas refs that
#     include eagerly-loaded payloads
# Anything else raises ``handler_failed``.
# ---------------------------------------------------------------------------

def _coerce_image_bytes(image: Any, slot: str) -> bytes:
    if isinstance(image, bytes):
        return image
    if isinstance(image, (str, Path)):
        path = Path(image)
        if not path.exists():
            raise _capability_error(
                "handler_failed",
                f"Image path does not exist: {path}",
                slot=slot,
            )
        return path.read_bytes()
    if isinstance(image, dict) and isinstance(image.get("bytes"), bytes):
        return image["bytes"]
    raise _capability_error(
        "handler_failed",
        f"Unsupported image input type for slot '{slot}': "
        f"{type(image).__name__}. Pass bytes, a path, or a dict "
        "with 'bytes'.",
        slot=slot,
    )


# ---------------------------------------------------------------------------
# Public dispatchers
# ---------------------------------------------------------------------------

def dispatch_image_generates(
    prompt: str,
    style: str | None = None,
    aspect_ratio: str | None = None,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    output_format: str = "png",
    **_unused: Any,
) -> bytes:
    """Generate an image with SD3 Large via the Stability v2beta API.

    Slot contract: ``image_generates`` (capabilities.json §image_generates).
    Returns image bytes (PNG by default).
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise _capability_error(
            "prompt_rejected",
            "Stability `image_generates` requires a non-empty prompt.",
            slot="image_generates",
        )

    full_prompt = prompt.strip()
    if style:
        full_prompt = f"{full_prompt}, {style.strip()}"

    fields: dict[str, Any] = {
        "prompt": full_prompt,
        "model": model,
        "output_format": output_format,
        # Stability v2beta requires *some* file part to switch the
        # endpoint into multipart mode; a zero-byte 'none' file is the
        # documented sentinel for "no init image".
        "mode": "text-to-image",
    }
    if aspect_ratio:
        fields["aspect_ratio"] = ASPECT_RATIOS.get(
            aspect_ratio, aspect_ratio
        )

    files = {
        "none": ("none", b"", "application/octet-stream"),
    }

    return _multipart_request(
        GENERATE_ENDPOINT,
        fields=fields,
        files=files,
        api_key=api_key,
        slot="image_generates",
    )


def dispatch_image_outpaints(
    image: Any,
    directions: Iterable[str],
    prompt: str,
    aspect_ratio: str | None = None,
    *,
    api_key: str | None = None,
    pixels_per_direction: int = 512,
    output_format: str = "png",
    **_unused: Any,
) -> bytes:
    """Extend an image in one or more cardinal directions.

    Slot contract: ``image_outpaints`` (capabilities.json §image_outpaints).
    The Stability outpaint endpoint takes per-direction pixel counts;
    we expose ``pixels_per_direction`` (default 512) so callers can
    tune extension distance without breaking the slot signature.
    Returns image bytes.
    """
    direction_list = list(directions or [])
    if not direction_list:
        raise _capability_error(
            "direction_invalid",
            "image_outpaints requires at least one direction "
            "(top / bottom / left / right).",
            slot="image_outpaints",
        )
    invalid = [d for d in direction_list if d not in VALID_DIRECTIONS]
    if invalid:
        raise _capability_error(
            "direction_invalid",
            f"Unrecognized direction(s): {invalid}. "
            f"Valid: {sorted(VALID_DIRECTIONS)}.",
            slot="image_outpaints",
        )

    if not isinstance(prompt, str) or not prompt.strip():
        raise _capability_error(
            "handler_failed",
            "image_outpaints requires a non-empty prompt describing "
            "the new region.",
            slot="image_outpaints",
        )

    img_bytes = _coerce_image_bytes(image, slot="image_outpaints")

    fields: dict[str, Any] = {
        "prompt": prompt.strip(),
        "output_format": output_format,
    }
    for direction in direction_list:
        fields[direction] = pixels_per_direction
    if aspect_ratio:
        fields["aspect_ratio"] = ASPECT_RATIOS.get(
            aspect_ratio, aspect_ratio
        )

    files = {
        "image": ("source.png", img_bytes, "image/png"),
    }

    return _multipart_request(
        OUTPAINT_ENDPOINT,
        fields=fields,
        files=files,
        api_key=api_key,
        slot="image_outpaints",
    )


def dispatch_image_upscales(
    image: Any,
    scale_factor: float = 2.0,
    *,
    api_key: str | None = None,
    prompt: str | None = None,
    output_format: str = "png",
    **_unused: Any,
) -> bytes:
    """Upscale an image via Stability's conservative-tier endpoint.

    Slot contract: ``image_upscales`` (capabilities.json §image_upscales).
    Returns image bytes.

    Notes:
      * Stability's conservative upscaler outputs at a fixed multiple
        of the input (the API decides the exact factor based on the
        input dimensions; ``scale_factor`` is preserved for callers
        but currently informational only — the conservative endpoint
        takes a target dimension implicitly).
      * For finer-grained scale control, callers should switch
        provider to a Replicate-hosted ESRGAN-style model
        (WP-7.3.2c) — that's the long-tail aggregator role per the
        Visual Intelligence Implementation Plan.
    """
    if scale_factor <= 1.0:
        raise _capability_error(
            "handler_failed",
            "image_upscales requires scale_factor > 1.0.",
            slot="image_upscales",
        )

    img_bytes = _coerce_image_bytes(image, slot="image_upscales")

    fields: dict[str, Any] = {
        "output_format": output_format,
    }
    if prompt:
        fields["prompt"] = prompt.strip()
    else:
        # Stability's conservative upscale endpoint requires a prompt
        # (it's a guidance signal, not the only generative input). When
        # callers don't supply one, fall back to a neutral default that
        # describes "preserve detail" semantics.
        fields["prompt"] = "high detail, sharp focus"

    files = {
        "image": ("source.png", img_bytes, "image/png"),
    }

    return _multipart_request(
        UPSCALE_ENDPOINT,
        fields=fields,
        files=files,
        api_key=api_key,
        slot="image_upscales",
    )


# ---------------------------------------------------------------------------
# Slot fulfillment registration
# ---------------------------------------------------------------------------

def _handler_image_generates(inputs: dict) -> bytes:
    return dispatch_image_generates(
        prompt=inputs.get("prompt", ""),
        style=inputs.get("style"),
        aspect_ratio=inputs.get("aspect_ratio"),
    )


def _handler_image_outpaints(inputs: dict) -> bytes:
    return dispatch_image_outpaints(
        image=inputs.get("image"),
        directions=inputs.get("directions") or [],
        prompt=inputs.get("prompt", ""),
        aspect_ratio=inputs.get("aspect_ratio"),
    )


def _handler_image_upscales(inputs: dict) -> bytes:
    return dispatch_image_upscales(
        image=inputs.get("image"),
        scale_factor=float(inputs.get("scale_factor") or 2.0),
    )


def register(registry) -> list[str]:
    """Bind Stability's three handlers to the ``CapabilityRegistry``.

    Returns the list of slot names actually registered (for observable
    side effects from the boot sequence). Registration is idempotent —
    calling twice replaces the prior handler.
    """
    bindings = [
        ("image_generates", _handler_image_generates),
        ("image_outpaints", _handler_image_outpaints),
        ("image_upscales", _handler_image_upscales),
    ]
    registered: list[str] = []
    for slot_name, handler in bindings:
        if registry.has_slot(slot_name):
            registry.register_provider(slot_name, PROVIDER_ID, handler)
            registered.append(slot_name)
    return registered
