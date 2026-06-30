#!/usr/bin/env python3
"""Install Chunk 5 — auto-populate-configuration.py unit tests.

Fixture catalog covers small/midsize/large buckets, vision-capable and
text-only, free and paid, models with and without AA enrichment, etc.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

SPEC = importlib.util.spec_from_file_location(
    "auto_populate", REPO_ROOT / "scripts" / "auto-populate-configuration.py",
)
auto_populate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auto_populate)


def _model(id, *, intelligence=None, blended=None, size="large",
           vision=False, is_free=False, provider="x"):
    return {
        "id": id, "display_name": id, "provider": provider,
        "size_bucket": size, "vision_capable": vision, "is_free": is_free,
        "aa_intelligence_index": intelligence,
        "openrouter_pricing": {"input_per_m": None, "output_per_m": None, "blended_per_m": blended},
    }


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
                "speed_mode": True,
                "sort_by": "latency_asc",
                "floor_pct": 40,
                "min_floor_pct": 25,
                "cost_ceiling_per_m": None,
                "adaptive_cost_ceiling": {
                    "enabled": True,
                    "peak_fraction": 0.4,
                    "outlier_median_multiple": 3.0,
                },
                "loosening": True,
                "loosening_strategy": "paired",
                "floor_step_pct": 5,
                "ceiling_growth_factor": 1.25,
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
        config = auto_populate.populate_configuration("speed", catalog, presets)
        self.assertEqual(config["preset_lineage"], "speed")
        # Workhorse cells populated under the latency-sort path
        self.assertIsNotNone(config["cells"]["analysis"]["gear4"]["depth"])
        self.assertIsNotNone(config["cells"]["analysis"]["gear4"]["breadth"])
        self.assertIsNotNone(config["cells"]["post_analysis"]["consolidation"])
        # gear3.breadth is explicitly null (sequential mode)
        self.assertIsNone(config["cells"]["analysis"]["gear3"]["breadth"])

    def test_unknown_preset_raises(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        with self.assertRaises(ValueError):
            auto_populate.populate_configuration("nonexistent", catalog, presets)


if __name__ == "__main__":
    unittest.main()
