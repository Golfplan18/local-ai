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


if __name__ == "__main__":
    unittest.main(verbosity=2)
