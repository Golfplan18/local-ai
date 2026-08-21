#!/usr/bin/env python3
"""Solo source-install profile — install.py smoke tests.

Verifies the install script's structure and step contract. Live
network calls are not exercised here (catalog refresh has its own
test file); these tests confirm the install scaffold + state
machine work correctly.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
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


def _tree_checksum(root: Path) -> str:
    """One digest over every path, its kind, and every file's bytes."""
    entries = sorted(root.rglob("*"), key=lambda p: str(p))
    if not entries:
        # An empty tree hashes to the digest of nothing, which matches any
        # other empty tree — including one this test was meant to prove is
        # still full. Refuse rather than hand back a false pass.
        raise AssertionError(f"refusing to checksum an empty tree at {root}")
    digest = hashlib.sha256()
    for path in entries:
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            digest.update(f"L:{rel}:{os.readlink(path)}\0".encode())
        elif path.is_dir():
            digest.update(f"D:{rel}\0".encode())
        else:
            digest.update(f"F:{rel}:".encode())
            digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
            digest.update(b"\0")
    return digest.hexdigest()


class TestVaultCreation(unittest.TestCase):
    """Milestone C — the installer creates the vault a fresh clone lacks.

    Before this, install reported success into a product with nothing to
    load: the resolved vault did not exist, the installer said so, and then
    said it would not create one.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_path = self.root / "install.log"
        self.state_path_patch = mock.patch.object(
            install, "STATE_PATH", self.root / "install-state.json")
        self.log_path_patch = mock.patch.object(install, "LOG_PATH", self.log_path)
        self.state_path_patch.start()
        self.log_path_patch.start()

    def tearDown(self):
        self.state_path_patch.stop()
        self.log_path_patch.stop()
        self.tmp.cleanup()

    def _logged(self) -> str:
        return self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""

    def _preflight_with_vault(self, vault: Path, dry_run: bool = False) -> bool:
        """Run the real path preflight against an ORA_VAULT-resolved vault."""
        with mock.patch.dict(
            "os.environ",
            {"ORA_DOCUMENTS": str(self.root), "ORA_VAULT": str(vault)},
            clear=True,
        ):
            return install._runtime_path_preflight(dry_run=dry_run)

    def test_missing_vault_is_created_with_the_runtime_skeleton(self):
        vault = self.root / "fresh-vault"
        self.assertFalse(vault.exists())

        self.assertTrue(self._preflight_with_vault(vault))

        self.assertTrue(vault.is_dir(), "vault root was not created")
        for segments in install.VAULT_SKELETON:
            folder = vault.joinpath(*segments)
            self.assertTrue(folder.is_dir(), f"missing skeleton folder {folder}")
        self.assertIn(f"Created vault at {vault}", self._logged())

    def test_created_vault_carries_no_content(self):
        """Content is an explicit non-goal: folders only, no seeded files."""
        vault = self.root / "fresh-vault"
        self._preflight_with_vault(vault)
        files = [p for p in vault.rglob("*") if p.is_file()]
        self.assertEqual(files, [])

    def test_skeleton_holds_only_folders_the_runtime_uses(self):
        top_level = {segments[0] for segments in install.VAULT_SKELETON}
        self.assertEqual(
            top_level,
            {"Projects", "Sessions", "Engrams", "Resources", "Administration"},
        )
        # Guard the non-goal: these have no runtime reference beyond skip-lists.
        for decorative in ("Archive", "Workshop", "Templates"):
            self.assertNotIn(decorative, top_level)

    def test_existing_vault_is_left_byte_identical(self):
        vault = self.root / "real-vault"
        (vault / "Projects" / "Ora").mkdir(parents=True)
        (vault / "Projects" / "Ora" / "Registry — Ora.md").write_text(
            "# Registry\n\nreal work\n", encoding="utf-8")
        (vault / "Engrams").mkdir()
        (vault / "Engrams" / "note.md").write_text("engram\n", encoding="utf-8")
        (vault / "Idiosyncratic Folder").mkdir()
        (vault / "top-level.md").write_text("root note\n", encoding="utf-8")
        # Deliberately missing Sessions / Resources / Administration: an
        # existing vault must not be "repaired" into the skeleton shape.

        before = _tree_checksum(vault)
        self.assertTrue(self._preflight_with_vault(vault))
        after = _tree_checksum(vault)

        self.assertEqual(before, after, "install modified an existing vault")
        self.assertFalse((vault / "Sessions").exists())
        self.assertIn(f"Vault found at {vault}", self._logged())

    def test_dry_run_creates_nothing(self):
        vault = self.root / "fresh-vault"
        self.assertTrue(self._preflight_with_vault(vault, dry_run=True))
        self.assertFalse(vault.exists())

    def test_creation_failure_halts_instead_of_reporting_success(self):
        vault = self.root / "fresh-vault"
        with mock.patch(
            "orchestrator.runtime_paths.safe_owned_subdir",
            side_effect=OSError("read-only file system"),
        ):
            self.assertFalse(self._preflight_with_vault(vault))
        self.assertIn("Could not create the vault", self._logged())

    # ── A creation that fails part-way must not leave a vault behind ──
    #
    # The failure is a real one from the operating system: a folder name
    # longer than any filesystem accepts. Only the skeleton list is swapped,
    # so the root and the folders before it are created for real and the
    # kernel refuses the next one — the same shape as a disk filling up or
    # permissions changing mid-run.
    _UNCREATABLE = "x" * 300

    def _skeleton_that_fails_after(self, *good: tuple[str, ...]):
        return mock.patch.object(
            install, "VAULT_SKELETON", (*good, (self._UNCREATABLE,)))

    def test_partial_creation_leaves_no_vault_root_behind(self):
        vault = self.root / "fresh-vault"
        with self._skeleton_that_fails_after(("Sessions",), ("Projects", "Ora")):
            self.assertFalse(self._preflight_with_vault(vault))

        self.assertFalse(
            vault.exists(),
            "a half-created vault survived — the next --resume would adopt it",
        )
        logged = self._logged()
        self.assertIn(f"Could not create the vault at {vault}", logged)
        self.assertIn(f"Removed the partial vault this run created at {vault}", logged)

    def test_re_run_after_a_partial_failure_creates_the_vault_completely(self):
        vault = self.root / "fresh-vault"
        with self._skeleton_that_fails_after(("Sessions",)):
            self.assertFalse(self._preflight_with_vault(vault))
        self.assertFalse(vault.exists())

        # Second run, nothing engineered: the clean state the first run left
        # behind is what lets this one build the whole skeleton.
        self.assertTrue(self._preflight_with_vault(vault))
        self.assertTrue(vault.is_dir())
        for segments in install.VAULT_SKELETON:
            self.assertTrue(vault.joinpath(*segments).is_dir(),
                            f"missing skeleton folder {vault.joinpath(*segments)}")
        self.assertIn(f"Created vault at {vault}", self._logged())

    def test_removal_stops_at_anything_this_run_did_not_create(self):
        """Content that appears mid-run is left alone, not swept up."""
        vault = self.root / "fresh-vault"
        stray = vault / "not-ours.md"
        from orchestrator import runtime_paths as rp
        real_subdir = rp.safe_owned_subdir

        def drop_a_file_then_carry_on(base, *segments, create=False):
            made = real_subdir(base, *segments, create=create)
            if segments == ("Sessions",):
                stray.write_text("somebody else's work\n", encoding="utf-8")
            return made

        with mock.patch("orchestrator.runtime_paths.safe_owned_subdir",
                        side_effect=drop_a_file_then_carry_on):
            with self._skeleton_that_fails_after(("Sessions",)):
                self.assertFalse(self._preflight_with_vault(vault))

        self.assertTrue(vault.is_dir(), "the vault was removed with content in it")
        self.assertEqual(stray.read_text(encoding="utf-8"), "somebody else's work\n")
        self.assertFalse((vault / "Sessions").exists(), "own empty folder not undone")
        self.assertIn(f"Could not remove {vault}", self._logged())

    def test_an_existing_vault_is_never_removed(self):
        """The found-existing branch records nothing, so nothing can undo it.

        The skeleton here is one that cannot be created at all. An existing
        vault never reaches it — and must survive byte-identical either way.
        """
        vault = self.root / "real-vault"
        (vault / "Engrams").mkdir(parents=True)
        (vault / "Engrams" / "note.md").write_text("engram\n", encoding="utf-8")
        before = _tree_checksum(vault)

        with self._skeleton_that_fails_after():
            self.assertTrue(self._preflight_with_vault(vault))

        self.assertTrue(vault.is_dir(), "an existing vault was removed")
        self.assertEqual(before, _tree_checksum(vault))
        self.assertIn(f"Vault found at {vault}", self._logged())

    def test_undo_refuses_a_path_outside_the_vault_it_created(self):
        elsewhere = self.root / "somebody-elses-folder"
        elsewhere.mkdir()
        install._undo_created_vault(self.root / "fresh-vault", [elsewhere])
        self.assertTrue(elsewhere.is_dir())
        self.assertIn("not inside the vault this run created", self._logged())

    def test_undo_never_removes_a_symlink(self):
        target = self.root / "real-folder"
        target.mkdir()
        (target / "keep.md").write_text("keep\n", encoding="utf-8")
        link = self.root / "linked-vault"
        link.symlink_to(target, target_is_directory=True)

        install._undo_created_vault(link, [link])

        self.assertTrue(link.is_symlink(), "a symlink was removed")
        self.assertEqual((target / "keep.md").read_text(encoding="utf-8"), "keep\n")
        self.assertIn("it is a symlink", self._logged())

    def test_the_old_refusal_message_is_gone(self):
        source = (REPO_ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
        self.assertNotIn("will not create or replace a canonical vault", source)


class TestMCPRuntimeInstall(unittest.TestCase):
    def test_installs_locked_chromium_through_repo_local_playwright_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "mcp-runtime"
            runtime.mkdir()
            (runtime / "package-lock.json").write_text("{}", encoding="utf-8")
            for package, version in install.MCP_RUNTIME_PACKAGES.items():
                metadata = runtime / "node_modules" / package / "package.json"
                metadata.parent.mkdir(parents=True, exist_ok=True)
                metadata.write_text(json.dumps({"version": version}), encoding="utf-8")
            core = runtime / "node_modules" / "playwright-core"
            cli = core / "cli.js"
            cli.parent.mkdir(parents=True, exist_ok=True)
            cli.write_text("", encoding="utf-8")
            browser = core / ".local-browsers" / "chromium-123" / "chrome"
            browser.parent.mkdir(parents=True)
            browser.write_text("binary", encoding="utf-8")
            results = [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, str(browser), ""),
            ]
            with mock.patch.object(install, "MCP_RUNTIME_DIR", runtime), \
                 mock.patch.object(install.shutil, "which", side_effect=lambda name: f"/exact/{name}"), \
                 mock.patch.object(install.subprocess, "run", side_effect=results) as run:
                self.assertTrue(install._install_mcp_runtime(dry_run=False))
        browser_call = run.call_args_list[1]
        self.assertEqual(
            browser_call.args[0],
            ["/exact/node", str(cli), "install", "chromium"],
        )
        self.assertEqual(
            browser_call.kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"], "0",
        )
        self.assertNotIn("npx", " ".join(browser_call.args[0]))


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
