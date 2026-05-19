#!/usr/bin/env python3
"""Install Chunk 7 (Solo profile) — install.py smoke tests.

Verifies the install script's structure and step contract. Live
network calls are not exercised here (catalog refresh has its own
test file); these tests confirm the install scaffold + state
machine work correctly.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

SPEC = importlib.util.spec_from_file_location(
    "install_script", REPO_ROOT / "scripts" / "install.py",
)
install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)


class TestDeploymentProfiles(unittest.TestCase):
    def test_solo_supported(self):
        self.assertTrue(install.DEPLOYMENT_PROFILES["solo"]["supported_now"])

    def test_hybrid_scaffolded_not_supported_yet(self):
        self.assertFalse(install.DEPLOYMENT_PROFILES["hybrid"]["supported_now"])

    def test_organization_scaffolded_not_supported_yet(self):
        self.assertFalse(install.DEPLOYMENT_PROFILES["organization"]["supported_now"])


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path_patch = mock.patch.object(install, "STATE_PATH", Path(self.tmp.name) / "install-state.json")
        self.log_path_patch = mock.patch.object(install, "LOG_PATH", Path(self.tmp.name) / "install.log")
        self.state_path_patch.start()
        self.log_path_patch.start()

    def tearDown(self):
        self.state_path_patch.stop()
        self.log_path_patch.stop()
        self.tmp.cleanup()

    def test_load_state_returns_default_when_missing(self):
        state = install.load_state()
        self.assertEqual(state["steps_completed"], [])
        self.assertIsNone(state["profile"])

    def test_save_then_load_roundtrip(self):
        state = {"steps_completed": ["preflight"], "profile": "solo", "started_at": "2026-05-19T00:00:00+00:00"}
        install.save_state(state)
        loaded = install.load_state()
        self.assertEqual(loaded["steps_completed"], ["preflight"])
        self.assertEqual(loaded["profile"], "solo")

    def test_save_state_skipped_in_dry_run(self):
        install.save_state({"steps_completed": ["x"]}, dry_run=True)
        self.assertFalse(install.STATE_PATH.exists())


class TestPreflightStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path_patch = mock.patch.object(install, "STATE_PATH", Path(self.tmp.name) / "install-state.json")
        self.log_path_patch = mock.patch.object(install, "LOG_PATH", Path(self.tmp.name) / "install.log")
        self.state_path_patch.start()
        self.log_path_patch.start()

    def tearDown(self):
        self.state_path_patch.stop()
        self.log_path_patch.stop()
        self.tmp.cleanup()

    def test_preflight_passes_on_current_env(self):
        # We're already running on Python 3.11+ with disk space and write perms.
        state = {"steps_completed": []}
        ok = install.step_preflight(state, dry_run=True)
        self.assertTrue(ok)


class TestProfileStep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path_patch = mock.patch.object(install, "STATE_PATH", Path(self.tmp.name) / "install-state.json")
        self.log_path_patch = mock.patch.object(install, "LOG_PATH", Path(self.tmp.name) / "install.log")
        self.state_path_patch.start()
        self.log_path_patch.start()

    def tearDown(self):
        self.state_path_patch.stop()
        self.log_path_patch.stop()
        self.tmp.cleanup()

    def test_solo_profile_accepted(self):
        state = {"steps_completed": []}
        self.assertTrue(install.step_select_profile(state, "solo", dry_run=True))

    def test_hybrid_blocked_with_message(self):
        state = {"steps_completed": []}
        self.assertFalse(install.step_select_profile(state, "hybrid", dry_run=True))

    def test_organization_blocked_with_message(self):
        state = {"steps_completed": []}
        self.assertFalse(install.step_select_profile(state, "organization", dry_run=True))

    def test_unknown_profile_rejected(self):
        state = {"steps_completed": []}
        self.assertFalse(install.step_select_profile(state, "fake-profile", dry_run=True))


class TestCompletionMarker(unittest.TestCase):
    def test_marker_matches_test_protocol(self):
        # The test protocol in Working — Project — Ora Install Script Overhaul
        # specifies the exact grep target:
        self.assertEqual(install.COMPLETION_MARKER, "INSTALL_COMPLETE: 0 warnings, 0 errors")


if __name__ == "__main__":
    unittest.main()
