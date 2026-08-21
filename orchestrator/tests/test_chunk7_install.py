#!/usr/bin/env python3
"""Solo source-install profile — install.py smoke tests.

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

    def test_hybrid_reserved_for_g127_network_validation(self):
        """Hybrid is a future multi-machine profile, not a public install path."""
        self.assertFalse(install.DEPLOYMENT_PROFILES["hybrid"]["supported_now"])

    def test_organization_reserved_for_future_concurrency_path(self):
        """Organization is a future shared/API-pool profile, not a public install path."""
        self.assertFalse(install.DEPLOYMENT_PROFILES["organization"]["supported_now"])

    def test_local_models_flag_present_per_profile(self):
        self.assertTrue(install.DEPLOYMENT_PROFILES["solo"]["local_models"])
        self.assertTrue(install.DEPLOYMENT_PROFILES["hybrid"]["local_models"])
        self.assertFalse(install.DEPLOYMENT_PROFILES["organization"]["local_models"])

    def test_each_profile_has_description(self):
        for name, info in install.DEPLOYMENT_PROFILES.items():
            self.assertTrue(info.get("description"),
                            f"profile {name!r} missing description")
            self.assertNotIn("blocked", info["description"].lower())


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

    def test_path_preflight_accepts_explicit_documents_and_vault(self):
        docs = Path(self.tmp.name)
        with mock.patch.dict(
            "os.environ",
            {"ORA_DOCUMENTS": str(docs), "ORA_VAULT": str(docs / "vault")},
            clear=True,
        ):
            self.assertTrue(install._runtime_path_preflight(dry_run=True))

    def test_path_preflight_rejects_conflicting_vault_aliases(self):
        docs = Path(self.tmp.name)
        with mock.patch.dict(
            "os.environ",
            {
                "ORA_DOCUMENTS": str(docs),
                "ORA_VAULT": str(docs / "a"),
                "ORA_VAULT_PATH": str(docs / "b"),
            },
            clear=True,
        ):
            self.assertFalse(install._runtime_path_preflight(dry_run=True))

    def test_document_conversion_dependency_preflight_is_complete(self):
        self.assertEqual(
            set(install.DOCUMENT_CONVERSION_DEPENDENCIES.values()),
            {"pdfplumber", "python-docx", "python-pptx", "openpyxl",
             "markdownify", "beautifulsoup4", "striprtf"},
        )

    def test_missing_document_dependency_is_reported_by_distribution_name(self):
        with mock.patch.object(install.importlib.util, "find_spec", return_value=None):
            missing = install._missing_document_dependencies()
        self.assertIn("python-docx", missing)
        self.assertIn("beautifulsoup4", missing)


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

    def test_hybrid_profile_rejected_until_network_validation(self):
        state = {"steps_completed": []}
        self.assertFalse(install.step_select_profile(state, "hybrid", dry_run=True))

    def test_organization_profile_rejected_until_concurrency_path(self):
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

    def test_windows_completion_uses_batch_launcher(self):
        lines = install._next_launch_instructions(platform_name="win32", os_name="nt")
        self.assertIn("start.bat", " ".join(lines))
        self.assertNotIn("./start.sh", " ".join(lines))


class TestSmokeHelpers(unittest.TestCase):
    def test_extract_smoke_models_preserves_primary_then_fallbacks(self):
        cfg = {
            "cells": {
                "analysis": {
                    "gear4": {
                        "depth": {
                            "primary": "provider/primary:free",
                            "fallback": ["provider/fallback:free", "provider/primary:free"],
                        }
                    }
                }
            }
        }
        self.assertEqual(
            install._extract_smoke_models(cfg)[:3],
            ["provider/primary:free", "provider/fallback:free", "openrouter/free"],
        )

    def test_openrouter_smoke_uses_origin_locked_transport(self):
        payload = {
            "choices": [{"message": {"content": "Ora install smoke ok"}}],
        }
        with mock.patch.object(
            install.network_policy, "openrouter_request_bytes",
            return_value=(json.dumps(payload).encode(), mock.sentinel.destination),
        ) as request:
            ok, message, auth_failure = install._openrouter_smoke_call(
                "openrouter/free", "secret",
            )
        self.assertTrue(ok)
        self.assertFalse(auth_failure)
        self.assertEqual(message, "Ora install smoke ok")
        self.assertEqual(
            request.call_args.args[0],
            "https://openrouter.ai/api/v1/chat/completions",
        )


class TestExternalApiWalkthrough(unittest.TestCase):
    def test_recommended_minimal_package_present(self):
        first_group = install.EXTERNAL_API_GROUPS[0]
        self.assertEqual(first_group["title"], "Recommended minimal package")
        self.assertEqual(
            [p["name"] for p in first_group["providers"]],
            ["OpenRouter", "Tavily", "Artificial Analysis"],
        )

    def test_optional_chatgpt_orientation_is_truthful(self):
        lines = []
        state = {"steps_completed": []}
        with mock.patch.object(install, "log", side_effect=lines.append):
            self.assertTrue(
                install.step_external_api_walkthrough(state, dry_run=True)
            )
        copy = "\n".join(lines)
        self.assertIn("Optional ChatGPT subscription route", copy)
        self.assertIn("browser sign-in", copy)
        self.assertIn("system keychain", copy)
        self.assertIn("depends on your ChatGPT plan or workspace", copy)
        self.assertNotIn("every ChatGPT plan", copy)

    def test_requirements_install_codex_sdk_and_pinned_runtime_package(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text().splitlines()
        self.assertIn("openai-codex==0.144.4", requirements)


if __name__ == "__main__":
    unittest.main()
