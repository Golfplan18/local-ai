"""Tests for orchestrator/model_registry.py (the runtime reader for the
curated model registry).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


SAMPLE_REGISTRY = {
    "$schema_version": 1,
    "generated_at": "2026-05-20T12:00:00+00:00",
    "model_count": 3,
    "models": {
        "moonshotai/kimi-k2.6": {
            "id": "moonshotai/kimi-k2.6",
            "display_name": "MoonshotAI: Kimi K2.6",
            "vision_capable": False,
            "vision_verified_by": "empirical_probe",
            "intelligence_score": None,
            "intelligence_rank": None,
        },
        "openai/gpt-4o": {
            "id": "openai/gpt-4o",
            "display_name": "OpenAI: GPT-4o",
            "vision_capable": True,
            "vision_verified_by": "litellm",
            "intelligence_score": 1287.0,
            "intelligence_rank": 12,
        },
        "qwen/qwen3.6-plus": {
            "id": "qwen/qwen3.6-plus",
            "display_name": "Qwen 3.6 Plus",
            "vision_capable": True,
            "vision_verified_by": "empirical_probe",
            "intelligence_score": None,
            "intelligence_rank": None,
        },
    },
}


class _RegistryFixture(unittest.TestCase):
    """Base class that wires a temp registry file in place of the real one."""

    def setUp(self):
        import model_registry
        self.tmpdir = tempfile.mkdtemp()
        self.registry_path = Path(self.tmpdir) / "model-registry.json"
        with open(self.registry_path, "w") as f:
            json.dump(SAMPLE_REGISTRY, f)
        self.module = model_registry
        self._orig_path = model_registry.REGISTRY_PATH
        self._orig_cache = model_registry._registry
        model_registry.REGISTRY_PATH = self.registry_path
        model_registry._registry = None  # bust cache so reload reads our fixture

    def tearDown(self):
        self.module.REGISTRY_PATH = self._orig_path
        self.module._registry = self._orig_cache


class TestLoadRegistry(_RegistryFixture):

    def test_loads_valid_registry(self):
        reg = self.module.load_registry()
        self.assertEqual(reg["model_count"], 3)
        self.assertIn("moonshotai/kimi-k2.6", reg["models"])

    def test_caches_on_first_load(self):
        reg1 = self.module.load_registry()
        # Write garbage to disk; cache should still hold the old data
        self.registry_path.write_text("{ this is not valid JSON")
        reg2 = self.module.load_registry()
        self.assertIs(reg1, reg2)

    def test_force_reload_re_reads(self):
        self.module.load_registry()
        # Overwrite with a different shape
        self.registry_path.write_text(json.dumps({"$schema_version": 1,
                                                   "model_count": 0,
                                                   "models": {}}))
        new = self.module.reload()
        self.assertEqual(new["model_count"], 0)

    def test_missing_file_returns_empty_shape(self):
        self.registry_path.unlink()
        self.module._registry = None
        reg = self.module.load_registry()
        self.assertEqual(reg["model_count"], 0)
        self.assertEqual(reg["models"], {})

    def test_malformed_json_returns_empty_shape(self):
        self.registry_path.write_text("{ broken json")
        self.module._registry = None
        reg = self.module.load_registry()
        self.assertEqual(reg["models"], {})


class TestLookup(_RegistryFixture):

    def test_lookup_known_model(self):
        entry = self.module.lookup("moonshotai/kimi-k2.6")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["vision_capable"], False)

    def test_lookup_unknown_returns_none(self):
        self.assertIsNone(self.module.lookup("not-a-real-model"))

    def test_lookup_none_or_empty_returns_none(self):
        self.assertIsNone(self.module.lookup(""))
        self.assertIsNone(self.module.lookup(None))

    def test_vision_capable_returns_value(self):
        self.assertIs(self.module.vision_capable("moonshotai/kimi-k2.6"), False)
        self.assertIs(self.module.vision_capable("openai/gpt-4o"), True)

    def test_vision_capable_default_for_unknown(self):
        self.assertIsNone(self.module.vision_capable("unknown-model"))
        self.assertEqual(
            self.module.vision_capable("unknown-model", default="fallback"),
            "fallback",
        )

    def test_intelligence_score(self):
        self.assertEqual(self.module.intelligence_score("openai/gpt-4o"), 1287.0)
        self.assertIsNone(self.module.intelligence_score("moonshotai/kimi-k2.6"))
        self.assertIsNone(self.module.intelligence_score("unknown"))


class TestOverlayRoutingConfig(_RegistryFixture):

    def test_overlay_corrects_vision_capable(self):
        # Simulate a routing-config where kimi is marked vision_capable=True
        # (the actual bug shape from 2026-05-20).
        rc = {
            "endpoints": [
                {"id": "moonshotai/kimi-k2.6", "vision_capable": True,
                 "type": "api", "service": "openrouter"},
                {"id": "openai/gpt-4o", "vision_capable": True,
                 "type": "api", "service": "openrouter"},
            ]
        }
        result = self.module.overlay_routing_config(rc)
        # kimi: registry says False; overlay corrects it
        kimi = next(e for e in result["endpoints"] if e["id"] == "moonshotai/kimi-k2.6")
        self.assertIs(kimi["vision_capable"], False)
        self.assertEqual(kimi["_vision_capable_source"], "empirical_probe")
        # gpt-4o: registry says True; overlay confirms
        gpt = next(e for e in result["endpoints"] if e["id"] == "openai/gpt-4o")
        self.assertIs(gpt["vision_capable"], True)
        # Counter populated
        self.assertEqual(result["_registry_overlaid_count"], 2)

    def test_overlay_adds_intelligence_score(self):
        rc = {"endpoints": [{"id": "openai/gpt-4o", "vision_capable": True}]}
        result = self.module.overlay_routing_config(rc)
        gpt = result["endpoints"][0]
        self.assertEqual(gpt["intelligence_score"], 1287.0)
        self.assertEqual(gpt["intelligence_rank"], 12)

    def test_overlay_noop_when_no_endpoint_match(self):
        rc = {"endpoints": [{"id": "completely-unknown-model", "vision_capable": True}]}
        result = self.module.overlay_routing_config(rc)
        # No registry entry → no overlay; original flag intact
        self.assertIs(result["endpoints"][0]["vision_capable"], True)
        self.assertEqual(result["_registry_overlaid_count"], 0)

    def test_overlay_handles_alternate_id_fields(self):
        # An endpoint dict that uses model_id / model instead of id
        rc = {"endpoints": [
            {"model_id": "openai/gpt-4o", "vision_capable": False},
        ]}
        result = self.module.overlay_routing_config(rc)
        # Registry value (True) overrides the wrong False flag
        self.assertIs(result["endpoints"][0]["vision_capable"], True)

    def test_overlay_safe_on_empty_registry(self):
        # Drop the registry; overlay should be a no-op
        self.registry_path.unlink()
        self.module._registry = None
        rc = {"endpoints": [{"id": "openai/gpt-4o", "vision_capable": True}]}
        result = self.module.overlay_routing_config(rc)
        self.assertIs(result["endpoints"][0]["vision_capable"], True)
        # No counter written (since the early return path)
        self.assertNotIn("_registry_overlaid_count", result)

    def test_overlay_safe_on_missing_endpoints_list(self):
        rc = {"slot_assignments": {"depth": "openai/gpt-4o"}}  # no endpoints[]
        result = self.module.overlay_routing_config(rc)
        self.assertEqual(result, rc)  # untouched

    def test_overlay_skips_endpoint_without_id(self):
        rc = {"endpoints": [{"vision_capable": True}]}  # no id field
        result = self.module.overlay_routing_config(rc)
        # No id → nothing to look up → no overlay
        self.assertIs(result["endpoints"][0]["vision_capable"], True)
        self.assertEqual(result["_registry_overlaid_count"], 0)


class TestStats(_RegistryFixture):

    def test_stats_summary(self):
        s = self.module.stats()
        self.assertTrue(s["loaded"])
        self.assertEqual(s["model_count"], 3)
        self.assertEqual(s["vision_capable_true"], 2)
        self.assertEqual(s["vision_capable_false"], 1)
        self.assertEqual(s["intelligence_score_count"], 1)


class TestComputePicks(unittest.TestCase):
    """compute_picks walks ``config/configurations/*.json`` and unions
    every model id that appears as a primary or fallback in any slot.
    ``vision_substitute`` is deliberately excluded."""

    def setUp(self):
        import model_registry
        self.module = model_registry
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = Path(self.tmpdir) / "configurations"
        self.config_dir.mkdir()

    def _write_config(self, name, payload):
        with open(self.config_dir / name, "w") as f:
            json.dump(payload, f)

    def _typical_config(self, preset_lineage, primaries,
                        fallbacks=None, vision_substitute=None):
        """Build a configuration dict shaped like the real auto-populate
        output. ``primaries`` and ``fallbacks`` are keyed by slot path
        ('utility.step1_cleanup', 'analysis.gear4.depth', etc.). The
        helper renders the nested shape so each test reads cleanly."""
        fallbacks = fallbacks or {}
        cells = {
            "utility": {},
            "analysis": {"gear4": {}, "gear3": {"breadth": None}},
            "post_analysis": {},
        }
        def _set(path, primary):
            parts = path.split(".")
            node = cells
            for p in parts[:-1]:
                node = node[p]
            slot = {
                "primary": primary,
                "fallback": fallbacks.get(path, []),
            }
            if vision_substitute:
                slot["vision_substitute"] = vision_substitute
            node[parts[-1]] = slot
        for path, primary in primaries.items():
            _set(path, primary)
        return {
            "name": "test",
            "preset_lineage": preset_lineage,
            "cells": cells,
        }

    def test_empty_directory_returns_empty_picks(self):
        result = self.module.compute_picks(self.config_dir)
        self.assertEqual(result["picks"], [])
        self.assertEqual(result["by_model"], {})
        self.assertEqual(result["configurations_scanned"], [])

    def test_missing_directory_returns_empty(self):
        missing = Path(self.tmpdir) / "does-not-exist"
        result = self.module.compute_picks(missing)
        self.assertEqual(result["picks"], [])

    def test_picks_union_across_files(self):
        self._write_config("optimum.json", self._typical_config(
            preset_lineage="optimum",
            primaries={
                "utility.step1_cleanup": "openai/gpt-5-nano",
                "analysis.gear4.depth": "qwen/qwen3.6-plus",
                "analysis.gear4.breadth": "moonshotai/kimi-k2.6",
                "post_analysis.consolidation": "qwen/qwen3.6-plus",
            },
            fallbacks={
                "analysis.gear4.depth": [
                    "moonshotai/kimi-k2.6",
                    "google/gemini-3.1-pro",
                ],
            },
        ))
        self._write_config("premium.json", self._typical_config(
            preset_lineage="premium",
            primaries={
                "analysis.gear4.depth": "anthropic/claude-opus-4.7",
                "analysis.gear4.breadth": "anthropic/claude-sonnet-4.6",
            },
        ))
        result = self.module.compute_picks(self.config_dir)
        self.assertEqual(set(result["picks"]), {
            "openai/gpt-5-nano",
            "qwen/qwen3.6-plus",
            "moonshotai/kimi-k2.6",
            "google/gemini-3.1-pro",
            "anthropic/claude-opus-4.7",
            "anthropic/claude-sonnet-4.6",
        })
        self.assertEqual(result["picks"], sorted(result["picks"]))

    def test_per_model_endorsements_aggregate(self):
        self._write_config("optimum.json", self._typical_config(
            preset_lineage="optimum",
            primaries={"analysis.gear4.depth": "qwen/qwen3.6-plus"},
        ))
        self._write_config("budget.json", self._typical_config(
            preset_lineage="budget",
            primaries={"analysis.gear4.depth": "qwen/qwen3.6-plus"},
        ))
        result = self.module.compute_picks(self.config_dir)
        entry = result["by_model"]["qwen/qwen3.6-plus"]
        self.assertEqual(set(entry["preset_lineages"]), {"optimum", "budget"})
        self.assertEqual(set(entry["configurations"]), {"optimum.json", "budget.json"})

    def test_vision_substitute_is_NOT_in_picks(self):
        """vision_substitute is a text-to-vision fallback for image
        input, not a primary recommendation. Including it would dilute
        the PICK badge."""
        self._write_config("free.json", self._typical_config(
            preset_lineage="free",
            primaries={"analysis.gear4.depth": "meta-llama/llama-3.3-70b:free"},
            vision_substitute="openrouter:openai/gpt-5",
        ))
        result = self.module.compute_picks(self.config_dir)
        self.assertIn("meta-llama/llama-3.3-70b:free", result["picks"])
        self.assertNotIn("openrouter:openai/gpt-5", result["picks"])

    def test_malformed_file_skipped(self):
        (self.config_dir / "broken.json").write_text("{ not json")
        self._write_config("good.json", self._typical_config(
            preset_lineage="optimum",
            primaries={"analysis.gear4.depth": "qwen/qwen3.6-plus"},
        ))
        result = self.module.compute_picks(self.config_dir)
        self.assertEqual(set(result["picks"]), {"qwen/qwen3.6-plus"})
        self.assertIn("good.json", result["configurations_scanned"])
        self.assertNotIn("broken.json", result["configurations_scanned"])

    def test_fallback_chain_contributes_to_picks(self):
        """A model can earn PICK from being in a fallback list, not
        just from being primary anywhere."""
        self._write_config("optimum.json", self._typical_config(
            preset_lineage="optimum",
            primaries={"analysis.gear4.depth": "qwen/qwen3.6-plus"},
            fallbacks={"analysis.gear4.depth": [
                "moonshotai/kimi-k2.6",
                "local-mlx-kimi-dev-72b",
            ]},
        ))
        result = self.module.compute_picks(self.config_dir)
        self.assertIn("qwen/qwen3.6-plus", result["picks"])
        self.assertIn("moonshotai/kimi-k2.6", result["picks"])
        self.assertIn("local-mlx-kimi-dev-72b", result["picks"])

    def test_empty_or_null_primary_is_skipped(self):
        """Empty-string primary or null primary shouldn't pollute the
        PICK set with empty entries."""
        cells = {
            "utility": {
                "step1_cleanup": {"primary": "", "fallback": []},
                "classification": {"primary": None, "fallback": ["foo/bar"]},
            },
        }
        self._write_config("weird.json", {
            "name": "weird",
            "preset_lineage": "optimum",
            "cells": cells,
        })
        result = self.module.compute_picks(self.config_dir)
        self.assertEqual(set(result["picks"]), {"foo/bar"})


if __name__ == "__main__":
    unittest.main()
