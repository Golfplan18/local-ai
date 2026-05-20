"""Tests for Chunk B — slot-fallback advancement on retry (2026-05-20).

Closes the silent-failure class where a transient flake on the slot's
primary model bounced both the first call and the retry against the same
model. Before Chunk B, `_call_with_retry`'s second attempt re-hit the
same endpoint; if the model had a bad minute, both attempts came back
empty / errored and the pipeline degraded to the contingency. After
Chunk B, when callers pass `slot`/`gear`, the retry attempt advances the
slot's fallback chain via `_resolve_fallback_endpoint` — a different
model gets a chance to produce the verdict / revision / consolidation.

Pins:

  1. `_resolve_fallback_endpoint` asks the router for the next endpoint
     and returns the v1-shape conversion.

  2. `_call_with_retry` uses the fallback endpoint on its second attempt
     when slot+gear are provided and the helper returns one.

  3. Backwards compatibility: omitting slot/gear leaves the retry
     attempt pointed at the original endpoint (the pre-Chunk-B path).

  4. Safe degradation: if the router is unavailable, the helper returns
     None, and the caller silently reuses the original endpoint —
     identical to the pre-Chunk-B path.

  5. Router-side exceptions inside the helper don't poison the retry.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from boot import (
    _call_with_retry,
    _resolve_fallback_endpoint,
)


def _ep(name, model):
    """Minimal v1-shape endpoint dict (matches `Router._to_v1_endpoint`)."""
    return {"name": name, "type": "api", "service": "openrouter",
            "model": model, "status": "active"}


class TestResolveFallbackEndpoint(unittest.TestCase):
    """The helper asks the router for the next endpoint, excluding the
    current one. Returns a v1-shape dict when the router has one
    available; None otherwise.
    """

    def test_returns_next_endpoint_when_router_has_one(self):
        current = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")
        # Stub the router to return a different endpoint when our id
        # is in the exclusion set.
        v2_next = {"id": "moonshotai/kimi-k2.6", "type": "api"}
        v1_next = _ep("moonshotai/kimi-k2.6", "moonshotai/kimi-k2.6")

        mock_router = MagicMock()
        mock_router.resolve_endpoint.return_value = v2_next
        mock_router._to_v1_endpoint.return_value = v1_next

        with patch("boot._get_router", return_value=mock_router):
            result = _resolve_fallback_endpoint(
                "depth", 4, current, config_name="user-pipeline",
            )

        self.assertEqual(result, v1_next)
        # Verify the exclusion set carried the current endpoint's id.
        called_kwargs = mock_router.resolve_endpoint.call_args.kwargs
        self.assertIn("qwen/qwen3.6-plus", called_kwargs["excluded_ids"])
        # Verify config_name plumbed through.
        self.assertEqual(called_kwargs["config_name"], "user-pipeline")

    def test_returns_none_when_router_unavailable(self):
        current = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")
        with patch("boot._get_router", return_value=None):
            result = _resolve_fallback_endpoint("depth", 4, current)
        self.assertIsNone(result)

    def test_returns_none_when_router_has_no_fallback(self):
        current = _ep("only-model", "only-model")
        mock_router = MagicMock()
        mock_router.resolve_endpoint.return_value = None  # nothing left
        with patch("boot._get_router", return_value=mock_router):
            result = _resolve_fallback_endpoint("depth", 4, current)
        self.assertIsNone(result)

    def test_returns_none_when_current_endpoint_has_no_id(self):
        # An endpoint dict with no `name` field — we can't tell the
        # router what to exclude. Safe-degrade rather than guess.
        current = {"type": "api", "service": "openrouter"}
        mock_router = MagicMock()
        with patch("boot._get_router", return_value=mock_router):
            result = _resolve_fallback_endpoint("depth", 4, current)
        self.assertIsNone(result)
        mock_router.resolve_endpoint.assert_not_called()

    def test_router_exception_swallowed_returns_none(self):
        # Router-side failure should never poison the retry path —
        # caller falls back to the original endpoint.
        current = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")
        mock_router = MagicMock()
        mock_router.resolve_endpoint.side_effect = RuntimeError("router boom")
        with patch("boot._get_router", return_value=mock_router):
            result = _resolve_fallback_endpoint("depth", 4, current)
        self.assertIsNone(result)


class TestCallWithRetryUsesFallback(unittest.TestCase):
    """The retry attempt switches endpoints when slot+gear are provided
    and `_resolve_fallback_endpoint` returns a fallback.
    """

    def _messages(self):
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
        ]

    def test_retry_uses_fallback_endpoint_when_slot_provided(self):
        primary = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")
        fallback = _ep("moonshotai/kimi-k2.6", "moonshotai/kimi-k2.6")

        endpoint_seen = []
        recovery_text = "All checks pass.\nVERIFIED"

        def fake_call(messages, endpoint, images=None):
            endpoint_seen.append(endpoint.get("name"))
            # First attempt against primary returns empty (the flake).
            # Retry against fallback returns a real verdict.
            if endpoint.get("name") == "qwen/qwen3.6-plus":
                return ""
            return recovery_text

        with patch("boot._resolve_fallback_endpoint", return_value=fallback), \
             patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                self._messages(), primary, "verifier",
                min_chars=20, retry_hint=None, images=None,
                slot="depth", gear=4, config_name="user-pipeline",
            )

        self.assertEqual(
            endpoint_seen,
            ["qwen/qwen3.6-plus", "moonshotai/kimi-k2.6"],
            "retry attempt did not switch to the fallback endpoint",
        )
        self.assertTrue(ok)
        self.assertEqual(text, recovery_text)

    def test_no_slot_info_keeps_same_endpoint_on_retry(self):
        # Backwards compatibility — omitting slot/gear preserves the
        # pre-Chunk-B path (retry uses the same endpoint).
        primary = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")

        endpoint_seen = []

        def fake_call(messages, endpoint, images=None):
            endpoint_seen.append(endpoint.get("name"))
            return ""  # both attempts empty

        # `_resolve_fallback_endpoint` should not even be consulted.
        with patch("boot._resolve_fallback_endpoint") as resolve_mock, \
             patch("boot._run_model_with_tools", side_effect=fake_call):
            _call_with_retry(
                self._messages(), primary, "verifier",
                min_chars=20, retry_hint=None, images=None,
                # No slot/gear/config_name.
            )

        resolve_mock.assert_not_called()
        self.assertEqual(
            endpoint_seen,
            ["qwen/qwen3.6-plus", "qwen/qwen3.6-plus"],
            "retry should have re-hit the same endpoint",
        )

    def test_no_fallback_available_keeps_same_endpoint(self):
        # Slot+gear provided, but the helper returns None (no fallback
        # configured or router unavailable). The retry attempt must
        # silently reuse the original endpoint — identical to the
        # pre-Chunk-B path. No crash, no skip.
        primary = _ep("only-model", "only-model")

        endpoint_seen = []

        def fake_call(messages, endpoint, images=None):
            endpoint_seen.append(endpoint.get("name"))
            return ""

        with patch("boot._resolve_fallback_endpoint", return_value=None), \
             patch("boot._run_model_with_tools", side_effect=fake_call):
            _call_with_retry(
                self._messages(), primary, "verifier",
                min_chars=20, retry_hint=None, images=None,
                slot="depth", gear=4, config_name="user-pipeline",
            )

        self.assertEqual(endpoint_seen, ["only-model", "only-model"])

    def test_endpoint_swap_drops_regenerate_hint(self):
        # Chunk I (2026-05-20): when the retry attempt swaps to a
        # different endpoint, the "REGENERATE: the prior attempt was
        # unhealthy..." hint should NOT be appended. A different model
        # has no prior attempt to regenerate from — sending the task
        # fresh is cleaner. Same-endpoint retry still gets the hint.
        primary = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")
        fallback = _ep("moonshotai/kimi-k2.6", "moonshotai/kimi-k2.6")

        retry_user_content_seen = []

        def fake_call(messages, endpoint, images=None):
            user_msg = next(
                (m["content"] for m in messages if m["role"] == "user"),
                "",
            )
            retry_user_content_seen.append((endpoint.get("name"), user_msg))
            return "" if endpoint.get("name") == "qwen/qwen3.6-plus" else "All checks pass.\nVERIFIED"

        with patch("boot._resolve_fallback_endpoint", return_value=fallback), \
             patch("boot._run_model_with_tools", side_effect=fake_call):
            _call_with_retry(
                self._messages(), primary, "verifier",
                min_chars=20, retry_hint=None, images=None,
                slot="depth", gear=4, config_name="user-pipeline",
            )

        # First attempt — original task, no hint.
        first_name, first_msg = retry_user_content_seen[0]
        self.assertEqual(first_name, "qwen/qwen3.6-plus")
        self.assertNotIn("REGENERATE", first_msg)
        # Retry attempt — swapped endpoint, hint must be suppressed.
        retry_name, retry_msg = retry_user_content_seen[1]
        self.assertEqual(retry_name, "moonshotai/kimi-k2.6")
        self.assertNotIn(
            "REGENERATE", retry_msg,
            "endpoint-swap retry should not carry the regenerate hint",
        )
        self.assertEqual(
            retry_msg, "task",
            "endpoint-swap retry should send the original task verbatim",
        )

    def test_same_endpoint_retry_keeps_regenerate_hint(self):
        # Mirror test: when retry hits the same endpoint (no fallback
        # available), the regenerate hint must still land — otherwise
        # the second attempt has no signal that the prior attempt
        # failed for a specific reason.
        primary = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")

        retry_user_content_seen = []

        def fake_call(messages, endpoint, images=None):
            user_msg = next(
                (m["content"] for m in messages if m["role"] == "user"),
                "",
            )
            retry_user_content_seen.append(user_msg)
            return ""

        # No fallback available → same endpoint on retry.
        with patch("boot._resolve_fallback_endpoint", return_value=None), \
             patch("boot._run_model_with_tools", side_effect=fake_call):
            _call_with_retry(
                self._messages(), primary, "verifier",
                min_chars=20, retry_hint=None, images=None,
                slot="depth", gear=4, config_name="user-pipeline",
            )

        # First attempt — clean task.
        self.assertNotIn("REGENERATE", retry_user_content_seen[0])
        # Retry attempt — hint appended.
        self.assertIn(
            "REGENERATE", retry_user_content_seen[1],
            "same-endpoint retry should still carry the regenerate hint",
        )

    def test_healthy_first_attempt_skips_fallback_resolution(self):
        # When the first attempt is healthy, the retry never fires, so
        # the fallback helper should not even be consulted. Saves a
        # router round-trip on every successful first attempt.
        primary = _ep("qwen/qwen3.6-plus", "qwen/qwen3.6-plus")
        good = "All checks pass.\nVERIFIED"

        with patch("boot._resolve_fallback_endpoint") as resolve_mock, \
             patch("boot._run_model_with_tools", return_value=good):
            text, ok, reason = _call_with_retry(
                self._messages(), primary, "verifier",
                min_chars=20, retry_hint=None, images=None,
                slot="depth", gear=4, config_name="user-pipeline",
            )

        resolve_mock.assert_not_called()
        self.assertTrue(ok)
        self.assertEqual(text, good)


if __name__ == "__main__":
    unittest.main()
