"""Tests for the Phase 2A path2 orchestrator (cleaned-pair → chunks)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.embedding import install_test_stub  # noqa: E402
from orchestrator.historical.path2_orchestrator import (  # noqa: E402
    MAX_EMBED_CHARS,
    SessionEmissionResult,
    emit_chunks_for_session,
    emit_chunks_for_all_sessions,
    group_cleaned_pairs_by_session,
    historical_conversation_id,
    backfill_legacy_path2_identities,
)

# Replace the Ollama-backed embedding function with a deterministic stub
# so tests don't require Ollama to be running.
install_test_stub()


# ---------------------------------------------------------------------------
# Fixture builders — write minimal cleaned-pair files into a temp dir
# ---------------------------------------------------------------------------


_FIXTURE_COUNTER = [0]


def _write_cleaned_pair(
    dir_: str,
    *,
    pair_num: int,
    timestamp: str,
    user_input: str,
    ai_response: str,
    source_chat: str = "~/Documents/conversations/raw/test-chat.md",
    platform: str = "claude",
    thread_id: str = "thread_abcdef12_001",
    prior_pair: str = "",
    next_pair: str = "",
    tags: str = "[]",
) -> str:
    # Per-call unique counter so multiple sessions in the same test
    # directory don't collide on filenames (the on-disk file name is
    # purely a fixture artefact; what matters is the source_chat
    # frontmatter field for grouping).
    _FIXTURE_COUNTER[0] += 1
    name = f"fixture-{_FIXTURE_COUNTER[0]:06d}.md"
    path = os.path.join(dir_, name)
    content = (
        "---\n"
        "nexus:\n"
        "type: cleaned-pair\n"
        f"date created: {timestamp[:10]}\n"
        f"date modified: {timestamp[:10]}\n"
        f"source_chat: {source_chat}\n"
        f"source_pair_num: {pair_num}\n"
        f"source_platform: {platform}\n"
        f"source_timestamp: {timestamp}\n"
        f"thread_id: {thread_id}\n"
        f"prior_pair: {prior_pair}\n"
        f"next_pair: {next_pair}\n"
        "processing_model: claude-haiku-4-5\n"
        "processed_at: 2026-05-02T08:00:00\n"
        f"tags: {tags}\n"
        "---\n"
        "\n## Context\n\n"
        "### Session context\n\n"
        "A discussion about the project.\n\n"
        "### Pair context\n\n"
        f"Pair {pair_num} of the conversation.\n\n"
        "## Exchange\n\n"
        "### User input\n\n"
        f"{user_input}\n\n"
        "### Assistant response\n\n"
        f"{ai_response}\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# Per-session emission
# ---------------------------------------------------------------------------


class TestEmitChunksForSession(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cp_dir   = os.path.join(self.tmp, "cleaned-pairs")
        self.conv_dir = os.path.join(self.tmp, "conversations")
        self.chroma   = os.path.join(self.tmp, "chromadb")
        os.makedirs(self.cp_dir)
        from orchestrator import runtime_paths
        self._data_patch = mock.patch.object(
            runtime_paths, "DATA_DIR_STR", os.path.join(self.tmp, "data"),
        )
        self._data_patch.start()

    def tearDown(self):
        self._data_patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_session(self, source_chat="~/Documents/conversations/raw/test.md",
                       platform="claude", n_pairs=3) -> list[str]:
        paths = []
        for i in range(1, n_pairs + 1):
            ts = f"2025-08-12T10:{i:02d}:00"
            paths.append(_write_cleaned_pair(
                self.cp_dir,
                pair_num=i,
                timestamp=ts,
                user_input=f"Question {i} about quantum mechanics.",
                ai_response=f"Answer {i} explaining the topic.",
                source_chat=source_chat,
                platform=platform,
                thread_id=f"thread_abcdef12_{i:03d}",
                prior_pair=("" if i == 1 else f"prev-{i-1}.md"),
                next_pair=(f"next-{i+1}.md" if i < n_pairs else ""),
            ))
        return paths

    def test_emits_one_chunk_per_pair(self):
        paths = self._make_session()
        result = emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        self.assertEqual(result.pairs_total, 3)
        self.assertEqual(result.chunks_written, 3)
        self.assertEqual(result.chunks_indexed, 3)
        self.assertEqual(len(result.errors), 0)
        chunk_files = [f for f in os.listdir(self.conv_dir) if f.endswith(".md")]
        self.assertEqual(len(chunk_files), 3)

    def test_chunks_use_schema12_yaml(self):
        paths = self._make_session()
        emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        files = sorted(os.listdir(self.conv_dir))
        body = open(os.path.join(self.conv_dir, files[0]),
                    encoding="utf-8").read()
        self.assertTrue(body.startswith("---\n"))
        self.assertIn("type: chat", body)
        # Bespoke per-pair frontmatter fields must NOT appear in the chunk
        # (they live in the cleaned-pair archive, not the chunk).
        self.assertNotIn("source_pair_num:", body)
        self.assertNotIn("processing_model:", body)
        self.assertNotIn("source_chat:", body)
        expected_id = historical_conversation_id(
            "~/Documents/conversations/raw/test.md"
        )
        self.assertIn(
            f'<!-- ora-conversation-id: "{expected_id}" -->',
            body,
        )

    def test_index_failure_chunk_is_recoverable_by_exact_owner_marker(self):
        class FailingCollection:
            def upsert(self, **_kwargs):
                raise RuntimeError("synthetic indexing failure")

        from orchestrator.conversation_closeout import _scan_owned_chunks

        paths = self._make_session(n_pairs=1)
        result = emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            chromadb_collection=FailingCollection(),
        )

        self.assertEqual(result.chunks_written, 1)
        self.assertEqual(result.chunks_indexed, 0)
        expected_id = historical_conversation_id(
            "~/Documents/conversations/raw/test.md"
        )
        recovered = _scan_owned_chunks(Path(self.conv_dir), expected_id)
        self.assertEqual(recovered, [Path(result.output_paths[0])])
        manifest = Path(self.tmp) / "data" / "conversation-manifest.jsonl"
        record = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(
            record["conversation_id"],
            expected_id,
        )
        self.assertEqual(
            record["source_path"],
            "~/Documents/conversations/raw/test.md",
        )
        self.assertEqual(record["raw_path"], "")
        self.assertEqual(record["artifact_kind"], "conversation_chunk")
        self.assertEqual(record["managed_by"], "ora")

    def test_chunks_use_historical_dates_in_filename(self):
        paths = self._make_session()
        emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        files = sorted(os.listdir(self.conv_dir))
        for fname in files:
            self.assertTrue(fname.startswith("2025-08-12"),
                            f"unexpected filename: {fname}")

    def test_chromadb_metadata_carries_historical_fields(self):
        paths = self._make_session()
        emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chroma)
        col = get_or_create_collection(client, "conversations")
        records = col.get(where={"source_platform": "historical-claude"})
        self.assertEqual(len(records["ids"]), 3)
        for meta in records["metadatas"]:
            self.assertEqual(meta["year"], 2025)
            self.assertEqual(meta["month"], 8)
            self.assertEqual(meta["date"], "2025-08-12")
            self.assertEqual(meta["model_id"], "historical-claude")

    def test_active_writer_stores_full_exchange_with_explicit_bounded_embedding(self):
        from orchestrator.embedding import EMBEDDING_DIM

        assistant = "ACTIVE-PATH2-ASSISTANT-SENTINEL " + ("answer " * 2400)
        path = _write_cleaned_pair(
            self.cp_dir,
            pair_num=1,
            timestamp="2025-08-12T10:00:00",
            user_input="ACTIVE-PATH2-USER asks a focused historical question.",
            ai_response=assistant,
        )
        calls = []
        orientations = []

        class CapturingCollection:
            def upsert(self, **kwargs):
                calls.append(kwargs)

        result = emit_chunks_for_session(
            [path],
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            chromadb_collection=CapturingCollection(),
            embedder=lambda texts: (
                orientations.extend(texts)
                or [[0.0] * EMBEDDING_DIM for _ in texts]
            ),
        )

        self.assertEqual(result.chunks_indexed, 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("ACTIVE-PATH2-USER", calls[0]["documents"][0])
        self.assertIn(assistant.rstrip(), calls[0]["documents"][0])
        self.assertIn("embeddings", calls[0])
        self.assertEqual(len(calls[0]["embeddings"][0]), EMBEDDING_DIM)
        self.assertEqual(len(orientations), 1)
        self.assertLessEqual(len(orientations[0]), MAX_EMBED_CHARS)
        self.assertIn("ACTIVE-PATH2-USER", orientations[0])
        self.assertNotIn("ACTIVE-PATH2-ASSISTANT-SENTINEL", orientations[0])

    def test_chain_id_propagates_to_metadata(self):
        paths = self._make_session()
        emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            chain_id="chain-abc1234567",
            chain_label="quantum mechanics",
        )
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chroma)
        col = get_or_create_collection(client, "conversations")
        records = col.get(where={"chain_id": "chain-abc1234567"})
        self.assertEqual(len(records["ids"]), 3)
        for meta in records["metadatas"]:
            self.assertEqual(meta["chain_id"], "chain-abc1234567")
            self.assertEqual(meta["chain_label"], "quantum mechanics")

    def test_chain_label_omitted_when_chain_id_empty(self):
        paths = self._make_session()
        emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            chain_id="",
            chain_label="",
        )
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chroma)
        col = get_or_create_collection(client, "conversations")
        records = col.get()
        for meta in records["metadatas"]:
            # Chain fields should be absent (or empty).
            self.assertEqual(meta.get("chain_id", ""), "")

    def test_skip_if_chunk_exists_re_run(self):
        paths = self._make_session()
        # First run writes everything.
        first = emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        self.assertEqual(first.chunks_written, 3)
        self.assertEqual(first.chunks_skipped, 0)
        # Second run with skip_if_chunk_exists=True (default) skips them.
        second = emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            skip_if_chunk_exists=True,
        )
        self.assertEqual(second.chunks_written, 0)
        self.assertEqual(second.chunks_skipped, 3)

    def test_filename_collision_uses_pair_suffix(self):
        # Two pairs with the SAME timestamp + slug → second one gets
        # `-pair003` style suffix.
        paths = []
        for i, content in enumerate([
            "Same prompt content here exactly.",
            "Same prompt content here exactly.",
        ], start=1):
            paths.append(_write_cleaned_pair(
                self.cp_dir,
                pair_num=i,
                timestamp=f"2025-08-12T10:00:00",   # identical timestamp
                user_input=content,
                ai_response="Response.",
                thread_id=f"thread_abcdef12_{i:03d}",
            ))
        emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        files = sorted(os.listdir(self.conv_dir))
        # Two chunk files, one with the -pair002 suffix.
        self.assertEqual(len(files), 2)
        suffixed = [f for f in files if "-pair" in f]
        self.assertEqual(len(suffixed), 1)

    def test_preexisting_unowned_filename_is_never_claimed(self):
        paths = self._make_session(n_pairs=1)
        expected = (
            Path(self.conv_dir)
            / "2025-08-12_10-01_question-about-quantum-mechanics.md"
        )
        Path(self.conv_dir).mkdir(parents=True, exist_ok=True)
        expected.write_text("user-owned collision\n", encoding="utf-8")
        result = emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        self.assertEqual(expected.read_text(encoding="utf-8"),
                         "user-owned collision\n")
        self.assertEqual(result.chunks_written, 1)
        self.assertIn("-pair001.md", result.output_paths[0])
        self.assertIn(
            historical_conversation_id(
                "~/Documents/conversations/raw/test.md"
            ),
            Path(result.output_paths[0]).read_text(encoding="utf-8"),
        )

    def test_session_id_stable_across_calls(self):
        # Same source_chat → same session_id every time.
        paths = self._make_session(source_chat="~/foo/test.md")
        r1 = emit_chunks_for_session(
            paths, conversations_dir=self.conv_dir, chromadb_path=self.chroma,
        )
        # Re-emit (same source_chat) — session_id matches.
        paths2 = self._make_session(source_chat="~/foo/test.md")
        r2 = emit_chunks_for_session(
            paths2, conversations_dir=self.conv_dir, chromadb_path=self.chroma,
        )
        self.assertEqual(r1.session_id, r2.session_id)

    def test_runtime_migration_rekeys_legacy_records_markers_and_manifest(self):
        source = "~/Documents/conversations/raw/legacy-source.md"
        paths = self._make_session(source_chat=source, n_pairs=1)
        emitted = emit_chunks_for_session(
            paths,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        safe_id = historical_conversation_id(source)
        new_chunk_id = emitted.chunk_ids[0]
        legacy_chunk_id = "session-acde12-pair-001"

        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chroma)
        collection = get_or_create_collection(client, "conversations")
        current = collection.get(
            ids=[new_chunk_id], include=["metadatas", "documents"],
        )
        legacy_meta = dict(current["metadatas"][0])
        legacy_meta["conversation_id"] = source
        legacy_meta["session_id"] = "acde12"
        legacy_meta["raw_path"] = source
        legacy_meta.pop("source_path", None)
        collection.delete(ids=[new_chunk_id])
        collection.upsert(
            ids=[legacy_chunk_id],
            documents=[current["documents"][0]],
            metadatas=[legacy_meta],
        )
        from orchestrator import embedding
        retired = client.get_or_create_collection(
            name="conversations_v2",
            metadata={
                "hnsw:space": "cosine",
                "ora:logical_collection": "conversations",
            },
            embedding_function=embedding.get_embedding_function(),
        )
        retired.upsert(
            ids=[legacy_chunk_id],
            documents=[current["documents"][0]],
            metadatas=[legacy_meta],
        )

        chunk_path = Path(emitted.output_paths[0])
        chunk_body = chunk_path.read_text(encoding="utf-8")
        chunk_path.write_text(
            chunk_body.replace(
                f'<!-- ora-conversation-id: "{safe_id}" -->',
                f'<!-- ora-conversation-id: "{source}" -->',
            ).replace(
                f'<!-- ora-chunk-id: "{new_chunk_id}" -->',
                f'<!-- ora-chunk-id: "{legacy_chunk_id}" -->',
            ),
            encoding="utf-8",
        )
        manifest = Path(self.tmp) / "data" / "conversation-manifest.jsonl"
        record = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
        record["conversation_id"] = source
        record["chunk_id"] = legacy_chunk_id
        record["raw_path"] = source
        record.pop("source_path", None)
        manifest.write_text(json.dumps(record) + "\n", encoding="utf-8")

        backfilled = backfill_legacy_path2_identities(
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            manifest_path=manifest,
        )
        self.assertEqual(backfilled["sources_discovered"], 1)
        migrated = backfilled["migrations"][safe_id]
        self.assertEqual(migrated["errors"], [])
        self.assertGreaterEqual(migrated["chromadb_records"], 1)
        rows = collection.get(where={"conversation_id": safe_id})
        self.assertEqual(rows["ids"], [new_chunk_id])
        self.assertEqual(rows["metadatas"][0]["raw_path"], "")
        self.assertEqual(rows["metadatas"][0]["source_path"], source)
        self.assertEqual(collection.get(ids=[legacy_chunk_id])["ids"], [])
        retired_rows = retired.get(where={"conversation_id": safe_id})
        self.assertEqual(retired_rows["ids"], [new_chunk_id])
        self.assertEqual(retired.get(ids=[legacy_chunk_id])["ids"], [])
        migrated_body = chunk_path.read_text(encoding="utf-8")
        self.assertIn(f'<!-- ora-conversation-id: "{safe_id}" -->', migrated_body)
        self.assertIn(f'<!-- ora-chunk-id: "{new_chunk_id}" -->', migrated_body)
        migrated_manifest = json.loads(
            manifest.read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(migrated_manifest["conversation_id"], safe_id)
        self.assertEqual(migrated_manifest["chunk_id"], new_chunk_id)
        self.assertEqual(migrated_manifest["raw_path"], "")
        self.assertEqual(migrated_manifest["source_path"], source)

    def test_delete_safe_id_migrates_legacy_marker_before_purge(self):
        from orchestrator import conversation_closeout

        source_path = Path(self.tmp) / "imports" / "source-chat.md"
        source_path.parent.mkdir()
        source_path.write_text("user-owned imported source\n", encoding="utf-8")
        source = str(source_path)
        safe_id = historical_conversation_id(source)
        chunk = Path(self.conv_dir) / "legacy-chunk.md"
        chunk.parent.mkdir(parents=True, exist_ok=True)
        chunk.write_text(
            "---\ntype: chat\ntags:\n---\n"
            f'<!-- ora-conversation-id: "{source}" -->\n'
            '<!-- ora-chunk-id: "session-old-pair-001" -->\n\nbody\n',
            encoding="utf-8",
        )
        manifest = Path(self.tmp) / "data" / "conversation-manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({
            "conversation_id": source,
            "chunk_id": "session-old-pair-001",
            "chunk_path": str(chunk),
            "chunk_root": str(chunk.parent),
            "artifact_kind": "conversation_chunk",
            "managed_by": "ora",
            "raw_path": "",
        }) + "\n", encoding="utf-8")
        vault_sessions = Path(self.tmp) / "vault" / "Sessions"
        vault_sessions.mkdir(parents=True)

        result = conversation_closeout._purge_stealth(
            safe_id,
            sessions_root=Path(self.tmp) / "sessions",
            conversations_dir=Path(self.conv_dir),
            conversations_raw=Path(self.tmp) / "conversations" / "raw",
            chromadb_path=Path(self.chroma),
            vault_sessions=vault_sessions,
        )
        self.assertFalse(chunk.exists())
        self.assertTrue(source_path.exists())
        self.assertEqual(manifest.read_text(encoding="utf-8"), "")
        migration = result["deleted"]["historical_identity_migration"]
        self.assertEqual(migration["matched_source"], source)
        self.assertEqual(result["deleted"]["recovered_chunk_files"], [str(chunk)])

    def test_empty_user_input_pair_emits_chunk(self):
        # Phase 1 empty-side success contract: empty user input still
        # emits a valid chunk (with empty User section).
        path = _write_cleaned_pair(
            self.cp_dir,
            pair_num=1,
            timestamp="2025-08-12T10:00:00",
            user_input="",   # empty
            ai_response="The AI did all the talking.",
        )
        result = emit_chunks_for_session(
            [path],
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        self.assertEqual(result.chunks_written, 1)
        self.assertEqual(len(result.errors), 0)

    def test_private_cleaned_pair_remains_private_through_path2(self):
        path = _write_cleaned_pair(
            self.cp_dir,
            pair_num=1,
            timestamp="2025-08-12T10:00:00",
            user_input="Private prompt",
            ai_response="Private answer",
            tags="[private]",
        )
        result = emit_chunks_for_session(
            [path], conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
        )
        self.assertEqual(result.errors, [])
        body = Path(result.output_paths[0]).read_text(encoding="utf-8")
        self.assertIn("tags:\n  - private", body)
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        collection = get_or_create_collection(
            chromadb.PersistentClient(path=self.chroma), "conversations",
        )
        rows = collection.get(where={
            "conversation_id": historical_conversation_id(
                "~/Documents/conversations/raw/test-chat.md"
            ),
        })
        self.assertTrue(rows["metadatas"][0]["tag_private"])
        self.assertEqual(rows["metadatas"][0]["tag"], "private")


# ---------------------------------------------------------------------------
# Multi-session orchestration
# ---------------------------------------------------------------------------


class TestEmitChunksForAllSessions(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cp_dir   = os.path.join(self.tmp, "cleaned-pairs")
        self.conv_dir = os.path.join(self.tmp, "conversations")
        self.chroma   = os.path.join(self.tmp, "chromadb")
        os.makedirs(self.cp_dir)
        from orchestrator import runtime_paths
        self._data_patch = mock.patch.object(
            runtime_paths, "DATA_DIR_STR", os.path.join(self.tmp, "data"),
        )
        self._data_patch.start()

    def tearDown(self):
        self._data_patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_pair_in_session(self, source: str, pair_num: int,
                                ts: str = "2025-08-12T10:00:00") -> str:
        return _write_cleaned_pair(
            self.cp_dir,
            pair_num=pair_num,
            timestamp=ts,
            user_input=f"Q from {source} pair {pair_num}",
            ai_response=f"A for {source} pair {pair_num}",
            source_chat=source,
            thread_id=f"thread_xx{pair_num:06d}_001",
        )

    def test_groups_pairs_by_source_chat(self):
        # Three sessions, each with 2 pairs.
        paths_a = [self._make_pair_in_session("~/raw/A.md", i) for i in (1, 2)]
        paths_b = [self._make_pair_in_session("~/raw/B.md", i) for i in (1, 2)]
        paths_c = [self._make_pair_in_session("~/raw/C.md", i) for i in (1, 2)]
        all_paths = paths_a + paths_b + paths_c
        groups = group_cleaned_pairs_by_session(all_paths)
        self.assertEqual(len(groups), 3)
        self.assertEqual(len(groups["~/raw/A.md"]), 2)
        self.assertEqual(len(groups["~/raw/B.md"]), 2)
        self.assertEqual(len(groups["~/raw/C.md"]), 2)

    def test_emit_all_sessions_assigns_chains_from_lookup(self):
        from orchestrator.historical.chain_detector import derive_session_id
        a = "~/raw/A.md"
        b = "~/raw/B.md"
        sid_a = derive_session_id(a)
        sid_b = derive_session_id(b)
        paths_a = [self._make_pair_in_session(a, 1, ts="2025-08-12T10:00:00"),
                   self._make_pair_in_session(a, 2, ts="2025-08-12T10:01:00")]
        paths_b = [self._make_pair_in_session(b, 1, ts="2025-08-12T11:00:00")]
        groups = {a: paths_a, b: paths_b}
        results = emit_chunks_for_all_sessions(
            groups,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            session_to_chain={sid_a: "chain-AAAA", sid_b: "chain-BBBB"},
            chain_labels={"chain-AAAA": "label-a", "chain-BBBB": "label-b"},
            max_workers=1,   # serial for determinism in tests
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[a].chain_id, "chain-AAAA")
        self.assertEqual(results[b].chain_id, "chain-BBBB")
        # Verify metadata in ChromaDB.
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=self.chroma)
        col = get_or_create_collection(client, "conversations")
        a_records = col.get(where={"chain_id": "chain-AAAA"})
        self.assertEqual(len(a_records["ids"]), 2)
        for m in a_records["metadatas"]:
            self.assertEqual(m["chain_label"], "label-a")

    def test_collection_open_failure_raises_instead_of_succeeding_empty(self):
        source = "~/raw/A.md"
        paths = [self._make_pair_in_session(source, 1)]
        with mock.patch("chromadb.PersistentClient",
                        side_effect=RuntimeError("database malformed")):
            with self.assertRaisesRegex(RuntimeError, "open ChromaDB"):
                emit_chunks_for_all_sessions(
                    {source: paths},
                    conversations_dir=self.conv_dir,
                    chromadb_path=self.chroma,
                    max_workers=1,
                )


if __name__ == "__main__":
    unittest.main()
