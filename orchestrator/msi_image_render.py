"""MSI image rendering — operational executor for the Hector cartoon and
News Image Generator frameworks.

The framework files (Framework — MSI Hector Rentier Editorial Cartoon,
Framework — News Image Generator) specify what the framework AI does in
Layers 1–5 (cartoon recipe construction / image-generation request
preparation). This module implements what those frameworks describe at
Layers 6–8 (image generation, suitability screens, output assembly).

Inputs are structured JSON files (a "recipe" for Hector, a "request" for
news image) produced by manually running the framework or by the article
generator. Each render function:
  - Constructs the AI image-generation prompt per Reference — MSI Image
    Style Specification §5 / §6
  - Calls capability_registry.invoke('image_generates', ...) which cascades
    the Slot 1 → Slot 2 → Slot 3 → Slot 4 chain configured in
    routing-config.json
  - For Hector: runs potrace vectorization + SVG text overlay per Image
    Style Spec §4.5 / §5.1
  - For News: applies the contractual likeness / PII / register-match gates
    per News Image Generator Layer 3 / 4
  - Writes the image asset to ~/sites/mainstreetindependent/public/...
  - Emits / updates the .md content file with a fully-attributed
    imageSchema matching the Astro content-collection schema

Per:
  - Reference — MSI Image Style Specification.md v1.6 §5.4, §5.8.1, §6
  - Framework — MSI Hector Rentier Editorial Cartoon.md Layers 6, 7, 8
  - Framework — News Image Generator.md Layers 3, 4, 5
  - mainstreetindependent/src/content/config.ts (imageSchema + columns +
    articles collections)
"""
from __future__ import annotations

import datetime
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from capability_registry import CapabilityError, CapabilityRegistry, load_registry


def _register_all_image_providers(registry: CapabilityRegistry) -> None:
    """Defensively register every image-generation integration we know about
    against ``registry`` so the cascade for ``image_generates`` has a full
    chain to walk.

    ``capability_registry.load_registry()`` only auto-registers
    ``local-diffusers`` (the always-available local fallback). The cloud
    integrations (Civitai LoRA, OpenAI gpt-image-1 / DALL-E 3, Gemini)
    register themselves via the server's boot path in production. When
    ``render_hector_cartoon`` / ``render_news_image`` are called from a
    fresh Python process (e.g., via the ``/hector-render`` /
    ``/news-image-render`` slash commands which go through
    ``slash_commands.py`` → ``msi_image_render.py`` and call
    ``load_registry()`` themselves), the cloud integrations would be
    absent without this helper. Each registration is wrapped so a missing
    module / dependency doesn't break the others.
    """
    import sys as _sys
    import os as _os
    integrations_dir = _os.path.expanduser(
        "~/ora/orchestrator/integrations")
    if integrations_dir not in _sys.path:
        _sys.path.insert(0, integrations_dir)

    for module_name in ("civitai_images", "openai_images", "gemini_images"):
        try:
            module = __import__(module_name)
            module.register(registry)
        except Exception:
            # Missing module / dependency / keychain key — leave the
            # provider unregistered. The cascade walks whatever IS
            # registered; local-diffusers is the always-available floor.
            pass


# ---------------------------------------------------------------------------
# Astro repo paths
# ---------------------------------------------------------------------------

ASTRO_REPO = os.path.expanduser("~/sites/mainstreetindependent")
ASTRO_PUBLIC = os.path.join(ASTRO_REPO, "public")
ASTRO_CONTENT = os.path.join(ASTRO_REPO, "src", "content")
ASTRO_COLUMNS_DIR = os.path.join(ASTRO_CONTENT, "columns")
ASTRO_ARTICLES_DIR = os.path.join(ASTRO_CONTENT, "articles")
ASTRO_CARTOONS_PUBLIC_DIR = os.path.join(ASTRO_PUBLIC, "cartoons")
ASTRO_ARTICLES_IMAGES_PUBLIC_DIR = os.path.join(ASTRO_PUBLIC, "articles")


# ---------------------------------------------------------------------------
# Image Style Specification vocabulary blocks
# ---------------------------------------------------------------------------

# Per §6.3 Editorial Cartoon row
HECTOR_VISUAL_REGISTER_VOCAB = [
    "heavy cross-hatching",
    "engraved aesthetic",
    "single central allegorical figure",
    "figure-ground hierarchy via outline weight",
    "pure black masses with carved-out whites",
    "banner with quotation",
    "label-as-argument",
    "butt-face caricature for propaganda figures",
    "peanut gallery crowd",
    "spectacled gopher in lower frame",
    "in the lineage of Thomas Nast, Honoré Daumier, John Tenniel, "
    "Herblock, Pat Oliphant",
]

# Per §6.2 — universal positive
UNIVERSAL_POSITIVE_VOCAB = [
    "hand-drawn",
    "ink on cream paper",
    "transparent background",
    "linework dominant",
    "no solid fill",
    "varied pen technique",
    "single accent stroke in burnt orange",
]

# Per §6.4 — universal negative
UNIVERSAL_NEGATIVE_VOCAB = [
    "color fill", "gradient", "gradient shading", "photorealistic",
    "anime", "manga", "soft focus", "lens flare", "drop shadow",
    "modern digital style", "vector clip art", "decorative cartoon",
    "gag cartoon", "text in image", "embedded labels",
]

# Per §6.5 — forbidden caricature
FORBIDDEN_CARICATURE_NEGATIVE = [
    "racialized caricature", "physiognomic distortion",
    "simian-Irish trope", "anti-Catholic imagery",
    "antisemitic visual conventions", "gendered caricature",
    "hypersexualized figure",
]

# Per §6.6 — editorial-cartoon-specific additions
EDITORIAL_CARTOON_NEGATIVE_ADDITIONS = [
    "light cartoon style", "New Yorker single-line drawing",
]

# Civitai LoRA activation token — included when the Slot 1 provider is the
# Hector LoRA. Harmless extra tokens when the LoRA is not active.
HECTOR_LORA_TRIGGER = "hectorcartoon"

# Register vocab for the News Image Generator (non-editorial-cartoon paths)
PHOTOGRAPHIC_VOCAB = [
    "photojournalism", "documentary photography", "wire-service style",
    "natural light", "candid", "newsworthy moment",
]
ILLUSTRATED_VOCAB = [
    "editorial illustration", "graphic novel aesthetic",
    "muted palette", "expressive linework",
]
DIAGRAMMATIC_VOCAB = [
    "clean lines", "labeled components", "informational graphic",
    "minimal palette", "no decorative elements",
]


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

@dataclass
class HectorCartoonRecipe:
    """Output of Hector framework Layers 1–5; input to Layer 6 rendering."""
    cluster_id: str
    headline: str
    lede: str
    publish_date: str  # ISO-8601 date string
    composition_spec: str  # Layer 3 output
    caption: str  # Layer 4 — ≤15 words
    banner: Optional[str] = None  # Layer 4 banner text if present
    likeness_verdict: dict = field(default_factory=dict)  # Layer 5
    sources: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class NewsImageRequest:
    """Image-generation request emitted by the article generator."""
    article_slug: str
    article_headline: str
    article_lede: str
    visual_register: str  # photographic | illustrated | diagrammatic
    prompt_seeds: list[str]
    primary_entities: list[dict] = field(default_factory=list)
    style_spec_version: str = "current"
    source_path_strategy: str = "ai_preferred"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def construct_hector_prompt(recipe: HectorCartoonRecipe,
                            *, lora_active: bool = False) -> str:
    """Build the Hector cartoon prompt per framework Layer 6 step 1.

    Composes: optional LoRA trigger token → Layer 3 composition spec →
    §6.3 editorial-cartoon vocab → §6.2 universal positive → §6.4 universal
    negative → §6.5 forbidden caricature → §6.6 editorial-cartoon-specific
    additions. Pipe-separated sections keep the structure legible to both
    Civitai (which expects loose comma-tokens) and the OpenAI / Gemini
    natural-language image models.
    """
    parts: list[str] = []
    if lora_active:
        parts.append(HECTOR_LORA_TRIGGER)
    parts.append(recipe.composition_spec)
    parts.append(", ".join(HECTOR_VISUAL_REGISTER_VOCAB))
    parts.append(", ".join(UNIVERSAL_POSITIVE_VOCAB))
    parts.append("negative prompt: " + ", ".join(UNIVERSAL_NEGATIVE_VOCAB))
    parts.append("strictly forbidden: "
                 + ", ".join(FORBIDDEN_CARICATURE_NEGATIVE))
    parts.append("avoid: "
                 + ", ".join(EDITORIAL_CARTOON_NEGATIVE_ADDITIONS))
    return " | ".join(parts)


def construct_news_prompt(request: NewsImageRequest) -> str:
    """Build the news image prompt per News Image Generator Layer 3 step 3."""
    register_vocab = {
        "photographic": PHOTOGRAPHIC_VOCAB,
        "illustrated": ILLUSTRATED_VOCAB,
        "diagrammatic": DIAGRAMMATIC_VOCAB,
    }.get(request.visual_register, [])

    parts: list[str] = []
    if register_vocab:
        parts.append(", ".join(register_vocab))
    parts.append(", ".join(request.prompt_seeds))
    parts.append("negative prompt: text in image, embedded labels, watermark")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Pre-generation gates (News Image Generator Layer 3 steps 1–2)
# ---------------------------------------------------------------------------

def apply_likeness_gate(request: NewsImageRequest) -> tuple[list[dict], list[str]]:
    """Apply the likeness gate from News Image Generator Layer 3 step 1.

    A named real individual may be referenced in the prompt only if (a) they
    are a public figure AND (b) the article context is their public role.
    Otherwise the entity must be removed from the prompt seed.

    Returns ``(allowed_entities, removed_entity_names)``.
    """
    allowed: list[dict] = []
    removed: list[str] = []
    for entity in request.primary_entities:
        is_public = bool(entity.get("is_public_figure", False))
        in_public_role = bool(entity.get("in_public_role", False))
        if is_public and in_public_role:
            allowed.append(entity)
        else:
            removed.append(entity.get("name", "<unnamed>"))
    return allowed, removed


# ---------------------------------------------------------------------------
# capability_registry call wrapper
# ---------------------------------------------------------------------------

def invoke_image_gen(prompt: str, *, registry: CapabilityRegistry,
                     aspect_ratio: str = "1:1") -> tuple[bytes, dict]:
    """Call capability_registry.invoke for the image_generates slot.

    Returns ``(image_bytes, metadata)`` where metadata carries:
      - ``provider_id``: the provider that actually answered
      - ``ai_model``: provider_id (reused for imageSchema.ai_model)
      - ``attempts``: full fallback-chain attempt record
    """
    result = registry.invoke("image_generates", {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    })
    metadata = {
        "provider_id": result.provider_id,
        "ai_model": result.provider_id,
        "attempts": result.attempts,
    }
    return result.output, metadata


def _slot1_is_hector_lora(registry: CapabilityRegistry) -> bool:
    """Return True if the resolved Slot 1 provider for image_generates is the
    Civitai Hector LoRA. Drives the LoRA trigger-token insertion in the prompt.
    """
    chain = registry.resolve_provider_chain("image_generates")
    if not chain:
        return False
    head = chain[0].lower()
    return "civitai" in head and "hector" in head


# ---------------------------------------------------------------------------
# Vectorization (Hector framework Layer 6 step 5)
# ---------------------------------------------------------------------------

def potrace_vectorize(raster_bytes: bytes) -> str:
    """Convert raster image bytes (PNG, JPEG, etc.) to an SVG via
    mkbitmap + potrace.

    Implements Image Style Spec §4.5 step 4 (vectorization). The
    Civitai dispatcher returns JPEG, OpenAI returns PNG, and Gemini
    returns PNG — mkbitmap only reads pnm / bmp, so we normalize the
    input through Pillow to a PNG that mkbitmap accepts regardless of
    which provider answered. CSS hooks applied per the same spec step:
    ``fill="currentColor"`` so the cartoon adopts the page's text
    color through theme tokens; transparent background so the
    underlying paper texture (or none) shows through.
    """
    with tempfile.TemporaryDirectory() as tmp:
        input_pgm_path = os.path.join(tmp, "input.pgm")
        processed_pgm_path = os.path.join(tmp, "processed.pgm")
        svg_path = os.path.join(tmp, "output.svg")

        # Normalize whatever bytes the provider gave us (PNG / JPEG /
        # WebP) into a grayscale PGM — mkbitmap only reads pnm/bmp.
        # Pillow handles every format the cascade produces.
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(raster_bytes))
        img = img.convert("L")  # 8-bit grayscale
        img.save(input_pgm_path, "PPM")

        # mkbitmap: PGM → preprocessed PGM with edge enhancement.
        # -x: enable inversion if needed
        # -f 10: filter radius (smooths very fine detail before tracing)
        # -t 0.48: threshold (slightly under midpoint, favours line preservation)
        subprocess.run(
            ["mkbitmap", "-x", "-f", "10", "-t", "0.48",
             "-o", processed_pgm_path, input_pgm_path],
            check=True, capture_output=True,
        )

        # potrace: PGM → SVG with conservative path optimization.
        subprocess.run(
            ["potrace", "--svg", "--opttolerance", "0.4",
             "--output", svg_path, processed_pgm_path],
            check=True, capture_output=True,
        )

        with open(svg_path, "r") as f:
            svg = f.read()

    svg = svg.replace('fill="#000000"', 'fill="currentColor"')
    svg = re.sub(
        r'<svg([^>]*)>',
        r'<svg\1 style="background:transparent">',
        svg,
        count=1,
    )
    return svg


# ---------------------------------------------------------------------------
# SVG text overlay (Hector framework Layer 6 steps 6–7)
# ---------------------------------------------------------------------------

def composite_text_overlays(svg: str, *, banner: Optional[str],
                            signature: str = "Hector Rentier") -> str:
    """Composite banner + signature as SVG ``<text>`` overlays.

    Per Image Style Spec §4.5 step 4 and §5.1:
      - Banner (if present): italic Georgia, centered near top of frame.
      - Signature: italic Georgia, lower-right, hand-lettered feel.
      - Caption is intentionally NOT baked into the SVG — it renders below
        the image from the column's imageSchema.caption (per §4.5).
    """
    width = 1024.0
    height = 1024.0
    m = re.search(
        r'<svg[^>]*viewBox="\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)"', svg)
    if m:
        try:
            width = float(m.group(1))
            height = float(m.group(2))
        except ValueError:
            pass

    overlays: list[str] = []

    if banner:
        overlays.append(
            f'<text x="{width/2:.1f}" y="{height*0.08:.1f}" '
            f'text-anchor="middle" '
            f'font-family="Georgia, serif" font-style="italic" '
            f'font-size="{height*0.04:.0f}" fill="currentColor">'
            f'{_escape_xml(banner)}</text>'
        )

    overlays.append(
        f'<text x="{width*0.97:.1f}" y="{height*0.97:.1f}" '
        f'text-anchor="end" '
        f'font-family="Georgia, serif" font-style="italic" '
        f'font-size="{height*0.025:.0f}" fill="currentColor" '
        f'opacity="0.85">'
        f'{_escape_xml(signature)}</text>'
    )

    if "</svg>" in svg:
        svg = svg.replace("</svg>", "\n".join(overlays) + "\n</svg>", 1)
    return svg


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


# ---------------------------------------------------------------------------
# Slug + alt-text helpers
# ---------------------------------------------------------------------------

def slugify(text: str, *, max_length: int = 60) -> str:
    """URL-safe slug: lowercased, alphanumerics + hyphens, trimmed."""
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug).strip('-')
    if len(slug) > max_length:
        cut = slug.rfind('-', 0, max_length)
        slug = slug[:cut if cut > max_length * 0.6 else max_length].rstrip('-')
    return slug or "untitled"


def trim_alt_text(text: str, *, max_chars: int = 125) -> str:
    """Trim alt text to WCAG 2.1 ≤125 chars (News Img Gen Layer 4 step 6)."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind(' ', 0, max_chars - 1)
    if cut > max_chars * 0.6:
        return text[:cut] + "…"
    return text[:max_chars - 1] + "…"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def render_hector_cartoon(recipe_data: dict, *,
                          registry: Optional[CapabilityRegistry] = None
                          ) -> dict:
    """Render a Hector editorial cartoon from a Layers 1–5 recipe.

    Operationalizes Framework — MSI Hector Rentier Editorial Cartoon
    Layers 6–8: prompt construction → image generation (with one retry
    on failure) → potrace vectorization → SVG text overlays → write SVG
    asset and column .md to the Astro repo.

    Returns a dict::

        {
          "success": bool,
          "column_md_path": str,
          "svg_path": str,
          "slug": str,
          "image_schema": dict,    # imageSchema for the column
          "attempts": list[dict],  # capability_registry fallback chain
        }

    On failure, returns ``{"success": False, "error": str, "attempts": [...]}``.
    """
    try:
        recipe = HectorCartoonRecipe(**recipe_data)
    except TypeError as exc:
        return {"success": False, "error": f"Invalid recipe schema: {exc}"}

    if registry is None:
        registry = load_registry()
        _register_all_image_providers(registry)

    lora_active = _slot1_is_hector_lora(registry)
    prompt = construct_hector_prompt(recipe, lora_active=lora_active)

    # Layer 6 step 3–4: submit + retry-once on failure
    try:
        image_bytes, gen_metadata = invoke_image_gen(prompt, registry=registry)
    except CapabilityError as exc:
        simplified = recipe.composition_spec + " | " + ", ".join(
            HECTOR_VISUAL_REGISTER_VOCAB[:5])
        if lora_active:
            simplified = HECTOR_LORA_TRIGGER + " " + simplified
        try:
            image_bytes, gen_metadata = invoke_image_gen(
                simplified, registry=registry)
        except CapabilityError as exc2:
            return {
                "success": False,
                "error": f"Generation failed twice: {exc2.code} — {exc2}",
                "attempts": getattr(exc2, "attempts", []),
            }

    # Layer 6 step 5: vectorize
    try:
        svg = potrace_vectorize(image_bytes)
    except FileNotFoundError as exc:
        return {
            "success": False,
            "error": (f"Vectorization tool missing: {exc}. "
                      f"Install with `brew install potrace`."),
        }
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode() if exc.stderr else str(exc)
        return {
            "success": False,
            "error": f"Vectorization failed: {err}",
        }

    # Layer 6 steps 6–7: composite banner + signature (caption renders below)
    svg = composite_text_overlays(svg, banner=recipe.banner)

    slug = slugify(recipe.headline)
    os.makedirs(ASTRO_CARTOONS_PUBLIC_DIR, exist_ok=True)
    svg_filename = f"{slug}.svg"
    svg_path = os.path.join(ASTRO_CARTOONS_PUBLIC_DIR, svg_filename)
    with open(svg_path, "w") as f:
        f.write(svg)

    image_schema = {
        "url": f"/cartoons/{svg_filename}",
        "alt": trim_alt_text(
            f"Editorial cartoon by Hector Rentier: {recipe.headline}"),
        "caption": recipe.caption,
        "credit": "Hector Rentier (Main Street Independent, algorithmic)",
        "source": "ai_generated",
        "disclosure": (
            "AI-generated illustration. Prompt summary and model identifier "
            "available in metadata."),
        "ai_model": gen_metadata["ai_model"],
        "ai_prompt": prompt[:200],
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
    }

    column_md = _emit_hector_column_md(recipe, image_schema)
    os.makedirs(ASTRO_COLUMNS_DIR, exist_ok=True)
    column_md_path = os.path.join(ASTRO_COLUMNS_DIR, f"{slug}.md")
    with open(column_md_path, "w") as f:
        f.write(column_md)

    return {
        "success": True,
        "column_md_path": column_md_path,
        "svg_path": svg_path,
        "slug": slug,
        "image_schema": image_schema,
        "attempts": gen_metadata["attempts"],
    }


def render_news_image(request_data: dict, *,
                      registry: Optional[CapabilityRegistry] = None
                      ) -> dict:
    """Render a news article image from an image-generation request.

    Operationalizes Framework — News Image Generator Layers 3–5 along the
    AI path. The commons-search path (Layer 2) is intentionally not
    implemented here — the article generator drives that decision, and a
    commons-only request should resolve in the publisher's workflow before
    reaching this entry point. The function rejects ``editorial_cartoon``
    register (that path goes through :func:`render_hector_cartoon`).

    Returns a dict::

        {
          "success": bool,
          "image_path": str,         # PNG asset path
          "article_md_path": str,    # article .md path (may not exist yet)
          "article_md_updated": bool,
          "image_schema": dict,      # imageSchema for the article
          "removed_entities": list,  # names removed by likeness gate
          "attempts": list[dict],
        }

    On failure, returns ``{"success": False, "error": str, "attempts": [...]}``.
    """
    try:
        request = NewsImageRequest(**request_data)
    except TypeError as exc:
        return {"success": False, "error": f"Invalid request schema: {exc}"}

    if registry is None:
        registry = load_registry()
        _register_all_image_providers(registry)

    if request.visual_register == "editorial_cartoon":
        return {
            "success": False,
            "error": ("editorial_cartoon register is handled by "
                      "render_hector_cartoon(), not render_news_image()"),
        }

    # Layer 3 step 1: likeness gate. Removed entities are stripped from seeds
    # below so they do not appear in the prompt.
    _allowed, removed_entities = apply_likeness_gate(request)

    # Strip removed-entity names from prompt seeds
    removed_lower = {name.lower() for name in removed_entities}
    request.prompt_seeds = [
        seed for seed in request.prompt_seeds
        if seed.lower() not in removed_lower
    ]

    prompt = construct_news_prompt(request)

    # Layer 3 step 4–5: submit + retry-once on failure
    try:
        image_bytes, gen_metadata = invoke_image_gen(prompt, registry=registry)
    except CapabilityError as exc:
        simplified = ", ".join(request.prompt_seeds)
        try:
            image_bytes, gen_metadata = invoke_image_gen(
                simplified, registry=registry)
        except CapabilityError as exc2:
            return {
                "success": False,
                "error": f"Generation failed twice: {exc2.code} — {exc2}",
                "attempts": getattr(exc2, "attempts", []),
            }

    # Layer 4 step 6: alt text (≤125 chars per WCAG 2.1)
    alt = trim_alt_text(
        f"Illustration accompanying article: {request.article_headline}")

    os.makedirs(ASTRO_ARTICLES_IMAGES_PUBLIC_DIR, exist_ok=True)
    img_filename = f"{request.article_slug}.png"
    img_path = os.path.join(ASTRO_ARTICLES_IMAGES_PUBLIC_DIR, img_filename)
    with open(img_path, "wb") as f:
        f.write(image_bytes)

    # Layer 5: imageSchema with full attribution
    image_schema = {
        "url": f"/articles/{img_filename}",
        "alt": alt,
        "credit": "Main Street Independent (algorithmic)",
        "source": "ai_generated",
        "disclosure": (
            "AI-generated image. Prompt summary and model identifier "
            "available in metadata."),
        "ai_model": gen_metadata["ai_model"],
        "ai_prompt": prompt[:200],
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
    }

    article_md_path = os.path.join(ASTRO_ARTICLES_DIR,
                                   f"{request.article_slug}.md")
    updated = False
    if os.path.isfile(article_md_path):
        updated = _patch_article_image_field(article_md_path, image_schema)

    return {
        "success": True,
        "image_path": img_path,
        "image_schema": image_schema,
        "article_md_path": article_md_path,
        "article_md_updated": updated,
        "removed_entities": removed_entities,
        "attempts": gen_metadata["attempts"],
    }


# ---------------------------------------------------------------------------
# Markdown emission / patching
# ---------------------------------------------------------------------------

def _emit_hector_column_md(recipe: HectorCartoonRecipe,
                           image_schema: dict) -> str:
    """Emit the .md column file for an Astro columns entry."""
    metadata = recipe.metadata or {
        "framework_version": "msi-hector-cartoon-0.2.0",
        "generation_timestamp": datetime.datetime.now(
            datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_cluster_id": recipe.cluster_id,
        "gdelt_event_ids": [],
        "consensus_floor_version": "current",
        "publication_mindspec_version": "current",
        "ai_disclosure": (
            "Editorial cartoon generated by AI image model; analytical "
            "framing and composition authored by the Hector Rentier framework."),
        "human_review_status": "not_triggered",
        "human_review_triggers": [],
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "primary_entities": [],
        "primary_themes": [],
        "floor_values_engaged": [],
    }
    frontmatter = {
        "headline": recipe.headline,
        "pen_name": "hector-rentier",
        "lede": recipe.lede,
        "publish_date": recipe.publish_date,
        "image": image_schema,
        "sources": recipe.sources,
        "atomic_claims": [],
        "metadata": metadata,
        "draft": False,
        "parody": False,
    }
    body = (
        f"![{image_schema['alt']}]({image_schema['url']})\n\n"
        f"*{recipe.caption}*\n"
    )
    return _dump_md(frontmatter, body)


def _patch_article_image_field(md_path: str, image_schema: dict) -> bool:
    """Add or replace the ``image:`` field in an article's YAML frontmatter.

    Returns True on success, False if the file lacks parseable frontmatter.
    """
    with open(md_path, "r") as f:
        content = f.read()

    m = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not m:
        return False

    fm_text = m.group(1)
    body = m.group(2)

    # Drop any existing image: block (top-level key + indented children) and
    # any single-line image: value.
    fm_text = re.sub(
        r'(^|\n)image:\s*\n(?:[ \t]+.+\n)*', r'\1', fm_text)
    fm_text = re.sub(
        r'(^|\n)image:[ \t]+[^\n]+\n', r'\1', fm_text)

    image_yaml = _yaml_dump_image(image_schema)
    fm_text = fm_text.rstrip() + "\n" + image_yaml

    new_content = f"---\n{fm_text}\n---\n{body}"
    with open(md_path, "w") as f:
        f.write(new_content)
    return True


def _yaml_dump_image(image_schema: dict) -> str:
    """Render imageSchema dict as YAML (no PyYAML dependency)."""
    lines = ["image:"]
    for key in ("url", "alt", "caption", "credit", "source", "license",
                "license_url", "disclosure", "ai_model", "ai_prompt"):
        if key in image_schema and image_schema[key] is not None:
            lines.append("  " + _yaml_scalar(key, image_schema[key]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Minimal YAML emitter (avoids PyYAML to stay stdlib-only)
# ---------------------------------------------------------------------------

def _dump_md(frontmatter: dict, body: str) -> str:
    """Render an Astro .md content file with YAML frontmatter."""
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(_yaml_render(key, value, indent=0))
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def _yaml_render(key: str, value: Any, *, indent: int) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return f"{pad}{key}: {{}}"
        sub = "\n".join(
            _yaml_render(k, v, indent=indent + 1) for k, v in value.items())
        return f"{pad}{key}:\n{sub}"
    if isinstance(value, list):
        if not value:
            return f"{pad}{key}: []"
        sub = "\n".join(_yaml_list_item(item, indent=indent + 1)
                        for item in value)
        return f"{pad}{key}:\n{sub}"
    return f"{pad}{_yaml_scalar(key, value)}"


def _yaml_list_item(item: Any, *, indent: int) -> str:
    pad = "  " * indent
    if isinstance(item, dict):
        items = list(item.items())
        if not items:
            return f"{pad}- {{}}"
        first_key, first_val = items[0]
        first_line = _yaml_render(first_key, first_val, indent=0).lstrip()
        out = [f"{pad}- {first_line}"]
        for k, v in items[1:]:
            out.append(_yaml_render(k, v, indent=indent + 1))
        return "\n".join(out)
    return f"{pad}- {_yaml_scalar_value(item)}"


def _yaml_scalar(key: str, value: Any) -> str:
    return f"{key}: {_yaml_scalar_value(value)}"


def _yaml_scalar_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    sval = str(value)
    needs_quote = (
        ':' in sval or '#' in sval or '\n' in sval
        or sval.startswith(('-', '?', '*', '!', '&', '@', '|', '>', '"', "'"))
        or sval.strip() != sval
    )
    if needs_quote:
        return '"' + sval.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return sval
