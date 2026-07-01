"""Tests for the G1.35×G1.33 engine binding: a container project's execution
defaults (model profile + output style) actually drive dispatch/style.

Covers router._resolve_config_name (project model-profile → config name) and
boot._resolve_effective_style_id (container-record output_style fallback)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ORCH = os.path.join(_REPO, "orchestrator")
for _p in (_REPO, _ORCH):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class RouterProjectProfileTests(unittest.TestCase):
    """router._resolve_config_name honors the active project's model profile."""

    @classmethod
    def setUpClass(cls):
        from router import Router
        cls.router = Router()  # real routing-config + seed configurations

    def setUp(self):
        # router.py imports `from orchestrator import active_project / project_meta`.
        import orchestrator.active_project as ap
        import orchestrator.project_meta as pm
        self.ap, self.pm = ap, pm
        self._orig = (ap.get_active_project, pm.read_project_meta)

    def tearDown(self):
        self.ap.get_active_project, self.pm.read_project_meta = self._orig

    def _patch(self, nexus, rec):
        self.ap.get_active_project = lambda: nexus
        self.pm.read_project_meta = lambda n, *a, **k: rec

    def test_explicit_config_name_wins(self):
        # A per-run config_name (the closest override) is honored as-is.
        self._patch("proj", {"default_model_profile": "user-pipeline"})
        self.assertEqual(
            self.router._resolve_config_name("background-default", "interactive"),
            "background-default")

    def test_project_profile_used_when_resolvable(self):
        self._patch("proj", {"default_model_profile": "user-pipeline"})
        self.assertEqual(
            self.router._resolve_config_name(None, "interactive"), "user-pipeline")

    def test_unresolvable_profile_falls_through(self):
        # A stored profile that isn't a real configuration must NOT be returned;
        # dispatch falls back to the account-wide active configuration.
        self._patch("proj", {"default_model_profile": "no-such-config-xyz"})
        got = self.router._resolve_config_name(None, "interactive")
        self.assertNotEqual(got, "no-such-config-xyz")

    def test_general_ignores_project(self):
        self._patch("general", {"default_model_profile": "user-pipeline"})
        got = self.router._resolve_config_name(None, "interactive")
        self.assertNotEqual(got, "user-pipeline")

    def test_no_profile_falls_through(self):
        self._patch("proj", {"default_model_profile": ""})
        got = self.router._resolve_config_name(None, "interactive")
        self.assertNotEqual(got, "")  # empty profile is skipped


class BootStyleFallbackTests(unittest.TestCase):
    """boot._resolve_effective_style_id falls back to the container record."""

    def setUp(self):
        import boot
        # boot's function imports the TOP-LEVEL modules first.
        import active_project as ap
        import project_registry as pr
        import project_meta as pm
        import user_settings as us
        self.boot, self.ap, self.pr, self.pm, self.us = boot, ap, pr, pm, us
        self._orig = (ap.get_active_project, pr.get_project,
                      pm.read_project_meta, us.get_setting)

    def tearDown(self):
        (self.ap.get_active_project, self.pr.get_project,
         self.pm.read_project_meta, self.us.get_setting) = self._orig

    def test_container_record_output_style(self):
        self.ap.get_active_project = lambda: "my-proj"
        self.pr.get_project = lambda n, *a, **k: None  # container-only → no manifest
        self.pm.read_project_meta = lambda n, *a, **k: {"output_style": "conversational"}
        self.assertEqual(self.boot._resolve_effective_style_id({}), "conversational")

    def test_manifest_style_still_wins(self):
        # A plugin project with a manifest default_style_id keeps priority.
        class _P:
            default_style_id = "from-manifest"
        self.ap.get_active_project = lambda: "plugin-proj"
        self.pr.get_project = lambda n, *a, **k: _P()
        self.pm.read_project_meta = lambda n, *a, **k: {"output_style": "conversational"}
        self.assertEqual(self.boot._resolve_effective_style_id({}), "from-manifest")

    def test_general_ignores_record(self):
        self.ap.get_active_project = lambda: "general"
        self.pr.get_project = lambda n, *a, **k: None
        self.pm.read_project_meta = lambda n, *a, **k: {"output_style": "conversational"}
        self.us.get_setting = lambda k, *a, **kw: None
        self.assertIsNone(self.boot._resolve_effective_style_id({}))


if __name__ == "__main__":
    unittest.main()
