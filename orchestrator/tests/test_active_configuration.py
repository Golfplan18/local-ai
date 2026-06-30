"""Tests for orchestrator/active_configuration.py — the active-config
pointer + per-configuration toggle persistence used by the V3 Models
pane header strip (install Chunk 10 step 3)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.runtime_config_dir = (
            Path(self.tmpdir) / "data" / "runtime" / "config" / "configurations")
        self.data_dir.mkdir(parents=True)
        self.config_dir.mkdir(parents=True)
        self._orig_data = ac.DATA_DIR
        self._orig_pointer = ac.ACTIVE_POINTER_PATH
        self._orig_config = ac.CONFIGURATIONS_DIR
        self._orig_default_config = ac._DEFAULT_CONFIGURATIONS_DIR
        self._orig_runtime_config = ac.RUNTIME_CONFIGURATIONS_DIR
        ac.DATA_DIR = self.data_dir
        ac.ACTIVE_POINTER_PATH = self.data_dir / "active-configuration.json"
        ac.CONFIGURATIONS_DIR = self.config_dir
        ac.RUNTIME_CONFIGURATIONS_DIR = self.runtime_config_dir

    def tearDown(self):
        self.module.DATA_DIR = self._orig_data
        self.module.ACTIVE_POINTER_PATH = self._orig_pointer
        self.module.CONFIGURATIONS_DIR = self._orig_config
        self.module._DEFAULT_CONFIGURATIONS_DIR = self._orig_default_config
        self.module.RUNTIME_CONFIGURATIONS_DIR = self._orig_runtime_config

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
        self.assertEqual(n1, "Configuration 01")
        self.assertEqual(n2, "Configuration 02")

    def test_duplicate_skips_taken_auto_numbers(self):
        self._write_config("source", {"cells": {}})
        self._write_config("Configuration 01", {"cells": {}})
        self._write_config("Configuration 02", {"cells": {}})
        n = self.module.duplicate_configuration("source")
        self.assertEqual(n, "Configuration 03")

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
        self.assertEqual(name, "Configuration 01")


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


if __name__ == "__main__":
    unittest.main()
