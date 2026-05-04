"""Local diffusers image-generation integration (local-first default).

Fulfills the six synthesis slots — ``image_generates``, ``image_edits``,
``image_outpaints``, ``image_upscales``, ``image_styles``,
``image_varies`` — entirely on the user's machine with no API
dependency, by driving the Hugging Face ``diffusers`` library against
the Stable Diffusion 1.5 weights.

Why SD 1.5
----------
SD 1.5 is the universal-portability default for Ora because it:

  * Runs on Apple Silicon (MPS), NVIDIA (CUDA), AMD ROCm, and CPU via
    the same Python code path — no per-platform branches.
  * Has the smallest weight footprint of any current open generator
    (~4 GB), so the first-run download finishes in minutes rather than
    tens of minutes.
  * Carries a permissive open license (CreativeML OpenRAIL-M) — no
    Hugging Face login required, no commercial-use restriction, no
    user-account friction at install.

Users with strong hardware can swap to SDXL, SD3, Flux, or any other
diffusers-compatible checkpoint by setting the ``ORA_DIFFUSERS_MODEL``
environment variable to a Hugging Face model id (e.g.,
``stabilityai/stable-diffusion-xl-base-1.0``); the dispatchers below
honor that override.

Lazy weight download
--------------------
Weights are not pulled at install time. The first call to any
dispatcher triggers a one-time download to ``~/ora/models/diffusers/``
(overridable via ``ORA_DIFFUSERS_CACHE``). Subsequent calls hit the
local cache. The first call therefore takes 5–10 minutes on a typical
home connection; every call after that is millisecond-cold.

Lazy library import
-------------------
``diffusers`` and ``torch`` are imported inside each dispatcher (not at
module load), so the server starts cleanly on machines without those
packages installed. When a dispatcher is called and the libraries are
missing, ``CapabilityError(model_unavailable)`` carries an installation
hint matching the ``common_errors`` taxonomy in capabilities.json.

Provider id
-----------
``local-diffusers``. This is the string Ora records in
``routing-config.json``'s ``slots.<slot>.preferred`` /
``slots.<slot>.fallback`` lists, and the same string passed to
``capability_registry.register_provider`` below.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

# capability_registry is the sibling module under ~/ora/orchestrator/.
# Import is by module name (orchestrator/ is on the path when boot.py
# or the test harness loads this file).
from capability_registry import CapabilityError, CapabilityRegistry, load_registry


# ---------------------------------------------------------------------------
# Provider identifier — the string recorded in routing-config.json's
# slots.<slot>.preferred / .fallback fields.
# ---------------------------------------------------------------------------

PROVIDER_ID = "local-diffusers"

# Default model id. Users override via $ORA_DIFFUSERS_MODEL with any
# Hugging Face model id whose pipeline class matches the slot
# (StableDiffusionPipeline / StableDiffusionImg2ImgPipeline /
# StableDiffusionInpaintPipeline / StableDiffusionUpscalePipeline).
DEFAULT_MODEL_ID = "runwayml/stable-diffusion-v1-5"
DEFAULT_UPSCALE_MODEL_ID = "stabilityai/stable-diffusion-x4-upscaler"

# Cache root — all downloaded weights live here. Overridable via env so
# multi-user installs and dev environments can isolate.
DEFAULT_CACHE_DIR = Path.home() / "ora" / "models" / "diffusers"

# Native resolution of SD 1.5. Generating at higher resolutions is
# possible but quality degrades; the aspect-ratio table below picks
# dimensions that stay close to 512²-equivalent pixel counts and remain
# multiples of 8 (a U-Net stride requirement).
_ASPECT_TO_DIMENSIONS = {
    "1:1":  (512, 512),
    "16:9": (768, 432),
    "9:16": (432, 768),
    "4:3":  (640, 480),
    "3:4":  (480, 640),
}


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _model_id() -> str:
    return os.environ.get("ORA_DIFFUSERS_MODEL", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID


def _upscale_model_id() -> str:
    return os.environ.get("ORA_DIFFUSERS_UPSCALE_MODEL", DEFAULT_UPSCALE_MODEL_ID).strip() or DEFAULT_UPSCALE_MODEL_ID


def _cache_dir() -> str:
    override = os.environ.get("ORA_DIFFUSERS_CACHE", "").strip()
    target = Path(override) if override else DEFAULT_CACHE_DIR
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


def _resolve_device():
    """Pick the best available torch device — MPS on Apple, CUDA on
    NVIDIA, CPU otherwise. Imported lazily so a missing torch doesn't
    crash module load."""
    import torch  # type: ignore

    if torch.cuda.is_available():
        return "cuda"
    # mps_is_available is the Apple Silicon backend; only present on
    # PyTorch ≥ 1.12 with macOS ≥ 12.3. ``hasattr`` guard keeps older
    # torch builds from raising AttributeError.
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _resolve_torch_dtype(device: str):
    """Half precision on accelerators (matches diffusers' recommended
    default for SD 1.5) and full precision on CPU (where fp16 is slow
    and lossy on most CPU kernels)."""
    import torch  # type: ignore

    return torch.float16 if device in ("cuda", "mps") else torch.float32


# ---------------------------------------------------------------------------
# Pipeline cache — load weights once per process, reuse across calls.
# Keyed by (pipeline_class_name, model_id) so a runtime swap to SDXL
# doesn't collide with the SD 1.5 cache, and switching slots reuses the
# underlying VAE/UNet via diffusers' shared component cache.
# ---------------------------------------------------------------------------

_pipeline_cache: dict[tuple[str, str], Any] = {}


def _load_pipeline(pipeline_class_name: str, *, model_id: str | None = None):
    """Load (or return a cached) diffusers pipeline.

    ``pipeline_class_name`` is one of ``"StableDiffusionPipeline"``,
    ``"StableDiffusionImg2ImgPipeline"``,
    ``"StableDiffusionInpaintPipeline"``, ``"StableDiffusionUpscalePipeline"``.
    First call downloads weights to ``_cache_dir()``; subsequent calls
    are instant.
    """
    target_model = model_id or _model_id()
    if pipeline_class_name == "StableDiffusionUpscalePipeline":
        target_model = model_id or _upscale_model_id()

    cache_key = (pipeline_class_name, target_model)
    cached = _pipeline_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        import diffusers  # type: ignore
    except ImportError as exc:
        raise CapabilityError(
            "model_unavailable",
            "diffusers / torch not installed. Run: "
            "pip install diffusers transformers accelerate safetensors torch",
        ) from exc

    pipeline_cls = getattr(diffusers, pipeline_class_name, None)
    if pipeline_cls is None:
        raise CapabilityError(
            "model_unavailable",
            f"diffusers package missing pipeline class '{pipeline_class_name}' "
            f"— upgrade with 'pip install --upgrade diffusers'.",
        )

    device = _resolve_device()
    dtype = _resolve_torch_dtype(device)

    try:
        pipeline = pipeline_cls.from_pretrained(
            target_model,
            torch_dtype=dtype,
            cache_dir=_cache_dir(),
            # Disable the safety checker. Local-first means the user
            # owns the prompts, the outputs, and the moral judgment;
            # the SD 1.5 default safety checker has a high false-
            # positive rate on legitimate creative work and produces
            # all-black returns that look like a generation failure.
            safety_checker=None,
            requires_safety_checker=False,
        )
    except Exception as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Failed to load diffusers model '{target_model}': {exc}",
        ) from exc

    try:
        pipeline = pipeline.to(device)
    except Exception:
        # Some pipelines (or some torch builds) don't support .to()
        # for every device combo. Fall back to whatever device the
        # pipeline initialized on.
        pass

    _pipeline_cache[cache_key] = pipeline
    return pipeline


# ---------------------------------------------------------------------------
# Image-bytes coercion (mirrors openai_images._coerce_to_png_bytes).
# ---------------------------------------------------------------------------

def _coerce_to_bytes(value: Any, *, field_name: str, slot: str) -> bytes:
    """Accept bytes, a file-like, or a path string; return bytes."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if hasattr(value, "read"):
        return value.read()
    if isinstance(value, str) and os.path.exists(value):
        with open(value, "rb") as f:
            return f.read()
    raise CapabilityError(
        "missing_required_input",
        f"{slot} {field_name} must be bytes, a file-like object, or a path "
        f"to an existing file (got {type(value).__name__}).",
        slot=slot,
    )


def _bytes_to_pil(image_bytes: bytes):
    """Decode bytes → PIL.Image, lazy-importing PIL."""
    from PIL import Image  # type: ignore

    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def _pil_to_png_bytes(image) -> bytes:
    """Encode a PIL Image as PNG bytes."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _aspect_dimensions(aspect_ratio: str | None) -> tuple[int, int]:
    return _ASPECT_TO_DIMENSIONS.get(aspect_ratio or "1:1", _ASPECT_TO_DIMENSIONS["1:1"])


# ---------------------------------------------------------------------------
# image_generates — txt2img
# ---------------------------------------------------------------------------

def dispatch_image_generates(inputs: dict) -> bytes:
    """Fulfill ``image_generates`` (capabilities.json §3.1) via diffusers
    text-to-image. Returns PNG bytes."""
    prompt = inputs.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise CapabilityError(
            "missing_required_input",
            "image_generates requires a non-empty 'prompt' string.",
            slot="image_generates",
        )

    style_hint = inputs.get("style")
    if style_hint and isinstance(style_hint, str) and style_hint.strip():
        composed = f"{prompt.strip()}, in the style of {style_hint.strip()}"
    else:
        composed = prompt.strip()

    width, height = _aspect_dimensions(inputs.get("aspect_ratio"))
    pipeline = _load_pipeline("StableDiffusionPipeline")

    try:
        result = pipeline(
            composed,
            width=width,
            height=height,
            num_inference_steps=30,
            guidance_scale=7.5,
        )
    except Exception as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Local diffusers image_generates failed: {exc}",
            slot="image_generates",
        ) from exc

    images = getattr(result, "images", None) or []
    if not images:
        raise CapabilityError(
            "model_unavailable",
            "Local diffusers returned no image for image_generates.",
            slot="image_generates",
        )
    return _pil_to_png_bytes(images[0])


# ---------------------------------------------------------------------------
# image_edits — inpaint
# ---------------------------------------------------------------------------

def dispatch_image_edits(inputs: dict) -> bytes:
    """Fulfill ``image_edits`` (capabilities.json §3.2) via diffusers
    inpainting pipeline. Returns PNG bytes."""
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

    image_bytes = _coerce_to_bytes(raw_image, field_name="'image'", slot="image_edits")
    mask_bytes = _coerce_to_bytes(raw_mask, field_name="'mask'", slot="image_edits")
    image_pil = _bytes_to_pil(image_bytes)
    mask_pil = _bytes_to_pil(mask_bytes)

    strength = inputs.get("strength")
    try:
        strength_f = float(strength) if strength is not None else 0.75
    except (TypeError, ValueError):
        strength_f = 0.75
    strength_f = max(0.0, min(1.0, strength_f))

    pipeline = _load_pipeline("StableDiffusionInpaintPipeline")

    try:
        result = pipeline(
            prompt=prompt.strip(),
            image=image_pil,
            mask_image=mask_pil,
            strength=strength_f,
            num_inference_steps=30,
            guidance_scale=7.5,
        )
    except Exception as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Local diffusers image_edits failed: {exc}",
            slot="image_edits",
        ) from exc

    images = getattr(result, "images", None) or []
    if not images:
        raise CapabilityError(
            "model_unavailable",
            "Local diffusers returned no image for image_edits.",
            slot="image_edits",
        )
    return _pil_to_png_bytes(images[0])


# ---------------------------------------------------------------------------
# image_outpaints — extend canvas via inpaint on a padded image
# ---------------------------------------------------------------------------

def _build_outpaint_canvas(image_pil, directions: list[str]):
    """Pad ``image_pil`` outward in each requested direction and build a
    matching mask whose white region is the new (to-be-filled) area.

    Padding amount is half the relevant dimension on each chosen side
    (matching common open-source outpaint workflows). Returns
    (padded_image, mask, (new_w, new_h))."""
    from PIL import Image  # type: ignore

    w, h = image_pil.size
    pad_w = max(64, w // 2)
    pad_h = max(64, h // 2)

    pad_left = pad_w if "left" in directions else 0
    pad_right = pad_w if "right" in directions else 0
    pad_top = pad_h if "top" in directions else 0
    pad_bottom = pad_h if "bottom" in directions else 0

    new_w = w + pad_left + pad_right
    new_h = h + pad_top + pad_bottom

    canvas = Image.new("RGB", (new_w, new_h), (0, 0, 0))
    canvas.paste(image_pil, (pad_left, pad_top))

    # White = inpaint here; black = preserve. So the mask is white
    # everywhere EXCEPT the original-image rectangle.
    mask = Image.new("L", (new_w, new_h), 255)
    keep_box = Image.new("L", (w, h), 0)
    mask.paste(keep_box, (pad_left, pad_top))

    return canvas, mask, (new_w, new_h)


def dispatch_image_outpaints(inputs: dict) -> bytes:
    """Fulfill ``image_outpaints`` (capabilities.json §3.3) by padding
    the source image and running the inpaint pipeline over the new
    region. Returns PNG bytes of the extended image."""
    raw_image = inputs.get("image")
    directions = inputs.get("directions") or []
    prompt = inputs.get("prompt")

    if not raw_image:
        raise CapabilityError(
            "missing_required_input",
            "image_outpaints requires an 'image' (image-ref).",
            slot="image_outpaints",
        )
    if not isinstance(directions, (list, tuple)) or not directions:
        raise CapabilityError(
            "direction_invalid",
            "image_outpaints requires at least one direction "
            "(top / bottom / left / right).",
            slot="image_outpaints",
        )
    valid = {"top", "bottom", "left", "right"}
    bad = [d for d in directions if d not in valid]
    if bad:
        raise CapabilityError(
            "direction_invalid",
            f"image_outpaints got invalid direction(s) {bad!r}. "
            "Use any of: top / bottom / left / right.",
            slot="image_outpaints",
        )
    if not isinstance(prompt, str) or not prompt.strip():
        raise CapabilityError(
            "missing_required_input",
            "image_outpaints requires a non-empty 'prompt' string.",
            slot="image_outpaints",
        )

    image_bytes = _coerce_to_bytes(raw_image, field_name="'image'", slot="image_outpaints")
    image_pil = _bytes_to_pil(image_bytes)
    canvas, mask, _ = _build_outpaint_canvas(image_pil, list(directions))

    pipeline = _load_pipeline("StableDiffusionInpaintPipeline")

    try:
        result = pipeline(
            prompt=prompt.strip(),
            image=canvas,
            mask_image=mask,
            num_inference_steps=30,
            guidance_scale=7.5,
        )
    except Exception as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Local diffusers image_outpaints failed: {exc}",
            slot="image_outpaints",
        ) from exc

    images = getattr(result, "images", None) or []
    if not images:
        raise CapabilityError(
            "model_unavailable",
            "Local diffusers returned no image for image_outpaints.",
            slot="image_outpaints",
        )
    return _pil_to_png_bytes(images[0])


# ---------------------------------------------------------------------------
# image_upscales — diffusion-based super-resolution
# ---------------------------------------------------------------------------

def dispatch_image_upscales(inputs: dict) -> bytes:
    """Fulfill ``image_upscales`` (capabilities.json §3.4) using
    diffusers' StableDiffusionUpscalePipeline (default model:
    stabilityai/stable-diffusion-x4-upscaler — 4× super-resolution).
    Returns PNG bytes."""
    raw_image = inputs.get("image")
    if not raw_image:
        raise CapabilityError(
            "missing_required_input",
            "image_upscales requires an 'image' (image-ref).",
            slot="image_upscales",
        )

    image_bytes = _coerce_to_bytes(raw_image, field_name="'image'", slot="image_upscales")
    image_pil = _bytes_to_pil(image_bytes)

    # The x4 upscaler accepts a guiding prompt; the slot contract
    # doesn't surface one, so we use a neutral default that lets the
    # model stay faithful to the source.
    pipeline = _load_pipeline("StableDiffusionUpscalePipeline")

    try:
        result = pipeline(
            prompt="a high quality photograph",
            image=image_pil,
            num_inference_steps=30,
        )
    except Exception as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Local diffusers image_upscales failed: {exc}",
            slot="image_upscales",
        ) from exc

    images = getattr(result, "images", None) or []
    if not images:
        raise CapabilityError(
            "model_unavailable",
            "Local diffusers returned no image for image_upscales.",
            slot="image_upscales",
        )
    return _pil_to_png_bytes(images[0])


# ---------------------------------------------------------------------------
# image_styles — img2img with a style-reference prompt construction
# ---------------------------------------------------------------------------

def dispatch_image_styles(inputs: dict) -> bytes:
    """Fulfill ``image_styles`` (capabilities.json §3.5) via img2img.

    The contract gives us a source image and a style-reference image.
    SD 1.5 doesn't have a native dual-image style transfer mode, so we
    approximate: img2img on the source with a strength derived from the
    user's strength input and a prompt that encodes the style intent.
    For higher fidelity style transfer the user can later install IP-
    Adapter or ControlNet — both diffusers-compatible.
    """
    raw_source = inputs.get("source_image")
    raw_style = inputs.get("style_reference")
    if not raw_source:
        raise CapabilityError(
            "missing_required_input",
            "image_styles requires a 'source_image' (image-ref).",
            slot="image_styles",
        )
    if not raw_style:
        raise CapabilityError(
            "missing_required_input",
            "image_styles requires a 'style_reference' (image-ref).",
            slot="image_styles",
        )

    source_bytes = _coerce_to_bytes(raw_source, field_name="'source_image'", slot="image_styles")
    source_pil = _bytes_to_pil(source_bytes)

    strength = inputs.get("strength")
    try:
        strength_f = float(strength) if strength is not None else 0.75
    except (TypeError, ValueError):
        strength_f = 0.75
    strength_f = max(0.0, min(1.0, strength_f))

    pipeline = _load_pipeline("StableDiffusionImg2ImgPipeline")

    # SD 1.5 needs a textual style hint to drive the transfer; absent a
    # reverse-prompt model wired in, we use a generic style-transfer
    # phrasing. Style-reference image is captured but unused at this
    # quality tier — full IP-Adapter integration is a follow-on.
    style_prompt = "in a distinctive artistic style, high quality"

    try:
        result = pipeline(
            prompt=style_prompt,
            image=source_pil,
            strength=strength_f,
            num_inference_steps=30,
            guidance_scale=7.5,
        )
    except Exception as exc:
        raise CapabilityError(
            "model_unavailable",
            f"Local diffusers image_styles failed: {exc}",
            slot="image_styles",
        ) from exc

    images = getattr(result, "images", None) or []
    if not images:
        raise CapabilityError(
            "model_unavailable",
            "Local diffusers returned no image for image_styles.",
            slot="image_styles",
        )
    return _pil_to_png_bytes(images[0])


# ---------------------------------------------------------------------------
# image_varies — img2img with low-strength noise to produce variations
# ---------------------------------------------------------------------------

def dispatch_image_varies(inputs: dict) -> list[bytes]:
    """Fulfill ``image_varies`` (capabilities.json §3.6) via img2img.

    Returns a list of PNG bytes — one per requested variation. Variation
    strength maps directly to img2img's ``strength`` parameter (lower =
    closer to source).
    """
    raw_source = inputs.get("source_image")
    if not raw_source:
        raise CapabilityError(
            "missing_required_input",
            "image_varies requires a 'source_image' (image-ref).",
            slot="image_varies",
        )

    source_bytes = _coerce_to_bytes(raw_source, field_name="'source_image'", slot="image_varies")
    source_pil = _bytes_to_pil(source_bytes)

    count = inputs.get("count")
    try:
        count_n = int(count) if count is not None else 4
    except (TypeError, ValueError):
        count_n = 4
    count_n = max(1, min(8, count_n))

    variation_strength = inputs.get("variation_strength")
    try:
        strength_f = float(variation_strength) if variation_strength is not None else 0.5
    except (TypeError, ValueError):
        strength_f = 0.5
    strength_f = max(0.0, min(1.0, strength_f))

    pipeline = _load_pipeline("StableDiffusionImg2ImgPipeline")

    out: list[bytes] = []
    for _ in range(count_n):
        try:
            result = pipeline(
                prompt="",
                image=source_pil,
                strength=strength_f,
                num_inference_steps=30,
                guidance_scale=7.5,
            )
        except Exception as exc:
            raise CapabilityError(
                "model_unavailable",
                f"Local diffusers image_varies failed: {exc}",
                slot="image_varies",
            ) from exc

        images = getattr(result, "images", None) or []
        if images:
            out.append(_pil_to_png_bytes(images[0]))

    if not out:
        raise CapabilityError(
            "model_unavailable",
            "Local diffusers returned no images for image_varies.",
            slot="image_varies",
        )
    return out


# ---------------------------------------------------------------------------
# Slot fulfillment registration
# ---------------------------------------------------------------------------

_SLOT_HANDLERS = {
    "image_generates":  dispatch_image_generates,
    "image_edits":      dispatch_image_edits,
    "image_outpaints":  dispatch_image_outpaints,
    "image_upscales":   dispatch_image_upscales,
    "image_styles":     dispatch_image_styles,
    "image_varies":     dispatch_image_varies,
}


def _diffusers_installed() -> bool:
    """Light-weight check — does the diffusers package exist on the
    Python path? Uses importlib.util.find_spec so we don't pay the
    multi-second cost of actually importing the library at startup."""
    import importlib.util

    return importlib.util.find_spec("diffusers") is not None


def register(registry: CapabilityRegistry) -> list[str]:
    """Bind every supported synthesis slot's dispatcher to ``registry``.

    Returns the list of slots actually registered. Skips registration
    entirely when the diffusers package isn't installed — this lets
    ``resolve_provider`` cleanly fall through to API providers
    configured as fallback in routing-config, instead of dispatching to
    a handler that would raise ``model_unavailable`` on every call.
    Slots whose contract isn't defined in ``capabilities.json`` are
    also silently skipped so a partial deployment doesn't raise
    ``unknown_slot`` at startup.
    """
    if not _diffusers_installed():
        return []
    bound: list[str] = []
    for slot_name, handler in _SLOT_HANDLERS.items():
        if not registry.has_slot(slot_name):
            continue
        registry.register_provider(slot_name, PROVIDER_ID, handler)
        bound.append(slot_name)
    return bound


_default_registered = False


def register_with_default_registry() -> CapabilityRegistry:
    """Lazy-register against the standard registry. Idempotent."""
    global _default_registered
    registry = load_registry()
    if not _default_registered:
        register(registry)
        _default_registered = True
    return registry
