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
  mixed into paid ranking. The Free preset has its own loosening rule:
  when a slot's pool comes up empty, drop vision_only first, then
  size_bucket, before giving up — each step logged in the output
  metadata's loosening_log. The reachability gate never loosens.

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
    """Measured Artificial Analysis intelligence index (0-100); 0.0 if the
    model has no AA benchmark.

    Deliberately single-source. Arena Elo is NOT used as a fallback: over
    the 145 models carrying both scores it correlates only weakly with the
    AA benchmark (Pearson r≈0.44), so an Elo-derived estimate would
    systematically mis-rank — the top-Elo model (gemini-2.5-pro) measures
    AA 34.6 while a lower-Elo model (opus-4.8) measures 61.4. An
    unbenchmarked model therefore ranks at the bottom, which is honest: we
    have no quality signal for it. The "newest and latest" preference is
    served by the recency tiebreak (release_key) and by admitting
    unclassified flagships into the large bucket — not by inventing a
    quality score.
    """
    val = model.get("aa_intelligence_index")
    return float(val) if val is not None else 0.0


# A model with no release_date sorts as oldest, so a missing date never
# displaces a dated model in the recency tiebreak.
_NO_DATE = ""


def release_key(model: dict) -> str:
    """Release date as a sortable string (YYYY-MM-DD), '' when unknown.

    Used only as a SECONDARY tiebreak — it never reorders models that
    differ on intelligence or cost, it only decides 'newest wins' among
    otherwise-equal candidates, which is the literal 'newest and latest'
    preference."""
    return model.get("release_date") or _NO_DATE


def cost_of(model: dict) -> float:
    """Get the blended cost ($/M tokens). math.inf when missing — sorts to
    the bottom on cost-ascending."""
    pricing = model.get("openrouter_pricing", {}) or {}
    val = pricing.get("blended_per_m")
    return float(val) if val is not None else math.inf


def pareto_filter(candidates: list[dict], cost_fn=cost_of) -> list[dict]:
    """Remove strictly dominated models.

    A model A is dominated by B if B has higher (or equal) intelligence
    AND lower (or equal) cost, with at least one strict inequality.
    Returns the Pareto-frontier subset of candidates. ``cost_fn`` picks
    the cost axis (per-M-token blended cost for chat slots).
    """
    frontier = []
    for cand in candidates:
        c_int = intelligence_of(cand)
        c_cost = cost_fn(cand)
        c_rel = release_key(cand)
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
            # Exact tie on both axes (e.g. opus-4.8 and opus-4.8-fast both
            # 61.4 at the same cost): keep the NEWER. Without this the
            # winner was arbitrary list order; recency is the documented
            # "newest and latest" preference and only ever breaks an exact
            # tie, never the frontier shape.
            if o_int == c_int and o_cost == c_cost and release_key(other) > c_rel:
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
    """Restrict to a specific size_bucket. ``size_bucket=None`` (the Fast
    slot, which selects on tokens/sec) skips the filter entirely.

    The ``large`` bucket ALSO admits a model whose own ``size_bucket`` is
    ``None`` *when that model carries a measured intelligence score*
    (2026-06-14). A closed/codenamed flagship that carries neither a
    parameter count in its slug nor a matching family-classification rule
    ships unclassified (``size_bucket=None``) — the normal state of a
    brand-new top-tier model (e.g. claude-fable-5, the single
    highest-intelligence model in the catalog, was excluded from every big
    slot purely because no 'fable' rule existed yet). The
    measured-intelligence guard is load-bearing: a null-bucket model is
    doubly-unknown (unknown size AND, if also unbenchmarked, unknown
    quality), so admitting an UNSCORED null model would let a 0.0 model
    occupy a big slot and would suppress the free slot's soft-bucket
    fallback that surfaces benchmarked midsize models. Admitting only
    null-bucket models that ARE benchmarked keeps known-good unclassified
    flagships (fable-5, hy3-preview, step-3.7-flash) competing while
    leaving genuinely-unknown models out. Smaller buckets stay strict — a
    None model must never be forced into a small/midsize slot."""
    if size_bucket is None:
        return candidates
    if size_bucket == "large":
        return [m for m in candidates
                if m.get("size_bucket") == "large"
                or (m.get("size_bucket") is None
                    and m.get("aa_intelligence_index") is not None)]
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
    """Drop models in the reachability exclusion set.

    The set is built by ``registry_crossref``: with probe data present it
    is STRICT — every chat id the probe has not positively verified
    (``reachable`` is not True) is excluded, so an auto-pick can never
    select a model that hasn't demonstrably answered a completion call.
    Rate-limited verdicts count as verified (reachable=True +
    rate_limited flag) — the fallback chain absorbs transient 429s at
    runtime. On a fresh install with no probe data the set degrades to
    confirmed-unreachable only (see registry_crossref)."""
    if not unreachable_ids:
        return candidates
    return [m for m in candidates if m.get("id") not in unreachable_ids]


def registry_crossref(registry_path: Path | None = None) -> dict:
    """Build the registry-derived pick inputs shared by the CLI and the
    server-side bake (orchestrator/active_configuration.py).

    Returns a dict with:
      ``registry_ids``        — every id in the live registry (filter_in_registry)
      ``unreachable_ids``     — reachability exclusion set (see below)
      ``tokens_per_sec``      — Fast-slot sort key map
      ``reasoning_model_ids`` — Fast-slot exclusion set

    Reachability policy (2026-06-11): a chat model is pick-eligible only
    when the probe POSITIVELY verified it (``reachable`` is True), so the
    exclusion set contains every chat id with a false/null/absent verdict.
    Safety valve: when the registry holds NO positive verdicts at all
    (fresh install, probe never run), the strict gate would empty every
    slot — fall back to excluding only confirmed-unreachable ids and let
    the first probe tighten things up. Missing/unreadable registry →
    empty sets (no filtering), same as before.
    """
    path = registry_path or (CONFIG_DIR / "model-registry.json")
    out = {
        "registry_ids": set(),
        "unreachable_ids": set(),
        "tokens_per_sec": {},
        "reasoning_model_ids": set(),
    }
    if not Path(path).exists():
        return out
    try:
        with open(path) as f:
            registry = json.load(f)
        models = registry.get("models") or {}
        out["registry_ids"] = set(models.keys())
        any_verified = any(m.get("reachable") is True for m in models.values())
        for mid, m in models.items():
            if (m.get("category") or "chat") == "chat":
                if any_verified:
                    if m.get("reachable") is not True:
                        out["unreachable_ids"].add(mid)
                elif m.get("reachable") is False:
                    out["unreachable_ids"].add(mid)
            if m.get("reasoning_model") is True:
                out["reasoning_model_ids"].add(mid)
            tps = m.get("output_tokens_per_second")
            if tps is not None:
                out["tokens_per_sec"][mid] = float(tps)
    except Exception as exc:
        # Fail soft but never silently: a corrupt registry disables the
        # reachability gate, the in-registry filter, and the Fast-slot
        # inputs all at once — the bake still runs, but say why.
        print(
            f"[auto-populate] registry read failed (proceeding without "
            f"reachability/registry/reasoning/tps filters): {exc}",
            file=sys.stderr,
        )
        return {
            "registry_ids": set(),
            "unreachable_ids": set(),
            "tokens_per_sec": {},
            "reasoning_model_ids": set(),
        }
    return out


def filter_in_registry(candidates: list[dict], registry_ids: set[str]) -> list[dict]:
    """Drop catalog entries whose id is absent from the live model registry.

    The catalog (config/model-catalog.json) and the registry
    (config/model-registry.json) refresh on independent schedules — the
    Models pane's Refresh button re-syncs the registry but not the catalog —
    so the catalog can carry models the registry has since dropped or renamed
    (a ``:free`` tier that went away, a model superseded by a newer version).
    Picking one of those yields a slot the Models pane flags DEPRECATED
    ("model no longer in the registry"). Filtering against the registry here
    guarantees the autopicker only ever selects live models, regardless of how
    stale the catalog is. Empty/None registry_ids → no-op (fresh install
    before any sync, or an older caller that can't supply the set)."""
    if not registry_ids:
        return candidates
    return [m for m in candidates if m.get("id") in registry_ids]


def sort_by_cost_ascending(candidates: list[dict], cost_fn=cost_of) -> list[dict]:
    # Primary: cost (asc). Secondary tiebreak: recency (newest first).
    # Done as two stable passes — recency-descending first, then a stable
    # cost-ascending sort that preserves recency order within equal-cost
    # groups — because a single key tuple can't mix ascending cost with
    # descending dates cleanly. Never reorders models of different cost.
    by_recency = sorted(candidates, key=release_key, reverse=True)
    return sorted(by_recency, key=cost_fn)


def sort_by_intelligence_descending(candidates: list[dict]) -> list[dict]:
    # Primary: intelligence (desc). Secondary tiebreak: recency (newest
    # first) — only decides ties, never displaces a higher-intelligence
    # model. This is the "newest and latest" preference, scoped so it can
    # never trade quality for freshness.
    return sorted(candidates, key=lambda m: (intelligence_of(m), release_key(m)),
                  reverse=True)


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
) -> tuple[list[dict], list[str]]:
    """Pick top-N free models. No cost math.

    ``sort_by`` defaults to ``intelligence_desc`` (the historical Free
    behavior); Fast slot overrides to ``tokens_per_sec_desc``.

    size_bucket=None means "any free model" (Free preset doesn't require
    bucket conformance because free models are scarcer).

    Returns (picks, loosening_notes) — mirroring pick_for_paid_slot.

    Graceful degradation (2026-06-12): the free pool is small enough that
    vision_only + size_bucket + the strict reachability gate can empty it
    entirely (live example: every free vision-capable reachable model sits
    in the midsize bucket, so small/large slots baked null cells). Rather
    than return nothing, constraints loosen tier-by-tier, each loosening
    recorded in the notes so the Models pane can show why:

      Tier 0 — as configured (size_bucket soft-falls-back when the bucket
               itself is empty, the pre-existing behavior).
      Tier 1 — drop vision_only (the cell's vision_substitute still
               carries a vision model for image-input fallback).
      Tier 2 — drop size_bucket as well.

    The reachability gate is NEVER loosened — picks stay probe-verified
    even when the cell ends up empty.
    """
    excluded_ids = excluded_ids or set()
    # Base pool — these filters never loosen. Same chat-category +
    # text-output guards as pick_for_paid_slot.
    base = filter_by_category(catalog, "chat")
    base = filter_text_output(base)
    base = filter_free(base)
    base = filter_reachable(base, unreachable_ids or set())
    if exclude_reasoning_models and reasoning_model_ids:
        base = filter_exclude_reasoning(base, reasoning_model_ids)

    # (apply_vision, apply_bucket, note-on-entering-this-tier)
    tiers: list[tuple] = [(vision_only, True, None)]
    if vision_only:
        tiers.append((False, True,
                      "vision_only dropped: no eligible free vision-capable "
                      "model for this cell (vision_substitute still handles "
                      "image input; reachability gate stays strict)"))
    if size_bucket:
        tiers.append((False, False,
                      f"size_bucket '{size_bucket}' dropped: free pool "
                      f"exhausted within the bucket"))

    notes: list[str] = []
    for tier_vision, tier_bucket, tier_note in tiers:
        if tier_note:
            notes.append(tier_note)
        candidates = base
        if tier_bucket and size_bucket:
            # Soft filter — fall back to all free if bucket-conformance is empty
            bucketed = filter_by_size_bucket(candidates, size_bucket)
            if bucketed:
                candidates = bucketed
        if tier_vision:
            candidates = filter_vision(candidates)
        candidates = [m for m in candidates if m["id"] not in excluded_ids]
        candidates = _apply_vendor_diversity(candidates, excluded_vendors)
        # Same reason as pick_for_paid_slot: skip Pareto when selecting on speed.
        if sort_by != "tokens_per_sec_desc":
            candidates = pareto_filter(candidates)
        if sort_by == "tokens_per_sec_desc":
            picks = sort_by_tokens_per_sec_descending(candidates, tokens_per_sec or {})[:top_n]
        else:
            picks = sort_by_intelligence_descending(candidates)[:top_n]
        if picks:
            return picks, notes

    notes.append(
        "free pool exhausted even after dropping vision_only and size_bucket; "
        "cell left empty (reachability gate never loosened)")
    return [], notes


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
    # Soft bucket filter: an off-bucket vision substitute beats none at all
    # (a null substitute means image input has no fallback path). Live
    # example: every free vision-capable model is midsize, so the large-
    # bucket requirement left the Free preset with substitute=null.
    bucketed = filter_by_size_bucket(candidates, size_bucket)
    if bucketed:
        candidates = bucketed
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
    registry_ids: set[str] | None = None,
) -> dict:
    """Compute the full configuration dict for a given preset.

    ``vision_only``: when True, every slot picks only from vision-capable
    models. When False, text-only primaries are admissible (the
    vision_substitute field still carries a vision model for the image
    extraction fallback). When None, falls through to the preset's
    declared default (``vision_only`` field on the preset; defaults to
    False if absent).

    ``unreachable_ids``: reachability exclusion set, normally built by
    ``registry_crossref`` — with probe data present it contains every
    chat id the probe has not positively verified (strict gate), so picks
    can only land on models that demonstrably answered a completion call.
    Rate-limited models count as verified; the fallback chain absorbs
    transient 429s at runtime.

    ``registry_ids``: set of model ids present in the live registry. When
    supplied, the catalog is filtered down to these before any slot picks,
    so a stale catalog can never inject a model the Models pane would flag
    DEPRECATED. None/empty → no filtering (fresh install before any sync).
    See filter_in_registry.
    """
    presets = presets_config["presets"]
    slot_specs = presets_config["slot_specs"]
    vision_spec = presets_config.get("vision_substitute", {})

    if preset_name not in presets:
        raise ValueError(f"Unknown preset: {preset_name}. Known: {list(presets)}")
    preset = presets[preset_name]

    # Drop catalog entries no longer in the live registry before any pick —
    # otherwise a stale catalog injects models the Models pane flags
    # DEPRECATED. Applied once here so it covers every slot (chat + media)
    # and the vision-substitute pick below. See filter_in_registry.
    catalog = filter_in_registry(catalog, registry_ids or set())

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
        # The slot_spec may override the preset's sort_by — Fast does this
        # to force tokens_per_sec_desc across every preset. Same story for
        # exclude_reasoning_models. size_bucket is optional; None means
        # no parameter-bucket filter (Fast uses tps to bubble fast tier).
        slot_sort_by = slot_spec.get("sort_by") or preset.get("sort_by", "cost_asc")
        slot_exclude_reasoning = slot_spec.get("exclude_reasoning_models", False)
        slot_size_bucket = slot_spec.get("size_bucket")
        for cell_name in slot_spec["cells"]:
            notes: list = []
            if preset["mode"] == "free_intelligence":
                picks, notes = pick_for_free_slot(
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

    # No media slots: image-model selection lives on the Visual tab /
    # routing-config.json's slots.image_generates chain, not in chat
    # configurations (decision 2026-06-11 — the configuration cell was
    # never read by the image-generation runtime).

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

    # Cross-reference the registry: reachability gate (only probe-verified
    # models are pick-eligible — see registry_crossref), reasoning_model
    # flag (excluded from Fast slot), and tokens/sec (Fast slot's primary
    # sort key). Registry lives next to the catalog; missing or unread →
    # empty defaults, so the script still runs cleanly on a fresh install
    # before any sync has happened.
    xref = registry_crossref()
    unreachable_ids = xref["unreachable_ids"]
    reasoning_model_ids = xref["reasoning_model_ids"]
    tokens_per_sec = xref["tokens_per_sec"]
    registry_ids = xref["registry_ids"]
    if unreachable_ids:
        print(f"[auto-populate] excluding {len(unreachable_ids)} models without a positive reachability verdict (strict gate; see registry_crossref).")
    if reasoning_model_ids:
        print(f"[auto-populate] {len(reasoning_model_ids)} reasoning models available for exclusion (Fast slot).")

    config = populate_configuration(
        args.preset, catalog, presets_config,
        vision_only=vision_override,
        unreachable_ids=unreachable_ids,
        tokens_per_sec=tokens_per_sec,
        reasoning_model_ids=reasoning_model_ids,
        registry_ids=registry_ids,
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
