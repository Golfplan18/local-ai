"""Tests for scripts/auto-populate-buckets.py.

Two test classes:
  * Pure-function tests with synthetic catalog fixtures (TestSelector*) —
    fast, deterministic, pin the selection logic.
  * Live-catalog smoke test (TestLiveCatalog) — runs the selector against
    the real config/openrouter-catalog.json and verifies the picks are
    non-empty for every workhorse tier and image_extracts. Marked optional
    so CI without a fresh catalog still passes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import unittest


# Load the selector module by path (it lives in scripts/, not a package)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
_SELECTOR_PATH = os.path.join(_REPO_ROOT, "scripts", "auto-populate-buckets.py")
_PATTERNS_PATH = os.path.join(_REPO_ROOT, "config", "vendor-tier-patterns.json")
_CATALOG_PATH = os.path.join(_REPO_ROOT, "config", "openrouter-catalog.json")

_spec = importlib.util.spec_from_file_location("auto_populate_buckets", _SELECTOR_PATH)
selector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(selector)


# ── Synthetic catalog fixtures ──────────────────────────────────────────────
def _mk(id_, vendor=None, prompt=0.0, completion=0.0, ctx=128_000,
        modality="text", inputs=("text",), accepts_img=False):
    """Build a minimal catalog model record."""
    return {
        "id": id_,
        "vendor": vendor or id_.split("/")[0],
        "modality": modality,
        "input_modalities": list(inputs),
        "accepts_image": accepts_img,
        "context_length": ctx,
        "pricing_per_million": {"prompt": prompt, "completion": completion},
    }


def _patterns():
    with open(_PATTERNS_PATH) as f:
        return json.load(f)


# ── Param-count estimation ──────────────────────────────────────────────────
class TestParamEstimation(unittest.TestCase):

    def test_explicit_70b_in_name(self):
        m = _mk("meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(selector.estimate_param_count_b(m), 70.0)

    def test_moe_total_active(self):
        # 122B total / 10B active — we take the total
        m = _mk("qwen/qwen3.5-122b-a10b")
        self.assertEqual(selector.estimate_param_count_b(m), 122.0)

    def test_anthropic_flagship_synthetic_high(self):
        m = _mk("anthropic/claude-opus-4-7")
        est = selector.estimate_param_count_b(m)
        self.assertIsNotNone(est)
        self.assertGreaterEqual(est, 25.0)

    def test_openai_flagship_synthetic_high(self):
        m = _mk("openai/gpt-5-pro")
        self.assertGreaterEqual(selector.estimate_param_count_b(m), 25.0)

    def test_unknown_model_returns_none(self):
        m = _mk("randomvendor/mystery-model")
        self.assertIsNone(selector.estimate_param_count_b(m))

    def test_small_model_returns_low(self):
        m = _mk("microsoft/phi-3-mini-4b")
        est = selector.estimate_param_count_b(m)
        self.assertIsNotNone(est)
        self.assertLess(est, 25.0)


# ── Floor enforcement ───────────────────────────────────────────────────────
class TestFloorEnforcement(unittest.TestCase):

    def setUp(self):
        self.patterns = _patterns()

    def test_70b_passes_floor(self):
        m = _mk("meta-llama/llama-3.3-70b-instruct")
        self.assertTrue(selector.hits_floor(m, self.patterns))

    def test_7b_fails_floor(self):
        m = _mk("qwen/qwen3-7b")
        self.assertFalse(selector.hits_floor(m, self.patterns))

    def test_mini_suffix_fails_floor(self):
        m = _mk("openai/gpt-4-1-mini")
        self.assertFalse(selector.hits_floor(m, self.patterns))

    def test_nano_suffix_fails_floor(self):
        m = _mk("openai/gpt-4-1-nano")
        self.assertFalse(selector.hits_floor(m, self.patterns))

    def test_unknown_param_count_passes_by_default(self):
        # Unknown vendor + no param marker → include rather than exclude
        m = _mk("randomvendor/mystery-model")
        self.assertTrue(selector.hits_floor(m, self.patterns))

    def test_flagship_passes(self):
        for mid in ("anthropic/claude-opus-4-7",
                    "openai/gpt-5-pro",
                    "google/gemini-3-pro-preview"):
            with self.subTest(mid):
                self.assertTrue(
                    selector.hits_floor(_mk(mid), self.patterns)
                )


# ── Tier matching ───────────────────────────────────────────────────────────
class TestTierMatching(unittest.TestCase):

    def setUp(self):
        self.patterns = _patterns()

    def test_opus_is_premium(self):
        m = _mk("anthropic/claude-opus-4-7")
        self.assertTrue(selector.matches_tier(m, self.patterns, "premium"))
        self.assertFalse(selector.matches_tier(m, self.patterns, "mid"))
        self.assertFalse(selector.matches_tier(m, self.patterns, "fast"))

    def test_sonnet_is_mid(self):
        m = _mk("anthropic/claude-sonnet-4-5")
        self.assertFalse(selector.matches_tier(m, self.patterns, "premium"))
        self.assertTrue(selector.matches_tier(m, self.patterns, "mid"))

    def test_haiku_is_fast(self):
        m = _mk("anthropic/claude-haiku-4")
        self.assertTrue(selector.matches_tier(m, self.patterns, "fast"))
        self.assertFalse(selector.matches_tier(m, self.patterns, "premium"))

    def test_gpt5_full_is_premium(self):
        m = _mk("openai/gpt-5")
        self.assertTrue(selector.matches_tier(m, self.patterns, "premium"))

    def test_gpt5_mini_is_fast(self):
        m = _mk("openai/gpt-5-mini")
        self.assertTrue(selector.matches_tier(m, self.patterns, "fast"))
        # And NOT premium even though the base name contains "gpt-5"
        self.assertFalse(selector.matches_tier(m, self.patterns, "premium"))

    def test_gpt5_codex_mini_is_fast_not_mid(self):
        m = _mk("openai/gpt-5.1-codex-mini")
        self.assertTrue(selector.matches_tier(m, self.patterns, "fast"))
        self.assertFalse(selector.matches_tier(m, self.patterns, "mid"))

    def test_free_tier_is_cost_based(self):
        m_free = _mk("meta-llama/llama-3.3-70b-instruct:free", prompt=0, completion=0)
        m_paid = _mk("meta-llama/llama-3.3-70b-instruct", prompt=0.59, completion=0.79)
        self.assertTrue(selector.matches_tier(m_free, self.patterns, "free"))
        self.assertFalse(selector.matches_tier(m_paid, self.patterns, "free"))


# ── Candidate ordering ──────────────────────────────────────────────────────
class TestCandidateOrdering(unittest.TestCase):

    def setUp(self):
        self.patterns = _patterns()

    def test_free_sorts_before_paid_within_tier(self):
        models = [
            _mk("anthropic/claude-sonnet-4-5", prompt=3.0),
            _mk("openai/gpt-4-1", prompt=0, completion=0),  # synthetic free mid
        ]
        cands = selector.candidates_for_tier(models, self.patterns, "mid")
        self.assertEqual(cands[0]["id"], "openai/gpt-4-1")

    def test_lower_cost_wins_within_tier(self):
        models = [
            _mk("openai/gpt-5", prompt=5.0),
            _mk("anthropic/claude-opus-4-7", prompt=15.0),
        ]
        cands = selector.candidates_for_tier(models, self.patterns, "premium")
        self.assertEqual(cands[0]["id"], "openai/gpt-5")

    def test_context_length_breaks_ties(self):
        models = [
            _mk("openai/gpt-5", prompt=5.0, ctx=200_000),
            _mk("anthropic/claude-opus-4-7", prompt=5.0, ctx=500_000),
        ]
        cands = selector.candidates_for_tier(models, self.patterns, "premium")
        self.assertEqual(cands[0]["id"], "anthropic/claude-opus-4-7")


# ── Image extracts ──────────────────────────────────────────────────────────
class TestImageExtracts(unittest.TestCase):

    def setUp(self):
        self.patterns = _patterns()

    def test_free_vision_wins(self):
        models = [
            _mk("anthropic/claude-opus-4-7", prompt=15.0, accepts_img=True,
                inputs=("text", "image")),
            _mk("xai/grok-4-vision", prompt=0, completion=0, accepts_img=True,
                inputs=("text", "image")),
        ]
        pick = selector.pick_image_extracts(models, self.patterns)
        self.assertEqual(pick["id"], "xai/grok-4-vision")
        self.assertFalse(pick["is_paid"])

    def test_paid_fallback_when_no_free_vision(self):
        models = [
            _mk("anthropic/claude-opus-4-7", prompt=15.0, accepts_img=True,
                inputs=("text", "image")),
            _mk("google/gemini-3-pro-preview", prompt=2.5, accepts_img=True,
                inputs=("text", "image")),
            _mk("openai/gpt-5", prompt=5.0, accepts_img=True,
                inputs=("text", "image")),
        ]
        pick = selector.pick_image_extracts(models, self.patterns)
        # Cheapest paid wins
        self.assertEqual(pick["id"], "google/gemini-3-pro-preview")
        self.assertTrue(pick["is_paid"])
        self.assertIn("No free vision-capable", pick["note"])

    def test_skips_image_output_models(self):
        # Recraft is image-output (modality=image), shouldn't be selected
        # as a vision-input extractor even though accepts_image=True
        models = [
            _mk("recraft/recraft-v4.1-pro", prompt=0, completion=0,
                accepts_img=True, modality="image"),
            _mk("anthropic/claude-opus-4-7", prompt=15.0, accepts_img=True,
                inputs=("text", "image")),
        ]
        pick = selector.pick_image_extracts(models, self.patterns)
        # Should pick the chat model, not the image-gen model
        self.assertEqual(pick["id"], "anthropic/claude-opus-4-7")

    def test_floor_enforced_on_vision(self):
        models = [
            _mk("vendor/tiny-vision-7b", prompt=0, completion=0,
                accepts_img=True, inputs=("text", "image")),
            _mk("anthropic/claude-opus-4-7", prompt=15.0, accepts_img=True,
                inputs=("text", "image")),
        ]
        pick = selector.pick_image_extracts(models, self.patterns)
        # Tiny model below floor; opus selected
        self.assertEqual(pick["id"], "anthropic/claude-opus-4-7")

    def test_warning_when_no_vision_available(self):
        models = [_mk("anthropic/claude-opus-4-7", prompt=15.0)]  # no vision
        pick = selector.pick_image_extracts(models, self.patterns)
        self.assertIsNone(pick["id"])
        self.assertIn("WARNING", pick["note"])


# ── Cross-bucket diversity ──────────────────────────────────────────────────
class TestCrossBucketDiversity(unittest.TestCase):

    def setUp(self):
        self.patterns = _patterns()

    def test_no_duplicate_picks_across_buckets(self):
        # A model that could pattern-match multiple tiers ends up in only one
        models = [
            _mk("anthropic/claude-opus-4-7", prompt=15.0),
            _mk("anthropic/claude-sonnet-4-5", prompt=3.0),
            _mk("anthropic/claude-haiku-4", prompt=0.25),
            _mk("meta-llama/llama-3.3-70b:free", prompt=0, completion=0),
        ]
        result = selector.populate_all(
            {"models": models}, self.patterns, n_per_bucket=1
        )
        all_picks = []
        for tier in selector.WORKHORSE_TIERS:
            all_picks.extend(result["buckets"][tier])
        self.assertEqual(len(all_picks), len(set(all_picks)))


# ── Live catalog smoke test ─────────────────────────────────────────────────
class TestLiveCatalog(unittest.TestCase):
    """Runs against config/openrouter-catalog.json. Sanity-checks that the
    selector produces non-empty picks for every workhorse tier and a
    vision-capable image_extracts pick. Skips when catalog missing."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(_CATALOG_PATH):
            raise unittest.SkipTest("openrouter-catalog.json not present")
        with open(_CATALOG_PATH) as f:
            cls.catalog = json.load(f)
        with open(_PATTERNS_PATH) as f:
            cls.patterns = json.load(f)

    def test_every_workhorse_tier_has_at_least_one_pick(self):
        result = selector.populate_all(self.catalog, self.patterns)
        for tier in selector.WORKHORSE_TIERS:
            with self.subTest(tier=tier):
                self.assertTrue(
                    result["buckets"][tier],
                    f"Tier '{tier}' has no picks against live catalog "
                    f"(check vendor-tier-patterns.json)"
                )

    def test_image_extracts_picks_something(self):
        result = selector.populate_all(self.catalog, self.patterns)
        self.assertIsNotNone(
            result["image_extracts"]["id"],
            "No image_extracts pick — vision-capable text models exist in "
            "the catalog; selector logic is at fault"
        )


if __name__ == "__main__":
    unittest.main()
