#!/usr/bin/env python3
"""Auto-populate a named configuration from the model catalog (install Chunk 5).

Algorithm (per the install plan):
  Per slot, against its size bucket:
    1. Pareto pass — remove strictly dominated models (worse on both cost and
       intelligence than another model in the same bucket).
    2. Percentage floor — keep models scoring at least floor_pct% of the
       top intelligence in the (post-Pareto) bucket.
    3. Cost ceiling (Budget preset) — drop models above the ceiling.
    4. Sort by cost ascending.
    5. Return top N (3 for workhorse slots, 2 for utility).

  Budget preset has a loosening rule: if fewer than top-N pass both bounds,
  loosen the floor by 10pp at a time, then loosen the ceiling 2x, until
  top-N pass or the bucket is exhausted. Loosening events surface in
  output metadata.

  Free preset operates over a parallel free-models list — no cost math,
  sort by intelligence descending, return top N. Free models are never
  mixed into paid ranking.

  Vision substitute: a single model id per configuration, picked from
  the vision_capable subset of the configured size bucket. Threaded into
  every cell's vision_substitute field.

Inputs:
    config/model-catalog.json          — produced by scripts/refresh-catalog.py
    config/configuration-presets.json  — preset and slot specs

Output:
    config/configurations/<name>.json  — the auto-populated configuration

Usage:
    python3 scripts/auto-populate-configuration.py optimum user-pipeline
    python3 scripts/auto-populate-configuration.py budget my-budget-config
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
CONFIGURATIONS_DIR = CONFIG_DIR / "configurations"
CATALOG_PATH = CONFIG_DIR / "model-catalog.json"
PRESETS_PATH = CONFIG_DIR / "configuration-presets.json"


# ─── Algorithm primitives ────────────────────────────────────────────────


def intelligence_of(model: dict) -> float:
    """Get the AA intelligence index; 0 if absent.

    Models without AA enrichment sort to the bottom — they're admissible
    but not preferred. When the entire bucket lacks AA data the relative
    ordering collapses and the algorithm falls back to cost-only sorting.
    """
    val = model.get("aa_intelligence_index")
    return float(val) if val is not None else 0.0


def cost_of(model: dict) -> float:
    """Get the blended cost ($/M tokens). math.inf when missing — sorts to
    the bottom on cost-ascending."""
    pricing = model.get("openrouter_pricing", {}) or {}
    val = pricing.get("blended_per_m")
    return float(val) if val is not None else math.inf


def cost_of_media(model: dict) -> float:
    """Get the image-generation cost ($/1k images). math.inf when missing.

    Image-gen models price per-image rather than per-token; ``image_pricing``
    is populated by the AA per-model detail-page scrape (see Models pane
    refresh path). Models without pricing data sort to the bottom on
    cost-ascending — same admissible-but-not-preferred treatment chat models
    without ``blended_per_m`` get.
    """
    pricing = model.get("image_pricing") or {}
    val = pricing.get("per_1k_images")
    return float(val) if val is not None else math.inf


def pareto_filter(candidates: list[dict], cost_fn=cost_of) -> list[dict]:
    """Remove strictly dominated models.

    A model A is dominated by B if B has higher (or equal) intelligence
    AND lower (or equal) cost, with at least one strict inequality.
    Returns the Pareto-frontier subset of candidates. ``cost_fn`` picks
    the cost axis — ``cost_of`` for chat (tokens) or ``cost_of_media``
    for image-gen ($/1k images).
    """
    frontier = []
    for cand in candidates:
        c_int = intelligence_of(cand)
        c_cost = cost_fn(cand)
        dominated = False
        for other in candidates:
            if other is cand:
                continue
            o_int = intelligence_of(other)
            o_cost = cost_fn(other)
            # other dominates cand if other is no worse on both
            # and strictly better on at least one
            if o_int >= c_int and o_cost <= c_cost and (o_int > c_int or o_cost < c_cost):
                dominated = True
                break
        if not dominated:
            frontier.append(cand)
    return frontier


def apply_floor(candidates: list[dict], floor_pct: float | None) -> list[dict]:
    """Drop models below floor_pct% of the top intelligence in the bucket.

    floor_pct=None disables the filter (Premium preset).
    """
    if floor_pct is None or not candidates:
        return candidates
    top = max(intelligence_of(m) for m in candidates)
    if top <= 0:
        # No intelligence data — can't apply floor; return all
        return candidates
    threshold = top * (floor_pct / 100.0)
    return [m for m in candidates if intelligence_of(m) >= threshold]


def apply_cost_ceiling(candidates: list[dict], ceiling: float | None, cost_fn=cost_of) -> list[dict]:
    """Drop models with cost above the ceiling.

    ceiling=None disables (Premium / Optimum / Free).
    """
    if ceiling is None:
        return candidates
    return [m for m in candidates if cost_fn(m) <= ceiling]


def filter_by_size_bucket(candidates: list[dict], size_bucket: str | None) -> list[dict]:
    """Restrict to a specific size_bucket. ``size_bucket=None`` skips
    the filter — used by the Fast slot, which selects on tokens/sec
    instead of parameter range."""
    if size_bucket is None:
        return candidates
    return [m for m in candidates if m.get("size_bucket") == size_bucket]


def filter_exclude_reasoning(candidates: list[dict], reasoning_ids: set[str]) -> list[dict]:
    """Drop reasoning / thinking models. Their hidden chain-of-thought
    output defeats the Fast slot's speed purpose."""
    if not reasoning_ids:
        return candidates
    return [m for m in candidates if m.get("id") not in reasoning_ids]


_NON_CHAT_OUTPUT_MODALITIES = {"audio", "video", "music", "speech"}


def filter_text_output(candidates: list[dict]) -> list[dict]:
    """Drop models whose output includes audio, video, music, or speech.
    Some entries mis-classify as ``chat`` in the catalog because their
    input includes text — Lyria (text→audio music) is the canonical
    case: it carries ``output_modalities=['text', 'audio']`` and slips
    past a naive 'text in modalities' check. Reject any entry that
    declares a non-chat output modality at all. Catalog entries with
    no ``output_modalities`` field pass through (admit on incomplete
    metadata rather than reject a real chat model)."""
    def is_chat_output(m):
        mods = m.get("output_modalities")
        if not mods:
            return True
        return not any(mod in _NON_CHAT_OUTPUT_MODALITIES for mod in mods)
    return [m for m in candidates if is_chat_output(m)]


def filter_by_category(candidates: list[dict], category: str) -> list[dict]:
    """Restrict to a specific category. Entries with no ``category``
    field are treated as ``chat`` (the existing 358-model corpus from
    OpenRouter)."""
    return [m for m in candidates if (m.get("category") or "chat") == category]


def filter_paid(candidates: list[dict]) -> list[dict]:
    """Paid = NOT free by either signal (catalog flag OR :free suffix).

    Symmetric with filter_free — together they partition the catalog
    cleanly so a paid preset (Premium/Optimum/Budget) can't accidentally
    pick a :free variant just because its is_free flag was unset."""
    return [
        m for m in candidates
        if not (m.get("is_free", False) or m.get("id", "").endswith(":free"))
    ]


def filter_free(candidates: list[dict]) -> list[dict]:
    """Free = the catalog marked it free, OR the id ends in ":free".

    The :free-suffix recognition matters because most free-tier
    entries on OpenRouter are `:free` variants of paid base models
    (e.g. `meta-llama/llama-3.3-70b-instruct:free`). The catalog's
    is_free flag is set inconsistently across vendors, so the suffix
    check picks up models the flag misses — and the suffix is itself
    OpenRouter's authoritative signal."""
    return [
        m for m in candidates
        if m.get("is_free", False) or m.get("id", "").endswith(":free")
    ]


def filter_vision(candidates: list[dict]) -> list[dict]:
    return [m for m in candidates if m.get("vision_capable", False)]


def filter_reachable(candidates: list[dict], unreachable_ids: set[str]) -> list[dict]:
    """Drop models the reachability probe (sync_model_registry.py reach)
    has confirmed as unreachable (HTTP 404 / 410 / 400 not_token_limit on
    a 1-prompt completion). Rate-limited and inconclusive verdicts are NOT
    excluded — those models still have working endpoints; the fallback
    chain handles transient 429s at runtime."""
    if not unreachable_ids:
        return candidates
    return [m for m in candidates if m.get("id") not in unreachable_ids]


def sort_by_cost_ascending(candidates: list[dict], cost_fn=cost_of) -> list[dict]:
    return sorted(candidates, key=cost_fn)


def sort_by_intelligence_descending(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=intelligence_of, reverse=True)


def sort_by_tokens_per_sec_descending(candidates: list[dict], tps_map: dict[str, float]) -> list[dict]:
    """Sort by output tokens/sec descending. Models without tps data sink
    to the bottom. Used by the Fast slot to surface speed-tier models
    independent of intelligence ranking."""
    return sorted(
        candidates,
        key=lambda m: tps_map.get(m.get("id", ""), -math.inf),
        reverse=True,
    )


def _vendor_key(model: dict) -> str:
    """Normalised vendor key for diversity comparisons.

    Prefers the catalog's ``provider`` field when it names a real maker;
    falls back to the slash-prefix of the id when ``provider`` is generic
    (``artificial-analysis`` on the 221 AA-only entries). Leading ``~``
    on AA-direct-vendor variants (``~anthropic`` etc.) is stripped so
    they match their non-tilde siblings."""
    provider = (model.get("provider") or "").lower()
    if provider and provider != "artificial-analysis":
        return provider.lstrip("~")
    mid = model.get("id") or ""
    if "/" in mid:
        return mid.split("/", 1)[0].lower().lstrip("~")
    return mid.lower()


def _apply_vendor_diversity(candidates: list[dict], excluded_vendors: set | None) -> list[dict]:
    """Soft vendor-diversity filter. When excluded_vendors is set, drop any
    candidate whose vendor key is in the excluded set — but if that empties
    the pool, drop the filter rather than return nothing (the user picked
    soft fallback: prefer vendor-diverse, accept same-vendor when impossible)."""
    if not excluded_vendors:
        return candidates
    filtered = [m for m in candidates if _vendor_key(m) not in excluded_vendors]
    return filtered or candidates


# ─── Per-slot picker ─────────────────────────────────────────────────────


def pick_for_paid_slot(
    catalog: list[dict],
    size_bucket: str | None,
    top_n: int,
    floor_pct: float | None,
    cost_ceiling: float | None,
    loosening: bool,
    excluded_ids: set | None = None,
    excluded_vendors: set | None = None,
    vision_only: bool = False,
    sort_by: str = "cost_asc",
    unreachable_ids: set[str] | None = None,
    tokens_per_sec: dict[str, float] | None = None,
    reasoning_model_ids: set[str] | None = None,
    exclude_reasoning_models: bool = False,
) -> tuple[list[dict], list[str]]:
    """Pick top-N models for a paid slot.

    ``sort_by`` controls the final selection order after filtering:
      "cost_asc"             — cheapest first (default; used by Optimum/Budget)
      "intelligence_desc"    — smartest first (used by Premium for Big)
      "tokens_per_sec_desc"  — fastest first (used by Fast slot)

    ``exclude_reasoning_models``: when True, drop entries flagged
    ``reasoning_model=True`` in the registry. Fast slot uses this.

    Returns (picks, loosening_notes).
    """
    excluded_ids = excluded_ids or set()
    # Restrict to chat models first. Pre-Fast slots got this implicitly via
    # size_bucket (only chat models carry size_bucket "small"/"large"); Fast
    # passes size_bucket=None so image-gen / video models would otherwise
    # leak in and dominate intelligence-floor checks via their Elo scores.
    candidates = filter_by_category(catalog, "chat")
    # Belt-and-suspenders: catalog mis-classifies some audio/music
    # models (Lyria) as chat because they take text input. Drop anything
    # whose output isn't text. See filter_text_output.
    candidates = filter_text_output(candidates)
    candidates = filter_paid(candidates)
    candidates = filter_by_size_bucket(candidates, size_bucket)
    candidates = filter_reachable(candidates, unreachable_ids or set())
    if exclude_reasoning_models and reasoning_model_ids:
        candidates = filter_exclude_reasoning(candidates, reasoning_model_ids)
    if vision_only:
        candidates = filter_vision(candidates)
    candidates = [m for m in candidates if m["id"] not in excluded_ids]
    candidates = _apply_vendor_diversity(candidates, excluded_vendors)

    # Pareto-filter against (intelligence, cost). Skip for tokens_per_sec_desc
    # selection — Pareto on intel/cost is the wrong frontier when speed is the
    # axis, and leaves slow-but-Pareto-optimal models in the Fast fallback chain.
    if sort_by != "tokens_per_sec_desc":
        candidates = pareto_filter(candidates)

    loosening_notes: list[str] = []
    current_floor = floor_pct
    current_ceiling = cost_ceiling

    if sort_by == "tokens_per_sec_desc":
        sort_fn = lambda c: sort_by_tokens_per_sec_descending(c, tokens_per_sec or {})
    elif sort_by == "intelligence_desc":
        sort_fn = sort_by_intelligence_descending
    else:
        sort_fn = sort_by_cost_ascending

    for attempt in range(10):  # bound the loosening loop
        floored = apply_floor(candidates, current_floor)
        ceilinged = apply_cost_ceiling(floored, current_ceiling)
        picks = sort_fn(ceilinged)[:top_n]

        if len(picks) >= top_n or not loosening:
            return picks, loosening_notes

        # Budget loosening: floor first (by 10pp), then ceiling (2x)
        if current_floor is not None and current_floor > 10:
            current_floor -= 10
            loosening_notes.append(f"floor loosened to {current_floor:.0f}% (attempt {attempt + 1})")
            continue

        if current_ceiling is not None:
            current_ceiling *= 2
            loosening_notes.append(f"ceiling loosened to ${current_ceiling:.2f}/M (attempt {attempt + 1})")
            continue

        # Both bounds at their limits — return what we have
        loosening_notes.append("bounds exhausted; returning fewer than top-N")
        return picks, loosening_notes

    return picks, loosening_notes


def pick_for_free_slot(
    catalog: list[dict],
    size_bucket: str | None,
    top_n: int,
    excluded_ids: set | None = None,
    excluded_vendors: set | None = None,
    vision_only: bool = False,
    unreachable_ids: set[str] | None = None,
    sort_by: str = "intelligence_desc",
    tokens_per_sec: dict[str, float] | None = None,
    reasoning_model_ids: set[str] | None = None,
    exclude_reasoning_models: bool = False,
) -> list[dict]:
    """Pick top-N free models. No cost math.

    ``sort_by`` defaults to ``intelligence_desc`` (the historical Free
    behavior); Fast slot overrides to ``tokens_per_sec_desc``.

    size_bucket=None means "any free model" (Free preset doesn't require
    bucket conformance because free models are scarcer).
    """
    excluded_ids = excluded_ids or set()
    # Same chat-category + text-output guards as pick_for_paid_slot.
    candidates = filter_by_category(catalog, "chat")
    candidates = filter_text_output(candidates)
    candidates = filter_free(candidates)
    candidates = filter_reachable(candidates, unreachable_ids or set())
    if exclude_reasoning_models and reasoning_model_ids:
        candidates = filter_exclude_reasoning(candidates, reasoning_model_ids)
    if size_bucket:
        # Soft filter — fall back to all free if bucket-conformance is empty
        bucketed = filter_by_size_bucket(candidates, size_bucket)
        if bucketed:
            candidates = bucketed
    if vision_only:
        candidates = filter_vision(candidates)
    candidates = [m for m in candidates if m["id"] not in excluded_ids]
    candidates = _apply_vendor_diversity(candidates, excluded_vendors)
    # Same reason as pick_for_paid_slot: skip Pareto when selecting on speed.
    if sort_by != "tokens_per_sec_desc":
        candidates = pareto_filter(candidates)
    if sort_by == "tokens_per_sec_desc":
        return sort_by_tokens_per_sec_descending(candidates, tokens_per_sec or {})[:top_n]
    return sort_by_intelligence_descending(candidates)[:top_n]


FREE_MEDIA_PROXY_CEILING = 10.0
"""Free preset fallback: when no zero-cost image-gen models exist (or fewer
than top-N do), admit models under this $/1k-images ceiling. Picked to be
well below the median $35/1k so the Free pool stays recognisably budget."""


def pick_for_media_slot(
    catalog: list[dict],
    category: str,
    top_n: int,
    mode: str = "paid_intelligence",
    floor_pct: float | None = None,
    cost_ceiling: float | None = None,
    sort_by: str = "cost_asc",
    excluded_ids: set | None = None,
    excluded_vendors: set | None = None,
) -> list[dict]:
    """Pick top-N image-gen models, mirroring ``pick_for_paid_slot`` semantics
    against per-1k-images cost rather than per-M-tokens cost.

    ``mode`` switches the algorithm path:

      "paid_intelligence" — Pareto pass on (Elo, $/1k) → floor_pct% of top
                            Elo (when set) → cost ceiling (when set) →
                            sort by ``sort_by``. Used by Premium / Optimum /
                            Budget.
      "free_intelligence" — Restrict to per_1k_images == 0; if that returns
                            fewer than top_n, fall back to per_1k_images
                            <= FREE_MEDIA_PROXY_CEILING ($10/1k) as the
                            "cheap-enough-to-treat-as-free" pool. Pareto
                            pass + sort by intelligence descending.

    Models without ``image_pricing.per_1k_images`` get math.inf for cost
    (same admissible-but-not-preferred treatment chat models without
    blended_per_m get). They participate in Pareto + intelligence-desc
    sort but never pass a finite cost ceiling.
    """
    excluded_ids = excluded_ids or set()
    candidates = filter_by_category(catalog, category)
    candidates = [m for m in candidates if m["id"] not in excluded_ids]
    candidates = _apply_vendor_diversity(candidates, excluded_vendors)
    if not candidates:
        return []

    if mode == "free_intelligence":
        zero_cost = [m for m in candidates if cost_of_media(m) == 0]
        pool = zero_cost
        if len(pool) < top_n:
            # Fallback: admit models priced below the free-proxy ceiling
            # so the Free preset isn't capped at the handful of zero-cost
            # image models AA exposes today (3 as of the 2026-05 scrape).
            pool = [m for m in candidates if cost_of_media(m) <= FREE_MEDIA_PROXY_CEILING]
        pool = pareto_filter(pool, cost_fn=cost_of_media)
        return sort_by_intelligence_descending(pool)[:top_n]

    # paid_intelligence path
    candidates = pareto_filter(candidates, cost_fn=cost_of_media)
    candidates = apply_floor(candidates, floor_pct)
    candidates = apply_cost_ceiling(candidates, cost_ceiling, cost_fn=cost_of_media)
    if sort_by == "intelligence_desc":
        return sort_by_intelligence_descending(candidates)[:top_n]
    return sort_by_cost_ascending(candidates, cost_fn=cost_of_media)[:top_n]


def pick_vision_substitute(catalog: list[dict], size_bucket: str, preset_mode: str) -> str | None:
    """Pick a vision-capable model from the configured size bucket.

    For paid presets: lowest cost vision-capable in bucket.
    For free preset: highest intelligence vision-capable in bucket
    (cost is 0 for all candidates).
    """
    # Same chat + text-output guards as the chat-slot pickers — vision
    # substitute is the image-input handler for chat output, so audio /
    # music mis-classified entries don't belong here either.
    candidates = filter_by_category(catalog, "chat")
    candidates = filter_text_output(candidates)
    candidates = filter_vision(candidates)
    if preset_mode == "free_intelligence":
        candidates = filter_free(candidates)
    else:
        candidates = filter_paid(candidates)
    candidates = filter_by_size_bucket(candidates, size_bucket)
    if not candidates:
        return None
    candidates = pareto_filter(candidates)
    if preset_mode == "free_intelligence":
        candidates = sort_by_intelligence_descending(candidates)
    else:
        candidates = sort_by_cost_ascending(candidates)
    return candidates[0]["id"] if candidates else None


# ─── Cell shape ──────────────────────────────────────────────────────────


def picks_to_cell(picks: list[dict], vision_substitute: str | None) -> dict | None:
    """Convert top-N picks to the cell shape (primary + fallback + vision_substitute)."""
    if not picks:
        return None
    cell = {
        "primary": picks[0]["id"],
        "fallback": [p["id"] for p in picks[1:]],
    }
    if vision_substitute:
        cell["vision_substitute"] = vision_substitute
    return cell


# ─── Main population ─────────────────────────────────────────────────────


def populate_configuration(
    preset_name: str,
    catalog: list[dict],
    presets_config: dict,
    vision_only: bool | None = None,
    unreachable_ids: set[str] | None = None,
    tokens_per_sec: dict[str, float] | None = None,
    reasoning_model_ids: set[str] | None = None,
) -> dict:
    """Compute the full configuration dict for a given preset.

    ``vision_only``: when True, every slot picks only from vision-capable
    models. When False, text-only primaries are admissible (the
    vision_substitute field still carries a vision model for the image
    extraction fallback). When None, falls through to the preset's
    declared default (``vision_only`` field on the preset; defaults to
    False if absent).

    ``unreachable_ids``: set of model ids the reachability probe has
    confirmed as unreachable (HTTP 404 / 410 / non-token 400). These are
    filtered out of every paid / free pick. Rate-limited and inconclusive
    verdicts are NOT excluded — those endpoints still work, the fallback
    chain absorbs transient 429s at runtime.
    """
    presets = presets_config["presets"]
    slot_specs = presets_config["slot_specs"]
    vision_spec = presets_config.get("vision_substitute", {})

    if preset_name not in presets:
        raise ValueError(f"Unknown preset: {preset_name}. Known: {list(presets)}")
    preset = presets[preset_name]

    # vision_only resolution: CLI override > preset default > False
    effective_vision_only = vision_only if vision_only is not None else preset.get("vision_only", False)

    # Vision substitute (single id per configuration). Always vision-capable
    # regardless of the toggle — it's the fallback for image input even when
    # primary picks are vision-capable.
    vision_substitute = pick_vision_substitute(
        catalog,
        size_bucket=vision_spec.get("size_bucket", "large"),
        preset_mode=preset["mode"],
    )

    cells: dict = {}
    loosening_log: dict = {}

    def _pick(slot_section: str, slot_spec: dict) -> dict:
        section: dict = {}
        diversity = slot_spec.get("diversity_excluded", False)
        excluded_so_far: set = set()
        excluded_vendors_so_far: set = set()
        # Slots carrying a ``category`` field (e.g. image_generation) route
        # through the media picker, which sorts by Elo and ignores the
        # chat-only paid/free machinery. See pick_for_media_slot.
        slot_category = slot_spec.get("category")
        # The slot_spec may override the preset's sort_by — Fast does this
        # to force tokens_per_sec_desc across every preset. Same story for
        # exclude_reasoning_models. size_bucket is optional; None means
        # no parameter-bucket filter (Fast uses tps to bubble fast tier).
        slot_sort_by = slot_spec.get("sort_by") or preset.get("sort_by", "cost_asc")
        slot_exclude_reasoning = slot_spec.get("exclude_reasoning_models", False)
        slot_size_bucket = slot_spec.get("size_bucket")
        for cell_name in slot_spec["cells"]:
            notes: list = []
            if slot_category and slot_category != "chat":
                picks = pick_for_media_slot(
                    catalog,
                    category=slot_category,
                    top_n=slot_spec["top_n"],
                    mode=preset["mode"],
                    floor_pct=preset.get("floor_pct"),
                    cost_ceiling=preset.get("image_cost_ceiling_per_1k"),
                    sort_by=preset.get("sort_by", "cost_asc"),
                    excluded_ids=excluded_so_far if diversity else None,
                    excluded_vendors=excluded_vendors_so_far if diversity else None,
                )
                # Media cells don't carry a vision_substitute (the slot IS
                # the image-handling slot — no fallback needed).
                section[cell_name] = picks_to_cell(picks, None)
            elif preset["mode"] == "free_intelligence":
                picks = pick_for_free_slot(
                    catalog,
                    size_bucket=slot_size_bucket,
                    top_n=slot_spec["top_n"],
                    excluded_ids=excluded_so_far if diversity else None,
                    excluded_vendors=excluded_vendors_so_far if diversity else None,
                    vision_only=effective_vision_only,
                    unreachable_ids=unreachable_ids,
                    sort_by=slot_sort_by,
                    tokens_per_sec=tokens_per_sec,
                    reasoning_model_ids=reasoning_model_ids,
                    exclude_reasoning_models=slot_exclude_reasoning,
                )
                section[cell_name] = picks_to_cell(picks, vision_substitute)
            else:
                picks, notes = pick_for_paid_slot(
                    catalog,
                    size_bucket=slot_size_bucket,
                    top_n=slot_spec["top_n"],
                    floor_pct=preset.get("floor_pct"),
                    cost_ceiling=preset.get("cost_ceiling_per_m"),
                    loosening=preset.get("loosening", False),
                    excluded_ids=excluded_so_far if diversity else None,
                    excluded_vendors=excluded_vendors_so_far if diversity else None,
                    vision_only=effective_vision_only,
                    sort_by=slot_sort_by,
                    unreachable_ids=unreachable_ids,
                    tokens_per_sec=tokens_per_sec,
                    reasoning_model_ids=reasoning_model_ids,
                    exclude_reasoning_models=slot_exclude_reasoning,
                )
                section[cell_name] = picks_to_cell(picks, vision_substitute)
            if notes:
                loosening_log[f"{slot_section}.{cell_name}"] = notes
            if diversity and picks:
                excluded_so_far.add(picks[0]["id"])
                excluded_vendors_so_far.add(_vendor_key(picks[0]))
        return section

    cells["utility"] = _pick("utility", slot_specs["utility"])
    cells["analysis"] = {
        "gear4": _pick("analysis.gear4", slot_specs["analysis.gear4"]),
    }

    # Fast slot composition (2026-05-23 architecture). Primary → gear3.depth
    # + utility.gear2_rag_lookup; secondary → gear3.breadth (when adversarial
    # diversity is on; post-bake mirrors primary into breadth when off).
    # When slot_specs.fast is absent, fall back to the legacy analysis.gear3
    # path so older preset files keep working.
    if "fast" in slot_specs:
        import copy as _copy
        fast_section = _pick("fast", slot_specs["fast"])
        fast_primary = fast_section.get("primary")
        fast_secondary = fast_section.get("secondary")
        cells["analysis"]["gear3"] = {
            "depth": fast_primary,
            "breadth": fast_secondary,
        }
        cells["utility"]["gear2_rag_lookup"] = _copy.deepcopy(fast_primary)
    else:
        cells["analysis"]["gear3"] = _pick("analysis.gear3", slot_specs["analysis.gear3"])
        cells["analysis"]["gear3"]["breadth"] = None

    cells["post_analysis"] = _pick("post_analysis", slot_specs["post_analysis"])

    # Media slots (image_generation today; image_editing + text_to_video
    # will land on the Visual tab in later steps). Guarded by presence
    # in the preset spec so a configuration without the slot still bakes
    # cleanly against older preset files.
    if "image_generation" in slot_specs:
        cells["image_generation"] = _pick("image_generation", slot_specs["image_generation"])

    return {
        "name": "<set by caller>",
        "description": f"Auto-populated from preset '{preset_name}' on {datetime.now(timezone.utc).isoformat()}.",
        "preset_lineage": preset_name,
        "cells": cells,
        "_auto_populate_metadata": {
            "preset": preset_name,
            "vision_only": effective_vision_only,
            "vision_substitute": vision_substitute,
            "loosening_log": loosening_log,
            "catalog_models_considered": len(catalog),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Auto-populate a named configuration from the model catalog.")
    parser.add_argument("preset", help="Preset name: premium | optimum | budget | free")
    parser.add_argument("config_name", help="Configuration name (e.g. user-pipeline)")
    parser.add_argument("--dry-run", action="store_true", help="Print the populated configuration without writing.")
    parser.add_argument(
        "--vision-only", action="store_true",
        help="Restrict every slot to vision-capable models. Overrides the preset's vision_only field.",
    )
    parser.add_argument(
        "--no-vision-only", action="store_true",
        help="Allow text-only models in any slot. Overrides the preset's vision_only field.",
    )
    args = parser.parse_args()

    # CLI flag resolution: explicit --vision-only / --no-vision-only override
    # the preset's declared default; otherwise None defers to the preset.
    if args.vision_only and args.no_vision_only:
        print("[auto-populate] Cannot pass both --vision-only and --no-vision-only.", file=sys.stderr)
        sys.exit(1)
    vision_override: bool | None = None
    if args.vision_only:
        vision_override = True
    elif args.no_vision_only:
        vision_override = False

    if not CATALOG_PATH.exists():
        print(f"[auto-populate] {CATALOG_PATH} not found. Run scripts/refresh-catalog.py first.", file=sys.stderr)
        sys.exit(1)
    if not PRESETS_PATH.exists():
        print(f"[auto-populate] {PRESETS_PATH} not found.", file=sys.stderr)
        sys.exit(1)

    with open(CATALOG_PATH) as f:
        catalog_data = json.load(f)
    with open(PRESETS_PATH) as f:
        presets_config = json.load(f)

    catalog = catalog_data.get("models", [])
    if not catalog:
        print("[auto-populate] catalog is empty.", file=sys.stderr)
        sys.exit(1)

    # Cross-reference the registry: reachability probe (skip unreachables),
    # reasoning_model flag (excluded from Fast slot), and tokens/sec
    # (Fast slot's primary sort key). Registry lives next to the catalog;
    # missing or unread → empty defaults, so the script still runs cleanly
    # on a fresh install before any sync has happened.
    unreachable_ids: set[str] = set()
    reasoning_model_ids: set[str] = set()
    tokens_per_sec: dict[str, float] = {}
    registry_path = CONFIG_DIR / "model-registry.json"
    if registry_path.exists():
        try:
            with open(registry_path) as f:
                registry = json.load(f)
            for mid, m in (registry.get("models") or {}).items():
                if m.get("reachable") is False:
                    unreachable_ids.add(mid)
                if m.get("reasoning_model") is True:
                    reasoning_model_ids.add(mid)
                tps = m.get("output_tokens_per_second")
                if tps is not None:
                    tokens_per_sec[mid] = float(tps)
            if unreachable_ids:
                print(f"[auto-populate] skipping {len(unreachable_ids)} models flagged unreachable by the reachability probe.")
            if reasoning_model_ids:
                print(f"[auto-populate] {len(reasoning_model_ids)} reasoning models available for exclusion (Fast slot).")
        except Exception as exc:
            print(f"[auto-populate] registry read failed (proceeding without reachability/reasoning/tps filters): {exc}", file=sys.stderr)

    config = populate_configuration(
        args.preset, catalog, presets_config,
        vision_only=vision_override,
        unreachable_ids=unreachable_ids,
        tokens_per_sec=tokens_per_sec,
        reasoning_model_ids=reasoning_model_ids,
    )
    config["name"] = args.config_name

    if args.dry_run:
        print(json.dumps(config, indent=2))
        return

    CONFIGURATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONFIGURATIONS_DIR / f"{args.config_name}.json"
    with open(out_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"[auto-populate] Wrote {out_path}")
    if config["_auto_populate_metadata"]["loosening_log"]:
        print("[auto-populate] Loosening applied:")
        for cell, notes in config["_auto_populate_metadata"]["loosening_log"].items():
            print(f"  {cell}: {notes[-1]}")


if __name__ == "__main__":
    main()
