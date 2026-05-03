"""Replicate aggregator integration (WP-7.3.2c).

Replicate is the **long-tail aggregator** in Ora's image-generation
provider chain — it covers slots OpenAI (WP-7.3.2a) and Stability AI
(WP-7.3.2b) don't fulfill: style transfer, image variations,
image-to-prompt captioning, video generation, and style training.

The Replicate API is intentionally generic: every model is reached
through ``POST /v1/predictions`` with a ``version`` (model SHA) and an
``input`` dict. This module wraps that endpoint into per-slot dispatch
functions that take the validated input dict from
``capability_registry.invoke()``, translate it into Replicate's payload
shape, and either:

* poll the prediction synchronously to completion (sync slots:
  ``image_styles``, ``image_varies``, ``image_to_prompt``), or
* file the prediction with the WP-7.6.1 job queue and return the job
  handle immediately (async slots: ``video_generates``, ``style_trains``).

Authentication
--------------

Per §11.13 the API key lives in the macOS Keychain under service-name
``ora-replicate``, account ``api-key``. The acquisition flow (Layer 2 of
``Framework — API Key Acquisition.md``) places the key there. We also
respect the ``REPLICATE_API_TOKEN`` environment variable as a developer
override (used in tests / CI). When the key is missing we surface
``model_unavailable`` per the slot's ``common_errors`` taxonomy — the
slot still registers, it just degrades gracefully and the orchestrator's
'Configure a model in Settings →' UX (per the sibling spec §5) takes
over.

Async layer
-----------

Long-running predictions (video, style training) are filed with
``job_queue.get_default_queue()``. The dispatcher returns the queue's
job dict immediately. A polling thread, started lazily, calls
``replicate.predictions.get()`` until the prediction reaches a terminal
state (``succeeded`` / ``failed`` / ``canceled``), then transitions the
job via ``mark_complete`` or ``mark_failed``.

If the WP-7.6.1 module is not yet on disk when this module loads, the
async dispatchers fall back to a synchronous no-op stub that returns a
TODO marker — the import-time ``_HAS_JOB_QUEUE`` flag flips off, and
WP-7.6.1's completion can wire it up by re-importing this module.

Module-load registration
------------------------

``register_replicate_provider(registry)`` binds the dispatch functions
to their slots. Boot-time code (typically the first orchestrator import)
calls this once. If no API key is configured, registration still
proceeds — invocation will surface ``model_unavailable`` at call time so
the slot remains visible in the catalog.

Default model SHAs
------------------

Replicate models are addressed by an opaque content-addressed SHA. The
SHAs in ``DEFAULT_MODELS`` were the canonical published versions of the
named models at module-authoring time (2026-04-29). Operators can
override them by editing ``~/ora/config/replicate-models.json`` (this
module reads that file on init if present and merges it on top of the
defaults). The choices:

* ``image_styles`` → ``stability-ai/sdxl`` with init-image + style image
  conditioning (a Replicate hosted SDXL variant). Style transfer.
* ``image_varies`` → ``lucataco/sdxl-img2img`` with low strength and a
  re-prompted variation pass. Replicate hosts several image-variation
  pipelines; this one keeps API usage simple (no separate variation
  endpoint needed).
* ``image_to_prompt`` → ``salesforce/blip`` for captioning, with a
  post-processing pass that adapts the caption to the requested
  ``target_style`` (DALL-E vs SD vs MJ vs Flux phrasing).
* ``video_generates`` → ``minimax/video-01`` (text-to-video). Async.
* ``style_trains`` → ``ostris/flux-dev-lora-trainer`` (style adapter
  training). Async.

These are *defaults*. The acquisition flow + Settings UI eventually let
users pick alternatives without code changes.

Test posture
------------

Live network calls are out-of-scope for the unit suite (§13.3 WP-7.3.2
notes: "Live call to each integrated endpoint with a benign payload"
belongs in WP-7.3.5's manual verification, not in `unittest`). The
shipped tests therefore mock ``requests.post`` / ``requests.get`` and
exercise the dispatch + polling logic. A ``--live`` opt-in flag on the
test file gates a single benign live captioning call for the ad-hoc
integration smoke test.

Public API
----------

* ``ReplicateClient`` — generic HTTP client. ``run(model, inputs,
  *, timeout=600)`` for sync completion. ``create(model, inputs)`` +
  ``poll(prediction_id)`` for async control.
* ``dispatch_image_styles(inputs)`` etc. — per-slot dispatchers
  matching the ``capability_registry`` handler signature
  (``handler(inputs: dict) -> Any``).
* ``register_replicate_provider(registry)`` — bind dispatchers to
  slots. Returns the list of slots actually registered.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

# --- Optional dependencies. We fail-soft so a developer machine without
# `keyring` or `requests` can still import this module (the registry
# call surfaces a graceful 'unavailable' error at invocation time
# instead of a hard ImportError at boot).

try:
    import keyring  # type: ignore
    _HAS_KEYRING = True
except Exception:  # pragma: no cover — optional
    keyring = None  # type: ignore
    _HAS_KEYRING = False

try:
    import requests  # type: ignore
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover — optional
    requests = None  # type: ignore
    _HAS_REQUESTS = False

try:
    from orchestrator.job_queue import get_default_queue  # type: ignore
    _HAS_JOB_QUEUE = True
except Exception:
    try:
        # fallback when invoked from inside the orchestrator package
        from job_queue import get_default_queue  # type: ignore
        _HAS_JOB_QUEUE = True
    except Exception:
        get_default_queue = None  # type: ignore
        _HAS_JOB_QUEUE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROVIDER_ID = "replicate"
KEYRING_SERVICE = "ora-replicate"
KEYRING_ACCOUNT = "api-key"
ENV_OVERRIDE = "REPLICATE_API_TOKEN"

API_BASE = "https://api.replicate.com/v1"

# Default Replicate model identifiers per slot.
#
# Note: in the live Replicate API a "model" call usually requires the
# fully-pinned version SHA. We carry a ``model`` (owner/name) slug here
# and resolve to the latest version at call time via the ``GET
# /v1/models/{owner}/{name}`` endpoint. Operators who want a deterministic
# SHA pin override via ``replicate-models.json``.
DEFAULT_MODELS: dict[str, dict] = {
    "image_styles": {
        "model": "stability-ai/sdxl",
        "input_template": {
            "prompt": "in the style of the provided reference image",
            "refine": "no_refiner",
            "num_inference_steps": 25,
        },
    },
    "image_varies": {
        "model": "lucataco/sdxl-img2img",
        "input_template": {
            "prompt": "image variation, slight changes",
            "num_outputs": 1,
        },
    },
    "image_to_prompt": {
        "model": "salesforce/blip",
        "input_template": {"task": "image_captioning"},
    },
    "video_generates": {
        "model": "minimax/video-01",
        "input_template": {},
    },
    "style_trains": {
        "model": "ostris/flux-dev-lora-trainer",
        "input_template": {},
    },
    # Optional fallback fulfillments for §3.1–3.4 if user routes here.
    "image_generates": {
        "model": "stability-ai/sdxl",
        "input_template": {"refine": "no_refiner", "num_inference_steps": 25},
    },
    "image_edits": {
        "model": "stability-ai/sdxl",
        "input_template": {"refine": "no_refiner", "num_inference_steps": 25},
    },
    "image_outpaints": {
        "model": "stability-ai/sdxl",
        "input_template": {"refine": "no_refiner", "num_inference_steps": 25},
    },
    "image_upscales": {
        "model": "nightmareai/real-esrgan",
        "input_template": {"scale": 2.0},
    },
}


# Terminal Replicate prediction states.
_TERMINAL_STATES = {"succeeded", "failed", "canceled"}


# ---------------------------------------------------------------------------
# Errors — translate to capability-registry error taxonomy
# ---------------------------------------------------------------------------

class ReplicateError(Exception):
    """Provider-side failure with a slot-taxonomy-aligned ``code``.

    ``code`` follows the ``common_errors`` declared in
    ``capabilities.json`` so the dispatcher can surface a fix-path UX
    without re-mapping. Common values:

    * ``model_unavailable``  — auth missing, network down.
    * ``quota_exceeded``     — Replicate rate limit hit.
    * ``prompt_rejected``    — content-policy refusal.
    * ``handler_failed``     — anything else.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _resolve_api_key() -> str | None:
    """Return the configured Replicate API key, or ``None``.

    Order: env override → keychain. Returns ``None`` when no key is
    configured (caller surfaces ``model_unavailable``).
    """
    env_key = os.environ.get(ENV_OVERRIDE, "").strip()
    if env_key:
        return env_key
    if _HAS_KEYRING:
        try:
            key = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) or ""
            key = key.strip()
            if key:
                return key
        except Exception:  # pragma: no cover — defensive
            return None
    return None


# ---------------------------------------------------------------------------
# Operator override loader
# ---------------------------------------------------------------------------

_OVERRIDE_PATH = Path(os.path.expanduser("~/ora/config/replicate-models.json"))


def _load_model_overrides() -> dict[str, dict]:
    """Merge ``~/ora/config/replicate-models.json`` over ``DEFAULT_MODELS``.

    The override file is optional; missing or malformed → fall back to
    defaults silently. Operators can override per slot:

    .. code-block:: json

        {
          "image_to_prompt": {
            "model": "andreasjansson/blip-2",
            "version": "<sha>",
            "input_template": {}
          }
        }
    """
    merged = {k: dict(v) for k, v in DEFAULT_MODELS.items()}
    if not _OVERRIDE_PATH.exists():
        return merged
    try:
        with open(_OVERRIDE_PATH) as fh:
            override = json.load(fh)
        for slot, cfg in (override or {}).items():
            if isinstance(cfg, dict):
                if slot in merged:
                    merged[slot].update(cfg)
                else:
                    merged[slot] = cfg
    except Exception as exc:  # pragma: no cover — log + ignore
        print(f"[replicate] override load failed: {exc}")
    return merged


# ---------------------------------------------------------------------------
# Generic HTTP client
# ---------------------------------------------------------------------------

class ReplicateClient:
    """Generic Replicate API client.

    Wraps ``POST /v1/predictions`` (create) + ``GET /v1/predictions/{id}``
    (poll). ``run()`` is the convenient sync wrapper used by sync slots.
    Async slots use ``create()`` directly + the ``job_queue`` polling
    thread.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        api_base: str = API_BASE,
        session: Any = None,
    ):
        self._api_key = api_key or _resolve_api_key()
        self._api_base = api_base.rstrip("/")
        self._session = session  # injection point for tests
        if not self._api_key:
            # Defer the error to call time — the registry can still list
            # the slot, the user just gets a clean 'model_unavailable'
            # when they try to invoke it.
            self._auth_error: ReplicateError | None = ReplicateError(
                "model_unavailable",
                "No Replicate API key configured. Set REPLICATE_API_TOKEN "
                "in env or store via keychain ('ora-replicate' / 'api-key').",
            )
        else:
            self._auth_error = None

    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if self._auth_error:
            raise self._auth_error
        return {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        if not _HAS_REQUESTS:
            raise ReplicateError(
                "model_unavailable",
                "The 'requests' Python package is not installed; cannot reach "
                "the Replicate API. Run `pip install requests`.",
            )
        url = f"{self._api_base}{path}"
        resp = (self._session or requests).post(
            url, headers=self._headers(), json=payload, timeout=60
        )
        return self._raise_or_json(resp)

    def _get(self, path: str) -> dict:
        if not _HAS_REQUESTS:
            raise ReplicateError(
                "model_unavailable",
                "The 'requests' Python package is not installed; cannot reach "
                "the Replicate API.",
            )
        url = f"{self._api_base}{path}"
        resp = (self._session or requests).get(
            url, headers=self._headers(), timeout=60
        )
        return self._raise_or_json(resp)

    @staticmethod
    def _raise_or_json(resp) -> dict:
        try:
            data = resp.json()
        except Exception:
            data = {"raw": getattr(resp, "text", "")}
        status = getattr(resp, "status_code", 0) or 0
        if 200 <= status < 300:
            return data
        # Map HTTP status to our error taxonomy.
        msg = (data or {}).get("detail") or (data or {}).get("error") or str(data)
        if status == 401 or status == 403:
            raise ReplicateError("model_unavailable",
                                 f"Replicate auth failed ({status}): {msg}")
        if status == 429:
            raise ReplicateError("quota_exceeded",
                                 f"Replicate rate limit ({status}): {msg}")
        if status == 422 and "nsfw" in str(msg).lower():
            raise ReplicateError("prompt_rejected",
                                 f"Replicate content policy: {msg}")
        raise ReplicateError("handler_failed",
                             f"Replicate API {status}: {msg}")

    # ------------------------------------------------------------------

    def resolve_version(self, model_slug: str, *, fallback_version: str | None = None) -> str:
        """Resolve ``owner/name`` to the latest version SHA.

        Replicate's prediction API requires the version SHA, not the
        slug. The ``GET /v1/models/{owner}/{name}`` endpoint returns the
        ``latest_version.id`` we want. ``fallback_version`` is used when
        the lookup fails (e.g., flaky network) so we degrade rather than
        die.
        """
        try:
            data = self._get(f"/models/{model_slug}")
            latest = (data or {}).get("latest_version") or {}
            ver = latest.get("id")
            if ver:
                return ver
        except ReplicateError:
            if fallback_version:
                return fallback_version
            raise
        if fallback_version:
            return fallback_version
        raise ReplicateError(
            "model_unavailable",
            f"Could not resolve version for Replicate model '{model_slug}'.",
        )

    def create(self, version: str, inputs: dict) -> dict:
        """Create a prediction. Returns the raw Replicate prediction
        dict (with ``id``, ``status``, ``urls`` etc.)."""
        return self._post("/predictions",
                          {"version": version, "input": inputs})

    def poll(self, prediction_id: str) -> dict:
        return self._get(f"/predictions/{prediction_id}")

    def cancel(self, prediction_id: str) -> dict:
        return self._post(f"/predictions/{prediction_id}/cancel", {})

    # ------------------------------------------------------------------

    def run(
        self,
        model_slug: str,
        inputs: dict,
        *,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
        version: str | None = None,
    ) -> dict:
        """Sync convenience: create + poll until terminal.

        Returns the final prediction dict. Raises ``ReplicateError`` on
        failure / timeout.
        """
        ver = version or self.resolve_version(model_slug)
        prediction = self.create(ver, inputs)
        deadline = time.time() + timeout
        while prediction.get("status") not in _TERMINAL_STATES:
            if time.time() > deadline:
                # Best-effort cancel; ignore errors so the timeout is
                # what the caller sees.
                try:
                    self.cancel(prediction["id"])
                except Exception:
                    pass
                raise ReplicateError(
                    "handler_failed",
                    f"Replicate prediction timed out after {timeout}s "
                    f"for model '{model_slug}'.",
                )
            time.sleep(poll_interval)
            prediction = self.poll(prediction["id"])
        if prediction.get("status") == "failed":
            raise ReplicateError(
                "handler_failed",
                f"Replicate prediction failed: {prediction.get('error')}",
            )
        if prediction.get("status") == "canceled":
            raise ReplicateError(
                "handler_failed",
                "Replicate prediction was canceled.",
            )
        return prediction


# ---------------------------------------------------------------------------
# Per-slot dispatchers
# ---------------------------------------------------------------------------

def _normalize_image_ref(ref: Any) -> str | None:
    """Best-effort coerce a canvas image-ref into something Replicate
    accepts (a URL or a base64 data URI).

    The full WP-7.5.1 selection model defines a richer image-ref shape
    (object id, layer, bbox). For the WP-7.3.2c slice we accept:

    * ``str`` — a URL or data URI: passed through.
    * ``dict`` with ``url`` key — passed through.
    * ``dict`` with ``data`` key (base64) — wrapped as a data URI.
    * ``dict`` with ``path`` key — read from disk and base64-encoded.
    * anything else — best-effort ``str()``.
    """
    if ref is None:
        return None
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        if "url" in ref:
            return ref["url"]
        if "data" in ref:
            mime = ref.get("mime", "image/png")
            return f"data:{mime};base64,{ref['data']}"
        if "path" in ref:
            try:
                import base64
                p = Path(os.path.expanduser(str(ref["path"])))
                with open(p, "rb") as fh:
                    encoded = base64.b64encode(fh.read()).decode("ascii")
                mime = ref.get("mime", "image/png")
                return f"data:{mime};base64,{encoded}"
            except Exception as exc:
                raise ReplicateError(
                    "handler_failed",
                    f"Could not read image from path '{ref['path']}': {exc}",
                )
    return str(ref)


def _client_for_model(slot: str) -> tuple[ReplicateClient, dict]:
    """Resolve the ``(client, slot_config)`` pair for ``slot``.

    The slot config is the merged DEFAULT_MODELS + override entry.
    """
    overrides = _load_model_overrides()
    cfg = overrides.get(slot)
    if not cfg:
        raise ReplicateError(
            "model_unavailable",
            f"No Replicate model configured for slot '{slot}'.",
        )
    client = ReplicateClient()
    return client, cfg


def _build_inputs(slot_cfg: dict, **overrides: Any) -> dict:
    """Merge overrides over the slot's input template."""
    inputs = dict(slot_cfg.get("input_template", {}))
    for k, v in overrides.items():
        if v is not None:
            inputs[k] = v
    return inputs


# --- §3.5 image_styles -------------------------------------------------

def dispatch_image_styles(inputs: dict) -> dict:
    """Apply the ``style_reference`` style to ``source_image``.

    Sync. Returns ``{'image_url': ..., 'image_data_uri': ...}`` —
    the canvas insertion logic in WP-7.3.3e renders whichever it gets.
    """
    client, cfg = _client_for_model("image_styles")
    source = _normalize_image_ref(inputs.get("source_image"))
    style = _normalize_image_ref(inputs.get("style_reference"))
    strength = inputs.get("strength", 0.75)
    payload = _build_inputs(
        cfg,
        image=source,
        style_image=style,
        prompt_strength=float(strength),
    )
    pred = client.run(cfg["model"], payload, version=cfg.get("version"))
    return _extract_first_image(pred)


# --- §3.6 image_varies (fallback for §3.6) -----------------------------

def dispatch_image_varies(inputs: dict) -> list[dict]:
    """Generate variations of ``source_image``.

    Replicate is a fallback for §3.6 — DALL-E 2 is the OpenAI-side
    primary. Returns a list of ``{'image_url': ...}`` dicts.
    """
    client, cfg = _client_for_model("image_varies")
    source = _normalize_image_ref(inputs.get("source_image"))
    count = int(inputs.get("count") or 4)
    variation_strength = float(inputs.get("variation_strength") or 0.5)
    results = []
    for _ in range(max(1, count)):
        payload = _build_inputs(
            cfg,
            image=source,
            prompt_strength=variation_strength,
        )
        pred = client.run(cfg["model"], payload, version=cfg.get("version"))
        results.append(_extract_first_image(pred))
    return results


# --- §3.7 image_to_prompt ---------------------------------------------

def dispatch_image_to_prompt(inputs: dict) -> str:
    """Caption ``image`` and adapt to ``target_style`` phrasing.

    Sync. Uses BLIP for the base caption; appends a tail string
    appropriate to the target prompt style so the user can paste into
    DALL-E / SD / MJ / Flux directly.
    """
    client, cfg = _client_for_model("image_to_prompt")
    image = _normalize_image_ref(inputs.get("image"))
    target_style = inputs.get("target_style") or "dalle"
    payload = _build_inputs(cfg, image=image)
    pred = client.run(cfg["model"], payload, version=cfg.get("version"))
    caption = _extract_text(pred)
    return _adapt_caption_for_style(caption, target_style)


def _adapt_caption_for_style(caption: str, target_style: str) -> str:
    """Adapt a base caption to the requested prompt-style flavor.

    The flavor tail is short on purpose — over-engineering this in code
    is a trap; the user can refine in the chat. We just nudge each
    target's idiomatic terminology.
    """
    base = caption.strip()
    suffix_map = {
        "dalle": "",
        "sd": ", highly detailed, masterpiece, 8k, hyperrealistic",
        "mj": " --ar 16:9 --v 6 --style raw",
        "flux": ", cinematic lighting, ultra-realistic",
    }
    return base + suffix_map.get(target_style, "")


# --- §3.9 video_generates (async) -------------------------------------

def dispatch_video_generates(inputs: dict) -> dict:
    """Async dispatcher for video generation.

    Files the prediction with the WP-7.6.1 job queue and returns the
    queue's job dict. A polling thread transitions the job from
    ``queued`` → ``in_progress`` → ``complete``/``failed``.

    When WP-7.6.1's ``job_queue`` module is not present at import time
    (parallel WP), we surface a stub job dict carrying a ``TODO_*`` flag
    so the dispatcher can wire it up after the fact.
    """
    client, cfg = _client_for_model("video_generates")
    prompt = inputs.get("prompt")
    payload = _build_inputs(
        cfg,
        prompt=prompt,
        duration=inputs.get("duration"),
        style=inputs.get("style"),
        resolution=inputs.get("resolution"),
    )
    return _async_dispatch(
        slot="video_generates",
        client=client,
        cfg=cfg,
        payload=payload,
        parameters_for_queue=dict(inputs),
    )


# --- §3.10 style_trains (async) ---------------------------------------

def dispatch_style_trains(inputs: dict) -> dict:
    """Async dispatcher for style adapter training.

    Same shape as ``dispatch_video_generates`` — files a prediction +
    polls for completion. The successful result_ref is the trained
    style adapter id; WP-7.5.x registers it in ``image_styles``.
    """
    client, cfg = _client_for_model("style_trains")
    refs = inputs.get("reference_images") or []
    if len(refs) < 3:
        raise ReplicateError(
            "insufficient_examples",
            f"style_trains requires ≥3 reference images, got {len(refs)}.",
        )
    normalized_refs = [_normalize_image_ref(r) for r in refs]
    payload = _build_inputs(
        cfg,
        input_images=normalized_refs,
        trigger_word=inputs.get("name"),
        training_depth=inputs.get("training_depth"),
    )
    return _async_dispatch(
        slot="style_trains",
        client=client,
        cfg=cfg,
        payload=payload,
        parameters_for_queue=dict(inputs),
    )


# ---------------------------------------------------------------------------
# Async-dispatch helper + polling thread
# ---------------------------------------------------------------------------

# Conversation id is set per-thread by the dispatcher layer (boot.py / the
# capability-registry caller). We read it lazily; if it is not set we use
# a synthetic 'default' bucket so the queue still has a home for the job.
_thread_local = threading.local()


def set_active_conversation(conversation_id: str) -> None:
    """Set the conversation id the dispatcher thread should file
    queue jobs under. Called once per request by the orchestrator
    before invoking an async slot."""
    _thread_local.conversation_id = conversation_id


def _active_conversation() -> str:
    return getattr(_thread_local, "conversation_id", "default")


def _async_dispatch(
    *,
    slot: str,
    client: ReplicateClient,
    cfg: dict,
    payload: dict,
    parameters_for_queue: dict,
) -> dict:
    """Common async-dispatch path used by both video_generates and
    style_trains.

    Behavior:

    * If the WP-7.6.1 queue is present, file a queued job, kick off the
      polling thread, return the job dict (the dispatcher renders
      placeholders + chat-bridge entries from this).
    * If the queue is absent (parallel WP not yet landed), return a
      stub dict with ``stub: true`` and a ``TODO`` note. The capability
      registry surfaces this to the caller verbatim and the job-queue
      WP can wire it after the fact.
    """
    if not _HAS_JOB_QUEUE or get_default_queue is None:
        # TODO(WP-7.6.1): once job_queue lands, remove this stub branch
        # and the regular `_HAS_JOB_QUEUE` path will take over.
        return {
            "stub": True,
            "TODO": "WP-7.6.1 job_queue not present at import time; "
                    "async dispatch is unwired. Re-import this module after "
                    "job_queue.py is on disk to enable proper async dispatch.",
            "slot": slot,
            "would_have_dispatched": {
                "model": cfg["model"],
                "input": payload,
            },
        }

    queue = get_default_queue()
    conversation_id = _active_conversation()
    job = queue.dispatch(
        conversation_id=conversation_id,
        capability=slot,
        parameters=parameters_for_queue,
        metadata={"provider": PROVIDER_ID, "model": cfg["model"]},
    )
    # Kick off prediction creation + polling on a background thread so
    # the dispatch call returns immediately. Failures during creation
    # transition the job to ``failed`` directly.
    t = threading.Thread(
        target=_poll_thread,
        args=(client, cfg, payload, conversation_id, job["id"]),
        name=f"replicate-{slot}-{job['id']}",
        daemon=True,
    )
    t.start()
    return job


def _poll_thread(
    client: ReplicateClient,
    cfg: dict,
    payload: dict,
    conversation_id: str,
    job_id: str,
) -> None:
    """Background polling for a Replicate prediction tied to a
    queue job. Transitions the job to terminal status when the
    prediction reaches ``succeeded`` / ``failed`` / ``canceled``."""
    queue = get_default_queue()
    try:
        version = cfg.get("version") or client.resolve_version(cfg["model"])
        pred = client.create(version, payload)
        queue.mark_in_progress(conversation_id, job_id)
        # Long polling — async slots are minutes-scale.
        deadline = time.time() + 60 * 60  # 1h hard cap.
        while pred.get("status") not in _TERMINAL_STATES:
            if time.time() > deadline:
                queue.mark_failed(
                    conversation_id, job_id,
                    "Replicate prediction exceeded 1h hard cap.",
                )
                return
            # Honor cancellation requests from WP-7.6.3.
            try:
                snap = queue.get_job(conversation_id, job_id)
                if snap.get("cancel_requested"):
                    try:
                        client.cancel(pred["id"])
                    except Exception:
                        pass
                    queue.cancel_job(conversation_id, job_id)
                    return
            except Exception:
                pass
            time.sleep(2.0)
            pred = client.poll(pred["id"])
        if pred.get("status") == "succeeded":
            result_ref = _extract_async_result(pred)
            queue.mark_complete(conversation_id, job_id, result_ref)
        else:
            queue.mark_failed(
                conversation_id, job_id,
                f"Replicate prediction {pred.get('status')}: "
                f"{pred.get('error') or 'no detail'}",
            )
    except ReplicateError as exc:
        try:
            queue.mark_failed(conversation_id, job_id, str(exc))
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover — defensive
        try:
            queue.mark_failed(conversation_id, job_id, f"Unexpected: {exc}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Result extraction helpers — Replicate output shapes vary per model
# ---------------------------------------------------------------------------

def _extract_first_image(prediction: dict) -> dict:
    """Pull the first image URL out of a Replicate prediction.

    Replicate models commonly return ``output`` as either a single URL
    string or a list of URL strings. We normalise to ``{'image_url':
    str}``.
    """
    out = prediction.get("output")
    if isinstance(out, str):
        return {"image_url": out}
    if isinstance(out, list) and out:
        first = out[0]
        if isinstance(first, str):
            return {"image_url": first}
        if isinstance(first, dict) and first.get("url"):
            return {"image_url": first["url"]}
    raise ReplicateError(
        "handler_failed",
        f"Could not parse image output from Replicate prediction; "
        f"output shape: {type(out).__name__}",
    )


def _extract_text(prediction: dict) -> str:
    """Pull a text string out of a Replicate prediction.

    BLIP and other captioning models return a string or list-of-string
    under ``output``.
    """
    out = prediction.get("output")
    if isinstance(out, str):
        return out
    if isinstance(out, list) and out:
        if isinstance(out[0], str):
            return " ".join(str(x) for x in out)
    raise ReplicateError(
        "handler_failed",
        f"Could not parse text output from Replicate prediction; "
        f"output shape: {type(out).__name__}",
    )


def _extract_async_result(prediction: dict) -> Any:
    """Pull a generic result_ref from a successful async prediction.

    Video → ``{'video_url': str}``. Style training → either an
    adapter id or a model-version id Replicate exposes. We pass
    through whatever ``output`` is — downstream WP-7.6.2 renders it.
    """
    out = prediction.get("output")
    return out


# ---------------------------------------------------------------------------
# Module-load registration
# ---------------------------------------------------------------------------

# Map slot name → dispatcher. Order matters only for documentation —
# registration is independent per slot.
_SLOT_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "image_styles":     dispatch_image_styles,
    "image_varies":     dispatch_image_varies,
    "image_to_prompt":  dispatch_image_to_prompt,
    "video_generates":  dispatch_video_generates,
    "style_trains":     dispatch_style_trains,
}


def register_replicate_provider(registry: Any) -> list[str]:
    """Register Replicate as a provider for its supported slots.

    Returns the list of slot names actually registered. We register
    even when the API key is missing — the slot stays visible in the
    catalog and the user gets a clean ``model_unavailable`` at call
    time, which is the documented UX (sibling spec §5).
    """
    registered: list[str] = []
    for slot_name, handler in _SLOT_HANDLERS.items():
        if not registry.has_slot(slot_name):
            # Slot not declared in capabilities.json — skip silently.
            continue
        registry.register_provider(slot_name, PROVIDER_ID, handler)
        registered.append(slot_name)
    return registered
