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
     bytes, and return the bytes — matching the openai / gemini
     handler contract so downstream consumers (msi_image_render,
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

  This is the contract that lets ``image_generates_cartoon`` (an
  explicit publisher-defined cloud-only chain: GPT-5.4 Image 2
  preferred, Google image models catching its moderation refusals,
  gpt-5-image as the deeper fallback) walk past a refusing provider
  instead of silently stopping the cascade.

Video generation uses the same persistent Ora job queue as the other async
capabilities.  The handler returns the queue descriptor immediately; a bounded
worker runs the existing OpenRouter submit/poll/download path and publishes an
owned artifact route when it completes.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time
import urllib.error
from urllib.parse import urljoin, urlsplit
from typing import Any, Callable

try:
    from orchestrator import network_policy
except ImportError:  # pragma: no cover
    import network_policy

_OPENROUTER_CATALOG_PATH = os.path.expanduser("~/ora/config/openrouter-catalog.json")
_API_BASE                = network_policy.OPENROUTER_API_BASE
_OPENROUTER_ORIGIN       = network_policy.OPENROUTER_ORIGIN
_OPENROUTER_IMAGE_TIMEOUT_SECONDS = float(
    os.environ.get("OPENROUTER_IMAGE_TIMEOUT_SECONDS", "120"))
_video_dispatch_context = threading.local()


class _VideoJobCancelled(Exception):
    """The provider or Ora queue ended one video job by cancellation."""

    def __init__(self, message: str, *, remote: bool = False):
        self.remote = remote
        super().__init__(message)

_ASPECT_HINTS = {
    "1:1": (
        "Compose as a square image (1:1 aspect ratio). Fill the square canvas "
        "edge to edge; no letterboxing, no empty margins."
    ),
    "16:9": "Compose as a wide landscape image (16:9 aspect ratio).",
    "9:16": "Compose as a tall portrait image (9:16 aspect ratio).",
    "4:3": "Compose as a landscape image (4:3 aspect ratio).",
    "3:4": "Compose as a portrait image (3:4 aspect ratio).",
}


def _with_image_deadline(callable_):
    timeout = _OPENROUTER_IMAGE_TIMEOUT_SECONDS
    if (
        timeout <= 0
        or not hasattr(signal, "setitimer")
        or threading.current_thread() is not threading.main_thread()
    ):
        return callable_()

    def _raise_timeout(_signum, _frame):
        raise TimeoutError(
            f"OpenRouter image request timed out after {timeout:.0f}s")

    old_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        return callable_()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


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
    safe_msg = network_policy.redact_sensitive_text(msg)[:240]

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
            f"OpenRouter content-policy refusal: {safe_msg}",
            slot=slot,
        )

    # Rate limit / quota → quota_exceeded
    if status == 429 or any(s in msg_lower for s in (
        "rate limit", "rate_limit", "quota", "insufficient_quota",
        "billing", "credits",
    )):
        return _capability_error(
            "quota_exceeded",
            f"OpenRouter quota/rate-limit: {safe_msg}",
            slot=slot,
        )

    # Auth, model-not-found, transport, 5xx → model_unavailable
    if status in (401, 403, 404) or any(s in msg_lower for s in (
        "unauthorized", "forbidden", "not found", "no endpoints found",
        "invalid api key", "model not found",
    )):
        return _capability_error(
            "model_unavailable",
            f"OpenRouter availability error: {safe_msg}",
            slot=slot,
        )

    if (status is not None and 500 <= status < 600) or any(s in msg_lower for s in (
        "timeout", "timed out", "connection", "network",
    )):
        return _capability_error(
            "model_unavailable",
            f"OpenRouter network/5xx: {safe_msg}",
            slot=slot,
        )

    # Unclassified — treat as model_unavailable so the cascade still walks
    # rather than fail-stopping the whole chain on a novel error shape.
    return _capability_error(
        "model_unavailable",
        f"OpenRouter unclassified error: {safe_msg}",
        slot=slot,
    )


def _validate_openrouter_request(request: Any) -> None:
    """httpx request hook: refuse before a bearer can leave the exact origin."""
    network_policy.validate_openrouter_request(request)


@contextmanager
def _openrouter_sdk_client(key: str):
    """Yield the SDK over one no-redirect, exact-origin checked transport."""
    with network_policy.openrouter_sdk_client(
        key, request_validator=_validate_openrouter_request,
    ) as client:
        yield client


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
        try:
            body, _destination = network_policy.urllib_request_bytes(
                url, timeout=60,
            )
            return body
        except Exception as exc:
            # Provider-returned asset URLs are commonly signed.  Never copy a
            # transport exception containing that raw URL into model-visible
            # capability errors.
            raise ValueError(
                f"public image asset fetch failed: {type(exc).__name__}",
            ) from exc

    raise ValueError(f"unsupported image URL scheme: {url[:64]}...")


def _is_exact_openrouter_origin(value: str) -> bool:
    """Recognize only HTTPS URLs on the credential's exact API origin."""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
        trusted = urlsplit(_OPENROUTER_ORIGIN)
        trusted_port = trusted.port
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() == trusted.scheme.casefold()
        and (parsed.hostname or "").rstrip(".").casefold()
        == (trusted.hostname or "").rstrip(".").casefold()
        and (port or 443) == (trusted_port or 443)
        and parsed.username is None
        and parsed.password is None
    )


def _resolve_openrouter_api_url(value: str) -> str:
    """Resolve a provider-relative API URL without expanding authority."""
    if not isinstance(value, str) or not value:
        raise network_policy.NetworkPolicyError(
            "OpenRouter API URL is missing or malformed",
        )
    resolved = urljoin(_API_BASE.rstrip("/") + "/", value)
    if not _is_exact_openrouter_origin(resolved):
        raise network_policy.NetworkPolicyError(
            "OpenRouter API URL is outside its trusted origin",
        )
    return resolved


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


def _append_aspect_hint(prompt: str, aspect_ratio: str | None) -> str:
    hint = _ASPECT_HINTS.get(aspect_ratio or "")
    if not hint or hint in prompt:
        return prompt
    return f"{prompt}. {hint}"


def _call_image_model(model_id: str, prompt: str,
                      slot: str = "image_generates",
                      source_image: Any = None,
                      aspect_ratio: str | None = None) -> bytes:
    """Invoke a chosen OpenRouter image-output model and return raw bytes.

    Returns raw image bytes (PNG/JPEG/WebP) ready for vectorization or
    direct write. Matches the openai/gemini handler contract.

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
    prompt = _append_aspect_hint(prompt, aspect_ratio)

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
        with _openrouter_sdk_client(key) as client:
            def _do(modalities):
                return client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    modalities=modalities,
                    timeout=_OPENROUTER_IMAGE_TIMEOUT_SECONDS,
                    extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora"},
                )
            try:
                resp = _with_image_deadline(lambda: _do(["image", "text"]))
            except Exception as e:
                if "No endpoints found that support the requested output modalities" in str(e):
                    resp = _with_image_deadline(lambda: _do(["image"]))
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
                       slot: str = "video_generates",
                       duration: int | float | None = None,
                       style: str | None = None,
                       resolution: str | None = None,
                       cancel_requested: Callable[[], bool] | None = None,
                       ) -> bytes:
    """Submit an OpenRouter video-generation job and poll until done,
    then fetch the video bytes.

    OpenRouter's video endpoint (``POST /v1/videos``) is async — it
    returns ``{"id":..., "polling_url":..., "status":"pending"}``. The
    polling URL returns the same envelope with ``status`` transitioning
    to ``completed`` and result links in ``unsigned_urls``. Authenticated
    polling is origin-locked to OpenRouter. Results on that same exact origin
    receive the bearer; external/CDN result assets never do.

    Raises ``CapabilityError`` on provider failure and
    ``_VideoJobCancelled`` when provider or local queue cancellation wins.
    Verified end-to-end against ``google/veo-3.1-fast`` (~77s, ~1 MB MP4).
    """
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

    def stop_if_cancelled() -> None:
        if cancel_requested is not None and cancel_requested():
            raise _VideoJobCancelled("Ora video job cancellation requested.")

    # ── Submit job
    stop_if_cancelled()
    try:
        request_body = {"model": model_id, "prompt": prompt}
        for name, value in (
            ("duration", duration),
            ("style", style),
            ("resolution", resolution),
        ):
            if value is not None:
                request_body[name] = value
        body = json.dumps(request_body).encode()
        payload, _destination = network_policy.openrouter_request_bytes(
            _API_BASE + "/videos",
            data=body,
            headers=headers,
            timeout=60,
        )
        job = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise _classify_openrouter_failure(exc, slot=slot) from exc

    raw_poll_url = job.get("polling_url")
    job_id   = job.get("id")
    if not raw_poll_url:
        raise _capability_error("model_unavailable",
            "OpenRouter video submit returned no polling URL.", slot=slot)
    try:
        poll_url = _resolve_openrouter_api_url(raw_poll_url)
    except Exception as exc:
        raise _capability_error(
            "model_unavailable",
            "OpenRouter video submit returned an untrusted polling URL.",
            slot=slot,
        ) from exc

    # ── Poll for completion
    last_state = None
    while time.time() - started < max_wait_s:
        stop_if_cancelled()
        time.sleep(poll_interval_s)
        stop_if_cancelled()
        try:
            payload, _destination = network_policy.openrouter_request_bytes(
                poll_url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=30,
            )
            last_state = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise _classify_openrouter_failure(exc, slot=slot) from exc

        status = (last_state or {}).get("status", "").lower()
        if status in ("completed", "complete", "success", "succeeded"):
            stop_if_cancelled()
            url = _extract_video_url(last_state)
            if not url:
                raise _capability_error("model_unavailable",
                    f"Video job {job_id} completed but no URL was present.",
                    slot=slot)
            # OpenRouter-hosted results require the same bearer as polling.
            # External/CDN results must never receive that credential.
            try:
                if _is_exact_openrouter_origin(url):
                    payload, _destination = (
                        network_policy.openrouter_request_bytes(
                            url,
                            headers={"Authorization": f"Bearer {key}"},
                            timeout=180,
                        )
                    )
                else:
                    payload, _destination = network_policy.urllib_request_bytes(
                        url, timeout=180,
                    )
                stop_if_cancelled()
                return payload
            except _VideoJobCancelled:
                raise
            except Exception as exc:
                raise _capability_error("model_unavailable",
                    "Video fetch failed for "
                    f"{network_policy.safe_url_label(url)}: {type(exc).__name__}",
                    slot=slot) from exc
        if status in ("cancelled", "canceled"):
            raise _VideoJobCancelled(
                f"OpenRouter video job {job_id} was cancelled.",
                remote=True,
            )
        if status in ("failed", "error", "errored", "expired"):
            raise _capability_error("model_unavailable",
                f"OpenRouter video job {job_id} ended with terminal status "
                f"'{status}'.",
                slot=slot)
        # pending / running / queued — continue polling

    raise _capability_error("model_unavailable",
        f"OpenRouter video job {job_id} timed out after {max_wait_s}s.",
        slot=slot)


@contextmanager
def video_conversation(conversation_id: str):
    """Bind one HTTP request's Dialogue to an OpenRouter async dispatch."""
    missing = object()
    previous = getattr(_video_dispatch_context, "conversation_id", missing)
    _video_dispatch_context.conversation_id = conversation_id
    try:
        yield
    finally:
        if previous is missing:
            try:
                del _video_dispatch_context.conversation_id
            except AttributeError:
                pass
        else:
            _video_dispatch_context.conversation_id = previous


def _active_video_conversation() -> str:
    conversation_id = getattr(_video_dispatch_context, "conversation_id", None)
    if not isinstance(conversation_id, str) or not conversation_id:
        raise _capability_error(
            "missing_required_input",
            "OpenRouter video generation requires a bound Dialogue.",
            slot="video_generates",
        )
    return conversation_id


def _video_job_queue():
    """Return the package-qualified singleton used by server job routes."""
    from orchestrator.job_queue import get_default_queue
    return get_default_queue()


def _materialize_video_bytes(
    queue: Any,
    conversation_id: str,
    job_id: str,
    payload: bytes,
) -> dict[str, str]:
    """Store provider bytes under the existing authenticated artifact route."""
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("OpenRouter returned no video bytes.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(job_id or "")):
        raise ValueError("OpenRouter job identity is malformed.")

    from orchestrator import runtime_paths as _rp

    root = Path(getattr(queue, "_root", _rp.ORA_HOME / "sessions"))
    conversation_dir = _rp.safe_owned_subdir(root, conversation_id)
    if not conversation_dir.is_dir() or conversation_dir.is_symlink():
        raise ValueError("OpenRouter output owner is no longer available.")
    uploads = _rp.safe_owned_subdir(conversation_dir, "uploads")
    try:
        uploads.mkdir()
    except FileExistsError:
        pass
    if not uploads.is_dir() or uploads.is_symlink():
        raise ValueError("OpenRouter output directory is unavailable.")

    filename = f"openrouter-{job_id}.mp4"
    _rp.atomic_write_bytes(uploads / filename, bytes(payload))
    return {
        "video_url": (
            f"/api/jobs/{conversation_id}/{job_id}/artifacts/{filename}"
        ),
    }


def _run_video_job(
    queue: Any,
    conversation_id: str,
    job_id: str,
    model_id: str,
    prompt: str,
    duration: int | float | None,
    style: str | None,
    resolution: str | None,
) -> None:
    """Complete one queued OpenRouter job without blocking its HTTP request."""
    try:
        queue.mark_in_progress(conversation_id, job_id)

        def cancellation_requested() -> bool:
            snapshot = queue.get_job(conversation_id, job_id)
            return (
                snapshot.get("status") == "cancelled"
                or bool(snapshot.get("cancel_requested"))
            )

        payload = _call_video_model(
            model_id,
            prompt,
            slot="video_generates",
            duration=duration,
            style=style,
            resolution=resolution,
            cancel_requested=cancellation_requested,
        )
        snapshot = queue.get_job(conversation_id, job_id)
        if (
            snapshot.get("status") == "cancelled"
            or snapshot.get("cancel_requested")
        ):
            if snapshot.get("status") != "cancelled":
                queue.cancel_job(conversation_id, job_id)
            return
        result_ref = _materialize_video_bytes(
            queue, conversation_id, job_id, payload,
        )
        queue.mark_complete(conversation_id, job_id, result_ref)
    except _VideoJobCancelled:
        try:
            snapshot = queue.get_job(conversation_id, job_id)
            if snapshot.get("status") != "cancelled":
                queue.cancel_job(conversation_id, job_id)
        except Exception:
            pass
    except Exception as exc:
        try:
            snapshot = queue.get_job(conversation_id, job_id)
            if snapshot.get("status") in {"complete", "failed", "cancelled"}:
                return
            detail = network_policy.redact_sensitive_text(str(exc))[:500]
            queue.mark_failed(
                conversation_id,
                job_id,
                detail or f"OpenRouter video failure: {type(exc).__name__}",
            )
        except Exception:
            pass


def _start_video_worker(*args: Any) -> None:
    queue, _conversation_id, job_id, model_id, *_rest = args
    worker = threading.Thread(
        target=_run_video_job,
        args=args,
        name=f"openrouter-video-{model_id}-{job_id}",
        daemon=True,
    )
    worker.start()


def _dispatch_video_model(
    model_id: str,
    prompt: str,
    *,
    duration: int | float | None = None,
    style: str | None = None,
    resolution: str | None = None,
) -> dict:
    """Queue the real OpenRouter handler and return its async descriptor."""
    conversation_id = _active_video_conversation()
    if not _resolve_key():
        raise _capability_error(
            "model_unavailable", "OpenRouter API key not set.",
            slot="video_generates",
        )
    if not prompt:
        raise _capability_error(
            "missing_required_input",
            "Video generation requires a non-empty prompt.",
            slot="video_generates",
        )

    parameters = {"prompt": prompt}
    for name, value in (
        ("duration", duration),
        ("style", style),
        ("resolution", resolution),
    ):
        if value is not None:
            parameters[name] = value

    queue = _video_job_queue()
    job = queue.dispatch(
        conversation_id=conversation_id,
        capability="video_generates",
        parameters=parameters,
        metadata={
            "provider": f"openrouter:{model_id}",
            "model": model_id,
        },
    )
    try:
        _start_video_worker(
            queue,
            conversation_id,
            job["id"],
            model_id,
            prompt,
            duration,
            style,
            resolution,
        )
    except Exception as exc:
        try:
            queue.mark_failed(
                conversation_id,
                job["id"],
                f"OpenRouter worker could not start: {type(exc).__name__}",
            )
        finally:
            raise _capability_error(
                "model_unavailable",
                "OpenRouter video worker could not start.",
                slot="video_generates",
            ) from exc
    return job


def _extract_video_url(state: dict) -> str | None:
    """Walk a video-job-complete envelope for the actual video URL.
    The exact field name varies upstream — try several common shapes.

    OpenRouter's observed completion shape carries the result URL in
    ``unsigned_urls`` (a list). External/CDN assets are fetched without the
    OpenRouter bearer; same-origin results receive it. ``signed_urls`` covers
    time-limited public links.
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
        return _dispatch_video_model(
            model_id,
            prompt,
            duration=params.get("duration"),
            style=params.get("style"),
            resolution=params.get("resolution"),
        )
    return _handler


def _image_handler_factory(model_id: str, slot: str) -> Callable[[dict], Any]:
    def _handler(params: dict) -> Any:
        prompt = params.get("prompt") or params.get("text") or params.get("input") or ""
        aspect_ratio = params.get("aspect_ratio") or "1:1"
        return _call_image_model(
            model_id, prompt, slot=slot, aspect_ratio=aspect_ratio)
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
        with _openrouter_sdk_client(key) as client:
            def _do(modalities):
                return client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    modalities=modalities,
                    timeout=_OPENROUTER_IMAGE_TIMEOUT_SECONDS,
                    extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora"},
                )
            try:
                resp = _with_image_deadline(lambda: _do(["image", "text"]))
            except Exception as e:
                if "No endpoints found that support the requested output modalities" in str(e):
                    resp = _with_image_deadline(lambda: _do(["image"]))
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
#   ``image_generates`` + cartoon image slots           — text → image
#   ``image_styles`` / ``image_varies``                  — image + text → image
# Skipped:
#   ``image_edits``    — slot contract requires a ``mask`` (DALL-E-style
#                        region edit); OpenRouter models do whole-image
#                        instruction edits, no mask concept. Different
#                        semantics — would need its own slot.
#   ``image_outpaints``/``image_upscales`` — not OpenRouter-native
#                        operations; remain on Replicate / Stability.
_IMAGE_GENERATE_SLOTS = (
    "image_generates",
    "image_generates_cartoon",
    "image_generates_barb_cartoon",
)
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
