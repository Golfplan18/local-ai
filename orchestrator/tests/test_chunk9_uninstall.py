#!/usr/bin/env python3
"""Install Chunk 9 — uninstall.py tests.

Verifies the uninstaller's hard-preserve list catches the vault, the
git checkout, and the source tree, and that the multi-step typed-DELETE
confirmation is the only way to proceed.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

SPEC = importlib.util.spec_from_file_location(
    "uninstall_script", REPO_ROOT / "uninstall" / "uninstall.py",
)
uninstall = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uninstall)
from orchestrator import runtime_paths as rp  # noqa: E402


class TestHardPreserve(unittest.TestCase):
    """The vault and source tree must NEVER be touched, regardless of flags."""

    def test_vault_is_hard_preserved(self):
        self.assertTrue(uninstall._is_hard_preserved(uninstall.VAULT))

    def test_user_roots_match_shared_runtime_snapshot(self):
        roots = rp.resolve_runtime_roots()
        self.assertEqual(uninstall.VAULT, roots.vault)
        self.assertEqual(uninstall.CONVERSATIONS, roots.conversations)

    def test_vault_subpath_is_hard_preserved(self):
        # Defense in depth — a subpath under the vault is also protected.
        self.assertTrue(uninstall._is_hard_preserved(uninstall.VAULT / "anything"))

    def test_source_tree_is_hard_preserved(self):
        for source_dir in ("orchestrator", "server", "scripts", "modes", "frameworks"):
            with self.subTest(dir=source_dir):
                self.assertTrue(uninstall._is_hard_preserved(uninstall.REPO_ROOT / source_dir))

    def test_git_dir_is_hard_preserved(self):
        self.assertTrue(uninstall._is_hard_preserved(uninstall.REPO_ROOT / ".git"))

    def test_uninstall_dir_is_hard_preserved(self):
        # The uninstaller protects itself from accidental self-deletion
        self.assertTrue(uninstall._is_hard_preserved(uninstall.REPO_ROOT / "uninstall"))

    def test_runtime_state_not_hard_preserved(self):
        # install.log IS a removal target
        self.assertFalse(uninstall._is_hard_preserved(uninstall.REPO_ROOT / "install.log"))

    def test_data_dir_not_hard_preserved(self):
        # Runtime data (chroma, traces) is fair game
        self.assertFalse(uninstall._is_hard_preserved(uninstall.REPO_ROOT / "data" / "chroma"))


class TestRemove(unittest.TestCase):
    """_remove honors the hard-preserve list and handles missing paths gracefully."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_remove_existing_file(self):
        target = self.tmp_path / "doomed.txt"
        target.write_text("x")
        self.assertTrue(uninstall._remove(target, dry_run=False))
        self.assertFalse(target.exists())

    def test_remove_existing_directory(self):
        target = self.tmp_path / "doomed_dir"
        target.mkdir()
        (target / "child.txt").write_text("x")
        self.assertTrue(uninstall._remove(target, dry_run=False))
        self.assertFalse(target.exists())

    def test_remove_missing_path_returns_true(self):
        target = self.tmp_path / "does-not-exist"
        # Absent paths are a successful no-op
        self.assertTrue(uninstall._remove(target, dry_run=False))

    def test_dry_run_does_not_delete(self):
        target = self.tmp_path / "spared.txt"
        target.write_text("x")
        self.assertTrue(uninstall._remove(target, dry_run=True))
        self.assertTrue(target.exists())  # preserved

    def test_hard_preserved_path_refused_even_when_passed_directly(self):
        # If someone constructs a removal target that resolves to a
        # hard-preserved path, the remover must refuse.
        self.assertFalse(uninstall._remove(uninstall.VAULT, dry_run=False))
        # Vault still exists after the call
        # (we can't assert this if vault doesn't exist on the test machine,
        # so just confirm the call returned False)


class TestGatherTargets(unittest.TestCase):
    """_gather_targets includes the default removals + opt-in flags."""

    def test_default_targets_only(self):
        targets = uninstall._gather_targets(include_models=False, include_conversations=False)
        # Always-remove list + configurations directory glob
        self.assertIn(uninstall.REPO_ROOT / "install.log", targets)
        self.assertNotIn(uninstall.REPO_ROOT / "models", targets)
        self.assertNotIn(uninstall.CONVERSATIONS, targets)

    def test_include_models_adds_models_dir(self):
        targets = uninstall._gather_targets(include_models=True, include_conversations=False)
        self.assertIn(uninstall.REPO_ROOT / "models", targets)

    def test_include_conversations_adds_conversations_dir(self):
        targets = uninstall._gather_targets(include_models=False, include_conversations=True)
        self.assertIn(uninstall.CONVERSATIONS, targets)

    def test_both_opt_ins(self):
        targets = uninstall._gather_targets(include_models=True, include_conversations=True)
        self.assertIn(uninstall.REPO_ROOT / "models", targets)
        self.assertIn(uninstall.CONVERSATIONS, targets)


class TestConfirmation(unittest.TestCase):
    """Multi-step typed-DELETE confirmation is the only way to proceed."""

    def test_typed_delete_confirms(self):
        with mock.patch("builtins.input", return_value="DELETE"):
            self.assertTrue(uninstall._confirm())

    def test_lowercase_delete_rejected(self):
        with mock.patch("builtins.input", return_value="delete"):
            self.assertFalse(uninstall._confirm())

    def test_yes_rejected(self):
        with mock.patch("builtins.input", return_value="yes"):
            self.assertFalse(uninstall._confirm())

    def test_y_rejected(self):
        with mock.patch("builtins.input", return_value="y"):
            self.assertFalse(uninstall._confirm())

    def test_empty_input_rejected(self):
        with mock.patch("builtins.input", return_value=""):
            self.assertFalse(uninstall._confirm())

    def test_keyboard_interrupt_cancels(self):
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertFalse(uninstall._confirm())

    def test_eof_cancels(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(uninstall._confirm())


if __name__ == "__main__":
    unittest.main()
