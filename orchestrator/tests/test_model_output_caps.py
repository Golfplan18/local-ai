"""Output caps come from the model, not from a flat default.

Before 2026-08-01 every API call used one flat default regardless of the
model. That was wrong in both directions: it exceeded gpt-4o's ceiling, so the
provider rejected the request and _call_api_with_truncation_retry returned the
rejection as *text* rather than raising — a silent failure — while throttling
models that will emit far more than 32000.

These cover the resolution order and the provider-correction path, which are the
user-visible behaviours. The registry lookup itself is not tested separately.
"""

import unittest
from unittest import mock

from orchestrator import boot

# What one first call requests when the endpoint declares neither an explicit
# cap nor any context metadata: a conservative quarter of the fail-small
# 32_768 window (boot._endpoint_initial_output_tokens). Until 2026-08-10 this
# was a flat default regardless of the endpoint, which reserved the whole
# unknown window for output and could reject even a short prompt.
NO_METADATA_FALLBACK = 8192
# An endpoint that declares a real context window but no cap gets the full
# frontier-model allowance instead.
DECLARED_WINDOW_FALLBACK = 32_000


class ModelOutputCapResolutionTests(unittest.TestCase):

    def setUp(self):
        boot._MODEL_OUTPUT_CAPS = None
        self.addCleanup(setattr, boot, "_MODEL_OUTPUT_CAPS", None)

    def _capture(self, endpoint, *, truncated=False, raises=None):
        """Run one call, returning the max_tokens values actually requested."""
        seen = []
        calls = {"n": 0}

        def make_call(cap):
            seen.append(cap)
            calls["n"] += 1
            if raises is not None and calls["n"] == 1:
                raise raises
            return "body", truncated

        with mock.patch.object(boot, "_record_physical_model_call_config"):
            text = boot._call_api_with_truncation_retry(
                make_call, "TestProvider", endpoint)
        return seen, text

    def test_published_cap_is_used_instead_of_the_flat_default(self):
        boot._MODEL_OUTPUT_CAPS = {"listed-model": 16384}
        seen, _ = self._capture({"model": "listed-model"})
        self.assertEqual(seen[0], 16384)
        self.assertNotEqual(seen[0], NO_METADATA_FALLBACK)

    def test_unlisted_model_falls_back_to_the_default(self):
        boot._MODEL_OUTPUT_CAPS = {}
        seen, _ = self._capture({"model": "not-in-registry"})
        self.assertEqual(seen[0], NO_METADATA_FALLBACK)
        # A declared window is enough to lift the reservation off the floor.
        seen, _ = self._capture(
            {"model": "not-in-registry", "context_window": 128_000})
        self.assertEqual(seen[0], DECLARED_WINDOW_FALLBACK)

    def test_explicit_endpoint_max_tokens_outranks_the_published_cap(self):
        boot._MODEL_OUTPUT_CAPS = {"listed-model": 16384}
        seen, _ = self._capture({"model": "listed-model", "max_tokens": 99})
        self.assertEqual(seen[0], 99)

    def test_provider_stated_limit_is_honoured_rather_than_returned_as_text(self):
        # The exact shape OpenAI returns when the request overshoots.
        rejection = RuntimeError(
            "Error code: 400 - {'error': {'message': 'max_tokens is too large: "
            "32000. This model supports at most 16384 completion tokens, "
            "whereas you provided 32000.', 'type': 'invalid_request_error'}}")
        boot._MODEL_OUTPUT_CAPS = {}
        # The endpoint declares its window, so the first attempt asks for the
        # 32000 the rejection above quotes back.
        seen, text = self._capture(
            {"model": "stale-registry-model", "context_window": 128_000},
            raises=rejection)
        self.assertEqual(seen, [DECLARED_WINDOW_FALLBACK, 16384])
        self.assertEqual(text, "body")
        self.assertNotIn("Error calling", text)

    def test_unparseable_failure_still_surfaces(self):
        boot._MODEL_OUTPUT_CAPS = {}
        seen, text = self._capture({"model": "any"},
                                   raises=RuntimeError("connection reset"))
        self.assertEqual(len(seen), 1)
        self.assertIn("Error calling TestProvider API", text)


if __name__ == "__main__":
    unittest.main()
