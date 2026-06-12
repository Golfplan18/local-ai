"""Tests for Path B additions to scripts/sync_model_registry.py:
  - AA overlay (build_aa_overlay): canonical-id + fuzzy-Jaccard match
  - Layered AA enrichment (layer_aa_enrichment / merge_sources):
    OpenRouter-embedded benchmarks block primary, name-matched overlay
    supplement, disagreement warning
  - :free suffix inheritance (_apply_free_suffix_inheritance)
"""
import contextlib
import io
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
    layer_aa_enrichment,
    merge_sources,
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


def _or_model(mid, benchmarks=None):
    """Minimal OpenRouter /api/v1/models entry for merge_sources tests."""
    return {
        "id": mid,
        "name": mid,
        "context_length": 8192,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        "benchmarks": benchmarks or {},
    }


def _merged(or_models, aa_overlay):
    """Run merge_sources with empty LiteLLM/Arena, swallowing its log
    lines; returns (registry, captured_stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        registry = merge_sources(or_models, {}, {}, aa_overlay=aa_overlay)
    return registry, buf.getvalue()


class TestLayerAAEnrichment(unittest.TestCase):
    """Unit tests for the layering helper itself."""

    MATCHED = {
        "aa_intelligence_index": 50.0,
        "aa_coding_index": 45.0,
        "aa_agentic_index": 55.0,
        "aa_math_index": 40.0,
        "latency_total_seconds": 5.0,
        "latency_ttft_seconds": 1.0,
        "output_tokens_per_second": 120.0,
        "aa_reasoning_model": True,
        "aa_release_date": "2025-01-01",
        "match_type": "jaccard",
    }
    EMBEDDED = {
        "intelligence_index": 51.0,
        "coding_index": 46.5,
        "agentic_index": 56.0,
    }

    def test_embedded_primary_wins_over_matched(self):
        fields, source, _ = layer_aa_enrichment(self.EMBEDDED, self.MATCHED)
        self.assertEqual(fields["aa_intelligence_index"], 51.0)
        self.assertEqual(fields["aa_coding_index"], 46.5)
        self.assertEqual(fields["aa_agentic_index"], 56.0)
        self.assertEqual(source, "openrouter-embedded")

    def test_matched_fills_supplementary_fields(self):
        # Fields OpenRouter doesn't embed always come from the overlay,
        # even when the embedded block wins the headline indexes.
        fields, _, _ = layer_aa_enrichment(self.EMBEDDED, self.MATCHED)
        self.assertEqual(fields["aa_math_index"], 40.0)
        self.assertEqual(fields["latency_total_seconds"], 5.0)
        self.assertEqual(fields["latency_ttft_seconds"], 1.0)
        self.assertEqual(fields["output_tokens_per_second"], 120.0)
        self.assertEqual(fields["reasoning_model"], True)
        self.assertEqual(fields["release_date"], "2025-01-01")

    def test_embedded_only(self):
        fields, source, disagreement = layer_aa_enrichment(self.EMBEDDED, None)
        self.assertEqual(fields["aa_intelligence_index"], 51.0)
        self.assertIsNone(fields["aa_math_index"])
        self.assertIsNone(fields["latency_total_seconds"])
        self.assertEqual(source, "openrouter-embedded")
        self.assertIsNone(disagreement)

    def test_matched_only(self):
        fields, source, disagreement = layer_aa_enrichment(None, self.MATCHED)
        self.assertEqual(fields["aa_intelligence_index"], 50.0)
        self.assertEqual(source, "aa-matched")
        self.assertIsNone(disagreement)

    def test_neither_source(self):
        fields, source, disagreement = layer_aa_enrichment(None, None)
        self.assertTrue(all(v is None for v in fields.values()))
        self.assertIsNone(source)
        self.assertIsNone(disagreement)

    def test_partial_embedded_does_not_clobber_matched(self):
        # An embedded block carrying only intelligence_index must not
        # null out the overlay's coding / agentic values.
        embedded = {"intelligence_index": 51.0, "coding_index": None}
        fields, source, _ = layer_aa_enrichment(embedded, self.MATCHED)
        self.assertEqual(fields["aa_intelligence_index"], 51.0)
        self.assertEqual(fields["aa_coding_index"], 45.0)
        self.assertEqual(fields["aa_agentic_index"], 55.0)
        self.assertEqual(source, "openrouter-embedded")

    def test_disagreement_above_threshold_flagged_embedded_wins(self):
        # The glm-4.6v case: 23.4 embedded vs 17.1 fuzzy-matched.
        embedded = {"intelligence_index": 23.4}
        matched = dict(self.MATCHED, aa_intelligence_index=17.1)
        fields, source, disagreement = layer_aa_enrichment(embedded, matched)
        self.assertEqual(fields["aa_intelligence_index"], 23.4)
        self.assertEqual(source, "openrouter-embedded")
        self.assertIsNotNone(disagreement)
        self.assertEqual(disagreement["embedded"], 23.4)
        self.assertEqual(disagreement["matched"], 17.1)
        self.assertEqual(disagreement["match_type"], "jaccard")

    def test_small_delta_not_flagged(self):
        embedded = {"intelligence_index": 51.5}
        fields, _, disagreement = layer_aa_enrichment(embedded, self.MATCHED)
        self.assertEqual(fields["aa_intelligence_index"], 51.5)
        self.assertIsNone(disagreement)


class TestMergeSourcesAALayering(unittest.TestCase):
    """End-to-end through merge_sources: embedded block threaded from the
    OpenRouter model entry, overlay supplement, provenance + warning."""

    def test_embedded_wins_and_provenance_recorded(self):
        aa = [_aa_entry("GLM 4.6V", "glm-4-6v", "zai", intelligence_index=17.1)]
        or_models = [_or_model(
            "z-ai/glm-4.6v",
            benchmarks={"artificial_analysis": {
                "intelligence_index": 23.4,
                "coding_index": 19.7,
                "agentic_index": 17.5,
            }},
        )]
        overlay = build_aa_overlay(aa, ["z-ai/glm-4.6v"])
        self.assertIn("z-ai/glm-4.6v", overlay)  # sanity: overlay matched
        registry, out = _merged(or_models, overlay)
        entry = registry["models"]["z-ai/glm-4.6v"]
        self.assertEqual(entry["aa_intelligence_index"], 23.4)
        self.assertEqual(entry["aa_coding_index"], 19.7)
        self.assertEqual(entry["aa_agentic_index"], 17.5)
        self.assertEqual(entry["_provenance"]["aa_source"], "openrouter-embedded")
        self.assertEqual(
            entry["_provenance"]["aa_embedded"]["intelligence_index"], 23.4)
        # Disagreement (23.4 vs 17.1 > 2 points) recorded + warned
        self.assertIn("aa_disagreement", entry["_provenance"])
        self.assertIn("WARNING", out)
        self.assertIn("z-ai/glm-4.6v", out)

    def test_matched_supplements_embedded_in_registry_entry(self):
        aa = [_aa_entry("GPT-4o", "gpt-4o", "openai",
                        intelligence_index=50.0, math_index=44.0,
                        reasoning_model=False, release_date="2024-08-06")]
        or_models = [_or_model(
            "openai/gpt-4o",
            benchmarks={"artificial_analysis": {
                "intelligence_index": 50.5,
                "coding_index": 47.0,
                "agentic_index": 52.0,
            }},
        )]
        overlay = build_aa_overlay(aa, ["openai/gpt-4o"])
        registry, out = _merged(or_models, overlay)
        entry = registry["models"]["openai/gpt-4o"]
        # Headline indexes from the embedded block
        self.assertEqual(entry["aa_intelligence_index"], 50.5)
        # Supplement from the matched overlay
        self.assertEqual(entry["aa_math_index"], 44.0)
        self.assertEqual(entry["latency_total_seconds"], 5.0)
        self.assertEqual(entry["output_tokens_per_second"], 120.0)
        self.assertEqual(entry["reasoning_model"], False)
        self.assertEqual(entry["release_date"], "2024-08-06")
        # 0.5-point delta is within tolerance — no warning
        self.assertNotIn("WARNING", out)
        self.assertNotIn("aa_disagreement", entry["_provenance"])

    def test_matched_only_model_keeps_full_overlay_coverage(self):
        # Models OpenRouter hasn't linked to AA (~40 today) still get the
        # full name-matched enrichment.
        aa = [_aa_entry("Kimi K2.6", "kimi-k2-6", "kimi", intelligence_index=53.9)]
        or_models = [_or_model("moonshotai/kimi-k2.6")]  # no benchmarks
        overlay = build_aa_overlay(aa, ["moonshotai/kimi-k2.6"])
        registry, _ = _merged(or_models, overlay)
        entry = registry["models"]["moonshotai/kimi-k2.6"]
        self.assertEqual(entry["aa_intelligence_index"], 53.9)
        self.assertEqual(entry["aa_math_index"], 40.0)
        self.assertEqual(entry["_provenance"]["aa_source"], "aa-matched")
        self.assertNotIn("aa_embedded", entry["_provenance"])

    def test_no_aa_anywhere(self):
        registry, _ = _merged([_or_model("some-vendor/some-model")], {})
        entry = registry["models"]["some-vendor/some-model"]
        self.assertIsNone(entry["aa_intelligence_index"])
        self.assertIsNone(entry["_provenance"]["aa_source"])


if __name__ == "__main__":
    unittest.main()
