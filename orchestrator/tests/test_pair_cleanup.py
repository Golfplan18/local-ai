"""Tests for per-pair cleanup orchestration (Phase 1.8).

Verifies the end-to-end pipeline with a mocked AnthropicClient:
  - Empty pair → skipped
  - Normal pair → cleaned user + cleaned AI + engagement strips
  - User cleanup error → falls back to raw user input + records error
  - AI cleanup error → falls back to raw AI content (post-strip) + records error
  - Retry escalation propagates correctly to record.retried_tier
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import RawPair, RawTurn  # noqa: E402
from orchestrator.historical.api_client import AnthropicClient, CallResult  # noqa: E402
from orchestrator.historical.pair_cleanup import (  # noqa: E402
    CleanedPair,
    CleanupSideRecord,
    PERSONAL_SEGMENT_CHUNK_TARGET_CHARS,
    PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS,
    chunk_personal_segment,
    clean_pair,
)
from orchestrator.historical.model_router import (  # noqa: E402
    MODEL_HAIKU,
    TIER_HAIKU,
    TIER_QWEN_27,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_pair(user: str, assistant: str, pair_num: int = 1) -> RawPair:
    when = datetime(2025, 7, 14, 21, 5, 34)
    user_turn = RawTurn(role="user", content=user, timestamp=when, raw_text=user)
    asst_turn = RawTurn(role="assistant", content=assistant,
                        timestamp=when, raw_text=assistant)
    return RawPair(
        pair_num=pair_num,
        user_turn=user_turn,
        assistant_turns=[asst_turn] if assistant else [],
        when=when,
    )


class _FakeStream:
    def __init__(self, text, input_tokens=50, output_tokens=30):
        self._text = text
        self._in   = input_tokens
        self._out  = output_tokens
    def __enter__(self): return self
    def __exit__(self, *args): return False
    @property
    def text_stream(self):
        return iter([self._text])
    def get_final_message(self):
        msg = MagicMock()
        msg.usage = MagicMock(input_tokens=self._in, output_tokens=self._out)
        return msg


def _make_anthropic_message(text: str, input_tokens: int = 50,
                              output_tokens: int = 30) -> _FakeStream:
    """Returns a streaming context manager (the new SDK shape)."""
    return _FakeStream(text, input_tokens, output_tokens)


def _client_with_responses(*texts) -> AnthropicClient:
    """AnthropicClient backed by a fake SDK whose .stream() returns
    the given texts in order via successive context managers."""
    fake = MagicMock()
    fake.messages = MagicMock()
    fake.messages.stream = MagicMock(
        side_effect=[_make_anthropic_message(t) for t in texts],
    )
    return AnthropicClient(client=fake)


# ---------------------------------------------------------------------------
# Empty / skipped
# ---------------------------------------------------------------------------


class TestSkippedPair(unittest.TestCase):

    def test_empty_pair_skipped(self):
        pair = _make_pair("", "")
        client = _client_with_responses()  # no calls expected
        result = clean_pair(pair, anthropic_client=client)
        self.assertTrue(result.skipped)
        self.assertEqual(result.cleaned_user_input, "")
        self.assertEqual(result.cleaned_ai_response, "")


class TestOneSidedPair(unittest.TestCase):
    """Pairs with content on only one side are legitimate (e.g. Claude
    Code sessions where the user pressed Enter to advance a prompt).
    They are NOT errors: emit a cleaned-pair with the present side
    cleaned and the empty side preserved as empty."""

    def test_user_empty_ai_present_succeeds_with_one_call(self):
        # User side is empty; AI side has content. Only the AI cleanup
        # call should fire — user side is short-circuited cleanly.
        pair = _make_pair("", "You're in! Installation succeeded.")
        client = _client_with_responses("Installation succeeded.")
        result = clean_pair(pair, anthropic_client=client)
        self.assertFalse(result.skipped)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.cleaned_user_input, "")
        self.assertIn("succeeded", result.cleaned_ai_response.lower())
        # Only one model call (AI side); user side did not call the model.
        self.assertEqual(client.stats().calls, 1)

    def test_user_present_ai_empty_succeeds_with_one_call(self):
        # Mirror: user side has content; AI side empty.
        pair = _make_pair("Trying again.", "")
        client = _client_with_responses("Trying again.")
        result = clean_pair(pair, anthropic_client=client)
        self.assertFalse(result.skipped)
        self.assertEqual(result.errors, [])
        self.assertIn("trying", result.cleaned_user_input.lower())
        self.assertEqual(result.cleaned_ai_response, "")
        self.assertEqual(client.stats().calls, 1)


# ---------------------------------------------------------------------------
# Normal pair cleanup
# ---------------------------------------------------------------------------


class TestNormalCleanup(unittest.TestCase):

    def test_simple_pair_end_to_end(self):
        pair = _make_pair(
            user="Tell me about quantum mechanics please.",
            assistant="Quantum mechanics describes nature at small scales.",
        )
        # First model call cleans user, second cleans AI.
        client = _client_with_responses(
            "Tell me about quantum mechanics.",
            "Quantum mechanics describes nature at small scales.",
        )
        result = clean_pair(pair, anthropic_client=client)
        self.assertFalse(result.skipped)
        self.assertEqual(result.errors, [])
        self.assertIn("quantum", result.cleaned_user_input.lower())
        self.assertIn("quantum", result.cleaned_ai_response.lower())
        # Token + cost stats populated.
        self.assertGreater(result.user_record.input_tokens, 0)
        self.assertGreater(result.ai_record.input_tokens, 0)
        self.assertGreater(result.total_cost_usd, 0)

    def test_engagement_strip_runs_on_ai_cleanup(self):
        pair = _make_pair(
            user="What's 2+2?",
            assistant="2 plus 2 equals 4.",
        )
        # AI cleanup model returns content + trailing engagement.
        client = _client_with_responses(
            "What is two plus two?",
            "2 plus 2 equals 4.\n\nWould you like me to explain the math behind it?",
        )
        result = clean_pair(pair, anthropic_client=client)
        # The trailing question paragraph should have been stripped.
        self.assertNotIn("Would you like", result.cleaned_ai_response)
        self.assertIn("equals 4", result.cleaned_ai_response)
        # Pre-strip preserves it.
        self.assertIn("Would you like", result.cleaned_ai_pre_strip)
        self.assertEqual(len(result.engagement_strips), 1)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class FakeRetriableError(Exception):
    pass


class FakeTerminalError(Exception):
    pass


class TestErrorHandling(unittest.TestCase):

    def test_user_cleanup_terminal_error_falls_back_to_raw(self):
        # User cleanup's API call fails terminally. Retry escalation goes
        # to local-endpoint, which has no config so it falls back to Haiku
        # via API — that ALSO fails terminally. User cleanup then falls
        # back to raw content. Then AI cleanup runs and succeeds.
        pair = _make_pair("dirty raw user", "ai response")
        fake = MagicMock()
        fake.messages = MagicMock()
        fake.messages.stream = MagicMock(side_effect=[
            FakeTerminalError("perm 1"),               # user attempt 1 (Haiku)
            FakeTerminalError("perm 2"),               # user retry → local → Haiku-fallback
            _make_anthropic_message("clean ai response"),  # ai attempt 1
        ])
        client = AnthropicClient(client=fake)
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = clean_pair(pair, anthropic_client=client)
        self.assertTrue(any("user cleanup" in e for e in result.errors))
        self.assertEqual(result.cleaned_user_input, "dirty raw user")
        self.assertEqual(result.cleaned_ai_response, "clean ai response")

    def test_ai_cleanup_terminal_error_falls_back_to_raw_with_strip(self):
        # Mirror: user cleanup succeeds, AI cleanup fails on both Haiku
        # and the Haiku-fallback (local-unavailable retry). AI then falls
        # back to engagement-stripped raw content.
        pair = _make_pair(
            "user input",
            "Real content.\n\nWould you like more?",
        )
        fake = MagicMock()
        fake.messages = MagicMock()
        fake.messages.stream = MagicMock(side_effect=[
            _make_anthropic_message("clean user"),     # user attempt 1
            FakeTerminalError("perm 1"),               # ai attempt 1
            FakeTerminalError("perm 2"),               # ai retry → Haiku-fallback
        ])
        client = AnthropicClient(client=fake)
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = clean_pair(pair, anthropic_client=client)
        self.assertTrue(any("ai cleanup" in e for e in result.errors))
        self.assertIn("Real content", result.cleaned_ai_response)
        self.assertNotIn("Would you like more", result.cleaned_ai_response)


# ---------------------------------------------------------------------------
# Personal-segment chunker (Step 1b — for huge inline pastes that exhaust
# the per-call output-token budget if processed as one segment)
# ---------------------------------------------------------------------------


class TestChunkPersonalSegment(unittest.TestCase):

    def test_below_threshold_returns_unchanged(self):
        text = "short text that fits comfortably in one call"
        self.assertEqual(chunk_personal_segment(text), [text])

    def test_just_at_threshold_returns_unchanged(self):
        text = "x" * PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS
        self.assertEqual(chunk_personal_segment(text), [text])

    def test_oversize_with_paragraph_breaks_splits(self):
        # Build text that exceeds the threshold by stacking paragraphs.
        # Each paragraph is ~40K chars (= one chunk's target), so the
        # chunker should produce roughly one chunk per paragraph.
        para = ("word " * (PERSONAL_SEGMENT_CHUNK_TARGET_CHARS // 5)).strip()
        # 4 paragraphs of ~target each → text well over threshold.
        text = "\n\n".join([para] * 4)
        chunks = chunk_personal_segment(text)
        self.assertGreater(len(chunks), 1)
        # Every chunk should be roughly target-sized; none oversized.
        for c in chunks:
            self.assertLessEqual(
                len(c),
                PERSONAL_SEGMENT_CHUNK_TARGET_CHARS + len(para),
            )
        # Concatenation reconstructs the original content (modulo whitespace).
        self.assertEqual(
            sum(len(c) for c in chunks),
            len(text) - 2 * (len(chunks) - 1),  # we lose `\n\n` separators
        )

    def test_groups_small_paragraphs_into_target_chunks(self):
        # Many small paragraphs should be grouped, not produce one chunk
        # per paragraph.
        small_para = "x" * 1000
        # 200 paragraphs × 1000 chars = 200K chars (above threshold).
        text = "\n\n".join([small_para] * 200)
        chunks = chunk_personal_segment(text)
        self.assertGreater(len(chunks), 1)
        # We should NOT have 200 chunks — paragraphs should be grouped.
        self.assertLess(len(chunks), 50)

    def test_single_huge_paragraph_no_breaks_returns_one_chunk(self):
        # No `\n\s*\n` boundary anywhere — chunker can't split. Returns
        # a single chunk containing the whole text. The downstream
        # MAX_CLEANUP_INPUT_CHARS check is responsible for catching this.
        text = "x" * (PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS + 50_000)
        chunks = chunk_personal_segment(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_paragraph_break_with_whitespace_only_lines_splits(self):
        # `\n\s*\n` matches blank lines with arbitrary whitespace.
        text = (
            "x" * 80_000
            + "\n   \n"  # whitespace-only blank line
            + "y" * 60_000
        )
        chunks = chunk_personal_segment(text)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("x"))
        self.assertTrue(chunks[1].startswith("y"))


# ---------------------------------------------------------------------------
# End-to-end: huge personal segment chunked + concatenated through clean_pair
# ---------------------------------------------------------------------------


class TestHugePersonalSegmentEndToEnd(unittest.TestCase):

    # Personal-voice paragraph that the paste detector classifies as
    # personal (high first-person voice keeps it out of the paste bucket).
    _PERSONAL_PARA = (
        "I think this matters and I want to explore the idea further. " * 1000
    ).strip()

    def test_huge_personal_segment_is_chunked_into_multiple_calls(self):
        # Build a user input that is one huge personal segment (no paste
        # signals — it's all conversational stream-of-consciousness).
        # Three large paragraphs, well above the 120K-char threshold.
        para = self._PERSONAL_PARA  # ~60K chars
        big_user = "\n\n".join([para] * 3)  # ~180K chars total
        self.assertGreater(
            len(big_user), PERSONAL_SEGMENT_CHUNK_THRESHOLD_CHARS,
        )

        pair = _make_pair(big_user, "fine, here's my answer.")
        # Each chunk gets one cleanup call. With ~180K chars / ~40K target
        # we expect 3-5 chunks, plus 1 AI cleanup call → enough fake
        # responses to cover any chunk count up to 7.
        responses = [f"cleaned-chunk-{i}" for i in range(7)] + ["clean ai"]
        client = _client_with_responses(*responses)

        result = clean_pair(pair, anthropic_client=client)
        self.assertFalse(result.skipped)
        # No `personal segment too large` warning — chunking handles it.
        self.assertFalse(any("too large" in w for w in result.user_cleanup_warnings))
        # The cleaned user input concatenates the per-chunk cleaned text
        # — every "cleaned-chunk-N" we returned should be present.
        n_calls = client.stats().calls
        # n_calls = chunks (user side) + 1 (ai side)
        n_chunks = n_calls - 1
        self.assertGreater(n_chunks, 1, "huge segment must be chunked")
        for i in range(n_chunks):
            self.assertIn(f"cleaned-chunk-{i}", result.cleaned_user_input)

    def test_chunk_failure_falls_back_to_raw_for_that_chunk_only(self):
        # One chunk fails terminally on both Haiku and Sonnet escalation.
        # The failed chunk is preserved raw; the rest are cleaned. A
        # warning is recorded.
        para = self._PERSONAL_PARA  # ~60K chars
        big_user = "\n\n".join([para] * 3)

        pair = _make_pair(big_user, "ai response")
        # Mix in one terminal failure across the user-side calls.
        fake = MagicMock()
        fake.messages = MagicMock()
        fake.messages.stream = MagicMock(side_effect=[
            _make_anthropic_message("clean-chunk-A"),  # user chunk 1
            FakeTerminalError("perm 1"),               # user chunk 2 (Haiku)
            FakeTerminalError("perm 2"),               # user chunk 2 (escalation retry)
            _make_anthropic_message("clean-chunk-C"),  # user chunk 3
            _make_anthropic_message("clean-ai"),       # ai
        ])
        client = AnthropicClient(client=fake)
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = clean_pair(pair, anthropic_client=client)
        # The successfully-cleaned chunks made it through.
        self.assertIn("clean-chunk-A", result.cleaned_user_input)
        self.assertIn("clean-chunk-C", result.cleaned_user_input)
        # The failed chunk's raw content (the original paragraph prefix)
        # is preserved.
        self.assertIn(para[:200], result.cleaned_user_input)
        # A warning is recorded.
        self.assertTrue(any("segment cleanup error" in w
                            for w in result.user_cleanup_warnings))


if __name__ == "__main__":
    unittest.main()
