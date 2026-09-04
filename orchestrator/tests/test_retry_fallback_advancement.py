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
    ModelInvocationFailure,
    _call_with_retry,
    _resolve_fallback_endpoint,
    resolve_single_pass_endpoint,
    run_single_pass_with_tools,
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

    def test_gear2_accepts_one_word_primary_answer(self):
        primary = _ep("primary-endpoint", "primary-model")
        context = {}
        with patch("boot._resolve_fallback_endpoint") as resolve_mock, \
             patch("boot._run_model_with_tools", return_value="Yes"), \
             patch("pipeline_health.record") as warning:
            result = run_single_pass_with_tools(
                self._messages(), primary, slot="fast", gear=2,
                config_name="user-pipeline", history=[], context_pkg=context,
            )

        self.assertEqual(result, "Yes")
        resolve_mock.assert_not_called()
        warning.assert_not_called()

    def test_gear2_same_model_retry_emits_no_substitution_warning(self):
        primary = _ep("primary-endpoint", "same-model")
        responses = iter(("", "Recovered"))
        with patch("boot._resolve_fallback_endpoint") as resolve_mock, \
             patch("boot._run_model_with_tools",
                   side_effect=lambda *_a, **_k: next(responses)), \
             patch("pipeline_health.record") as warning:
            result = run_single_pass_with_tools(
                self._messages(), primary, slot="fast", gear=2,
                config_name="user-pipeline", history=[], context_pkg={},
            )

        self.assertEqual(result, "Recovered")
        self.assertFalse(result.substituted)
        resolve_mock.assert_not_called()
        warning.assert_not_called()

    def test_gear2_alternate_model_repairs_request_with_one_warning(self):
        primary = _ep("primary-endpoint", "primary-model")
        fallback = _ep("fallback-endpoint", "fallback-model")
        calls = []

        def invoke(_messages, endpoint, images=None):
            calls.append(endpoint["name"])
            return "" if endpoint["name"] == "primary-endpoint" else "Recovered"

        with patch("boot._resolve_fallback_endpoint", return_value=fallback), \
             patch("boot._run_model_with_tools", side_effect=invoke), \
             patch("pipeline_health.record") as warning:
            result = run_single_pass_with_tools(
                self._messages(), primary, slot="fast", gear=2,
                config_name="user-pipeline", history=[], context_pkg={},
            )

        self.assertEqual(calls, [
            "primary-endpoint", "primary-endpoint", "fallback-endpoint",
        ])
        self.assertEqual(result, "Recovered")
        self.assertTrue(result.substituted)
        self.assertEqual(result.selected_endpoint_id, "fallback-endpoint")
        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[0], "model_substitution")

    def test_gear2_alternate_endpoint_for_same_model_emits_no_warning(self):
        primary = _ep("primary-provider", "shared-model")
        retry_endpoint = _ep("backup-provider", "shared-model")

        def invoke(_messages, endpoint, images=None):
            return "" if endpoint["name"] == "primary-provider" else "Recovered"

        with patch("boot._resolve_fallback_endpoint",
                   return_value=retry_endpoint), \
             patch("boot._run_model_with_tools", side_effect=invoke), \
             patch("pipeline_health.record") as warning:
            result = run_single_pass_with_tools(
                self._messages(), primary, slot="fast", gear=2,
                config_name="user-pipeline", history=[], context_pkg={},
            )

        self.assertEqual(result.selected_endpoint_id, "backup-provider")
        self.assertFalse(result.substituted)
        warning.assert_not_called()

    def test_gear2_exhaustion_raises_typed_failure_without_candidate_text(self):
        primary = _ep("primary-endpoint", "primary-model")
        fallback = _ep("fallback-endpoint", "fallback-model")
        with patch("boot._resolve_fallback_endpoint",
                   side_effect=(fallback, None)), \
             patch("boot._run_model_with_tools", return_value=""):
            with self.assertRaises(ModelInvocationFailure) as raised:
                run_single_pass_with_tools(
                    self._messages(), primary, slot="fast", gear=2,
                    config_name="user-pipeline", history=[], context_pkg={},
                )

        self.assertEqual(raised.exception.kind, "exhausted_chain")
        self.assertIsNone(raised.exception.selected_endpoint_id)
        self.assertIn("primary-endpoint",
                      raised.exception.attempted_endpoint_ids)
        self.assertIn("fallback-endpoint",
                      raised.exception.attempted_endpoint_ids)

    def test_gear2_legacy_cell_advances_its_own_configured_chain(self):
        primary = _ep("legacy-primary", "legacy-primary-model")
        fallback = _ep("legacy-fallback", "legacy-fallback-model")

        def configured_endpoint(_config, slot, **_kwargs):
            if slot == "fast":
                return None
            if slot == "step1_cleanup":
                return primary
            self.fail(f"unexpected cell lookup: {slot}")

        with patch("boot.get_slot_endpoint", side_effect=configured_endpoint):
            endpoint, selected_cell = resolve_single_pass_endpoint(
                {}, 2, config_name="legacy-profile")

        self.assertEqual(endpoint, primary)
        self.assertEqual(selected_cell, "step1_cleanup")

        def invoke(_messages, selected_endpoint, images=None):
            if selected_endpoint["name"] == "legacy-primary":
                return ""
            return "Recovered from the legacy cell fallback"

        with patch("boot._run_model_with_tools", side_effect=invoke), \
             patch("boot._resolve_fallback_endpoint",
                   return_value=fallback) as advance:
            result = run_single_pass_with_tools(
                self._messages(), endpoint, slot=selected_cell, gear=2,
                config_name="legacy-profile", history=[], context_pkg={},
            )

        self.assertEqual(result, "Recovered from the legacy cell fallback")
        self.assertEqual(advance.call_args.args[:3], (
            "step1_cleanup", 2, primary,
        ))


if __name__ == "__main__":
    unittest.main()
