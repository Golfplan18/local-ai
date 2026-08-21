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


if __name__ == "__main__":
    unittest.main()
