"""Tests for Path B additions to scripts/sync_model_registry.py:
  - AA overlay (build_aa_overlay): canonical-id + fuzzy-Jaccard match
  - :free suffix inheritance (_apply_free_suffix_inheritance)
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(WORKTREE_ROOT, "scripts")
for p in (HERE, WORKTREE_ROOT, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from sync_model_registry import (  # noqa: E402
    build_aa_overlay,
    _aa_canonical_or_id,
    _apply_free_suffix_inheritance,
    _project_aa_view,
    _AA_CREATOR_SLUG_REMAP,
)


def _aa_entry(name, slug, creator_slug, **extras):
    """Build a fake AA model entry matching the shape of the real
    /models page's defaultData array."""
    base = {
        "name": name,
        "slug": slug,
        "deleted": False,
        "model_creators": {"slug": creator_slug, "name": creator_slug.title()},
        "intelligence_index": 50.0,
        "coding_index": 45.0,
        "agentic_index": 55.0,
        "math_index": 40.0,
        "input_modality_image": True,
        "reasoning_model": False,
        "release_date": "2025-01-01",
        "end_to_end_response_time_metrics": {"total_time": 5.0},
        "time_to_first_answer_token_metrics": {"total_time": 1.0},
        "timescaleData": {"median_output_speed": 120.0},
    }
    base.update(extras)
    return base


class TestAACanonicalIdSynthesis(unittest.TestCase):

    def test_openai_creator_maps_directly(self):
        m = _aa_entry("GPT-4o (Aug '24)", "gpt-4o-2024-08-06", "openai")
        self.assertEqual(_aa_canonical_or_id(m), "openai/gpt-4o-2024-08-06")

    def test_anthropic_maps_directly(self):
        m = _aa_entry("Claude Opus 4", "claude-opus-4", "anthropic")
        self.assertEqual(_aa_canonical_or_id(m), "anthropic/claude-opus-4")

    def test_meta_remapped_to_meta_llama(self):
        # AA uses "meta"; OpenRouter uses "meta-llama"
        m = _aa_entry("Llama 3.3 70B", "llama-3.3-70b-instruct", "meta")
        self.assertEqual(_aa_canonical_or_id(m), "meta-llama/llama-3.3-70b-instruct")

    def test_alibaba_remapped_to_qwen(self):
        m = _aa_entry("Qwen3-235B", "qwen3-235b-a22b", "alibaba")
        self.assertEqual(_aa_canonical_or_id(m), "qwen/qwen3-235b-a22b")

    def test_renamed_creators_remap_to_or_vendors(self):
        # 2026-06-12 audit: AA's creator slugs drifted from OpenRouter's
        # vendor prefixes for a dozen vendors (Mistral, xAI/Grok,
        # Z-AI/GLM, AWS/Nova, ...). Each left its whole line-up with
        # aa_intelligence_index=None.
        cases = {
            "mistral": ("mistral-medium-3-5", "mistralai/mistral-medium-3-5"),
            "xai": ("grok-4-3", "x-ai/grok-4-3"),
            "zai": ("glm-4-6v", "z-ai/glm-4-6v"),
            "aws": ("nova-premier", "amazon/nova-premier"),
            "nous-research": ("hermes-4-405b", "nousresearch/hermes-4-405b"),
        }
        for creator, (slug, expected) in cases.items():
            m = _aa_entry(slug, slug, creator)
            self.assertEqual(_aa_canonical_or_id(m), expected,
                             f"creator {creator!r}")

    def test_kimi_remapped_to_moonshotai(self):
        # AA rebranded Moonshot AI's creator entry to "Kimi"; OpenRouter
        # keeps the moonshotai vendor prefix. Without the remap every
        # Kimi model shipped aa_intelligence_index=None (2026-06-12).
        m = _aa_entry("Kimi K2.6", "kimi-k2-6", "kimi")
        self.assertEqual(_aa_canonical_or_id(m), "moonshotai/kimi-k2-6")

    def test_kimi_dotted_or_id_matches_via_normalized_pass(self):
        # The real OpenRouter id is dotted (kimi-k2.6); AA's slug is
        # hyphenated (kimi-k2-6). End-to-end overlay must connect them
        # through the canonical-normalized pass.
        rows = [_aa_entry("Kimi K2.6", "kimi-k2-6", "kimi",
                          intelligence_index=53.9)]
        overlay = build_aa_overlay(rows, ["moonshotai/kimi-k2.6"])
        self.assertIn("moonshotai/kimi-k2.6", overlay)
        view = overlay["moonshotai/kimi-k2.6"]
        self.assertEqual(view["match_type"], "canonical-normalized")
        self.assertEqual(view["aa_intelligence_index"], 53.9)

    def test_missing_creator_returns_none(self):
        m = {"name": "X", "slug": "x"}
        self.assertIsNone(_aa_canonical_or_id(m))

    def test_remap_table_covers_known_cases(self):
        # Pin: the table must remap meta + alibaba.
        self.assertEqual(_AA_CREATOR_SLUG_REMAP.get("meta"), "meta-llama")
        self.assertEqual(_AA_CREATOR_SLUG_REMAP.get("alibaba"), "qwen")


class TestAAOverlayDirectMatching(unittest.TestCase):

    def test_direct_canonical_match_hits_first(self):
        aa = [_aa_entry("GPT-4o", "gpt-4o-2024-08-06", "openai",
                         intelligence_index=68.0)]
        or_ids = ["openai/gpt-4o-2024-08-06"]
        overlay = build_aa_overlay(aa, or_ids)
        self.assertIn("openai/gpt-4o-2024-08-06", overlay)
        self.assertEqual(overlay["openai/gpt-4o-2024-08-06"]["match_type"], "canonical")
        self.assertEqual(overlay["openai/gpt-4o-2024-08-06"]["aa_intelligence_index"], 68.0)

    def test_deleted_aa_entries_excluded(self):
        aa = [_aa_entry("X", "deleted-model", "openai", deleted=True)]
        or_ids = ["openai/deleted-model"]
        overlay = build_aa_overlay(aa, or_ids)
        self.assertNotIn("openai/deleted-model", overlay)


class TestAAOverlayFuzzyFallback(unittest.TestCase):

    def test_fuzzy_match_when_canonical_id_differs(self):
        # OR id "openai/gpt-4o" (no date suffix) doesn't match canonical
        # AA "openai/gpt-4o-2024-08-06" exactly; fuzzy Jaccard should hit
        aa = [_aa_entry("GPT-4o", "gpt-4o-2024-08-06", "openai",
                         intelligence_index=68.0)]
        or_ids = ["openai/gpt-4o"]
        overlay = build_aa_overlay(aa, or_ids)
        self.assertIn("openai/gpt-4o", overlay)
        self.assertEqual(overlay["openai/gpt-4o"]["match_type"], "jaccard")

    def test_no_vendor_match_skipped(self):
        aa = [_aa_entry("X", "x", "openai")]
        or_ids = ["unrelated-vendor/some-model"]
        overlay = build_aa_overlay(aa, or_ids)
        self.assertEqual(overlay, {})


class TestAAViewProjection(unittest.TestCase):

    def test_latency_and_tps_extracted(self):
        m = _aa_entry(
            "GPT-4o", "gpt-4o-2024-08-06", "openai",
            end_to_end_response_time_metrics={"total_time": 5.5},
            time_to_first_answer_token_metrics={"total_time": 1.2},
            timescaleData={"median_output_speed": 145.0},
        )
        view = _project_aa_view(m)
        self.assertEqual(view["latency_total_seconds"], 5.5)
        self.assertEqual(view["latency_ttft_seconds"], 1.2)
        self.assertEqual(view["output_tokens_per_second"], 145.0)

    def test_missing_latency_blocks_handled(self):
        m = _aa_entry("X", "x", "openai",
                       end_to_end_response_time_metrics=None,
                       time_to_first_answer_token_metrics=None,
                       timescaleData=None)
        view = _project_aa_view(m)
        self.assertIsNone(view["latency_total_seconds"])
        self.assertIsNone(view["latency_ttft_seconds"])
        self.assertIsNone(view["output_tokens_per_second"])


class TestFreeSuffixInheritance(unittest.TestCase):

    def test_free_inherits_intelligence_from_paid_base(self):
        models = {
            "meta-llama/llama-3.3-70b-instruct": {
                "id": "meta-llama/llama-3.3-70b-instruct",
                "vision_capable": False,
                "intelligence_score": 1300.0,
                "aa_intelligence_index": 45.0,
                "latency_ttft_seconds": 0.5,
                "output_tokens_per_second": 200.0,
            },
            "meta-llama/llama-3.3-70b-instruct:free": {
                "id": "meta-llama/llama-3.3-70b-instruct:free",
                "vision_capable": False,
                "intelligence_score": None,
                "aa_intelligence_index": None,
                "latency_ttft_seconds": None,
                "output_tokens_per_second": None,
            },
        }
        count = _apply_free_suffix_inheritance(models)
        free = models["meta-llama/llama-3.3-70b-instruct:free"]
        self.assertEqual(free["intelligence_score"], 1300.0)
        self.assertEqual(free["aa_intelligence_index"], 45.0)
        self.assertEqual(free["latency_ttft_seconds"], 0.5)
        self.assertEqual(free["output_tokens_per_second"], 200.0)
        self.assertEqual(free["_inherited_from_base"], "meta-llama/llama-3.3-70b-instruct")
        self.assertGreater(count, 0)

    def test_inheritance_does_not_overwrite_existing(self):
        # When the :free already has a value, the base shouldn't overwrite it.
        models = {
            "x/foo": {"intelligence_score": 100.0},
            "x/foo:free": {"intelligence_score": 200.0},
        }
        _apply_free_suffix_inheritance(models)
        # :free's existing value should be preserved
        self.assertEqual(models["x/foo:free"]["intelligence_score"], 200.0)

    def test_no_base_no_inheritance(self):
        models = {
            "x/orphan:free": {"intelligence_score": None},
        }
        count = _apply_free_suffix_inheritance(models)
        self.assertEqual(count, 0)
        self.assertNotIn("_inherited_from_base", models["x/orphan:free"])

    def test_pricing_not_inherited(self):
        # :free pricing is by definition different from base — the
        # whole point of the tier. Make sure pricing isn't inherited.
        models = {
            "x/foo": {"pricing": {"input_per_token": 1e-6, "output_per_token": 5e-6}},
            "x/foo:free": {"pricing": {"input_per_token": 0, "output_per_token": 0}},
        }
        _apply_free_suffix_inheritance(models)
        # :free pricing unchanged
        self.assertEqual(models["x/foo:free"]["pricing"]["input_per_token"], 0)

    def test_inheritance_marks_provenance(self):
        models = {
            "x/foo": {"vision_capable": True},
            "x/foo:free": {"vision_capable": None},
        }
        _apply_free_suffix_inheritance(models)
        self.assertEqual(models["x/foo:free"]["_inherited_from_base"], "x/foo")


if __name__ == "__main__":
    unittest.main()
