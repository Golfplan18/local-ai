#!/usr/bin/env python3
"""Router config_name parameter tests (install Chunk 2b).

Covers the new named-configuration resolution path: when the Router is
called with ``config_name="user-pipeline"`` (or any other configuration
in config/configurations/), slot resolution reads the cell's
primary + fallback[] list rather than walking pipelines[context] →
buckets[bucket_name].

During the Chunk-2b→2d transition these tests asserted the config_name path
resolved to the SAME endpoint as the legacy no-config path. That cutover is now
complete (MSI_CHAIN_FROM_CONFIG): production always supplies a config_name, the
legacy no-config path is vestigial, and the configs are re-baked independently of
the now-stale legacy buckets — so the two paths legitimately diverge. The tests
therefore assert the live invariant instead: the config_name path resolves every
workhorse slot to a usable endpoint.
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
sys.path.insert(0, str(ORCHESTRATOR))

from router import Router  # noqa: E402
import boot  # noqa: E402


class TestApiCapacityMetadata(unittest.TestCase):
    def test_missing_capacity_uses_shared_conservative_floor_for_boot_packing(self):
        endpoint = {"id": "missing-capacity", "type": "local"}
        history = [
            {"role": "user", "content": "history user " + ("u" * 4000)},
            {"role": "assistant", "content": "history answer " + ("a" * 4000)},
        ]
        messages, _reference, coverage = boot._pack_physical_call_context(
            history,
            endpoint,
            [{"role": "system", "content": "required system"}],
            include_prompt_metadata=False,
        )

        self.assertEqual(boot._endpoint_context_window(endpoint), 32_000)
        self.assertEqual(coverage["context_window"], 32_000)
        self.assertEqual(coverage["output_reserve"], 8_000)
        self.assertEqual(coverage["safe_input_capacity"], 23_872)
        self.assertGreater(len(messages), 1)

    def test_missing_api_capacity_uses_conservative_floor(self):
        router = Router(config_dict={"endpoints": []})
        for key in ("context_window", "context_length", "max_context_length"):
            with self.subTest(key=key):
                endpoint = router._to_v1_endpoint({
                    "id": f"missing-{key}", "type": "api",
                    "service": "openrouter", "model_id": "missing-capacity",
                    key: None,
                })
                self.assertEqual(endpoint["context_window"], 32_000)

    def test_context_aliases_survive_v1_conversion(self):
        router = Router(config_dict={"endpoints": []})
        for key in ("context_window", "context_length", "max_context_length"):
            with self.subTest(key=key):
                endpoint = router._to_v1_endpoint({
                    "id": f"explicit-{key}", "type": "api",
                    "service": "openrouter", "model_id": "explicit",
                    key: 128_000,
                })
                self.assertEqual(endpoint["context_window"], 128_000)

    def test_production_api_route_keeps_positive_bounded_phase_a_and_gear_history(self):
        raw_endpoint = {
            "id": "openrouter/production-shaped",
            "type": "api",
            "service": "openrouter",
            "model_id": "vendor/production-shaped",
            "enabled": True,
            "status": "active",
            "context_window": 131_072,
            "max_output_tokens": 8_192,
            "capabilities": {
                "tool_access": True,
                "web_access": False,
                "retrieval_approach": "pre-assembled",
            },
        }
        router = Router(config_dict={"endpoints": [raw_endpoint]})
        endpoint = router._to_v1_endpoint(raw_endpoint)

        self.assertEqual(endpoint["context_window"], 131_072)
        self.assertEqual(endpoint["max_tokens"], 8_192)
        self.assertEqual(endpoint["max_output_tokens"], 8_192)

        history = []
        for index in range(40):
            history.extend([
                {
                    "role": "user",
                    "content": f"ROUTE-U{index:02d}:" + ("u" * 2000),
                },
                {
                    "role": "assistant",
                    "content": f"ROUTE-A{index:02d}:" + ("a" * 2000),
                },
            ])

        gear_messages, gear_stats = boot.prepare_messages_with_continuity(
            [
                {"role": "system", "content": "gear system"},
                {"role": "user", "content": "gear current"},
            ],
            endpoint,
            history,
        )
        self.assertGreater(gear_stats["history_selected_units"], 0)
        self.assertLess(gear_stats["history_selected_units"], 40)
        self.assertLessEqual(
            boot.estimate_message_tokens(gear_messages, endpoint),
            gear_stats["safe_input_capacity"],
        )
        self.assertIn("ROUTE-U39:", "\n".join(
            message["content"] for message in gear_messages
        ))

        captured = []

        def phase_a(messages, _endpoint, images=None):
            captured.append(messages)
            return (
                "### CLEANED PROMPT (Natural Language)\nAnalyse routing.\n"
                "### CLEANED PROMPT (Operational Notation)\nanalyse_routing()\n"
                "### CORRECTIONS LOG\nNone\n"
                "### INFERRED ITEMS\nNone"
            )

        with (
            mock.patch.object(boot, "get_slot_endpoint", return_value=endpoint),
            mock.patch.object(boot, "call_model", side_effect=phase_a),
            mock.patch.object(boot, "pre_phase_a_bypass_check", return_value=None),
        ):
            boot.run_step1_cleanup(
                "Analyse routing.",
                "",
                {},
                conversation_history=history,
            )

        phase_a_text = captured[0][-1]["content"]
        self.assertIn("ROUTE-U39:", phase_a_text)
        self.assertNotIn("ROUTE-U00:", phase_a_text)
        self.assertLessEqual(
            boot.estimate_message_tokens(captured[0], endpoint),
            endpoint["context_window"]
            - boot._endpoint_output_reserve(
                endpoint, endpoint["context_window"],
            )
            - 128,
        )


class TestMsiCapacityBoundary(unittest.TestCase):
    def _router(self):
        return Router(config_dict={
            "endpoints": [
                {"id": "small", "type": "api", "service": "openrouter",
                 "model_id": "small", "context_window": 128_000,
                 "enabled": True, "status": "active"},
                {"id": "missing", "type": "api", "service": "openrouter",
                 "model_id": "missing", "enabled": True, "status": "active"},
                {"id": "large", "type": "api", "service": "openrouter",
                 "model_id": "large", "context_window": 400_000,
                 "enabled": True, "status": "active"},
            ],
        })

    def test_msi_skips_unknown_capacity_and_uses_authoritative_large(self):
        router = self._router()
        config = {"cells": {"analysis": {"gear4": {
            "depth": {"primary": "small", "fallback": ["missing", "large"]},
        }}}}
        with mock.patch.object(router, "_load_configuration", return_value=config):
            endpoint = router.resolve_endpoint(
                "depth", 4, "interactive", config_name="msi-publication",
                mutex_check=False)
        self.assertEqual(endpoint["id"], "large")

    def test_msi_keeps_explicit_small_capacity_out_of_analysis(self):
        router = self._router()
        config = {"cells": {"analysis": {"gear4": {
            "depth": {"primary": "small", "fallback": []},
        }}}}
        with mock.patch.object(router, "_load_configuration", return_value=config):
            endpoint = router.resolve_endpoint(
                "depth", 4, "interactive", config_name="msi-publication",
                mutex_check=False)
        self.assertIsNone(endpoint)

    def test_msi_does_not_filter_small_utility_endpoint(self):
        router = self._router()
        config = {"cells": {"utility": {
            "step1_cleanup": {"primary": "small", "fallback": []},
        }}}
        with mock.patch.object(router, "_load_configuration", return_value=config):
            endpoint = router.resolve_utility_slot(
                "step1_cleanup", config_name="msi-publication")
        self.assertEqual(endpoint["id"], "small")

    def test_aliases_resolve_against_registry_catalog(self):
        router = Router(config_dict={
            "endpoints": [{
                "id": "deepseek/deepseek-v4-flash", "type": "api",
                "service": "openrouter", "model_id": "deepseek/deepseek-v4-flash",
            }],
        })
        self.assertEqual(
            router._resolve_endpoint_id("~deepseek/deepseek-v4-flash-latest"),
            "deepseek/deepseek-v4-flash")

    def test_providerless_leaf_does_not_choose_first_endpoint(self):
        router = Router(config_dict={
            "endpoints": [
                {"id": "provider-a/shared-model", "type": "api"},
                {"id": "provider-b/shared-model", "type": "api"},
            ],
        })
        self.assertEqual(
            router._resolve_endpoint_id("shared-model"), "shared-model")
        self.assertEqual(
            router._resolve_endpoint_id("provider-a/shared-model"),
            "provider-a/shared-model")

    def test_installer_models_json_missing_capacity_uses_conservative_floor(self):
        import router as router_module

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model_path = root / "models" / "missing-capacity"
            models_json = root / "models.json"
            models_json.write_text(json.dumps({"local_models": [{
                "id": "local-missing", "path": str(model_path),
            }]}))
            config = {"endpoints": [{
                "id": "local-missing", "type": "local",
                "model_path": str(model_path), "enabled": True,
                "status": "active",
            }]}
            with mock.patch.object(
                router_module.rp, "models_json_path", return_value=models_json,
            ):
                router = Router(config_dict=config)
            self.assertEqual(
                router._endpoints["local-missing"]["context_window"], 32_000)

    def test_local_capacity_alias_survives_discovery_and_v1_conversion(self):
        import router as router_module

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model_path = root / "models" / "explicit-capacity"
            models_json = root / "models.json"
            models_json.write_text(json.dumps({"local_models": [{
                "id": "local-explicit", "path": str(model_path),
                "context_length": 128_000,
            }]}))
            config = {"endpoints": [{
                "id": "local-explicit", "type": "local",
                "model_path": str(model_path), "enabled": True,
                "status": "active",
            }]}
            with mock.patch.object(
                router_module.rp, "models_json_path", return_value=models_json,
            ):
                router = Router(config_dict=config)
            endpoint = router._endpoints["local-explicit"]
            self.assertEqual(endpoint["context_window"], 128_000)
            self.assertEqual(
                router._to_v1_endpoint(endpoint)["context_window"], 128_000)


class TestConfigNameEquivalence(unittest.TestCase):
    """The new path returns the same endpoint as the legacy path."""

    @classmethod
    def setUpClass(cls):
        # Uses the real routing-config.json + the seed configurations
        # generated by scripts/migrate-to-configurations.py.
        cls.router = Router()

    def _equivalence(self, slot, gear, context, config_name):
        # Post-cutover (MSI_CHAIN_FROM_CONFIG): the config_name path is the live,
        # authoritative one — production always supplies a config_name. The
        # legacy no-config path is vestigial and no longer guaranteed to agree
        # (configs are re-baked independently of the now-stale legacy buckets),
        # so the original equivalence assertion is obsolete. The meaningful
        # invariant is that the config path resolves every workhorse slot to a
        # usable endpoint.
        ep = self.router.resolve_endpoint(
            slot=slot, gear=gear, context=context, config_name=config_name)
        self.assertIsNotNone(
            ep, f"config path resolved no endpoint for slot={slot} gear={gear} "
                f"context={context} config_name={config_name}")
        self.assertTrue(
            isinstance(ep.get("id"), str) and ep["id"],
            f"config path resolved slot={slot} to a malformed endpoint: {ep!r}")

    def test_interactive_utility_step1_cleanup(self):
        self._equivalence("step1_cleanup", 1, "interactive", "user-pipeline")

    def test_interactive_utility_classification(self):
        self._equivalence("classification", 1, "interactive", "user-pipeline")

    def test_interactive_utility_rag_planner(self):
        self._equivalence("rag_planner", 1, "interactive", "user-pipeline")

    def test_interactive_analysis_gear4_depth(self):
        self._equivalence("depth", 4, "interactive", "user-pipeline")

    def test_interactive_analysis_gear4_breadth(self):
        self._equivalence("breadth", 4, "interactive", "user-pipeline")

    def test_interactive_analysis_gear3_depth(self):
        self._equivalence("depth", 3, "interactive", "user-pipeline")

    def test_agent_utility_step1_cleanup(self):
        self._equivalence("step1_cleanup", 1, "agent", "background-default")

    def test_agent_analysis_gear4_depth(self):
        self._equivalence("depth", 4, "agent", "background-default")

    def test_agent_analysis_gear4_breadth(self):
        self._equivalence("breadth", 4, "agent", "background-default")


class TestConfigNamePostAnalysis(unittest.TestCase):
    """Post-analysis slot resolution via config_name."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()

    def _equivalence(self, slot, context, config_name):
        # See TestConfigNameEquivalence._equivalence: post-cutover the config
        # path is authoritative; assert it resolves to a usable endpoint rather
        # than equal the vestigial legacy no-config path.
        ep = self.router.resolve_post_analysis_slot(slot, context, config_name=config_name)
        self.assertIsNotNone(
            ep, f"config path resolved no post-analysis endpoint for slot={slot} "
                f"context={context} config_name={config_name}")
        self.assertTrue(
            isinstance(ep.get("id"), str) and ep["id"],
            f"config path resolved post-analysis slot={slot} to a malformed endpoint: {ep!r}")

    def test_interactive_consolidation(self):
        self._equivalence("consolidation", "interactive", "user-pipeline")

    def test_interactive_verification(self):
        self._equivalence("verification", "interactive", "user-pipeline")

    def test_agent_consolidation(self):
        self._equivalence("consolidation", "agent", "background-default")

    def test_agent_verification(self):
        self._equivalence("verification", "agent", "background-default")


class TestConfigNameUtility(unittest.TestCase):
    """Utility slot resolution via config_name."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()

    def _equivalence(self, slot, context, config_name):
        # See TestConfigNameEquivalence._equivalence: post-cutover the config
        # path is authoritative; assert it resolves to a usable endpoint rather
        # than equal the vestigial legacy no-config path.
        ep = self.router.resolve_utility_slot(slot, context, config_name=config_name)
        self.assertIsNotNone(
            ep, f"config path resolved no utility endpoint for slot={slot} "
                f"context={context} config_name={config_name}")
        self.assertTrue(
            isinstance(ep.get("id"), str) and ep["id"],
            f"config path resolved utility slot={slot} to a malformed endpoint: {ep!r}")

    def test_interactive_step1_cleanup(self):
        self._equivalence("step1_cleanup", "interactive", "user-pipeline")

    def test_interactive_classification(self):
        self._equivalence("classification", "interactive", "user-pipeline")

    def test_interactive_rag_planner(self):
        self._equivalence("rag_planner", "interactive", "user-pipeline")

    def test_interactive_fast_resolves_gear2_rag_lookup_cell(self):
        direct = self.router.resolve_utility_slot(
            "gear2_rag_lookup", "interactive", config_name="user-pipeline")
        alias = self.router.resolve_utility_slot(
            "fast", "interactive", config_name="user-pipeline")
        self.assertIsNotNone(direct)
        self.assertEqual(alias["id"], direct["id"])

    def test_agent_step1_cleanup(self):
        self._equivalence("step1_cleanup", "agent", "background-default")


class TestExecuteWithConfigName(unittest.TestCase):
    """execute() with config_name resolves a full gear's assignments to valid
    endpoints. (Post-cutover the config path is authoritative and no longer
    mirrors the vestigial legacy context-based path — see the module docstring.)"""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()

    def _assert_valid_gear4(self, config_name):
        res = self.router.execute(
            requested_gear=4, context="interactive", config_name=config_name)
        self.assertEqual(res.gear, 4)
        ids = {s: ep.get("id") for s, ep in res.assignments_v2.items()}
        self.assertTrue(ids, f"no gear-4 assignments for config_name={config_name}")
        for slot, eid in ids.items():
            self.assertTrue(
                isinstance(eid, str) and eid,
                f"config {config_name} resolved slot={slot} to a malformed id: {eid!r}")

    def test_execute_gear4_interactive_resolves(self):
        self._assert_valid_gear4("user-pipeline")

    def test_execute_gear4_agent_resolves(self):
        self._assert_valid_gear4("background-default")


class TestConfigNameMissing(unittest.TestCase):
    """Missing or invalid config_name returns None gracefully."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()

    def test_unknown_config_returns_none(self):
        ep = self.router.resolve_endpoint(
            slot="depth", gear=4, context="interactive",
            config_name="this-config-does-not-exist",
        )
        self.assertIsNone(ep)

    def test_unknown_slot_returns_none(self):
        ep = self.router.resolve_endpoint(
            slot="totally-unknown-slot", gear=4, context="interactive",
            config_name="user-pipeline",
        )
        self.assertIsNone(ep)

    def test_boot_unknown_slot_does_not_fall_back_to_cleanup(self):
        with mock.patch.object(boot, "_get_router", return_value=self.router):
            endpoint = boot.get_slot_endpoint(
                self.router.config,
                "totally-unknown-slot",
                config_name="user-pipeline",
            )
        self.assertIsNone(endpoint)


class TestSameMachineLocalResolution(unittest.TestCase):
    def _router(self):
        local = {
            "id": "local-a", "type": "local", "engine": "mlx",
            "machine": "studio-128", "model_path": "/not-loaded/local-a",
            "enabled": True, "status": "active",
        }
        config = {
            "endpoints": [local],
            "buckets": {"local": ["local-a"]},
            "pipelines": {"legacy-test": {"analysis": {"gear4": {
                "depth": {"buckets": ["local"]},
            }}}},
        }
        with mock.patch.object(
            Router, "_merge_models_json_local_endpoints", return_value=True,
        ):
            return Router(config_dict=config)

    def test_legacy_path_does_not_exclude_same_machine_local(self):
        endpoint = self._router().resolve_endpoint(
            "depth", 4, "legacy-test", same_machine_block="studio-128",
            mutex_check=False,
        )
        self.assertEqual(endpoint["id"], "local-a")

    def test_named_path_does_not_exclude_same_machine_local(self):
        import router as router_module

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "local-profile.json").write_text(json.dumps({
                "cells": {"analysis": {"gear4": {"depth": {
                    "primary": "local-a", "fallback": [],
                }}}},
            }), encoding="utf-8")
            with mock.patch.object(
                router_module, "CONFIGURATIONS_DIR", config_dir,
            ), mock.patch(
                "orchestrator.model_profiles.ac._load_local_models",
                return_value=[],
            ):
                endpoint = self._router().resolve_endpoint(
                    "depth", 4, "interactive",
                    config_name="local-profile",
                    same_machine_block="studio-128", mutex_check=False,
                )
        self.assertEqual(endpoint["id"], "local-a")

    def test_profile_diversity_override_is_authoritative_for_retry(self):
        import router as router_module

        endpoint = {
            "id": "api-a", "type": "api", "service": "test",
            "model_id": "api-a", "enabled": True, "status": "active",
        }
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            for name, diversity in (("strict", True), ("reuse", False)):
                (config_dir / f"{name}.json").write_text(json.dumps({
                    "diversity_override": diversity,
                    "cells": {"analysis": {"gear4": {
                        "depth": {"primary": "api-a", "fallback": []},
                        "breadth": {"primary": "api-a", "fallback": []},
                    }}},
                }), encoding="utf-8")
            with mock.patch.object(
                router_module, "CONFIGURATIONS_DIR", config_dir,
            ), mock.patch(
                "orchestrator.model_profiles.ac._load_local_models",
                return_value=[],
            ), mock.patch.object(
                Router, "_merge_models_json_local_endpoints", return_value=True,
            ):
                global_reuse = Router(config_dict={
                    "endpoints": [endpoint], "diversity": {"enabled": False},
                })
                global_strict = Router(config_dict={
                    "endpoints": [endpoint], "diversity": {"enabled": True},
                })
                self.assertIsNone(global_reuse.resolve_gear(
                    4, "interactive", config_name="strict"))
                reused = global_strict.resolve_gear(
                    4, "interactive", config_name="reuse")

        self.assertEqual(reused["depth"]["id"], "api-a")
        self.assertEqual(reused["breadth"]["id"], "api-a")


class TestConfigurationRamContract(unittest.TestCase):
    def test_direct_named_profile_load_rejects_over_cap_allocation(self):
        from orchestrator import model_profiles as mp
        import router as router_module

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            (config_dir / "oversized.json").write_text(json.dumps({
                "roles": {
                    "inner": {
                        "primary": "vendor/cloud-model", "fallback": [],
                    },
                    "large": {
                        "role": "inner",
                        "primary": "local-too-large", "fallback": [],
                    },
                },
                "cells": {"analysis": {
                    "role": "inner",
                    "gear4": {"depth": {"role": "large"}},
                }},
            }), encoding="utf-8")
            with (
                mock.patch.object(router_module, "CONFIGURATIONS_DIR", config_dir),
                mock.patch.object(mp.ac, "_get_system_ram_gb", return_value=100),
                mock.patch.object(mp.ac, "_load_local_models", return_value=[
                    {"id": "local-too-large", "ram_gb": 86},
                ]),
            ):
                router = Router(config_dict={"endpoints": []})
                with self.assertRaisesRegex(mp.ModelProfileError, "85% hard cap"):
                    router._load_configuration("oversized")
                self.assertNotIn("oversized", router._configurations)

                router._configurations["oversized"] = json.loads(
                    (config_dir / "oversized.json").read_text(encoding="utf-8")
                )
                with self.assertRaisesRegex(mp.ModelProfileError, "85% hard cap"):
                    router._load_configuration("oversized")

    def test_named_profile_without_installed_locals_still_loads(self):
        import router as router_module

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            expected = {"cells": {"analysis": {"gear4": {"depth": {
                "primary": "vendor/cloud-model", "fallback": [],
            }}}}}
            (config_dir / "cloud-only.json").write_text(
                json.dumps(expected), encoding="utf-8",
            )
            with mock.patch.object(
                router_module, "CONFIGURATIONS_DIR", config_dir,
            ), mock.patch(
                "orchestrator.model_profiles.ac._load_local_models",
                return_value=[],
            ):
                router = Router(config_dict={"endpoints": []})
                self.assertEqual(router._load_configuration("cloud-only"), expected)

class TestConfigurationCacheClearsOnReload(unittest.TestCase):
    """reload() must invalidate the configuration cache so file edits
    take effect on the next call."""

    def test_cache_cleared_on_reload(self):
        router = Router()
        # Warm the cache
        router._load_configuration("user-pipeline")
        self.assertIn("user-pipeline", router._configurations)

        # Reload should clear the cache via _build_lookup_tables.
        router.reload()
        self.assertEqual(router._configurations, {})


class TestProjectOwnedConfiguration(unittest.TestCase):
    def test_msi_path_override_and_role_reference(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "msi-model-routing.json"
            path.write_text(json.dumps({
                "roles": {
                    "big1": {"primary": "xiaomi/mimo-v2.5",
                             "fallback": ["deepseek/deepseek-v4-flash"]},
                },
                "cells": {"analysis": {"gear4": {
                    "depth": {"role": "big1"},
                }}},
            }), encoding="utf-8")
            env = {
                "MSI_GEAR4_CONFIG_NAME": "msi-publication",
                "MSI_BACKGROUND_CONFIG_PATH": str(path),
            }
            with mock.patch.dict(os.environ, env):
                router = Router()
                self.assertEqual(
                    router._configuration_path("msi-publication"), path)
                self.assertEqual(
                    router.get_slot_chain("depth", 4, "msi-publication"),
                    ["xiaomi/mimo-v2.5", "deepseek/deepseek-v4-flash"],
                )
                self.assertNotEqual(
                    router._configuration_path("background-default"), path)

    def test_msi_configuration_fails_closed_without_bridge_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            router = Router()
            with self.assertRaisesRegex(RuntimeError, "MSI routing must set"):
                router._configuration_path("msi-publication")

    def test_msi_configuration_fails_closed_for_missing_project_file(self):
        env = {
            "MSI_GEAR4_CONFIG_NAME": "msi-publication",
            "MSI_BACKGROUND_CONFIG_PATH": "/definitely/missing/msi-routing.json",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            router = Router()
            with self.assertRaisesRegex(RuntimeError, "routing file is missing"):
                router._configuration_path("msi-publication")


class TestVisionCapableLookup(unittest.TestCase):
    """vision_capable_for_endpoint prefers models.json (Chunk 2e)."""

    @classmethod
    def setUpClass(cls):
        cls.router = Router()

    def test_local_model_text_only(self):
        # All local MLX models are text-only per models.json.
        self.assertFalse(self.router.vision_capable_for_endpoint("local-mlx-hermes-4-70b"))
        self.assertFalse(self.router.vision_capable_for_endpoint("local-mlx-kimi-dev-72b"))
        self.assertFalse(self.router.vision_capable_for_endpoint("local-mlx-qwen3.5-4b"))

    def test_unknown_endpoint_defaults_false(self):
        self.assertFalse(self.router.vision_capable_for_endpoint("definitely-not-an-endpoint"))

    def test_lookup_cached(self):
        router = Router()
        # Warm
        router.vision_capable_for_endpoint("local-mlx-hermes-4-70b")
        cache1 = router._vision_lookup_cache
        # Second call returns cached
        router.vision_capable_for_endpoint("local-mlx-kimi-dev-72b")
        cache2 = router._vision_lookup_cache
        self.assertIs(cache1, cache2)

    def test_cache_cleared_on_reload(self):
        router = Router()
        # Warm
        router.vision_capable_for_endpoint("local-mlx-hermes-4-70b")
        self.assertIsNotNone(router._vision_lookup_cache)
        # Reload clears via _build_lookup_tables
        router.reload()
        self.assertIsNone(router._vision_lookup_cache)


if __name__ == "__main__":
    unittest.main()
