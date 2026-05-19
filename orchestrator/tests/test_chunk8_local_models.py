#!/usr/bin/env python3
"""Install Chunk 8 — local_models.py tests.

Covers hardware tier classification, RAM estimation formulas (including
the new 3-bit option), recommendations per tier, and state persistence.
Actual huggingface_hub downloads are not exercised (multi-GB files);
the download_model function's dry-run path is tested instead.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

SPEC = importlib.util.spec_from_file_location(
    "local_models", REPO_ROOT / "scripts" / "local_models.py",
)
local_models = importlib.util.module_from_spec(SPEC)
# Register in sys.modules BEFORE exec_module so @dataclass can resolve
# the class's home module at definition time (Python 3.14 strictness).
sys.modules["local_models"] = local_models
SPEC.loader.exec_module(local_models)


class TestRAMEstimation(unittest.TestCase):
    """RAM estimation formulas preserved from layer2-model-selection.md
    plus the new 3-bit addition for Chunk 8."""

    def test_4bit_70b(self):
        # 70B × 0.5 + 2 = 37 GB
        self.assertEqual(local_models.estimate_ram_required_gb(70, "4-bit"), 37.0)

    def test_4bit_7b(self):
        # 7B × 0.5 + 2 = 5.5 GB
        self.assertEqual(local_models.estimate_ram_required_gb(7, "4-bit"), 5.5)

    def test_8bit_70b(self):
        # 70B × 1.0 + 2 = 72 GB
        self.assertEqual(local_models.estimate_ram_required_gb(70, "8-bit"), 72.0)

    def test_3bit_70b(self):
        # 70B × 0.375 + 2 = 28.25 GB — extends 64GB Tier 4 reach
        self.assertEqual(local_models.estimate_ram_required_gb(70, "3-bit"), 28.25)

    def test_16bit_7b(self):
        # 7B × 2.0 + 2 = 16 GB (rare; for sanity)
        self.assertEqual(local_models.estimate_ram_required_gb(7, "16-bit"), 16.0)

    def test_unknown_quant_defaults_to_4bit(self):
        # Defensive fallback when quantization label is unrecognized
        self.assertEqual(
            local_models.estimate_ram_required_gb(7, "weird-quant"),
            local_models.estimate_ram_required_gb(7, "4-bit"),
        )


class TestHardwareClassification(unittest.TestCase):
    """User-facing deployment tiers (≤32 / 32-64 / 64-128 / 128+)."""

    def test_8gb_laptop_classifies_small_only(self):
        tier = local_models.classify_hardware(8.0)
        self.assertEqual(tier.name, "small_only")
        self.assertAlmostEqual(tier.available_ram_gb, 6.0)

    def test_16gb_classifies_small_only(self):
        tier = local_models.classify_hardware(16.0)
        self.assertEqual(tier.name, "small_only")

    def test_32gb_classifies_workhorse_choice(self):
        # Boundary: 32 is the lower edge of the 32-64 tier
        tier = local_models.classify_hardware(32.0)
        self.assertEqual(tier.name, "workhorse_choice")
        self.assertAlmostEqual(tier.available_ram_gb, 24.0)

    def test_48gb_classifies_workhorse_choice(self):
        tier = local_models.classify_hardware(48.0)
        self.assertEqual(tier.name, "workhorse_choice")

    def test_64gb_classifies_full_local(self):
        # Boundary: 64 is the lower edge of full_local
        tier = local_models.classify_hardware(64.0)
        self.assertEqual(tier.name, "full_local")
        self.assertAlmostEqual(tier.available_ram_gb, 48.0)

    def test_96gb_classifies_full_local(self):
        tier = local_models.classify_hardware(96.0)
        self.assertEqual(tier.name, "full_local")

    def test_128gb_classifies_adversarial(self):
        # Boundary: 128 is the lower edge of adversarial
        tier = local_models.classify_hardware(128.0)
        self.assertEqual(tier.name, "adversarial")
        self.assertAlmostEqual(tier.available_ram_gb, 96.0)

    def test_256gb_classifies_adversarial(self):
        tier = local_models.classify_hardware(256.0)
        self.assertEqual(tier.name, "adversarial")


class TestRecommendations(unittest.TestCase):
    """Each tier has curated model recommendations matching its budget."""

    def test_small_only_has_utility_recommendation(self):
        recs = local_models.recommend_models_for_tier("small_only")
        self.assertGreater(len(recs), 0)
        utility_recs = [r for r in recs if r.role == "utility"]
        self.assertGreater(len(utility_recs), 0)

    def test_full_local_has_workhorse_and_utility(self):
        recs = local_models.recommend_models_for_tier("full_local")
        roles = {r.role for r in recs}
        self.assertIn("workhorse_a", roles)
        self.assertIn("utility", roles)

    def test_adversarial_has_two_workhorses_different_families(self):
        recs = local_models.recommend_models_for_tier("adversarial")
        workhorse_a = next((r for r in recs if r.role == "workhorse_a"), None)
        workhorse_b = next((r for r in recs if r.role == "workhorse_b"), None)
        self.assertIsNotNone(workhorse_a)
        self.assertIsNotNone(workhorse_b)
        # Different model families for adversarial diversity
        self.assertNotEqual(workhorse_a.id, workhorse_b.id)

    def test_all_recommendations_are_dense(self):
        # MoE rejection rule preserved from layer2-model-selection.md
        for tier_name in ("small_only", "workhorse_choice", "full_local", "adversarial"):
            for r in local_models.recommend_models_for_tier(tier_name):
                self.assertEqual(r.architecture, "dense", f"{tier_name}/{r.id} should be dense")

    def test_unknown_tier_returns_empty(self):
        self.assertEqual(local_models.recommend_models_for_tier("nonexistent"), [])


class TestRecommendationsFitTier(unittest.TestCase):
    """Each tier's recommendations actually fit the tier's RAM budget."""

    def _budget(self, tier_name: str, total_ram: float) -> float:
        return local_models.classify_hardware(total_ram).available_ram_gb

    def test_small_only_recommendations_fit_24gb_machine(self):
        # 24GB is mid-range for small_only; recommendations should comfortably fit
        budget = self._budget("small_only", 24.0)
        for r in local_models.recommend_models_for_tier("small_only"):
            self.assertLess(
                local_models.estimate_ram_required_gb(r.parameters_b, r.quantization),
                budget,
                f"{r.display_name} doesn't fit small_only tier on 24GB",
            )

    def test_full_local_recommendations_fit_64gb_machine(self):
        # 64GB is the lower edge of full_local; sum of all recs should fit
        budget = self._budget("full_local", 64.0)
        total = sum(
            local_models.estimate_ram_required_gb(r.parameters_b, r.quantization)
            for r in local_models.recommend_models_for_tier("full_local")
        )
        self.assertLessEqual(
            total, budget,
            f"full_local recommendations total {total:.1f}GB > 64GB budget {budget:.1f}GB",
        )


class TestStatePersistence(unittest.TestCase):
    """local-models.json round-trips."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_patch = mock.patch.object(
            local_models, "LOCAL_MODELS_STATE",
            Path(self.tmp.name) / "local-models.json",
        )
        self.state_patch.start()

    def tearDown(self):
        self.state_patch.stop()
        self.tmp.cleanup()

    def test_load_default_when_missing(self):
        state = local_models.load_local_models_state()
        self.assertEqual(state, {"installed": [], "selected": {}})

    def test_save_then_load_roundtrip(self):
        state = {"installed": [{"id": "test/model", "parameters_b": 7}], "selected": {"workhorse_a": "test/model"}}
        local_models.save_local_models_state(state)
        loaded = local_models.load_local_models_state()
        self.assertEqual(loaded["installed"][0]["id"], "test/model")
        self.assertEqual(loaded["selected"]["workhorse_a"], "test/model")


class TestDownloadDryRun(unittest.TestCase):
    """download_model dry-run returns None and doesn't touch huggingface_hub."""

    def test_dry_run_returns_none(self):
        result = local_models.download_model("fake/repo", dry_run=True)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
