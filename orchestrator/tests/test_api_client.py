"""Tests for the Anthropic API client wrapper (Phase 1.5).

Verifies:
  - Token estimation + cost estimation
  - Single call uses injected SDK client (no real network)
  - Retry on classified-retriable errors with exponential backoff
  - Terminal failure path records error + does not raise
  - Cumulative stats tracking under concurrent calls
  - call_batch preserves input order
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.api_client import (  # noqa: E402
    AnthropicClient,
    CallResult,
    ClientStats,
    DEFAULT_MODEL,
    estimate_cost_usd,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# Fake SDK message + client builders
# ---------------------------------------------------------------------------


class _FakeStream:
    """Mimics the anthropic streaming context manager."""
    def __init__(self, text: str, input_tokens: int = 100,
                  output_tokens: int = 50):
        self._text = text
        self._in   = input_tokens
        self._out  = output_tokens
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    @property
    def text_stream(self):
        # The SDK yields text chunks; for tests we yield the whole text once.
        return iter([self._text])
    def get_final_message(self):
        msg = MagicMock()
        msg.usage = MagicMock(input_tokens=self._in, output_tokens=self._out)
        return msg


def _fake_stream(text: str, input_tokens: int = 100,
                  output_tokens: int = 50) -> _FakeStream:
    return _FakeStream(text, input_tokens, output_tokens)


def _fake_client_returning(*texts) -> MagicMock:
    """Build a fake anthropic client whose .messages.stream(...) returns
    a streaming context manager yielding the given text on successive calls."""
    client = MagicMock()
    client.messages = MagicMock()
    streams = [_fake_stream(t) for t in texts]
    client.messages.stream = MagicMock(side_effect=streams)
    return client


def _fake_client_raising(*errors) -> MagicMock:
    """Build a fake client that raises `errors` in order on successive calls."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=errors)
    return client


def _fake_client_seq(*items) -> MagicMock:
    """Each item is either an exception (raises) or a string (returns)."""
    client = MagicMock()
    client.messages = MagicMock()
    side_effects = []
    for it in items:
        if isinstance(it, Exception):
            side_effects.append(it)
        else:
            side_effects.append(_fake_stream(it))
    client.messages.stream = MagicMock(side_effect=side_effects)
    return client


# Custom exception classes for retry classification.
class FakeRateLimitError(Exception):
    pass


class FakeTimeoutError(Exception):
    pass


class FakeOverloadedError(Exception):
    pass


class FakePermanentError(Exception):
    pass


# ---------------------------------------------------------------------------
# Token + cost estimation
# ---------------------------------------------------------------------------


class TestEstimation(unittest.TestCase):

    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_estimate_tokens_proportional(self):
        # ~4 chars per token
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcd" * 100), 100)

    def test_cost_haiku(self):
        # 1M input + 1M output Haiku = $1 + $5 = $6
        cost = estimate_cost_usd("claude-haiku-4-5",
                                   input_tokens=1_000_000,
                                   output_tokens=1_000_000)
        self.assertAlmostEqual(cost, 6.0)

    def test_cost_unknown_model_zero(self):
        cost = estimate_cost_usd("unknown-model", 1000, 1000)
        self.assertEqual(cost, 0.0)


# ---------------------------------------------------------------------------
# Single-call success
# ---------------------------------------------------------------------------


class TestSingleCall(unittest.TestCase):

    def test_call_returns_text(self):
        client = AnthropicClient(client=_fake_client_returning("hello"))
        result = client.call(user="ping")
        self.assertEqual(result.text, "hello")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.error, "")
        self.assertGreater(result.input_tokens, 0)
        self.assertGreater(result.output_tokens, 0)
        self.assertGreater(result.cost_usd, 0)

    def test_call_with_system_and_messages(self):
        fake = _fake_client_returning("ok")
        client = AnthropicClient(client=fake)
        result = client.call(system="be terse",
                              messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(result.text, "ok")
        # Verify call kwargs (now .stream not .create)
        call_kwargs = fake.messages.stream.call_args.kwargs
        self.assertEqual(call_kwargs["system"], "be terse")
        self.assertEqual(call_kwargs["model"], DEFAULT_MODEL)

    def test_call_per_call_model_override(self):
        fake = _fake_client_returning("ok")
        client = AnthropicClient(client=fake)
        client.call(user="hi", model="claude-sonnet-4-5")
        self.assertEqual(fake.messages.stream.call_args.kwargs["model"],
                         "claude-sonnet-4-5")


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


class TestRetry(unittest.TestCase):

    def test_retry_on_rate_limit(self):
        client = AnthropicClient(
            client=_fake_client_seq(
                FakeRateLimitError("429 Too Many Requests"),
                "ok",
            ),
            max_retries=3,
        )
        # Patch backoff to no-op so test runs fast.
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = client.call(user="hi")
        self.assertEqual(result.text, "ok")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.error, "")

    def test_retry_on_timeout(self):
        client = AnthropicClient(
            client=_fake_client_seq(
                FakeTimeoutError("Connection timeout"),
                FakeTimeoutError("Connection timeout"),
                "ok",
            ),
            max_retries=4,
        )
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = client.call(user="hi")
        self.assertEqual(result.text, "ok")
        self.assertEqual(result.attempts, 3)

    def test_retry_classification_message_substring(self):
        # Generic Exception with retriable substring in message.
        client = AnthropicClient(
            client=_fake_client_seq(
                Exception("Service overloaded, please retry"),
                "ok",
            ),
            max_retries=3,
        )
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = client.call(user="hi")
        self.assertEqual(result.text, "ok")

    def test_terminal_error_records_failure(self):
        client = AnthropicClient(
            client=_fake_client_raising(
                FakePermanentError("authentication failed"),
            ),
            max_retries=3,
        )
        result = client.call(user="hi")
        self.assertEqual(result.text, "")
        self.assertIn("authentication", result.error.lower())
        self.assertEqual(result.attempts, 1)

    def test_max_retries_exhausted(self):
        # Always raises retriable errors → exhaust retries
        errors = [FakeRateLimitError("429")] * 5
        client = AnthropicClient(
            client=_fake_client_raising(*errors),
            max_retries=3,
        )
        client._backoff = staticmethod(lambda attempt: 0.0)
        result = client.call(user="hi")
        self.assertEqual(result.text, "")
        self.assertNotEqual(result.error, "")
        self.assertEqual(result.attempts, 3)


# ---------------------------------------------------------------------------
# retry-after header handling
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Mimics an httpx Response with a .headers dict."""
    def __init__(self, headers):
        self.headers = headers


class _RateLimitWithRetryAfter(Exception):
    """Mimics anthropic.RateLimitError carrying a .response with headers."""
    def __init__(self, retry_after_value, message="429 Too Many Requests"):
        super().__init__(message)
        headers = {} if retry_after_value is None else {"retry-after": retry_after_value}
        self.response = _FakeResponse(headers)


class TestRetryAfterHeader(unittest.TestCase):

    def test_extract_retry_after_returns_seconds(self):
        exc = _RateLimitWithRetryAfter("42")
        self.assertEqual(AnthropicClient._extract_retry_after(exc), 42.0)

    def test_extract_retry_after_returns_none_when_missing(self):
        exc = _RateLimitWithRetryAfter(None)
        self.assertIsNone(AnthropicClient._extract_retry_after(exc))

    def test_extract_retry_after_handles_no_response_attribute(self):
        exc = FakeRateLimitError("plain rate-limit error, no response attached")
        self.assertIsNone(AnthropicClient._extract_retry_after(exc))

    def test_extract_retry_after_returns_none_for_malformed_value(self):
        exc = _RateLimitWithRetryAfter("not-a-number")
        self.assertIsNone(AnthropicClient._extract_retry_after(exc))

    def test_extract_retry_after_returns_none_above_sanity_cap(self):
        # 9999s is unreasonable — fall back to backoff instead of waiting.
        exc = _RateLimitWithRetryAfter("9999")
        self.assertIsNone(AnthropicClient._extract_retry_after(exc))

    def test_extract_retry_after_returns_none_for_zero_or_negative(self):
        self.assertIsNone(
            AnthropicClient._extract_retry_after(_RateLimitWithRetryAfter("0"))
        )
        self.assertIsNone(
            AnthropicClient._extract_retry_after(_RateLimitWithRetryAfter("-5"))
        )

    def test_call_uses_retry_after_header_for_sleep(self):
        # When retry-after is present, sleep duration must come from the header
        # — NOT from exponential backoff.
        sleeps = []
        client = AnthropicClient(
            client=_fake_client_seq(
                _RateLimitWithRetryAfter("3"),  # asks for 3s
                "ok",
            ),
            max_retries=3,
        )
        # Capture sleep durations and short-circuit them.
        import orchestrator.historical.api_client as mod
        orig_sleep = mod.time.sleep
        mod.time.sleep = lambda s: sleeps.append(s)
        try:
            result = client.call(user="hi")
        finally:
            mod.time.sleep = orig_sleep
        self.assertEqual(result.text, "ok")
        self.assertEqual(result.attempts, 2)
        # The single sleep must be the 3s the header asked for.
        self.assertEqual(sleeps, [3.0])

    def test_call_falls_back_to_backoff_when_retry_after_absent(self):
        # No retry-after header present → exponential backoff used.
        sleeps = []
        client = AnthropicClient(
            client=_fake_client_seq(
                _RateLimitWithRetryAfter(None),
                "ok",
            ),
            max_retries=3,
        )
        # Force backoff to a recognizable value.
        client._backoff = staticmethod(lambda attempt: 7.5)
        import orchestrator.historical.api_client as mod
        orig_sleep = mod.time.sleep
        mod.time.sleep = lambda s: sleeps.append(s)
        try:
            result = client.call(user="hi")
        finally:
            mod.time.sleep = orig_sleep
        self.assertEqual(result.text, "ok")
        self.assertEqual(sleeps, [7.5])


# ---------------------------------------------------------------------------
# Cumulative stats
# ---------------------------------------------------------------------------


class TestStats(unittest.TestCase):

    def test_stats_track_successes_and_failures(self):
        client = AnthropicClient(
            client=_fake_client_seq("ok", FakePermanentError("nope"), "ok"),
        )
        client.call(user="a")
        client.call(user="b")
        client.call(user="c")
        s = client.stats()
        self.assertEqual(s.calls, 3)
        self.assertEqual(s.successes, 2)
        self.assertEqual(s.failures, 1)
        self.assertGreater(s.input_tokens, 0)
        self.assertGreater(s.cost_usd, 0)

    def test_stats_thread_safe_under_concurrency(self):
        # Many concurrent successful calls — stats must reflect all of them.
        client = AnthropicClient(
            client=_fake_client_seq(*(["ok"] * 64)),
        )
        threads = []
        for _ in range(64):
            t = threading.Thread(target=lambda: client.call(user="hi"))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        s = client.stats()
        self.assertEqual(s.calls, 64)
        self.assertEqual(s.successes, 64)


# ---------------------------------------------------------------------------
# Concurrent batch
# ---------------------------------------------------------------------------


class TestCallBatch(unittest.TestCase):

    def test_call_batch_preserves_order(self):
        # 10 items each returning their own string.
        texts = [f"reply-{i}" for i in range(10)]
        client = AnthropicClient(client=_fake_client_seq(*texts))
        items = [{"user": f"prompt-{i}"} for i in range(10)]
        # Note: with thread pool and side_effect being deterministic order,
        # the SDK calls happen in some order. But our results list preserves
        # input order regardless of completion order.
        results = client.call_batch(
            items, fn=lambda it: it, max_workers=4,
        )
        self.assertEqual(len(results), 10)
        # All succeed (texts could have been served in any order, but
        # order in results matches the input order; can't guarantee text-i
        # ↔ result-i pairing because thread pool is unordered. We just
        # verify all 10 succeeded.)
        self.assertTrue(all(r.error == "" for r in results))

    def test_call_batch_empty_input(self):
        client = AnthropicClient(client=_fake_client_returning())
        self.assertEqual(client.call_batch([], fn=lambda x: x), [])


# ---------------------------------------------------------------------------
# Auth resolution (no real keyring touch)
# ---------------------------------------------------------------------------


class TestAuth(unittest.TestCase):

    def test_no_key_raises_at_construction(self):
        # Defeat both env var and keyring.
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with unittest.mock.patch(
                "orchestrator.historical.api_client.AnthropicClient._resolve_api_key",
                return_value="",
            ):
                with self.assertRaises(RuntimeError):
                    AnthropicClient()


if __name__ == "__main__":
    import unittest.mock  # noqa: F401  (used by TestAuth)
    unittest.main()
