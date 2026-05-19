#!/usr/bin/env python3
"""Install Chunk 4 — refresh-catalog.py unit tests.

Mocks network calls; tests normalization, classification, blending,
diff detection. Live-API smoke tests are out of scope for unit tests —
they belong in a separate integration runner.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

# Import refresh-catalog.py as a module (dash in filename → load by path)
SPEC = importlib.util.spec_from_file_location(
    "refresh_catalog", REPO_ROOT / "scripts" / "refresh-catalog.py",
)
refresh_catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh_catalog)


class TestBlendCost(unittest.TestCase):
    """3:1 input:output blended-cost methodology."""

    def test_typical_chat_cost(self):
        # input=$3/M, output=$15/M → blended = (3*3 + 1*15)/4 = 6.0
        self.assertEqual(refresh_catalog.blend_cost(3.0, 15.0), 6.0)

    def test_equal_input_output(self):
        self.assertEqual(refresh_catalog.blend_cost(10.0, 10.0), 10.0)

    def test_free_model(self):
        self.assertEqual(refresh_catalog.blend_cost(0.0, 0.0), 0.0)

    def test_missing_input_returns_none(self):
        self.assertIsNone(refresh_catalog.blend_cost(None, 15.0))

    def test_missing_output_returns_none(self):
        self.assertIsNone(refresh_catalog.blend_cost(3.0, None))


class TestSizeBucketFromParameters(unittest.TestCase):
    """Open-weights models classified by published parameter count."""

    def test_small_under_12b(self):
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(3), "small")
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(8), "small")
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(11.9), "small")

    def test_midsize_12_to_50(self):
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(12), "midsize")
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(27), "midsize")
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(49.9), "midsize")

    def test_large_over_50(self):
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(50), "large")
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(70), "large")
        self.assertEqual(refresh_catalog.size_bucket_from_parameters(671), "large")

    def test_none_returns_none(self):
        # Closed proprietary models with no published count
        self.assertIsNone(refresh_catalog.size_bucket_from_parameters(None))


class TestClassifyFamily(unittest.TestCase):
    """family-classification.json rule matching."""

    def setUp(self):
        self.rules = refresh_catalog.load_family_classification()

    def test_anthropic_haiku_small(self):
        tier, bucket = refresh_catalog.classify_family(
            "anthropic/claude-haiku-4-5", "anthropic", self.rules,
        )
        self.assertEqual(tier, "fast")
        self.assertEqual(bucket, "small")

    def test_anthropic_sonnet_midsize(self):
        tier, bucket = refresh_catalog.classify_family(
            "anthropic/claude-sonnet-4-7", "anthropic", self.rules,
        )
        self.assertEqual(tier, "mid")
        self.assertEqual(bucket, "midsize")

    def test_anthropic_opus_large(self):
        tier, bucket = refresh_catalog.classify_family(
            "anthropic/claude-opus-4-7", "anthropic", self.rules,
        )
        self.assertEqual(tier, "flagship")
        self.assertEqual(bucket, "large")

    def test_openai_mini_small(self):
        tier, bucket = refresh_catalog.classify_family(
            "openai/gpt-5-mini", "openai", self.rules,
        )
        self.assertEqual(tier, "fast")
        self.assertEqual(bucket, "small")

    def test_openai_gpt5_large(self):
        tier, bucket = refresh_catalog.classify_family(
            "openai/gpt-5", "openai", self.rules,
        )
        self.assertEqual(tier, "flagship")
        self.assertEqual(bucket, "large")

    def test_google_flash_lite_small(self):
        tier, bucket = refresh_catalog.classify_family(
            "google/gemini-2.5-flash-lite", "google", self.rules,
        )
        self.assertEqual(tier, "fast")
        self.assertEqual(bucket, "small")

    def test_google_pro_large(self):
        tier, bucket = refresh_catalog.classify_family(
            "google/gemini-3-pro", "google", self.rules,
        )
        self.assertEqual(tier, "flagship")
        self.assertEqual(bucket, "large")

    def test_unknown_provider_returns_none(self):
        tier, bucket = refresh_catalog.classify_family(
            "obscure/strange-model", "obscure", self.rules,
        )
        self.assertIsNone(tier)
        self.assertIsNone(bucket)

    def test_no_pattern_matches_returns_none(self):
        tier, bucket = refresh_catalog.classify_family(
            "anthropic/some-experimental-thing", "anthropic", self.rules,
        )
        self.assertIsNone(tier)
        self.assertIsNone(bucket)


class TestNormalizeOpenRouterEntry(unittest.TestCase):
    """Conversion from OpenRouter /v1/models entry shape to our catalog shape."""

    def setUp(self):
        self.rules = refresh_catalog.load_family_classification()

    def test_typical_paid_text_model(self):
        entry = {
            "id": "openai/gpt-5",
            "name": "OpenAI: GPT-5",
            "context_length": 200000,
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "pricing": {
                "prompt": "0.000005",      # $5/M
                "completion": "0.000015",  # $15/M
            },
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertEqual(normalized["id"], "openai/gpt-5")
        self.assertEqual(normalized["provider"], "openai")
        self.assertFalse(normalized["vision_capable"])
        self.assertEqual(normalized["openrouter_pricing"]["input_per_m"], 5.0)
        self.assertEqual(normalized["openrouter_pricing"]["output_per_m"], 15.0)
        # 3:1 blend: (5*3 + 15*1) / 4 = 7.5
        self.assertEqual(normalized["openrouter_pricing"]["blended_per_m"], 7.5)
        self.assertFalse(normalized["is_free"])
        # Family-classification picks this up: openai/gpt-5 → flagship/large
        self.assertEqual(normalized["family_tier"], "flagship")
        self.assertEqual(normalized["size_bucket"], "large")

    def test_vision_capable_model(self):
        entry = {
            "id": "openai/gpt-5",
            "name": "OpenAI: GPT-5",
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
            "pricing": {"prompt": "0.000005", "completion": "0.000015"},
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertTrue(normalized["vision_capable"])

    def test_free_model(self):
        entry = {
            "id": "meta-llama/llama-3.3-70b-instruct:free",
            "name": "Meta: Llama 3.3 70B (free)",
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "pricing": {"prompt": "0", "completion": "0"},
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertTrue(normalized["is_free"])
        self.assertEqual(normalized["openrouter_pricing"]["blended_per_m"], 0.0)

    def test_missing_pricing_blended_is_none(self):
        entry = {
            "id": "experimental/model",
            "name": "Experimental",
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {},  # missing
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertIsNone(normalized["openrouter_pricing"]["blended_per_m"])

    def test_open_weights_with_param_count(self):
        # When parameters_b is set, takes precedence over family-classification
        entry = {
            "id": "meta-llama/llama-3.3-70b-instruct",
            "name": "Meta: Llama 3.3 70B",
            "parameters_b": 70,
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0.000001", "completion": "0.000003"},
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertEqual(normalized["parameters_b"], 70)
        self.assertEqual(normalized["size_bucket"], "large")


class TestEnrichWithAA(unittest.TestCase):
    """Artificial Analysis enrichment by display-name match."""

    def test_exact_name_match(self):
        catalog = [{
            "id": "openai/gpt-5", "display_name": "OpenAI: GPT-5",
            "aa_intelligence_index": None, "aa_blended_per_m": None,
        }]
        aa_data = {
            "data": [
                {"name": "openai: gpt-5", "intelligence_index": 78, "blended_cost_usd_per_million_tokens": 7.5},
            ],
        }
        enriched = refresh_catalog.enrich_with_aa(catalog, aa_data)
        self.assertEqual(enriched, 1)
        self.assertEqual(catalog[0]["aa_intelligence_index"], 78)
        self.assertEqual(catalog[0]["aa_blended_per_m"], 7.5)

    def test_substring_match(self):
        catalog = [{
            "id": "anthropic/claude-opus-4-7",
            "display_name": "Anthropic: Claude Opus 4.7",
            "aa_intelligence_index": None, "aa_blended_per_m": None,
        }]
        aa_data = {
            "data": [
                {"name": "Claude Opus 4.7", "intelligence_index": 84, "blended_cost_usd_per_million_tokens": 22.0},
            ],
        }
        enriched = refresh_catalog.enrich_with_aa(catalog, aa_data)
        self.assertEqual(enriched, 1)
        self.assertEqual(catalog[0]["aa_intelligence_index"], 84)

    def test_no_match_leaves_entry_unchanged(self):
        catalog = [{
            "id": "obscure/model", "display_name": "Obscure",
            "aa_intelligence_index": None, "aa_blended_per_m": None,
        }]
        aa_data = {"data": [{"name": "Different Model", "intelligence_index": 50}]}
        enriched = refresh_catalog.enrich_with_aa(catalog, aa_data)
        self.assertEqual(enriched, 0)
        self.assertIsNone(catalog[0]["aa_intelligence_index"])

    def test_alternative_field_names(self):
        # Defensive against AA's schema evolution: tries multiple field names
        catalog = [{
            "id": "x/y", "display_name": "X: Y",
            "aa_intelligence_index": None, "aa_blended_per_m": None,
        }]
        aa_data = {"models": [{"model_name": "X: Y", "intelligence": 60, "blended_cost": 1.0}]}
        enriched = refresh_catalog.enrich_with_aa(catalog, aa_data)
        self.assertEqual(enriched, 1)
        self.assertEqual(catalog[0]["aa_intelligence_index"], 60)


class TestDetectChanges(unittest.TestCase):
    """Per-refresh diff: new, retired, free→paid, paid→free."""

    def test_no_changes(self):
        catalog = [{"id": "a", "is_free": False}]
        changes = refresh_catalog.detect_changes(catalog, catalog)
        self.assertEqual(changes["new"], [])
        self.assertEqual(changes["retired"], [])
        self.assertEqual(changes["free_to_paid"], [])
        self.assertEqual(changes["paid_to_free"], [])

    def test_new_model(self):
        old = [{"id": "a", "is_free": False}]
        new = [{"id": "a", "is_free": False}, {"id": "b", "is_free": False}]
        changes = refresh_catalog.detect_changes(new, old)
        self.assertEqual(changes["new"], ["b"])
        self.assertEqual(changes["retired"], [])

    def test_retired_model(self):
        old = [{"id": "a", "is_free": False}, {"id": "b", "is_free": False}]
        new = [{"id": "a", "is_free": False}]
        changes = refresh_catalog.detect_changes(new, old)
        self.assertEqual(changes["new"], [])
        self.assertEqual(changes["retired"], ["b"])

    def test_free_to_paid_transition(self):
        old = [{"id": "a", "is_free": True}]
        new = [{"id": "a", "is_free": False}]
        changes = refresh_catalog.detect_changes(new, old)
        self.assertEqual(changes["free_to_paid"], ["a"])
        self.assertEqual(changes["paid_to_free"], [])

    def test_paid_to_free_transition(self):
        old = [{"id": "a", "is_free": False}]
        new = [{"id": "a", "is_free": True}]
        changes = refresh_catalog.detect_changes(new, old)
        self.assertEqual(changes["free_to_paid"], [])
        self.assertEqual(changes["paid_to_free"], ["a"])

    def test_no_old_catalog(self):
        new = [{"id": "a", "is_free": False}]
        changes = refresh_catalog.detect_changes(new, None)
        # First refresh — no diff to compute
        self.assertEqual(changes["new"], [])
        self.assertEqual(changes["retired"], [])


if __name__ == "__main__":
    unittest.main()
