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
        self.data_dir.mkdir(parents=True)
        self.config_dir.mkdir(parents=True)
        self._orig_data = ac.DATA_DIR
        self._orig_pointer = ac.ACTIVE_POINTER_PATH
        self._orig_config = ac.CONFIGURATIONS_DIR
        ac.DATA_DIR = self.data_dir
        ac.ACTIVE_POINTER_PATH = self.data_dir / "active-configuration.json"
        ac.CONFIGURATIONS_DIR = self.config_dir

    def tearDown(self):
        self.module.DATA_DIR = self._orig_data
        self.module.ACTIVE_POINTER_PATH = self._orig_pointer
        self.module.CONFIGURATIONS_DIR = self._orig_config

    def _write_config(self, name, payload):
        with open(self.config_dir / f"{name}.json", "w") as f:
            json.dump(payload, f)


class TestActivePointer(_Fixture):

    def test_missing_pointer_returns_default(self):
        self.assertEqual(self.module.get_active_name(),
                         self.module.DEFAULT_ACTIVE_NAME)

    def test_set_and_get_roundtrip(self):
        self._write_config("optimum-bake", {"name": "optimum-bake", "cells": {}})
        self.module.set_active_name("optimum-bake")
        self.assertEqual(self.module.get_active_name(), "optimum-bake")

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
            "preset_lineage": "optimum",
            "cells": {"utility": {"step1_cleanup": {"primary": "x"}}},
        })
        self.module.set_toggles("c", {"adversarial_diversity": True})
        with open(self.config_dir / "c.json") as f:
            data = json.load(f)
        self.assertEqual(data["description"], "keep me")
        self.assertEqual(data["preset_lineage"], "optimum")
        self.assertIn("step1_cleanup", data["cells"]["utility"])

    def test_get_toggles_raises_for_missing_config(self):
        with self.assertRaises(FileNotFoundError):
            self.module.get_toggles("ghost")


if __name__ == "__main__":
    unittest.main()
