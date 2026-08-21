#!/usr/bin/env python3
"""Solo source-install profile — install.py smoke tests.

Verifies the install script's structure and step contract. Live
network calls are not exercised here (catalog refresh has its own
test file); these tests confirm the install scaffold + state
machine work correctly.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

# Loading scripts/converters.py below imports orchestrator.export, which is the
# first thing here to import runtime_paths — and runtime_paths bakes its roots
# at import. Without this, the roots would be the author's ~/ora rather than
# this checkout, and every later module that derives a path from ORA_HOME would
# disagree with them. test_export.py pins the same variable for the same reason.
os.environ.setdefault("ORA_HOME", str(REPO_ROOT))

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


# ─── Document converters (Pandoc + Typst) ────────────────────────────────

CONVERTERS_SPEC = importlib.util.spec_from_file_location(
    "converters_script", REPO_ROOT / "scripts" / "converters.py",
)
converters = importlib.util.module_from_spec(CONVERTERS_SPEC)
# Registered before execution because @dataclass resolves annotations through
# sys.modules; a module loaded by path alone is not there yet.
sys.modules[CONVERTERS_SPEC.name] = converters
CONVERTERS_SPEC.loader.exec_module(converters)


def _fake_pandoc_archive(kind: str, member: str, payload: bytes | None = None) -> bytes:
    """An archive shaped like a publisher release, holding a runnable stand-in.

    ``payload`` overrides the stand-in, which is how the "downloaded cleanly
    but will not run" case below gets a binary that fails its own check.
    """
    import io
    import tarfile
    import zipfile

    if payload is None:
        payload = b'#!/bin/sh\necho "pandoc 9.9.9 test stand-in"\n'
    buffer = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo(member)
            info.external_attr = 0o755 << 16
            archive.writestr(info, payload)
    else:
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(member)
            info.size = len(payload)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class TestConverterPins(unittest.TestCase):
    """The pinned release table is what a download has to match."""

    def test_every_pin_is_a_publisher_url_with_a_real_digest(self):
        publishers = {
            "pandoc": "https://github.com/jgm/pandoc/releases/download/",
            "typst": "https://github.com/typst/typst/releases/download/",
        }
        for tool, releases in converters.RELEASES.items():
            self.assertTrue(releases, f"{tool} has no pinned releases")
            for key, release in releases.items():
                with self.subTest(tool=tool, platform=key):
                    self.assertTrue(release.url.startswith(publishers[tool]))
                    self.assertRegex(release.sha256, r"^[0-9a-f]{64}$")
                    self.assertTrue(release.member.endswith(release.binary))
                    self.assertFalse(release.member.startswith(("/", "..")))

    def test_the_platforms_ora_ships_to_are_all_covered(self):
        wanted = {
            "darwin-arm64", "darwin-x86_64",
            "linux-arm64", "linux-x86_64", "windows-x86_64",
        }
        for tool, releases in converters.RELEASES.items():
            self.assertEqual(wanted, set(releases), f"{tool} platform coverage")

    def test_platform_key_names_this_machine_the_way_the_table_is_keyed(self):
        self.assertEqual(converters.platform_key("darwin", "arm64"), "darwin-arm64")
        self.assertEqual(converters.platform_key("darwin", "x86_64"), "darwin-x86_64")
        self.assertEqual(converters.platform_key("linux", "aarch64"), "linux-arm64")
        self.assertEqual(converters.platform_key("win32", "AMD64"), "windows-x86_64")
        # Windows on ARM runs the x64 build under emulation; Pandoc ships no
        # ARM build for Windows at all.
        self.assertEqual(converters.platform_key("win32", "ARM64"), "windows-x86_64")

    def test_unpublished_platforms_are_named_rather_than_guessed(self):
        self.assertIsNone(converters.platform_key("linux", "i686"))
        self.assertIsNone(converters.platform_key("freebsd14", "x86_64"))


class TestConverterProvisioning(unittest.TestCase):
    def setUp(self):
        from orchestrator import export, runtime_paths
        self.export = export
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_patch = mock.patch.object(
            runtime_paths, "DATA_DIR_STR", str(self.data_dir))
        self.data_patch.start()
        self.lines: list[str] = []
        self.key = converters.platform_key() or "darwin-arm64"

    def tearDown(self):
        self.data_patch.stop()
        self.tmp.cleanup()

    def _log(self, msg=""):
        self.lines.append(str(msg))

    @property
    def transcript(self) -> str:
        return "\n".join(self.lines)

    def test_an_existing_install_is_used_and_nothing_is_downloaded(self):
        with (
            mock.patch.object(self.export, "_which", return_value="/usr/bin/pandoc"),
            mock.patch.object(converters, "_download") as download,
        ):
            result = converters.provision("pandoc", log=self._log)
        download.assert_not_called()
        self.assertEqual(result.status, "present")
        self.assertEqual(result.path, "/usr/bin/pandoc")
        self.assertIn("already on this machine", self.transcript)
        self.assertFalse(self.data_dir.exists())

    @unittest.skipIf(os.name == "nt", "the stand-in binary is a POSIX shell script")
    def test_a_missing_converter_is_downloaded_verified_and_made_runnable(self):
        archive = _fake_pandoc_archive("zip", "pandoc-test/bin/pandoc")
        release = converters.Release(
            url="https://github.com/jgm/pandoc/releases/download/9.9.9/x.zip",
            sha256=hashlib.sha256(archive).hexdigest(),
            member="pandoc-test/bin/pandoc",
            binary="pandoc",
        )
        with (
            mock.patch.object(self.export, "_which", return_value=None),
            mock.patch.dict(converters.RELEASES["pandoc"], {self.key: release},
                            clear=True),
            mock.patch.object(converters, "_download", return_value=archive),
        ):
            result = converters.provision("pandoc", log=self._log)

        self.assertEqual(result.status, "installed", self.transcript)
        landed = self.data_dir / "converters" / "bin" / "pandoc"
        self.assertTrue(landed.is_file())
        self.assertTrue(os.access(landed, os.X_OK))
        self.assertIn("checksum verified", self.transcript)
        # And the runtime finds it there: the whole point of the directory.
        self.assertIn(str(landed.parent), self.export._binary_search_dirs())
        self.assertEqual(
            shutil.which("pandoc", path=str(landed.parent)), str(landed))

    def test_a_checksum_mismatch_is_refused_and_writes_nothing(self):
        archive = _fake_pandoc_archive("targz", "pandoc-test/bin/pandoc")
        release = converters.Release(
            url="https://github.com/jgm/pandoc/releases/download/9.9.9/x.tar.gz",
            sha256="0" * 64,
            member="pandoc-test/bin/pandoc",
            binary="pandoc",
        )
        with (
            mock.patch.object(self.export, "_which", return_value=None),
            mock.patch.dict(converters.RELEASES["pandoc"], {self.key: release},
                            clear=True),
            mock.patch.object(converters, "_download", return_value=archive),
        ):
            result = converters.provision("pandoc", log=self._log)

        self.assertEqual(result.status, "failed")
        self.assertIn("REFUSED", self.transcript)
        self.assertIn("Nothing was written to disk", self.transcript)
        self.assertIn(converters.RETRY_COMMAND, self.transcript)
        self.assertFalse((self.data_dir / "converters" / "bin" / "pandoc").exists())

    @unittest.skipIf(os.name == "nt", "the stand-in binary is a POSIX shell script")
    def test_a_converter_that_will_not_run_is_taken_back_out_again(self):
        # A checksum-valid publisher binary can still refuse to run: wrong
        # runtime, a noexec mount, antivirus interference. Leaving it on disk
        # made the next run find it, report "already on this machine", and let
        # Ora switch on exports that silently produce nothing — a worse answer
        # than "unavailable", because "unavailable" was at least true.
        archive = _fake_pandoc_archive(
            "zip", "pandoc-test/bin/pandoc",
            payload=b'#!/bin/sh\necho "not pandoc" >&2\nexit 3\n')
        release = converters.Release(
            url="https://github.com/jgm/pandoc/releases/download/9.9.9/x.zip",
            sha256=hashlib.sha256(archive).hexdigest(),
            member="pandoc-test/bin/pandoc",
            binary="pandoc",
        )
        bin_dir = self.data_dir / "converters" / "bin"

        def only_oras_own_copy(name):
            # The half of detection this defect is about: does Ora's own
            # directory hold something it will call installed?
            return shutil.which(name, path=str(bin_dir))

        with (
            mock.patch.object(self.export, "_which", side_effect=only_oras_own_copy),
            mock.patch.dict(converters.RELEASES["pandoc"], {self.key: release},
                            clear=True),
            mock.patch.object(converters, "_download",
                              return_value=archive) as download,
        ):
            first = converters.provision("pandoc", log=self._log)
            self.assertEqual(first.status, "failed", self.transcript)
            self.assertIn("exited 3", self.transcript)

            # Nothing left behind: the state is what it was before the attempt.
            self.assertFalse(bin_dir.exists(), sorted(
                p.name for p in bin_dir.iterdir()) if bin_dir.exists() else "")
            self.assertIsNone(shutil.which("pandoc", path=str(bin_dir)))

            # So the printed retry command really retries, instead of
            # congratulating the user on a converter that does not work.
            self.lines.clear()
            second = converters.provision("pandoc", log=self._log)

        self.assertEqual(download.call_count, 2)
        self.assertEqual(second.status, "failed", self.transcript)
        self.assertNotIn("already on this machine", self.transcript)

    def test_an_unreachable_download_names_the_cause_and_the_retry_command(self):
        import urllib.error

        with (
            mock.patch.object(self.export, "_which", return_value=None),
            mock.patch.object(
                converters, "_download",
                side_effect=urllib.error.URLError("Network is unreachable")),
        ):
            result = converters.provision("pandoc", log=self._log)

        self.assertEqual(result.status, "failed")
        self.assertIn("Network is unreachable", self.transcript)
        self.assertIn("Word (.docx) and PDF export stay unavailable",
                      self.transcript)
        self.assertIn(converters.RETRY_COMMAND, self.transcript)

    def test_an_unpublished_platform_is_reported_not_guessed_at(self):
        with (
            mock.patch.object(self.export, "_which", return_value=None),
            mock.patch.object(converters, "platform_key", return_value=None),
            mock.patch.object(converters, "_download") as download,
        ):
            result = converters.provision("typst", log=self._log)
        download.assert_not_called()
        self.assertEqual(result.status, "failed")
        self.assertIn("no official typst release is published", self.transcript)

    def test_dry_run_downloads_nothing_and_writes_nothing(self):
        with (
            mock.patch.object(self.export, "_which", return_value=None),
            mock.patch.object(converters, "_download") as download,
        ):
            results = converters.provision_all(dry_run=True, log=self._log)
        download.assert_not_called()
        self.assertEqual([r.status for r in results],
                         ["would-install", "would-install"])
        self.assertFalse(self.data_dir.exists())
        # A preview must not claim the formats are ready.
        self.lines.clear()
        converters.summarize(results, log=self._log)
        self.assertNotIn("are ready", self.transcript)
        self.assertIn("Re-run without --dry-run", self.transcript)

    def test_summary_says_which_formats_the_user_actually_has(self):
        good = [converters.Result("pandoc", "present", "x"),
                converters.Result("typst", "installed", "y")]
        self.assertTrue(converters.summarize(good, log=self._log))
        self.assertIn("Word (.docx) and PDF export are ready", self.transcript)

        self.lines.clear()
        bad = [converters.Result("pandoc", "present", "x"),
               converters.Result("typst", "failed", "boom")]
        self.assertFalse(converters.summarize(bad, log=self._log))
        self.assertIn("typst could not be provisioned", self.transcript)
        self.assertIn(converters.RETRY_COMMAND, self.transcript)


class TestConverterInstallStep(unittest.TestCase):
    """The install must survive a converter that would not download."""

    def setUp(self):
        self.lines: list[str] = []
        self.log_patch = mock.patch.object(install, "log",
                                           side_effect=self.lines.append)
        self.log_patch.start()

    def tearDown(self):
        self.log_patch.stop()

    @property
    def transcript(self) -> str:
        return "\n".join(str(line) for line in self.lines)

    def test_a_failed_provision_does_not_halt_the_install(self):
        state = {"steps_completed": []}
        failed = subprocess.CompletedProcess(
            [], 1, stdout="  ✗ pandoc: download failed", stderr="")
        with mock.patch.object(install.subprocess, "run", return_value=failed):
            self.assertTrue(install.step_converters(state, dry_run=False))
        self.assertIn("The install continues", self.transcript)
        self.assertIn(install.CONVERTER_RETRY_COMMAND, self.transcript)
        # Not recorded as done, so --resume tries again.
        self.assertNotIn("converters", state["steps_completed"])

    def test_a_successful_provision_is_recorded_once(self):
        state = {"steps_completed": []}
        done = subprocess.CompletedProcess(
            [], 0, stdout="  ✓ pandoc already on this machine: /usr/bin/pandoc",
            stderr="")
        with (
            mock.patch.object(install.subprocess, "run", return_value=done),
            mock.patch.object(install, "save_state"),
        ):
            self.assertTrue(install.step_converters(state, dry_run=False))
        self.assertEqual(state["steps_completed"], ["converters"])

    def test_a_timeout_is_survivable_too(self):
        state = {"steps_completed": []}
        with mock.patch.object(
            install.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="converters", timeout=1),
        ):
            self.assertTrue(install.step_converters(state, dry_run=False))
        self.assertIn(install.CONVERTER_RETRY_COMMAND, self.transcript)
        self.assertNotIn("converters", state["steps_completed"])

    def test_dry_run_runs_nothing(self):
        state = {"steps_completed": []}
        with mock.patch.object(install.subprocess, "run") as run:
            self.assertTrue(install.step_converters(state, dry_run=True))
        run.assert_not_called()

    def test_the_retry_command_is_a_real_subcommand(self):
        # The printed retry line has to be a command that exists.
        self.assertTrue(install.CONVERTER_RETRY_COMMAND.endswith(
            "scripts/install.py converters"))
        with mock.patch.object(install.subprocess, "call", return_value=0) as call:
            self.assertEqual(install._delegate_to_converters([]), 0)
        self.assertEqual(
            call.call_args[0][0][1], str(REPO_ROOT / "scripts" / "converters.py"))

    def test_the_converters_land_in_this_clone_not_in_home_slash_ora(self):
        # The bug this replaces: converters.py asks runtime_paths where Ora
        # lives, and an unset ORA_HOME answers "$HOME/ora" wherever the clone
        # actually is — while start.sh / start.bat / run-ora-server.sh fall
        # back to the checkout they live in. The installer said "ready", the
        # server said "unavailable", and 240 MB landed in a ~/ora nobody had
        # cloned. With nothing set, both entry points default to this clone.
        state = {"steps_completed": []}
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with (
            mock.patch.dict("os.environ", {}, clear=False),
            mock.patch.object(install.subprocess, "run", return_value=done) as run,
            mock.patch.object(install, "save_state"),
        ):
            os.environ.pop("ORA_HOME", None)
            install.step_converters(state, dry_run=False)
        self.assertEqual(run.call_args.kwargs["env"]["ORA_HOME"], str(REPO_ROOT))
        self.assertEqual(run.call_args.kwargs["cwd"], str(REPO_ROOT))

        with (
            mock.patch.dict("os.environ", {}, clear=False),
            mock.patch.object(install.subprocess, "call", return_value=0) as call,
        ):
            os.environ.pop("ORA_HOME", None)
            install._delegate_to_converters([])
        self.assertEqual(call.call_args.kwargs["env"]["ORA_HOME"], str(REPO_ROOT))

    def test_the_installer_follows_the_launchers_ora_home_rule(self):
        # start.sh:8 and run-ora-server.sh:11 both read
        # WORKSPACE="${ORA_HOME:-$SCRIPT_DIR}", and run-ora-server.sh:24
        # exports that value back out — so an ORA_HOME with something in it
        # decides where the SERVER looks, and an ORA_HOME with nothing in it
        # (unset, or exported empty, which ${...:-...} counts the same way)
        # falls back to the checkout. The installer has to decide the same
        # way by the same test, or it writes
        # where the toolbar never reads. An unconditional pin to the clone
        # gets the unset half right and reproduces the whole defect on the
        # other half: the launcher honors the user's ORA_HOME, the installer
        # overrides it, the installer reports ready, and Word and PDF stay
        # greyed out — which is exactly the failure this step exists to end.
        elsewhere = str(Path(tempfile.gettempdir()) / "ora-elsewhere")

        with mock.patch.dict("os.environ", {"ORA_HOME": elsewhere}, clear=False):
            honored = install._converter_environment()
        self.assertEqual(honored["ORA_HOME"], elsewhere)

        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("ORA_HOME", None)
            defaulted = install._converter_environment()
        self.assertEqual(defaulted["ORA_HOME"], str(REPO_ROOT))

        # Exported but empty is the case a plain setdefault gets wrong, and
        # it is not exotic: `export ORA_HOME=` in a profile, or a launchd
        # plist with an empty string, produces it. The shell counts an empty
        # value as no value — ${ORA_HOME:-$SCRIPT_DIR} falls straight through
        # to the checkout — while setdefault sees a key that exists and hands
        # the child a blank, after which runtime_paths strips it and answers
        # $HOME/ora. Launcher and installer then name two different
        # directories, which is the whole defect wearing a different hat.
        # Whitespace goes the same way: runtime_paths strips before it decides
        # whether anyone set a home, so "   " names one for nobody either.
        for blank in ("", "   ", "\t\n"):
            with mock.patch.dict("os.environ", {"ORA_HOME": blank}, clear=False):
                blanked = install._converter_environment()
            self.assertEqual(
                blanked["ORA_HOME"], str(REPO_ROOT),
                msg=f"ORA_HOME={blank!r} must fall back to the clone, as "
                    "${ORA_HOME:-$SCRIPT_DIR} does",
            )

        # Both entry points, not just the helper: the install step and the
        # retry command it prints have to agree with the launchers alike.
        state = {"steps_completed": []}
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with (
            mock.patch.dict("os.environ", {"ORA_HOME": elsewhere}, clear=False),
            mock.patch.object(install.subprocess, "run", return_value=done) as run,
            mock.patch.object(install.subprocess, "call", return_value=0) as call,
            mock.patch.object(install, "save_state"),
        ):
            install.step_converters(state, dry_run=False)
            install._delegate_to_converters([])
        self.assertEqual(run.call_args.kwargs["env"]["ORA_HOME"], elsewhere)
        self.assertEqual(call.call_args.kwargs["env"]["ORA_HOME"], elsewhere)

    def test_the_converter_environment_keeps_everything_else(self):
        # Deciding one variable must not strip the rest: the child needs the
        # user's PATH, proxy settings and CA bundle to download anything.
        with mock.patch.dict("os.environ", {"ORA_CONVERTER_CANARY": "kept"},
                             clear=False):
            env = install._converter_environment()
        self.assertEqual(env["ORA_CONVERTER_CANARY"], "kept")
        self.assertIn("PATH", env)

    def _preflight_transcript(self, extra_env: dict) -> str:
        lines: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            env = {"ORA_DOCUMENTS": tmp, "ORA_VAULT": str(Path(tmp) / "vault")}
            env.update(extra_env)
            with (
                mock.patch.object(install, "log", side_effect=lines.append),
                mock.patch.dict("os.environ", env, clear=True),
            ):
                install._runtime_path_preflight(dry_run=True)
        return "\n".join(str(line) for line in lines)

    def test_preflight_reports_ora_home_and_where_it_came_from(self):
        # Ora home was the one root the pre-flight never printed, which is why
        # the divergence above went unnoticed for a whole milestone. Both ways
        # of diverging get named, because they have different consequences.
        with tempfile.TemporaryDirectory() as tmp:
            elsewhere = str(Path(tmp) / "elsewhere")
            explicit = self._preflight_transcript({"ORA_HOME": elsewhere})
        self.assertIn(f"Ora home: {elsewhere} (ORA_HOME)", explicit)
        self.assertIn(f"This clone: {REPO_ROOT}", explicit)
        self.assertIn("Ora home is not this clone", explicit)
        # An ORA_HOME the user set is honored by the launchers, so the server
        # runs out of there rather than this checkout — worth saying out loud.
        # The converters follow it too, so the warning must not claim they
        # land in the clone: that was true of the unconditional pin and is a
        # falsehood now.
        self.assertIn("ORA_HOME is set explicitly", explicit)
        self.assertIn("install there too", explicit)
        self.assertNotIn("install into this", explicit)

        # Unset is the ordinary case: $HOME/ora by default, the clone in
        # practice, and no reason for alarm beyond naming the mismatch.
        default = self._preflight_transcript({"HOME": str(Path(REPO_ROOT).parent)})
        self.assertIn("(home-default)", default)
        self.assertIn("start.sh, start.bat", default)
        self.assertNotIn("ORA_HOME is set explicitly", default)

    def test_the_step_is_in_the_pipeline_after_dependencies(self):
        source = (REPO_ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
        self.assertIn('("converters",     step_converters,', source)
        self.assertLess(source.index('("dependencies",   step_dependencies'),
                        source.index('("converters",     step_converters'))


# ─── Catalog outage policy + promised presets ────────────────────────────


class TestCatalogBaseline(unittest.TestCase):
    """What counts as a catalog the install can fall back on."""

    def _baseline_at(self, path):
        with mock.patch.dict(os.environ, {"ORA_MODEL_CATALOG_PATH": str(path)}):
            return install._catalog_baseline()

    def test_the_catalog_this_repository_ships_is_usable(self):
        # The whole policy rests on a clean clone already carrying a catalog
        # good enough to fill every preset. If that stops being true, an
        # offline install stops working and this is where it shows up.
        usable, description = install._catalog_baseline()
        self.assertTrue(usable, description)
        self.assertRegex(description, r"^\d+ models \(\d+ free, \d+ with an intelligence score\)")

    def test_a_missing_catalog_is_not_a_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            usable, description = self._baseline_at(Path(tmp) / "gone.json")
            self.assertFalse(usable)
            self.assertIn("there is no catalog at", description)

    def test_an_unreadable_catalog_names_the_read_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-catalog.json"
            path.write_text('{"models": [', encoding="utf-8")
            usable, description = self._baseline_at(path)
            self.assertFalse(usable)
            self.assertIn("could not be read", description)
            self.assertIn("JSONDecodeError", description)

    def test_a_catalog_with_no_models_is_not_a_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-catalog.json"
            path.write_text('{"models": []}', encoding="utf-8")
            usable, description = self._baseline_at(path)
            self.assertFalse(usable)
            self.assertIn("lists no models", description)

    def test_entries_without_an_id_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-catalog.json"
            path.write_text('{"models": [{"display_name": "x"}]}', encoding="utf-8")
            usable, description = self._baseline_at(path)
            self.assertFalse(usable)
            self.assertIn("carries a model id", description)


class TestCatalogOutagePolicy(unittest.TestCase):
    """Pre-flight and step 5 must tell the user the same story."""

    def _transcript(self, fn, *args, **kwargs):
        lines = []
        with mock.patch.object(install, "log", side_effect=lines.append):
            result = fn(*args, **kwargs)
        return result, "\n".join(lines)

    def test_preflight_and_step_five_quote_one_policy(self):
        _, preflight = self._transcript(install._log_catalog_outage_policy)
        _, step_five = self._transcript(
            install.step_catalog_refresh, {"steps_completed": []}, True)
        self.assertIn(install.CATALOG_OUTAGE_POLICY, preflight)
        self.assertIn(install.CATALOG_OUTAGE_POLICY, step_five)

    def test_preflight_says_an_outage_is_survivable_when_a_baseline_exists(self):
        _, transcript = self._transcript(install._log_catalog_outage_policy)
        self.assertIn("does not stop the install", transcript)
        self.assertIn("packaged catalog is usable", transcript)
        self.assertNotIn("will halt the install", transcript)

    def test_preflight_predicts_the_halt_when_no_baseline_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                {"ORA_MODEL_CATALOG_PATH": str(Path(tmp) / "gone.json")},
            ):
                _, transcript = self._transcript(install._log_catalog_outage_policy)
        self.assertIn("no usable catalog to fall back on", transcript)
        self.assertIn("step 5 will halt the install", transcript)

    def test_a_failed_refresh_continues_on_a_usable_baseline(self):
        state = {"steps_completed": []}
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="[refresh-catalog] OpenRouter fetch failed. Aborting.",
        )
        with mock.patch.object(install.subprocess, "run", return_value=failed), \
                mock.patch.object(install, "save_state"):
            ok, transcript = self._transcript(
                install.step_catalog_refresh, state, False)
        self.assertTrue(ok)
        self.assertIn("catalog", state["steps_completed"])
        self.assertIn("OpenRouter fetch failed", transcript)
        self.assertIn("Continuing on the catalog packaged with this checkout", transcript)
        self.assertIn(install.CATALOG_REFRESH_RETRY_COMMAND, transcript)

    def test_a_failed_refresh_halts_once_when_there_is_no_baseline(self):
        state = {"steps_completed": []}
        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom")
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "model-catalog.json"
            with mock.patch.dict(os.environ, {"ORA_MODEL_CATALOG_PATH": str(missing)}), \
                    mock.patch.object(install.subprocess, "run", return_value=failed), \
                    mock.patch.object(install, "save_state"):
                ok, transcript = self._transcript(
                    install.step_catalog_refresh, state, False)
        self.assertFalse(ok)
        self.assertNotIn("catalog", state["steps_completed"])
        self.assertIn("There is no catalog to fall back on", transcript)
        self.assertIn(str(missing), transcript)

    def test_a_timeout_takes_the_same_fallback_as_an_outage(self):
        state = {"steps_completed": []}
        with mock.patch.object(
            install.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="refresh", timeout=120),
        ), mock.patch.object(install, "save_state"):
            ok, transcript = self._transcript(
                install.step_catalog_refresh, state, False)
        self.assertTrue(ok)
        self.assertIn("did not finish within 120s", transcript)
        self.assertIn("Continuing on the catalog packaged with this checkout", transcript)


class TestPromisedPresets(unittest.TestCase):
    """Ora promises four preset cards; the install has to deliver all four."""

    def test_every_source_names_the_same_four_presets(self):
        from orchestrator import active_configuration as ac
        from orchestrator import runtime_paths as rp
        declared = json.loads(
            (REPO_ROOT / "config" / "configuration-presets.json").read_text()
        )["presets"]
        pane_source = (REPO_ROOT / "server" / "static" / "models-pane.js").read_text()
        pane_order = re.search(
            r"var PRESET_ORDER = \[([^\]]*)\];", pane_source).group(1)
        pane_names = re.findall(r"'([a-z]+)'", pane_order)
        self.assertEqual(set(declared), {"free", "budget", "speed", "premium"})
        self.assertEqual(set(rp.PRESET_NAMES), set(declared))
        self.assertEqual(set(ac.PRESET_ORDER), set(declared))
        self.assertEqual(pane_names, list(ac.PRESET_ORDER))

    def _bake_transcript(self, listing, baked=None, *, catalogs=None):
        """Run the preset half against a canned listing, capturing what it says.

        ``catalogs`` is ``(picker_path, baker_path)`` when the test wants the
        two halves of step 7 to disagree about which catalog they read.
        """
        from orchestrator import active_configuration as ac
        lines = []
        patches = [
            mock.patch.object(install, "_refresh_local_model_inventory",
                              return_value=None),
            mock.patch.object(ac, "bake_missing_presets",
                              return_value=baked or []),
            mock.patch.object(ac, "list_configurations", return_value=listing),
            mock.patch.object(install, "log", side_effect=lines.append),
        ]
        if catalogs:
            picker, baker = catalogs
            patches.append(mock.patch.dict(
                os.environ, {"ORA_MODEL_CATALOG_PATH": str(picker)}))
            patches.append(mock.patch.object(
                ac, "_catalog_path", return_value=Path(baker)))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            ok = install._bake_promised_presets()
        return ok, "\n".join(lines)

    @staticmethod
    def _summary(name, incomplete=False):
        return {"name": name, "big1": "big", "fast1": "fast", "small": "small",
                "incomplete": incomplete}

    def test_all_four_present_is_a_pass(self):
        from orchestrator import active_configuration as ac
        listing = {
            "presets": {n: self._summary(n) for n in ac.PRESET_ORDER},
            "preset_errors": {},
        }
        ok, transcript = self._bake_transcript(listing, baked=list(ac.PRESET_ORDER))
        self.assertTrue(ok)
        self.assertIn("All 4 promised presets exist", transcript)

    def test_a_missing_preset_halts_and_names_its_cause(self):
        from orchestrator import active_configuration as ac
        presets = {n: self._summary(n) for n in ac.PRESET_ORDER}
        presets["speed"] = None
        listing = {
            "presets": presets,
            "preset_errors": {"speed": "ValueError: no candidate met the floor"},
        }
        ok, transcript = self._bake_transcript(listing)
        self.assertFalse(ok)
        self.assertIn("do not exist after the bake: speed", transcript)
        self.assertIn("ValueError: no candidate met the floor", transcript)

    def test_an_incomplete_preset_is_flagged_but_does_not_halt(self):
        from orchestrator import active_configuration as ac
        presets = {n: self._summary(n) for n in ac.PRESET_ORDER}
        presets["speed"] = self._summary("speed", incomplete=True)
        listing = {"presets": presets, "preset_errors": {}}
        ok, transcript = self._bake_transcript(listing, baked=list(ac.PRESET_ORDER))
        self.assertTrue(ok)
        self.assertIn("Some slots came out empty", transcript)

    # ── A preset file with no model in it is not a preset ──────────────
    #
    # The bake writes a file whenever the picker returns without raising, and
    # on a catalog holding nothing usable the picker returns cleanly with
    # every slot empty. That used to read as four warnings followed by "All 4
    # promised presets exist" and a clean INSTALL_COMPLETE, over four blank
    # cards and a pipeline with nothing to call.

    @staticmethod
    def _empty_summary(name):
        return {"name": name, "big1": None, "big2": None, "fast1": None,
                "fast2": None, "small": None, "incomplete": True}

    @staticmethod
    def _summary_missing_one_slot(name):
        """The genuinely thin case: a catalog that fills most slots but has
        no candidate for one of them. Ordinary incompleteness, not a halt."""
        return {"name": name, "big1": "big", "big2": None, "fast1": None,
                "fast2": None, "small": "small", "incomplete": True}

    def test_a_bake_that_fills_nothing_at_all_halts_the_install(self):
        from orchestrator import active_configuration as ac
        listing = {
            "presets": {n: self._empty_summary(n) for n in ac.PRESET_ORDER},
            "preset_errors": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            junk = Path(tmp) / "model-catalog.json"
            junk.write_text(
                json.dumps({"models": [{"id": "junk/not-a-real-model"}]}),
                encoding="utf-8")
            with mock.patch.dict(os.environ, {"ORA_MODEL_CATALOG_PATH": str(junk)}):
                ok, transcript = self._bake_transcript(
                    listing, baked=list(ac.PRESET_ORDER))
        self.assertFalse(ok)
        self.assertIn(
            "baked with no model in any slot: free, budget, speed, premium",
            transcript)
        # The message has to name the real problem — the catalog behind the
        # picks — not just the presets that came out of it.
        self.assertIn("They were picked from a catalog holding 1 models", transcript)
        self.assertIn("Get a current one with", transcript)
        self.assertIn(install.CATALOG_REFRESH_RETRY_COMMAND, transcript)
        self.assertNotIn("promised presets exist", transcript)

    # ── The halt has to describe the catalog the presets came out of ───
    #
    # The two halves of step 7 resolve the catalog differently, so on a
    # machine with a runtime overlay the presets are picked from a file the
    # picker CLI never opens. A halt that described the picker's file instead
    # told the user their four blank presets came from a 296-model catalog,
    # named no path at all, and sent them to a refresh that rewrites the file
    # that was already fine — straight back into the identical halt.

    def test_an_empty_preset_halt_describes_the_catalog_the_baker_read(self):
        from orchestrator import active_configuration as ac
        listing = {
            "presets": {n: self._empty_summary(n) for n in ac.PRESET_ORDER},
            "preset_errors": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            picker = Path(tmp) / "config" / "model-catalog.json"
            picker.parent.mkdir(parents=True)
            picker.write_text(json.dumps({"models": [
                {"id": f"vendor/model-{i}", "aa_intelligence_index": 40}
                for i in range(12)
            ]}), encoding="utf-8")
            baker = Path(tmp) / "data" / "runtime" / "config" / "model-catalog.json"
            baker.parent.mkdir(parents=True)
            baker.write_text(
                json.dumps({"models": [{"id": "junk/not-a-real-model"}]}),
                encoding="utf-8")
            ok, transcript = self._bake_transcript(
                listing, baked=list(ac.PRESET_ORDER), catalogs=(picker, baker))
        self.assertFalse(ok)
        # The baker's one-model file, not the picker's healthy dozen.
        self.assertIn("They were picked from a catalog holding 1 models", transcript)
        self.assertNotIn("12 models", transcript)

    def test_an_empty_preset_halt_names_both_catalogs_when_they_disagree(self):
        from orchestrator import active_configuration as ac
        listing = {
            "presets": {n: self._empty_summary(n) for n in ac.PRESET_ORDER},
            "preset_errors": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            picker = Path(tmp) / "config" / "model-catalog.json"
            picker.parent.mkdir(parents=True)
            picker.write_text(
                json.dumps({"models": [{"id": "fine/model"}]}), encoding="utf-8")
            baker = Path(tmp) / "data" / "runtime" / "config" / "model-catalog.json"
            ok, transcript = self._bake_transcript(
                listing, baked=list(ac.PRESET_ORDER), catalogs=(picker, baker))
        self.assertFalse(ok)
        self.assertIn("read different", transcript)
        self.assertIn(f"The picker read {picker}", transcript)
        self.assertIn(f"the preset baker read {baker}", transcript)
        # And it says which half is the one that still looks fine, so the
        # healthy user-pipeline line printed above is not read as a
        # contradiction.
        self.assertIn("The user-pipeline line above can look healthy", transcript)

    def test_one_catalog_for_both_halves_says_nothing_about_a_split(self):
        from orchestrator import active_configuration as ac
        listing = {
            "presets": {n: self._empty_summary(n) for n in ac.PRESET_ORDER},
            "preset_errors": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "model-catalog.json"
            shared.write_text(
                json.dumps({"models": [{"id": "junk/not-a-real-model"}]}),
                encoding="utf-8")
            ok, transcript = self._bake_transcript(
                listing, baked=list(ac.PRESET_ORDER), catalogs=(shared, shared))
        self.assertFalse(ok)
        self.assertIn("no model in any slot", transcript)
        self.assertNotIn("different catalog files", transcript)
        self.assertNotIn("The picker read", transcript)

    def test_one_empty_preset_among_four_halts_and_names_only_that_one(self):
        from orchestrator import active_configuration as ac
        presets = {n: self._summary(n) for n in ac.PRESET_ORDER}
        presets["premium"] = self._empty_summary("premium")
        ok, transcript = self._bake_transcript(
            {"presets": presets, "preset_errors": {}},
            baked=list(ac.PRESET_ORDER))
        self.assertFalse(ok)
        halt_line = [line for line in transcript.split("\n")
                     if "baked with no model in any slot" in line]
        self.assertEqual(
            halt_line,
            ["  ✗ These presets baked with no model in any slot: premium"])

    def test_a_thin_catalog_that_leaves_one_slot_empty_still_finishes(self):
        # The line between "thin" and "absent": Free has a big model and a
        # small model but nothing for its fast slot. That is the warning it
        # has always been, and the install completes.
        from orchestrator import active_configuration as ac
        presets = {n: self._summary(n) for n in ac.PRESET_ORDER}
        presets["free"] = self._summary_missing_one_slot("free")
        ok, transcript = self._bake_transcript(
            {"presets": presets, "preset_errors": {}},
            baked=list(ac.PRESET_ORDER))
        self.assertTrue(ok)
        self.assertIn("⚠ free: big big · fast — · small small", transcript)
        self.assertIn("Some slots came out empty", transcript)
        self.assertIn("All 4 promised presets exist", transcript)
        self.assertNotIn("no model in any slot", transcript)

    def test_one_filled_slot_anywhere_is_enough_to_count_as_baked(self):
        # Whatever the card shows a model in — big, fast, small, or one of
        # the second-column slots — the preset exists and can be repaired
        # from the pane. Only a file with nothing in it is treated as absent.
        for slot in install.CARD_SLOTS:
            summary = self._empty_summary("speed")
            summary[slot] = "some/model"
            self.assertEqual(install._card_picks(summary), ["some/model"], slot)
        self.assertEqual(install._card_picks(self._empty_summary("speed")), [])

    def test_step_seven_is_still_the_seventh_step(self):
        source = (REPO_ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
        self.assertIn('("autopopulate",   step_autopopulate,', source)
        self.assertIn("Step 7/9:", source)
        self.assertIn("_bake_promised_presets()", source)


class TestActiveConfiguration(unittest.TestCase):
    """The same honesty test, applied to the configuration Ora runs on.

    Step 7 fills ``user-pipeline`` through the picker CLI and bakes the four
    preset cards through the runtime's baker, and the two do not find the model
    catalog the same way — the CLI takes ORA_MODEL_CATALOG_PATH or this
    checkout's ``config/model-catalog.json``, the baker prefers a runtime
    overlay copy when one exists. A stale overlay therefore lets the presets
    bake perfectly out of one catalog while ``user-pipeline`` is picked out of
    another and comes out blank — and ``user-pipeline`` is the one the pipeline
    actually runs on.
    """

    @staticmethod
    def _summary(**slots):
        base = {"name": install.ACTIVE_CONFIGURATION, "big1": None, "big2": None,
                "fast1": None, "fast2": None, "small": None, "incomplete": True}
        base.update(slots)
        return base

    def _verify_transcript(self, listing, *, catalogs=None):
        """Run the read-back against a canned listing, capturing what it says.

        ``catalogs`` is ``(picker_path, baker_path)`` when the test wants the
        two halves of step 7 to disagree about which catalog they read.
        """
        from orchestrator import active_configuration as ac
        lines = []
        patches = [
            mock.patch.object(ac, "list_configurations", return_value=listing),
            mock.patch.object(install, "log", side_effect=lines.append),
        ]
        if catalogs:
            picker, baker = catalogs
            patches.append(mock.patch.dict(
                os.environ, {"ORA_MODEL_CATALOG_PATH": str(picker)}))
            patches.append(mock.patch.object(
                ac, "_catalog_path", return_value=Path(baker)))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            ok = install._verify_active_configuration()
        return ok, "\n".join(lines)

    def test_a_populated_active_configuration_passes(self):
        listing = {"presets": {}, "customs": [self._summary(
            big1="big", fast1="fast", small="small", incomplete=False)]}
        ok, transcript = self._verify_transcript(listing)
        self.assertTrue(ok)
        self.assertIn("✓ user-pipeline: big big · fast fast · small small",
                      transcript)
        self.assertNotIn("no model in any slot", transcript)

    def test_an_empty_active_configuration_halts_the_install(self):
        listing = {"presets": {}, "customs": [self._summary()]}
        with tempfile.TemporaryDirectory() as tmp:
            junk = Path(tmp) / "model-catalog.json"
            junk.write_text(
                json.dumps({"models": [{"id": "junk/not-a-real-model"}]}),
                encoding="utf-8")
            with mock.patch.dict(os.environ, {"ORA_MODEL_CATALOG_PATH": str(junk)}):
                ok, transcript = self._verify_transcript(listing)
        self.assertFalse(ok)
        self.assertIn(
            "This configuration was picked with no model in any slot: "
            "user-pipeline", transcript)
        # It has to name the real cause — the catalog behind the picks — and
        # the one command that gets a current one.
        self.assertIn("It was picked from a catalog holding 1 models", transcript)
        self.assertIn(install.CATALOG_REFRESH_RETRY_COMMAND, transcript)
        # And say why this one matters more than any single preset.
        self.assertIn("the configuration Ora serves", transcript)

    def test_the_halt_names_both_catalogs_when_the_two_halves_disagree(self):
        # The reported case: a stale runtime overlay, presets baked from it,
        # user-pipeline picked from the checkout's own copy and blank.
        listing = {"presets": {}, "customs": [self._summary()]}
        with tempfile.TemporaryDirectory() as tmp:
            picker = Path(tmp) / "config" / "model-catalog.json"
            picker.parent.mkdir(parents=True)
            picker.write_text(
                json.dumps({"models": [{"id": "stale/model"}]}), encoding="utf-8")
            baker = Path(tmp) / "data" / "runtime" / "config" / "model-catalog.json"
            ok, transcript = self._verify_transcript(
                listing, catalogs=(picker, baker))
        self.assertFalse(ok)
        self.assertIn("read different catalog files", transcript)
        self.assertIn(f"The picker read {picker}", transcript)
        self.assertIn(f"the preset baker read {baker}", transcript)

    def test_one_catalog_for_both_halves_says_nothing_about_a_split(self):
        listing = {"presets": {}, "customs": [self._summary()]}
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp) / "model-catalog.json"
            shared.write_text(
                json.dumps({"models": [{"id": "stale/model"}]}), encoding="utf-8")
            ok, transcript = self._verify_transcript(
                listing, catalogs=(shared, shared))
        self.assertFalse(ok)
        self.assertIn("no model in any slot", transcript)
        self.assertNotIn("different catalog files", transcript)

    def test_a_partly_filled_active_configuration_still_finishes(self):
        # The line between "thin" and "absent" is the same one the presets
        # draw: a big model and a small model but nothing for fast is the
        # warning it has always been, and the install completes.
        listing = {"presets": {}, "customs": [self._summary(
            big1="big", small="small", incomplete=True)]}
        ok, transcript = self._verify_transcript(listing)
        self.assertTrue(ok)
        # Flagged exactly the way a thin preset card is, and it still passes.
        self.assertIn("⚠ user-pipeline: big big · fast — · small small",
                      transcript)
        self.assertIn("Some slots came out empty", transcript)
        self.assertNotIn("no model in any slot", transcript)

    def test_one_filled_slot_anywhere_is_enough(self):
        for slot in install.CARD_SLOTS:
            listing = {"presets": {},
                       "customs": [self._summary(**{slot: "some/model"})]}
            ok, _transcript = self._verify_transcript(listing)
            self.assertTrue(ok, slot)

    def test_an_absent_active_configuration_halts_too(self):
        listing = {"presets": {}, "customs": [
            {"name": "something-else", "big1": "big"}]}
        ok, transcript = self._verify_transcript(listing)
        self.assertFalse(ok)
        self.assertIn("user-pipeline does not exist after the picker ran",
                      transcript)

    def test_it_is_found_even_when_adopted_into_a_preset_slot(self):
        # user-pipeline carries preset_lineage "budget"; with no budget.json of
        # its own it can be adopted into that preset slot instead of appearing
        # among the customs. It still has to be checked.
        listing = {"presets": {"budget": self._summary()}, "customs": []}
        ok, transcript = self._verify_transcript(listing)
        self.assertFalse(ok)
        self.assertIn("no model in any slot: user-pipeline", transcript)

    def test_an_unreadable_listing_halts_rather_than_passes(self):
        from orchestrator import active_configuration as ac
        lines = []
        with mock.patch.object(ac, "list_configurations",
                               side_effect=OSError("disk gone")), \
                mock.patch.object(install, "log", side_effect=lines.append):
            ok = install._verify_active_configuration()
        self.assertFalse(ok)
        self.assertIn("Could not read user-pipeline back", "\n".join(lines))

    def test_presets_and_the_active_configuration_share_one_rule(self):
        # There is one emptiness test and one halt message, and both halves of
        # step 7 go through them — not two guards that have to be kept in step.
        source = (REPO_ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("def _card_picks("), 1)
        self.assertEqual(source.count("def _report_no_model_in_any_slot("), 1)
        self.assertEqual(source.count("def _catalog_split_note("), 1)
        for half in ("def _bake_promised_presets(",
                     "def _verify_active_configuration("):
            body = source.split(half)[1].split("\ndef ")[0]
            self.assertIn("_card_picks(", body, half)
            self.assertIn("_report_no_model_in_any_slot(", body, half)
            # Each half names the catalog its own picks came from, and each
            # reaches for the same split note when the two disagree. A half
            # that leaves either to the default is the half that ends up
            # describing somebody else's file.
            self.assertIn("catalog=", body, half)
            self.assertIn("_catalog_split_note(", body, half)
        # And step 7 actually runs the read-back.
        self.assertIn("_verify_active_configuration()", source)

    def test_the_step_runs_the_read_back_after_the_presets(self):
        source = (REPO_ROOT / "scripts" / "install.py").read_text(encoding="utf-8")
        step = source.split("def step_autopopulate(")[1]
        self.assertLess(step.index("_bake_promised_presets()"),
                        step.index("_verify_active_configuration()"))


class TestBakerLinesReachTheInstallLog(unittest.TestCase):
    """What the preset baker says has to survive into install.log.

    The installer calls the baker in-process, so the two lines only it can
    write — why a preset did not bake, and the warning that a forced bake has
    just overwritten hand-picked slots — landed on the terminal and stopped
    there. install.log is the file the install points the user at when
    something has gone wrong, and the replacement warning exists precisely so
    a destructive act is on the record; missing from that file, it was doing
    half its job.
    """

    def test_a_relayed_line_is_written_to_install_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "install.log"
            with mock.patch.object(install, "LOG_PATH", log_path):
                install._relay_baker_line(
                    "[presets] speed: replacing the existing configuration")
            written = log_path.read_text(encoding="utf-8")
        self.assertIn("[presets] speed: replacing the existing configuration",
                      written)
        # Indented to sit with the ✓ and ⚠ lines of the step around it.
        self.assertRegex(written, r"^\[[0-9:]{8}\]   \[presets\] ")

    def test_the_bake_is_handed_that_relay_rather_than_left_to_print(self):
        from orchestrator import active_configuration as ac
        seen = {}

        def _capture(force=False, **kwargs):
            seen.update(kwargs)
            seen["force"] = force
            return []

        with mock.patch.object(install, "_refresh_local_model_inventory",
                               return_value=None), \
                mock.patch.object(ac, "bake_missing_presets",
                                  side_effect=_capture), \
                mock.patch.object(ac, "list_configurations",
                                  return_value={"presets": {}, "preset_errors": {}}), \
                mock.patch.object(install, "log"):
            install._bake_promised_presets()
        self.assertTrue(seen.get("force"))
        self.assertIs(seen.get("log"), install._relay_baker_line)

    def test_both_lost_messages_travel_the_relay_end_to_end(self):
        """Drive the real baker with a stub picker and read install.log back.

        Not a mocked return value: a preset file is on disk, ``force=True``
        replaces it, and the picker raises for one preset. Those are the exact
        two lines that used to go nowhere.
        """
        from orchestrator import active_configuration as ac

        class _AP:
            @staticmethod
            def registry_crossref(path=None):
                return {}

            @staticmethod
            def populate_configuration(preset_name, catalog, presets, **kwargs):
                if preset_name == "premium":
                    raise ValueError("no candidate met the floor")
                return {
                    "preset_lineage": preset_name,
                    "cells": {
                        "utility": {"step1_cleanup": {"primary": "small",
                                                      "fallback": []}},
                        "analysis": {
                            "gear4": {"depth": {"primary": "big", "fallback": []},
                                      "breadth": None},
                            "gear3": {"depth": {"primary": "fast", "fallback": []},
                                      "breadth": None},
                        },
                        "post_analysis": {},
                    },
                }

        seeded = {
            "name": "premium", "preset_lineage": "premium",
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
        }

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config" / "configurations").mkdir(parents=True)
            (home / "scripts").mkdir()
            (home / "config" / "configuration-presets.json").write_text(
                json.dumps({"presets": {}}), encoding="utf-8")
            (home / "config" / "model-catalog.json").write_text(
                json.dumps({"models": [{"id": "m"}]}), encoding="utf-8")
            (home / "scripts" / "auto-populate-configuration.py").write_text(
                "# stub\n", encoding="utf-8")
            (home / "config" / "configurations" / "premium.json").write_text(
                json.dumps(seeded), encoding="utf-8")
            log_path = home / "install.log"

            import importlib.util as ilu
            fake_spec = type("S", (), {"loader": type(
                "L", (), {"exec_module": staticmethod(lambda m: None)})()})
            with mock.patch.object(install, "LOG_PATH", log_path), \
                    mock.patch.object(ac, "ORA_HOME", home), \
                    mock.patch.object(ac, "CONFIGURATIONS_DIR",
                                      home / "config" / "configurations"), \
                    mock.patch.object(ac, "DATA_DIR", home / "data"), \
                    mock.patch.object(ilu, "spec_from_file_location",
                                      lambda name, path: fake_spec()), \
                    mock.patch.object(ilu, "module_from_spec", lambda spec: _AP), \
                    contextlib.redirect_stdout(io.StringIO()):
                ac._bake_errors.clear()
                try:
                    ac.bake_missing_presets(force=True,
                                            log=install._relay_baker_line)
                finally:
                    ac._bake_errors.clear()
            written = log_path.read_text(encoding="utf-8")

        self.assertIn("[presets] premium: replacing the existing configuration",
                      written)
        self.assertIn("any hand-picked slots in it are overwritten", written)
        self.assertIn("[presets] premium did not bake — "
                      "ValueError: no candidate met the floor", written)
        # One line per replaced file, not one per preset considered.
        self.assertEqual(written.count("replacing the existing configuration"), 1)


if __name__ == "__main__":
    unittest.main()
