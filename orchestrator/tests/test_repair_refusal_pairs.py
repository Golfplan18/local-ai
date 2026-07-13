"""Portable runtime-path tests for refusal-pair repair provenance."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import repair_refusal_pairs as repair  # noqa: E402


class ResolveRawPathTests(unittest.TestCase):

    def test_all_persisted_provenance_forms_use_configured_documents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            documents = root / "OneDrive" / "Documents"
            expected = (
                documents
                / "Raw Chat Archive"
                / "raw"
                / "nested"
                / "O'Brien Notes.md"
            )
            expected.parent.mkdir(parents=True)
            expected.write_text("canonical", encoding="utf-8")
            env = {
                "HOME": str(root / "profile"),
                "USERPROFILE": str(root / "profile"),
                "ORA_DOCUMENTS": str(documents),
                "ORA_HOME": str(root / "ora"),
            }
            forms = (
                "~/Documents/conversations/raw/nested/O'Brien Notes.md",
                "~/Documents/Raw Chat Archive/raw/nested/O'Brien Notes.md",
                r"~\Documents\conversations\raw\nested\O'Brien Notes.md",
                r"~\Documents\Raw Chat Archive\raw\nested\O'Brien Notes.md",
            )
            with mock.patch.dict(os.environ, env, clear=True):
                for source_chat in forms:
                    with self.subTest(source_chat=source_chat):
                        self.assertEqual(
                            repair.resolve_raw_path(source_chat), str(expected),
                        )

    def test_configured_archive_wins_over_stale_profile_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "profile"
            documents = root / "OneDrive" / "Documents"
            suffix = Path("nested") / "same-name.md"
            stale = home / "Documents" / "conversations" / "raw" / suffix
            canonical = documents / "Raw Chat Archive" / "raw" / suffix
            stale.parent.mkdir(parents=True)
            canonical.parent.mkdir(parents=True)
            stale.write_text("stale", encoding="utf-8")
            canonical.write_text("canonical", encoding="utf-8")
            with mock.patch.dict(os.environ, {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "ORA_DOCUMENTS": str(documents),
                "ORA_HOME": str(root / "ora"),
            }, clear=True):
                resolved = repair.resolve_raw_path(
                    "~/Documents/conversations/raw/nested/same-name.md"
                )

            self.assertEqual(resolved, str(canonical))

    def test_legacy_file_is_fallback_when_relocation_is_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "profile"
            legacy = (
                home
                / "Documents"
                / "conversations"
                / "raw"
                / "legacy-only.md"
            )
            legacy.parent.mkdir(parents=True)
            legacy.write_text("legacy", encoding="utf-8")
            with mock.patch.dict(os.environ, {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "ORA_DOCUMENTS": str(root / "OneDrive" / "Documents"),
                "ORA_HOME": str(root / "ora"),
            }, clear=True):
                resolved = repair.resolve_raw_path(
                    "~/Documents/conversations/raw/legacy-only.md"
                )

            self.assertEqual(resolved, str(legacy))

    def test_arbitrary_existing_explicit_path_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "raw.md"
            path.write_text("raw", encoding="utf-8")
            self.assertEqual(repair.resolve_raw_path(str(path)), str(path))

    def test_unsafe_provenance_suffixes_are_rejected(self):
        unsafe = (
            "~/Documents/conversations/raw/../escape.md",
            "~/Documents/conversations/raw/C:/escape.md",
            "~/Documents/Raw Chat Archive/raw/../../escape.md",
        )
        for source_chat in unsafe:
            with self.subTest(source_chat=source_chat):
                self.assertIsNone(repair.resolve_raw_path(source_chat))

    def test_ntfs_quote_bridge_resolves_renamed_file(self):
        """After renaming '"' → '\'' on disk, provenance tokens that
        still carry '"' resolve through the bridge in resolve_raw_path."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            documents = root / "Documents"
            archive_raw = documents / "Raw Chat Archive" / "raw"
            subdir = archive_raw / "Raw Chats 2025-4-17"
            subdir.mkdir(parents=True)
            renamed_file = subdir / "Analyzing '#We Too' Book Outline.md"
            renamed_file.write_text("test content", encoding="utf-8")
            # The provenance token uses the OLD form with ".
            source_chat = (
                '~/Documents/conversations/raw/Raw Chats 2025-4-17/'
                'Analyzing "#We Too" Book Outline.md'
            )
            env = {
                "HOME": str(root / "profile"),
                "USERPROFILE": str(root / "profile"),
                "ORA_DOCUMENTS": str(documents),
                "ORA_HOME": str(root / "ora"),
            }
            with mock.patch.dict(os.environ, env, clear=True):
                resolved = repair.resolve_raw_path(source_chat)

            self.assertIsNotNone(resolved)
            self.assertEqual(resolved, str(renamed_file))

    def test_ntfs_quote_bridge_returns_none_when_no_renamed_file(self):
        """Bridge returns None when neither the original '"' file nor the
        renamed '\'' file exists at the canonical location."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            documents = root / "Documents"
            env = {
                "HOME": str(root / "profile"),
                "USERPROFILE": str(root / "profile"),
                "ORA_DOCUMENTS": str(documents),
                "ORA_HOME": str(root / "ora"),
            }
            source_chat = (
                '~/Documents/conversations/raw/Raw Chats 2025-4-17/'
                'Analyzing "#We Too" Book Outline.md'
            )
            with mock.patch.dict(os.environ, env, clear=True):
                resolved = repair.resolve_raw_path(source_chat)

            self.assertIsNone(resolved)


class RepairCliRuntimePathTests(unittest.TestCase):

    def test_cli_defaults_resolve_after_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ora_home = root / "Relocated Ora"
            archive = root / "Historical Archive"
            scan_result = {
                "files_scanned": 0,
                "damaged": [],
                "raw_missing": [],
                "legit_signature_files": 0,
            }
            repair_report = {
                "repaired": 0,
                "repaired_files": [],
                "affected_sessions": [],
                "errors_detail": [],
                "client_stats": {},
            }
            with (
                mock.patch.dict(os.environ, {
                    "HOME": str(root / "profile"),
                    "USERPROFILE": str(root / "profile"),
                    "ORA_HOME": str(ora_home),
                    "ORA_HISTORICAL_ARCHIVE": str(archive),
                }, clear=True),
                mock.patch.object(
                    repair, "scan_archive", return_value=scan_result,
                ) as scan_mock,
                mock.patch.object(
                    repair, "repair_damaged", return_value=repair_report,
                ) as repair_mock,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                rc = repair.main(["--scan", "--repair"])

            repair_list = ora_home / "data" / "refusal-repair-list.json"
            report = ora_home / "data" / "refusal-repair-report.json"
            self.assertEqual(rc, 0)
            scan_mock.assert_called_once_with(str(archive))
            self.assertEqual(repair_mock.call_args.args[0], scan_result)
            self.assertTrue(repair_list.is_file())
            self.assertTrue(report.is_file())
            self.assertEqual(
                json.loads(report.read_text(encoding="utf-8"))["repaired"], 0,
            )


if __name__ == "__main__":
    unittest.main()
