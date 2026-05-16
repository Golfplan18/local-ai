"""Tests for scripts/refresh-openrouter.py — specifically the
input_modalities extraction added 2026-05-16 so the picker UI can
filter for vision-capable models when configuring the
``slots.image_generates`` chain or any other vision-extraction-eligible
slot.

The live OpenRouter API isn't called here — ``_extract_input_modalities``,
``_normalize``, ``_group``, and ``build_catalog`` are all pure functions
of an input dict shape, so the tests pin the contract on synthetic
fixtures.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_SCRIPT_PATH = os.path.join(_REPO_ROOT, "scripts", "refresh-openrouter.py")


def _load_script_as_module():
    """Load scripts/refresh-openrouter.py as a module so we can test its
    functions without executing main()."""
    spec = importlib.util.spec_from_file_location(
        "refresh_openrouter", _SCRIPT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["refresh_openrouter"] = mod
    spec.loader.exec_module(mod)
    return mod


refresh = _load_script_as_module()


# Fixtures — three OpenRouter raw-entry shapes seen in practice:
# (1) explicit input_modalities array; (2) "modality" shorthand only;
# (3) neither present (old entries that should default to text).

ENTRY_EXPLICIT_INPUT = {
    "id": "openai/gpt-5-image",
    "name": "OpenAI: GPT-5 Image",
    "architecture": {
        "modality": "text+image->image",
        "input_modalities": ["text", "image"],
        "output_modalities": ["image", "text"],
        "tokenizer": "GPT",
    },
    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
    "top_provider": {"context_length": 128000, "max_completion_tokens": 4096},
    "description": "  Image generation with conditioning  ",
    "created": 1778963401,
}

ENTRY_SHORTHAND_ONLY = {
    "id": "anthropic/claude-opus-4-7",
    "name": "Anthropic: Claude Opus 4.7",
    "architecture": {
        "modality": "text+image->text",
        # NO input_modalities array — only the shorthand.
        "tokenizer": "Claude",
    },
    "pricing": {"prompt": "0.000015", "completion": "0.000075"},
    "top_provider": {"context_length": 200000},
    "created": 1778963000,
}

ENTRY_TEXT_ONLY = {
    "id": "qwen/qwen3.5-122b-a10b",
    "name": "Qwen: Qwen3.5-122B-A10B",
    "architecture": {
        "modality": "text->text",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
    },
    "pricing": {"prompt": "0.0", "completion": "0.0"},
    "top_provider": {"context_length": 131072},
    "created": 1778963200,
}

ENTRY_NO_ARCHITECTURE = {
    "id": "ancient/legacy-model",
    "name": "Ancient Legacy Model",
    # NO architecture field at all — an old entry.
    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
    "created": 1700000000,
}


class ExtractInputModalities(unittest.TestCase):
    def test_explicit_array_used_when_present(self):
        out = refresh._extract_input_modalities(ENTRY_EXPLICIT_INPUT)
        self.assertEqual(out, ["text", "image"])

    def test_falls_back_to_shorthand_when_array_missing(self):
        out = refresh._extract_input_modalities(ENTRY_SHORTHAND_ONLY)
        self.assertEqual(out, ["text", "image"])

    def test_text_only_explicit(self):
        out = refresh._extract_input_modalities(ENTRY_TEXT_ONLY)
        self.assertEqual(out, ["text"])

    def test_defaults_to_text_when_no_architecture(self):
        out = refresh._extract_input_modalities(ENTRY_NO_ARCHITECTURE)
        self.assertEqual(out, ["text"])

    def test_lowercases_array_entries(self):
        entry = {"architecture": {"input_modalities": ["TEXT", "Image"]}}
        out = refresh._extract_input_modalities(entry)
        self.assertEqual(out, ["text", "image"])

    def test_empty_array_falls_back(self):
        entry = {"architecture": {"input_modalities": [],
                                   "modality": "text+image->text"}}
        out = refresh._extract_input_modalities(entry)
        self.assertEqual(out, ["text", "image"])

    def test_only_lhs_of_arrow_used_for_shorthand(self):
        # ``text->text+image`` is image OUTPUT only; input is text.
        entry = {"architecture": {"modality": "text->text+image"}}
        out = refresh._extract_input_modalities(entry)
        self.assertEqual(out, ["text"])


class NormalizeAddsInputFields(unittest.TestCase):
    def test_normalized_entry_carries_input_modalities(self):
        n = refresh._normalize(ENTRY_EXPLICIT_INPUT)
        self.assertEqual(n["input_modalities"], ["text", "image"])
        self.assertTrue(n["accepts_image"])

    def test_text_only_model_has_accepts_image_false(self):
        n = refresh._normalize(ENTRY_TEXT_ONLY)
        self.assertEqual(n["input_modalities"], ["text"])
        self.assertFalse(n["accepts_image"])

    def test_shorthand_only_works(self):
        n = refresh._normalize(ENTRY_SHORTHAND_ONLY)
        self.assertEqual(n["input_modalities"], ["text", "image"])
        self.assertTrue(n["accepts_image"])


class GroupBuildsInputIndex(unittest.TestCase):
    def test_by_input_modality_groups_correctly(self):
        models = [
            refresh._normalize(ENTRY_EXPLICIT_INPUT),  # text + image
            refresh._normalize(ENTRY_SHORTHAND_ONLY),  # text + image
            refresh._normalize(ENTRY_TEXT_ONLY),       # text
            refresh._normalize(ENTRY_NO_ARCHITECTURE), # text
        ]
        # _ora_modality tag isn't set on the fixtures (skipped the merge
        # pass) — _classify_modality falls back to architecture inspection
        # or defaults to "text". That's fine for this test.
        groups = refresh._group(models)
        by_in = groups["by_input_modality"]

        self.assertIn("text",  by_in)
        self.assertIn("image", by_in)

        # All four accept text input.
        self.assertEqual(len(by_in["text"]), 4)
        # Two accept image input.
        self.assertEqual(len(by_in["image"]), 2)
        self.assertIn("openai/gpt-5-image",       by_in["image"])
        self.assertIn("anthropic/claude-opus-4-7", by_in["image"])
        self.assertNotIn("qwen/qwen3.5-122b-a10b", by_in["image"])


class BuildCatalogIntegrationShape(unittest.TestCase):
    def test_top_level_has_by_input_modality_alongside_existing_indices(self):
        raw = [ENTRY_EXPLICIT_INPUT, ENTRY_TEXT_ONLY]
        catalog = refresh.build_catalog(raw)
        # Existing indices preserved.
        self.assertIn("by_modality", catalog)
        self.assertIn("by_vendor",   catalog)
        # New index landed.
        self.assertIn("by_input_modality", catalog)
        self.assertIn("text",  catalog["by_input_modality"])
        self.assertIn("image", catalog["by_input_modality"])

    def test_per_model_carries_input_modalities_field(self):
        raw = [ENTRY_EXPLICIT_INPUT]
        catalog = refresh.build_catalog(raw)
        m = catalog["models"][0]
        self.assertIn("input_modalities", m)
        self.assertIn("accepts_image",    m)
        self.assertTrue(m["accepts_image"])


if __name__ == "__main__":
    unittest.main()
