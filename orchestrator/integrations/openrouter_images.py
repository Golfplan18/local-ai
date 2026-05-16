"""OpenRouter image/video capability provider.

Registers each OpenRouter image-output model from the cached catalog as
its own provider on the ``image_generates`` slot, and each video-output
model on ``video_generates``. The provider id is
``openrouter:<vendor>/<model-id>`` (e.g.,
``openrouter:google/gemini-2.5-flash-image``), matching the IDs the
``/api/capability/providers`` endpoint surfaces.

Call path:
  1. Capability slot is invoked → dispatcher pulled by provider id.
  2. Dispatcher calls OpenRouter's OpenAI-compatible chat-completions
     endpoint with the chosen model and the user prompt, including
     ``modalities=["image", "text"]`` to request image output.
  3. OpenRouter returns a normal completion whose ``message.images``
     list carries ``{type: "image_url", image_url: {url: "data:..."}}``
     dicts. We extract the first base64 data URL, decode it to raw
     bytes, and return the bytes — matching the openai / gemini /
     civitai handler contract so downstream consumers (msi_image_render,
     article_image_sweeper) can treat all image providers uniformly.

Failure-signal contract (Image Spec §5.8.1 v2.0):

  Errors raise ``CapabilityError`` with one of three slot-level codes
  so ``capability_registry.invoke`` can walk the fallback chain.

  * HTTP 400 / 422 / explicit ``content_policy`` markers → ``prompt_rejected``
  * HTTP 401 / 403 (auth)                                → ``model_unavailable``
  * HTTP 429 / explicit ``rate_limit`` / ``quota`` markers → ``quota_exceeded``
  * HTTP 5xx + ``URLError`` network failures              → ``model_unavailable``
  * HTTP 200 with no parseable image content              → ``prompt_rejected``
    (OpenRouter sometimes soft-refuses by returning a text-only response
    explaining what it won't generate — that has to fall through to the
    next provider, not silently succeed)

  This is the contract that lets ``image_generates_cartoon`` (which
  inherits the general slot's chain and appends civitai-hector-lora-v1
  per spec v2.0) reach the LoRA when every OpenRouter and OpenAI
  provider has refused or errored.

Video generation is registered for surface visibility but the call path
is stubbed — OpenRouter's video models have provider-specific request
shapes (Kling, Veo, Wan, Seedance all differ) and need per-model adapters.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
from typing import Any, Callable

_OPENROUTER_CATALOG_PATH = os.path.expanduser("~/ora/config/openrouter-catalog.json")
_API_BASE                = "https://openrouter.ai/api/v1"


def _capability_error(code: str, message: str, *, slot: str | None = None):
    """Lazy CapabilityError constructor — capability_registry sits one dir
    above this file in the orchestrator package and is imported defensively
    so a missing module at import-time doesn't break catalog registration.
    """
    try:
        from capability_registry import CapabilityError  # noqa: WPS433
    except ImportError:
        _orch_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _orch_dir not in sys.path:
            sys.path.insert(0, _orch_dir)
        from capability_registry import CapabilityError  # noqa: WPS433
    return CapabilityError(code, message, slot=slot)


def _classify_openrouter_failure(exc: Exception, slot: str):
    """Translate an arbitrary OpenRouter call exception into a slot-level
    CapabilityError with one of the three cascade-trigger codes.

    The OpenAI SDK proxies most OpenRouter responses through its own
    exception hierarchy when the base_url is set to OpenRouter; raw
    ``urllib.error.HTTPError`` shows up when we hit the videos endpoint
    directly. Text-pattern matching on the exception message catches the
    "content_policy" / "rate_limit" / "quota" / "auth" markers
    OpenRouter and downstream providers actually use.
    """
    msg = str(exc) or exc.__class__.__name__
    msg_lower = msg.lower()

    # Status code may live on the exception (OpenAI SDK) or be embedded
    # in the message (urllib.error.HTTPError, generic OpenAI proxies).
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is None and isinstance(exc, urllib.error.HTTPError):
        status = exc.code
    if status is None:
        m = re.search(r"\b([45]\d\d)\b", msg)
        if m:
            try:
                status = int(m.group(1))
            except ValueError:
                status = None

    # Content-policy / safety / moderation refusals → prompt_rejected
    if any(s in msg_lower for s in (
        "content policy", "content_policy", "safety", "moderation",
        "harmful", "violates", "prohibited", "not allowed", "refus",
        "policy violation",
    )):
        return _capability_error(
            "prompt_rejected",
            f"OpenRouter content-policy refusal: {msg[:240]}",
            slot=slot,
        )

    # Rate limit / quota → quota_exceeded
    if status == 429 or any(s in msg_lower for s in (
        "rate limit", "rate_limit", "quota", "insufficient_quota",
        "billing", "credits",
    )):
        return _capability_error(
            "quota_exceeded",
            f"OpenRouter quota/rate-limit: {msg[:240]}",
            slot=slot,
        )

    # Auth, model-not-found, transport, 5xx → model_unavailable
    if status in (401, 403, 404) or any(s in msg_lower for s in (
        "unauthorized", "forbidden", "not found", "no endpoints found",
        "invalid api key", "model not found",
    )):
        return _capability_error(
            "model_unavailable",
            f"OpenRouter availability error: {msg[:240]}",
            slot=slot,
        )

    if (status is not None and 500 <= status < 600) or any(s in msg_lower for s in (
        "timeout", "timed out", "connection", "network",
    )):
        return _capability_error(
            "model_unavailable",
            f"OpenRouter network/5xx: {msg[:240]}",
            slot=slot,
        )

    # Unclassified — treat as model_unavailable so the cascade still walks
    # rather than fail-stopping the whole chain on a novel error shape.
    return _capability_error(
        "model_unavailable",
        f"OpenRouter unclassified error: {msg[:240]}",
        slot=slot,
    )


def _decode_image_url_to_bytes(url: str) -> bytes:
    """Decode an image URL returned by OpenRouter into raw bytes.

    Accepts either a base64 data URL (``data:image/png;base64,...``) —
    by far the common case for OpenRouter image responses — or an
    ``https://`` URL which we fetch directly.
    """
    if url.startswith("data:"):
        # data:image/png;base64,<payload>
        m = re.match(r"^data:[^;,]+(?:;[^,]+)*,(.*)$", url, re.DOTALL)
        if not m:
            raise ValueError("malformed data URL")
        payload = m.group(1)
        # The standard for image data URLs is ;base64 — but be tolerant.
        if ";base64" in url.split(",", 1)[0]:
            return base64.b64decode(payload)
        # URL-encoded payload — rare but possible
        import urllib.parse
        return urllib.parse.unquote_to_bytes(payload)

    if url.startswith(("http://", "https://")):
        import urllib.request
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()

    raise ValueError(f"unsupported image URL scheme: {url[:64]}...")


def _resolve_key() -> str:
    try:
        import keyring
        return (os.environ.get("OPENROUTER_API_KEY", "")
                or keyring.get_password("ora", "openrouter-api-key") or "")
    except Exception:
        return os.environ.get("OPENROUTER_API_KEY", "")


def _load_catalog() -> dict:
    try:
        with open(_OPENROUTER_CATALOG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"by_modality": {}, "models": []}


def _extract_image_url(message: Any) -> str | None:
    """Pull the first image-result URL out of an OpenRouter chat-completion
    message. Handles the documented shape (``message.images`` list of
    ``{type:"image_url", image_url:{url:...}}``) plus a couple of
    documented fallbacks (markdown ``![]()`` in string content)."""
    # Pattern A: msg.images list of typed image blocks
    images = getattr(message, "images", None) or []
    for img in images:
        if isinstance(img, dict):
            url_obj = img.get("image_url")
            if isinstance(url_obj, dict) and url_obj.get("url"):
                return url_obj["url"]
            if isinstance(url_obj, str):
                return url_obj
    # Pattern B: content is a string carrying a data URL or markdown image
    content = getattr(message, "content", None) or ""
    if isinstance(content, str):
        if content.startswith("data:image"):
            return content
        m = re.search(r"!\[[^\]]*\]\(([^)]+)\)", content)
        if m:
            return m.group(1)
        m = re.search(r"https?://\S+\.(?:png|jpe?g|webp|gif)", content)
        if m:
            return m.group(0)
    return None


def _image_ref_to_data_url(ref: Any) -> str:
    """Normalize an ``image_edits``/etc. input to a data URL the
    chat-completions image_url block accepts. Accepts:
      * existing data: or http(s): URL string  (returned unchanged)
      * file path string                       (read and base64-encoded)
      * bytes                                  (base64-encoded as png)
    """
    if isinstance(ref, str):
        if ref.startswith(("data:", "http://", "https://")):
            return ref
        # Treat as a file path
        if os.path.exists(ref):
            with open(ref, "rb") as f:
                data = f.read()
            ext = os.path.splitext(ref)[1].lstrip(".").lower() or "png"
            mime = {"jpg": "jpeg"}.get(ext, ext)
            return f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
        raise ValueError(f"image ref not found on disk: {ref}")
    if isinstance(ref, (bytes, bytearray)):
        return f"data:image/png;base64,{base64.b64encode(bytes(ref)).decode()}"
    raise ValueError(f"unsupported image ref type: {type(ref).__name__}")


def _call_image_model(model_id: str, prompt: str,
                      slot: str = "image_generates",
                      source_image: Any = None) -> bytes:
    """Invoke a chosen OpenRouter image-output model and return raw bytes.

    Returns raw image bytes (PNG/JPEG/WebP) ready for vectorization or
    direct write. Matches the openai/gemini/civitai handler contract.

    When ``source_image`` is provided (path, URL, or bytes), it's passed
    alongside the prompt as a chat-completions ``image_url`` content
    block. This is the ``image_edits`` / ``image_styles`` / ``image_varies``
    path — only image-input-capable upstreams support it (Gemini Image,
    GPT-image, FLUX 2). Models that don't accept image input will surface
    an upstream error which we translate to ``model_unavailable`` so the
    cascade walks.

    Raises ``CapabilityError`` with a slot-level code on any failure so
    ``capability_registry.invoke`` walks the next provider:
      * ``prompt_rejected`` — content policy, soft refusal, missing image
      * ``quota_exceeded`` — rate limit, quota exhaustion, billing
      * ``model_unavailable`` — auth, 5xx, network, model-not-found, etc.
    """
    key = _resolve_key()
    if not key:
        raise _capability_error(
            "model_unavailable",
            "OpenRouter API key not set (Settings → External APIs).",
            slot=slot,
        )
    if not prompt:
        raise _capability_error(
            "missing_required_input",
            "OpenRouter image generation requires a non-empty prompt.",
            slot=slot,
        )

    # Build the messages payload. Plain text-only for generation; multi-part
    # text+image for edit/style/varies operations.
    if source_image is not None:
        try:
            img_url = _image_ref_to_data_url(source_image)
        except Exception as exc:
            raise _capability_error("missing_required_input",
                f"could not load source_image: {exc}", slot=slot) from exc
        messages = [{
            "role": "user",
            "content": [
                {"type": "text",      "text": prompt},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        }]
    else:
        messages = [{"role": "user", "content": prompt}]

    # Different OpenRouter image models advertise different output
    # modalities. Dual-output models (e.g. ``google/gemini-2.5-flash-image``,
    # ``openai/gpt-image-1``) need ``["image", "text"]``; pure-image
    # models (FLUX, Recraft) need ``["image"]`` and 404 otherwise. Try
    # the more-permissive request first; on the specific "no endpoints
    # found" rejection, retry with image-only.
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=_API_BASE)
        def _do(modalities):
            return client.chat.completions.create(
                model=model_id,
                messages=messages,
                modalities=modalities,
                extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora"},
            )
        try:
            resp = _do(["image", "text"])
        except Exception as e:
            if "No endpoints found that support the requested output modalities" in str(e):
                resp = _do(["image"])
            else:
                raise
    except Exception as exc:
        raise _classify_openrouter_failure(exc, slot=slot) from exc

    msg = resp.choices[0].message if resp.choices else None
    url = _extract_image_url(msg) if msg else None
    if not url:
        # OpenRouter sometimes soft-refuses by returning a text-only
        # explanation of what it won't draw. Surface as prompt_rejected
        # so the cascade walks to the next provider (and ultimately the
        # LoRA backstop) instead of treating the refusal as success.
        preview = ""
        if msg is not None:
            content = getattr(msg, "content", "") or ""
            preview = str(content)[:240]
        raise _capability_error(
            "prompt_rejected",
            f"OpenRouter returned no image (model {model_id}). "
            f"Response preview: {preview!r}",
            slot=slot,
        )

    try:
        return _decode_image_url_to_bytes(url)
    except Exception as exc:
        raise _capability_error(
            "model_unavailable",
            f"OpenRouter image decode failed for {model_id}: {exc}",
            slot=slot,
        ) from exc


def _call_video_model(model_id: str, prompt: str,
                       poll_interval_s: float = 5.0,
                       max_wait_s: float = 600.0,
                       slot: str = "video_generates") -> bytes:
    """Submit an OpenRouter video-generation job and poll until done,
    then fetch the video bytes.

    OpenRouter's video endpoint (``POST /v1/videos``) is async — it
    returns ``{"id":..., "polling_url":..., "status":"pending"}``. The
    polling URL returns the same envelope with ``status`` transitioning
    to ``completed`` and result links in ``unsigned_urls``. We fetch
    the first URL (with the bearer token) and return its bytes — matching
    the image-handler contract.

    Raises ``CapabilityError`` on any failure so the cascade walks.
    Verified end-to-end against ``google/veo-3.1-fast`` (~77s, ~1 MB MP4).
    """
    import urllib.request
    key = _resolve_key()
    if not key:
        raise _capability_error("model_unavailable",
                                 "OpenRouter API key not set.", slot=slot)
    if not prompt:
        raise _capability_error("missing_required_input",
                                 "Video generation requires a non-empty prompt.", slot=slot)

    headers = {
        "Authorization":  f"Bearer {key}",
        "Content-Type":   "application/json",
        "HTTP-Referer":   "https://ora.local",
        "X-Title":        "Ora",
    }
    started = time.time()

    # ── Submit job
    try:
        body = json.dumps({"model": model_id, "prompt": prompt}).encode()
        req = urllib.request.Request(_API_BASE + "/videos", data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            job = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        raise _classify_openrouter_failure(exc, slot=slot) from exc

    poll_url = job.get("polling_url")
    job_id   = job.get("id")
    if not poll_url:
        raise _capability_error("model_unavailable",
            f"OpenRouter video submit returned no polling_url: {job}", slot=slot)

    # ── Poll for completion
    last_state = None
    while time.time() - started < max_wait_s:
        time.sleep(poll_interval_s)
        try:
            req = urllib.request.Request(poll_url, headers={"Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                last_state = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            raise _classify_openrouter_failure(exc, slot=slot) from exc

        status = (last_state or {}).get("status", "").lower()
        if status in ("completed", "complete", "success", "succeeded"):
            url = _extract_video_url(last_state)
            if not url:
                raise _capability_error("model_unavailable",
                    f"Video job {job_id} completed but no URL found. Body: {str(last_state)[:240]}",
                    slot=slot)
            # ── Fetch the video bytes
            try:
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    return r.read()
            except Exception as exc:
                raise _capability_error("model_unavailable",
                    f"Video fetch failed for {url}: {exc}", slot=slot) from exc
        if status in ("failed", "error", "errored"):
            raise _capability_error("model_unavailable",
                f"OpenRouter video job {job_id} failed: {last_state.get('error') or last_state}",
                slot=slot)
        # pending / running / queued — continue polling

    raise _capability_error("model_unavailable",
        f"OpenRouter video job {job_id} timed out after {max_wait_s}s (poll: {poll_url})",
        slot=slot)


def _extract_video_url(state: dict) -> str | None:
    """Walk a video-job-complete envelope for the actual video URL.
    The exact field name varies upstream — try several common shapes.

    OpenRouter's observed completion shape carries the result URL in
    ``unsigned_urls`` (a list); fetching that URL with the bearer key
    returns the actual video bytes. ``signed_urls`` covers the
    alternate form for time-limited links.
    """
    if not isinstance(state, dict):
        return None
    # List-of-URLs fields (OpenRouter primary shape)
    for key in ("unsigned_urls", "signed_urls", "urls"):
        v = state.get(key)
        if isinstance(v, list) and v:
            for item in v:
                if isinstance(item, str) and item.startswith(("http", "data:")):
                    return item
                if isinstance(item, dict):
                    u = _extract_video_url(item)
                    if u: return u
    # Direct top-level fields
    for key in ("video_url", "url", "output_url"):
        v = state.get(key)
        if isinstance(v, str) and v.startswith(("http", "data:")):
            return v
    # Nested under output / result / data
    for k in ("output", "result", "data", "video"):
        nested = state.get(k)
        if isinstance(nested, dict):
            u = _extract_video_url(nested)
            if u: return u
        if isinstance(nested, str) and nested.startswith(("http", "data:")):
            return nested
        if isinstance(nested, list) and nested:
            for item in nested:
                if isinstance(item, dict):
                    u = _extract_video_url(item)
                    if u: return u
                if isinstance(item, str) and item.startswith(("http", "data:")):
                    return item
    return None


def _video_handler_factory(model_id: str) -> Callable[[dict], Any]:
    def _handler(params: dict) -> Any:
        prompt = params.get("prompt") or params.get("text") or params.get("input") or ""
        return _call_video_model(model_id, prompt, slot="video_generates")
    return _handler


def _image_handler_factory(model_id: str, slot: str) -> Callable[[dict], Any]:
    def _handler(params: dict) -> Any:
        prompt = params.get("prompt") or params.get("text") or params.get("input") or ""
        return _call_image_model(model_id, prompt, slot=slot)
    return _handler


def _image_edit_handler_factory(model_id: str, slot: str) -> Callable[[dict], Any]:
    """Edit-slot handler. Takes a source image (and optionally a style
    reference) plus a prompt; routes through the multi-modal chat-completions
    path. ``image_styles`` sends two image blocks (source + style ref);
    ``image_varies`` sends one. The prompt expresses the operation."""
    def _handler(params: dict) -> Any:
        source = params.get("source_image") or params.get("image")
        if source is None:
            raise _capability_error(
                "missing_required_input",
                f"{slot} requires source_image (path, URL, or bytes).",
                slot=slot,
            )
        style_ref = params.get("style_reference")
        if slot == "image_styles":
            prompt = (params.get("prompt") or params.get("instruction")
                      or "Restyle the first image to match the visual style of the second image.")
            if style_ref is not None:
                # Send both source and style as image blocks; the prompt
                # tells the model what to do with them.
                return _call_image_model_two_images(model_id, prompt, source, style_ref, slot=slot)
            # No style ref provided — fall through to single-image varies path
        prompt = (params.get("prompt") or params.get("instruction")
                  or "Generate a creative variation of this image.")
        return _call_image_model(model_id, prompt, slot=slot, source_image=source)
    return _handler


def _call_image_model_two_images(model_id: str, prompt: str,
                                  source: Any, style_ref: Any,
                                  slot: str = "image_styles") -> bytes:
    """Two-image variant for ``image_styles`` — source + style reference.
    Same as ``_call_image_model`` but builds a 3-block content array."""
    key = _resolve_key()
    if not key:
        raise _capability_error("model_unavailable",
                                 "OpenRouter API key not set.", slot=slot)
    try:
        src_url = _image_ref_to_data_url(source)
        sty_url = _image_ref_to_data_url(style_ref)
    except Exception as exc:
        raise _capability_error("missing_required_input",
            f"could not load image refs: {exc}", slot=slot) from exc
    messages = [{
        "role": "user",
        "content": [
            {"type": "text",      "text": prompt},
            {"type": "image_url", "image_url": {"url": src_url}},
            {"type": "image_url", "image_url": {"url": sty_url}},
        ],
    }]
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=_API_BASE)
        def _do(modalities):
            return client.chat.completions.create(
                model=model_id, messages=messages, modalities=modalities,
                extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora"},
            )
        try:
            resp = _do(["image", "text"])
        except Exception as e:
            if "No endpoints found that support the requested output modalities" in str(e):
                resp = _do(["image"])
            else:
                raise
    except Exception as exc:
        raise _classify_openrouter_failure(exc, slot=slot) from exc

    msg = resp.choices[0].message if resp.choices else None
    url = _extract_image_url(msg) if msg else None
    if not url:
        raise _capability_error("prompt_rejected",
            f"OpenRouter returned no image (model {model_id}, two-image input).",
            slot=slot)
    try:
        return _decode_image_url_to_bytes(url)
    except Exception as exc:
        raise _capability_error("model_unavailable",
            f"image decode failed: {exc}", slot=slot) from exc


# Image slots OpenRouter providers can serve.
#   ``image_generates`` + ``image_generates_cartoon``   — text → image
#   ``image_styles`` / ``image_varies``                  — image + text → image
# Skipped:
#   ``image_edits``    — slot contract requires a ``mask`` (DALL-E-style
#                        region edit); OpenRouter models do whole-image
#                        instruction edits, no mask concept. Different
#                        semantics — would need its own slot.
#   ``image_outpaints``/``image_upscales`` — not OpenRouter-native
#                        operations; remain on Replicate / Stability.
_IMAGE_GENERATE_SLOTS = ("image_generates", "image_generates_cartoon")
_IMAGE_EDIT_SLOTS     = ("image_styles", "image_varies")


def register(registry: Any) -> list[str]:
    """Register OpenRouter image/video models as capability providers.

    Returns ``[provider_id, ...]`` of everything registered. Catalog
    misses don't raise — the registration silently no-ops so the rest
    of the capability surface stays available.
    """
    catalog = _load_catalog()
    by_modality = catalog.get("by_modality", {}) or {}
    registered: list[str] = []

    for slot in _IMAGE_GENERATE_SLOTS:
        if not registry.has_slot(slot):
            continue
        for mid in by_modality.get("image", []) or []:
            pid = f"openrouter:{mid}"
            try:
                registry.register_provider(
                    slot, pid, _image_handler_factory(mid, slot))
                if pid not in registered:
                    registered.append(pid)
            except Exception:
                continue

    # Edit-slot registration. Same model list as generation — at call time
    # the model either supports image input (Gemini Image, GPT-image,
    # FLUX 2) or surfaces an upstream "doesn't accept image input" error
    # that the failure classifier turns into ``model_unavailable``, so
    # the cascade walks to the next provider.
    for slot in _IMAGE_EDIT_SLOTS:
        if not registry.has_slot(slot):
            continue
        for mid in by_modality.get("image", []) or []:
            pid = f"openrouter:{mid}"
            try:
                registry.register_provider(
                    slot, pid, _image_edit_handler_factory(mid, slot))
                if pid not in registered:
                    registered.append(pid)
            except Exception:
                continue

    if registry.has_slot("video_generates"):
        for mid in by_modality.get("video", []) or []:
            pid = f"openrouter:{mid}"
            try:
                registry.register_provider("video_generates", pid,
                                            _video_handler_factory(mid))
                registered.append(pid)
            except Exception:
                continue

    return registered
