"""Focused contract tests for the runtime Resources watcher."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO_ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import resources_watcher as rw  # noqa: E402
from oversight_sandbox import redirect_oversight_logs  # noqa: E402


class ResourcesWatcherTests(unittest.TestCase):
    def setUp(self):
        # Must precede watcher-specific path patches: audit events emitted by
        # the watcher must never reach the live oversight event/router logs.
        redirect_oversight_logs(self)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inbound = self.root / "Ora Resources"
        self.vault = self.root / "vault"
        self.resources = self.vault / "Resources"
        self.state = self.root / "runtime-state"
        self.oversight = self.root / "oversight"
        self.inbound.mkdir()
        self.vault.mkdir()
        self.resources.mkdir()
        self.patches = [
            mock.patch.object(rw, "OVERSIGHT_DATA_DIR", str(self.oversight)),
            mock.patch.object(
                rw, "HEARTBEAT_FILE",
                str(self.oversight / "resources-watcher-heartbeat.json"),
            ),
        ]
        for patch in self.patches:
            patch.start()
        self.addCleanup(self.temp.cleanup)
        for patch in reversed(self.patches):
            self.addCleanup(patch.stop)

    def sweep(self, *, indexer=None, **kwargs):
        indexer = indexer or mock.Mock(
            return_value={"indexed": 1, "skipped": 0, "errors": 0},
        )
        with mock.patch.object(rw, "_index_reading_copy", indexer):
            result = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                settle_seconds=0,
                **kwargs,
            )
        return result, indexer

    def test_txt_ingest_writes_canonical_reading_copy_and_is_idempotent(self):
        source = self.inbound / "Research Notes.txt"
        source.write_text("A sufficiently substantive source document.\n", encoding="utf-8")
        indexer = mock.Mock(
            return_value={"indexed": 1, "skipped": 0, "errors": 0},
        )

        first, _ = self.sweep(indexer=indexer)
        second, _ = self.sweep(indexer=indexer)

        self.assertEqual(first["processed"], 1)
        self.assertEqual(second["unchanged"], 1)
        indexer.assert_called_once()
        copies = list(self.resources.glob("*.md"))
        self.assertEqual(len(copies), 1)
        body = copies[0].read_text(encoding="utf-8")
        self.assertIn("nexus:\ntype: resource\ntags:\n", body)
        self.assertIn('source_file: "Research Notes.txt"', body)
        self.assertIn("source_format: txt", body)
        self.assertRegex(body, r"processed_date: \d{4}-\d{2}-\d{2}")
        self.assertRegex(body, r"date created: \d{4}-\d{2}-\d{2}")
        self.assertRegex(body, r"date modified: \d{4}-\d{2}-\d{2}")
        self.assertIn(f"# {copies[0].stem}\n", body)

    def test_index_call_uses_force_hcp_path_and_chroma_override(self):
        source = self.inbound / "Long.txt"
        source.write_text("Long source text " * 10, encoding="utf-8")
        chroma = self.root / "alternate-chroma"
        result = {"indexed": 1, "skipped": 0, "errors": 0}
        with mock.patch(
            "orchestrator.tools.knowledge_index.index_single_file",
            return_value=result,
        ) as index_single:
            summary = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                chromadb_path=chroma,
                settle_seconds=0,
            )
        self.assertEqual(summary["processed"], 1)
        index_single.assert_called_once()
        _args, kwargs = index_single.call_args
        self.assertTrue(kwargs["force"])
        self.assertEqual(kwargs["chromadb_path"], chroma)

    def test_index_call_uses_call_time_chroma_default(self):
        source = self.inbound / "Portable.txt"
        source.write_text("Portable source text " * 10, encoding="utf-8")
        chroma = self.root / "late-chroma"
        result = {"indexed": 1, "skipped": 0, "errors": 0}
        with mock.patch.object(
            rw._rp, "chromadb_dir", return_value=chroma,
        ) as chromadb_dir, mock.patch(
            "orchestrator.tools.knowledge_index.index_single_file",
            return_value=result,
        ) as index_single:
            summary = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                settle_seconds=0,
            )

        self.assertEqual(summary["processed"], 1)
        chromadb_dir.assert_called_once_with()
        self.assertEqual(index_single.call_args.kwargs["chromadb_path"], chroma)

    def test_conversion_failure_preserves_original_without_reading_copy(self):
        source = self.inbound / "Scanned.pdf"
        source.write_bytes(b"%PDF-scanned-placeholder")
        with mock.patch.object(
            rw, "_convert_snapshot",
            side_effect=ValueError("conversion returned no readable text"),
        ):
            summary, indexer = self.sweep()
        self.assertTrue(source.exists())
        self.assertEqual(list(self.resources.glob("*.md")), [])
        self.assertTrue(summary["errors"])
        indexer.assert_not_called()
        manifest = json.loads((self.state / "manifest.json").read_text())
        self.assertEqual(next(iter(manifest["entries"].values()))["status"], "failed")

    def test_source_symlink_is_rejected_and_cannot_escape_root(self):
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.inbound / "escape.txt"
        link.symlink_to(outside)
        summary, indexer = self.sweep()
        self.assertEqual(summary["rejected"], 1)
        self.assertIn("symlink", summary["errors"][0])
        self.assertTrue(outside.exists())
        self.assertEqual(list(self.resources.glob("*.md")), [])
        indexer.assert_not_called()

    def test_collision_never_overwrites_user_note(self):
        user_note = self.resources / "Report.md"
        user_note.write_text("USER CONTENT\n", encoding="utf-8")
        (self.inbound / "Report.txt").write_text(
            "Converted report body with enough detail.", encoding="utf-8",
        )
        summary, _ = self.sweep()
        self.assertEqual(summary["processed"], 1)
        self.assertEqual(user_note.read_text(), "USER CONTENT\n")
        generated = [path for path in self.resources.glob("*.md") if path != user_note]
        self.assertEqual(len(generated), 1)
        self.assertIn("txt-", generated[0].name)

    def test_mutated_managed_copy_is_not_adopted_or_overwritten(self):
        (self.inbound / "Report.txt").write_text(
            "Original report body with enough detail.", encoding="utf-8",
        )
        first, _ = self.sweep()
        self.assertEqual(first["processed"], 1)
        original_copy = next(self.resources.glob("*.md"))
        original_copy.write_text("USER REPLACEMENT\n", encoding="utf-8")

        second, _ = self.sweep()

        self.assertEqual(second["processed"], 1)
        self.assertTrue(second["errors"], "mismatch must be reported loudly")
        self.assertEqual(original_copy.read_text(), "USER REPLACEMENT\n")
        self.assertEqual(len(list(self.resources.glob("*.md"))), 2)

    def test_index_failure_resume_reuses_single_exact_reading_copy(self):
        source = self.inbound / "Retry.txt"
        source.write_text("Retryable document body with enough detail.", encoding="utf-8")
        indexer = mock.Mock(side_effect=[
            RuntimeError("embedding temporarily unavailable"),
            {"indexed": 1, "skipped": 0, "errors": 0},
        ])
        with mock.patch.object(rw, "_index_reading_copy", indexer):
            first = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                settle_seconds=0,
            )
            second = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                settle_seconds=0,
            )
        self.assertTrue(first["errors"])
        self.assertEqual(second["processed"], 1)
        self.assertEqual(indexer.call_count, 2)
        self.assertEqual(len(list(self.resources.glob("*.md"))), 1)

    def test_cross_date_index_retry_reuses_persisted_render_bytes(self):
        source = self.inbound / "Midnight.txt"
        source.write_text("Document crossing midnight during index retry.", encoding="utf-8")
        failed_index = mock.Mock(side_effect=RuntimeError("index offline"))
        with mock.patch.object(rw, "_date_values", return_value=(
            "2026-07-12", "2026-07-12",
        )), mock.patch.object(rw, "_index_reading_copy", failed_index):
            first = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                settle_seconds=0,
            )
        reading = next(self.resources.glob("*.md"))
        first_bytes = reading.read_bytes()

        successful_index = mock.Mock(
            return_value={"indexed": 1, "skipped": 0, "errors": 0},
        )
        with mock.patch.object(rw, "_date_values", return_value=(
            "2026-07-13", "2026-07-13",
        )) as second_date, mock.patch.object(
            rw, "_index_reading_copy", successful_index,
        ):
            second = rw.sweep(
                inbound_root=self.inbound,
                vault_root=self.vault,
                state_dir=self.state,
                settle_seconds=0,
            )

        self.assertTrue(first["errors"])
        self.assertEqual(second["processed"], 1)
        self.assertEqual(len(list(self.resources.glob("*.md"))), 1)
        self.assertEqual(reading.read_bytes(), first_bytes)
        self.assertIn(b"processed_date: 2026-07-12", first_bytes)
        self.assertNotIn(b"2026-07-13", first_bytes)
        second_date.assert_not_called()

    def test_orphan_destination_race_preserves_other_process_file(self):
        source = self.vault / "race.txt"
        source.write_text("source payload", encoding="utf-8")
        destination = self.inbound / source.name
        self.state.mkdir()
        real_open = os.open

        def racing_open(path, flags, mode=0o777):
            candidate = Path(path)
            if candidate == destination and flags & os.O_EXCL:
                destination.write_bytes(b"OTHER PROCESS")
            return real_open(path, flags, mode)

        with mock.patch.object(rw.os, "open", side_effect=racing_open):
            with self.assertRaises(FileExistsError):
                rw._move_orphan_no_overwrite(
                    source, self.vault, self.inbound, self.state,
                )
        self.assertTrue(source.exists())
        self.assertEqual(destination.read_bytes(), b"OTHER PROCESS")

    def test_unreferenced_document_moves_on_first_complete_sweep(self):
        loose = self.vault / "Loose.txt"
        loose.write_text("Loose document body with readable content.", encoding="utf-8")
        summary, _ = self.sweep()
        self.assertFalse(loose.exists())
        self.assertTrue((self.inbound / "Loose.txt").exists())
        self.assertEqual(summary["orphans_moved"], 1)
        self.assertEqual(summary["processed"], 1)

    def test_unreferenced_media_requires_two_consecutive_sweeps(self):
        image = self.vault / "photo.jpg"
        image.write_bytes(b"image-bytes")
        first, _ = self.sweep()
        self.assertTrue(image.exists())
        self.assertEqual(first["orphans_moved"], 0)
        self.assertEqual(first["orphan_candidates"], 1)

        second, _ = self.sweep()
        self.assertFalse(image.exists())
        self.assertTrue((self.inbound / "photo.jpg").exists())
        self.assertEqual(second["orphans_moved"], 1)
        # Media is canonical in the external folder, not an unsupported error.
        self.assertFalse(second["errors"])

    def test_replaced_media_at_same_path_resets_consecutive_count(self):
        image = self.vault / "replace.jpg"
        image.write_bytes(b"first-version")
        first, _ = self.sweep()
        self.assertEqual(first["orphan_candidates"], 1)

        # Rewrite the same inode/path with a different size.  Observation
        # identity must change, so this is a new first sighting, not sweep #2.
        image.write_bytes(b"replacement-version-with-different-size")
        second, _ = self.sweep()
        self.assertTrue(image.exists())
        self.assertEqual(second["orphans_moved"], 0)
        manifest = json.loads((self.state / "manifest.json").read_text())
        candidate = next(iter(manifest["orphan_candidates"].values()))
        self.assertEqual(candidate["consecutive_sweeps"], 1)

        third, _ = self.sweep()
        self.assertFalse(image.exists())
        self.assertEqual(third["orphans_moved"], 1)

    def test_referenced_pdf_is_never_moved(self):
        pdf = self.vault / "paper.pdf"
        pdf.write_bytes(b"%PDF-placeholder")
        (self.vault / "Note.md").write_text("See ![[paper.pdf]].\n", encoding="utf-8")
        first, _ = self.sweep()
        second, _ = self.sweep()
        self.assertTrue(pdf.exists())
        self.assertEqual(first["referenced_assets"], 1)
        self.assertEqual(second["referenced_assets"], 1)
        self.assertEqual(second["orphans_moved"], 0)

    def test_unknown_sidecars_and_excluded_directories_are_untouched(self):
        unknown = self.vault / "record.json"
        archived = self.vault / "note.md.archived-20260712"
        unknown.write_text("{}")
        archived.write_text("old")
        for dirname in (".space", ".hidden", "Old AI Working Files", "Archive"):
            folder = self.vault / dirname
            folder.mkdir()
            (folder / "orphan.jpg").write_bytes(b"image")
        self.sweep()
        second, _ = self.sweep()
        self.assertTrue(unknown.exists())
        self.assertTrue(archived.exists())
        for dirname in (".space", ".hidden", "Old AI Working Files", "Archive"):
            self.assertTrue((self.vault / dirname / "orphan.jpg").exists())
        self.assertEqual(second["orphans_moved"], 0)

    def test_missing_original_reports_without_deleting_reading_copy(self):
        source = self.inbound / "Durable.txt"
        source.write_text("Durable source content for a reading copy.", encoding="utf-8")
        self.sweep()
        reading = next(self.resources.glob("*.md"))
        source.unlink()
        summary, _ = self.sweep()
        self.assertEqual(summary["source_mismatches"], 1)
        self.assertTrue(reading.exists())
        audit = (self.state / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn("ResourceSourceMissing", audit)

    def test_dry_run_is_write_free_and_previews_document_media_timing(self):
        state = self.root / "absent-state"
        resources = self.resources
        resources.rmdir()
        document = self.vault / "move-now.txt"
        media = self.vault / "wait.jpg"
        document.write_text("document")
        media.write_bytes(b"media")
        inbound_source = self.inbound / "incoming.txt"
        inbound_source.write_text("incoming")
        heartbeat = Path(rw.HEARTBEAT_FILE)

        result = rw.preview(
            inbound_root=self.inbound,
            vault_root=self.vault,
            state_dir=state,
            settle_seconds=0,
        )

        self.assertIn(str(document), result["would_move_documents"])
        self.assertIn(str(media), result["media_first_seen"])
        self.assertIn(str(inbound_source), result["supported_inbound"])
        self.assertFalse(state.exists())
        self.assertFalse(resources.exists())
        self.assertFalse(heartbeat.exists())
        self.assertTrue(document.exists())
        self.assertTrue(media.exists())

    def test_settle_debounce_defers_inbound_and_conformance_files(self):
        incoming = self.inbound / "new.txt"
        loose = self.vault / "new-too.txt"
        incoming.write_text("incoming")
        loose.write_text("loose")
        result = rw.preview(
            inbound_root=self.inbound,
            vault_root=self.vault,
            state_dir=self.state,
            settle_seconds=60,
        )
        self.assertIn(str(incoming), result["settling_inbound"])
        self.assertIn(str(loose), result["settling_assets"])
        self.assertNotIn(str(loose), result["would_move_documents"])

    def test_unsupported_inbound_is_reported_and_preserved(self):
        unsupported = self.inbound / "payload.json"
        unsupported.write_text("{}")
        summary, indexer = self.sweep()
        self.assertTrue(unsupported.exists())
        self.assertEqual(summary["rejected"], 1)
        self.assertIn("unsupported inbound format", summary["errors"][0])
        indexer.assert_not_called()

    def test_vaultless_cloud_sweep_skips_without_creating_inbound_or_state(self):
        missing_vault = self.root / "cloud-no-vault"
        missing_inbound = self.root / "cloud-inbound"
        missing_state = self.root / "cloud-state"
        summary = rw.sweep(
            inbound_root=missing_inbound,
            vault_root=missing_vault,
            state_dir=missing_state,
            settle_seconds=0,
        )
        self.assertEqual(summary["skipped"], "vault_unavailable")
        self.assertFalse(summary["errors"])
        self.assertFalse(missing_inbound.exists())
        self.assertFalse(missing_state.exists())
        self.assertTrue(Path(rw.HEARTBEAT_FILE).exists())

    def test_defaults_follow_runtime_path_overrides_set_after_import(self):
        documents = self.root / "late-documents"
        inbound = documents / "Ora Resources"
        vault = self.root / "late-vault"
        state = self.root / "late-state"
        inbound.mkdir(parents=True)
        vault.mkdir()

        with mock.patch.dict(
            os.environ,
            {"ORA_DOCUMENTS": str(documents), "ORA_VAULT": str(vault)},
            clear=False,
        ), mock.patch.object(rw, "_index_reading_copy") as indexer:
            summary = rw.sweep(state_dir=state, settle_seconds=0)
            preview = rw.preview(state_dir=state, settle_seconds=0)

        self.assertIsNone(summary["skipped"])
        self.assertFalse(summary["errors"])
        self.assertIsNone(preview["skipped"])
        self.assertFalse(preview["errors"])
        self.assertTrue((vault / "Resources").is_dir())
        self.assertTrue(state.is_dir())
        indexer.assert_not_called()


class AllowlistContractTests(unittest.TestCase):
    def test_batch_and_converter_allowlists_match_approved_contract(self):
        from orchestrator.tools.batch_processor import BatchProcessor
        from orchestrator.tools import format_convert

        self.assertIn(".xlsx", BatchProcessor.SUPPORTED_EXTENSIONS)
        self.assertNotIn(".json", BatchProcessor.SUPPORTED_EXTENSIONS)
        self.assertEqual(
            set(format_convert.detect_format("file" + ext) for ext in rw.SUPPORTED_EXTENSIONS),
            {"pdf", "docx", "pptx", "xlsx", "html", "rtf", "text", "markdown"},
        )


if __name__ == "__main__":
    unittest.main()
