#!/usr/bin/env python3
"""Tests for orchestrator/local_model_discovery.py.

Covers per-config detection (vision capability, MoE classification,
parameter estimation from safetensors size), per-directory probe, full
directory scan, recommended-role rule table at boundaries, and the
refresh() round-trip that preserves commercial_models + top-level keys.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

from local_model_discovery import (  # noqa: E402
    ROLE_RULES,
    _is_moe,
    _is_vision_capable,
    _quant_bits,
    _recommended_roles,
    probe_model_dir,
    refresh,
    scan_models_dir,
)


def _make_fake_model_dir(
    root: Path,
    name: str,
    config: dict,
    safetensors_bytes: int = 1_000_000_000,
    safetensors_count: int = 1,
) -> Path:
    """Create a fake MLX model directory for tests."""
    model_dir = root / name
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text(json.dumps(config))
    # Create N empty safetensors files, sized to satisfy size checks.
    per_file = safetensors_bytes // safetensors_count
    for i in range(safetensors_count):
        path = model_dir / f"model-{i + 1:05d}-of-{safetensors_count:05d}.safetensors"
        with open(path, "wb") as f:
            f.truncate(per_file)
    return model_dir


# ----------------------------------------------------------------------
# Vision-capability detection
# ----------------------------------------------------------------------


class VisionDetection(unittest.TestCase):

    def test_vision_config_present(self):
        self.assertTrue(_is_vision_capable({"vision_config": {}}))

    def test_image_token_id_at_top_level(self):
        self.assertTrue(_is_vision_capable({"image_token_id": 248056}))

    def test_image_token_index_at_top_level(self):
        # Mistral convention.
        self.assertTrue(_is_vision_capable({"image_token_index": 10}))

    def test_image_token_id_in_text_config(self):
        self.assertTrue(_is_vision_capable({
            "text_config": {"image_token_id": 248056}
        }))

    def test_conditional_generation_architecture(self):
        self.assertTrue(_is_vision_capable({
            "architectures": ["Qwen3_5ForConditionalGeneration"]
        }))

    def test_for_causal_lm_is_text_only(self):
        self.assertFalse(_is_vision_capable({
            "architectures": ["LlamaForCausalLM"]
        }))

    def test_empty_config_defaults_to_text_only(self):
        self.assertFalse(_is_vision_capable({}))


# ----------------------------------------------------------------------
# MoE detection
# ----------------------------------------------------------------------


class MoEDetection(unittest.TestCase):

    def test_num_experts_in_text_config(self):
        self.assertTrue(_is_moe({"text_config": {"num_experts": 128}}))

    def test_n_routed_experts_in_text_config(self):
        self.assertTrue(_is_moe({"text_config": {"n_routed_experts": 128}}))

    def test_moe_intermediate_size_in_text_config(self):
        self.assertTrue(_is_moe({"text_config": {"moe_intermediate_size": 1408}}))

    def test_moe_in_model_type(self):
        self.assertTrue(_is_moe({"model_type": "qwen3_5_moe"}))

    def test_moe_in_architecture_name(self):
        self.assertTrue(_is_moe({
            "architectures": ["Glm4vMoeForConditionalGeneration"]
        }))

    def test_dense_model_is_not_moe(self):
        self.assertFalse(_is_moe({
            "model_type": "mistral3",
            "architectures": ["Mistral3ForConditionalGeneration"],
            "text_config": {"hidden_size": 12288},
        }))


# ----------------------------------------------------------------------
# Quantization bits
# ----------------------------------------------------------------------


class QuantBits(unittest.TestCase):

    def test_default_when_missing(self):
        self.assertEqual(_quant_bits({}), 4)

    def test_from_quantization_block(self):
        self.assertEqual(_quant_bits({"quantization": {"bits": 8}}), 8)

    def test_from_quantization_config_block(self):
        self.assertEqual(_quant_bits({"quantization_config": {"bits": 3}}), 3)


# ----------------------------------------------------------------------
# Recommended-roles rule table
# ----------------------------------------------------------------------


class RecommendedRoles(unittest.TestCase):

    def test_4b_classification_only(self):
        self.assertEqual(_recommended_roles(4), ["classification"])

    def test_just_under_5b_still_classification(self):
        self.assertEqual(_recommended_roles(4.99), ["classification"])

    def test_5b_jumps_to_small_fast_band(self):
        # 5.0 falls into the 5-15B band (NOT <5B).
        roles = _recommended_roles(5)
        self.assertIn("classification", roles)
        self.assertIn("sidebar", roles)

    def test_15b_jumps_to_mid_fast_band(self):
        roles = _recommended_roles(15)
        self.assertIn("sidebar", roles)
        self.assertNotIn("classification", roles)

    def test_40b_is_large_analyst(self):
        roles = _recommended_roles(40)
        self.assertEqual(roles, ["breadth", "depth", "evaluator", "consolidator"])

    def test_122b_is_large_analyst(self):
        roles = _recommended_roles(122)
        self.assertEqual(roles, ["breadth", "depth", "evaluator", "consolidator"])

    def test_rule_table_is_sorted_and_complete(self):
        # Each rule's threshold must be greater than the previous.
        thresholds = [r[0] for r in ROLE_RULES]
        self.assertEqual(thresholds, sorted(thresholds))
        # Last threshold must be inf so every model size is covered.
        self.assertEqual(thresholds[-1], float("inf"))


# ----------------------------------------------------------------------
# probe_model_dir
# ----------------------------------------------------------------------


class ProbeModelDir(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_none_when_no_config(self):
        empty = self.root / "no_config"
        empty.mkdir()
        self.assertIsNone(probe_model_dir(empty))

    def test_returns_none_when_no_safetensors(self):
        d = self.root / "no_weights"
        d.mkdir()
        (d / "config.json").write_text("{}")
        self.assertIsNone(probe_model_dir(d))

    def test_returns_none_when_malformed_config(self):
        d = _make_fake_model_dir(
            self.root, "bad_config", {},
            safetensors_bytes=1_000_000,
        )
        (d / "config.json").write_text("{not json")
        self.assertIsNone(probe_model_dir(d))

    def test_dense_text_only_model(self):
        d = _make_fake_model_dir(
            self.root, "llama-7b-4bit",
            {
                "architectures": ["LlamaForCausalLM"],
                "model_type": "llama",
                "quantization": {"bits": 4},
                "text_config": {"hidden_size": 4096},
            },
            safetensors_bytes=3_500_000_000,
        )
        entry = probe_model_dir(d)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["type"], "dense")
        self.assertFalse(entry["vision_capable"])
        # At 4-bit, 3.5GB → ~7B params → 5-15B band.
        self.assertIn("sidebar", entry["recommended_roles"])

    def test_dense_vision_model_qwen3_5(self):
        d = _make_fake_model_dir(
            self.root, "qwen3.5-9b-mlx-4bit",
            {
                "architectures": ["Qwen3_5ForConditionalGeneration"],
                "model_type": "qwen3_5",
                "image_token_id": 248056,
                "quantization": {"bits": 4},
                "text_config": {"hidden_size": 4096},
            },
            safetensors_bytes=5_000_000_000,
        )
        entry = probe_model_dir(d)
        self.assertEqual(entry["type"], "dense")
        self.assertTrue(entry["vision_capable"])

    def test_moe_vision_model_with_active_params_in_name(self):
        d = _make_fake_model_dir(
            self.root, "qwen3.5-122b-a10b-mxfp4",
            {
                "architectures": ["Qwen3_5MoeForConditionalGeneration"],
                "model_type": "qwen3_5_moe",
                "image_token_id": 248056,
                "quantization": {"bits": 4},
                "text_config": {
                    "hidden_size": 4096,
                    "num_experts": 128,
                    "num_experts_per_tok": 8,
                },
            },
            safetensors_bytes=60_000_000_000,
        )
        entry = probe_model_dir(d)
        self.assertEqual(entry["type"], "moe")
        self.assertTrue(entry["vision_capable"])
        # "a10b" in directory name → active_params should be 10.
        self.assertEqual(entry["active_params_per_token"], 10)
        # Large model → large-analyst roles.
        self.assertEqual(
            entry["recommended_roles"],
            ["breadth", "depth", "evaluator", "consolidator"],
        )

    def test_moe_without_active_params_in_name_falls_back_to_config(self):
        d = _make_fake_model_dir(
            self.root, "glm-4.6v-mxfp4",
            {
                "architectures": ["Glm4vMoeForConditionalGeneration"],
                "model_type": "glm4v_moe",
                "image_token_id": 151363,
                "quantization": {"bits": 4},
                "text_config": {
                    "num_experts": 128,
                    "num_experts_per_tok": 8,
                    "moe_intermediate_size": 1408,
                },
            },
            safetensors_bytes=55_000_000_000,
        )
        entry = probe_model_dir(d)
        self.assertEqual(entry["type"], "moe")
        # 8 of 128 experts active → ratio 0.0625 → 0.7×0.0625 + 0.3 = ~0.344
        # Total at 4-bit from 55GB = ~110B. Active ≈ 110 × 0.344 ≈ 38.
        # Assertion: smaller than total but greater than zero.
        self.assertGreater(entry["active_params_per_token"], 0)
        self.assertLess(entry["active_params_per_token"], 110)

    def test_id_slug_is_kebab_case_of_directory_name(self):
        d = _make_fake_model_dir(
            self.root, "Foo_Bar-Baz",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=1_000_000_000,
        )
        entry = probe_model_dir(d)
        self.assertEqual(entry["id"], "local-mlx-foo-bar-baz")


# ----------------------------------------------------------------------
# scan_models_dir
# ----------------------------------------------------------------------


class ScanModelsDir(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_empty_for_missing_directory(self):
        self.assertEqual(scan_models_dir(self.root / "nope"), [])

    def test_skips_non_model_subdirectories(self):
        # diffusers / whisper / loras shouldn't show up — they lack
        # MLX config.json files.
        for name in ("diffusers", "whisper", "loras"):
            (self.root / name).mkdir()
        # And one real model.
        _make_fake_model_dir(
            self.root, "qwen3.5-9b-mlx-4bit",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=2_000_000_000,
        )
        entries = scan_models_dir(self.root)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "local-mlx-qwen3.5-9b-mlx-4bit")

    def test_returns_entries_sorted_by_ram(self):
        _make_fake_model_dir(
            self.root, "big",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=60_000_000_000,
        )
        _make_fake_model_dir(
            self.root, "small",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=2_000_000_000,
        )
        entries = scan_models_dir(self.root)
        self.assertEqual(len(entries), 2)
        self.assertLess(entries[0]["ram_gb"], entries[1]["ram_gb"])


# ----------------------------------------------------------------------
# refresh() — preserves top-level keys; safety on empty discovery
# ----------------------------------------------------------------------


class RefreshRoundTrip(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.models_dir = self.root / "models"
        self.models_dir.mkdir()
        self.models_json = self.root / "models.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_models_json(self, doc: dict) -> None:
        self.models_json.write_text(json.dumps(doc, indent=2))

    def test_preserves_commercial_models_and_top_level_keys(self):
        self._seed_models_json({
            "overhead_reservation_gb": 8,
            "local_model_directory": "~/ora/models/",
            "_vision_capable_defaults": "...",
            "local_models": [
                {"id": "stale-entry-to-be-replaced", "path": "/gone"}
            ],
            "commercial_models": [
                {"id": "anthropic-claude", "provider": "anthropic"},
                {"id": "openai-gpt-5", "provider": "openai"},
            ],
        })
        _make_fake_model_dir(
            self.models_dir, "qwen-test",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=2_000_000_000,
        )
        result = refresh(
            models_json=self.models_json,
            models_dir=self.models_dir,
            write=True,
        )
        self.assertTrue(result["wrote"])
        self.assertEqual(len(result["discovered"]), 1)

        loaded = json.loads(self.models_json.read_text())
        self.assertEqual(loaded["overhead_reservation_gb"], 8)
        self.assertEqual(loaded["local_model_directory"], "~/ora/models/")
        self.assertEqual(loaded["_vision_capable_defaults"], "...")
        # commercial_models block untouched.
        self.assertEqual(len(loaded["commercial_models"]), 2)
        self.assertEqual(loaded["commercial_models"][0]["id"], "anthropic-claude")
        # local_models now contains the discovered entry, not the stale one.
        self.assertEqual(len(loaded["local_models"]), 1)
        self.assertEqual(loaded["local_models"][0]["id"], "local-mlx-qwen-test")

    def test_does_not_blank_file_when_models_dir_empty(self):
        original_locals = [{"id": "manual-entry", "vision_capable": True}]
        self._seed_models_json({
            "overhead_reservation_gb": 8,
            "local_models": original_locals,
            "commercial_models": [],
        })
        # Empty models directory.
        result = refresh(
            models_json=self.models_json,
            models_dir=self.models_dir,
            write=True,
        )
        self.assertEqual(result["discovered"], [])
        self.assertFalse(result["wrote"])
        # File preserves original local_models.
        loaded = json.loads(self.models_json.read_text())
        self.assertEqual(loaded["local_models"], original_locals)

    def test_dry_run_returns_diff_without_writing(self):
        self._seed_models_json({
            "local_models": [{"id": "old-model"}],
            "commercial_models": [],
        })
        _make_fake_model_dir(
            self.models_dir, "new-model",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=2_000_000_000,
        )
        # Don't pass write=True.
        result = refresh(
            models_json=self.models_json,
            models_dir=self.models_dir,
            write=False,
        )
        self.assertFalse(result["wrote"])
        self.assertEqual(result["added"], ["local-mlx-new-model"])
        self.assertEqual(result["removed"], ["old-model"])
        # File should be unchanged.
        loaded = json.loads(self.models_json.read_text())
        self.assertEqual(loaded["local_models"], [{"id": "old-model"}])


if __name__ == "__main__":
    unittest.main()
