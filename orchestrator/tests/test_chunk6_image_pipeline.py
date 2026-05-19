#!/usr/bin/env python3
"""Install Chunk 6 — image-pipeline mitigations tests.

Two mitigations are covered:

1. ``_strip_annotated_image_clauses`` appends a text-only override to
   the formatter's OUTPUT FORMAT GUIDANCE so a vision-incapable model
   doesn't hallucinate image-relative coordinates for ``annotated_image``
   envelopes. ``build_system_prompt_for_gear(step="formatter",
   endpoint_vision_capable=False)`` invokes it.

2. ``_images_for_endpoint`` gates raw image passthrough at non-analyst
   call sites (evaluator / reviser / verifier / consolidator). When the
   downstream endpoint is text-only, images are dropped — the analyst
   stage already runs the extraction fallback (image →
   spatial_representation text) upstream, and the extracted text rides
   in context_pkg.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from boot import (  # noqa: E402
    _images_for_endpoint,
    _strip_annotated_image_clauses,
    build_system_prompt_for_gear,
)


class TestImagesForEndpoint(unittest.TestCase):
    """Image passthrough gate for non-analyst stages."""

    def test_vision_capable_endpoint_passes_images(self):
        ep = {"id": "gpt-5", "vision_capable": True}
        self.assertEqual(_images_for_endpoint(["bytes"], ep), ["bytes"])

    def test_text_only_endpoint_drops_images(self):
        ep = {"id": "local-mlx-hermes-4-70b", "vision_capable": False}
        self.assertIsNone(_images_for_endpoint(["bytes"], ep))

    def test_missing_vision_capable_field_drops_images(self):
        # vision_capable absent → default False per safety
        ep = {"id": "unknown-model"}
        self.assertIsNone(_images_for_endpoint(["bytes"], ep))

    def test_none_endpoint_drops_images(self):
        self.assertIsNone(_images_for_endpoint(["bytes"], None))

    def test_none_images_stays_none(self):
        ep = {"id": "gpt-5", "vision_capable": True}
        self.assertIsNone(_images_for_endpoint(None, ep))

    def test_empty_list_preserved_when_vision_capable(self):
        # Edge case: caller passes []; preserved when capable, dropped when not
        ep_vision = {"id": "gpt-5", "vision_capable": True}
        ep_text = {"id": "text", "vision_capable": False}
        self.assertEqual(_images_for_endpoint([], ep_vision), [])
        self.assertIsNone(_images_for_endpoint([], ep_text))


class TestStripAnnotatedImageClauses(unittest.TestCase):
    """Text-only formatter override for annotated_image emission."""

    def test_appends_override(self):
        sample = (
            "Some guidance.\n\n"
            "11. Annotated visual overlay (when image attached). "
            "Emit annotated_image envelope...\n"
        )
        result = _strip_annotated_image_clauses(sample)
        # Original guidance preserved (caller will see both)
        self.assertIn("Annotated visual overlay", result)
        # Override appended at end
        self.assertIn("Text-only formatter override", result)
        self.assertIn("Do NOT emit `annotated_image`", result)

    def test_empty_input_returns_empty(self):
        self.assertEqual(_strip_annotated_image_clauses(""), "")
        # None handling — the function checks falsy
        self.assertFalse(bool(_strip_annotated_image_clauses("")))

    def test_override_only_appears_once(self):
        sample = "Some guidance with no image content."
        result = _strip_annotated_image_clauses(sample)
        # Override mentions "Text-only formatter override" exactly once
        self.assertEqual(result.count("Text-only formatter override"), 1)


class TestFormatterPromptGating(unittest.TestCase):
    """build_system_prompt_for_gear honors endpoint_vision_capable for the
    formatter step specifically."""

    def _ctx(self, mode_text: str):
        # Minimal context package the prompt builder needs.
        return {
            "mode_text": mode_text,
            "mode_name": "test-mode",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "web_rag": "",
            "inferred_items": "",
        }

    def _mode_with_format_guidance(self):
        return (
            "# Test Mode\n\n"
            "## OUTPUT FORMAT GUIDANCE\n\n"
            "Format the output as plain prose.\n\n"
            "11. Annotated visual overlay (when image attached). "
            "Emit annotated_image envelope with normalized coords.\n"
        )

    def test_vision_capable_formatter_sees_full_guidance(self):
        prompt = build_system_prompt_for_gear(
            self._ctx(self._mode_with_format_guidance()),
            slot="depth", step="formatter",
            endpoint_vision_capable=True,
        )
        self.assertIn("Annotated visual overlay", prompt)
        self.assertNotIn("Text-only formatter override", prompt)

    def test_text_only_formatter_gets_override(self):
        prompt = build_system_prompt_for_gear(
            self._ctx(self._mode_with_format_guidance()),
            slot="depth", step="formatter",
            endpoint_vision_capable=False,
        )
        # Original content still present (the model sees it but is told to ignore)
        self.assertIn("Annotated visual overlay", prompt)
        # Override telling the model to suppress envelope emission
        self.assertIn("Text-only formatter override", prompt)
        self.assertIn("Do NOT emit `annotated_image`", prompt)

    def test_non_formatter_steps_unaffected(self):
        # The gate only applies at step="formatter". Other steps don't
        # inject OUTPUT FORMAT GUIDANCE so the override is irrelevant.
        for step in ("analyst", "evaluator", "reviser", "verifier", "consolidator"):
            prompt = build_system_prompt_for_gear(
                self._ctx(self._mode_with_format_guidance()),
                slot="depth", step=step,
                endpoint_vision_capable=False,
            )
            self.assertNotIn(
                "Text-only formatter override", prompt,
                f"step={step} should not carry the formatter override",
            )

    def test_default_is_vision_capable(self):
        # Backward compat: callers that don't pass endpoint_vision_capable
        # get the pre-Chunk-6 behaviour (assume capable → no stripping).
        prompt = build_system_prompt_for_gear(
            self._ctx(self._mode_with_format_guidance()),
            slot="depth", step="formatter",
        )
        self.assertNotIn("Text-only formatter override", prompt)


if __name__ == "__main__":
    unittest.main()
