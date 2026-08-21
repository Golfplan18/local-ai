"""Tests for orchestrator/active_configuration.py — the active-config
pointer + per-configuration toggle persistence used by the V3 Models
pane header strip (install Chunk 10 step 3)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


class _Fixture(unittest.TestCase):
    """Redirects the module's CONFIG + DATA paths into a temp dir so
    tests don't touch the real ~/ora state."""

    def setUp(self):
        import active_configuration as ac
        self.module = ac
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir) / "data"
        self.config_dir = Path(self.tmpdir) / "config" / "configurations"
        self.models_path = Path(self.tmpdir) / "config" / "models.json"
        self.runtime_config_dir = (
            Path(self.tmpdir) / "data" / "runtime" / "config" / "configurations")
        self.data_dir.mkdir(parents=True)
        self.config_dir.mkdir(parents=True)
        self.models_path.write_text('{"local_models": []}\n', encoding="utf-8")
        self._orig_data = ac.DATA_DIR
        self._orig_pointer = ac.ACTIVE_POINTER_PATH
        self._orig_config = ac.CONFIGURATIONS_DIR
        self._orig_default_config = ac._DEFAULT_CONFIGURATIONS_DIR
        self._orig_runtime_config = ac.RUNTIME_CONFIGURATIONS_DIR
        self._orig_models_path = ac.MODELS_JSON_PATH
        ac.DATA_DIR = self.data_dir
        ac.ACTIVE_POINTER_PATH = self.data_dir / "active-configuration.json"
        ac.CONFIGURATIONS_DIR = self.config_dir
        ac.RUNTIME_CONFIGURATIONS_DIR = self.runtime_config_dir
        ac.MODELS_JSON_PATH = self.models_path

    def tearDown(self):
        self.module.DATA_DIR = self._orig_data
        self.module.ACTIVE_POINTER_PATH = self._orig_pointer
        self.module.CONFIGURATIONS_DIR = self._orig_config
        self.module._DEFAULT_CONFIGURATIONS_DIR = self._orig_default_config
        self.module.RUNTIME_CONFIGURATIONS_DIR = self._orig_runtime_config
        self.module.MODELS_JSON_PATH = self._orig_models_path

    def _write_config(self, name, payload):
        with open(self.config_dir / f"{name}.json", "w") as f:
            json.dump(payload, f)

    def _write_runtime_config(self, name, payload):
        self.runtime_config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.runtime_config_dir / f"{name}.json", "w") as f:
            json.dump(payload, f)


class TestActivePointer(_Fixture):

    def test_missing_pointer_returns_default(self):
        self.assertEqual(self.module.get_active_name(),
                         self.module.DEFAULT_ACTIVE_NAME)

    def test_set_and_get_roundtrip(self):
        self._write_config("budget-bake", {"name": "budget-bake", "cells": {}})
        self.module.set_active_name("budget-bake")
        self.assertEqual(self.module.get_active_name(), "budget-bake")

    def test_set_rejects_nonexistent_config(self):
        with self.assertRaises(ValueError):
            self.module.set_active_name("not-a-real-config")

    def test_set_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            self.module.set_active_name("")
        with self.assertRaises(ValueError):
            self.module.set_active_name("   ")

    def test_malformed_pointer_falls_back_to_default(self):
        (self.data_dir / "active-configuration.json").write_text("{not json")
        self.assertEqual(self.module.get_active_name(),
                         self.module.DEFAULT_ACTIVE_NAME)


class TestProfileRamAllocation(_Fixture):

    def _profile(self, primary, *, fallback=None, visual=None):
        return {"cells": {"analysis": {"gear4": {"depth": {
            "primary": primary,
            "fallback": list(fallback or []),
            "vision_substitute": visual,
        }}}}}

    def test_unique_models_across_primary_fallback_and_visual_count_once(self):
        profile = {"cells": {
            "analysis": {"gear4": {
                "depth": {
                    "primary": "local-a",
                    "fallback": ["local-b", "local-a", "deleted-local"],
                    "vision_substitute": "local-c",
                },
                "breadth": {
                    "primary": "local-b",
                    "fallback": ["local-c"],
                    "vision_substitute": "local-a",
                },
            }},
        }}
        allocation = self.module.profile_ram_allocation(
            profile,
            system_ram_gb=100,
            local_models=[
                {"id": "local-a", "ram_gb": 20},
                {"id": "local-b", "ram_gb": 30},
                {"id": "local-c", "ram_gb": 10},
            ],
        )
        self.assertEqual(allocation["active_local_model_ids"], [
            "local-a", "local-c", "local-b",
        ])
        self.assertEqual(allocation["allocated_local_ram_gb"], 60)
        self.assertEqual(allocation["automatic_target_gb"], 80)
        self.assertEqual(allocation["hard_cap_gb"], 85)
        self.assertEqual(allocation["headroom_to_hard_cap_gb"], 25)

    def test_only_reachable_roles_count_and_reuse_counts_once(self):
        profile = {
            "roles": {
                "shared": {
                    "primary": "local-a",
                    "fallback": ["local-b", "local-a"],
                },
                "alias": {"role": "shared"},
                "duplicate": {"primary": "local-a", "fallback": []},
                "unused": {"primary": "unused-local", "fallback": []},
            },
            "cells": {
                "utility": {"step1_cleanup": {"role": "alias"}},
                "analysis": {"gear4": {
                    "depth": {"role": "duplicate"},
                    "breadth": {
                        "role": "shared",
                        "primary": "overridden-local",
                    },
                }},
            },
        }
        allocation = self.module.profile_ram_allocation(
            profile,
            system_ram_gb=100,
            local_models=[
                {"id": "local-a", "ram_gb": 20},
                {"id": "local-b", "ram_gb": 30},
                {"id": "unused-local", "ram_gb": 90},
                {"id": "overridden-local", "ram_gb": 90},
            ],
        )
        self.assertEqual(
            allocation["active_local_model_ids"], ["local-a", "local-b"],
        )
        self.assertEqual(allocation["allocated_local_ram_gb"], 50)

    def test_reachable_malformed_role_references_fail_clearly(self):
        invalid_profiles = (
            ({"cells": {"slot": {"role": "missing"}}}, "no roles object"),
            (
                {"roles": {"bad": "not-an-object"},
                 "cells": {"slot": {"role": "bad"}}},
                "does not name an object",
            ),
            ({"roles": {}, "cells": {"slot": {"role": []}}},
             "non-empty string"),
        )
        for profile, message in invalid_profiles:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.module.profile_ram_allocation(
                        profile, system_ram_gb=100, local_models=[],
                    )

    def test_grouping_role_metadata_cannot_hide_descendant_allocation(self):
        profile = {
            "roles": {
                "metadata": {
                    "primary": "vendor/cloud-model", "fallback": [],
                },
                "large": {
                    "role": "metadata",
                    "primary": "local-too-large", "fallback": [],
                },
            },
            "cells": {"analysis": {
                "role": "metadata",
                "gear4": {"depth": {"role": "large"}},
            }},
        }
        inventory = [{"id": "local-too-large", "ram_gb": 86}]
        allocation = self.module.profile_ram_allocation(
            profile, system_ram_gb=100, local_models=inventory,
        )
        self.assertEqual(
            allocation["active_local_model_ids"], ["local-too-large"],
        )
        with self.assertRaisesRegex(ValueError, "85% hard cap"):
            self.module.validate_profile_allocation(
                profile, system_ram_gb=100, local_models=inventory,
            )

    def test_unavailable_or_deleted_ids_count_zero(self):
        allocation = self.module.profile_ram_allocation(
            self._profile("deleted-local", fallback=["local-a", "missing-local"]),
            system_ram_gb=100,
            local_models=[{"id": "local-a", "ram_gb": 20}],
        )
        self.assertEqual(allocation["active_local_model_ids"], ["local-a"])
        self.assertEqual(allocation["allocated_local_ram_gb"], 20)

    def test_missing_or_malformed_inventory_fails_closed_but_empty_is_valid(self):
        empty = self.module.validate_profile_allocation(
            self._profile("local-a"), system_ram_gb=100,
        )
        self.assertEqual(empty["allocated_local_ram_gb"], 0)

        self.models_path.unlink()
        with self.assertRaisesRegex(ValueError, "inventory is unavailable"):
            self.module.validate_profile_allocation(
                self._profile("local-a"), system_ram_gb=100,
            )

        for malformed in ("{not json", "[]", '{}', '{"local_models": {}}'):
            with self.subTest(malformed=malformed):
                self.models_path.write_text(malformed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "inventory is (?:unavailable|malformed)"):
                    self.module.validate_profile_allocation(
                        self._profile("local-a"), system_ram_gb=100,
                    )

    def test_injected_inventory_rejects_duplicate_ids_and_invalid_ram(self):
        invalid_inventories = (
            None,
            {"not": "a list"},
            [
                {"id": "local-a", "ram_gb": 1},
                {"id": "local-a", "ram_gb": 2},
            ],
            [{"id": "local-a", "ram_gb": -1}],
            [{"id": "local-a", "ram_gb": float("nan")}],
            [{"id": "local-a", "ram_gb": float("inf")}],
            [{"id": "local-a", "ram_gb": "unknown"}],
            ["not-an-object"],
        )
        for rows in invalid_inventories:
            with self.subTest(rows=rows):
                with self.assertRaisesRegex(ValueError, "inventory is malformed"):
                    self.module.validate_profile_allocation(
                        self._profile("local-a"),
                        system_ram_gb=100,
                        local_models=rows,
                    )

    def test_stale_canonical_path_is_unavailable_and_counts_zero(self):
        allocation = self.module.profile_ram_allocation(
            self._profile("local-stale"),
            system_ram_gb=100,
            local_models=[{
                "id": "local-stale",
                "ram_gb": 80,
                "path": str(Path(self.tmpdir) / "models" / "gone"),
            }],
        )
        self.assertEqual(allocation["active_local_model_ids"], [])
        self.assertEqual(allocation["allocated_local_ram_gb"], 0)

    def test_exact_hard_cap_is_accepted_and_any_excess_is_rejected(self):
        at_cap = self.module.validate_profile_allocation(
            self._profile("at-cap"),
            system_ram_gb=100,
            local_models=[{"id": "at-cap", "ram_gb": 85}],
        )
        self.assertEqual(at_cap["headroom_to_hard_cap_gb"], 0)
        with self.assertRaisesRegex(ValueError, "85% hard cap"):
            self.module.validate_profile_allocation(
                {
                    "roles": {
                        "large": {"primary": "over-cap", "fallback": []},
                    },
                    "cells": {"analysis": {"gear4": {
                        "depth": {"role": "large"},
                    }}},
                },
                system_ram_gb=100,
                local_models=[{"id": "over-cap", "ram_gb": 85.01}],
            )

    def test_failed_manual_edits_leave_profile_bytes_unchanged(self):
        original = {
            "cells": {
                "utility": {"step1_cleanup": {
                    "primary": "base-local", "fallback": [],
                }},
                "analysis": {
                    "gear4": {"depth": {"primary": "cloud", "fallback": []}},
                    "gear3": {"depth": {"primary": "cloud", "fallback": []}},
                },
            },
        }
        inventory = [
            {"id": "base-local", "ram_gb": 80},
            {"id": "extra-local", "ram_gb": 6},
        ]
        operations = (
            lambda: self.module.set_slot_primary("c", "fast 2", "extra-local"),
            lambda: self.module.set_slot_fallback("c", "large", 0, "extra-local"),
            lambda: self.module.set_visual_substitute("c", "extra-local"),
        )
        with mock.patch.object(self.module, "_get_system_ram_gb", return_value=100), \
             mock.patch.object(self.module, "_load_local_models", return_value=inventory):
            for operation in operations:
                with self.subTest(operation=operation):
                    self._write_config("c", original)
                    path = self.config_dir / "c.json"
                    before = path.read_bytes()
                    with self.assertRaisesRegex(ValueError, "85% hard cap"):
                        operation()
                    self.assertEqual(path.read_bytes(), before)

    def test_missing_inventory_rejects_edit_without_writing(self):
        self._write_config("c", self._profile("local-a"))
        path = self.config_dir / "c.json"
        before = path.read_bytes()
        self.models_path.unlink()
        with self.assertRaisesRegex(ValueError, "inventory is unavailable"):
            self.module.set_slot_fallback("c", "large", 0, "local-b")
        self.assertEqual(path.read_bytes(), before)

    def test_failed_activation_leaves_pointer_bytes_unchanged(self):
        self._write_config("too-large", {
            "roles": {
                "large": {"primary": "large-local", "fallback": []},
            },
            "cells": {"analysis": {"gear4": {
                "depth": {"role": "large"},
            }}},
        })
        self.module.ACTIVE_POINTER_PATH.write_bytes(b'{"name":"keep-me"}\n')
        before = self.module.ACTIVE_POINTER_PATH.read_bytes()
        with mock.patch.object(self.module, "_get_system_ram_gb", return_value=100), \
             mock.patch.object(self.module, "_load_local_models", return_value=[
                 {"id": "large-local", "ram_gb": 86},
             ]):
            with self.assertRaisesRegex(ValueError, "85% hard cap"):
                self.module.set_active_name("too-large")
        self.assertEqual(self.module.ACTIVE_POINTER_PATH.read_bytes(), before)


class TestFreeLocalOverlay(_Fixture):
    @staticmethod
    def _cell(primary, *fallback):
        return {"primary": primary, "fallback": list(fallback)}

    def _cloud_free(self):
        cell = self._cell
        return {"name": "free", "preset_lineage": "free", "cells": {
            "utility": {
                "step1_cleanup": cell("cloud-small", "cloud-small-2"),
                "classification": cell("cloud-classify", "cloud-small-2"),
                "rag_planner": cell("cloud-plan", "cloud-small-2"),
                "gear2_rag_lookup": cell("cloud-fast-lookup", "cloud-fast-3"),
            },
            "analysis": {
                "gear4": {
                    "depth": cell("cloud-big-1", "cloud-big-3"),
                    "breadth": cell("cloud-big-2", "cloud-big-4"),
                },
                "gear3": {
                    "depth": cell("cloud-fast-1", "cloud-fast-3"),
                    "breadth": cell("cloud-fast-2", "cloud-fast-4"),
                },
            },
            "post_analysis": {
                "consolidation": cell("cloud-consolidate", "cloud-big-3"),
                "verification": cell("cloud-verify", "cloud-big-3"),
                "formatter": cell("cloud-format", "cloud-big-3"),
            },
        }}

    @staticmethod
    def _local(model_id, params, ram, family, **overrides):
        row = {
            "id": model_id,
            "parameters_b": params,
            "ram_gb": ram,
            "training_family": family,
            "context_window": 262_144,
            "vision_capable": True,
            "enabled": True,
            "status": "active",
        }
        row.update(overrides)
        return row

    def test_128gb_free_uses_94gb_and_reuses_pair_slots(self):
        config = self._cloud_free()
        locals_ = [
            self._local("local-big", 156, 73, "mistral"),
            self._local("local-fast", 32, 15, "qwen"),
            self._local("local-small", 11.9, 6, "qwen"),
        ]

        self.module._apply_free_local_overlay(
            config, local_models=locals_, system_ram_gb=128,
            toggles={"adversarial_diversity": False},
        )

        cells = config["cells"]
        self.assertEqual(cells["analysis"]["gear4"]["depth"]["primary"],
                         "local-big")
        self.assertEqual(cells["analysis"]["gear4"]["breadth"]["primary"],
                         "local-big")
        self.assertEqual(cells["analysis"]["gear3"]["depth"]["primary"],
                         "local-fast")
        self.assertEqual(cells["analysis"]["gear3"]["breadth"]["primary"],
                         "local-fast")
        self.assertEqual(cells["utility"]["step1_cleanup"]["primary"],
                         "local-small")
        self.assertEqual(
            cells["analysis"]["gear4"]["depth"]["fallback"][0],
            "cloud-big-1",
        )
        self.assertEqual(
            cells["post_analysis"]["verification"]["fallback"][0],
            "cloud-verify",
        )
        for section in (cells["utility"], cells["analysis"]["gear4"],
                        cells["analysis"]["gear3"], cells["post_analysis"]):
            for chain in section.values():
                self.assertFalse(any(mid.startswith("local-")
                                     for mid in chain.get("fallback", [])))
        allocation = self.module.profile_ram_allocation(
            config, system_ram_gb=128, local_models=locals_)
        self.assertEqual(allocation["allocated_local_ram_gb"], 94)
        self.assertLessEqual(allocation["allocated_local_ram_gb"],
                             allocation["automatic_target_gb"])
        self.assertFalse(config["diversity_override"])

    def test_diversity_adds_distinct_family_pairs_after_core_slots(self):
        config = self._cloud_free()
        locals_ = [
            self._local("big-a", 120, 70, "a"),
            self._local("big-a-older", 110, 60, "a"),
            self._local("big-b", 100, 50, "b"),
            self._local("fast-a", 40, 20, "a"),
            self._local("fast-b", 30, 15, "b"),
            self._local("small", 8, 5, "s"),
        ]

        self.module._apply_free_local_overlay(
            config, local_models=locals_, system_ram_gb=250,
            toggles={"adversarial_diversity": True},
        )

        gear4 = config["cells"]["analysis"]["gear4"]
        gear3 = config["cells"]["analysis"]["gear3"]
        self.assertEqual(gear4["depth"]["primary"], "big-a")
        self.assertEqual(gear4["breadth"]["primary"], "big-b")
        self.assertEqual(gear3["depth"]["primary"], "fast-a")
        self.assertEqual(gear3["breadth"]["primary"], "fast-b")
        self.assertTrue(config["diversity_override"])

    def test_vision_toggle_and_unusable_context_leave_locals_out(self):
        config = self._cloud_free()
        locals_ = [
            self._local("text-big", 100, 40, "a", vision_capable="false"),
            self._local("nan-big", 90, 35, "d", context_window=float("nan")),
            self._local("eligible-small", 8, 5, "c"),
        ]

        self.module._apply_free_local_overlay(
            config, local_models=locals_, system_ram_gb=128,
            toggles={"vision_only": True},
        )

        # Vision-only rejects text-big; a non-finite context window rejects
        # nan-big. Both big slots therefore stay on the cloud bake.
        self.assertEqual(
            config["cells"]["analysis"]["gear4"]["depth"]["primary"],
            "cloud-big-1",
        )
        self.assertEqual(
            config["cells"]["utility"]["step1_cleanup"]["primary"],
            "eligible-small",
        )

    def test_1m_context_floor_does_not_exclude_locals(self):
        """The 1M floor is a cloud control; it must not void the overlay.

        No local model ships a ~1M window, so applying the floor here once
        meant "never overlay a local" for every user with the toggle on —
        while the cloud bake it overlays kept 128k picks.
        """
        config = self._cloud_free()
        locals_ = [
            self._local("short-big", 100, 40, "a", context_window=899_999),
            self._local("short-small", 8, 5, "c", context_window=131_072),
        ]

        self.module._apply_free_local_overlay(
            config, local_models=locals_, system_ram_gb=128,
            toggles={"min_context_1m": True, "vision_only": True},
        )

        self.assertEqual(
            config["cells"]["analysis"]["gear4"]["depth"]["primary"],
            "short-big",
        )
        self.assertEqual(
            config["cells"]["utility"]["step1_cleanup"]["primary"],
            "short-small",
        )

    def test_stale_disabled_and_inactive_models_are_excluded(self):
        config = self._cloud_free()
        locals_ = [
            self._local("stale", 200, 50, "stale",
                        path=str(Path(self.tmpdir) / "missing-model")),
            self._local("disabled", 190, 50, "disabled", enabled=False),
            self._local("inactive", 180, 50, "inactive", status="inactive"),
            self._local("eligible", 100, 40, "eligible"),
        ]

        self.module._apply_free_local_overlay(
            config, local_models=locals_, system_ram_gb=128, toggles={})

        self.assertEqual(
            config["cells"]["analysis"]["gear4"]["depth"]["primary"],
            "eligible",
        )


class TestToggles(_Fixture):

    def test_get_infers_adversarial_from_breadth_populated(self):
        self._write_config("c", {
            "cells": {"analysis": {"gear4": {
                "depth": {"primary": "d"},
                "breadth": {"primary": "b"},
            }}},
        })
        t = self.module.get_toggles("c")
        self.assertTrue(t["adversarial_diversity"])
        self.assertFalse(t["vision_only"])

    def test_get_infers_adversarial_false_when_breadth_null(self):
        self._write_config("c", {
            "cells": {"analysis": {"gear4": {
                "depth": {"primary": "d"},
                "breadth": None,
            }}},
        })
        t = self.module.get_toggles("c")
        self.assertFalse(t["adversarial_diversity"])

    def test_get_reads_vision_only_from_auto_populate_metadata(self):
        self._write_config("c", {
            "cells": {},
            "_auto_populate_metadata": {"vision_only": True},
        })
        t = self.module.get_toggles("c")
        self.assertTrue(t["vision_only"])

    def test_saved_toggles_override_inferred(self):
        self._write_config("c", {
            "cells": {"analysis": {"gear4": {"breadth": {"primary": "b"}}}},
            "_auto_populate_metadata": {"vision_only": True},
            "toggles": {"adversarial_diversity": False, "vision_only": False},
        })
        t = self.module.get_toggles("c")
        self.assertFalse(t["adversarial_diversity"])
        self.assertFalse(t["vision_only"])

    def test_set_persists_partial_update(self):
        """Passing only one toggle should leave the other alone."""
        self._write_config("c", {
            "cells": {},
            "toggles": {"adversarial_diversity": True, "vision_only": True},
        })
        out = self.module.set_toggles("c", {"vision_only": False})
        self.assertTrue(out["adversarial_diversity"])  # unchanged
        self.assertFalse(out["vision_only"])           # updated
        # Verify on-disk
        with open(self.config_dir / "c.json") as f:
            data = json.load(f)
        self.assertEqual(data["toggles"]["adversarial_diversity"], True)
        self.assertEqual(data["toggles"]["vision_only"], False)

    def test_set_creates_toggles_block_when_missing(self):
        self._write_config("c", {"cells": {}})
        out = self.module.set_toggles("c", {"adversarial_diversity": True})
        self.assertTrue(out["adversarial_diversity"])
        with open(self.config_dir / "c.json") as f:
            self.assertIn("toggles", json.load(f))

    def test_set_preserves_other_top_level_fields(self):
        self._write_config("c", {
            "name": "c",
            "description": "keep me",
            "preset_lineage": "budget",
            "cells": {"utility": {"step1_cleanup": {"primary": "x"}}},
        })
        self.module.set_toggles("c", {"adversarial_diversity": True})
        with open(self.config_dir / "c.json") as f:
            data = json.load(f)
        self.assertEqual(data["description"], "keep me")
        self.assertEqual(data["preset_lineage"], "budget")
        self.assertIn("step1_cleanup", data["cells"]["utility"])

    def test_get_toggles_raises_for_missing_config(self):
        with self.assertRaises(FileNotFoundError):
            self.module.get_toggles("ghost")


class TestRuntimeOverlayConfigurations(_Fixture):
    """Default user-pipeline settings are seeds; live edits belong in runtime."""

    def setUp(self):
        super().setUp()
        self.module._DEFAULT_CONFIGURATIONS_DIR = self.config_dir

    def test_user_pipeline_reads_seed_when_no_runtime_overlay_exists(self):
        self._write_config("user-pipeline", {
            "cells": {},
            "toggles": {"vision_only": False, "adversarial_diversity": False},
        })
        t = self.module.get_toggles("user-pipeline")
        self.assertFalse(t["vision_only"])
        self.assertFalse(t["adversarial_diversity"])
        self.assertFalse((self.runtime_config_dir / "user-pipeline.json").exists())

    def test_user_pipeline_runtime_overlay_overrides_seed(self):
        self._write_config("user-pipeline", {
            "cells": {},
            "toggles": {"vision_only": False, "adversarial_diversity": False},
        })
        self._write_runtime_config("user-pipeline", {
            "cells": {},
            "toggles": {"vision_only": True, "adversarial_diversity": True},
        })
        t = self.module.get_toggles("user-pipeline")
        self.assertTrue(t["vision_only"])
        self.assertTrue(t["adversarial_diversity"])

    def test_user_pipeline_toggle_write_creates_runtime_overlay(self):
        self._write_config("user-pipeline", {
            "cells": {},
            "toggles": {"vision_only": False, "adversarial_diversity": False},
        })
        out = self.module.set_toggles("user-pipeline", {"vision_only": True})
        self.assertTrue(out["vision_only"])

        with open(self.config_dir / "user-pipeline.json") as f:
            seed = json.load(f)
        with open(self.runtime_config_dir / "user-pipeline.json") as f:
            runtime = json.load(f)
        self.assertFalse(seed["toggles"]["vision_only"])
        self.assertTrue(runtime["toggles"]["vision_only"])
        self.assertFalse(runtime["toggles"]["adversarial_diversity"])


class TestListConfigurations(_Fixture):
    """list_configurations() buckets preset + custom configs and
    summarizes each one to the three slot picks the pane card renders."""

    def _ap_config(self, name, lineage, big1, big2, small):
        """Build a config the way auto-populate writes them."""
        return {
            "name": name,
            "preset_lineage": lineage,
            "cells": {
                "utility": {
                    "step1_cleanup": {"primary": small, "fallback": []},
                },
                "analysis": {
                    "gear4": {
                        "depth": {"primary": big1, "fallback": []},
                        "breadth": ({"primary": big2, "fallback": []}
                                    if big2 else None),
                    },
                    "gear3": {"breadth": None},
                },
                "post_analysis": {},
            },
        }

    def test_empty_dir_returns_null_presets(self):
        # Re-create empty config dir
        import shutil
        shutil.rmtree(self.config_dir)
        self.config_dir.mkdir()
        result = self.module.list_configurations()
        self.assertEqual(set(result["presets"].keys()),
                         {"free", "budget", "speed", "premium"})
        for v in result["presets"].values():
            self.assertIsNone(v)
        self.assertEqual(result["customs"], [])

    def test_canonical_named_preset_files_picked_up(self):
        self._write_config("free", self._ap_config(
            "free", "free", "llama-70b", "nemotron", "llama-3b"))
        self._write_config("speed", self._ap_config(
            "speed", "speed", "qwen-plus", "kimi-k2", "nano-paid"))
        result = self.module.list_configurations()
        self.assertEqual(result["presets"]["free"]["big1"], "llama-70b")
        self.assertEqual(result["presets"]["free"]["big2"], "nemotron")
        self.assertEqual(result["presets"]["free"]["small"], "llama-3b")
        self.assertEqual(result["presets"]["speed"]["big1"], "qwen-plus")
        self.assertIsNone(result["presets"]["budget"])
        self.assertIsNone(result["presets"]["premium"])

    def test_preset_lineage_match_when_no_canonical_file(self):
        """When free.json isn't present but some-other-name.json carries
        preset_lineage=free, that file fills the slot."""
        self._write_config("my-free-bake", self._ap_config(
            "my-free-bake", "free", "llama-70b", "nemotron", "llama-3b"))
        result = self.module.list_configurations()
        self.assertEqual(result["presets"]["free"]["name"], "my-free-bake")

    def test_canonical_named_wins_over_lineage_tag(self):
        """If both free.json AND something-else.json claim preset_lineage=free,
        the canonical-named file wins."""
        self._write_config("free", self._ap_config(
            "free", "free", "llama-70b", "nemo", "llama-3b"))
        self._write_config("rogue", self._ap_config(
            "rogue", "free", "wrong-big1", "wrong-big2", "wrong-small"))
        result = self.module.list_configurations()
        self.assertEqual(result["presets"]["free"]["name"], "free")
        # The rogue file falls into customs since its lineage slot is taken
        custom_names = [c["name"] for c in result["customs"]]
        self.assertIn("rogue", custom_names)

    def test_background_default_excluded_from_customs(self):
        self._write_config("background-default", self._ap_config(
            "background-default", None, "x", "y", "z"))
        result = self.module.list_configurations()
        custom_names = [c["name"] for c in result["customs"]]
        self.assertNotIn("background-default", custom_names)

    def test_customs_include_user_named_configs(self):
        self._write_config("daily-driver", self._ap_config(
            "daily-driver", None, "qwen-plus", "kimi-k2", "nano"))
        self._write_config("msi-backfill", self._ap_config(
            "msi-backfill", None, "nano-free", "nemo-free", "nano-free"))
        result = self.module.list_configurations()
        custom_names = sorted(c["name"] for c in result["customs"])
        self.assertEqual(custom_names, ["daily-driver", "msi-backfill"])

    def test_big2_null_when_breadth_slot_is_null(self):
        """A configuration with adversarial off has breadth: null;
        the summary's big2 should be null too."""
        self._write_config("free", self._ap_config(
            "free", "free", "llama-70b", None, "llama-3b"))
        result = self.module.list_configurations()
        self.assertIsNone(result["presets"]["free"]["big2"])
        # Toggles default to adversarial=False when breadth is null
        self.assertFalse(result["presets"]["free"]["toggles"]["adversarial_diversity"])

    def test_active_name_and_toggles_included(self):
        self._write_config("free", self._ap_config(
            "free", "free", "llama-70b", "nemo", "llama-3b"))
        self.module.set_active_name("free")
        result = self.module.list_configurations()
        self.assertEqual(result["active_name"], "free")
        self.assertIn("adversarial_diversity", result["active_toggles"])

    def test_summary_includes_saved_toggles_when_present(self):
        config = self._ap_config(
            "free", "free", "llama-70b", "nemo", "llama-3b")
        config["toggles"] = {"adversarial_diversity": False, "vision_only": True}
        self._write_config("free", config)
        result = self.module.list_configurations()
        t = result["presets"]["free"]["toggles"]
        self.assertFalse(t["adversarial_diversity"])
        self.assertTrue(t["vision_only"])

    def test_summary_includes_loosening_log(self):
        config = self._ap_config(
            "free", "free", "llama-70b", "nemo", "llama-3b")
        config["_auto_populate_metadata"] = {
            "preset": "free",
            "vision_only": True,
            "loosening_log": {
                "utility.step1_cleanup": [
                    "vision_only dropped: no eligible free vision model"],
                "analysis.gear4.depth": [
                    "vision_only dropped: no eligible free vision model"],
            },
        }
        self._write_config("free", config)
        result = self.module.list_configurations()
        log = result["presets"]["free"]["loosening_log"]
        self.assertEqual(set(log.keys()),
                         {"utility.step1_cleanup", "analysis.gear4.depth"})
        self.assertEqual(
            log["utility.step1_cleanup"],
            ["vision_only dropped: no eligible free vision model"])

    def test_summary_loosening_log_defaults_empty(self):
        # No metadata at all (custom / legacy config)
        self._write_config("free", self._ap_config(
            "free", "free", "llama-70b", "nemo", "llama-3b"))
        result = self.module.list_configurations()
        self.assertEqual(result["presets"]["free"]["loosening_log"], {})

    def test_summary_loosening_log_tolerates_malformed_shapes(self):
        config = self._ap_config(
            "free", "free", "llama-70b", "nemo", "llama-3b")
        config["_auto_populate_metadata"] = {
            "loosening_log": {
                "cell.a": "bare string note",      # string → wrapped in list
                "cell.b": ["", "  ", "real note"],  # blanks dropped
                "cell.c": 42,                       # non-list/str → dropped
                "cell.d": [],                       # empty → dropped
            },
        }
        self._write_config("free", config)
        result = self.module.list_configurations()
        log = result["presets"]["free"]["loosening_log"]
        self.assertEqual(log, {
            "cell.a": ["bare string note"],
            "cell.b": ["real note"],
        })


class TestDuplicateAndCreate(_Fixture):
    """duplicate_configuration / create_blank_configuration / auto-naming."""

    def test_duplicate_with_explicit_new_name(self):
        self._write_config("source", {
            "name": "source",
            "preset_lineage": "budget",
            "cells": {"analysis": {"gear4": {"depth": {"primary": "p"}}}},
            "_auto_populate_metadata": {"loosening_log": {}},
        })
        created = self.module.duplicate_configuration("source", "my-copy")
        self.assertEqual(created, "my-copy")
        with open(self.config_dir / "my-copy.json") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "my-copy")
        self.assertEqual(data["preset_lineage"], "custom")
        self.assertNotIn("_auto_populate_metadata", data)  # stripped
        # Cells preserved
        self.assertEqual(data["cells"]["analysis"]["gear4"]["depth"]["primary"], "p")

    def test_duplicate_auto_names(self):
        self._write_config("source", {"cells": {}})
        n1 = self.module.duplicate_configuration("source")
        n2 = self.module.duplicate_configuration("source")
        self.assertEqual(n1, "Model Profile 01")
        self.assertEqual(n2, "Model Profile 02")

    def test_duplicate_skips_taken_auto_numbers(self):
        self._write_config("source", {"cells": {}})
        self._write_config("Configuration 01", {"cells": {}})
        self._write_config("Configuration 02", {"cells": {}})
        n = self.module.duplicate_configuration("source")
        self.assertEqual(n, "Model Profile 03")

    def test_duplicate_rejects_existing_name(self):
        self._write_config("source", {"cells": {}})
        self._write_config("taken", {"cells": {}})
        with self.assertRaises(ValueError):
            self.module.duplicate_configuration("source", "taken")

    def test_duplicate_rejects_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            self.module.duplicate_configuration("ghost")

    def test_create_blank_has_full_slot_skeleton(self):
        name = self.module.create_blank_configuration("scratch")
        self.assertEqual(name, "scratch")
        with open(self.config_dir / "scratch.json") as f:
            data = json.load(f)
        # All five workhorse / utility / post-analysis cells exist with
        # primary=None — UI shows red border until 3 are filled.
        self.assertIsNone(data["cells"]["utility"]["step1_cleanup"]["primary"])
        self.assertIsNone(data["cells"]["analysis"]["gear4"]["depth"]["primary"])
        self.assertIsNone(data["cells"]["analysis"]["gear4"]["breadth"])
        self.assertIsNone(data["cells"]["post_analysis"]["consolidation"]["primary"])

    def test_create_blank_auto_names_when_missing(self):
        name = self.module.create_blank_configuration()
        self.assertEqual(name, "Model Profile 01")


class TestDelete(_Fixture):

    def test_delete_removes_file(self):
        self._write_config("scratch", {"cells": {}})
        self.module.delete_configuration("scratch")
        self.assertFalse((self.config_dir / "scratch.json").exists())

    def test_delete_active_config_reverts_to_free(self):
        # Active config gets deleted; pointer auto-reverts to "free".
        self._write_config("free", {"cells": {}})
        self._write_config("active-one", {"cells": {}})
        self.module.set_active_name("active-one")
        self.module.delete_configuration("active-one")
        self.assertFalse((self.config_dir / "active-one.json").exists())
        self.assertEqual(self.module.get_active_name(), "free")

    def test_delete_inactive_config_keeps_active_pointer(self):
        # Deleting an inactive config doesn't disturb the active pointer.
        self._write_config("active-one", {"cells": {}})
        self._write_config("other", {"cells": {}})
        self.module.set_active_name("active-one")
        self.module.delete_configuration("other")
        self.assertEqual(self.module.get_active_name(), "active-one")

    def test_delete_refuses_system_configs(self):
        self._write_config("background-default", {"cells": {}})
        self._write_config("user-pipeline", {"cells": {}})
        with self.assertRaises(ValueError):
            self.module.delete_configuration("background-default")
        with self.assertRaises(ValueError):
            self.module.delete_configuration("user-pipeline")

    def test_delete_refuses_named_presets(self):
        # The four named presets (free/budget/speed/premium) are
        # also system-managed and cannot be deleted.
        for preset in ("free", "budget", "speed", "premium"):
            self._write_config(preset, {"cells": {}})
            with self.assertRaises(ValueError):
                self.module.delete_configuration(preset)

    def test_delete_missing_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            self.module.delete_configuration("ghost")


class TestFastSlot(_Fixture):
    """Coverage for the Fast slot (Chunks A–D, 2026-05-23):
      - SLOT_LABEL_TO_PATHS schema: fast 1 fans out to gear3.depth +
        utility.gear2_rag_lookup; fast 2 writes only to gear3.breadth.
      - set_slot_primary respects the fan-out.
      - _is_baseline_complete requires fast 1; fast 2 is an internal
        fallback/breadth path, not a card-visible baseline.
    """

    # ─── Schema ──────────────────────────────────────────────────────────
    def test_fast1_schema_fans_out_to_gear3_and_gear2_rag(self):
        paths = self.module.SLOT_LABEL_TO_PATHS["fast 1"]
        # Order isn't load-bearing — just that both cells are covered.
        as_tuples = {tuple(p) for p in paths}
        self.assertIn(("analysis", "gear3", "depth"), as_tuples)
        self.assertIn(("utility", "gear2_rag_lookup"), as_tuples)

    def test_fast2_schema_writes_only_gear3_breadth(self):
        paths = self.module.SLOT_LABEL_TO_PATHS["fast 2"]
        self.assertEqual([tuple(p) for p in paths],
                         [("analysis", "gear3", "breadth")])

    def test_big1_no_longer_fans_into_gear3_depth(self):
        """Chunk A handed gear3.depth off to fast 1. big 1 must not write
        it any more — otherwise picking a Big model would overwrite the
        Fast pick."""
        paths = self.module.SLOT_LABEL_TO_PATHS["big 1"]
        as_tuples = {tuple(p) for p in paths}
        self.assertNotIn(("analysis", "gear3", "depth"), as_tuples)

    # ─── set_slot_primary fan-out ────────────────────────────────────────
    def test_set_fast1_writes_both_gear3_depth_and_gear2_rag(self):
        self._write_config("c", {"cells": {}})
        self.module.set_slot_primary("c", "fast 1", "qwen/qwen-fast")
        with open(self.config_dir / "c.json") as f:
            cells = json.load(f)["cells"]
        self.assertEqual(cells["analysis"]["gear3"]["depth"]["primary"],
                         "qwen/qwen-fast")
        self.assertEqual(cells["utility"]["gear2_rag_lookup"]["primary"],
                         "qwen/qwen-fast")

    def test_set_fast2_writes_only_gear3_breadth(self):
        self._write_config("c", {"cells": {}})
        self.module.set_slot_primary("c", "fast 2", "anthropic/haiku")
        with open(self.config_dir / "c.json") as f:
            cells = json.load(f)["cells"]
        self.assertEqual(cells["analysis"]["gear3"]["breadth"]["primary"],
                         "anthropic/haiku")
        # Must NOT have spilled into Fast 1's cells
        self.assertNotIn("depth", cells.get("analysis", {}).get("gear3", {}))
        self.assertNotIn("gear2_rag_lookup", cells.get("utility", {}))

    def test_set_fast1_then_fast2_independent_writes(self):
        """Two sequential picks should not clobber each other — fast 1
        keeps its fan-out, fast 2 lands cleanly in gear3.breadth."""
        self._write_config("c", {"cells": {}})
        self.module.set_slot_primary("c", "fast 1", "qwen/q-primary")
        self.module.set_slot_primary("c", "fast 2", "anthropic/h-secondary")
        with open(self.config_dir / "c.json") as f:
            cells = json.load(f)["cells"]
        self.assertEqual(cells["analysis"]["gear3"]["depth"]["primary"],
                         "qwen/q-primary")
        self.assertEqual(cells["analysis"]["gear3"]["breadth"]["primary"],
                         "anthropic/h-secondary")
        self.assertEqual(cells["utility"]["gear2_rag_lookup"]["primary"],
                         "qwen/q-primary")

    # ─── _is_baseline_complete ───────────────────────────────────────────
    def _full_baseline(self, *, fast1="f1", fast2=None, adversarial=False):
        """Build a config with big1 + small filled + optional fast1/fast2
        and an explicit adversarial toggle. (No image cell: image
        generation left the configuration schema 2026-06-11.)"""
        cells = {
            "utility": {"step1_cleanup": {"primary": "s"}},
            "analysis": {
                "gear4": {"depth": {"primary": "b1"}, "breadth": None},
                "gear3": {
                    "depth": ({"primary": fast1} if fast1 else None),
                    "breadth": ({"primary": fast2} if fast2 else None),
                },
            },
        }
        if adversarial:
            cells["analysis"]["gear4"]["breadth"] = {"primary": "b2"}
        return {
            "cells": cells,
            "toggles": {"adversarial_diversity": adversarial,
                        "vision_only": False},
        }

    def test_baseline_incomplete_when_fast1_missing(self):
        config = self._full_baseline(fast1=None)
        self.assertFalse(self.module._is_baseline_complete(config))

    def test_baseline_complete_with_fast1_when_adversarial_off(self):
        config = self._full_baseline(fast1="f1", fast2=None, adversarial=False)
        self.assertTrue(self.module._is_baseline_complete(config))

    def test_baseline_complete_when_fast2_missing_and_adversarial_on(self):
        config = self._full_baseline(fast1="f1", fast2=None, adversarial=True)
        self.assertTrue(self.module._is_baseline_complete(config))

    def test_baseline_complete_with_fast2_present_and_adversarial_on(self):
        config = self._full_baseline(fast1="f1", fast2="f2", adversarial=True)
        self.assertTrue(self.module._is_baseline_complete(config))


class TestMinContext1mToggle(_Fixture):
    """The new min_context_1m preset toggle — the top-of-pane '1M context'
    header toggle that constrains preset picks to ~1M-context models.
    Mirrors the vision_only toggle pattern."""

    def setUp(self):
        super().setUp()
        # PRESET_TOGGLES_PATH is computed at import from the original
        # DATA_DIR, so redirect it explicitly into the temp dir for the
        # global preset-toggle tests.
        self._orig_preset_toggles = self.module.PRESET_TOGGLES_PATH
        self.module.PRESET_TOGGLES_PATH = self.data_dir / "preset-toggles.json"

    def tearDown(self):
        self.module.PRESET_TOGGLES_PATH = self._orig_preset_toggles
        super().tearDown()

    # ── per-config toggle (get_toggles / set_toggles / _infer_defaults) ──

    def test_default_is_false_when_no_metadata(self):
        self._write_config("c", {"cells": {}})
        t = self.module.get_toggles("c")
        self.assertIn("min_context_1m", t)
        self.assertFalse(t["min_context_1m"])

    def test_infers_true_from_auto_populate_metadata_min_context(self):
        # A preset baked with the context floor on stamps min_context=900000.
        self._write_config("c", {
            "cells": {},
            "_auto_populate_metadata": {"min_context": 900000},
        })
        t = self.module.get_toggles("c")
        self.assertTrue(t["min_context_1m"])

    def test_infers_false_when_min_context_none(self):
        self._write_config("c", {
            "cells": {},
            "_auto_populate_metadata": {"min_context": None},
        })
        self.assertFalse(self.module.get_toggles("c")["min_context_1m"])

    def test_saved_toggle_overrides_inferred(self):
        self._write_config("c", {
            "cells": {},
            "_auto_populate_metadata": {"min_context": 900000},
            "toggles": {"min_context_1m": False},
        })
        self.assertFalse(self.module.get_toggles("c")["min_context_1m"])

    def test_set_persists_min_context_1m(self):
        self._write_config("c", {"cells": {},
                                 "toggles": {"vision_only": True}})
        out = self.module.set_toggles("c", {"min_context_1m": True})
        self.assertTrue(out["min_context_1m"])
        self.assertTrue(out["vision_only"])  # untouched
        with open(self.config_dir / "c.json") as f:
            data = json.load(f)
        self.assertTrue(data["toggles"]["min_context_1m"])

    def test_infer_defaults_includes_key(self):
        defaults = self.module._infer_defaults({"cells": {}})
        self.assertIn("min_context_1m", defaults)
        self.assertFalse(defaults["min_context_1m"])

    def test_empty_toggles_includes_key(self):
        self.assertIn("min_context_1m", self.module._empty_toggles())
        self.assertFalse(self.module._empty_toggles()["min_context_1m"])

    # ── global preset toggle (get_preset_toggles / set_preset_toggles) ──

    def test_global_default_false(self):
        self.assertFalse(self.module.get_preset_toggles()["min_context_1m"])

    def test_global_set_and_get_roundtrip(self):
        self.module.set_preset_toggles({"min_context_1m": True})
        self.assertTrue(self.module.get_preset_toggles()["min_context_1m"])
        # Other toggles untouched by the partial update.
        self.assertFalse(self.module.get_preset_toggles()["vision_only"])

    def test_global_partial_update_leaves_others(self):
        self.module.set_preset_toggles({"vision_only": True})
        self.module.set_preset_toggles({"min_context_1m": True})
        toggles = self.module.get_preset_toggles()
        self.assertTrue(toggles["vision_only"])
        self.assertTrue(toggles["min_context_1m"])

    # ── bake threading: min_context_1m → populate_configuration(min_context=) ──

    def test_bake_threads_min_context_when_toggle_on(self):
        """bake_missing_presets reads the global min_context_1m toggle and
        passes min_context=900000 into populate_configuration."""
        captured = {}

        class _FakeAP:
            def registry_crossref(self, *a, **k):
                return {}

            def populate_configuration(self, preset_name, catalog,
                                       presets_config, **kwargs):
                captured["min_context"] = kwargs.get("min_context")
                return {"name": preset_name, "cells": {}, "toggles": {}}

        self._patch_bake(_FakeAP())
        self.module.set_preset_toggles({"min_context_1m": True})
        self.module.bake_missing_presets(force=True)
        self.assertEqual(captured["min_context"], 900000)

    def test_bake_threads_none_when_toggle_off(self):
        captured = {}

        class _FakeAP:
            def registry_crossref(self, *a, **k):
                return {}

            def populate_configuration(self, preset_name, catalog,
                                       presets_config, **kwargs):
                captured["min_context"] = kwargs.get("min_context")
                return {"name": preset_name, "cells": {}, "toggles": {}}

        self._patch_bake(_FakeAP())
        self.module.set_preset_toggles({"min_context_1m": False})
        self.module.bake_missing_presets(force=True)
        self.assertIsNone(captured["min_context"])

    def test_bake_threads_vendor_canonical_aliases(self):
        captured = {}

        class _FakeAP:
            def registry_crossref(self, *a, **k):
                return {
                    "routing_endpoint_ids": {
                        "gemini/gemini-3.1-flash-lite",
                    },
                    "canonical_aliases": {
                        "google/gemini-3.1-flash-lite":
                            "gemini/gemini-3.1-flash-lite",
                    },
                }

            def populate_configuration(self, preset_name, catalog,
                                       presets_config, **kwargs):
                captured["canonical_aliases"] = kwargs.get("canonical_aliases")
                captured["routing_endpoint_ids"] = kwargs.get(
                    "routing_endpoint_ids")
                return {"name": preset_name, "cells": {}, "toggles": {}}

        self._patch_bake(_FakeAP())
        self.module.bake_missing_presets(force=True)
        self.assertEqual(
            captured["canonical_aliases"]["google/gemini-3.1-flash-lite"],
            "gemini/gemini-3.1-flash-lite",
        )
        self.assertEqual(
            captured["routing_endpoint_ids"],
            {"gemini/gemini-3.1-flash-lite"},
        )

    def test_bake_adds_connected_subscription_candidate_to_every_gate_then_removes_it(self):
        captured = []
        subscription_id = "codex-subscription:sdk-gpt"
        candidate = {
            "id": subscription_id,
            "category": "chat",
            "provider": "openai",
            "size_bucket": "large",
            "aa_intelligence_index": 90,
            "output_tokens_per_second": 120,
            "or_ttft_ms": 350,
            "reasoning_model": True,
            "_subscription_selector_cost_per_m": 0.01,
        }

        class _FakeAP:
            def registry_crossref(self, *a, **k):
                return {
                    "registry_ids": {"m"},
                    "routing_endpoint_ids": {"m"},
                    "va_resolvable_ids": {"m"},
                }

            def populate_configuration(self, preset_name, catalog,
                                       presets_config, **kwargs):
                captured.append((
                    preset_name,
                    {model["id"] for model in catalog},
                    kwargs,
                ))
                return {"name": preset_name, "cells": {}, "toggles": {}}

        self._patch_bake(_FakeAP())
        import codex_subscription as codex_sub
        with mock.patch.object(
            codex_sub, "selector_candidates",
            side_effect=[[candidate], []],
        ):
            self.module.bake_missing_presets(force=True)
            self.module.bake_missing_presets(force=True)

        connected_calls = captured[:len(self.module.PRESET_ORDER)]
        disconnected_calls = captured[len(self.module.PRESET_ORDER):]
        self.assertEqual(
            [name for name, _catalog, _kwargs in connected_calls],
            self.module.PRESET_ORDER,
        )
        for _name, catalog_ids, kwargs in connected_calls:
            self.assertIn(subscription_id, catalog_ids)
            self.assertIn(subscription_id, kwargs["registry_ids"])
            self.assertIn(subscription_id, kwargs["routing_endpoint_ids"])
            self.assertIn(subscription_id, kwargs["va_resolvable_ids"])
            self.assertEqual(kwargs["tokens_per_sec"][subscription_id], 120)
            self.assertEqual(kwargs["latency_ms"][subscription_id], 350)
            self.assertIn(subscription_id, kwargs["reasoning_model_ids"])
        for _name, catalog_ids, kwargs in disconnected_calls:
            self.assertNotIn(subscription_id, catalog_ids)
            self.assertNotIn(subscription_id, kwargs["registry_ids"])
            self.assertNotIn(subscription_id, kwargs["routing_endpoint_ids"])

    def _patch_bake(self, fake_ap):
        """Wire bake_missing_presets to use a fake auto-populate module +
        in-temp catalog/presets so we can capture the threaded args without
        running the real picker or touching ~/ora."""
        import importlib
        ac = self.module
        # ORA_HOME drives the presets/catalog/script paths inside the bake.
        cfg = Path(self.tmpdir) / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "configuration-presets.json").write_text(json.dumps({"presets": {}}))
        (cfg / "model-catalog.json").write_text(
            json.dumps({"models": [{"id": "m", "context_window": 1000000}]}))
        (Path(self.tmpdir) / "scripts").mkdir(parents=True, exist_ok=True)
        (Path(self.tmpdir) / "scripts" / "auto-populate-configuration.py").write_text("# stub\n")

        self._orig_ora_home = ac.ORA_HOME
        ac.ORA_HOME = Path(self.tmpdir)

        # Patch the dynamic-import machinery so exec_module yields the fake.
        self._orig_spec = importlib.util.spec_from_file_location
        self._orig_modfrom = importlib.util.module_from_spec

        def _fake_spec(name, path):
            class _S:
                loader = type("L", (), {"exec_module": staticmethod(lambda m: None)})()
            return _S()

        def _fake_modfrom(spec):
            return fake_ap

        importlib.util.spec_from_file_location = _fake_spec
        importlib.util.module_from_spec = _fake_modfrom

        def _restore():
            ac.ORA_HOME = self._orig_ora_home
            importlib.util.spec_from_file_location = self._orig_spec
            importlib.util.module_from_spec = self._orig_modfrom
        self.addCleanup(_restore)


class TestPresetBakeCauses(_Fixture):
    """An empty preset card has to say why it is empty.

    Before this, a preset that never baked and a preset whose picker blew up
    both arrived at the Models pane as the same silent ``null``. These tests
    pin the cause to the preset it belongs to, and pin it disappearing again
    the moment that preset exists.
    """

    def setUp(self):
        super().setUp()
        self.module._bake_errors.clear()
        self.addCleanup(self.module._bake_errors.clear)

    def _arm_bake(self, fake_ap=None, *, write_catalog=True):
        """Point the bake at an in-temp catalog/presets pair and, when a fake
        picker is supplied, at that instead of the real one."""
        import importlib
        ac = self.module
        cfg = Path(self.tmpdir) / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "configuration-presets.json").write_text(json.dumps({"presets": {}}))
        if write_catalog:
            (cfg / "model-catalog.json").write_text(
                json.dumps({"models": [{"id": "m"}]}))
        (Path(self.tmpdir) / "scripts").mkdir(parents=True, exist_ok=True)
        (Path(self.tmpdir) / "scripts" / "auto-populate-configuration.py").write_text("# stub\n")

        orig_home = ac.ORA_HOME
        ac.ORA_HOME = Path(self.tmpdir)
        orig_spec = importlib.util.spec_from_file_location
        orig_modfrom = importlib.util.module_from_spec

        if fake_ap is not None:
            def _fake_spec(name, path):
                class _S:
                    loader = type(
                        "L", (), {"exec_module": staticmethod(lambda m: None)})()
                return _S()

            importlib.util.spec_from_file_location = _fake_spec
            importlib.util.module_from_spec = lambda spec: fake_ap

        def _restore():
            ac.ORA_HOME = orig_home
            importlib.util.spec_from_file_location = orig_spec
            importlib.util.module_from_spec = orig_modfrom
        self.addCleanup(_restore)

    @staticmethod
    def _fake_picker(failing: dict):
        """A stand-in picker that fills every preset except the named ones."""
        class _AP:
            @staticmethod
            def registry_crossref(path=None):
                return {}

            @staticmethod
            def populate_configuration(preset_name, catalog, presets, **kwargs):
                if preset_name in failing:
                    raise failing[preset_name]
                return {
                    "preset_lineage": preset_name,
                    "cells": {
                        "utility": {"step1_cleanup": {"primary": "small", "fallback": []}},
                        "analysis": {
                            "gear4": {"depth": {"primary": "big", "fallback": []},
                                      "breadth": None},
                            "gear3": {"depth": {"primary": "fast", "fallback": []},
                                      "breadth": None},
                        },
                        "post_analysis": {},
                    },
                }
        return _AP

    def test_a_missing_catalog_is_reported_against_every_preset(self):
        self._arm_bake(write_catalog=False)
        self.assertEqual(self.module.bake_missing_presets(force=True), [])
        errors = self.module.preset_bake_errors()
        self.assertEqual(set(errors), set(self.module.PRESET_ORDER))
        for cause in errors.values():
            self.assertIn("model catalog is missing", cause)
            self.assertIn("model-catalog.json", cause)

    def test_one_preset_that_raises_does_not_hide_its_cause(self):
        boom = ValueError("no candidate met the 80 tokens/second floor")
        self._arm_bake(self._fake_picker({"speed": boom}))
        baked = self.module.bake_missing_presets(force=True)
        self.assertNotIn("speed", baked)
        errors = self.module.preset_bake_errors()
        self.assertEqual(set(errors), {"speed"})
        self.assertEqual(
            errors["speed"],
            "ValueError: no candidate met the 80 tokens/second floor")

    def test_the_cause_reaches_the_pane_payload_for_that_slot_only(self):
        boom = ValueError("catalog held no free model")
        self._arm_bake(self._fake_picker({"free": boom}))
        self.module.bake_missing_presets(force=True)
        payload = self.module.list_configurations()
        self.assertIsNone(payload["presets"]["free"])
        self.assertEqual(set(payload["preset_errors"]), {"free"})
        self.assertIn("catalog held no free model", payload["preset_errors"]["free"])
        # Slots that did bake carry no error at all.
        for name in ("budget", "speed", "premium"):
            self.assertIsNotNone(payload["presets"][name])
            self.assertNotIn(name, payload["preset_errors"])

    def test_a_bake_that_cannot_start_records_against_presets_that_exist(self):
        # What the preset_bake_errors docstring now says out loud: when the
        # whole bake aborts, nothing was attempted for any preset, so the
        # cause lands on every selected name — including ones with a
        # perfectly good file on disk. The pane never sees those, because
        # list_configurations only reports a cause for an empty slot.
        self._write_config("budget", {
            "preset_lineage": "budget",
            "cells": {
                "utility": {"step1_cleanup": {"primary": "small", "fallback": []}},
                "analysis": {
                    "gear4": {"depth": {"primary": "big", "fallback": []},
                              "breadth": None},
                    "gear3": {"depth": {"primary": "fast", "fallback": []},
                              "breadth": None},
                },
                "post_analysis": {},
            },
        })
        self._arm_bake(write_catalog=False)
        self.assertEqual(self.module.bake_missing_presets(force=True), [])
        self.assertIn("budget", self.module.preset_bake_errors())
        payload = self.module.list_configurations()
        self.assertIsNotNone(payload["presets"]["budget"])
        self.assertNotIn("budget", payload["preset_errors"])

    def test_a_later_success_clears_the_earlier_cause(self):
        self._arm_bake(self._fake_picker({"premium": RuntimeError("transient")}))
        self.module.bake_missing_presets(force=True)
        self.assertIn("premium", self.module.preset_bake_errors())
        self._arm_bake(self._fake_picker({}))
        self.module.bake_missing_presets(force=True)
        self.assertEqual(self.module.preset_bake_errors(), {})
        self.assertEqual(self.module.list_configurations()["preset_errors"], {})

    # ── Regenerating over an existing preset has to say so ─────────────
    #
    # ``force=True`` is how a toggle flip and the installer redo the picks,
    # and replacing the file is the point of it. Doing it in silence is not:
    # a user who hand-picked models into a preset lost them on the next
    # re-run with nothing in any log to explain where they went.

    def _bake_output(self, **kwargs):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            baked = self.module.bake_missing_presets(**kwargs)
        return baked, buffer.getvalue()

    def _seed_preset_file(self, name):
        self._write_config(name, {
            "name": name,
            "preset_lineage": name,
            "description": "hand-edited by the user",
            "cells": {
                "utility": {"step1_cleanup": {"primary": "chosen/by-hand",
                                              "fallback": []}},
                "analysis": {
                    "gear4": {"depth": {"primary": "chosen/by-hand",
                                        "fallback": []}, "breadth": None},
                    "gear3": {"depth": {"primary": "chosen/by-hand",
                                        "fallback": []}, "breadth": None},
                },
                "post_analysis": {},
            },
        })

    def test_replacing_an_existing_preset_logs_one_line_naming_the_file(self):
        self._seed_preset_file("speed")
        self._arm_bake(self._fake_picker({}))
        baked, output = self._bake_output(force=True)
        self.assertIn("speed", baked)
        replaced = [line for line in output.splitlines()
                    if "replacing the existing configuration" in line]
        self.assertEqual(len(replaced), 1, output)
        self.assertIn("[presets] speed:", replaced[0])
        self.assertIn(str(self.config_dir / "speed.json"), replaced[0])
        self.assertIn("overwritten", replaced[0])
        # The picks really were replaced — the line is not decorative.
        with open(self.config_dir / "speed.json") as f:
            self.assertEqual(
                json.load(f)["cells"]["analysis"]["gear4"]["depth"]["primary"],
                "big")

    def test_a_first_time_bake_is_not_noisier_for_it(self):
        self._arm_bake(self._fake_picker({}))
        baked, output = self._bake_output(force=True)
        self.assertEqual(set(baked), set(self.module.PRESET_ORDER))
        self.assertNotIn("replacing the existing configuration", output)

    def test_only_the_presets_actually_replaced_are_announced(self):
        self._seed_preset_file("premium")
        self._arm_bake(self._fake_picker({}))
        _baked, output = self._bake_output(force=True)
        announced = [line for line in output.splitlines()
                     if "replacing the existing configuration" in line]
        self.assertEqual(len(announced), 1, output)
        self.assertIn("[presets] premium:", announced[0])

    def test_an_unforced_bake_leaves_the_existing_file_alone_and_silently(self):
        self._seed_preset_file("free")
        self._arm_bake(self._fake_picker({}))
        baked, output = self._bake_output()
        self.assertNotIn("free", baked)
        self.assertNotIn("replacing the existing configuration", output)
        with open(self.config_dir / "free.json") as f:
            self.assertEqual(
                json.load(f)["cells"]["analysis"]["gear4"]["depth"]["primary"],
                "chosen/by-hand")

    # ── Who hears what the bake has to say ─────────────────────────────
    #
    # A bake writes two things nobody else can reconstruct: why a preset did
    # not bake, and the warning that a forced one has just overwritten
    # hand-picked slots. Printing them is right under the server, where stdout
    # is the log. It is not right under the installer, which calls this
    # in-process and keeps its own install.log — the file it tells the user to
    # read afterwards. So a caller can hand in a writer, and the same lines go
    # wherever that caller keeps its record.

    def _bake_to_writer(self, **kwargs):
        """Bake with a supplied writer, capturing stdout as well.

        Both are returned so a test can assert not just that the writer got
        the line but that stdout was not written to behind its back.
        """
        collected: list[str] = []
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            baked = self.module.bake_missing_presets(
                log=collected.append, **kwargs)
        return baked, collected, buffer.getvalue()

    def test_a_supplied_writer_gets_the_replacement_warning(self):
        self._seed_preset_file("speed")
        self._arm_bake(self._fake_picker({}))
        baked, collected, stdout = self._bake_to_writer(force=True)
        self.assertIn("speed", baked)
        replaced = [line for line in collected
                    if "replacing the existing configuration" in line]
        self.assertEqual(len(replaced), 1, collected)
        self.assertIn("[presets] speed:", replaced[0])
        self.assertIn(str(self.config_dir / "speed.json"), replaced[0])
        self.assertIn("overwritten", replaced[0])
        # And it went there instead of to stdout, not as well as.
        self.assertEqual(stdout, "")

    def test_a_supplied_writer_gets_the_cause_a_preset_did_not_bake(self):
        # The cause that would otherwise vanish: force=True over a preset file
        # that already exists, and the picker raises. The file survives, so
        # the preset is not "missing" and no caller can recover the reason
        # from the listing — this line is the only place it is said.
        self._seed_preset_file("premium")
        self._arm_bake(self._fake_picker(
            {"premium": ValueError("no candidate met the floor")}))
        _baked, collected, stdout = self._bake_to_writer(force=True)
        causes = [line for line in collected if "did not bake" in line]
        self.assertEqual(len(causes), 1, collected)
        self.assertIn("[presets] premium did not bake — "
                      "ValueError: no candidate met the floor", causes[0])
        self.assertEqual(stdout, "")
        self.assertTrue((self.config_dir / "premium.json").exists())

    def test_a_supplied_writer_gets_a_bake_that_could_not_start(self):
        self._arm_bake(write_catalog=False)
        baked, collected, stdout = self._bake_to_writer(force=True)
        self.assertEqual(baked, [])
        self.assertEqual(len(collected), 1, collected)
        self.assertIn("bake could not run", collected[0])
        self.assertIn("model catalog is missing", collected[0])
        self.assertEqual(stdout, "")

    def test_a_first_time_bake_says_nothing_to_the_writer_either(self):
        # The installer's ordinary case. Routing these lines somewhere new
        # must not turn a clean first install into a wall of text.
        self._arm_bake(self._fake_picker({}))
        baked, collected, stdout = self._bake_to_writer(force=True)
        self.assertEqual(set(baked), set(self.module.PRESET_ORDER))
        self.assertEqual(collected, [])
        self.assertEqual(stdout, "")

    def test_the_warning_fires_once_per_file_it_replaces(self):
        for name in ("free", "speed"):
            self._seed_preset_file(name)
        self._arm_bake(self._fake_picker({}))
        _baked, collected, _stdout = self._bake_to_writer(force=True)
        replaced = [line for line in collected
                    if "replacing the existing configuration" in line]
        self.assertEqual(len(replaced), 2, collected)
        self.assertIn("[presets] free:", replaced[0])
        self.assertIn("[presets] speed:", replaced[1])

    def test_a_caller_that_supplies_nothing_still_gets_stdout(self):
        # The server's call, unchanged: no writer, and the line lands on
        # stdout exactly where the server log picks it up.
        import inspect
        signature = inspect.signature(self.module.bake_missing_presets)
        self.assertIsNone(signature.parameters["log"].default)
        self.assertEqual(signature.parameters["log"].kind,
                         inspect.Parameter.KEYWORD_ONLY)
        self._seed_preset_file("budget")
        self._arm_bake(self._fake_picker({}))
        _baked, output = self._bake_output(force=True)
        self.assertIn("[presets] budget: replacing the existing configuration",
                      output)


if __name__ == "__main__":
    unittest.main()
