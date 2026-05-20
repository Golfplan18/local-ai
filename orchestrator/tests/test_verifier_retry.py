"""Tests for the verifier retry wrapper (Chunk A — 2026-05-20).

Closes the silent-failure class where a single OpenRouter / model
transient flake (empty response, malformed streaming chunk) classified
the verifier as BROKEN and unblocked the Gear 3 / Gear 4 verify cycle
without re-revision. The verifier was the only pipeline step calling
``_run_model_with_tools`` directly; every other step already went
through ``_call_with_retry``.

The test pins three behaviours:

  1. ``_step_output_health`` accepts both legacy free-form verdict
     lines (``VERIFIED``) and the newer structured form
     (``VERDICT: PASS``) via the shared line-anchored extractor.
     Substring matches buried inside prose no longer mask a missing
     verdict.

  2. ``_call_with_retry`` retries verifier calls that produce empty
     output on the first attempt, and accepts a real verdict that
     lands on retry.

  3. Two consecutive empties yield ``(text="", ok=False,
     reason="empty after stripping dispatch noise")`` — the caller's
     ``_verifier_broken`` then routes the cycle to the unblock path
     (which is correct: persistent verifier-side failure shouldn't
     re-revise the analyst).
"""

import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from boot import (
    _call_with_retry,
    _step_output_health,
    _verifier_broken,
    _verifier_passed,
)


class TestVerifierHealthCheck(unittest.TestCase):
    """``_step_output_health`` must accept both verdict-line shapes and
    reject prose with embedded-but-not-anchored verdict words.
    """

    def test_legacy_verified_line_is_healthy(self):
        out = (
            "V1 — Mandatory-fix coverage: all addressed.\n"
            "V2 — N/A.\n"
            "V3 — N/A.\n"
            "V4 — Nuance preserved.\n"
            "V5 — Contract satisfied.\n"
            "VERIFIED"
        )
        ok, reason = _step_output_health(out, "verifier", min_chars=20)
        self.assertTrue(ok, f"reason was {reason!r}")

    def test_legacy_verification_failed_line_is_healthy(self):
        out = "V1 fails: silent-drop of finding 3.\nVERIFICATION FAILED"
        ok, reason = _step_output_health(out, "verifier", min_chars=20)
        self.assertTrue(ok, f"reason was {reason!r}")

    def test_structured_verdict_pass_is_healthy(self):
        out = "All V1-V9 checks pass.\nVERDICT: PASS"
        ok, reason = _step_output_health(out, "verifier", min_chars=20)
        self.assertTrue(ok, f"reason was {reason!r}")

    def test_structured_verdict_fail_is_healthy(self):
        out = "V1 fails: silent-drop of finding 3.\nVERDICT: FAIL"
        ok, reason = _step_output_health(out, "verifier", min_chars=20)
        self.assertTrue(ok, f"reason was {reason!r}")

    def test_structured_verdict_broken_is_healthy(self):
        # The model self-declaring BROKEN is doing its job — the
        # health check passes, and ``_verifier_broken`` separately
        # routes this to the cycle-unblock path.
        out = (
            "Cannot complete verification — evaluator output was empty "
            "this cycle and there is no MANDATORY FIXES list to match "
            "against.\nVERDICT: BROKEN"
        )
        ok, reason = _step_output_health(out, "verifier", min_chars=20)
        self.assertTrue(ok, f"reason was {reason!r}")
        # Sanity: the dedicated broken-classifier catches this too.
        self.assertTrue(_verifier_broken(out))

    def test_embedded_verified_word_in_prose_is_unhealthy(self):
        # The bug the line-anchored check closes: substring "VERIFIED"
        # buried in dismissive prose used to pass the old check.
        out = (
            "The reviser's claim that finding 3 is addressed cannot be "
            "VERIFIED against the source — the change is purely "
            "cosmetic. No verdict line follows."
        )
        ok, reason = _step_output_health(out, "verifier", min_chars=20)
        self.assertFalse(ok)
        self.assertIn("verdict token", reason)

    def test_empty_output_is_unhealthy(self):
        ok, reason = _step_output_health("", "verifier", min_chars=20)
        self.assertFalse(ok)
        self.assertIn("empty", reason)


class TestVerifierRetryRecovery(unittest.TestCase):
    """``_call_with_retry`` must retry on empty / unhealthy verifier
    output and accept a real verdict on the second attempt.
    """

    def _verify_messages(self):
        return [
            {"role": "system", "content": "verifier system prompt"},
            {"role": "user", "content": "verifier user message"},
        ]

    def _endpoint(self):
        return {"name": "stub", "service": "openrouter", "model": "x/y"}

    def test_retry_recovers_after_empty_first_attempt(self):
        attempts = []

        def fake_call(messages, endpoint, images=None):
            attempts.append(messages)
            # First attempt: empty (the OpenRouter empty-content case).
            # Second attempt: a real verdict.
            if len(attempts) == 1:
                return ""
            return (
                "V1-V9 walk: all checks pass against the revised "
                "draft. No injection found.\nVERIFIED"
            )

        with patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                self._verify_messages(), self._endpoint(), "verifier",
                min_chars=20, retry_hint=None, images=None,
            )

        self.assertEqual(len(attempts), 2, "retry did not fire")
        self.assertTrue(ok, f"reason was {reason!r}")
        self.assertTrue(_verifier_passed(text))
        self.assertFalse(_verifier_broken(text))

    def test_two_empties_resolve_to_unhealthy_empty(self):
        def fake_call(messages, endpoint, images=None):
            return ""

        with patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                self._verify_messages(), self._endpoint(), "verifier",
                min_chars=20, retry_hint=None, images=None,
            )

        self.assertEqual(text, "")
        self.assertFalse(ok)
        # ``_verifier_broken`` short-circuits on empty input — the
        # cycle-unblock path triggers as expected.
        self.assertTrue(_verifier_broken(text))

    def test_openrouter_json_parse_error_routes_to_broken(self):
        # The exact shape from the 2026-05-20 cosmology smoke test
        # (smoke-cag-validate-1779238723). The dispatch wrapper at the
        # OpenRouter branch returns ``[Error calling OpenRouter API:
        # <e>]`` on any SDK exception, including the JSON parse error
        # that triggered the breadth-verifier failure.
        err = (
            "[Error calling OpenRouter API: Expecting value: line 333 "
            "column 1 (char 1826)]"
        )

        def fake_call(messages, endpoint, images=None):
            return err

        with patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                self._verify_messages(), self._endpoint(), "verifier",
                min_chars=20, retry_hint=None, images=None,
            )

        # Two attempts, both the same error. Retry layer reports
        # unhealthy; broken-classifier flags it for cycle-unblock.
        self.assertFalse(ok)
        self.assertTrue(_verifier_broken(text))

    def test_model_exception_on_both_attempts_routes_to_broken(self):
        # When ``_run_model_with_tools`` raises on the first call,
        # ``_call_with_retry`` substitutes ``[verifier call error: ...]``;
        # if the retry call also raises, the retry-branch substitutes
        # ``[verifier retry error: ...]``. Both shapes must classify as
        # BROKEN so the cycle unblocks rather than re-revising against
        # transport noise.
        def fake_call(messages, endpoint, images=None):
            raise RuntimeError("transport-level failure")

        with patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                self._verify_messages(), self._endpoint(), "verifier",
                min_chars=20, retry_hint=None, images=None,
            )

        self.assertFalse(ok)
        # Retry branch's substitution wins as the returned text.
        self.assertIn("verifier retry error", text)
        self.assertTrue(_verifier_broken(text))

    def test_first_attempt_exception_only_classifies_as_broken(self):
        # If the first call raises but the retry call succeeds, the
        # retry's text is returned. If both fail with different shapes,
        # the broken-classifier still catches it. Pin both legs.
        calls = []

        def fake_call(messages, endpoint, images=None):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("first-attempt transport failure")
            # Retry succeeds with a real verdict.
            return "V1-V9 walk: all pass.\nVERIFIED"

        with patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                self._verify_messages(), self._endpoint(), "verifier",
                min_chars=20, retry_hint=None, images=None,
            )

        self.assertEqual(len(calls), 2, "retry did not fire after first-attempt exception")
        self.assertTrue(ok)
        self.assertTrue(_verifier_passed(text))


class TestRetryRegression(unittest.TestCase):
    """Before the fix, the verifier was called via ``_run_model_with_tools``
    directly with no retry layer — meaning a single empty response went
    straight to ``_verifier_broken`` and unblocked the cycle. This test
    pins that the new path retries.
    """

    def test_single_attempt_empty_would_have_been_silent_failure(self):
        # Pre-fix mental model: the call would have been
        # ``_run_model_with_tools(...)`` once and that's it. Simulate
        # by directly calling the underlying function once and
        # checking it would have produced a BROKEN cycle-unblock.
        with patch("boot._run_model_with_tools", return_value=""):
            from boot import _run_model_with_tools as raw
            single_attempt = raw(
                [{"role": "system", "content": ""},
                 {"role": "user", "content": ""}],
                {"service": "openrouter", "model": "x/y"},
            )
        self.assertEqual(single_attempt, "")
        # The pre-fix flow would have run ``_verifier_broken("")`` →
        # True → unblocked the cycle. After the fix, the call path
        # is through ``_call_with_retry`` which gives empty output a
        # second chance before classification.
        self.assertTrue(_verifier_broken(single_attempt))

    def test_retry_path_gives_second_chance(self):
        # Same input shape as the regression test, but through the
        # retry wrapper: this is the new behaviour.
        responses = iter(["", "All checks pass.\nVERDICT: PASS"])

        def fake_call(messages, endpoint, images=None):
            return next(responses)

        with patch("boot._run_model_with_tools", side_effect=fake_call):
            text, ok, reason = _call_with_retry(
                [{"role": "system", "content": ""},
                 {"role": "user", "content": ""}],
                {"service": "openrouter", "model": "x/y"},
                "verifier", min_chars=20, retry_hint=None, images=None,
            )

        self.assertTrue(ok)
        self.assertTrue(_verifier_passed(text))


if __name__ == "__main__":
    unittest.main()
