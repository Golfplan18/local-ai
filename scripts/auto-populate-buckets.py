#!/usr/bin/env python3
"""Auto-populate model buckets in routing-config.json from the OpenRouter
catalog.

Used by the install script (`install.py`) to land a working configuration
with zero user input beyond the OpenRouter API key. Also callable manually
to re-populate after a `refresh-openrouter.py` run if the user wants the
defaults refreshed.

Rules (per the Install Script Overhaul project plan):

  - `premium` bucket: vendor-tier flagship models (Opus, GPT-5,
    Gemini-3-Pro, etc.). 25B parameter floor enforced.
  - `mid`     bucket: vendor-tier mid models (Sonnet, GPT-4.1, etc.).
    25B parameter floor enforced.
  - `fast`    bucket: vendor-tier fast models (Haiku, mini/nano, etc.).
    No parameter floor — utility-tier slots use this bucket and small
    models are fine for step1_cleanup / classification.
  - `free`    bucket: cost == $0 only. No parameter floor. Sorted by
    parameter count descending so the most capable free model lands
    first.
  - `image_extracts` slot: free vision-capable 25B+ first, else
    cheapest paid vision-capable 25B+. Surfaces a paid-default note
    in the post-install summary when no free option exists.

Selection within a bucket:
  1. Filter catalog to text-output, text-input models.
  2. Apply tier-pattern regex.
  3. Apply 25B floor (premium / mid / image_extracts only).
  4. Sort by: free first, then ascending prompt cost, then descending
     context_length, then preferred-vendor order, then id.
  5. Take top N (default N=2 per bucket so the slot cascade has a
     fallback within the bucket).

Output:
  Dict with `buckets` (mapping bucket name → list of model ids),
  `image_extracts_pick` (single id + paid-flag), and `summary` (list of
  human-readable lines for the post-install summary).

CLI usage:
  python3 auto-populate-buckets.py             # print picks (dry-run)
  python3 auto-populate-buckets.py --apply     # POST to /config/routing/buckets
  python3 auto-populate-buckets.py --catalog <path> --patterns <path>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

# ── Catalog + patterns paths ────────────────────────────────────────────────
DEFAULT_CATALOG = os.path.expanduser("~/ora/config/openrouter-catalog.json")
DEFAULT_PATTERNS = os.path.expanduser("~/ora/config/vendor-tier-patterns.json")
DEFAULT_ROUTING = os.path.expanduser("~/ora/config/routing-config.json")

# ── Tier registry ───────────────────────────────────────────────────────────
WORKHORSE_TIERS = ("premium", "mid", "fast", "free")
PARAM_FLOOR_TIERS = frozenset({"premium", "mid"})  # 25B floor enforced
DEFAULT_PARAM_FLOOR_B = 25  # billions of parameters


def load_json(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# ── Catalog filters ─────────────────────────────────────────────────────────
def is_text_output(model: dict) -> bool:
    return model.get("modality") == "text"


def accepts_text(model: dict) -> bool:
    mods = model.get("input_modalities") or []
    return "text" in mods


def accepts_image(model: dict) -> bool:
    return bool(model.get("accepts_image"))


def is_free(model: dict) -> bool:
    p = model.get("pricing_per_million") or {}
    return (p.get("prompt") or 0) == 0 and (p.get("completion") or 0) == 0


def prompt_cost(model: dict) -> float:
    return float((model.get("pricing_per_million") or {}).get("prompt") or 0)


# ── Param-count estimation ──────────────────────────────────────────────────
_PARAM_FROM_NAME_RES = (
    # "qwen3.5-122b-a10b" — total/active MoE, take total
    re.compile(r"(\d+(?:\.\d+)?)\s*[bB](?:-a\d+[bB])?\b"),
    # "70B" / "70b" standalone
    re.compile(r"\b(\d+(?:\.\d+)?)[bB]\b"),
)


def estimate_param_count_b(model: dict) -> Optional[float]:
    """Return estimated parameter count in BILLIONS, or None when unknown.

    Heuristic from the model id (OpenRouter doesn't expose param counts
    consistently). Vendor-known flagships (claude-opus, gpt-5, etc.)
    return a synthetic high value so they pass the 25B floor without
    requiring a numeric match. Returns None for ambiguous cases — the
    caller decides how to handle (typically: include unless the model
    is in the param_floor_25b denylist).
    """
    mid = (model.get("id") or "").lower()

    # Known-large flagships without param numbers in the name
    if any(s in mid for s in [
        "claude-opus", "claude-sonnet", "gpt-5", "gpt-4o", "gpt-4-1",
        "gemini-pro", "gemini-3-pro", "gemini-flash", "gemini-2-",
        "grok-4", "o1", "o3", "o4", "deepseek-r1", "deepseek-v3",
        "kimi-k2", "mimo-v2", "magistral", "qwen3.6-plus", "qwen3-plus",
    ]):
        # Synthetic high value — these all exceed 25B in practice
        return 200.0

    for rx in _PARAM_FROM_NAME_RES:
        m = rx.search(mid)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def hits_floor(model: dict, patterns: dict, floor_b: float = DEFAULT_PARAM_FLOOR_B) -> bool:
    """True when the model meets the parameter floor; False when below."""
    mid = (model.get("id") or "").lower()

    # Explicit small-model markers from vendor-tier-patterns.json
    floor_block_patterns = (patterns.get("param_floor_25b") or {}).get("patterns") or []
    for p in floor_block_patterns:
        if re.search(p, mid):
            return False

    est = estimate_param_count_b(model)
    if est is None:
        # Unknown: include rather than over-exclude. Better to risk a borderline
        # pick than reject a capable model whose vendor doesn't publish param counts.
        return True
    return est >= floor_b


# ── Tier matching ───────────────────────────────────────────────────────────
def matches_any(patterns: list, text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def matches_tier(model: dict, patterns: dict, tier: str) -> bool:
    if tier == "free":
        return is_free(model)
    key = f"{tier}_tier_patterns"
    rxs = patterns.get(key) or []
    return matches_any(rxs, (model.get("id") or "").lower())


def vendor_rank(vendor: str, patterns: dict) -> int:
    """Lower rank = more preferred. Unknown vendor goes last."""
    order = patterns.get("preferred_vendor_order") or []
    v = (vendor or "").lower()
    try:
        return order.index(v)
    except ValueError:
        return len(order) + 1


def is_denylisted(model: dict, patterns: dict) -> bool:
    deny = patterns.get("denylist") or {}
    if (model.get("id") in (deny.get("model_ids") or [])):
        return True
    if (model.get("vendor") in (deny.get("vendor_ids") or [])):
        return True
    return False


# ── Selection ───────────────────────────────────────────────────────────────
def candidates_for_tier(
    catalog_models: list,
    patterns: dict,
    tier: str,
    require_vision: bool = False,
) -> list:
    """Return ordered list of candidate models for a tier.

    Order: free-first, then ascending cost, then descending context_length,
    then preferred-vendor rank, then id (deterministic tiebreaker).
    """
    out = []
    for m in catalog_models:
        if not is_text_output(m):
            continue
        if not accepts_text(m):
            continue
        if require_vision and not accepts_image(m):
            continue
        if is_denylisted(m, patterns):
            continue
        if not matches_tier(m, patterns, tier):
            continue
        if tier in PARAM_FLOOR_TIERS and not hits_floor(m, patterns):
            continue
        if require_vision and not hits_floor(m, patterns):
            continue  # image_extracts always enforces the floor
        out.append(m)

    out.sort(key=lambda m: (
        0 if is_free(m) else 1,
        prompt_cost(m),
        -(m.get("context_length") or 0),
        vendor_rank(m.get("vendor"), patterns),
        m.get("id") or "",
    ))
    return out


def pick_bucket(
    catalog_models: list,
    patterns: dict,
    tier: str,
    n: int = 2,
    exclude: Optional[set] = None,
) -> list:
    """Return up to N model ids for a workhorse bucket. Excludes any ids
    in `exclude` for cross-bucket diversity."""
    excluded = set(exclude or ())
    cands = candidates_for_tier(catalog_models, patterns, tier)
    picks = []
    for m in cands:
        mid = m.get("id")
        if mid in excluded:
            continue
        picks.append(mid)
        excluded.add(mid)
        if len(picks) >= n:
            break
    return picks


def pick_image_extracts(catalog_models: list, patterns: dict) -> dict:
    """Return {'id': model_id, 'is_paid': bool, 'note': str} for the
    image_extracts slot. Falls back to lowest-cost paid vision model
    when no free vision option exists."""
    vision_text_models = [
        m for m in catalog_models
        if is_text_output(m) and accepts_image(m) and accepts_text(m)
        and not is_denylisted(m, patterns)
        and hits_floor(m, patterns)
    ]
    # Free first
    free_vision = [m for m in vision_text_models if is_free(m)]
    if free_vision:
        free_vision.sort(key=lambda m: (
            -(m.get("context_length") or 0),
            vendor_rank(m.get("vendor"), patterns),
            m.get("id") or "",
        ))
        return {
            "id": free_vision[0].get("id"),
            "is_paid": False,
            "note": "Free vision-capable model selected.",
        }
    paid_vision = sorted(vision_text_models, key=lambda m: (
        prompt_cost(m),
        -(m.get("context_length") or 0),
        vendor_rank(m.get("vendor"), patterns),
        m.get("id") or "",
    ))
    if paid_vision:
        m = paid_vision[0]
        return {
            "id": m.get("id"),
            "is_paid": True,
            "note": (
                "No free vision-capable model with 25B+ parameters is "
                "currently available on OpenRouter. Defaulted to the "
                f"lowest-cost paid option (${prompt_cost(m):.3f}/M prompt)."
            ),
        }
    return {
        "id": None,
        "is_paid": False,
        "note": (
            "WARNING: no vision-capable text model found in the OpenRouter "
            "catalog. Image-input prompts will fall through to text-only "
            "analysis. Re-run `refresh-openrouter.py` to refresh the catalog "
            "or configure a custom image_extracts slot in routing-config.json."
        ),
    }


# ── Top-level driver ────────────────────────────────────────────────────────
def populate_all(catalog: dict, patterns: dict, n_per_bucket: int = 2) -> dict:
    """Returns {buckets: {...}, image_extracts: {...}, summary: [...]}."""
    catalog_models = catalog.get("models") or []
    buckets = {}
    picked_so_far = set()
    for tier in WORKHORSE_TIERS:
        picks = pick_bucket(
            catalog_models, patterns, tier,
            n=n_per_bucket,
            exclude=picked_so_far,
        )
        buckets[tier] = picks
        picked_so_far.update(picks)

    img = pick_image_extracts(catalog_models, patterns)

    summary = []
    for tier in WORKHORSE_TIERS:
        members = buckets[tier]
        if members:
            summary.append(f"  {tier:<8} → {', '.join(members)}")
        else:
            summary.append(f"  {tier:<8} → (no eligible models found)")
    summary.append("")
    if img["id"]:
        tag = "paid" if img["is_paid"] else "free"
        summary.append(f"  image_extracts → {img['id']} ({tag})")
    if img["note"]:
        summary.append(f"     ↳ {img['note']}")

    return {"buckets": buckets, "image_extracts": img, "summary": summary}


# ── Apply to routing-config ─────────────────────────────────────────────────
def apply_to_routing(result: dict, routing_path: str = DEFAULT_ROUTING) -> None:
    """Merge the picks into routing-config.json. Preserves any existing
    bucket members the user has already added.

    Does NOT touch endpoints[] directly — relies on
    server.py::_sync_endpoints_from_buckets to synthesize endpoint
    entries from the bucket member list when the config is reloaded.
    """
    cfg = load_json(routing_path)
    cfg_buckets = cfg.get("buckets", {})

    # Workhorse buckets: replace if currently empty, otherwise prepend our
    # picks (so user's prior picks stay; ours land at top).
    for tier, picks in result["buckets"].items():
        existing = list(cfg_buckets.get(tier) or [])
        merged = list(picks)
        for e in existing:
            if e and e not in merged:
                merged.append(e)
        cfg_buckets[tier] = merged

    cfg["buckets"] = cfg_buckets

    # image_extracts slot
    slots = cfg.get("slots") or {}
    ie_slot = slots.get("image_extracts") or {}
    img_pick = result["image_extracts"]["id"]
    if img_pick:
        # Preserve any existing per-pipeline entries; only set when empty.
        if "interactive" not in ie_slot or not ie_slot["interactive"]:
            ie_slot["interactive"] = f"openrouter:{img_pick}"
        if "agent" not in ie_slot or not ie_slot["agent"]:
            ie_slot["agent"] = f"openrouter:{img_pick}"
        slots["image_extracts"] = ie_slot
    cfg["slots"] = slots

    with open(routing_path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


# ── CLI entry ───────────────────────────────────────────────────────────────
def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", default=DEFAULT_CATALOG)
    p.add_argument("--patterns", default=DEFAULT_PATTERNS)
    p.add_argument("--routing", default=DEFAULT_ROUTING)
    p.add_argument("--apply", action="store_true",
                   help="Write picks into routing-config.json")
    p.add_argument("--n", type=int, default=2,
                   help="Picks per bucket (default 2)")
    args = p.parse_args(argv)

    catalog = load_json(args.catalog)
    patterns = load_json(args.patterns)
    result = populate_all(catalog, patterns, n_per_bucket=args.n)

    print("=== Auto-populate buckets ===")
    print(f"Catalog: {args.catalog}")
    print(f"Patterns: {args.patterns}")
    print(f"Models in catalog: {len(catalog.get('models') or [])}")
    print()
    for line in result["summary"]:
        print(line)

    if args.apply:
        apply_to_routing(result, args.routing)
        print()
        print(f"✓ Applied to {args.routing}")
        print("  Reload Ora router via POST /config/routing or restart the server.")
    else:
        print()
        print("Dry-run — pass --apply to write to routing-config.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
