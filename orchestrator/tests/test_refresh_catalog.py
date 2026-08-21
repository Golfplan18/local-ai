#!/usr/bin/env python3
"""Install Chunk 4 — refresh-catalog.py unit tests.

Mocks network calls; tests normalization, classification, blending,
diff detection. Live-API smoke tests are out of scope for unit tests —
they belong in a separate integration runner.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

# Import refresh-catalog.py as a module (dash in filename → load by path)
SPEC = importlib.util.spec_from_file_location(
    "refresh_catalog", REPO_ROOT / "scripts" / "refresh-catalog.py",
)
refresh_catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh_catalog)


class TestAuthenticatedFetchBoundary(unittest.TestCase):
    def test_optional_bearer_catalog_uses_origin_locked_transport(self):
        payload = {"data": [{"id": "vendor/model"}]}
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
             mock.patch.object(
                 refresh_catalog.network_policy, "openrouter_request_bytes",
                 return_value=(json.dumps(payload).encode(), mock.sentinel.destination),
             ) as request:
            self.assertEqual(refresh_catalog.fetch_openrouter(), payload)
        self.assertEqual(request.call_args.args[0], refresh_catalog.OPENROUTER_URL)
        self.assertEqual(
            request.call_args.kwargs["headers"]["Authorization"],
            "Bearer secret",
        )


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


class TestInferParametersFromSlug(unittest.TestCase):
    """Slug-based parameter inference for open-weights models that carry
    size in their OpenRouter slug (llama-70b, qwen3-32b, mistral-7b, etc.)."""

    def test_meta_llama_70b(self):
        self.assertEqual(refresh_catalog.infer_parameters_b_from_slug("meta-llama/llama-3.3-70b-instruct"), 70.0)

    def test_qwen_32b(self):
        self.assertEqual(refresh_catalog.infer_parameters_b_from_slug("qwen/qwen3-32b"), 32.0)

    def test_mistral_7b(self):
        self.assertEqual(refresh_catalog.infer_parameters_b_from_slug("mistralai/mistral-7b-instruct-v0.3"), 7.0)

    def test_gemma_9b(self):
        self.assertEqual(refresh_catalog.infer_parameters_b_from_slug("google/gemma-2-9b-it"), 9.0)

    def test_decimal_size(self):
        self.assertEqual(refresh_catalog.infer_parameters_b_from_slug("nousresearch/hermes-3-llama-3.1-8.1b"), 8.1)

    def test_405b(self):
        self.assertEqual(refresh_catalog.infer_parameters_b_from_slug("meta-llama/llama-3.1-405b-instruct"), 405.0)

    def test_closed_proprietary_returns_none(self):
        # No Nb pattern → family-classification takes over
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("anthropic/claude-opus-4-7"))
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("openai/gpt-5"))
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("google/gemini-3-pro"))

    def test_named_tier_returns_none(self):
        # Named tiers without Nb suffix → family-classification takes over
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("deepseek/deepseek-v4-pro"))
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("qwen/qwen3.6-plus"))
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("moonshotai/kimi-k2.6"))
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("z-ai/glm-5"))

    def test_empty_returns_none(self):
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug(""))
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug(None))

    def test_version_numbers_dont_match(self):
        # "v3" is a version, not "3b"; we shouldn't false-fire on v3-style markers
        # Pattern requires Nb followed by a delimiter or end; "v3-" doesn't end in b
        self.assertIsNone(refresh_catalog.infer_parameters_b_from_slug("provider/model-v3-instruct"))


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

    def test_open_weights_inferred_from_slug(self):
        # parameters_b not set in OR response; inferred from slug
        entry = {
            "id": "qwen/qwen3-32b",
            "name": "Qwen 3 32B",
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0.000001", "completion": "0.000003"},
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertEqual(normalized["parameters_b"], 32.0)
        self.assertEqual(normalized["size_bucket"], "midsize")

    def test_named_tier_falls_through_to_family_rules(self):
        # No Nb in slug → falls through to family-classification.json
        entry = {
            "id": "deepseek/deepseek-v4-pro",
            "name": "DeepSeek V4 Pro",
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0.0000005", "completion": "0.0000015"},
        }
        normalized = refresh_catalog.normalize_openrouter_entry(entry, self.rules)
        self.assertIsNone(normalized["parameters_b"])  # not extracted from slug
        # Family rule for deepseek v4-pro → large
        self.assertEqual(normalized["size_bucket"], "large")
        self.assertEqual(normalized["family_tier"], "flagship")


class TestEnrichFromModelRegistry(unittest.TestCase):
    """Catalog enrichment from the curated model registry (replaces the
    prior direct AA API fetch; the registry itself is now sourced from
    OpenRouter + LiteLLM + Chatbot Arena + AA's public /models page).

    The registry is keyed by OpenRouter id — direct lookup, no fuzzy
    matching needed at the catalog layer.
    """

    def test_intelligence_copied_when_registry_has_entry(self):
        catalog = [{
            "id": "openai/gpt-5", "openrouter_slug": "openai/gpt-5",
            "display_name": "OpenAI: GPT-5",
            "aa_intelligence_index": None,
        }]
        registry = {"models": {
            "openai/gpt-5": {"aa_intelligence_index": 78.0},
        }}
        enriched = refresh_catalog.enrich_from_model_registry(catalog, registry)
        self.assertEqual(enriched, 1)
        self.assertEqual(catalog[0]["aa_intelligence_index"], 78.0)

    def test_no_registry_entry_leaves_field_null(self):
        catalog = [{
            "id": "obscurevendor/xyzzy", "openrouter_slug": "obscurevendor/xyzzy",
            "aa_intelligence_index": None,
        }]
        registry = {"models": {"unrelated/model": {"aa_intelligence_index": 50.0}}}
        enriched = refresh_catalog.enrich_from_model_registry(catalog, registry)
        self.assertEqual(enriched, 0)
        self.assertIsNone(catalog[0]["aa_intelligence_index"])

    def test_null_intelligence_does_not_count_as_enriched(self):
        # Registry has the entry but no AA score — count stays at 0
        catalog = [{
            "id": "sao10k/some-rp-tune", "openrouter_slug": "sao10k/some-rp-tune",
            "aa_intelligence_index": None,
        }]
        registry = {"models": {
            "sao10k/some-rp-tune": {"aa_intelligence_index": None},
        }}
        enriched = refresh_catalog.enrich_from_model_registry(catalog, registry)
        self.assertEqual(enriched, 0)
        self.assertIsNone(catalog[0]["aa_intelligence_index"])

    def test_empty_or_missing_registry_yields_zero(self):
        catalog = [{"id": "x/y", "openrouter_slug": "x/y",
                    "aa_intelligence_index": None}]
        # Empty models dict
        self.assertEqual(refresh_catalog.enrich_from_model_registry(catalog, {}), 0)
        self.assertEqual(refresh_catalog.enrich_from_model_registry(catalog, {"models": {}}), 0)
        # None registry
        self.assertEqual(refresh_catalog.enrich_from_model_registry(catalog, None), 0)

    def test_catalog_entry_without_id_skipped(self):
        # Defensive: missing openrouter_slug AND id → skip, don't crash
        catalog = [{"display_name": "Mystery model",
                    "aa_intelligence_index": None}]
        registry = {"models": {"x/y": {"aa_intelligence_index": 50.0}}}
        enriched = refresh_catalog.enrich_from_model_registry(catalog, registry)
        self.assertEqual(enriched, 0)


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


class TestNameMarkerSizeClassification(unittest.TestCase):
    """2026-06-14: a model that announces a smaller/speed tier in its name
    is classified by that marker so the picker's large slots exclude it by
    capability — even when it has no parameter count and no family rule."""

    def test_small_markers(self):
        for slug, expected in [
            ("mistralai/mistral-small-2603", "small"),
            ("microsoft/phi-4-mini-instruct", "small"),
            ("openai/gpt-5.4-nano", "small"),
            ("amazon/nova-lite-v1", "small"),
            ("x/something-tiny", "small"),
        ]:
            self.assertEqual(
                refresh_catalog.infer_size_from_name_markers(slug), expected,
                f"{slug} should be small")

    def test_flash_is_midsize(self):
        self.assertEqual(
            refresh_catalog.infer_size_from_name_markers("stepfun/step-3.7-flash"),
            "midsize")

    def test_marker_must_be_delimited_token(self):
        # "mini" inside "gemini" must NOT match; codenames stay None.
        self.assertIsNone(
            refresh_catalog.infer_size_from_name_markers("google/gemini-3.1-pro"))
        self.assertIsNone(
            refresh_catalog.infer_size_from_name_markers("anthropic/claude-fable-5"))
        self.assertIsNone(
            refresh_catalog.infer_size_from_name_markers("x-ai/grok-4.3"))

    def test_classification_order_params_win(self):
        # A real param count (via normalize) takes precedence over a name
        # marker — infer_size is only the last resort.
        rules = {"providers": {}}
        entry = {"id": "meta/llama-3-70b-mini", "pricing": {}, "architecture": {}}
        out = refresh_catalog.normalize_openrouter_entry(entry, rules)
        self.assertEqual(out["size_bucket"], "large")  # 70b wins over "mini"
