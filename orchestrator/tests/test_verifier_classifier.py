"""Tests for ``_verifier_broken`` against the dispatch-wrapper substitution
shapes emitted when a verifier-side model call raises.

The pipeline classifies verifier output three ways: PASS (real verdict),
FAIL (real verdict against analyst draft), BROKEN (the verifier itself
failed — re-revision must NOT fire). Prior to 2026-05-17 the OpenRouter
dispatch wrapper's substitution shape (``"[Error calling OpenRouter API:
<e>]"``) was not in ``_PROVIDER_TRANSPORT_ERROR_MARKERS``, so non-rate-limit
OpenRouter failures (billing / 404 / 5xx) were silently misclassified as
not-pass and the analyst was asked to rewrite the draft against what was
actually a transport-error message. These tests pin the BROKEN
classification for every dispatch-wrapper shape.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from boot import (
    _PROVIDER_TRANSPORT_ERROR_MARKERS,
    _verifier_broken,
    _verifier_passed,
)


class TestDispatchWrapperShapesClassifyAsBroken(unittest.TestCase):
    """Each provider's dispatch wrapper emits a distinctive substring on
    exception. The classifier must treat all of them as verifier-side
    failure, not analyst-side FAIL.
    """

    def test_openrouter_transport_error_is_broken(self):
        # The bug this fix closes: a 401 / 404 / 5xx wrapped by the
        # OpenAI SDK at the OpenRouter base URL.
        output = (
            "[Error calling OpenRouter API: AuthenticationError: "
            "Error code: 401 - {'error': {'message': 'No auth credentials "
            "found', 'code': 401}}]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_openrouter_billing_error_is_broken(self):
        output = (
            "[Error calling OpenRouter API: BadRequestError: Error code: "
            "402 - {'error': {'message': 'Insufficient credits', "
            "'code': 402}}]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_openrouter_404_is_broken(self):
        output = (
            "[Error calling OpenRouter API: NotFoundError: Error code: "
            "404 - {'error': {'message': 'No endpoints found that "
            "support requested parameters'}}]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_openrouter_5xx_is_broken(self):
        output = (
            "[Error calling OpenRouter API: APIError: 503 upstream "
            "model returned 503 service unavailable]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_claude_dispatch_error_is_broken(self):
        output = (
            "[Error calling Claude API: anthropic.BadRequestError: "
            "Error code: 400 - {'type': 'error', 'error': "
            "{'type': 'invalid_request_error', 'message': '...'}}]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_openai_dispatch_error_is_broken(self):
        output = (
            "[Error calling OpenAI API: openai.AuthenticationError: "
            "Error code: 401]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_gemini_dispatch_error_is_broken(self):
        output = (
            "[Error calling Gemini API: google.api_core.exceptions."
            "PermissionDenied: 403 The caller does not have permission]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_gemini_missing_key_is_broken(self):
        output = (
            "[Error calling Gemini API: No API key found. Store via: "
            "keyring set ora gemini-api-key]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_openrouter_missing_key_is_broken(self):
        output = (
            "[Error calling OpenRouter API: No API key found. Store via: "
            "keyring set ora openrouter-api-key]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_local_model_dispatch_error_is_broken(self):
        output = (
            "[Error calling local model: ConnectionError: HTTPConnectionPool"
            "(host='localhost', port=11434): Max retries exceeded]"
        )
        self.assertTrue(_verifier_broken(output))

    def test_mlx_model_dispatch_error_is_broken(self):
        output = (
            "[Error calling MLX model 'qwen3.5-4b-mlx': RuntimeError: "
            "Failed to load model]"
        )
        self.assertTrue(_verifier_broken(output))


class TestCaseInsensitiveMarkerMatch(unittest.TestCase):
    """``_verifier_broken`` lowercases its input — markers must match
    regardless of the casing the provider emits.
    """

    def test_uppercase_marker_text_matches(self):
        output = "[ERROR CALLING OPENROUTER API: SOMETHING FAILED]"
        self.assertTrue(_verifier_broken(output))

    def test_mixedcase_marker_text_matches(self):
        output = "[Error Calling OpenRouter Api: Something Failed]"
        self.assertTrue(_verifier_broken(output))


class TestRealVerdictsDoNotClassifyAsBroken(unittest.TestCase):
    """A genuine verifier verdict must not trip the broken-marker check.
    """

    def test_structured_verdict_pass_is_not_broken(self):
        output = (
            "## Verification Status\n\nAll eight checks pass.\n\n"
            "VERDICT: PASS"
        )
        self.assertFalse(_verifier_broken(output))
        self.assertTrue(_verifier_passed(output))

    def test_structured_verdict_fail_is_not_broken(self):
        # FAIL is a real analyst-side verdict, NOT verifier-broken.
        output = (
            "## Verification Status\n\nClaim 2 lacks citation; "
            "Claim 5 contradicts the source.\n\nVERDICT: FAIL"
        )
        self.assertFalse(_verifier_broken(output))

    def test_structured_pass_with_rate_limit_text_is_not_broken(self):
        # A verifier can legitimately approve code or prose that contains
        # generic outage phrases. Those phrases must not override an
        # anchored real verdict unless they appear as explicit wrapper
        # errors.
        output = (
            "## Verification Status\n\nThe React error branch correctly "
            "renders the user-facing string 'Rate limit exceeded'.\n\n"
            "VERDICT: PASS"
        )
        self.assertFalse(_verifier_broken(output))
        self.assertTrue(_verifier_passed(output))

    def test_legacy_verified_form_is_not_broken(self):
        output = (
            "All checks pass. The revised draft addresses each finding "
            "from the prior cycle.\n\nVERIFIED — all checks complete."
        )
        self.assertFalse(_verifier_broken(output))

    def test_legacy_verification_failed_is_not_broken(self):
        output = (
            "Claim 2 unsupported; reviser did not address coverage gap "
            "on claim 5.\n\nVERIFICATION FAILED — see findings above."
        )
        self.assertFalse(_verifier_broken(output))


class TestSharedMarkerListWiring(unittest.TestCase):
    """Pin the shape of ``_PROVIDER_TRANSPORT_ERROR_MARKERS`` so the
    dispatch-wrapper entries can't be dropped silently in a future
    cleanup.
    """

    def test_all_provider_wrappers_present(self):
        for marker in (
            "error calling claude api",
            "error calling openai api",
            "error calling gemini api",
            "error calling openrouter api",
            "error calling local model",
            "error calling mlx model",
        ):
            self.assertIn(marker, _PROVIDER_TRANSPORT_ERROR_MARKERS)


if __name__ == "__main__":
    unittest.main()
