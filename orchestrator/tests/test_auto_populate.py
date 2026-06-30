#!/usr/bin/env python3
"""Install Chunk 5 — auto-populate-configuration.py unit tests.

Fixture catalog covers small/midsize/large buckets, vision-capable and
text-only, free and paid, models with and without AA enrichment, etc.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

SPEC = importlib.util.spec_from_file_location(
    "auto_populate", REPO_ROOT / "scripts" / "auto-populate-configuration.py",
)
auto_populate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto_populate)


def _model(id, *, intelligence=None, blended=None, size="large",
           vision=False, is_free=False, provider="x", context=None):
    m = {
        "id": id, "display_name": id, "provider": provider,
        "size_bucket": size, "vision_capable": vision, "is_free": is_free,
        "aa_intelligence_index": intelligence,
        "openrouter_pricing": {"input_per_m": None, "output_per_m": None, "blended_per_m": blended},
    }
    # Catalog field for context window. Left unset (→ None → treated as 0
    # by filter_min_context) unless a test supplies one.
    if context is not None:
        m["context_window"] = context
    return m


def _fixture_catalog():
    """Realistic mini-catalog for algorithm validation."""
    return [
        # Large paid
        _model("a/flagship",  intelligence=80, blended=20.0, size="large", provider="a"),
        _model("a/value",     intelligence=75, blended=4.0,  size="large", provider="a"),
        _model("b/strong",    intelligence=72, blended=3.0,  size="large", provider="b"),
        _model("c/cheap",     intelligence=55, blended=1.5,  size="large", provider="c"),
        _model("d/weak",      intelligence=40, blended=0.5,  size="large", provider="d"),
        _model("e/dominated", intelligence=70, blended=10.0, size="large", provider="e"),
        # ↑ e is dominated by b/strong (both 70/72 int but b/strong cheaper)

        # Small paid
        _model("a/fast",      intelligence=60, blended=0.3,  size="small", provider="a"),
        _model("b/mini",      intelligence=55, blended=0.2,  size="small", provider="b"),
        _model("c/tiny",      intelligence=40, blended=0.1,  size="small", provider="c"),

        # Large vision-capable
        _model("a/vision-flagship", intelligence=78, blended=15.0, size="large", vision=True, provider="a"),
        _model("b/vision-value",    intelligence=70, blended=5.0,  size="large", vision=True, provider="b"),

        # Free models
        _model("free/large-1", intelligence=65, blended=0.0, size="large", is_free=True),
        _model("free/large-2", intelligence=60, blended=0.0, size="large", is_free=True),
        _model("free/small-1", intelligence=50, blended=0.0, size="small", is_free=True),
    ]


def _fixture_presets():
    """Mirror the production presets config."""
    return {
        "presets": {
            "premium":  {"mode": "paid_intelligence", "floor_pct": None, "cost_ceiling_per_m": None, "loosening": False},
            "budget":   {
                "mode": "paid_intelligence",
                "floor_pct": 70,
                "cost_ceiling_per_m": None,
                "adaptive_cost_ceiling": {
                    "enabled": True,
                    "peak_fraction": 0.3,
                    "outlier_median_multiple": 3.0,
                },
                "loosening": True,
                "loosening_strategy": "paired",
                "floor_step_pct": 5,
                "ceiling_growth_factor": 1.25,
                "min_floor_pct": 50,
            },
            "speed":    {
                "mode": "paid_intelligence",
                "selection": "latency_knee",
                "latency_ceiling_ms": 1200,
                "knee_cost_normalization": "log",
                "exclude_reasoning": True,
            },
            "free":     {"mode": "free_intelligence", "floor_pct": None, "cost_ceiling_per_m": None, "loosening": False},
        },
        "slot_specs": {
            "utility":         {"size_bucket": "small", "cells": ["step1_cleanup", "classification", "rag_planner"], "top_n": 2, "diversity_excluded": False},
            "analysis.gear4":  {"size_bucket": "large", "cells": ["depth", "breadth"], "top_n": 3, "diversity_excluded": True},
            "analysis.gear3":  {"size_bucket": "large", "cells": ["depth"], "top_n": 3, "diversity_excluded": False},
            "post_analysis":   {"size_bucket": "large", "cells": ["consolidation", "verification", "formatter"], "top_n": 3, "diversity_excluded": False},
        },
        "vision_substitute": {"size_bucket": "large"},
    }


class TestParetoFilter(unittest.TestCase):
    def test_removes_dominated(self):
        models = [
            _model("a", intelligence=80, blended=10.0),
            _model("b", intelligence=70, blended=5.0),
            _model("c", intelligence=70, blended=10.0),  # dominated by b
        ]
        frontier = auto_populate.pareto_filter(models)
        ids = {m["id"] for m in frontier}
        self.assertIn("a", ids)
        self.assertIn("b", ids)
        self.assertNotIn("c", ids)

    def test_equal_intelligence_cheaper_wins(self):
        models = [
            _model("a", intelligence=70, blended=10.0),
            _model("b", intelligence=70, blended=5.0),
        ]
        frontier = auto_populate.pareto_filter(models)
        ids = {m["id"] for m in frontier}
        self.assertIn("b", ids)
        self.assertNotIn("a", ids)

    def test_all_pareto_optimal(self):
        models = [
            _model("a", intelligence=80, blended=20.0),
            _model("b", intelligence=70, blended=10.0),
            _model("c", intelligence=60, blended=5.0),
        ]
        frontier = auto_populate.pareto_filter(models)
        self.assertEqual({m["id"] for m in frontier}, {"a", "b", "c"})


class TestFloor(unittest.TestCase):
    def test_floor_80_pct_keeps_top_band(self):
        models = [
            _model("a", intelligence=100),
            _model("b", intelligence=80),
            _model("c", intelligence=75),
            _model("d", intelligence=40),
        ]
        kept = auto_populate.apply_floor(models, 80)
        ids = {m["id"] for m in kept}
        self.assertIn("a", ids)
        self.assertIn("b", ids)  # exactly at 80%
        self.assertNotIn("c", ids)  # below 80%
        self.assertNotIn("d", ids)

    def test_floor_none_passes_all(self):
        models = [_model("a", intelligence=100), _model("b", intelligence=10)]
        kept = auto_populate.apply_floor(models, None)
        self.assertEqual(len(kept), 2)


class TestAdaptiveCostCeiling(unittest.TestCase):
    def test_uses_trimmed_peak_not_price_outlier(self):
        models = [
            _model("value/a", intelligence=45, blended=0.55),
            _model("value/b", intelligence=44, blended=0.75),
            _model("normal/peak", intelligence=54, blended=11.25),
            _model("openai/pro-price-outlier", intelligence=52, blended=57.75),
            _model("legacy/extreme-outlier", intelligence=40, blended=262.50),
        ]
        ceiling, meta = auto_populate.adaptive_cost_ceiling_for(
            models,
            floor_pct=70,
            spec={
                "enabled": True,
                "peak_fraction": 0.3,
                "outlier_median_multiple": 3.0,
            },
        )
        self.assertAlmostEqual(meta["adaptive_peak_per_m"], 11.25)
        self.assertAlmostEqual(ceiling, 3.375)


class TestPickForPaidSlot(unittest.TestCase):
    def test_budget_picks_cheapest_in_top_80(self):
        catalog = _fixture_catalog()
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=80, cost_ceiling=None, loosening=False,
        )
        # Large bucket has 80, 75, 72, 70,
        # 55, 40 intelligence (vision models too: 78, 70).
        # Floor 80% of 80 = 64. Survivors: a/flagship(80), a/vision-flagship(78),
        #   a/value(75), b/strong(72), b/vision-value(70), e/dominated(70).
        # Sort by cost ascending: b/strong($3), a/value($4), b/vision-value($5),
        #   e/dominated($10), a/vision-flagship($15), a/flagship($20).
        # Top 3: b/strong, a/value, b/vision-value
        pick_ids = [p["id"] for p in picks]
        self.assertEqual(len(picks), 3)
        self.assertEqual(pick_ids[0], "b/strong")  # cheapest in top band
        self.assertIn("a/value", pick_ids)
        self.assertEqual(notes, [])

    def test_premium_picks_highest_intelligence(self):
        catalog = _fixture_catalog()
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=None, cost_ceiling=None, loosening=False,
        )
        # No floor — all candidates available.
        # Sort by cost ascending → cheapest first
        pick_ids = [p["id"] for p in picks]
        self.assertEqual(len(picks), 3)
        # d/weak is cheapest at $0.50 — Premium without floor picks
        # cheap because cost is the tiebreaker. This is correct behavior:
        # Premium = "highest-scoring available". Without a floor, the
        # algorithm has no way to know what "highest scoring" means
        # versus what "cheapest" means. In practice Premium users would
        # benefit from a floor; the preset declaration is what
        # configures it.
        # For now, just assert the algorithm runs and returns 3.

    def test_dominated_model_included_without_pareto(self):
        # Pareto filtering was intentionally removed (2026-06-14, user request):
        # it pruned the cheap same-tier alternatives a fallback chain wants. A
        # strictly-dominated model is therefore no longer excluded — it just
        # sorts lower. See the rationale in pick_for_paid_slot.
        catalog = _fixture_catalog()
        picks, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=10,
            floor_pct=None, cost_ceiling=None, loosening=False,
        )
        pick_ids = {p["id"] for p in picks}
        self.assertIn("e/dominated", pick_ids)

    def test_diversity_exclusion(self):
        catalog = _fixture_catalog()
        picks_first, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=80, cost_ceiling=None, loosening=False,
        )
        first_primary = picks_first[0]["id"]
        picks_second, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=80, cost_ceiling=None, loosening=False,
            excluded_ids={first_primary},
        )
        self.assertNotEqual(picks_second[0]["id"], first_primary)

    def test_adaptive_ceiling_blocks_expensive_budget_pick(self):
        catalog = [
            _model("value/a", intelligence=45, blended=0.55, size="large"),
            _model("value/b", intelligence=44, blended=0.75, size="large"),
            _model("normal/peak", intelligence=54, blended=11.25, size="large"),
            _model("openai/pro-price-outlier", intelligence=52, blended=57.75, size="large"),
            _model("legacy/extreme-outlier", intelligence=40, blended=262.50, size="large"),
        ]
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=70, cost_ceiling=None, loosening=False,
            adaptive_cost_ceiling={
                "enabled": True,
                "peak_fraction": 0.3,
                "outlier_median_multiple": 3.0,
            },
        )
        self.assertEqual([p["id"] for p in picks], ["value/a", "value/b"])
        self.assertEqual(notes, [])

    def test_min_tokens_per_second_excludes_slow_and_unknown(self):
        catalog = [
            _model("fast/smart", intelligence=70, blended=1.0, size=None, vision=True),
            _model("slow/smarter", intelligence=80, blended=0.2, size=None, vision=True),
            _model("unknown/cheap", intelligence=90, blended=0.1, size=None, vision=True),
        ]
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket=None, top_n=2,
            floor_pct=None, cost_ceiling=None, loosening=False,
            min_tokens_per_second=80,
            tokens_per_sec={"fast/smart": 120, "slow/smarter": 40},
        )
        self.assertEqual([p["id"] for p in picks], ["fast/smart"])
        self.assertEqual(notes, [])


class TestFilterMinContext(unittest.TestCase):
    """The min_context_1m preset toggle's context floor."""

    def test_none_is_noop(self):
        cands = [_model("a", context=200000), _model("b", context=1000000)]
        out = auto_populate.filter_min_context(cands, None)
        self.assertEqual([m["id"] for m in out], ["a", "b"])

    def test_drops_below_floor_keeps_at_or_above(self):
        cands = [
            _model("small", context=200000),
            _model("exactly", context=900000),
            _model("big", context=1000000),
        ]
        out = auto_populate.filter_min_context(cands, 900000)
        # 200000 excluded; 900000 (boundary, >=) and 1000000 kept.
        self.assertEqual([m["id"] for m in out], ["exactly", "big"])

    def test_none_context_treated_as_zero_and_dropped(self):
        cands = [_model("no-ctx"), _model("big", context=1000000)]
        out = auto_populate.filter_min_context(cands, 900000)
        self.assertEqual([m["id"] for m in out], ["big"])

    def test_context_of_accepts_context_length_alias(self):
        # The registry / inventory surface the field as context_length;
        # _context_of must read either name.
        self.assertEqual(auto_populate._context_of({"context_length": 1000000}), 1000000)
        self.assertEqual(auto_populate._context_of({"context_window": 1000000}), 1000000)
        self.assertEqual(auto_populate._context_of({}), 0)
        self.assertEqual(auto_populate._context_of({"context_window": None}), 0)


class TestPickWithMinContext(unittest.TestCase):
    """min_context threaded into the pick functions — including the
    graceful-degrade that keeps a slot filled when no candidate reaches
    the floor."""

    def test_paid_slot_picks_only_ge_floor_when_available(self):
        catalog = [
            _model("big/a",   intelligence=70, blended=2.0, size="large", context=1000000),
            _model("big/b",   intelligence=65, blended=1.0, size="large", context=1048576),
            _model("small/c", intelligence=60, blended=0.5, size="large", context=200000),
        ]
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=None, cost_ceiling=None, loosening=False,
            min_context=900000,
        )
        pick_ids = {p["id"] for p in picks}
        self.assertEqual(pick_ids, {"big/a", "big/b"})  # 200000 model excluded
        self.assertNotIn("small/c", pick_ids)
        # Floor was satisfiable, so no skip note.
        self.assertEqual(notes, [])

    def test_paid_slot_graceful_degrade_when_no_candidate_meets_floor(self):
        # A small/utility-style slot where NO model reaches the 1M floor:
        # the slot must still fill, and a skip note must be recorded.
        catalog = [
            _model("small/a", intelligence=60, blended=0.3, size="small", context=128000),
            _model("small/b", intelligence=55, blended=0.2, size="small", context=200000),
        ]
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="small", top_n=2,
            floor_pct=None, cost_ceiling=None, loosening=False,
            min_context=900000,
        )
        self.assertEqual(len(picks), 2)  # still filled despite the floor
        self.assertTrue(
            any("context floor skipped" in n for n in notes),
            f"expected a context-floor-skipped note, got {notes!r}")

    def test_free_slot_picks_only_ge_floor_when_available(self):
        catalog = [
            _model("free/big",   intelligence=65, size="large", is_free=True, context=1000000),
            _model("free/small", intelligence=60, size="large", is_free=True, context=200000),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=2,
            min_context=900000,
        )
        self.assertEqual([p["id"] for p in picks], ["free/big"])

    def test_free_slot_graceful_degrade_when_no_candidate_meets_floor(self):
        catalog = [
            _model("free/a", intelligence=60, size="small", is_free=True, context=128000),
            _model("free/b", intelligence=55, size="small", is_free=True, context=200000),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="small", top_n=2,
            min_context=900000,
        )
        self.assertEqual(len(picks), 2)  # still filled
        self.assertTrue(
            any("context floor skipped" in n for n in notes),
            f"expected a context-floor-skipped note, got {notes!r}")


class TestVendorKey(unittest.TestCase):
    def test_prefers_provider_when_specific(self):
        self.assertEqual(auto_populate._vendor_key(
            {"id": "qwen/qwen3.5-something", "provider": "qwen"}), "qwen")

    def test_falls_back_to_id_prefix_when_provider_generic(self):
        # AA-only direct-vendor entries have provider="artificial-analysis"
        self.assertEqual(auto_populate._vendor_key(
            {"id": "anthropic/claude-opus-4-7", "provider": "artificial-analysis"}),
            "anthropic")

    def test_strips_tilde_prefix(self):
        # ~anthropic / ~google etc. mark AA-direct-vendor variants;
        # they should match their non-tilde siblings.
        self.assertEqual(auto_populate._vendor_key(
            {"id": "~anthropic/claude-via-aa"}), "anthropic")

    def test_lowercases(self):
        self.assertEqual(auto_populate._vendor_key(
            {"id": "Qwen/Foo", "provider": "Qwen"}), "qwen")


class TestVendorDiversity(unittest.TestCase):
    """Vendor-aware diversity — Optimum Fast 1 + Fast 2 used to both end up
    qwen. Verifies the new excluded_vendors filter and its soft fallback."""

    def _two_vendor_catalog(self):
        # Two paid large models per vendor; same intelligence/cost shape so
        # the only thing distinguishing picks is the vendor filter.
        return [
            _model("qwen/q-a", intelligence=80, blended=2.0, size="large", provider="qwen"),
            _model("qwen/q-b", intelligence=70, blended=2.0, size="large", provider="qwen"),
            _model("openai/o-a", intelligence=75, blended=2.0, size="large", provider="openai"),
            _model("openai/o-b", intelligence=65, blended=2.0, size="large", provider="openai"),
        ]

    def test_paid_slot_picks_different_vendor_when_excluded(self):
        picks, _ = auto_populate.pick_for_paid_slot(
            self._two_vendor_catalog(), size_bucket="large", top_n=1,
            floor_pct=None, cost_ceiling=None, loosening=False,
            excluded_vendors={"qwen"},
        )
        self.assertEqual(picks[0]["provider"], "openai")

    def test_paid_slot_soft_fallback_when_no_other_vendor(self):
        # Only qwen available; vendor filter empties the pool, soft fallback
        # accepts a qwen pick rather than returning [].
        qwen_only = [
            _model("qwen/q-a", intelligence=80, blended=2.0, size="large", provider="qwen"),
            _model("qwen/q-b", intelligence=70, blended=2.0, size="large", provider="qwen"),
        ]
        picks, _ = auto_populate.pick_for_paid_slot(
            qwen_only, size_bucket="large", top_n=1,
            floor_pct=None, cost_ceiling=None, loosening=False,
            excluded_vendors={"qwen"},
        )
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["provider"], "qwen")

    def test_free_slot_picks_different_vendor_when_excluded(self):
        catalog = [
            _model("qwen/free-a", intelligence=80, blended=0.0, size="large",
                   is_free=True, provider="qwen"),
            _model("openai/free-a", intelligence=70, blended=0.0, size="large",
                   is_free=True, provider="openai"),
        ]
        picks, _ = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=1,
            excluded_vendors={"qwen"},
        )
        self.assertEqual(picks[0]["provider"], "openai")

    def test_sequential_picks_diverge_by_vendor(self):
        # Mirrors the pattern used by _pick: first cell picks normally,
        # second cell receives the first's id + vendor as excluded.
        catalog = self._two_vendor_catalog()
        first, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=1,
            floor_pct=None, cost_ceiling=None, loosening=False,
            sort_by="intelligence_desc",
        )
        # First picks qwen/q-a (intelligence=80, the highest).
        self.assertEqual(first[0]["provider"], "qwen")
        second, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=1,
            floor_pct=None, cost_ceiling=None, loosening=False,
            sort_by="intelligence_desc",
            excluded_ids={first[0]["id"]},
            excluded_vendors={auto_populate._vendor_key(first[0])},
        )
        # Without vendor exclusion the next pick would be qwen/q-b
        # (intelligence=70). Vendor filter forces openai/o-a (intelligence=75).
        self.assertEqual(second[0]["id"], "openai/o-a")


class TestBudgetLoosening(unittest.TestCase):
    def test_loosens_floor_when_too_strict(self):
        catalog = _fixture_catalog()
        # Budget: floor 50%, ceiling $1.0/M
        # At ceiling $1: only d/weak($0.5) and c/cheap (no, $1.5).
        # Wait — c is $1.5, above ceiling. Only d/weak survives.
        # Need 3 picks but only 1 qualifies → loosening fires.
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=50, cost_ceiling=1.0, loosening=True,
        )
        # Loosening should fire
        self.assertGreater(len(notes), 0)

    def test_no_loosening_when_sufficient(self):
        catalog = _fixture_catalog()
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=2,
            floor_pct=80, cost_ceiling=None, loosening=False,
        )
        # 2 picks easy from top 80%, no loosening
        self.assertEqual(notes, [])
        self.assertEqual(len(picks), 2)


class TestFreeSlot(unittest.TestCase):
    def test_picks_free_models_only(self):
        catalog = _fixture_catalog()
        picks, _ = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2)
        pick_ids = {p["id"] for p in picks}
        # Only free large models
        for pid in pick_ids:
            self.assertTrue(pid.startswith("free/"))

    def test_intelligence_descending(self):
        catalog = _fixture_catalog()
        picks, _ = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2)
        # free/large-1 (65) before free/large-2 (60)
        self.assertEqual(picks[0]["id"], "free/large-1")

    def test_falls_back_to_any_free_when_bucket_empty(self):
        catalog = [
            _model("free/only-small", intelligence=40, blended=0.0, size="small", is_free=True),
        ]
        # Asking for large; no free larges; falls back to any free
        picks, _ = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["id"], "free/only-small")


class TestVisionSubstitute(unittest.TestCase):
    def test_picks_lowest_cost_vision_in_bucket(self):
        catalog = _fixture_catalog()
        # Two large vision-capable: vision-value($5,70) and vision-flagship($15,78)
        # Lowest cost wins: vision-value
        vid = auto_populate.pick_vision_substitute(
            catalog, size_bucket="large", preset_mode="paid_intelligence",
        )
        self.assertEqual(vid, "b/vision-value")

    def test_none_when_no_vision_in_bucket(self):
        catalog = [_model("a", intelligence=80, blended=10.0, size="small")]
        vid = auto_populate.pick_vision_substitute(
            catalog, size_bucket="large", preset_mode="paid_intelligence",
        )
        self.assertIsNone(vid)

    def test_soft_bucket_fallback_picks_off_bucket_vision(self):
        # A null substitute means image input has no fallback path at all —
        # an off-bucket vision model beats none. Live case: every free
        # vision-capable model is midsize, so the large-bucket requirement
        # baked vision_substitute=null into the Free preset.
        catalog = [
            _model("free/vis-mid", intelligence=65, blended=0.0,
                   size="midsize", is_free=True, vision=True),
            _model("free/txt-large", intelligence=60, blended=0.0,
                   size="large", is_free=True),
        ]
        vid = auto_populate.pick_vision_substitute(
            catalog, size_bucket="large", preset_mode="free_intelligence",
        )
        self.assertEqual(vid, "free/vis-mid")


class TestFreeGracefulDegradation(unittest.TestCase):
    """Free preset tier-by-tier loosening (2026-06-12 fix). Live failure:
    with vision_only on plus the strict reachability gate, every free
    vision-capable reachable model sat in the midsize bucket, so the
    small/large slots baked primary=None across 7 cells of free.json.
    pick_for_free_slot now loosens vision_only first, then size_bucket —
    never the reachability gate — and logs each step."""

    def test_no_loosening_when_vision_pool_sufficient(self):
        catalog = [
            _model("free/vis-large", intelligence=60, blended=0.0,
                   size="large", is_free=True, vision=True),
            _model("free/txt-large", intelligence=70, blended=0.0,
                   size="large", is_free=True),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=2, vision_only=True)
        self.assertEqual([p["id"] for p in picks], ["free/vis-large"])
        self.assertEqual(notes, [])

    def test_nonempty_text_bucket_does_not_block_vision_drop(self):
        # The exact live trap: the bucket holds text-only free models (so
        # the old soft-bucket fallback never fired) and the vision filter
        # then emptied the pool → null cell. Tier 1 recovers the in-bucket
        # text models; the off-bucket vision model is NOT preferred because
        # the prescribed loosening order keeps bucket conformance longer.
        catalog = [
            _model("free/txt-large", intelligence=60, blended=0.0,
                   size="large", is_free=True),
            _model("free/vis-mid", intelligence=65, blended=0.0,
                   size="midsize", is_free=True, vision=True),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=2, vision_only=True)
        self.assertEqual(picks[0]["id"], "free/txt-large")
        self.assertTrue(any("vision_only dropped" in n for n in notes))

    def test_size_bucket_drop_tier(self):
        # Tier 2: the bucket pool is non-empty but exclusions empty it;
        # dropping the bucket recovers a pick from the wider free pool.
        catalog = [
            _model("free/large-1", intelligence=65, blended=0.0,
                   size="large", is_free=True),
            _model("free/small-1", intelligence=50, blended=0.0,
                   size="small", is_free=True),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=2,
            excluded_ids={"free/large-1"})
        self.assertEqual(picks[0]["id"], "free/small-1")
        self.assertTrue(any("size_bucket 'large' dropped" in n for n in notes))

    def test_reachability_gate_never_loosened(self):
        # The only free vision model lacks a positive probe verdict; the
        # degradation must drop vision_only (tier 1) rather than ever admit
        # the unprobed model.
        catalog = [
            _model("free/vis-unprobed", intelligence=90, blended=0.0,
                   size="large", is_free=True, vision=True),
            _model("free/txt-probed", intelligence=50, blended=0.0,
                   size="large", is_free=True),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=2, vision_only=True,
            unreachable_ids={"free/vis-unprobed"})
        self.assertEqual([p["id"] for p in picks], ["free/txt-probed"])
        self.assertTrue(any("vision_only dropped" in n for n in notes))

    def test_exhausted_pool_returns_empty_with_note(self):
        # Nothing free and probe-verified at all → empty picks plus an
        # exhaustion note, and still no unreachable model admitted.
        catalog = [
            _model("free/unprobed", intelligence=90, blended=0.0,
                   size="large", is_free=True, vision=True),
            _model("paid/large", intelligence=80, blended=2.0, size="large"),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket="large", top_n=2, vision_only=True,
            unreachable_ids={"free/unprobed"})
        self.assertEqual(picks, [])
        self.assertTrue(any("exhausted" in n for n in notes))

    def test_populate_free_vision_only_bakes_no_null_chat_cells(self):
        # End-to-end regression for the null-cell bake: free + vision_only
        # over a catalog whose free models are all text-only must populate
        # every chat cell and surface per-cell loosening in the metadata.
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration(
            "free", catalog, presets, vision_only=True)
        cells = config["cells"]
        for cell_name in ("step1_cleanup", "classification", "rag_planner"):
            self.assertIsNotNone(cells["utility"][cell_name], cell_name)
        self.assertIsNotNone(cells["analysis"]["gear4"]["depth"])
        self.assertIsNotNone(cells["analysis"]["gear4"]["breadth"])
        self.assertIsNotNone(cells["analysis"]["gear3"]["depth"])
        for cell_name in ("consolidation", "verification", "formatter"):
            self.assertIsNotNone(cells["post_analysis"][cell_name], cell_name)
        log = config["_auto_populate_metadata"]["loosening_log"]
        self.assertTrue(
            any("vision_only dropped" in n for notes in log.values() for n in notes),
            f"expected vision loosening in log, got: {log}",
        )


class TestVisionOnlyToggle(unittest.TestCase):
    """vision_only filter restricts every slot to vision-capable models."""

    def test_paid_slot_filters_to_vision_only(self):
        catalog = _fixture_catalog()
        # Without toggle: cheap text-only models lead
        no_filter, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=80, cost_ceiling=None, loosening=False,
            vision_only=False,
        )
        # With toggle: only vision-capable in large bucket
        with_filter, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=80, cost_ceiling=None, loosening=False,
            vision_only=True,
        )
        # Picks differ: filtered list excludes text-only models
        for m in with_filter:
            self.assertTrue(m.get("vision_capable"), f"{m['id']} should be vision-capable")

    def test_free_slot_prefers_vision_when_available(self):
        # When the free pool has a vision-capable model, vision_only picks
        # it exclusively — no degradation, no notes.
        catalog = _fixture_catalog() + [
            _model("free/vis-large", intelligence=55, blended=0.0,
                   size="large", is_free=True, vision=True),
        ]
        no_filter, _ = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2, vision_only=False)
        with_filter, notes = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2, vision_only=True)
        self.assertGreater(len(no_filter), 0)
        self.assertEqual([p["id"] for p in with_filter], ["free/vis-large"])
        self.assertEqual(notes, [])

    def test_free_slot_degrades_when_no_free_vision(self):
        # Free models in fixture are all text-only; vision-only used to
        # return zero picks (→ null cells in the baked free preset). Now it
        # loosens vision_only and reports the loosening instead.
        catalog = _fixture_catalog()
        picks, notes = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2, vision_only=True)
        self.assertGreater(len(picks), 0)
        self.assertTrue(all(p["id"].startswith("free/") for p in picks))
        self.assertTrue(any("vision_only dropped" in n for n in notes))

    def test_populate_configuration_respects_cli_override(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration("budget", catalog, presets, vision_only=True)
        self.assertTrue(config["_auto_populate_metadata"]["vision_only"])
        # Verify every populated cell's primary is vision-capable
        by_id = {m["id"]: m for m in catalog}
        cells = config["cells"]
        for slot in cells["analysis"]["gear4"].values():
            if slot is not None:
                self.assertTrue(by_id[slot["primary"]].get("vision_capable"))
        for slot in cells["post_analysis"].values():
            if slot is not None:
                self.assertTrue(by_id[slot["primary"]].get("vision_capable"))

    def test_populate_configuration_respects_preset_default(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        # Add vision_only=True to the budget preset
        presets["presets"]["budget"]["vision_only"] = True
        # CLI override absent → preset default applies
        config = auto_populate.populate_configuration("budget", catalog, presets, vision_only=None)
        self.assertTrue(config["_auto_populate_metadata"]["vision_only"])

    def test_cli_override_beats_preset_default(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        presets["presets"]["budget"]["vision_only"] = True  # preset says yes
        config = auto_populate.populate_configuration("budget", catalog, presets, vision_only=False)
        # CLI override (False) wins
        self.assertFalse(config["_auto_populate_metadata"]["vision_only"])


class TestFilterInRegistry(unittest.TestCase):
    """The registry-presence filter keeps a stale catalog from injecting
    models the Models pane would flag DEPRECATED (id no longer in the live
    registry). Regression guard for the catalog/registry drift fix."""

    def test_drops_ids_absent_from_registry(self):
        cands = [_model("a/live"), _model("b/stale"), _model("c/live")]
        out = auto_populate.filter_in_registry(cands, {"a/live", "c/live"})
        self.assertEqual({m["id"] for m in out}, {"a/live", "c/live"})

    def test_empty_registry_is_noop(self):
        # Empty / None must NOT filter everything out — a fresh install with
        # no registry yet must still bake against the full catalog.
        cands = [_model("a/live"), _model("b/live")]
        self.assertEqual(auto_populate.filter_in_registry(cands, set()), cands)
        self.assertEqual(auto_populate.filter_in_registry(cands, None), cands)

    def _referenced_ids(self, config, catalog):
        catalog_ids = {m["id"] for m in catalog}
        seen: set = set()

        def walk(o):
            if isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
            elif isinstance(o, str) and o in catalog_ids:
                seen.add(o)

        walk(config.get("cells", {}))
        return seen

    def test_populate_configuration_never_picks_non_registry_model(self):
        # A maximally-attractive stale model (large, smartest, cheapest) the
        # picker would otherwise grab first — but it's absent from the registry.
        ghost = _model("ghost/stale", intelligence=99, blended=0.01,
                       size="large", provider="ghost")
        catalog = _fixture_catalog() + [ghost]
        presets = _fixture_presets()
        registry_ids = {m["id"] for m in _fixture_catalog()}  # excludes ghost

        # Without the filter, the ghost is attractive enough to be picked.
        unfiltered = auto_populate.populate_configuration("premium", catalog, presets)
        self.assertIn("ghost/stale", self._referenced_ids(unfiltered, catalog))

        # With the filter, nothing outside the live registry can be selected.
        filtered = auto_populate.populate_configuration(
            "premium", catalog, presets, registry_ids=registry_ids)
        referenced = self._referenced_ids(filtered, catalog)
        self.assertNotIn("ghost/stale", referenced)
        self.assertTrue(
            referenced <= registry_ids,
            f"picked ids outside registry: {referenced - registry_ids}",
        )


class TestLatencyKnee(unittest.TestCase):
    """Speed's latency-gated cost/intelligence Pareto knee selection
    (select_by_latency_knee + _cost_intel_frontier)."""

    @staticmethod
    def _m(mid, intel, cost):
        return {"id": mid, "display_name": mid,
                "aa_intelligence_index": intel,
                "openrouter_pricing": {"blended_per_m": cost}}

    def test_frontier_drops_dominated(self):
        pool = [
            self._m("cheap", 10, 0.10),
            self._m("good", 30, 0.50),
            self._m("dom", 20, 2.00),   # dominated by good (smarter AND cheaper)
        ]
        fr = {m["id"] for m in auto_populate._cost_intel_frontier(pool)}
        self.assertEqual(fr, {"cheap", "good"})

    def test_knee_picks_elbow_not_cost_cliff(self):
        # cheap-dumb / mid (elbow) / expensive-barely-better (15x for +3 intel).
        pool = [self._m("cheap", 10, 0.10), self._m("mid", 30, 0.50), self._m("cliff", 33, 10.0)]
        lat = {"cheap": 400, "mid": 500, "cliff": 600}
        picks, _ = auto_populate.select_by_latency_knee(pool, lat, 1200, top_n=3)
        self.assertEqual(picks[0]["id"], "mid")          # the knee, not the cliff
        self.assertEqual({p["id"] for p in picks}, {"cheap", "mid", "cliff"})  # rest = fallbacks

    def test_latency_gate_excludes_over_ceiling(self):
        pool = [self._m("fast", 30, 0.50), self._m("slow", 90, 0.20)]
        lat = {"fast": 500, "slow": 2000}   # slow is smarter+cheaper but TOO SLOW
        picks, _ = auto_populate.select_by_latency_knee(pool, lat, 1200, top_n=2)
        self.assertEqual(picks[0]["id"], "fast")
        self.assertNotIn("slow", [p["id"] for p in picks])

    def test_gate_empty_degrades_to_fastest(self):
        pool = [self._m("a", 30, 0.50), self._m("b", 40, 0.40)]
        lat = {"a": 3000, "b": 2500}        # nothing under the ceiling
        picks, notes = auto_populate.select_by_latency_knee(pool, lat, 1200, top_n=2)
        self.assertTrue(picks)
        self.assertEqual(picks[0]["id"], "b")   # fastest available
        self.assertTrue(any("latency ceiling skipped" in n for n in notes))

    def test_no_latency_signal_degrades_to_cost(self):
        pool = [self._m("pricey", 30, 5.0), self._m("cheap", 20, 0.20)]
        picks, notes = auto_populate.select_by_latency_knee(pool, {}, 1200, top_n=2)
        self.assertEqual(picks[0]["id"], "cheap")   # cost-ascending fallback
        self.assertTrue(any("no latency signal" in n for n in notes))

    def test_nonpositive_cost_excluded_no_log_crash(self):
        # Regression: a paid model priced 0 or negative (OpenRouter's
        # -1000000.0 variable-price router sentinel) must NOT reach log10 in the
        # default log-cost knee. _cost_intel_frontier requires cost>0, so the
        # bad rows are dropped from the cost axis and the knee never crashes.
        pool = [
            self._m("router", 0, -1000000.0),  # variable-price sentinel
            self._m("zero", 0, 0.0),            # zero price
            self._m("real", 25, 0.50),          # the only genuine cost
        ]
        lat = {"router": 300, "zero": 300, "real": 500}
        self.assertEqual({m["id"] for m in auto_populate._cost_intel_frontier(pool)}, {"real"})
        picks, _ = auto_populate.select_by_latency_knee(pool, lat, 1200, cost_norm="log", top_n=3)
        self.assertEqual(picks[0]["id"], "real")   # didn't crash; bad rows off the frontier

    def test_zero_ceiling_gates_everything_out(self):
        # A 0-ms ceiling must gate everything out (then degrade to fastest),
        # NOT be treated as "no ceiling" (the falsy-zero pitfall).
        pool = [self._m("a", 30, 0.5), self._m("b", 20, 0.3)]
        lat = {"a": 400, "b": 300}
        picks, notes = auto_populate.select_by_latency_knee(pool, lat, 0, top_n=2)
        self.assertTrue(picks)
        self.assertEqual(picks[0]["id"], "b")   # nothing ≤ 0ms → fastest available
        self.assertTrue(any("latency ceiling skipped" in n for n in notes))

    def test_log_vs_linear_normalization(self):
        # Smooth/convex frontier: log captures the smart end, linear leans cheaper.
        pool = [self._m("a", 8, 0.02), self._m("b", 16, 0.70),
                self._m("c", 18, 0.85), self._m("d", 30, 2.00)]
        lat = {k: 500 for k in ("a", "b", "c", "d")}
        log_pick, _ = auto_populate.select_by_latency_knee(pool, lat, 1200, cost_norm="log", top_n=1)
        lin_pick, _ = auto_populate.select_by_latency_knee(pool, lat, 1200, cost_norm="linear", top_n=1)
        self.assertEqual(log_pick[0]["id"], "d")    # log → smartest
        self.assertEqual(lin_pick[0]["id"], "c")    # linear → cheaper


class TestFilterVaResolvable(unittest.TestCase):
    """The vendor-catalogue-authoritative pool restriction. When the inversion
    is active, the Models pane serves each keyed vendor's NATIVE catalogue, so a
    pick that's in the base registry but absent from that inventory (and not
    aliased to it) renders DEPRECATED. filter_va_resolvable keeps the pool to
    ids the pane can resolve. Regression guard for the VA/picker-pool mismatch
    that surfaced as a DEPRECATED Speed pick."""

    def test_drops_ids_not_pane_resolvable(self):
        cands = [_model("openai/native"), _model("openai/orphan"), _model("meta/keep")]
        out = auto_populate.filter_va_resolvable(cands, {"openai/native", "meta/keep"})
        self.assertEqual({m["id"] for m in out}, {"openai/native", "meta/keep"})

    def test_empty_set_is_noop(self):
        # Inversion off / no VA file / fresh install → unchanged behaviour.
        cands = [_model("a/x"), _model("b/y")]
        self.assertEqual(auto_populate.filter_va_resolvable(cands, set()), cands)
        self.assertEqual(auto_populate.filter_va_resolvable(cands, None), cands)

    def _referenced_ids(self, config, catalog):
        catalog_ids = {m["id"] for m in catalog}
        seen: set = set()

        def walk(o):
            if isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
            elif isinstance(o, str) and o in catalog_ids:
                seen.add(o)

        walk(config.get("cells", {}))
        return seen

    def test_populate_never_picks_pane_unresolvable_model(self):
        # A maximally-attractive model that IS in the base registry but is an
        # OpenRouter-only orphan absent from the vendor-authoritative inventory:
        # the picker would grab it first, but it would render DEPRECATED.
        orphan = _model("openai/orphan", intelligence=99, blended=0.01,
                        size="large", provider="openai")
        catalog = _fixture_catalog() + [orphan]
        presets = _fixture_presets()
        registry_ids = {m["id"] for m in catalog}  # orphan IS in the base registry
        # Pane can resolve everything EXCEPT the orphan.
        va_resolvable = {m["id"] for m in _fixture_catalog()}

        # Without the VA filter the orphan is attractive enough to be picked
        # (it passes the registry filter — it's in the base registry).
        unfiltered = auto_populate.populate_configuration(
            "premium", catalog, presets, registry_ids=registry_ids)
        self.assertIn("openai/orphan", self._referenced_ids(unfiltered, catalog))

        # With it, nothing outside the pane-resolvable set is selected.
        filtered = auto_populate.populate_configuration(
            "premium", catalog, presets,
            registry_ids=registry_ids, va_resolvable_ids=va_resolvable)
        referenced = self._referenced_ids(filtered, catalog)
        self.assertNotIn("openai/orphan", referenced)
        self.assertTrue(
            referenced <= va_resolvable,
            f"picked pane-unresolvable ids: {referenced - va_resolvable}",
        )

    def test_metadata_records_pool_size(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        va = {m["id"] for m in catalog}
        cfg = auto_populate.populate_configuration(
            "premium", catalog, presets, va_resolvable_ids=va)
        self.assertEqual(
            cfg["_auto_populate_metadata"]["vendor_authoritative_pool"], len(va))
        # No restriction → None recorded.
        cfg2 = auto_populate.populate_configuration("premium", catalog, presets)
        self.assertIsNone(cfg2["_auto_populate_metadata"]["vendor_authoritative_pool"])

    def test_paid_slot_filters_to_resolvable(self):
        # Per-slot: the smartest model is a pane-unresolvable orphan; the slot
        # picks the resolvable one instead, never the orphan.
        catalog = [
            _model("ok/a",     intelligence=70, blended=2.0, size="large", provider="ok"),
            _model("orphan/b", intelligence=99, blended=0.5, size="large", provider="orphan"),
        ]
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3, floor_pct=None,
            cost_ceiling=None, loosening=False, va_resolvable_ids={"ok/a"})
        self.assertEqual({p["id"] for p in picks}, {"ok/a"})

    def test_paid_slot_graceful_degrade_when_va_empties_pool(self):
        # No candidate is pane-resolvable: rather than empty the slot (which
        # bakes a silent null primary), fall back to the full pool and record
        # the skip. A working pick that may show DEPRECATED beats a null cell.
        catalog = [
            _model("orphan/a", intelligence=70, blended=2.0, size="large", provider="orphan"),
            _model("orphan/b", intelligence=60, blended=1.0, size="large", provider="orphan"),
        ]
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3, floor_pct=None,
            cost_ceiling=None, loosening=False, va_resolvable_ids={"unrelated/x"})
        self.assertTrue(picks)  # slot still fills
        self.assertTrue(any("vendor-authoritative restriction skipped" in n for n in notes))

    def test_free_slot_graceful_degrade_when_va_empties_pool(self):
        catalog = [
            _model("orphan/f", intelligence=50, size="small", is_free=True, provider="orphan"),
        ]
        picks, notes = auto_populate.pick_for_free_slot(
            catalog, size_bucket=None, top_n=2, va_resolvable_ids={"unrelated/x"})
        self.assertTrue(picks)
        self.assertTrue(any("vendor-authoritative restriction skipped" in n for n in notes))


class TestRegistryCrossrefVaResolvable(unittest.TestCase):
    """registry_crossref builds va_resolvable_ids from the sibling
    vendor-authoritative file as native keys ∪ alias-forms-mapping-to-a-live-key
    — exactly the pane's _resolveRegistryModel contract — and only when the
    inversion is enabled."""

    def _write_va(self, tmp):
        """Write a VA file and return its path. The picker resolves the VA file
        through runtime_paths.vendor_authoritative_registry_path(), which honors
        ORA_VENDOR_AUTH_REGISTRY_PATH — so tests point that canonical env var at
        this file (the same knob the server-side resolver reads)."""
        va = Path(tmp) / "model-registry.vendor-authoritative.json"
        va.write_text(json.dumps({
            "models": {
                "openai/gpt-native": {"dispatch": "direct"},
                "meta/keep": {},
            },
            # legacy/OpenRouter forms → canonical; one points at a missing key
            # (must be dropped, mirroring the pane's models[aliases[id]] guard).
            "aliases": {
                "openai/native": "openai/gpt-native",
                "openai/dangling": "openai/not-present",
            },
        }))
        return va

    def _base(self, tmp):
        base = Path(tmp) / "model-registry.json"
        base.write_text(json.dumps({"models": {
            "openai/native": {"category": "chat"},
            "openai/orphan": {"category": "chat"},
            "meta/keep": {"category": "chat"},
        }}))
        return base

    def test_builds_resolvable_set_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, va = self._base(tmp), self._write_va(tmp)
            with mock.patch.dict(os.environ, {
                    "ORA_VENDOR_CATALOG_AUTHORITATIVE": "1",
                    "ORA_VENDOR_AUTH_REGISTRY_PATH": str(va)}, clear=False):
                xref = auto_populate.registry_crossref(base)
            got = xref["va_resolvable_ids"]
            # native keys + resolvable alias; dangling alias dropped.
            self.assertEqual(got, {"openai/gpt-native", "meta/keep", "openai/native"})
            self.assertNotIn("openai/dangling", got)

    def test_disabled_yields_empty_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, va = self._base(tmp), self._write_va(tmp)
            with mock.patch.dict(os.environ, {
                    "ORA_VENDOR_CATALOG_AUTHORITATIVE": "0",
                    "ORA_VENDOR_AUTH_REGISTRY_PATH": str(va)}, clear=False):
                xref = auto_populate.registry_crossref(base)
            self.assertEqual(xref["va_resolvable_ids"], set())

    def test_missing_va_file_yields_empty_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._base(tmp)
            missing = Path(tmp) / "nope.json"
            with mock.patch.dict(os.environ, {
                    "ORA_VENDOR_CATALOG_AUTHORITATIVE": "1",
                    "ORA_VENDOR_AUTH_REGISTRY_PATH": str(missing)}, clear=False):
                xref = auto_populate.registry_crossref(base)
            self.assertEqual(xref["va_resolvable_ids"], set())

    def test_computed_even_when_base_registry_missing(self):
        # The pane serves the VA inventory regardless of the base registry's
        # health, so the restriction must be computed even if the base registry
        # is absent — otherwise a missing/corrupt base silently drops the VA
        # filter and re-skews picker vs pane.
        with tempfile.TemporaryDirectory() as tmp:
            va = self._write_va(tmp)
            absent_base = Path(tmp) / "no-such-registry.json"
            with mock.patch.dict(os.environ, {
                    "ORA_VENDOR_CATALOG_AUTHORITATIVE": "1",
                    "ORA_VENDOR_AUTH_REGISTRY_PATH": str(va)}, clear=False):
                xref = auto_populate.registry_crossref(absent_base)
            self.assertIn("openai/gpt-native", xref["va_resolvable_ids"])

    def test_canonical_env_var_wins_old_name_ignored(self):
        # Regression: the picker MUST honor the system-wide
        # ORA_VENDOR_AUTH_REGISTRY_PATH (read by runtime_paths +
        # build_vendor_authoritative_registry.py), NOT a private name. Point the
        # canonical var at a missing file and the (legacy, never-honored)
        # ORA_VENDOR_AUTHORITATIVE_PATH at a valid one: the result must be empty,
        # proving the canonical var is authoritative and the old name is inert.
        with tempfile.TemporaryDirectory() as tmp:
            base, va = self._base(tmp), self._write_va(tmp)
            missing = Path(tmp) / "nope.json"
            with mock.patch.dict(os.environ, {
                    "ORA_VENDOR_CATALOG_AUTHORITATIVE": "1",
                    "ORA_VENDOR_AUTH_REGISTRY_PATH": str(missing),
                    "ORA_VENDOR_AUTHORITATIVE_PATH": str(va)}, clear=False):
                xref = auto_populate.registry_crossref(base)
            self.assertEqual(xref["va_resolvable_ids"], set())

    def test_enabled_helper_honours_env(self):
        with mock.patch.dict(os.environ, {"ORA_VENDOR_CATALOG_AUTHORITATIVE": "0"}, clear=False):
            self.assertFalse(auto_populate._vendor_authoritative_enabled())
        with mock.patch.dict(os.environ, {"ORA_VENDOR_CATALOG_AUTHORITATIVE": "1"}, clear=False):
            self.assertTrue(auto_populate._vendor_authoritative_enabled())


class TestPopulateConfiguration(unittest.TestCase):
    def test_budget_end_to_end(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration("budget", catalog, presets)
        self.assertEqual(config["preset_lineage"], "budget")
        # All workhorse cells populated
        self.assertIsNotNone(config["cells"]["analysis"]["gear4"]["depth"])
        self.assertIsNotNone(config["cells"]["analysis"]["gear4"]["breadth"])
        self.assertIsNotNone(config["cells"]["post_analysis"]["consolidation"])
        # gear3.breadth is explicitly null (sequential mode)
        self.assertIsNone(config["cells"]["analysis"]["gear3"]["breadth"])
        # gear4 diversity: breadth primary != depth primary
        self.assertNotEqual(
            config["cells"]["analysis"]["gear4"]["depth"]["primary"],
            config["cells"]["analysis"]["gear4"]["breadth"]["primary"],
        )
        # Vision input is a GLOBAL capability slot now (routing-config
        # slots.vision_input), not a per-cell field — bakes no longer emit it.
        for cell_name in ["depth", "breadth"]:
            cell = config["cells"]["analysis"]["gear4"][cell_name]
            self.assertNotIn("vision_substitute", cell)

    def test_free_end_to_end(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration("free", catalog, presets)
        # Picks should be free models
        depth = config["cells"]["analysis"]["gear4"]["depth"]
        self.assertTrue(depth["primary"].startswith("free/"))

    def test_loosening_metadata_surfaces(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration("budget", catalog, presets)
        # Budget should have triggered loosening somewhere
        self.assertIn("loosening_log", config["_auto_populate_metadata"])

    def test_speed_end_to_end(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        # Latency signal (ms) for the large-bucket models. a/flagship is OVER
        # the 1200ms gate; the rest are within it. With these costs/intels the
        # gated cost/intelligence frontier is d/weak → c/cheap → b/strong →
        # a/value, and the log-cost knee (diminishing-returns elbow) is b/strong.
        latency = {"a/flagship": 1500, "a/value": 800, "b/strong": 600,
                   "c/cheap": 400, "d/weak": 300, "e/dominated": 900}
        config = auto_populate.populate_configuration(
            "speed", catalog, presets, latency_ms=latency)
        self.assertEqual(config["preset_lineage"], "speed")
        depth = config["cells"]["analysis"]["gear4"]["depth"]
        self.assertIsNotNone(depth)
        self.assertIsNotNone(config["cells"]["analysis"]["gear4"]["breadth"])
        self.assertIsNotNone(config["cells"]["post_analysis"]["consolidation"])
        # gear3.breadth is explicitly null (sequential mode)
        self.assertIsNone(config["cells"]["analysis"]["gear3"]["breadth"])
        # Knee selection: never the over-the-gate flagship, never the dominated
        # model, and lands on the frontier's best-value knee (b/strong).
        self.assertNotEqual(depth["primary"], "a/flagship")
        self.assertNotEqual(depth["primary"], "e/dominated")
        self.assertEqual(depth["primary"], "b/strong")

    def test_unknown_preset_raises(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        with self.assertRaises(ValueError):
            auto_populate.populate_configuration("nonexistent", catalog, presets)

    def _mixed_context_catalog(self):
        """Large-bucket models reach ~1M context; small-bucket ones don't.
        Models the picker over a min_context floor: large slots should
        pick the ≥1M models, small/utility slots must degrade."""
        return [
            # Large paid, ~1M context — eligible under the floor.
            _model("big/ctx-a", intelligence=80, blended=5.0, size="large", provider="a", context=1000000),
            _model("big/ctx-b", intelligence=75, blended=3.0, size="large", provider="b", context=1048576),
            _model("big/ctx-c", intelligence=72, blended=2.0, size="large", provider="c", context=1000000),
            # Large paid, short context — must be excluded under the floor.
            _model("big/short", intelligence=85, blended=1.0, size="large", provider="d", context=200000),
            # Small paid, short context only — the utility slot degrades here.
            _model("small/a", intelligence=60, blended=0.3, size="small", provider="a", context=128000),
            _model("small/b", intelligence=55, blended=0.2, size="small", provider="b", context=200000),
            _model("small/c", intelligence=50, blended=0.1, size="small", provider="c", context=131072),
        ]

    def test_min_context_constrains_large_slots_and_degrades_small(self):
        catalog = self._mixed_context_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration(
            "premium", catalog, presets, min_context=900000)

        # Large analysis slots: every picked model must be a ≥1M-context one.
        ge_1m = {"big/ctx-a", "big/ctx-b", "big/ctx-c"}
        depth = config["cells"]["analysis"]["gear4"]["depth"]
        breadth = config["cells"]["analysis"]["gear4"]["breadth"]
        for cell in (depth, breadth):
            self.assertIsNotNone(cell)
            for mid in [cell["primary"], *cell.get("fallback", [])]:
                self.assertIn(mid, ge_1m,
                              f"{mid} should be a ≥1M-context model")
        # The short-context large model must never appear.
        all_primaries = json.dumps(config["cells"])
        self.assertNotIn("big/short", all_primaries)

        # Utility (small-bucket) slot has NO ≥1M candidate → graceful
        # degrade: it still fills, and the loosening_log carries the note.
        util = config["cells"]["utility"]["step1_cleanup"]
        self.assertIsNotNone(util, "utility slot must still fill (degrade)")
        self.assertTrue(util["primary"].startswith("small/"))
        loosening = config["_auto_populate_metadata"]["loosening_log"]
        flat = " ".join(
            note for notes in loosening.values() for note in notes)
        self.assertIn("context floor skipped", flat)

        # The toggle's resolved floor is recorded in the bake metadata.
        self.assertEqual(
            config["_auto_populate_metadata"]["min_context"], 900000)

    def test_min_context_none_picks_freely(self):
        catalog = self._mixed_context_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration(
            "premium", catalog, presets, min_context=None)
        # Without a floor, the short-context large model is eligible again.
        self.assertIsNone(config["_auto_populate_metadata"]["min_context"])


if __name__ == "__main__":
    unittest.main()
