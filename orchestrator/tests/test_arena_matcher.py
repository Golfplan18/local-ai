"""Tests for the Arena → OpenRouter name-matching algorithm in
``scripts/sync_model_registry.py``.

Pins the Chunk L (2026-05-20) algorithm fixes — pre-fix coverage was
19%; the new tokenizer + OR→Arena direction walking lifted it to 50%.
These tests cover the specific failure cases that informed the fix.
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
    tokenize_model_name,
    jaccard,
    build_arena_overlay,
)


class TestTokenizer(unittest.TestCase):
    """Tokenization preserves semantic tokens while stripping noise
    that previously bloated the Jaccard denominator."""

    def test_strips_parenthesized_suffix(self):
        # Bare numeric tokens like "4" are dropped on both sides
        # (digit-only = noise size/version). Versioned forms like
        # "4.5" are kept (the dot makes it semantic).
        toks = tokenize_model_name("Claude Opus 4 (20250514)")
        self.assertEqual(toks, {"claude", "opus"})

    def test_strips_thinking_size_parenthetical(self):
        toks = tokenize_model_name("Claude Opus 4 (thinking-16k)")
        self.assertIn("claude", toks); self.assertIn("opus", toks)
        # Parenthetical content stripped → '16k', 'thinking' both gone
        self.assertNotIn("16k", toks)

    def test_strips_date_suffix_hyphen(self):
        # "Grok-4-0709" → grok (4 and 0709 both dropped as digit-only)
        toks = tokenize_model_name("Grok-4-0709")
        self.assertEqual(toks, {"grok"})

    def test_preserves_dotted_version(self):
        # "claude-opus-4.5" → 4.5 has a dot → kept as semantic version
        toks = tokenize_model_name("claude-opus-4.5")
        self.assertEqual(toks, {"claude", "opus", "4.5"})

    def test_strips_yyyy_mm_dd(self):
        toks = tokenize_model_name("GPT-4o-2024-08-06")
        self.assertEqual(toks, {"gpt", "4o"})

    def test_strips_year_only(self):
        # Year tokens like "2025" should not survive as a standalone
        toks = tokenize_model_name("ChatGPT-4o-latest 2025")
        # chatgpt → gpt; latest dropped; 2025 dropped
        self.assertEqual(toks, {"gpt", "4o"})

    def test_chatgpt_normalized_to_gpt(self):
        a = tokenize_model_name("ChatGPT-4o-latest (2025-03-26)")
        b = tokenize_model_name("gpt-4o")
        self.assertEqual(a, b)

    def test_splits_compound_version_token(self):
        # "qwen2.5" must split into "qwen" + "2.5" so it can match
        # the hyphenated OpenRouter form
        toks = tokenize_model_name("Qwen2.5-72B-Instruct")
        self.assertIn("qwen", toks)
        self.assertIn("2.5", toks)
        self.assertIn("72b", toks)

    def test_splits_compound_with_letter_suffix(self):
        toks = tokenize_model_name("Qwen3-235B-A22B")
        self.assertEqual(toks, {"qwen", "3", "235b", "a22b"})

    def test_drops_pure_digit_tokens(self):
        # Bare "8", "16" digits are noise (size labels) after splitting
        toks = tokenize_model_name("Llama-3.3-70B-Instruct")
        self.assertEqual(toks, {"llama", "3.3", "70b"})

    def test_empty_returns_empty_set(self):
        self.assertEqual(tokenize_model_name(""), set())
        self.assertEqual(tokenize_model_name(None), set())


class TestJaccardMatching(unittest.TestCase):
    """The painful real-world cases from the coverage audit. Each pair
    must score >= 0.5 (the match threshold) or below 0.5 if they should
    not match."""

    POSITIVE = [
        ("ChatGPT-4o-latest (2025-03-26)", "gpt-4o"),
        ("GPT-4o-2024-08-06", "gpt-4o-2024-08-06"),
        ("GPT-4o-mini-2024-07-18", "gpt-4o-mini"),
        ("Claude Opus 4 (20250514)", "claude-opus-4"),
        ("Claude Opus 4 (thinking-16k)", "claude-opus-4"),
        ("Grok-4-0709", "grok-4"),
        ("Qwen3-235B-A22B", "qwen3-235b-a22b-2507"),
        ("Qwen3-235B-A22B", "qwen3-235b-a22b"),
        ("Qwen2.5-72B-Instruct", "qwen-2.5-72b-instruct"),
        ("Qwen2.5-Coder-32B-Instruct", "qwen-2.5-coder-32b-instruct"),
        ("DeepSeek-R1-0528", "deepseek-r1"),
        ("Llama-3.3-70B-Instruct", "llama-3.3-70b-instruct"),
    ]

    NEGATIVE = [
        ("ChatGPT-4o-latest (2025-03-26)", "gpt-3.5-turbo"),
        ("Claude Opus 4 (20250514)", "claude-3-haiku"),
        ("DeepSeek-R1-0528", "deepseek-v3"),  # different model line
        ("Qwen3-235B-A22B", "qwen-2.5-72b-instruct"),  # different version
    ]

    def test_positive_matches_clear_threshold(self):
        for arena, or_id in self.POSITIVE:
            with self.subTest(arena=arena, or_id=or_id):
                a = tokenize_model_name(arena)
                b = tokenize_model_name(or_id)
                score = jaccard(a, b)
                self.assertGreaterEqual(
                    score, 0.5,
                    f"{arena!r} ↔ {or_id!r}: {score:.2f}\n"
                    f"  arena tokens: {sorted(a)}\n"
                    f"  OR tokens:    {sorted(b)}",
                )

    def test_negative_matches_below_threshold(self):
        for arena, or_id in self.NEGATIVE:
            with self.subTest(arena=arena, or_id=or_id):
                a = tokenize_model_name(arena)
                b = tokenize_model_name(or_id)
                score = jaccard(a, b)
                self.assertLess(
                    score, 0.5,
                    f"{arena!r} ↔ {or_id!r}: {score:.2f}\n"
                    f"  arena tokens: {sorted(a)}\n"
                    f"  OR tokens:    {sorted(b)}",
                )


class TestOverlayMultipleVariants(unittest.TestCase):
    """The OR→Arena direction walk means multiple OpenRouter variants
    of the same family each independently get scored. The prior
    Arena→OR direction collapsed all four GPT-4o variants onto one ID."""

    def test_multiple_gpt4o_variants_each_get_scored(self):
        or_ids = [
            "openai/gpt-4o",
            "openai/gpt-4o-2024-05-13",
            "openai/gpt-4o-2024-08-06",
            "openai/gpt-4o-mini",
        ]
        arena_rows = [
            {"Model": "ChatGPT-4o-latest (2025-03-26)", "Organization": "OpenAI",
             "Arena Score": "1429", "Rank* (UB)": "4", "Votes": "26230"},
            {"Model": "GPT-4o-2024-05-13", "Organization": "OpenAI",
             "Arena Score": "1280", "Rank* (UB)": "70", "Votes": "8000"},
            {"Model": "GPT-4o-2024-08-06", "Organization": "OpenAI",
             "Arena Score": "1265", "Rank* (UB)": "85", "Votes": "5500"},
            {"Model": "GPT-4o-mini-2024-07-18", "Organization": "OpenAI",
             "Arena Score": "1287", "Rank* (UB)": "61", "Votes": "8500"},
        ]
        overlay = build_arena_overlay(arena_rows, or_ids)
        # Every variant should get a score — the collision bug used to
        # leave 3 of 4 null.
        self.assertEqual(len(overlay), 4)
        for oid in or_ids:
            self.assertIn(oid, overlay,
                          f"{oid} missing from overlay — collision regressed")
            self.assertIsNotNone(overlay[oid]["intelligence_score"])

    def test_unmatched_vendor_no_arena_entry(self):
        # OR id whose vendor has no Arena entry → not in overlay (null).
        or_ids = ["sao10k/some-fine-tune"]
        arena_rows = [
            {"Model": "Some-Other-Model", "Organization": "Unrelated",
             "Arena Score": "1000", "Rank* (UB)": "1", "Votes": "100"},
        ]
        overlay = build_arena_overlay(arena_rows, or_ids)
        self.assertNotIn("sao10k/some-fine-tune", overlay)


if __name__ == "__main__":
    unittest.main()
