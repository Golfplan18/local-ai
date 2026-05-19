#!/usr/bin/env python3
"""Refresh the unified model catalog (install Chunk 4).

Fetches OpenRouter and (optionally) Artificial Analysis catalogs, merges
them into a single ``config/model-catalog.json`` that the auto-populate
engine (Chunk 5) consumes. Standardizes cost to $/M blended tokens using
a 3:1 input:output ratio (matching AA's published methodology). Assigns
each cloud model a ``family_tier`` and ``size_bucket`` via
``config/family-classification.json`` for closed-proprietary models whose
parameter counts aren't published.

This is a new tool independent of ``scripts/refresh-openrouter.py`` —
that tool continues to maintain ``config/openrouter-catalog.json`` for
existing readers (server.py, the bucket selector, etc.). The new
``model-catalog.json`` is consumed only by the new auto-populate engine.

API keys (read from env):
    OPENROUTER_API_KEY   — optional. The /models endpoint is public, but
                            authenticated requests get higher rate limits.
    AA_API_KEY           — optional. When set, enriches the catalog with
                            Artificial Analysis intelligence index +
                            blended cost. When absent, AA enrichment is
                            skipped with a warning; the catalog still
                            ships with OpenRouter pricing only.

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

CATALOG_PATH = CONFIG_DIR / "model-catalog.json"
FAMILY_CLASS_PATH = CONFIG_DIR / "family-classification.json"
CHANGES_PATH = DATA_DIR / "model-catalog-changes.jsonl"

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
AA_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"

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


def fetch_artificial_analysis() -> dict | None:
    """Fetch the AA model list. Returns the parsed JSON or None on error
    (also returned when no AA_API_KEY is set in the environment)."""
    api_key = os.environ.get("AA_API_KEY", "").strip()
    if not api_key:
        print(
            "[refresh-catalog] AA_API_KEY not set; skipping Artificial Analysis "
            "enrichment. Catalog will ship with OpenRouter pricing only.",
            file=sys.stderr,
        )
        return None
    req = urllib.request.Request(
        AA_URL,
        headers={"x-api-key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"[refresh-catalog] Artificial Analysis fetch failed: {exc}", file=sys.stderr)
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
        "aa_intelligence_index": None,    # filled in by AA pass when available
        "aa_blended_per_m": None,         # filled in by AA pass when available
        "family_tier": family_tier,
        "size_bucket": size_bucket,
        "is_free": is_free,
    }


def enrich_with_aa(catalog: list[dict], aa_data: dict) -> int:
    """Add AA intelligence_index + blended_cost to matching catalog entries.

    Returns the count of entries enriched (with non-null values, not
    just name matches).

    AA's actual schema (verified 2026-05-19):
        {"status": 200, "data": [{
            "id": "<uuid>", "name": "<display>", "slug": "<slug>",
            "evaluations": {
                "artificial_analysis_intelligence_index": 78.0,
                "artificial_analysis_coding_index": ...,
                ...
            },
            "pricing": {
                "price_1m_blended_3_to_1": 7.5,
                "price_1m_input_tokens": 5.0,
                "price_1m_output_tokens": 15.0,
            },
            ...
        }, ...]}

    Matching: AA's slug ("kimi-k2-thinking") aligns closely with the
    tail of OpenRouter slugs ("moonshotai/kimi-k2-thinking"). We try
    direct slug match first (after stripping the OR provider prefix),
    then fall back to name-substring overlap.
    """
    rows = aa_data.get("data") or aa_data.get("models") or []
    if not isinstance(rows, list):
        return 0

    # Build both lookups for matching: by slug and by name.
    aa_by_slug = {}
    aa_by_name = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = (row.get("slug") or "").strip().lower()
        if slug:
            aa_by_slug[slug] = row
        name = (row.get("name") or "").strip().lower()
        if name:
            aa_by_name[name] = row

    def _extract(row: dict) -> tuple[float | None, float | None]:
        """Pull intelligence + blended cost from the nested schema."""
        evals = row.get("evaluations") or {}
        pricing = row.get("pricing") or {}
        # Primary fields (AA's canonical names as of 2026-05-19)
        intelligence = evals.get("artificial_analysis_intelligence_index")
        blended = pricing.get("price_1m_blended_3_to_1")
        # Defensive fallbacks in case AA renames a field in the future
        if intelligence is None:
            intelligence = (
                evals.get("intelligence_index")
                or evals.get("artificial_analysis_index")
                or row.get("intelligence_index")
            )
        if blended is None:
            blended = (
                pricing.get("blended_cost_usd_per_million_tokens")
                or pricing.get("blended_per_m")
                or row.get("blended_cost")
            )
        return intelligence, blended

    enriched = 0
    for entry in catalog:
        or_slug = entry.get("openrouter_slug") or entry.get("id") or ""
        # OR slugs look like "provider/model-name"; AA slugs are just
        # "model-name". Strip the provider prefix for matching.
        slug_tail = or_slug.split("/", 1)[-1].lower()
        display_lower = (entry.get("display_name") or "").lower()

        match = aa_by_slug.get(slug_tail)
        if match is None:
            # Try slug substring match (AA "kimi-k2-thinking" inside
            # OR slug "moonshotai/kimi-k2-thinking")
            for aa_slug, row in aa_by_slug.items():
                if aa_slug in slug_tail or slug_tail in aa_slug:
                    match = row
                    break
        if match is None:
            # Name substring fallback
            match = aa_by_name.get(display_lower)
            if match is None:
                for name, row in aa_by_name.items():
                    if name in display_lower or display_lower in name:
                        match = row
                        break

        if match:
            intelligence, blended = _extract(match)
            if intelligence is not None or blended is not None:
                entry["aa_intelligence_index"] = intelligence
                entry["aa_blended_per_m"] = blended
                enriched += 1

    return enriched


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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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

    # 4. Enrich with Artificial Analysis (optional)
    aa_data = fetch_artificial_analysis()
    aa_enriched_count = 0
    if aa_data is not None:
        aa_enriched_count = enrich_with_aa(catalog, aa_data)
        print(f"[refresh-catalog] Artificial Analysis: {aa_enriched_count} models enriched")

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
            "artificial_analysis": {
                "url": AA_URL,
                "enriched_count": aa_enriched_count,
                "skipped": aa_data is None,
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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
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
