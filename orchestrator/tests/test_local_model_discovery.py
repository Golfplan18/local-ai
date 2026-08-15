#!/usr/bin/env python3
"""Tests for orchestrator/local_model_discovery.py.

Covers per-config detection (vision capability, MoE classification,
parameter estimation from safetensors size), per-directory probe, full
directory scan, recommended-role rule table at boundaries, and the
refresh() round-trip that preserves commercial_models + top-level keys.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import local_model_discovery  # noqa: E402
from local_model_discovery import (  # noqa: E402
    LocalModelDeleteError,
    LocalModelDiscoveryError,
    ROLE_RULES,
    TRASH_BIN,
    _is_moe,
    _is_vision_capable,
    _quant_bits,
    _recommended_roles,
    move_model_to_trash,
    probe_model_dir,
    reconcile_static_local_endpoints,
    refresh,
    resolve_delete_target,
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

    def test_missing_directory_is_an_explicit_discovery_error(self):
        with self.assertRaises(LocalModelDiscoveryError):
            scan_models_dir(self.root / "nope")

    def test_unreadable_directory_is_an_explicit_discovery_error(self):
        with mock.patch.object(local_model_discovery.os, "access", return_value=False):
            with self.assertRaises(LocalModelDiscoveryError):
                scan_models_dir(self.root)

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
            routing_config=None,
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

    def test_readable_empty_directory_clears_inventory(self):
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
            routing_config=None,
            write=True,
        )
        self.assertEqual(result["discovered"], [])
        self.assertTrue(result["wrote"])
        loaded = json.loads(self.models_json.read_text())
        self.assertEqual(loaded["local_models"], [])

    def test_missing_directory_preserves_prior_inventory(self):
        original_locals = [{"id": "last-known-good"}]
        self._seed_models_json({
            "local_models": original_locals,
            "commercial_models": [{"id": "cloud"}],
        })
        self.models_dir.rmdir()

        with self.assertRaises(LocalModelDiscoveryError):
            refresh(
                models_json=self.models_json,
                models_dir=self.models_dir,
                routing_config=None,
                write=True,
            )

        loaded = json.loads(self.models_json.read_text())
        self.assertEqual(loaded["local_models"], original_locals)
        self.assertEqual(loaded["commercial_models"], [{"id": "cloud"}])

    def test_unreadable_directory_preserves_prior_inventory(self):
        original_locals = [{"id": "last-known-good"}]
        self._seed_models_json({"local_models": original_locals})

        with mock.patch.object(local_model_discovery.os, "access", return_value=False):
            with self.assertRaises(LocalModelDiscoveryError):
                refresh(
                    models_json=self.models_json,
                    models_dir=self.models_dir,
                    routing_config=None,
                    write=True,
                )

        self.assertEqual(
            json.loads(self.models_json.read_text())["local_models"],
            original_locals,
        )

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
            routing_config=None,
            write=False,
        )
        self.assertFalse(result["wrote"])
        self.assertEqual(result["added"], ["local-mlx-new-model"])
        self.assertEqual(result["removed"], ["old-model"])
        # File should be unchanged.
        loaded = json.loads(self.models_json.read_text())
        self.assertEqual(loaded["local_models"], [{"id": "old-model"}])


class StaticEndpointReconciliation(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.model_dir = _make_fake_model_dir(
            self.root,
            "physical-name-4bit",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=2_000_000_000,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_matching_path_keeps_static_identity_and_suppresses_duplicates(self):
        generated = probe_model_dir(self.model_dir)
        duplicate = dict(generated, id="second-generated-id")
        rows = reconcile_static_local_endpoints(
            [generated, duplicate],
            [
                {
                    "id": "stable-curated-id",
                    "type": "local",
                    "model_path": str(self.model_dir),
                    "display_name": "Curated Display Name",
                    "provider": "curated-provider",
                    "context_window": 262144,
                    "parameters_b": 9,
                },
                {
                    "id": "stale-static-id",
                    "type": "local",
                    "model_path": str(self.root / "absent-model"),
                },
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "stable-curated-id")
        self.assertEqual(rows[0]["display_name"], "Curated Display Name")
        self.assertEqual(rows[0]["provider"], "curated-provider")
        self.assertNotIn("stale-static-id", {row["id"] for row in rows})


class DeleteTargetSafety(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "models"
        self.root.mkdir()
        self.target = self.root / "safe-model"
        self.target.mkdir()
        self.inventory = [{"id": "local-safe", "path": str(self.target)}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolves_current_direct_child_by_id(self):
        self.assertEqual(
            resolve_delete_target("local-safe", self.inventory, self.root),
            self.target.resolve(),
        )

    def test_rejects_cloud_or_unknown_id(self):
        with self.assertRaises(LocalModelDeleteError):
            resolve_delete_target("openai/gpt-5", self.inventory, self.root)

    def test_rejects_traversal_outside_models_root(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        inventory = [{"id": "local-escape", "path": str(self.root / ".." / "outside")}]
        with self.assertRaises(LocalModelDeleteError):
            resolve_delete_target("local-escape", inventory, self.root)

    def test_rejects_symlink_escape(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        link = self.root / "linked-model"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(LocalModelDeleteError):
            resolve_delete_target(
                "local-linked", [{"id": "local-linked", "path": str(link)}], self.root
            )

    def test_rejects_target_that_is_no_longer_current(self):
        self.target.rmdir()
        with self.assertRaises(LocalModelDeleteError):
            resolve_delete_target("local-safe", self.inventory, self.root)

    def test_trash_invocation_uses_fixed_argv_without_shell(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.object(
            local_model_discovery.subprocess, "run", return_value=completed
        ) as run:
            self.assertIs(move_model_to_trash(self.target), completed)

        run.assert_called_once_with(
            [TRASH_BIN, str(self.target)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertNotIn("shell", run.call_args.kwargs)


class LocalModelProtectionIdentity(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "models"
        self.root.mkdir()
        self.target = self.root / "model"
        self.target.mkdir()
        from orchestrator import system_protection
        self.protection = system_protection

    def tearDown(self):
        self.tmp.cleanup()

    def test_identity_is_direct_child_lstat_without_tree_walk(self):
        weights = self.target / "weights.safetensors"
        weights.write_bytes(b"not-read-by-protection")
        with mock.patch.object(
            self.protection.os,
            "walk",
            side_effect=AssertionError("model contents must not be walked"),
        ):
            identity = self.protection.capture_local_model_identity(
                self.target.resolve(), self.root.resolve()
            )

        self.assertEqual(identity["target"]["type"], "directory")
        self.assertIsInstance(identity["target"]["lstat"]["inode"], int)

    def test_identity_rejects_non_child_and_changes_on_inode_replacement(self):
        first = self.protection.capture_local_model_identity(
            self.target.resolve(), self.root.resolve()
        )
        self.target.rmdir()
        self.target.mkdir()
        second = self.protection.capture_local_model_identity(
            self.target.resolve(), self.root.resolve()
        )
        self.assertNotEqual(first, second)

        outside = self.root.parent / "outside"
        outside.mkdir()
        with self.assertRaises(self.protection.ProtectionDenied):
            self.protection.capture_local_model_identity(
                outside.resolve(), self.root.resolve()
            )


class LocalModelTrashEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        repo = ORCHESTRATOR.parent
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from orchestrator.embedding import install_test_stub
        install_test_stub()
        from server import app as server
        from orchestrator import system_protection
        cls.server = server
        cls.system_protection = system_protection

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.models_dir = self.root / "models"
        self.models_dir.mkdir()
        self.model_dir = _make_fake_model_dir(
            self.models_dir,
            "physical-model",
            {"architectures": ["LlamaForCausalLM"], "quantization": {"bits": 4}},
            safetensors_bytes=2_000_000_000,
        )
        self.models_json = self.root / "models.json"
        self.models_json.write_text(json.dumps({
            "overhead_reservation_gb": 8,
            "local_models": [],
            "commercial_models": [{"id": "cloud-model"}],
        }))
        self.routing_config = self.root / "routing-config.json"
        self.routing_config.write_text(json.dumps({
            "endpoints": [
                {
                    "id": "stable-local-id",
                    "type": "local",
                    "engine": "mlx",
                    "machine": "test-machine",
                    "model_path": str(self.model_dir),
                    "display_name": "Stable Local",
                    "status": "active",
                    "enabled": True,
                },
                {
                    "id": "stale-static-id",
                    "type": "local",
                    "engine": "mlx",
                    "machine": "test-machine",
                    "model_path": str(self.models_dir / "absent-model"),
                    "display_name": "Absent Local",
                    "status": "active",
                    "enabled": True,
                },
            ],
        }))
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def _server_patches(self):
        return (
            mock.patch.object(self.server, "MODELS_JSON", str(self.models_json)),
            mock.patch.object(self.server, "LOCAL_MODELS_DIR", self.models_dir),
            mock.patch.object(
                self.server,
                "_routing_config_path",
                return_value=str(self.routing_config),
            ),
        )

    def test_endpoint_rejects_cloud_id_without_trashing(self):
        p1, p2, p3 = self._server_patches()
        with p1, p2, p3, mock.patch.object(
            local_model_discovery, "move_model_to_trash"
        ) as trash:
            response = self.client.post(
                "/api/local-models/trash", json={"model_id": "cloud-model"}
            )

        self.assertEqual(response.status_code, 404)
        trash.assert_not_called()
        self.assertTrue(self.model_dir.is_dir())

    def test_endpoint_rejects_cross_site_request_before_discovery(self):
        p1, p2, p3 = self._server_patches()
        with p1, p2, p3, mock.patch.object(
            local_model_discovery, "refresh"
        ) as refresh, mock.patch.object(
            local_model_discovery, "move_model_to_trash"
        ) as trash:
            response = self.client.post(
                "/api/local-models/trash",
                json={"model_id": "stable-local-id"},
                headers={"Origin": "https://attacker.example"},
            )

        self.assertEqual(response.status_code, 403)
        refresh.assert_not_called()
        trash.assert_not_called()

    def test_endpoint_returns_review_required_without_mutation(self):
        p1, p2, p3 = self._server_patches()
        review = self.system_protection.ProtectionReviewRequired(
            "approval required", queue_id="queue-1"
        )
        with p1, p2, p3, mock.patch.object(
            self.system_protection,
            "authorize_server_action",
            side_effect=review,
        ), mock.patch.object(
            local_model_discovery, "move_model_to_trash"
        ) as trash, mock.patch.object(
            self.server, "_reload_pipeline_router_after_config_change"
        ):
            response = self.client.post(
                "/api/local-models/trash", json={"model_id": "stable-local-id"}
            )

        self.assertEqual(response.status_code, 409)
        trash.assert_not_called()
        self.assertTrue(self.model_dir.is_dir())

    def test_registry_returns_one_local_row_per_discovered_path(self):
        p1, p2, p3 = self._server_patches()
        with p1, p2, p3, mock.patch.object(
            self.server.rp,
            "routing_config_path",
            return_value=self.routing_config,
        ):
            response = self.client.get("/api/model-registry?categories=all")

        self.assertEqual(response.status_code, 200, response.data)
        models = json.loads(response.data)["models"]
        local_ids = {
            model_id for model_id, model in models.items()
            if model.get("_local_endpoint")
        }
        self.assertEqual(local_ids, {"stable-local-id"})
        self.assertNotIn("local-mlx-physical-model", models)
        self.assertNotIn("stale-static-id", models)

    def test_endpoint_serializes_evicts_trashes_rescans_and_returns_inventory(self):
        trash_root = self.root / "Trash"
        trash_root.mkdir()
        acquired = []

        def fake_trash(target):
            target = Path(target)
            shutil.move(str(target), str(trash_root / target.name))
            return mock.Mock(returncode=0)

        def fake_acquire(machine_id):
            acquired.append(machine_id)
            return nullcontext()

        fake_boot = types.SimpleNamespace(evict_mlx_model=mock.Mock(return_value=True))
        protection = object()
        p1, p2, p3 = self._server_patches()
        with p1, p2, p3, \
             mock.patch.object(
                 local_model_discovery, "move_model_to_trash", side_effect=fake_trash
             ) as trash, \
             mock.patch("mlx_mutex.acquire", side_effect=fake_acquire), \
             mock.patch.object(
                 self.server, "_boot_context_api", return_value=fake_boot
             ), \
             mock.patch.object(
                 self.system_protection,
                 "authorize_server_action",
                 return_value=protection,
             ) as authorize, \
             mock.patch.object(
                 self.system_protection,
                 "protected_effect",
                 return_value=nullcontext(),
             ), \
             mock.patch.object(
                 self.system_protection, "complete_execution"
             ) as complete, \
             mock.patch.object(
                 self.server,
                 "_reload_pipeline_router_after_config_change",
                 return_value=True,
             ) as reload_router:
            response = self.client.post(
                "/api/local-models/trash", json={"model_id": "stable-local-id"}
            )

        self.assertEqual(response.status_code, 200, response.data)
        payload = json.loads(response.data)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["inventory"], [])
        self.assertEqual(payload["hardware"]["local_models"], [])
        self.assertEqual(acquired, ["test-machine"])
        trash.assert_called_once_with(self.model_dir.resolve())
        fake_boot.evict_mlx_model.assert_called_once_with(str(self.model_dir.resolve()))
        self.assertEqual(reload_router.call_count, 2)
        authorize.assert_called_once()
        self.assertEqual(authorize.call_args.args[0], "local_model_trash")
        complete.assert_called_once()
        self.assertTrue(complete.call_args.kwargs["ok"])
        saved = json.loads(self.models_json.read_text())
        self.assertEqual(saved["local_models"], [])
        self.assertEqual(saved["commercial_models"], [{"id": "cloud-model"}])

    def test_endpoint_revalidates_the_same_target_under_mutex(self):
        replacement = self.models_dir / "replacement-model"
        replacement.mkdir()
        initial = {
            "discovered": [{
                "id": "stable-local-id",
                "path": str(self.model_dir.resolve()),
                "machine": "test-machine",
            }],
            "previous": [{
                "id": "stable-local-id",
                "path": str(self.model_dir.resolve()),
                "machine": "test-machine",
            }],
            "wrote": True,
        }
        changed = {
            **initial,
            "discovered": [{
                "id": "stable-local-id",
                "path": str(replacement.resolve()),
                "machine": "test-machine",
            }],
        }
        protection = object()
        p1, p2, p3 = self._server_patches()
        with p1, p2, p3, mock.patch.object(
            local_model_discovery, "refresh", side_effect=[initial, changed]
        ), mock.patch.object(
            local_model_discovery, "move_model_to_trash"
        ) as trash, mock.patch(
            "mlx_mutex.acquire", return_value=nullcontext()
        ), mock.patch.object(
            self.system_protection,
            "authorize_server_action",
            return_value=protection,
        ), mock.patch.object(
            self.system_protection, "protected_effect"
        ) as protected_effect, mock.patch.object(
            self.system_protection, "complete_execution"
        ) as complete:
            response = self.client.post(
                "/api/local-models/trash", json={"model_id": "stable-local-id"}
            )

        self.assertEqual(response.status_code, 409, response.data)
        trash.assert_not_called()
        protected_effect.assert_not_called()
        complete.assert_called_once()
        self.assertFalse(complete.call_args.kwargs["ok"])

    def test_endpoint_persists_failure_receipt_when_trash_fails(self):
        protection = object()
        p1, p2, p3 = self._server_patches()
        with p1, p2, p3, mock.patch.object(
            local_model_discovery,
            "move_model_to_trash",
            side_effect=OSError("trash unavailable"),
        ), mock.patch(
            "mlx_mutex.acquire", return_value=nullcontext()
        ), mock.patch.object(
            self.server,
            "_boot_context_api",
            return_value=types.SimpleNamespace(evict_mlx_model=mock.Mock()),
        ), mock.patch.object(
            self.system_protection,
            "authorize_server_action",
            return_value=protection,
        ), mock.patch.object(
            self.system_protection,
            "protected_effect",
            return_value=nullcontext(),
        ), mock.patch.object(
            self.system_protection, "complete_execution"
        ) as complete, mock.patch.object(
            self.server, "_reload_pipeline_router_after_config_change"
        ):
            response = self.client.post(
                "/api/local-models/trash", json={"model_id": "stable-local-id"}
            )

        self.assertEqual(response.status_code, 500, response.data)
        complete.assert_called_once()
        self.assertFalse(complete.call_args.kwargs["ok"])

    def test_failed_reload_after_change_retries_on_unchanged_scan(self):
        changed = {
            "discovered": [{"id": "new"}],
            "previous": [],
            "wrote": True,
        }
        unchanged = {
            "discovered": [{"id": "new"}],
            "previous": [{"id": "new"}],
            "wrote": True,
        }
        with mock.patch.object(
            local_model_discovery, "refresh", side_effect=[changed, unchanged]
        ), mock.patch.object(
            self.server,
            "_reload_pipeline_router_after_config_change",
            side_effect=[False, True],
        ) as reload_router:
            first, first_error = self.server._refresh_local_model_inventory()
            second, second_error = self.server._refresh_local_model_inventory()

        self.assertIsNone(first_error)
        self.assertIsNone(second_error)
        self.assertFalse(first["router_reloaded"])
        self.assertTrue(second["router_reloaded"])
        self.assertEqual(reload_router.call_count, 2)
        reload_router.assert_has_calls([mock.call(), mock.call()])


if __name__ == "__main__":
    unittest.main()
