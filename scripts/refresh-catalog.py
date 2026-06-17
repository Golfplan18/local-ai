#!/usr/bin/env python3
"""Refresh the unified model catalog (install Chunk 4).

Fetches OpenRouter, enriches with intelligence_index pulled from the
curated model registry (``config/model-registry.json``), and writes
``config/model-catalog.json`` for the auto-populate engine (Chunk 5)
to consume. Standardizes cost to $/M blended tokens using a 3:1
input:output ratio (matching AA's published methodology). Assigns
each cloud model a ``family_tier`` and ``size_bucket`` via
``config/family-classification.json`` for closed-proprietary models
whose parameter counts aren't published.

This is a new tool independent of ``scripts/refresh-openrouter.py`` —
that tool continues to maintain ``config/openrouter-catalog.json`` for
existing readers (server.py, the bucket selector, etc.). The new
``model-catalog.json`` is consumed only by the new auto-populate engine.

Intelligence enrichment (2026-05-20): direct Artificial Analysis (AA)
API access was retired. The ``aa_intelligence_index`` field on each
catalog entry is now populated from ``config/model-registry.json``,
which is itself populated by ``scripts/sync_model_registry.py`` from
free public sources (OpenRouter + LiteLLM + Chatbot Arena + AA's
public website + empirical probe). No API key required anywhere.
When the registry is missing (fresh clone, no sync run yet),
``aa_intelligence_index`` stays null and auto-populate falls back to
cost-sort — same as today's no-AA-key state.

API keys (read from env):
    OPENROUTER_API_KEY   — optional. The /models endpoint is public, but
                            authenticated requests get higher rate limits.

Outputs:
    config/model-catalog.json            — unified catalog (canonical)
    data/model-catalog-changes.jsonl     — per-refresh changelog of new
                                           models, retired models, and
                                           free → paid transitions.

Usage:
    python3 scripts/refresh-catalog.py            # fetch + write
    python3 scripts/refresh-catalog.py --dry-run  # print summary, no write
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"

CATALOG_PATH = Path(
    os.environ.get("ORA_MODEL_CATALOG_PATH")
    or (CONFIG_DIR / "model-catalog.json")
)
FAMILY_CLASS_PATH = CONFIG_DIR / "family-classification.json"
CHANGES_PATH = Path(
    os.environ.get("ORA_MODEL_CATALOG_CHANGES_PATH")
    or (DATA_DIR / "model-catalog-changes.jsonl")
)
MODEL_REGISTRY_PATH = Path(
    os.environ.get("ORA_MODEL_REGISTRY_PATH")
    or (CONFIG_DIR / "model-registry.json")
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

# Blended cost ratio: AA convention is 3 parts input : 1 part output for
# chat-typical use. Using output-only cost systematically over-penalizes
# models with high output / low input pricing (a common pattern).
BLEND_INPUT_WEIGHT = 3.0
BLEND_OUTPUT_WEIGHT = 1.0
BLEND_DENOMINATOR = BLEND_INPUT_WEIGHT + BLEND_OUTPUT_WEIGHT  # 4.0


def fetch_openrouter() -> dict | None:
    """Fetch the OpenRouter model list. Returns the parsed JSON or None on error."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    req = urllib.request.Request(
        OPENROUTER_URL,
        headers={"Accept": "application/json"},
    )
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"[refresh-catalog] OpenRouter fetch failed: {exc}", file=sys.stderr)
        return None


def load_model_registry() -> dict | None:
    """Load the curated model registry. Returns the parsed dict or None
    when the file is missing / unreadable.

    Replaces the prior fetch_artificial_analysis() — intelligence data
    now comes from the curated registry (populated by sync_model_registry.py
    from free public sources: OpenRouter + LiteLLM + Chatbot Arena + AA's
    public /models page + empirical probe). No API key needed anywhere.

    When the registry is missing (fresh clone, no sync run yet), this
    returns None and refresh-catalog proceeds without intelligence
    enrichment — same fallback as the prior no-AA-key path.
    """
    if not MODEL_REGISTRY_PATH.exists():
        print(
            f"[refresh-catalog] ⚠ {MODEL_REGISTRY_PATH.name} not found; "
            f"intelligence enrichment will be skipped.\n"
            f"  Run `python3 scripts/sync_model_registry.py sync` first to populate it.",
            file=sys.stderr,
        )
        return None
    try:
        with open(MODEL_REGISTRY_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[refresh-catalog] model-registry.json read failed: {exc}", file=sys.stderr)
        return None


def load_family_classification() -> dict:
    """Load family-classification.json. Returns empty config on missing file."""
    if not FAMILY_CLASS_PATH.exists():
        print(
            f"[refresh-catalog] {FAMILY_CLASS_PATH} missing; cloud models will "
            "be classified as unknown-size.",
            file=sys.stderr,
        )
        return {"providers": {}}
    with open(FAMILY_CLASS_PATH) as f:
        return json.load(f)


def classify_family(model_id: str, provider: str, family_rules: dict) -> tuple[str | None, str | None]:
    """Match a model id against family-classification rules.

    Returns (family_tier, size_bucket) or (None, None) when no rule
    matches. Case-insensitive substring match against the model id
    (e.g., "openai/gpt-5-mini" matches the "mini" pattern under openai).
    """
    rules = family_rules.get("providers", {}).get(provider.lower(), [])
    lowered_id = model_id.lower()
    for rule in rules:
        pattern = rule.get("pattern", "").lower()
        if pattern and pattern in lowered_id:
            return rule.get("family_tier"), rule.get("size_bucket")
    return None, None


def size_bucket_from_parameters(params_b: float | int | None) -> str | None:
    """Classify by parameter count when known.

    < 12B  → small
    12-50B → midsize
    >= 50B → large
    None   → None (caller falls through to family-classification)
    """
    if params_b is None:
        return None
    if params_b < 12:
        return "small"
    if params_b < 50:
        return "midsize"
    return "large"


# Open-weights models typically carry their size in the slug
# (meta-llama/llama-3.3-70b-instruct, qwen/qwen3-32b, mistralai/mistral-7b).
# This regex matches a digit-then-b token bounded by hyphens / slashes /
# colons / underscores / start-or-end-of-string. It deliberately ignores
# in-word matches (so "v3b" version markers and "8x7b" MoE expressions
# don't false-fire — the latter would match "7b" alone which we accept
# as a known imprecision; Mixtral-class MoE landing in "small" is wrong
# but Mixtral models are scarce in current catalogs).
_SIZE_IN_SLUG = re.compile(
    r'(?:^|[-/:_])(\d{1,3}(?:\.\d+)?)b(?:[-/:_.]|$)',
    re.IGNORECASE,
)


def infer_parameters_b_from_slug(slug: str) -> float | None:
    """Extract parameter count (in billions) from a model slug.

    Matches patterns like ``70b`` ``27b`` ``7b`` ``8.1b`` when bounded
    by slug delimiters. Returns None when no recognizable size pattern
    appears (closed proprietary or named-tier products like
    ``deepseek-v4-pro``, ``qwen-plus``, ``kimi-k2.6`` — those go through
    family-classification instead).
    """
    if not slug:
        return None
    m = _SIZE_IN_SLUG.search(slug)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


# Size/speed markers a vendor puts in a model name to signal a smaller or
# speed-optimised variant. Matched as DELIMITED tokens (bounded by
# -/:_ or start/end) so "mini" never false-matches inside "gemini", etc.
# small-class markers → "small"; "flash" is a speed tier that is capable
# but not a flagship-large model → "midsize". Both exclude the model from
# the picker's large/big slots by capability (2026-06-14): a model that
# announces its size in its name must never qualify as a big model.
_SMALL_NAME_MARKERS = ("small", "mini", "nano", "tiny", "micro", "lite")
_MIDSIZE_NAME_MARKERS = ("flash",)
_NAME_MARKER_RE = re.compile(
    r'(?:^|[-/:_])(' + "|".join(_SMALL_NAME_MARKERS + _MIDSIZE_NAME_MARKERS)
    + r')(?:[-/:_.]|$)',
    re.IGNORECASE,
)


def infer_size_from_name_markers(slug: str) -> str | None:
    """Last-resort size bucket from an explicit size/speed marker in the
    model name. Returns 'small', 'midsize', or None (no marker). Only
    consulted after parameter-count and family-classification both fail —
    so a real param count or family rule always wins."""
    if not slug:
        return None
    m = _NAME_MARKER_RE.search(slug)
    if not m:
        return None
    marker = m.group(1).lower()
    return "midsize" if marker in _MIDSIZE_NAME_MARKERS else "small"


def blend_cost(input_per_m: float | None, output_per_m: float | None) -> float | None:
    """Blend input + output cost into a single $/M number.

    Uses the 3:1 input:output ratio (AA convention for chat-typical use).
    Returns None when either side is missing — caller treats as
    "cost unknown" and may exclude from cost-sensitive picks.
    """
    if input_per_m is None or output_per_m is None:
        return None
    return (input_per_m * BLEND_INPUT_WEIGHT + output_per_m * BLEND_OUTPUT_WEIGHT) / BLEND_DENOMINATOR


def normalize_openrouter_entry(entry: dict, family_rules: dict) -> dict:
    """Convert an OpenRouter /v1/models entry to our unified shape."""
    model_id = entry.get("id", "")
    provider = (entry.get("id", "").split("/")[0] if "/" in entry.get("id", "") else "openrouter").lower()

    pricing = entry.get("pricing", {}) or {}
    # OpenRouter pricing is $/token (string). Convert to $/M tokens (float).
    def _per_m(val):
        if val is None or val == "":
            return None
        try:
            return float(val) * 1_000_000
        except (TypeError, ValueError):
            return None

    input_per_m = _per_m(pricing.get("prompt"))
    output_per_m = _per_m(pricing.get("completion"))
    blended = blend_cost(input_per_m, output_per_m)

    arch = entry.get("architecture", {}) or {}
    input_mods = arch.get("input_modalities") or []
    output_mods = arch.get("output_modalities") or []
    vision_capable = "image" in input_mods

    # Parameter count: rarely populated in OpenRouter directly, but the
    # slug usually carries it for open-weights models (llama-3.3-70b,
    # qwen3-32b, mistral-7b, gemma-2-9b, etc.). Fall through to family
    # rules for closed proprietary (Haiku/Sonnet/Opus, GPT family,
    # Gemini Flash/Pro) and named-tier products (DeepSeek V4 Pro,
    # Qwen Plus/Max, Kimi K2.6, GLM, Mimo).
    params_b = entry.get("parameters_b")
    if params_b is None:
        params_b = infer_parameters_b_from_slug(model_id)
    size_bucket = size_bucket_from_parameters(params_b)
    family_tier: str | None = None
    if size_bucket is None:
        family_tier, size_bucket = classify_family(model_id, provider, family_rules)
    if size_bucket is None:
        # Last resort: an explicit size/speed marker in the name
        # (mistral-SMALL, gpt-NANO, step-3.7-FLASH) classifies the model
        # by capability so the picker's large slots exclude it. Leaving it
        # None here would let the auto-populate null-bucket admission sweep
        # a self-declared-small model into a big slot — the 2026-06-14
        # budget regression. A genuine codename (claude-fable-5) has no
        # marker and correctly stays None for that admission to catch.
        size_bucket = infer_size_from_name_markers(model_id)

    # Free / paid: free models have output cost == 0.
    is_free = (output_per_m == 0.0 and input_per_m == 0.0)

    return {
        "id": model_id,
        "display_name": entry.get("name", model_id),
        "provider": provider,
        "openrouter_slug": model_id,
        "vision_capable": vision_capable,
        "input_modalities": input_mods,
        "output_modalities": output_mods,
        "context_window": entry.get("context_length"),
        "parameters_b": params_b,
        "openrouter_pricing": {
            "input_per_m": input_per_m,
            "output_per_m": output_per_m,
            "blended_per_m": blended,
        },
        "aa_intelligence_index": None,    # measured AA score; filled by enrich pass
        "aa_blended_per_m": None,         # filled in by AA pass when available
        "intelligence_score": None,       # Arena Elo (UI/reference; not a picker axis)
        "intelligence_rank": None,        # Arena rank (UI/reference)
        "release_date": None,             # recency (YYYY-MM-DD) — picker tiebreak
        "family_tier": family_tier,
        "size_bucket": size_bucket,
        "is_free": is_free,
    }


def enrich_from_model_registry(catalog: list[dict], registry: dict) -> int:
    """Project the curated registry's selection-relevant signals onto
    matching catalog entries by direct OpenRouter-id lookup (the registry
    is keyed by OpenRouter id, so no fuzzy matching is needed).

    Copies, when present on the registry entry:
      * ``aa_intelligence_index`` — the measured Artificial Analysis 0-100
        score (the picker's only intelligence axis).
      * ``intelligence_score`` / ``intelligence_rank`` — Arena Elo and its
        rank. Carried for the UI / future use, but NOT used as an
        intelligence fallback: Arena Elo correlates only weakly with the
        AA benchmark (Pearson r≈0.44 over the 145 dual-scored models; the
        highest-Elo model, gemini-2.5-pro at 1474, measures AA 34.6 while
        opus-4.8 at Elo 1371 measures 61.4), so an Elo→AA estimate would
        systematically mis-rank. An unbenchmarked model honestly has no
        quality score and ranks accordingly.
      * ``release_date`` — recency (YYYY-MM-DD). Powers the picker's
        "newest wins among equals" tiebreak.

    Before this (2026-06-14) only ``aa_intelligence_index`` was copied, so
    the catalog the picker reads carried no recency signal at all — one
    reason the newest models couldn't be favoured. Returns the count of
    entries that received a measured ``aa_intelligence_index``.
    Missing/empty registry → 0, catalog ships unenriched.
    """
    models = (registry or {}).get("models") or {}
    if not models:
        return 0
    enriched = 0
    for entry in catalog:
        or_id = entry.get("openrouter_slug") or entry.get("id")
        if not or_id:
            continue
        reg = models.get(or_id)
        if reg is None:
            continue
        intelligence = reg.get("aa_intelligence_index")
        if intelligence is not None:
            entry["aa_intelligence_index"] = intelligence
            enriched += 1
        # Secondary signals — purely additive (recency tiebreak + UI).
        # output_tokens_per_second is the Fast slot's sort key: without it in the
        # catalog the tokens_per_sec_desc sort is a no-op (every model sinks to
        # -inf) and Fast falls back to catalog order — which is how a slow,
        # expensive flagship can land in a speed slot. Carry it from the registry.
        for field in ("intelligence_score", "intelligence_rank", "release_date",
                      "output_tokens_per_second"):
            val = reg.get(field)
            if val is not None:
                entry[field] = val
    return enriched


def append_media_entries_from_registry(catalog: list[dict], registry: dict) -> int:
    """Append AA media-leaderboard entries (image generation, image editing,
    text-to-video) to the catalog.

    These models have no OpenRouter or LiteLLM presence; they're scraped
    directly from AA's per-capability arena pages by sync_model_registry.
    The registry stores their Elo number in ``intelligence_score`` (same
    field chat models use for the AA intelligence index — Elo plays the
    same role for image-gen ranking that intelligence index plays for chat).

    Conversion:
      - id stays as the registry id (``aa-img:<uuid>`` etc.)
      - ``aa_intelligence_index`` ← registry ``intelligence_score`` (Elo)
      - ``category`` carried forward (image_generation / image_editing /
        text_to_video) — used by auto-populate's slot filter
      - ``size_bucket`` stays None (sizing doesn't apply to image models)
      - ``image_pricing`` (new 2026-05-22) — when AA published a per-1k
        images price, propagate it. Lets auto-populate differentiate
        Premium / Optimum / Budget / Free picks for image-gen slots.
      - ``is_free`` set from ``image_pricing == 0`` when known.
      - ``openrouter_pricing`` stays all-None (chat-side pricing
        doesn't apply to image models).

    Returns the count of media entries appended.
    """
    models = (registry or {}).get("models") or {}
    if not models:
        return 0
    appended = 0
    for mid, m in models.items():
        category = m.get("category")
        if category not in ("image_generation", "image_editing", "text_to_video"):
            continue
        elo = m.get("intelligence_score")
        # Media pricing — registry stores AA's pricePer1kImages under
        # ``pricing.per_1k_images`` (None when AA shows "Coming soon"
        # / "No API available" / null). Promote to a catalog-level
        # ``image_pricing`` field so auto-populate sees it without
        # peering into the nested dict.
        pricing = m.get("pricing") or {}
        per_1k_images = pricing.get("per_1k_images") if isinstance(pricing, dict) else None
        is_free = (per_1k_images == 0) if per_1k_images is not None else False
        catalog.append({
            "id": mid,
            "display_name": m.get("display_name") or mid,
            "provider": m.get("provider") or "artificial-analysis",
            "vendor": m.get("vendor"),
            "openrouter_slug": None,
            "category": category,
            "vision_capable": False,  # image-gen models output images; they don't ingest
            "input_modalities": ["text"] if category in ("image_generation", "text_to_video") else ["text", "image"],
            "output_modalities": ["video"] if category == "text_to_video" else ["image"],
            "context_window": None,
            "parameters_b": None,
            "openrouter_pricing": {
                "input_per_m": None,
                "output_per_m": None,
                "blended_per_m": None,
            },
            "image_pricing": {
                "per_1k_images": per_1k_images,
            },
            "aa_intelligence_index": elo,
            "aa_intelligence_rank": m.get("intelligence_rank"),
            "aa_intelligence_votes": m.get("intelligence_votes"),
            "aa_blended_per_m": None,
            "family_tier": None,
            "size_bucket": None,
            "is_free": is_free,
            "is_open_weights": m.get("is_open_weights", False),
            "release_date": m.get("release_date"),
        })
        appended += 1
    return appended


def detect_changes(new_catalog: list[dict], old_catalog: list[dict] | None) -> dict:
    """Compute new / retired / free→paid / paid→free transitions."""
    if old_catalog is None:
        return {"new": [], "retired": [], "free_to_paid": [], "paid_to_free": []}

    old_by_id = {m["id"]: m for m in old_catalog}
    new_by_id = {m["id"]: m for m in new_catalog}

    new_ids = set(new_by_id.keys()) - set(old_by_id.keys())
    retired_ids = set(old_by_id.keys()) - set(new_by_id.keys())

    free_to_paid = []
    paid_to_free = []
    for mid in set(old_by_id.keys()) & set(new_by_id.keys()):
        old = old_by_id[mid]
        new = new_by_id[mid]
        if old.get("is_free") and not new.get("is_free"):
            free_to_paid.append(mid)
        elif not old.get("is_free") and new.get("is_free"):
            paid_to_free.append(mid)

    return {
        "new": sorted(new_ids),
        "retired": sorted(retired_ids),
        "free_to_paid": sorted(free_to_paid),
        "paid_to_free": sorted(paid_to_free),
    }


def append_change_log(changes: dict, timestamp: str) -> None:
    """Append a refresh-summary line to data/model-catalog-changes.jsonl."""
    if not any(changes.values()):
        return
    CHANGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "refreshed_at": timestamp,
        **changes,
    }
    with open(CHANGES_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def load_existing_catalog() -> list[dict] | None:
    if not CATALOG_PATH.exists():
        return None
    try:
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        return data.get("models", [])
    except (json.JSONDecodeError, OSError):
        return None


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main():
    parser = argparse.ArgumentParser(description="Refresh the unified model catalog.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print a summary without writing the catalog or change log.",
    )
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).isoformat()

    # 1. Fetch OpenRouter
    or_data = fetch_openrouter()
    if or_data is None:
        print("[refresh-catalog] OpenRouter fetch failed. Aborting.", file=sys.stderr)
        sys.exit(1)
    or_models = or_data.get("data") or []
    if not isinstance(or_models, list):
        print("[refresh-catalog] OpenRouter response shape unexpected. Aborting.", file=sys.stderr)
        sys.exit(1)
    print(f"[refresh-catalog] OpenRouter: {len(or_models)} models fetched")

    # 2. Family classification rules
    family_rules = load_family_classification()

    # 3. Normalize OpenRouter entries
    catalog = [normalize_openrouter_entry(m, family_rules) for m in or_models]

    # 4. Enrich with intelligence_index from the curated model registry
    #    (replaces the prior direct AA API fetch; no API key needed)
    registry = load_model_registry()
    aa_enriched_count = 0
    media_appended = 0
    if registry is not None:
        aa_enriched_count = enrich_from_model_registry(catalog, registry)
        print(f"[refresh-catalog] model-registry enrichment: {aa_enriched_count} models scored")
        # 4b. Append AA media-leaderboard entries (image gen / image edit /
        #     text-to-video). They have no OpenRouter counterpart so they're
        #     additive — not merged into existing rows.
        media_appended = append_media_entries_from_registry(catalog, registry)
        if media_appended:
            print(f"[refresh-catalog] media-leaderboard entries appended: {media_appended}")

    # 5. Diff against previous catalog for free→paid detection
    old_catalog = load_existing_catalog()
    changes = detect_changes(catalog, old_catalog)
    if any(changes.values()):
        print(f"[refresh-catalog] changes detected: "
              f"new={len(changes['new'])} retired={len(changes['retired'])} "
              f"free_to_paid={len(changes['free_to_paid'])} "
              f"paid_to_free={len(changes['paid_to_free'])}")

    # 6. Compose the catalog file
    output = {
        "_schema_version": 1,
        "_refreshed_at": timestamp,
        "_sources": {
            "openrouter": {
                "url": OPENROUTER_URL,
                "model_count": len(or_models),
            },
            "model_registry": {
                "path": _display_path(MODEL_REGISTRY_PATH),
                "enriched_count": aa_enriched_count,
                "skipped": registry is None,
            },
        },
        "models": catalog,
    }

    if args.dry_run:
        print(json.dumps({
            "would_write_to": str(CATALOG_PATH),
            "model_count": len(catalog),
            "free_count": sum(1 for m in catalog if m.get("is_free")),
            "vision_capable_count": sum(1 for m in catalog if m.get("vision_capable")),
            "aa_enriched_count": aa_enriched_count,
            "changes": changes,
        }, indent=2))
        return

    # 7. Write atomically
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CATALOG_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")
    tmp_path.replace(CATALOG_PATH)
    print(f"[refresh-catalog] Wrote {CATALOG_PATH}")

    # 8. Append change log
    append_change_log(changes, timestamp)
    if any(changes.values()):
        print(f"[refresh-catalog] Appended change record to {CHANGES_PATH}")


if __name__ == "__main__":
    main()
