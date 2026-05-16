"""Tests for slot-inheritance resolution + OpenRouter failure-signal mapping.

Image Style Spec §5.8.1 v2.0 (2026-05-13) introduced:

  1. ``capability_registry.resolve_slot_inheritance()`` — materializes
     ``inherits`` / ``append_fallback`` / ``prepend_fallback`` directives
     at config-load time so the runtime sees only fully-explicit
     ``preferred`` + ``fallback`` lists.
  2. ``openrouter_images._classify_openrouter_failure()`` — translates
     arbitrary OpenRouter call exceptions into ``CapabilityError`` with
     one of the three cascade-trigger codes
     (``prompt_rejected``, ``quota_exceeded``, ``model_unavailable``).
     Load-bearing for the LoRA-backstop cascade: without it, an
     OpenRouter provider returning a dict with an ``error:`` string
     would silently stop the cascade and the LoRA would never be reached.

Both behaviors are verified here. The companion smoke tests for the
data-URL → bytes decode path are in ``test_openrouter_decode_image_url``.
"""

from __future__ import annotations

import os
import sys
import unittest
import urllib.error

# Import siblings via the standard ora orchestrator path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "integrations"))

from capability_registry import (  # noqa: E402
    CapabilityError,
    resolve_slot_inheritance,
)
import openrouter_images  # noqa: E402


class ResolveSlotInheritanceTests(unittest.TestCase):
    """resolve_slot_inheritance() — materialization rules per spec §5.8.1 v2.0."""

    def test_basic_inheritance_with_append(self):
        """Cartoon inherits parent's preferred + fallback; append goes at end.

        Note: image_generates_cartoon is in _HARDWIRED_SLOT_INHERITANCE,
        which excludes local-diffusers from the cartoon path per v2.2.
        Fixtures here use providers NOT in the exclusion list so the
        basic inheritance behavior is tested cleanly."""
        cfg = {"slots": {
            "image_generates": {
                "preferred": "openai-gpt-image-1",
                "fallback": ["gemini-2.5-flash-image"],
            },
            "image_generates_cartoon": {
                "inherits": "image_generates",
                "append_fallback": ["civitai-hector-lora-v1"],
            },
        }}
        resolve_slot_inheritance(cfg)
        cartoon = cfg["slots"]["image_generates_cartoon"]
        self.assertEqual(cartoon["preferred"], "openai-gpt-image-1")
        self.assertEqual(cartoon["fallback"], [
            "gemini-2.5-flash-image",
            "civitai-hector-lora-v1",
        ])
        # Directives stripped after resolution
        self.assertNotIn("inherits", cartoon)
        self.assertNotIn("append_fallback", cartoon)
        self.assertNotIn("exclude_inherited", cartoon)

    def test_publisher_added_openrouter_providers_flow_through(self):
        """If publisher adds OpenRouter providers to image_generates,
        the cartoon slot inherits them in order. local-diffusers (per
        v2.2 exclusion) is dropped from the cartoon chain — kept here
        in the fixture to exercise the exclusion alongside the inherit
        ordering."""
        cfg = {"slots": {
            "image_generates": {
                "preferred": "openrouter:openai/gpt-image-1",
                "fallback": [
                    "gemini-2.5-flash-image",
                    "openrouter:google/gemini-2.5-flash-image",
                    "local-diffusers",
                ],
            },
            "image_generates_cartoon": {
                "inherits": "image_generates",
                "append_fallback": ["civitai-hector-lora-v1"],
            },
        }}
        resolve_slot_inheritance(cfg)
        cartoon = cfg["slots"]["image_generates_cartoon"]
        self.assertEqual(cartoon["preferred"], "openrouter:openai/gpt-image-1")
        # local-diffusers is excluded per the hardwired v2.2 exclusion
        self.assertEqual(cartoon["fallback"], [
            "gemini-2.5-flash-image",
            "openrouter:google/gemini-2.5-flash-image",
            "civitai-hector-lora-v1",
        ])

    def test_child_preferred_override_wins_for_non_hardwired(self):
        """For slots NOT in the hardwired inheritance map, a child's
        explicit ``preferred`` overrides the parent's. (The cartoon slot
        is hardwired and intentionally ignores child-level preferred to
        keep UI-driven config rewrites from clobbering inheritance — see
        the hardwired-inheritance-wipes-stale-child-preferred test.)"""
        cfg = {"slots": {
            "custom_parent": {"preferred": "p1", "fallback": ["f1"]},
            "custom_child": {
                "inherits": "custom_parent",
                "preferred": "p2",
                "append_fallback": ["x"],
            },
        }}
        resolve_slot_inheritance(cfg)
        child = cfg["slots"]["custom_child"]
        self.assertEqual(child["preferred"], "p2")
        self.assertEqual(child["fallback"], ["f1", "x"])

    def test_local_diffusers_excluded_from_cartoon_chain(self):
        """v2.2 (2026-05-13): the hardwired inheritance for the cartoon
        slot excludes local-diffusers from the inherited fallback chain.
        SD 1.5 is a sensible last-resort for news photos but actively
        damages the cartoon path — its CLIP tokenizer truncates Hector's
        prompts at 77 tokens and its aesthetic vocabulary doesn't carry
        the Nast cross-hatch. Excluding it means the cascade walks past
        a failed cloud chain straight to the Hector LoRA (which IS
        trained on Hector's register), instead of stopping at a broken
        SD 1.5 render and never reaching the LoRA."""
        cfg = {"slots": {
            "image_generates": {
                "preferred": "openrouter:openai/gpt-5.4-image-2",
                "fallback": [
                    "openrouter:openai/gpt-5-image",
                    "openrouter:google/gemini-3-pro-image-preview",
                    "local-diffusers",
                ],
            },
        }}
        resolve_slot_inheritance(cfg)
        cartoon = cfg["slots"]["image_generates_cartoon"]
        # local-diffusers should NOT appear anywhere in the cartoon chain
        self.assertNotIn("local-diffusers", [cartoon["preferred"], *cartoon["fallback"]])
        # LoRA must still be at the end as the safety-net floor
        self.assertEqual(cartoon["fallback"][-1], "civitai-hector-lora-v1")
        # The other inherited providers should be present in order
        self.assertEqual(cartoon["fallback"], [
            "openrouter:openai/gpt-5-image",
            "openrouter:google/gemini-3-pro-image-preview",
            "civitai-hector-lora-v1",
        ])

    def test_local_diffusers_remains_in_news_chain(self):
        """The exclusion applies only to the cartoon path. local-diffusers
        stays in image_generates so news photos still have a local
        fallback when both cloud providers fail."""
        cfg = {"slots": {
            "image_generates": {
                "preferred": "gemini-2.5-flash-image",
                "fallback": ["local-diffusers"],
            },
        }}
        resolve_slot_inheritance(cfg)
        # News path unchanged
        self.assertEqual(cfg["slots"]["image_generates"]["fallback"],
                         ["local-diffusers"])
        # Cartoon path excludes local-diffusers
        self.assertNotIn("local-diffusers",
                         cfg["slots"]["image_generates_cartoon"]["fallback"])

    def test_excluded_preferred_falls_through_to_inherited_fallback(self):
        """If the parent's preferred is in the exclusion list, the child's
        effective preferred falls through to the first inherited (or
        appended) provider. Guards against the pathological case where
        the publisher sets local-diffusers as preferred for image_generates
        and expects the cartoon path to still function."""
        cfg = {"slots": {
            "image_generates": {
                "preferred": "local-diffusers",
                "fallback": ["gemini-2.5-flash-image"],
            },
        }}
        resolve_slot_inheritance(cfg)
        cartoon = cfg["slots"]["image_generates_cartoon"]
        # Parent's preferred was excluded → no effective preferred from parent
        self.assertIsNone(cartoon["preferred"])
        # Fallback chain still gets gemini + LoRA
        self.assertEqual(cartoon["fallback"],
                         ["gemini-2.5-flash-image", "civitai-hector-lora-v1"])

    def test_hardwired_inheritance_wipes_stale_child_preferred(self):
        """When the UI writes a standalone {preferred, fallback} block
        for image_generates_cartoon (the v1.9 shape, which the Visual
        settings panel keeps reverting to), the hardwired inheritance
        layer wipes those stale values so the parent's preferred wins.
        This is the load-bearing fix for the UI-clobbers-inheritance
        problem surfaced 2026-05-13."""
        cfg = {"slots": {
            "image_generates": {
                "preferred": "openrouter:google/gemini-3.1-flash-image-preview",
                "fallback": ["gemini-2.5-flash-image", "local-diffusers"],
            },
            # The shape the UI auto-saves — hardcoded preferred + bare
            # fallback, no inheritance directives. The hardwired layer
            # has to override this.
            "image_generates_cartoon": {
                "preferred": "openai-gpt-image-1",       # stale
                "fallback": ["civitai-hector-lora-v1"],  # stale
            },
        }}
        resolve_slot_inheritance(cfg)
        cartoon = cfg["slots"]["image_generates_cartoon"]
        self.assertEqual(
            cartoon["preferred"],
            "openrouter:google/gemini-3.1-flash-image-preview",
            "hardwired inheritance should pull preferred from image_generates",
        )
        self.assertEqual(cartoon["fallback"], [
            "gemini-2.5-flash-image",
            # local-diffusers excluded per v2.2 exclusion list
            "civitai-hector-lora-v1",  # always appended by hardwired layer
        ])

    def test_prepend_fallback_lands_before_inherited(self):
        cfg = {"slots": {
            "parent": {"preferred": "p", "fallback": ["a", "b"]},
            "child": {
                "inherits": "parent",
                "prepend_fallback": ["first"],
                "append_fallback": ["last"],
            },
        }}
        resolve_slot_inheritance(cfg)
        self.assertEqual(cfg["slots"]["child"]["fallback"],
                         ["first", "a", "b", "last"])

    def test_dedup_preserves_first_occurrence(self):
        """Duplicates in prepend/inherit/append collapse to first occurrence."""
        cfg = {"slots": {
            "parent": {"preferred": "p", "fallback": ["a", "b"]},
            "child": {
                "inherits": "parent",
                "prepend_fallback": ["a"],         # already in inherited
                "append_fallback": ["b", "lora"],  # b already in inherited
            },
        }}
        resolve_slot_inheritance(cfg)
        # 'a' is in prepend; comes first. Inherited 'a' is skipped. 'b'
        # comes from inherited (not append, since dedup preserves first).
        self.assertEqual(cfg["slots"]["child"]["fallback"],
                         ["a", "b", "lora"])

    def test_missing_parent_is_fail_soft(self):
        """Missing parent doesn't crash; child's append becomes the chain."""
        cfg = {"slots": {
            "child": {
                "inherits": "no_such_parent",
                "append_fallback": ["lora"],
            },
        }}
        resolve_slot_inheritance(cfg)
        self.assertEqual(cfg["slots"]["child"]["preferred"], None)
        self.assertEqual(cfg["slots"]["child"]["fallback"], ["lora"])

    def test_no_directives_no_op(self):
        """Slots without inheritance directives are left untouched."""
        cfg = {"slots": {
            "plain": {"preferred": "p", "fallback": ["a", "b"]},
        }}
        original = dict(cfg["slots"]["plain"])
        resolve_slot_inheritance(cfg)
        self.assertEqual(cfg["slots"]["plain"], original)

    def test_explicit_child_fallback_replaces_parent(self):
        """A child can opt out of the parent's chain entirely by declaring
        its own fallback list."""
        cfg = {"slots": {
            "parent": {"preferred": "p", "fallback": ["x", "y"]},
            "child": {
                "inherits": "parent",
                "fallback": [],
                "append_fallback": ["lora"],
            },
        }}
        resolve_slot_inheritance(cfg)
        # Inherited fallback ignored; only append survives
        self.assertEqual(cfg["slots"]["child"]["fallback"], ["lora"])
        # Preferred still inherited
        self.assertEqual(cfg["slots"]["child"]["preferred"], "p")

    def test_non_dict_slots_block_is_no_op(self):
        cfg = {"slots": "not a dict"}
        resolve_slot_inheritance(cfg)  # should not raise
        self.assertEqual(cfg, {"slots": "not a dict"})

    def test_returns_same_object(self):
        cfg = {"slots": {}}
        out = resolve_slot_inheritance(cfg)
        self.assertIs(out, cfg)


class OpenRouterFailureClassifierTests(unittest.TestCase):
    """openrouter_images._classify_openrouter_failure() — failure-signal
    mapping per Image Spec §5.8.1 v2.0."""

    SLOT = "image_generates_cartoon"

    def _assert_code(self, exc_msg, expected_code, *, exc_cls=Exception):
        err = openrouter_images._classify_openrouter_failure(
            exc_cls(exc_msg), slot=self.SLOT)
        self.assertIsInstance(err, CapabilityError)
        self.assertEqual(err.code, expected_code,
                         f"{exc_msg!r} → expected {expected_code}, got {err.code}")
        # All emitted errors must carry the slot context so capability_registry
        # knows which chain they belong to.
        self.assertEqual(err.slot, self.SLOT)

    def test_content_policy_keywords_to_prompt_rejected(self):
        self._assert_code(
            "Error 400: content_policy_violation",
            "prompt_rejected",
        )
        self._assert_code("safety filter blocked this prompt", "prompt_rejected")
        self._assert_code("This output violates our policy.", "prompt_rejected")
        self._assert_code("This content is not allowed.", "prompt_rejected")

    def test_rate_limit_to_quota_exceeded(self):
        self._assert_code("Error code: 429 rate_limit hit", "quota_exceeded")
        self._assert_code("insufficient_quota on your account", "quota_exceeded")
        self._assert_code("billing failure: out of credits", "quota_exceeded")

    def test_auth_and_not_found_to_model_unavailable(self):
        self._assert_code("HTTP 401 unauthorized", "model_unavailable")
        self._assert_code("403 forbidden", "model_unavailable")
        self._assert_code("404 model not found", "model_unavailable")

    def test_5xx_and_network_to_model_unavailable(self):
        self._assert_code("500 internal server error", "model_unavailable")
        self._assert_code("503 service unavailable", "model_unavailable")
        self._assert_code("Connection timed out after 60s", "model_unavailable")
        self._assert_code("Network unreachable", "model_unavailable")

    def test_unclassified_to_model_unavailable_so_cascade_walks(self):
        """Unknown error shapes must NOT fail-stop the cascade; they map
        to model_unavailable so the next provider gets a try."""
        self._assert_code("some entirely novel failure mode", "model_unavailable")

    def test_httperror_carries_status_code(self):
        """urllib.error.HTTPError exposes .code, which the classifier reads."""
        exc = urllib.error.HTTPError(
            url="https://openrouter.ai/api/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )
        err = openrouter_images._classify_openrouter_failure(exc, slot=self.SLOT)
        self.assertEqual(err.code, "quota_exceeded")


class OpenRouterDataUrlDecodeTests(unittest.TestCase):
    """openrouter_images._decode_image_url_to_bytes() — success-path normalization
    from data URL to raw bytes, so cartoon vectorization receives bytes
    matching the openai/gemini/civitai handler contract."""

    def test_base64_data_url_decodes_to_bytes(self):
        import base64
        payload = b"\x89PNG\r\n\x1a\n" + b"x" * 100  # fake PNG-ish bytes
        data_url = "data:image/png;base64," + base64.b64encode(payload).decode()
        out = openrouter_images._decode_image_url_to_bytes(data_url)
        self.assertEqual(out, payload)

    def test_jpeg_base64_data_url_decodes(self):
        import base64
        payload = b"\xff\xd8\xff\xe0" + b"y" * 50
        data_url = "data:image/jpeg;base64," + base64.b64encode(payload).decode()
        out = openrouter_images._decode_image_url_to_bytes(data_url)
        self.assertEqual(out, payload)

    def test_malformed_data_url_raises(self):
        with self.assertRaises(ValueError):
            openrouter_images._decode_image_url_to_bytes("data:not-a-url")

    def test_non_data_url_scheme_raises(self):
        with self.assertRaises(ValueError):
            openrouter_images._decode_image_url_to_bytes("ftp://x.example.com/foo.png")


if __name__ == "__main__":
    unittest.main()
