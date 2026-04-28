#!/usr/bin/env python3
"""
WP-4.3 — vision extraction prompt + response parser tests.

Runs under stdlib ``unittest`` — no pytest dependency. Invoke::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

Scope:
* ``EXTRACTION_PROMPT`` contains the required structural instructions.
* Response parser handles clean JSON, markdown-fenced JSON, preamble
  prose, trailing commas, and malformed JSON (→ parse_errors).
* Schema repair pass synthesizes missing ``id`` (via label slug) and
  defaults missing ``position`` to ``[0.5, 0.5]``.
* Low-confidence response is still returned but flagged with
  ``W_LOW_CONFIDENCE_EXTRACTION``.
* Extraction failure unparseable after repair → ``spatial_representation
  is None`` and ``parse_errors`` populated.
* Integration: ``route_for_image_input`` calls the extractor, stashes
  result on context_pkg, and ``build_system_prompt_for_gear`` emits a
  ``=== VISION EXTRACTION ===`` block.
* Backward compatibility: text-only / image-less requests flow unchanged.
* ``no_vision_available`` path: extraction never runs.

Model calls are mocked via ``unittest.mock.patch`` so tests stay fast
and deterministic.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(WORKSPACE / "server"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _clean_response_json() -> str:
    """A well-formed response the model might return."""
    return json.dumps({
        "entities": [
            {"id": "e-1", "position": [0.2, 0.35], "label": "Alpha node", "confidence": 0.9},
            {"id": "e-2", "position": [0.6, 0.35], "label": "Beta node", "confidence": 0.8},
        ],
        "relationships": [
            {"source": "e-1", "target": "e-2", "type": "causal", "confidence": 0.85},
        ],
    })


def _fenced_response_json() -> str:
    """The same JSON wrapped in a markdown code fence — common model slip."""
    return (
        "Here is the JSON:\n"
        "```json\n"
        + _clean_response_json()
        + "\n```"
    )


def _low_confidence_json() -> str:
    """Clean JSON with per-entity confidence well below the 0.5 threshold."""
    return json.dumps({
        "entities": [
            {"id": "e-1", "position": [0.2, 0.35], "label": "maybe?", "confidence": 0.1},
            {"id": "e-2", "position": [0.6, 0.35], "label": "perhaps?", "confidence": 0.15},
        ],
    })


def _missing_id_json() -> str:
    """Entity missing ``id`` — a repair-pass target."""
    return json.dumps({
        "entities": [
            {"position": [0.2, 0.35], "label": "Alpha Node", "confidence": 0.9},
        ],
    })


def _missing_position_json() -> str:
    """Entity missing ``position`` — a repair-pass target."""
    return json.dumps({
        "entities": [
            {"id": "e-1", "label": "Solo", "confidence": 0.9},
        ],
    })


def _malformed_json() -> str:
    """Broken JSON that survives neither parse nor repair."""
    return "this is not JSON at all"


def _trailing_comma_json() -> str:
    """JSON with a trailing comma — common LLM flaw, the cleaner fixes it."""
    return '{"entities": [{"id": "e-1", "position": [0.5, 0.5], "label": "One", "confidence": 0.9},],}'


def _fake_endpoint(endpoint_id: str = "test-vision-api") -> dict:
    return {
        "id": endpoint_id,
        "type": "api",
        "service": "claude",
        "display_name": "Test Vision API",
        "vision_capable": True,
    }


def _png_bytes() -> bytes:
    """Minimal bytes that look like a PNG — enough for base64 encoding."""
    return b"\x89PNG\r\n\x1a\nFAKE-PNG"


# ---------------------------------------------------------------------------
# Prompt — the constant must contain the load-bearing instructions.
# ---------------------------------------------------------------------------


class ExtractionPromptShapeTests(unittest.TestCase):
    """The prompt constant is part of our observable surface — assert
    its core structure so we know when it drifts."""

    def setUp(self) -> None:
        from visual_extraction import EXTRACTION_PROMPT
        self.prompt = EXTRACTION_PROMPT

    def test_prompt_demands_json_only_output(self) -> None:
        self.assertIn("ONLY the JSON", self.prompt)

    def test_prompt_forbids_markdown_fences(self) -> None:
        self.assertIn("markdown fences", self.prompt)

    def test_prompt_names_entity_required_fields(self) -> None:
        # id, position, label, confidence all need to appear.
        self.assertIn("id", self.prompt)
        self.assertIn("position", self.prompt)
        self.assertIn("label", self.prompt)
        self.assertIn("confidence", self.prompt)

    def test_prompt_specifies_position_normalization(self) -> None:
        self.assertIn("NORMALIZED", self.prompt)
        self.assertIn("[0.0, 1.0]", self.prompt)

    def test_prompt_lists_relationship_types(self) -> None:
        self.assertIn("causal", self.prompt)
        self.assertIn("associative", self.prompt)
        self.assertIn("hierarchical", self.prompt)
        self.assertIn("temporal", self.prompt)

    def test_prompt_discusses_image_type_strategy(self) -> None:
        # Diagram / text / ambiguous — the three branches we documented.
        self.assertIn("Diagram", self.prompt)
        self.assertIn("Text", self.prompt)
        self.assertIn("Ambiguous", self.prompt)


# ---------------------------------------------------------------------------
# Response parsing — clean JSON, fenced JSON, malformed, trailing commas.
# ---------------------------------------------------------------------------


def _run_extract_with_stubbed_response(raw_response: str,
                                       confidence_threshold: float = 0.5):
    """Call ``extract_spatial_from_image`` with the model call stubbed to
    return ``raw_response``. Uses a real tempfile on disk for the image
    so ``_load_image_as_attachment`` runs end-to-end.
    """
    import visual_extraction  # noqa: WPS433

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    try:
        tmp.write(_png_bytes())
        tmp.flush()
        tmp.close()
        with mock.patch.object(
            visual_extraction, "_invoke_vision_model",
            return_value=raw_response,
        ):
            return visual_extraction.extract_spatial_from_image(
                tmp.name, _fake_endpoint(), confidence_threshold=confidence_threshold,
            )
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


class ResponseParsingTests(unittest.TestCase):
    """Assert the parser handles the most common LLM response shapes."""

    def test_clean_json_parses_cleanly(self) -> None:
        result = _run_extract_with_stubbed_response(_clean_response_json())
        self.assertIsNotNone(result.spatial_representation)
        self.assertEqual(len(result.spatial_representation["entities"]), 2)
        # No error-level parse_errors expected.
        hard_errors = [e for e in result.parse_errors
                       if not e.startswith("W_") and "W_" not in e]
        self.assertEqual(hard_errors, [])
        # Confidence = mean of [0.9, 0.8] = 0.85
        self.assertAlmostEqual(result.confidence, 0.85, places=2)
        self.assertEqual(result.extractor_model, "test-vision-api")

    def test_markdown_fenced_response_is_stripped(self) -> None:
        result = _run_extract_with_stubbed_response(_fenced_response_json())
        self.assertIsNotNone(result.spatial_representation)
        self.assertEqual(len(result.spatial_representation["entities"]), 2)

    def test_trailing_comma_is_cleaned(self) -> None:
        result = _run_extract_with_stubbed_response(_trailing_comma_json())
        self.assertIsNotNone(result.spatial_representation,
                             f"expected parse success; got errors: {result.parse_errors}")
        self.assertEqual(len(result.spatial_representation["entities"]), 1)

    def test_malformed_json_populates_parse_errors(self) -> None:
        result = _run_extract_with_stubbed_response(_malformed_json())
        self.assertIsNone(result.spatial_representation)
        self.assertTrue(len(result.parse_errors) > 0)
        # Raw response is kept for debugging.
        self.assertEqual(result.raw_response, _malformed_json())

    def test_empty_response_fails_cleanly(self) -> None:
        result = _run_extract_with_stubbed_response("")
        self.assertIsNone(result.spatial_representation)
        self.assertTrue(any("empty" in e.lower() for e in result.parse_errors))

    def test_error_string_response_short_circuits(self) -> None:
        """When call_model returns ``[Error ...]``, we treat it as a
        failed extraction rather than attempting to parse."""
        result = _run_extract_with_stubbed_response("[Error calling API: timeout]")
        self.assertIsNone(result.spatial_representation)
        self.assertTrue(any("model returned error" in e.lower() for e in result.parse_errors))


# ---------------------------------------------------------------------------
# Schema repair pass — synthesized ids, defaulted positions.
# ---------------------------------------------------------------------------


class SchemaRepairTests(unittest.TestCase):
    """Assert the single-pass repair fixes the two common mistakes."""

    def test_missing_id_synthesized_from_label(self) -> None:
        result = _run_extract_with_stubbed_response(_missing_id_json())
        self.assertIsNotNone(result.spatial_representation,
                             f"repair should have succeeded: {result.parse_errors}")
        ent = result.spatial_representation["entities"][0]
        # Slug of "Alpha Node" → "alpha-node"
        self.assertEqual(ent["id"], "alpha-node")
        self.assertTrue(any("synthesized" in e for e in result.parse_errors))

    def test_missing_position_defaulted_to_centre(self) -> None:
        result = _run_extract_with_stubbed_response(_missing_position_json())
        self.assertIsNotNone(result.spatial_representation,
                             f"repair should have succeeded: {result.parse_errors}")
        ent = result.spatial_representation["entities"][0]
        self.assertEqual(ent["position"], [0.5, 0.5])
        self.assertTrue(any("position defaulted" in e for e in result.parse_errors))

    def test_unrepairable_extraction_returns_none(self) -> None:
        """Entity with no label AND a broken relationship ref → validator
        still fails after repair → spatial_representation is None."""
        bad = json.dumps({
            "entities": [
                {"id": "e-1", "position": [0.5, 0.5], "label": "A"},
            ],
            "relationships": [
                {"source": "e-1", "target": "e-GHOST", "type": "causal"},
            ],
        })
        result = _run_extract_with_stubbed_response(bad)
        # Repair only fixes entity ids/positions/labels — unresolved
        # relationship refs remain → schema fails after repair.
        self.assertIsNone(result.spatial_representation)
        self.assertTrue(any("schema" in e.lower() for e in result.parse_errors))


# ---------------------------------------------------------------------------
# Confidence thresholding — low-confidence flagged but still returned.
# ---------------------------------------------------------------------------


class LowConfidenceFlaggingTests(unittest.TestCase):

    def test_low_confidence_still_returned_with_warning(self) -> None:
        result = _run_extract_with_stubbed_response(
            _low_confidence_json(), confidence_threshold=0.5,
        )
        # The extraction is NOT None — caller decides what to do.
        self.assertIsNotNone(result.spatial_representation)
        self.assertEqual(len(result.spatial_representation["entities"]), 2)
        # Mean confidence = 0.125 — well below the 0.5 threshold.
        self.assertLess(result.confidence, 0.5)
        # The warning code must be present in parse_errors.
        self.assertTrue(
            any("W_LOW_CONFIDENCE_EXTRACTION" in e for e in result.parse_errors),
            f"expected W_LOW_CONFIDENCE_EXTRACTION; got: {result.parse_errors}",
        )

    def test_high_confidence_no_warning(self) -> None:
        result = _run_extract_with_stubbed_response(
            _clean_response_json(), confidence_threshold=0.5,
        )
        self.assertGreaterEqual(result.confidence, 0.5)
        self.assertFalse(
            any("W_LOW_CONFIDENCE_EXTRACTION" in e for e in result.parse_errors),
        )


# ---------------------------------------------------------------------------
# Image-loading edge cases
# ---------------------------------------------------------------------------


class ImageLoadingTests(unittest.TestCase):

    def test_missing_image_file_produces_parse_error(self) -> None:
        from visual_extraction import extract_spatial_from_image
        result = extract_spatial_from_image(
            "/tmp/nonexistent/definitely/not/a/real/image.png",
            _fake_endpoint(),
        )
        self.assertIsNone(result.spatial_representation)
        self.assertTrue(any("image load failed" in e.lower()
                            for e in result.parse_errors))

    def test_extraction_prompt_override(self) -> None:
        """When the endpoint carries ``extraction_prompt_override``, the
        override string is passed to ``_invoke_vision_model`` in place of
        the default prompt."""
        import visual_extraction  # noqa: WPS433

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            tmp.write(_png_bytes())
            tmp.flush()
            tmp.close()
            ep = _fake_endpoint()
            ep["extraction_prompt_override"] = "CUSTOM PROMPT — just the entities."
            captured = {}

            def fake_invoke(prompt, image_attachment, endpoint):
                captured["prompt"] = prompt
                return _clean_response_json()

            with mock.patch.object(visual_extraction, "_invoke_vision_model",
                                   side_effect=fake_invoke):
                result = visual_extraction.extract_spatial_from_image(tmp.name, ep)

            self.assertEqual(captured["prompt"],
                             "CUSTOM PROMPT — just the entities.")
            self.assertIsNotNone(result.spatial_representation)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Integration — route_for_image_input fills context_pkg; system prompt
# picks it up.
# ---------------------------------------------------------------------------


class RouteAndBuildSystemPromptIntegrationTests(unittest.TestCase):
    """End-to-end: routing gate → extractor stub → prompt injection."""

    def _mock_routing_config(self) -> dict:
        """Minimal routing-config with a text-only downstream and a
        vision-capable extractor in the preferred bucket."""
        return {
            "_schema_version": 2,
            "vision_extraction": {
                "enabled": True,
                "preferred_extractor_bucket": "premium",
                "fallback_extractor_bucket": "fast",
            },
            "endpoints": [
                {
                    "id": "api-vision",
                    "type": "api",
                    "status": "active",
                    "enabled": True,
                    "vision_capable": True,
                    "display_name": "Test Vision API",
                },
                {
                    "id": "local-text",
                    "type": "local",
                    "status": "active",
                    "enabled": True,
                    "vision_capable": False,
                    "display_name": "Local Text-Only",
                },
            ],
            "buckets": {
                "premium": ["api-vision"],
                "fast": [],
            },
        }

    def test_route_fills_vision_extraction_result(self) -> None:
        """Extractor selection + extraction attempt → context_pkg populated."""
        import visual_extraction  # noqa: WPS433
        from boot import route_for_image_input

        fake_result = visual_extraction.ExtractionResult(
            spatial_representation={
                "entities": [
                    {"id": "e-1", "position": [0.2, 0.35],
                     "label": "Alpha node", "confidence": 0.9},
                    {"id": "e-2", "position": [0.6, 0.35],
                     "label": "Beta node", "confidence": 0.8},
                ],
                "relationships": [
                    {"source": "e-1", "target": "e-2", "type": "causal",
                     "confidence": 0.85},
                ],
            },
            confidence=0.85,
            raw_response="...",
            parse_errors=[],
            extractor_model="api-vision",
        )

        ctx = {"image_path": "/abs/path/fake.png"}
        downstream = {"id": "local-text", "vision_capable": False}
        rc = self._mock_routing_config()

        with mock.patch.object(visual_extraction, "extract_spatial_from_image",
                               return_value=fake_result) as mocked:
            eff, out_ctx = route_for_image_input(ctx, downstream, routing_config=rc)

        # The extractor was called with the image path + extractor dict.
        self.assertTrue(mocked.called)
        args, _ = mocked.call_args
        self.assertEqual(args[0], "/abs/path/fake.png")
        self.assertEqual(args[1]["id"], "api-vision")

        # Result landed on context_pkg.
        self.assertEqual(out_ctx["vision_extraction_result"],
                         fake_result.spatial_representation)
        # Metadata is preserved.
        meta = out_ctx["vision_extraction_meta"]
        self.assertEqual(meta["extractor_model"], "api-vision")
        self.assertAlmostEqual(meta["confidence"], 0.85, places=2)

    def test_build_system_prompt_injects_vision_extraction(self) -> None:
        """``build_system_prompt_for_gear`` serializes the vision extraction
        result into a ``=== VISION EXTRACTION ===`` fenced block."""
        from boot import build_system_prompt_for_gear

        ctx = {
            "mode_text": "# Fake Mode\n",
            "mode_name": "systems_dynamics",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "rag_utilization": "",
            "vision_extraction_result": {
                "entities": [
                    {"id": "e-1", "position": [0.2, 0.35],
                     "label": "Alpha node", "confidence": 0.9},
                    {"id": "e-2", "position": [0.6, 0.35],
                     "label": "Beta node", "confidence": 0.8},
                ],
                "relationships": [
                    {"source": "e-1", "target": "e-2", "type": "causal"},
                ],
            },
            "vision_extraction_meta": {
                "extractor_model": "api-vision",
                "confidence": 0.85,
                "parse_errors": [],
            },
        }
        prompt = build_system_prompt_for_gear(ctx, slot="breadth")

        self.assertIn("=== VISION EXTRACTION ===", prompt)
        self.assertIn("=== END VISION EXTRACTION ===", prompt)
        # Provenance line names the extractor + confidence.
        self.assertIn("api-vision", prompt)
        self.assertIn("0.85", prompt)
        # Entity line matches the WP-3.3 serializer format.
        self.assertIn("e-1 at [0.200, 0.350]: Alpha node", prompt)
        self.assertIn("e-1 --(causal)--> e-2", prompt)

    def test_build_system_prompt_omits_vision_block_when_absent(self) -> None:
        """Text-only / no-image requests leave the prompt unchanged."""
        from boot import build_system_prompt_for_gear
        ctx = {
            "mode_text": "# Fake Mode\n",
            "mode_name": "systems_dynamics",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "rag_utilization": "",
        }
        prompt = build_system_prompt_for_gear(ctx, slot="breadth")
        self.assertNotIn("=== VISION EXTRACTION ===", prompt)

    def test_build_system_prompt_omits_block_when_extraction_failed(self) -> None:
        """If extraction returned None (failure), no block is injected."""
        from boot import build_system_prompt_for_gear
        ctx = {
            "mode_text": "# Fake Mode\n",
            "mode_name": "systems_dynamics",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "rag_utilization": "",
            "vision_extraction_result": None,
            "vision_extraction_meta": {
                "extractor_model": "api-vision",
                "confidence": 0.0,
                "parse_errors": ["JSON decode failed"],
            },
        }
        prompt = build_system_prompt_for_gear(ctx, slot="breadth")
        self.assertNotIn("=== VISION EXTRACTION ===", prompt)

    def test_no_vision_available_skips_extraction(self) -> None:
        """When the routing gate sets no_vision_available=True, extraction
        is never called."""
        import visual_extraction  # noqa: WPS433
        from boot import route_for_image_input

        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "local-text", "vision_capable": False}
        # Empty buckets → no vision model anywhere.
        rc = self._mock_routing_config()
        rc["buckets"]["premium"] = []
        rc["buckets"]["fast"] = []

        with mock.patch.object(visual_extraction, "extract_spatial_from_image",
                               return_value=None) as mocked:
            eff, out_ctx = route_for_image_input(ctx, downstream, routing_config=rc)

        self.assertTrue(out_ctx.get("no_vision_available"))
        # Crucially: the extractor was never called.
        self.assertFalse(mocked.called)
        # The result key is NOT populated in this branch (distinct from
        # "extraction attempted but failed" — important for WP-4.4 UX).
        self.assertNotIn("vision_extraction_result", out_ctx)

    def test_text_only_request_is_unchanged_by_wp43(self) -> None:
        """No image → gate is a strict no-op; extraction never fires."""
        import visual_extraction  # noqa: WPS433
        from boot import route_for_image_input

        ctx = {"mode_name": "systems_dynamics", "gear": 3}
        before = dict(ctx)
        downstream = {"id": "local-text", "vision_capable": False}

        with mock.patch.object(visual_extraction, "extract_spatial_from_image",
                               return_value=None) as mocked:
            eff, out_ctx = route_for_image_input(
                ctx, downstream, routing_config=self._mock_routing_config(),
            )

        self.assertEqual(ctx, before)
        self.assertFalse(mocked.called)
        self.assertNotIn("vision_extraction_result", out_ctx)

    def test_vision_capable_downstream_skips_extraction(self) -> None:
        """When downstream already handles vision, no extractor runs."""
        import visual_extraction  # noqa: WPS433
        from boot import route_for_image_input

        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "api-vision", "vision_capable": True}

        with mock.patch.object(visual_extraction, "extract_spatial_from_image",
                               return_value=None) as mocked:
            eff, out_ctx = route_for_image_input(
                ctx, downstream, routing_config=self._mock_routing_config(),
            )

        self.assertTrue(out_ctx.get("vision_direct_pass"))
        self.assertFalse(mocked.called)

    def test_extraction_exception_is_failopen(self) -> None:
        """If the extractor raises, the gate logs and sets the key to None
        — pipeline must not crash."""
        import visual_extraction  # noqa: WPS433
        from boot import route_for_image_input

        ctx = {"image_path": "/abs/img.png"}
        downstream = {"id": "local-text", "vision_capable": False}

        def _explode(*a, **k):
            raise RuntimeError("vision model on fire")

        with mock.patch.object(visual_extraction, "extract_spatial_from_image",
                               side_effect=_explode):
            eff, out_ctx = route_for_image_input(
                ctx, downstream, routing_config=self._mock_routing_config(),
            )

        # Pipeline continues; key is set to None so downstream knows
        # extraction was attempted and failed.
        self.assertIs(eff, downstream)
        self.assertIsNone(out_ctx.get("vision_extraction_result"))


if __name__ == "__main__":
    unittest.main()
