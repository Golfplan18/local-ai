#!/usr/bin/env python3
"""Tests for the vendor-catalogue-authoritative transform (pure logic)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import vendor_catalog_registry as vcr  # noqa: E402


class TestEnabledFlag(unittest.TestCase):
    def test_default_on(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORA_VENDOR_CATALOG_AUTHORITATIVE", None)
            self.assertTrue(vcr.enabled())
        for off in ("0", "false", "no", "off"):
            with mock.patch.dict(os.environ, {"ORA_VENDOR_CATALOG_AUTHORITATIVE": off}):
                self.assertFalse(vcr.enabled())


class TestChatFilter(unittest.TestCase):
    def test_keeps_chat(self):
        self.assertTrue(vcr.is_chat_model("qwen", {"id": "qwen-plus"}))
        self.assertTrue(vcr.is_chat_model("qwen", {"id": "qwen3-vl-plus"}))   # multimodal chat
        self.assertTrue(vcr.is_chat_model("xai", {"id": "grok-4.3"}))

    def test_drops_nonchat(self):
        for bad in ("text-embedding-v4", "qwen-image-max", "wan2.7-image-pro",
                    "cosyvoice-v2", "paraformer-asr", "qwen-mt-ocr", "z-image-turbo"):
            self.assertFalse(vcr.is_chat_model("qwen", {"id": bad}), bad)

    def test_drops_embedders_with_trailing_tokens_and_bge(self):
        for bad in ("nvidia/nv-embedqa-e5-v5", "nvidia/nv-embedcode-7b-v1",
                    "baai/bge-m3", "nvidia/nv-embed-v1"):
            self.assertFalse(vcr.is_chat_model("nvidia", {"id": bad}), bad)

    def test_drops_qwen_mt_translators(self):
        for bad in ("qwen-mt-flash", "qwen-mt-turbo", "qwen-mt-plus"):
            self.assertFalse(vcr.is_chat_model("qwen", {"id": bad}), bad)
        self.assertTrue(vcr.is_chat_model("qwen", {"id": "qwen-max"}))  # not an MT model

    def test_drops_nvidia_nonchat_nim_types(self):
        for bad in ("nvidia/nemotron-4-340b-reward", "nvidia/nemoretriever-parse",
                    "nvidia/nvclip", "nvidia/gliner-pii"):
            self.assertFalse(vcr.is_chat_model("nvidia", {"id": bad}), bad)

    def test_native_capability_flag_wins(self):
        self.assertFalse(vcr.is_chat_model("mistral", {"id": "mistral-embed", "capabilities": {"completion_chat": False}}))
        self.assertTrue(vcr.is_chat_model("mistral", {"id": "mistral-medium", "capabilities": {"completion_chat": True}}))


class TestNormalize(unittest.TestCase):
    def test_collapse_and_strip(self):
        self.assertEqual(vcr._norm("models/gemini-2.5-flash"), vcr._norm("gemini-2.5-flash"))
        self.assertEqual(vcr._norm("MiniMax-M2.7"), "minimaxm27")
        self.assertEqual(vcr._norm("qwen3.7-max-2026-06-08"), vcr._norm("qwen3.7-max"))
        self.assertEqual(vcr._norm("mistral-large-2411"), vcr._norm("mistral-large"))

    def test_sibling_variants_stay_distinct(self):
        # -instruct vs -thinking are different models — must NOT collapse together.
        a = vcr._norm("qwen3-235b-a22b-instruct")
        b = vcr._norm("qwen3-235b-a22b-thinking")
        self.assertNotEqual(a, b)


class TestEnrichIndex(unittest.TestCase):
    def test_vendor_prefix_set_and_alias_rows(self):
        items = [
            ("qwen/qwen-plus", {"x": 1}),
            ("alibaba/qwen3-max", {"x": 2}),       # alt prefix
            ("~qwen/qwen-flash", {"x": 3}),        # AA alias row
            ("openai/gpt-5", {"x": 9}),            # other vendor — excluded
        ]
        idx = vcr._enrich_index("qwen", items)
        self.assertIn(vcr._norm("qwen-plus"), idx)
        self.assertIn(vcr._norm("qwen3-max"), idx)
        self.assertIn(vcr._norm("qwen-flash"), idx)
        self.assertNotIn(vcr._norm("gpt-5"), idx)


class TestMerge(unittest.TestCase):
    def test_native_first_then_aa_then_or(self):
        aa = {vcr._norm("qwen-plus"): {
            "display_name": "Qwen Plus", "context_length": 131072,
            "aa_intelligence_index": 55, "output_tokens_per_second": 90,
            "pricing": {"input_per_token": 4e-7, "output_per_token": 1.2e-6},
            "reasoning_model": False}}
        e = vcr.merge_entry("qwen", {"id": "qwen-plus", "context_length": 1000000}, aa, {})
        self.assertEqual(e["native_model_id"], "qwen-plus")
        self.assertEqual(e["id"], "qwen/qwen-plus")
        self.assertEqual(e["dispatch"], "direct")
        self.assertEqual(e["context_length"], 1000000)         # native wins
        self.assertEqual(e["_enrichment_source"]["context_length"], "native")
        self.assertEqual(e["intelligence_index"], 55)          # AA only
        self.assertEqual(e["aa_intelligence_index"], 55)       # field the Models pane reads
        self.assertEqual(e["output_tokens_per_second"], 90)
        self.assertEqual(e["_enrichment_source"]["pricing"], "aa")

    def test_openrouter_price_fallback_per_million_to_per_token(self):
        orr = {vcr._norm("minimax-m2"): {"pricing_per_million": {"prompt": 0.3, "completion": 1.2}}}
        e = vcr.merge_entry("minimax", {"id": "MiniMax-M2"}, {}, orr)
        self.assertEqual(e["pricing"]["input_per_token"], 0.3 / 1e6)
        self.assertEqual(e["_enrichment_source"]["pricing"], "openrouter")
        self.assertIsNone(e["intelligence_index"])             # OR has no intelligence

    def test_elo_does_not_leak_into_intelligence_index(self):
        # qwen-plus has only an Arena Elo (intelligence_score≈1325), no AA Index.
        aa = {vcr._norm("qwen-plus"): {"aa_intelligence_index": None, "intelligence_score": 1325.0}}
        e = vcr.merge_entry("qwen", {"id": "qwen-plus"}, aa, {})
        self.assertIsNone(e["intelligence_index"])     # NOT 1325
        self.assertEqual(e["intelligence_score"], 1325.0)

    def test_vision_capable_detection(self):
        # native flag
        self.assertTrue(vcr.merge_entry("moonshot", {"id": "kimi-k2-vision", "supports_image_in": True}, {}, {})["vision_capable"])
        # AA enrichment
        aa = {vcr._norm("gpt-5"): {"vision_capable": True}}
        self.assertTrue(vcr.merge_entry("openai", {"id": "gpt-5"}, aa, {})["vision_capable"])
        # id heuristic (vl / omni)
        self.assertTrue(vcr.merge_entry("qwen", {"id": "qwen3-vl-plus"}, {}, {})["vision_capable"])
        self.assertTrue(vcr.merge_entry("qwen", {"id": "qwen3-omni-flash"}, {}, {})["vision_capable"])
        # unknown → None (text-only, no enrichment)
        self.assertIsNone(vcr.merge_entry("deepseek", {"id": "deepseek-chat"}, {}, {})["vision_capable"])

    def test_unmatched_is_blank_not_broken(self):
        e = vcr.merge_entry("xiaomi", {"id": "mimo-v9"}, {}, {})
        self.assertEqual(e["native_model_id"], "mimo-v9")
        self.assertIsNone(e["intelligence_index"])
        self.assertIsNone(e["pricing"])
        self.assertFalse(e["_enrichment_matched"])
        self.assertEqual(e["display_name"], "mimo-v9")


class TestBuild(unittest.TestCase):
    def test_dedup_or_and_add_native(self):
        base = {
            "qwen/qwen-2.5-72b-instruct": {"vendor": "qwen", "aa_intelligence_index": 40},
            "qwen/qwen-plus": {"display_name": "Qwen Plus", "aa_intelligence_index": 55,
                               "pricing": {"input_per_token": 1e-7}},
            "anthropic/claude-opus-4.8": {"vendor": "anthropic"},   # untouched (no qwen prefix)
        }
        cats = {"qwen": [{"id": "qwen-plus"}, {"id": "qwen3-max"}, {"id": "qwen-image-max"}]}
        new, report = vcr.build_authoritative_registry(base, cats, or_models=[])
        # all OpenRouter qwen/* removed
        self.assertNotIn("qwen/qwen-2.5-72b-instruct", new)
        # native chat models added (image dropped)
        self.assertIn("qwen/qwen-plus", new)
        self.assertEqual(new["qwen/qwen-plus"]["dispatch"], "direct")
        self.assertIn("qwen/qwen3-max", new)
        self.assertNotIn("qwen/qwen-image-max", new)
        # other vendor untouched
        self.assertIn("anthropic/claude-opus-4.8", new)
        r = report["qwen"]
        self.assertEqual(r["native_chat_added"], 2)
        self.assertEqual(r["non_chat_dropped"], 1)
        self.assertEqual(r["openrouter_removed"], 2)
        # qwen-plus picked up AA intelligence via the match
        self.assertEqual(new["qwen/qwen-plus"]["intelligence_index"], 55)

    def test_malformed_record_skipped_not_fatal(self):
        cats = {"qwen": [{"object": "model"}, {"id": "qwen-plus"}, {}]}  # two have no id
        new, report = vcr.build_authoritative_registry({}, cats, or_models=[])
        self.assertIn("qwen/qwen-plus", new)
        self.assertEqual(report["qwen"]["native_chat_added"], 1)


class TestNonChatJunk(unittest.TestCase):
    def test_drops_openai_nonchat_surfaces(self):
        for bad in ("davinci-002", "babbage-002", "omni-moderation-latest",
                    "omni-moderation-2024-09-26", "gpt-realtime", "gpt-realtime-mini",
                    "gpt-5-search-api", "lyria-3-pro-preview", "lyria-realtime-exp"):
            self.assertFalse(vcr.is_chat_model("openai", {"id": bad}), bad)

    def test_drops_google_nonchat_products(self):
        for bad in ("veo-3.0-generate-001", "veo-3.1-fast-generate-preview",
                    "nano-banana-pro-preview", "aqa", "gemini-robotics-er-1.5-preview",
                    "deep-research-preview-04-2026", "antigravity-preview-05-2026"):
            self.assertFalse(vcr.is_chat_model("gemini", {"id": bad}), bad)

    def test_keeps_real_google_chat_models(self):
        for ok in ("gemini-3.5-flash", "gemma-4-31b-it", "gemini-2.5-computer-use-preview"):
            self.assertTrue(vcr.is_chat_model("gemini", {"id": ok}), ok)


class TestEnrichmentNoCrossAttach(unittest.TestCase):
    def test_dated_sibling_matches_own_row_not_collapsed_twin(self):
        # gpt-4o-2024-05-13 must get ITS OWN metadata, not gpt-4o-2024-11-20's.
        aa_items = [
            ("openai/gpt-4o-2024-11-20", {"aa_intelligence_index": 17.3}),
            ("openai/gpt-4o-2024-05-13", {"aa_intelligence_index": 14.5}),
        ]
        idx = vcr._enrich_index("openai", aa_items)
        e = vcr.merge_entry("openai", {"id": "gpt-4o-2024-05-13"}, idx, {})
        self.assertEqual(e["aa_intelligence_index"], 14.5)   # own row, precise tier

    def test_fast_variant_does_not_pollute_ga(self):
        # claude-opus-4.8-fast is a distinct, higher-priced serving tier; its
        # price must NOT attach to the GA claude-opus-4-8.
        aa_items = [
            ("anthropic/claude-opus-4.8-fast", {"pricing": {"input_per_token": 1e-5, "output_per_token": 5e-5}}),
            ("anthropic/claude-opus-4-8", {"pricing": {"input_per_token": 5e-6, "output_per_token": 2.5e-5}}),
        ]
        idx = vcr._enrich_index("anthropic", aa_items)
        ga = vcr.merge_entry("anthropic", {"id": "claude-opus-4-8"}, idx, {})
        self.assertEqual(ga["pricing"]["input_per_token"], 5e-6)   # GA's own price
        fast = vcr.merge_entry("anthropic", {"id": "claude-opus-4.8-fast"}, idx, {})
        self.assertEqual(fast["pricing"]["input_per_token"], 1e-5)  # -fast keeps its own

    def test_preview_falls_back_to_base_when_no_own_row(self):
        # gemini preview WITHOUT its own AA row still inherits the base via loose.
        aa_items = [("google/gemini-2.5-flash", {"aa_intelligence_index": 30})]
        idx = vcr._enrich_index("gemini", aa_items)
        e = vcr.merge_entry("gemini", {"id": "models/gemini-2.5-flash-preview-05-20"}, idx, {})
        self.assertEqual(e["aa_intelligence_index"], 30)   # loose fallback


class TestVisionPrecedence(unittest.TestCase):
    def test_or_accepts_image_false_beats_family_table(self):
        # gpt-4o-search-preview matches the gpt-4o family rule but OR says no image.
        e = vcr._vision({}, {"vision_capable": False}, {"accepts_image": False},
                        "gpt-4o-search-preview")
        self.assertIs(e, False)

    def test_search_preview_negated_even_without_or_twin(self):
        self.assertIs(vcr._vision({}, {}, {}, "gpt-4o-search-preview-2025-03-11"), False)

    def test_family_true_survives_stale_aa_false_when_no_or_signal(self):
        # gpt-5.5 has a stale AA vision=False but no OR twin → family True wins.
        self.assertIs(vcr._vision({}, {"vision_capable": False}, {}, "gpt-5.5"), True)

    def test_keeps_qwen_omni_realtime_multimodal_chat(self):
        # gpt-realtime is OpenAI-scoped; must NOT match Qwen's omni-realtime.
        for ok in ("qwen3-omni-flash-realtime", "qwen3.5-omni-plus-realtime",
                   "gpt-4o", "gpt-5.4", "gemini-2.5-flash"):
            self.assertTrue(vcr.is_chat_model("qwen", {"id": ok}), ok)


class TestVisionFamily(unittest.TestCase):
    def test_known_vision_families_true(self):
        for vid, mid in (("openai", "gpt-5.4"), ("openai", "gpt-4o"),
                         ("gemini", "gemini-3.5-flash"), ("anthropic", "claude-opus-4-8"),
                         ("mistral", "pixtral-large"), ("xai", "grok-4.3")):
            self.assertIs(vcr._vision({}, {}, {}, mid), True, mid)

    def test_text_only_siblings_false_or_none(self):
        self.assertIs(vcr._vision({}, {}, {}, "claude-3-5-haiku"), False)

    def test_moderation_not_vision(self):
        # 'omni-moderation' matches the 'omni-' heuristic but is text classification.
        self.assertIsNone(vcr._vision({}, {}, {}, "omni-moderation-latest"))

    def test_unknown_stays_none(self):
        self.assertIsNone(vcr._vision({}, {}, {}, "deepseek-chat"))


class TestSizeClassify(unittest.TestCase):
    RULES = {
        "google": [{"pattern": "flash-lite", "size_bucket": "small"},
                   {"pattern": "flash", "size_bucket": "midsize"},
                   {"pattern": "pro", "size_bucket": "large"}],
        "x-ai": [{"pattern": "grok", "size_bucket": "large"}],
    }

    def test_param_count_still_wins(self):
        # explicit param count in id is authoritative; classifier not consulted.
        e = vcr.merge_entry("qwen", {"id": "qwen3-235b-a22b"}, {}, {}, self.RULES)
        self.assertEqual(e["size_bucket"], "large")
        self.assertEqual(e["parameters_b"], 235)

    def test_family_fallback_for_flagship(self):
        e = vcr.merge_entry("gemini", {"id": "models/gemini-3.5-flash"}, {}, {}, self.RULES)
        self.assertEqual(e["size_bucket"], "midsize")  # 'flash' rule (vendor alias google)
        self.assertIsNone(e["parameters_b"])           # no real param count invented

    def test_specificity_order(self):
        e = vcr.merge_entry("gemini", {"id": "gemini-3.5-flash-lite"}, {}, {}, self.RULES)
        self.assertEqual(e["size_bucket"], "small")     # flash-lite before flash

    def test_no_rules_leaves_none(self):
        e = vcr.merge_entry("xiaomi", {"id": "mimo-v9"}, {}, {})
        self.assertIsNone(e["size_bucket"])


class TestGeminiPrefixStrip(unittest.TestCase):
    def test_models_prefix_stripped_from_key_and_native_id(self):
        e = vcr.merge_entry("gemini", {"id": "models/gemini-2.5-flash"}, {}, {})
        self.assertEqual(e["id"], "gemini/gemini-2.5-flash")        # not gemini/models/...
        self.assertEqual(e["native_model_id"], "gemini-2.5-flash")

    def test_norm_preview_date_collapses(self):
        self.assertEqual(vcr._norm("models/gemini-2.5-flash-preview-05-20"),
                         vcr._norm("gemini-2.5-flash"))


class TestLegacyAliases(unittest.TestCase):
    def test_covers_inversion_id_forms(self):
        cases = [
            ("gemini", "gemini-3.5-flash", "google/gemini-3.5-flash"),
            ("xai", "grok-4.3", "x-ai/grok-4.3"),
            ("moonshot", "kimi-k2.6", "moonshotai/kimi-k2.6"),
            ("minimax", "MiniMax-M3", "minimax/minimax-m3"),
            ("anthropic", "claude-opus-4-8", "anthropic/claude-opus-4.8"),
            ("anthropic", "claude-opus-4-5-20251101", "anthropic/claude-opus-4.5"),
            ("qwen", "qwen3.5-plus-2026-04-20", "qwen/qwen3.5-plus-20260420"),
        ]
        for vid, nid, legacy in cases:
            self.assertIn(legacy, vcr._legacy_ids(vid, nid), f"{vid}/{nid} → {legacy}")

    def test_canonical_excluded(self):
        self.assertNotIn("gemini/gemini-3.5-flash", vcr._legacy_ids("gemini", "gemini-3.5-flash"))

    def test_alias_map_first_wins_and_never_shadows_live_id(self):
        models = {
            "anthropic/claude-opus-4-8": {"id": "anthropic/claude-opus-4-8",
                                          "also_known_as": ["anthropic/claude-opus-4.8"]},
            # a live id that is also some entry's legacy form must not be shadowed
            "openai/gpt-4o": {"id": "openai/gpt-4o", "also_known_as": []},
            "openai/gpt-4o-2024-11-20": {"id": "openai/gpt-4o-2024-11-20",
                                         "also_known_as": ["openai/gpt-4o"]},
        }
        amap = vcr.build_alias_map(models)
        self.assertEqual(amap["anthropic/claude-opus-4.8"], "anthropic/claude-opus-4-8")
        self.assertNotIn("openai/gpt-4o", amap)  # live id never aliased away


if __name__ == "__main__":
    unittest.main(verbosity=2)
