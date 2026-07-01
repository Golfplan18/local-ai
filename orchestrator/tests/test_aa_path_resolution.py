#!/usr/bin/env python3
"""AA data-path resolution tests (scripts/sync_model_registry.py).

Locks in the 2026-07-01 fix: key presence auto-activates the API path.
The old chain consulted user_settings.get_setting("external_apis.aa_path"),
which — because DEFAULTS carried "scrape" and get_setting deep-merges
DEFAULTS — returned "scrape" unconditionally and made the key-presence
step unreachable. Resolution is now CLI flag → ORA_AA_PATH env →
key presence → "scrape".

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_aa_path_resolution -v
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRIPT = REPO / "scripts" / "sync_model_registry.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_sync_mr_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ResolveAAPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def setUp(self):
        self._saved_env = os.environ.get("ORA_AA_PATH")
        os.environ.pop("ORA_AA_PATH", None)
        self._saved_loader = self.mod._load_aa_api_key

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("ORA_AA_PATH", None)
        else:
            os.environ["ORA_AA_PATH"] = self._saved_env
        self.mod._load_aa_api_key = self._saved_loader

    def _args(self, aa_path=None):
        return types.SimpleNamespace(aa_path=aa_path)

    def test_cli_flag_wins(self):
        self.mod._load_aa_api_key = lambda: "some-key"
        self.assertEqual(self.mod._resolve_aa_path(self._args("scrape")), "scrape")
        self.assertEqual(self.mod._resolve_aa_path(self._args("api")), "api")

    def test_env_var_wins_over_key(self):
        self.mod._load_aa_api_key = lambda: "some-key"
        os.environ["ORA_AA_PATH"] = "scrape"
        self.assertEqual(self.mod._resolve_aa_path(self._args()), "scrape")

    def test_key_presence_auto_activates_api(self):
        # The core regression: a configured key alone must flip to "api".
        self.mod._load_aa_api_key = lambda: "some-key"
        self.assertEqual(self.mod._resolve_aa_path(self._args()), "api")

    def test_no_key_defaults_to_scrape(self):
        self.mod._load_aa_api_key = lambda: ""
        self.assertEqual(self.mod._resolve_aa_path(self._args()), "scrape")

    def test_stored_setting_no_longer_consulted(self):
        # Even if a legacy panel wrote external_apis.aa_path, resolution
        # must not read user_settings — key presence decides.
        self.mod._load_aa_api_key = lambda: "some-key"
        sys.path.insert(0, str(REPO / "orchestrator"))
        try:
            import user_settings  # noqa: F401 — present in this repo
            saved = user_settings.get_setting
            user_settings.get_setting = lambda *_a, **_k: "scrape"
            try:
                self.assertEqual(self.mod._resolve_aa_path(self._args()), "api")
            finally:
                user_settings.get_setting = saved
        except ImportError:  # pragma: no cover
            self.skipTest("user_settings not importable")


if __name__ == "__main__":
    unittest.main()
