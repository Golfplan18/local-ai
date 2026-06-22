"""Runtime overlay tests for named model configurations."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))

import runtime_paths as rp  # noqa: E402
import router as router_module  # noqa: E402
from router import Router  # noqa: E402


class TestRuntimeConfigurationOverlay(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.seed_config_dir = self.tmpdir / "config" / "configurations"
        self.runtime_config_dir = (
            self.tmpdir / "data" / "runtime" / "config" / "configurations")
        self.seed_config_dir.mkdir(parents=True)
        self.runtime_config_dir.mkdir(parents=True)

        self._orig_rp_config_dir = rp.CONFIG_DIR
        self._orig_rp_runtime_config_dir = rp.RUNTIME_CONFIGURATIONS_DIR
        self._orig_router_config_dir = router_module.CONFIGURATIONS_DIR
        self._orig_router_default_config_dir = router_module._DEFAULT_CONFIGURATIONS_DIR

        rp.CONFIG_DIR = self.tmpdir / "config"
        rp.RUNTIME_CONFIGURATIONS_DIR = self.runtime_config_dir
        router_module.CONFIGURATIONS_DIR = self.seed_config_dir
        router_module._DEFAULT_CONFIGURATIONS_DIR = self.seed_config_dir

    def tearDown(self):
        rp.CONFIG_DIR = self._orig_rp_config_dir
        rp.RUNTIME_CONFIGURATIONS_DIR = self._orig_rp_runtime_config_dir
        router_module.CONFIGURATIONS_DIR = self._orig_router_config_dir
        router_module._DEFAULT_CONFIGURATIONS_DIR = self._orig_router_default_config_dir
        shutil.rmtree(self.tmpdir)

    def test_runtime_paths_write_user_pipeline_to_ignored_overlay(self):
        self.assertEqual(
            rp.configuration_path("user-pipeline", for_write=True),
            self.runtime_config_dir / "user-pipeline.json",
        )

    def test_runtime_paths_read_user_pipeline_seed_until_overlay_exists(self):
        self.assertEqual(
            rp.configuration_path("user-pipeline"),
            self.seed_config_dir / "user-pipeline.json",
        )
        (self.runtime_config_dir / "user-pipeline.json").write_text("{}")
        self.assertEqual(
            rp.configuration_path("user-pipeline"),
            self.runtime_config_dir / "user-pipeline.json",
        )

    def test_router_prefers_user_pipeline_runtime_overlay_when_present(self):
        router = Router.__new__(Router)
        self.assertEqual(
            router._configuration_path("user-pipeline"),
            self.seed_config_dir / "user-pipeline.json",
        )
        (self.runtime_config_dir / "user-pipeline.json").write_text("{}")
        self.assertEqual(
            router._configuration_path("user-pipeline"),
            self.runtime_config_dir / "user-pipeline.json",
        )


if __name__ == "__main__":
    unittest.main()
