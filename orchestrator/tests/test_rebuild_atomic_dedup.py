from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.historical import rebuild_atomic_dedup as rebuild


def _note(title: str = "Claim") -> str:
    return (
        "---\n"
        "source_chat: chat-1\n"
        "seen_count: 2\n"
        "---\n"
        f"# {title}\n\n"
        "A sufficiently long atomic claim body for embedding and deduplication.\n"
    )


class FakeCollection:
    def __init__(self, rows=None, *, fail_upsert: bool = False):
        self.rows = dict(rows or {})
        self.fail_upsert = fail_upsert
        self.upsert_calls = []

    def count(self):
        return len(self.rows)

    def get(self, *, limit, offset, include):
        ids = sorted(self.rows)[offset:offset + limit]
        return {
            "ids": ids,
            "documents": [self.rows[row_id][0] for row_id in ids],
            "metadatas": [self.rows[row_id][1] for row_id in ids],
        }

    def upsert(self, *, ids, documents, metadatas):
        if self.fail_upsert:
            raise RuntimeError("synthetic upsert failure")
        self.upsert_calls.append(list(ids))
        for row_id, document, metadata in zip(ids, documents, metadatas):
            self.rows[row_id] = (document, metadata)


class FakeCollectionDescriptor:
    def __init__(self, name):
        self.name = name


class FakeClient:
    def __init__(self, collection: FakeCollection, names=()):
        self.collection = collection
        self.names = set(names)
        self.deleted = []

    def list_collections(self):
        return [FakeCollectionDescriptor(name) for name in sorted(self.names)]

    def delete_collection(self, name):
        self.deleted.append(name)
        self.names.remove(name)
        self.collection.rows.clear()


class AtomicRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # macOS exposes /var as a symlink to /private/var; use the canonical
        # temporary root so ordinary fixtures do not intentionally violate the
        # all-components no-symlink contract.
        self.base = Path(self.tmp.name).resolve()
        self.active = self.base / "active" / "chromadb"
        self.active.mkdir(parents=True)
        self.target = self.base / "rebuild"
        self.target.mkdir()
        self.vault = self.base / "vault" / "Engrams"
        self.vault.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_note(self, relative="Claim.md", text=None):
        path = self.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_note() if text is None else text, encoding="utf-8")
        return path

    def _run(self, collection, *, drop_existing=False, **kwargs):
        client = FakeClient(collection)
        expected_source_count = sum(1 for _ in self.vault.rglob("*.md"))
        with (
            patch.object(rebuild._rp, "chromadb_dir", return_value=self.active),
            patch.object(rebuild.chromadb, "PersistentClient", return_value=client),
            patch(
                "orchestrator.embedding.get_or_create_collection",
                return_value=collection,
            ),
            patch(
                "orchestrator.embedding.resolve_collection",
                return_value="atomic_dedup_test",
            ),
        ):
            return rebuild.rebuild(
                chromadb_path=self.target,
                expected_source_count=expected_source_count,
                vault_root=self.vault,
                drop_existing=drop_existing,
                max_workers=1,
                batch_size=2,
                **kwargs,
            )

    def test_recovery_target_rejects_active_and_overlapping_paths(self):
        parent = self.active.parent
        child = self.active / "child"
        child.mkdir()
        with patch.object(rebuild._rp, "chromadb_dir", return_value=self.active):
            for candidate in (self.active, parent, child):
                with self.subTest(candidate=candidate):
                    with self.assertRaisesRegex(rebuild.RebuildError, "overlaps"):
                        rebuild.validate_chromadb_target(candidate)

    def test_normal_runtime_only_allows_exact_active_path(self):
        with patch.object(rebuild._rp, "chromadb_dir", return_value=self.active):
            self.assertEqual(
                rebuild.validate_chromadb_target(
                    self.active, allow_active_runtime=True,
                ),
                self.active,
            )
            with self.assertRaises(rebuild.RebuildError):
                rebuild.validate_chromadb_target(
                    self.active.parent, allow_active_runtime=True,
                )

    def test_target_must_be_existing_non_symlink_directory(self):
        missing = self.base / "missing"
        regular_file = self.base / "file"
        regular_file.write_text("x", encoding="utf-8")
        link = self.base / "link"
        link.symlink_to(self.target, target_is_directory=True)
        with patch.object(rebuild._rp, "chromadb_dir", return_value=self.active):
            for candidate in (missing, regular_file, link):
                with self.subTest(candidate=candidate):
                    with self.assertRaises(rebuild.RebuildError):
                        rebuild.validate_chromadb_target(candidate)

    def test_pre_root_alias_is_canonicalized_but_declared_roots_are_anchored(self):
        real_parent = self.base / "real-parent"
        real_parent.mkdir()
        target = real_parent / "target"
        target.mkdir()
        source = real_parent / "Engrams"
        source.mkdir()
        alias = self.base / "alias-parent"
        alias.symlink_to(real_parent, target_is_directory=True)
        with patch.object(rebuild._rp, "chromadb_dir", return_value=self.active):
            self.assertEqual(
                rebuild.validate_chromadb_target(alias / "target"),
                target.resolve(),
            )
        discovered_root, sources = rebuild.discover_sources(alias / "Engrams")
        self.assertEqual(discovered_root, source.resolve())
        self.assertEqual(sources, ())

    def test_source_discovery_rejects_symlink_file_and_directory(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "Other.md").write_text(_note(), encoding="utf-8")
        linked_directory = self.vault / "linked-dir"
        linked_directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(rebuild.RebuildError, "symlink directory"):
            rebuild.discover_sources(self.vault)
        linked_directory.unlink()
        linked_file = self.vault / "linked.md"
        linked_file.symlink_to(outside / "Other.md")
        with self.assertRaisesRegex(rebuild.RebuildError, "symlink file"):
            rebuild.discover_sources(self.vault)

    def test_snapshot_read_is_strict_utf8_and_rejects_identity_change(self):
        invalid = self.vault / "invalid.md"
        invalid.write_bytes(b"\xff\xfe")
        source = rebuild.SourceSnapshot(invalid, rebuild._source_identity(invalid))
        with self.assertRaisesRegex(rebuild.RebuildError, "valid UTF-8"):
            rebuild._read_text_snapshot(source)

        path = self._write_note()
        source = rebuild.SourceSnapshot(path, rebuild._source_identity(path))
        path.write_text(_note("Changed"), encoding="utf-8")
        with self.assertRaisesRegex(rebuild.RebuildError, "changed after discovery"):
            rebuild._read_text_snapshot(source)

    def test_snapshot_detects_edit_when_mtime_is_restored(self):
        path = self._write_note()
        before = path.stat()
        source = rebuild.SourceSnapshot(path, rebuild._source_identity(path))
        original = path.read_text(encoding="utf-8")
        changed = original.replace("# Claim", "# Clamo")
        self.assertEqual(len(original.encode()), len(changed.encode()))
        path.write_text(changed, encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(rebuild.RebuildError, "changed after discovery"):
            rebuild._read_text_snapshot(source)

    def test_invalid_yaml_fails_instead_of_becoming_empty_metadata(self):
        path = self.vault / "bad.md"
        with self.assertRaisesRegex(rebuild.RebuildError, "invalid YAML"):
            rebuild.parse_note_text(
                path,
                "---\ninvalid: [\n---\n# Bad\n\nA long enough body to parse.\n",
            )

    def test_ids_preserve_filename_compatibility_and_paths_normalize(self):
        first = self._write_note("a/Same.md")
        second = self._write_note("b/Same.md")
        self.assertEqual(
            rebuild.stable_id(first, self.vault),
            rebuild.stable_id(second, self.vault),
        )
        self.assertEqual(rebuild.legacy_stable_id(first), rebuild.legacy_stable_id(second))
        self.assertEqual(
            rebuild.normalized_vault_relative_path(first, self.vault),
            "a/Same.md",
        )

    def test_keep_existing_verifies_exact_payload_and_skips(self):
        path = self._write_note()
        plan = rebuild.build_rebuild_plan(self.vault, max_workers=1)
        record = plan.records[0]
        collection = FakeCollection({
            record.row_id: (record.document, dict(record.metadata)),
        })
        summary = self._run(collection)
        self.assertEqual(summary["embedded"], 0)
        self.assertEqual(summary["verified_existing"], 1)
        self.assertEqual(collection.upsert_calls, [])
        self.assertEqual(record.metadata["vault_path"], str(path))

    def test_keep_existing_payload_mismatch_fails_before_upsert(self):
        self._write_note()
        record = rebuild.build_rebuild_plan(self.vault, max_workers=1).records[0]
        collection = FakeCollection({
            record.row_id: (record.document + " changed", dict(record.metadata)),
        })
        with self.assertRaisesRegex(rebuild.RebuildError, "payload mismatch"):
            self._run(collection)
        self.assertEqual(collection.upsert_calls, [])

    def test_keep_existing_metadata_comparison_is_type_exact(self):
        self._write_note()
        record = rebuild.build_rebuild_plan(self.vault, max_workers=1).records[0]
        wrong_metadata = dict(record.metadata)
        wrong_metadata["seen_count"] = 2.0
        collection = FakeCollection({
            record.row_id: (record.document, wrong_metadata),
        })
        with self.assertRaisesRegex(rebuild.RebuildError, "payload mismatch"):
            self._run(collection)
        self.assertEqual(collection.upsert_calls, [])

    def test_duplicate_filename_id_fails_before_chroma_open(self):
        self._write_note("one/Claim.md")
        self._write_note("two/Claim.md")
        with patch.object(rebuild.chromadb, "PersistentClient") as client:
            with self.assertRaisesRegex(rebuild.RebuildError, "ID collision"):
                rebuild.rebuild(
                    chromadb_path=self.target,
                    expected_source_count=2,
                    vault_root=self.vault,
                    drop_existing=False,
                    max_workers=1,
                )
        client.assert_not_called()

    def test_upsert_error_fails_loudly(self):
        self._write_note()
        collection = FakeCollection(fail_upsert=True)
        with self.assertRaisesRegex(rebuild.RebuildError, "upsert failed"):
            self._run(collection)

    def test_success_preserves_source_count_and_short_skip_semantics(self):
        self._write_note("eligible.md")
        self._write_note("short.md", "tiny")
        collection = FakeCollection()
        summary = self._run(collection)
        self.assertEqual(summary["vault_notes"], 2)
        self.assertEqual(summary["eligible_records"], 1)
        self.assertEqual(summary["skipped_short"], 1)
        self.assertEqual(summary["final_count"], 1)
        self.assertEqual(summary["expected_source_count"], 2)
        self.assertEqual(summary["id_audit"], {
            "scheme": "filename-sha256-14",
            "eligible_records": 1,
            "unique_ids": 1,
            "duplicate_ids": 0,
        })

    def test_drop_failures_are_not_swallowed(self):
        self._write_note()
        collection = FakeCollection()
        client = FakeClient(collection, names={"atomic_dedup_test"})
        client.delete_collection = lambda name: (_ for _ in ()).throw(
            RuntimeError("delete failed")
        )
        with (
            patch.object(rebuild._rp, "chromadb_dir", return_value=self.active),
            patch.object(rebuild.chromadb, "PersistentClient", return_value=client),
            patch(
                "orchestrator.embedding.resolve_collection",
                return_value="atomic_dedup_test",
            ),
        ):
            with self.assertRaisesRegex(rebuild.RebuildError, "failed to drop"):
                rebuild.rebuild(
                    chromadb_path=self.target,
                    expected_source_count=1,
                    vault_root=self.vault,
                    drop_existing=True,
                    max_workers=1,
                )

    def test_expected_source_count_mismatch_never_opens_chroma(self):
        self._write_note()
        with patch.object(rebuild.chromadb, "PersistentClient") as client:
            with self.assertRaisesRegex(rebuild.RebuildError, "source count"):
                rebuild.rebuild(
                    chromadb_path=self.target,
                    expected_source_count=122118,
                    vault_root=self.vault,
                    drop_existing=True,
                    max_workers=1,
                )
        client.assert_not_called()

    def test_cli_requires_explicit_chromadb_path(self):
        with self.assertRaises(SystemExit) as raised:
            rebuild._parser().parse_args([])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
