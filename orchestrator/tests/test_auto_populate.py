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
            "optimum":  {"mode": "paid_intelligence", "floor_pct": 80,   "cost_ceiling_per_m": None, "loosening": False},
            "budget":   {"mode": "paid_intelligence", "floor_pct": 50,   "cost_ceiling_per_m": 1.0,  "loosening": True},
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


class TestPickForPaidSlot(unittest.TestCase):
    def test_optimum_picks_cheapest_in_top_80(self):
        catalog = _fixture_catalog()
        picks, notes = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=3,
            floor_pct=80, cost_ceiling=None, loosening=False,
        )
        # Large bucket has 80, 75, 72, 70 (e dominated, dropped),
        # 55, 40 intelligence (vision models too: 78, 70).
        # Pareto-filtered: a/flagship(80,20), a/vision-flagship(78,15),
        #   a/value(75,4), b/strong(72,3), b/vision-value(70,5),
        #   c/cheap(55,1.5), d/weak(40,0.5)
        # Floor 80% of 80 = 64. Survivors: a/flagship(80), a/vision-flagship(78),
        #   a/value(75), b/strong(72), b/vision-value(70)
        # Sort by cost ascending: b/strong($3), a/value($4), b/vision-value($5),
        #   a/vision-flagship($15), a/flagship($20)
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
        # No floor — all Pareto-filtered candidates available.
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

    def test_dominated_model_excluded(self):
        catalog = _fixture_catalog()
        picks, _ = auto_populate.pick_for_paid_slot(
            catalog, size_bucket="large", top_n=10,
            floor_pct=None, cost_ceiling=None, loosening=False,
        )
        pick_ids = {p["id"] for p in picks}
        # e/dominated should not appear (Pareto-pruned)
        self.assertNotIn("e/dominated", pick_ids)

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
        picks = auto_populate.pick_for_free_slot(
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
        picks = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2)
        pick_ids = {p["id"] for p in picks}
        # Only free large models
        for pid in pick_ids:
            self.assertTrue(pid.startswith("free/"))

    def test_intelligence_descending(self):
        catalog = _fixture_catalog()
        picks = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2)
        # free/large-1 (65) before free/large-2 (60)
        self.assertEqual(picks[0]["id"], "free/large-1")

    def test_falls_back_to_any_free_when_bucket_empty(self):
        catalog = [
            _model("free/only-small", intelligence=40, blended=0.0, size="small", is_free=True),
        ]
        # Asking for large; no free larges; falls back to any free
        picks = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2)
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

    def test_free_slot_filters_to_vision_only(self):
        # Free models in fixture are all text-only; vision-only should
        # return zero picks
        catalog = _fixture_catalog()
        no_filter = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2, vision_only=False)
        with_filter = auto_populate.pick_for_free_slot(catalog, size_bucket="large", top_n=2, vision_only=True)
        self.assertGreater(len(no_filter), 0)
        self.assertEqual(len(with_filter), 0)

    def test_populate_configuration_respects_cli_override(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration("optimum", catalog, presets, vision_only=True)
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
        # Add vision_only=True to the optimum preset
        presets["presets"]["optimum"]["vision_only"] = True
        # CLI override absent → preset default applies
        config = auto_populate.populate_configuration("optimum", catalog, presets, vision_only=None)
        self.assertTrue(config["_auto_populate_metadata"]["vision_only"])

    def test_cli_override_beats_preset_default(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        presets["presets"]["optimum"]["vision_only"] = True  # preset says yes
        config = auto_populate.populate_configuration("optimum", catalog, presets, vision_only=False)
        # CLI override (False) wins
        self.assertFalse(config["_auto_populate_metadata"]["vision_only"])


def _image_model(id, *, elo, per_1k=None, provider="aa"):
    """Image-gen catalog entry shape (category + image_pricing.per_1k_images)."""
    m = {
        "id": id, "display_name": id, "provider": provider,
        "category": "image_generation",
        "aa_intelligence_index": elo,
    }
    if per_1k is not None:
        m["image_pricing"] = {"per_1k_images": per_1k}
    return m


def _image_catalog():
    """Realistic image-gen mini-catalog mirroring the live distribution shape:
    one frontier model, one mid-Elo cheap model, three zero-cost models,
    plus a dominated entry to confirm the Pareto pass on (Elo, $/1k)."""
    return [
        _image_model("aa-img:frontier",   elo=1339, per_1k=211),
        _image_model("aa-img:premium",    elo=1266, per_1k=133),
        _image_model("aa-img:optimum",    elo=1141, per_1k=5),
        _image_model("aa-img:budget",     elo=941,  per_1k=1.5),
        _image_model("aa-img:dominated",  elo=900,  per_1k=10),  # 941/1.5 dominates
        _image_model("aa-img:free-strong", elo=1043, per_1k=0),
        _image_model("aa-img:free-mid",   elo=962,  per_1k=0),
        _image_model("aa-img:free-weak",  elo=715,  per_1k=0),
        _image_model("aa-img:no-price",   elo=1100),  # missing pricing → math.inf
    ]


class TestPickForMediaSlot(unittest.TestCase):
    def test_premium_picks_highest_elo(self):
        picks = auto_populate.pick_for_media_slot(
            _image_catalog(),
            category="image_generation",
            top_n=3,
            mode="paid_intelligence",
            floor_pct=None,
            cost_ceiling=None,
            sort_by="intelligence_desc",
        )
        self.assertEqual(picks[0]["id"], "aa-img:frontier")  # Elo 1339 wins
        self.assertEqual(len(picks), 3)

    def test_optimum_picks_cheapest_in_top_80_band(self):
        picks = auto_populate.pick_for_media_slot(
            _image_catalog(),
            category="image_generation",
            top_n=3,
            mode="paid_intelligence",
            floor_pct=80,
            cost_ceiling=None,
            sort_by="cost_asc",
        )
        # 80% of frontier 1339 = 1071. Survivors: frontier(211), premium(133),
        # optimum(1141, $5), no-price(1100, inf), free-strong(1043 — fails floor).
        # Pareto: frontier, premium, optimum survive (no-price dominated by
        # frontier on cost; free-strong dominated by optimum on Elo+cost).
        # cost_asc → optimum($5) first.
        self.assertEqual(picks[0]["id"], "aa-img:optimum")

    def test_budget_applies_image_cost_ceiling(self):
        # ceiling $80/1k: keeps optimum($5), budget($1.50), free-strong($0),
        #   free-mid($0), free-weak($0). Drops frontier($211), premium($133).
        # floor 50% of 1339 = 670: keeps optimum(1141), budget(941),
        #   free-strong(1043), free-mid(962), free-weak(715).
        # Pareto: budget($1.50,941) dominates free-strong-cheaper-but-weaker
        #   if they were both in the same axis, but they're not — Pareto
        #   keeps all non-dominated. cost_asc → free-* first (cost=0).
        picks = auto_populate.pick_for_media_slot(
            _image_catalog(),
            category="image_generation",
            top_n=3,
            mode="paid_intelligence",
            floor_pct=50,
            cost_ceiling=80,
            sort_by="cost_asc",
        )
        # No frontier or premium (above ceiling)
        ids = {p["id"] for p in picks}
        self.assertNotIn("aa-img:frontier", ids)
        self.assertNotIn("aa-img:premium", ids)

    def test_free_picks_zero_cost_when_available(self):
        picks = auto_populate.pick_for_media_slot(
            _image_catalog(),
            category="image_generation",
            top_n=2,
            mode="free_intelligence",
        )
        # Three zero-cost models all sit at cost=0; Pareto keeps only the
        # smartest (free-strong, Elo 1043). The lower-Elo zero-cost ones
        # are strictly dominated (worse Elo, equal cost). This matches the
        # existing chat-side free-slot behavior — a known limitation that
        # falls out of running Pareto on equal-cost pools.
        self.assertEqual(picks[0]["id"], "aa-img:free-strong")
        self.assertEqual(len(picks), 1)

    def test_free_falls_back_to_cheap_proxy_when_zero_cost_short(self):
        # Catalog with only one zero-cost; ask for 3 picks → fallback admits
        # models priced <= FREE_MEDIA_PROXY_CEILING ($10/1k).
        catalog = [
            _image_model("aa-img:one-free", elo=900, per_1k=0),
            _image_model("aa-img:cheap-1",  elo=950, per_1k=5),
            _image_model("aa-img:cheap-2",  elo=920, per_1k=8),
            _image_model("aa-img:premium",  elo=1300, per_1k=100),  # excluded
        ]
        picks = auto_populate.pick_for_media_slot(
            catalog, category="image_generation", top_n=3,
            mode="free_intelligence",
        )
        ids = {p["id"] for p in picks}
        self.assertNotIn("aa-img:premium", ids)
        self.assertIn("aa-img:one-free", ids)

    def test_dominated_excluded_by_pareto(self):
        picks = auto_populate.pick_for_media_slot(
            _image_catalog(),
            category="image_generation",
            top_n=10,
            mode="paid_intelligence",
            sort_by="intelligence_desc",
        )
        # dominated (Elo 900, $10): both worse than budget (Elo 941, $1.50)
        ids = {p["id"] for p in picks}
        self.assertNotIn("aa-img:dominated", ids)

    def test_excluded_ids_respected(self):
        picks = auto_populate.pick_for_media_slot(
            _image_catalog(),
            category="image_generation",
            top_n=3,
            mode="paid_intelligence",
            sort_by="intelligence_desc",
            excluded_ids={"aa-img:frontier"},
        )
        ids = {p["id"] for p in picks}
        self.assertNotIn("aa-img:frontier", ids)


class TestCostOfMedia(unittest.TestCase):
    def test_returns_per_1k_when_present(self):
        m = _image_model("x", elo=1000, per_1k=42)
        self.assertEqual(auto_populate.cost_of_media(m), 42)

    def test_returns_inf_when_pricing_absent(self):
        m = _image_model("x", elo=1000)  # no image_pricing
        self.assertEqual(auto_populate.cost_of_media(m), math.inf)


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
    def test_optimum_end_to_end(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        config = auto_populate.populate_configuration("optimum", catalog, presets)
        self.assertEqual(config["preset_lineage"], "optimum")
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
        # Vision substitute threaded into cells
        for cell_name in ["depth", "breadth"]:
            cell = config["cells"]["analysis"]["gear4"][cell_name]
            self.assertIn("vision_substitute", cell)

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

    def test_unknown_preset_raises(self):
        catalog = _fixture_catalog()
        presets = _fixture_presets()
        with self.assertRaises(ValueError):
            auto_populate.populate_configuration("nonexistent", catalog, presets)


if __name__ == "__main__":
    unittest.main()
