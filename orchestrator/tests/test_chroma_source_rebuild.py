from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.tools import chroma_source_rebuild as rebuild


def _cleaned_pair(
    *,
    source: str = "~/Documents/raw/example.md",
    pair: int = 1,
    user: str = "Question",
    assistant: str = "Answer",
    private: bool = False,
) -> str:
    return f"""---
nexus:
type: cleaned-pair
date created: 2025-01-02
date modified: 2026-07-12
source_chat: {source}
source_pair_num: {pair}
source_platform: chatgpt
source_timestamp: 2025-01-02T03:04:05
thread_id: thread_example_001
prior_pair:
next_pair:
processing_model: test
processed_at: 2026-07-12T00:00:00
tags: [{"private" if private else ""}]
---

## Context

### Session context

Conversation 'Example' on chatgpt, dated 2025-01-02, comprising 1 prompt+response pair(s).

### Pair context

Pair {pair} of 1. Topic keywords for this pair: question.

## Exchange

### User input

{user}

### Assistant response

{assistant}
"""


def _chunk(
    *,
    context: str,
    user: str = "Question",
    assistant: str = "Answer",
    owner: str = "",
    chunk_id: str = "",
    private: bool = False,
) -> str:
    markers = ""
    if owner:
        markers = (
            f'<!-- ora-conversation-id: {json.dumps(owner)} -->\n'
            f'<!-- ora-chunk-id: {json.dumps(chunk_id)} -->\n\n'
        )
    tags = "\n  - private" if private else ""
    return f"""---
nexus:
type: chat
tags:{tags}
date created: 2026-07-12
date modified: 2026-07-12
---

{markers}## Context

{context}

## Exchange

**User:**

{user}

**Assistant:**

{assistant}
"""


class _FakeCollection:
    def __init__(self, *, fail_once: bool = False):
        self.rows = {}
        self.fail_once = fail_once

    def upsert(self, *, ids, documents, metadatas, embeddings=None):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("synthetic interruption")
        for row_id, document, metadata in zip(ids, documents, metadatas):
            self.rows[row_id] = (document, metadata)

    def count(self):
        return len(self.rows)

    def get(self, *, ids, include):
        found = [row_id for row_id in ids if row_id in self.rows]
        result = {"ids": found}
        if "documents" in include:
            result["documents"] = [self.rows[row_id][0] for row_id in found]
        if "metadatas" in include:
            result["metadatas"] = [self.rows[row_id][1] for row_id in found]
        return result


class _EmbeddingFakeCollection:
    def __init__(self):
        self.rows = {}
        self.embeddings = {}
        self.upsert_sizes = []

    def upsert(self, *, ids, embeddings, documents, metadatas):
        self.upsert_sizes.append(len(ids))
        for row_id, vector, document, metadata in zip(
            ids, embeddings, documents, metadatas,
        ):
            self.rows[row_id] = (document, metadata)
            self.embeddings[row_id] = vector

    def count(self):
        return len(self.rows)

    def get(self, *, ids, include):
        found = [row_id for row_id in ids if row_id in self.rows]
        result = {"ids": found}
        if "documents" in include:
            result["documents"] = [self.rows[row_id][0] for row_id in found]
        if "metadatas" in include:
            result["metadatas"] = [self.rows[row_id][1] for row_id in found]
        return result


class _FinalReadCorruptingCollection(_FakeCollection):
    def get(self, *, ids, include):
        result = super().get(ids=ids, include=include)
        if result["ids"] and "documents" in result:
            result["documents"][0] = "corrupted stored document"
        return result


class _FinalMetadataCorruptingCollection(_EmbeddingFakeCollection):
    def get(self, *, ids, include):
        result = super().get(ids=ids, include=include)
        if result["ids"] and "metadatas" in result:
            result["metadatas"][0] = {"corrupted": True}
        return result


class _KnowledgeCaptureCollection:
    def __init__(self):
        self.ids = []
        self.documents = []
        self.metadatas = []

    def get(self, *, ids):
        return {"ids": []}

    def add(self, *, ids, documents, metadatas, **_kwargs):
        self.ids.extend(ids)
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)


class _MSIComposer:
    @staticmethod
    def _parse_frontmatter(content):
        return {"headline": content.splitlines()[0]}, content

    @staticmethod
    def _compose_chroma_metadata(filepath, meta):
        return {
            "path": str(Path(filepath).absolute()),
            "slug": Path(filepath).stem,
            "headline": meta["headline"],
        }

    @staticmethod
    def _build_embed_text(meta, body):
        return f"{meta['headline']}\n\n{body}"

    @staticmethod
    def _filename_slug(filepath):
        return Path(filepath).stem


class ConversationSourceRebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.conversations = self.root / "conversations"
        self.data = self.root / "data"
        self.sessions = self.root / "sessions"
        for path in (self.archive, self.conversations, self.data, self.sessions):
            path.mkdir()
        self.manifest = self.data / "conversation-manifest.jsonl"
        self.chain = self.data / "chain-index.json"

    def tearDown(self):
        self.temp.cleanup()

    def _plan(self):
        return rebuild.build_conversation_replay_plan(
            historical_archive=self.archive,
            conversations_root=self.conversations,
            manifest_path=self.manifest,
            chain_index_path=self.chain,
            sessions_root=self.sessions,
        )

    def test_historical_archive_is_authoritative_and_derived_chunk_is_excluded(self):
        cleaned = _cleaned_pair()
        (self.archive / "pair.md").write_text(cleaned, encoding="utf-8")
        context = (
            "Conversation 'Example' on chatgpt, dated 2025-01-02, "
            "comprising 1 prompt+response pair(s).\n\n"
            "Pair 1 of 1. Topic keywords for this pair: question."
        )
        (self.conversations / "2025-01-02_03-04_question.md").write_text(
            _chunk(context=context), encoding="utf-8"
        )

        plan = self._plan()
        plan.require_valid()
        self.assertEqual(plan.historical_files, 1)
        self.assertEqual(plan.historical_sessions, 1)
        self.assertEqual(plan.derived_historical_files, 1)
        self.assertEqual(plan.live_files, 0)
        self.assertEqual(len(plan.records), 1)
        row = plan.records[0]
        self.assertRegex(row.row_id, r"^session-[0-9a-f]{12}-pair-001$")
        self.assertEqual(row.metadata["turn_index"], 1)
        self.assertTrue(row.metadata["is_last_turn"])
        self.assertEqual(row.metadata["source_path"], "~/Documents/raw/example.md")
        durable_pair = str((self.archive / "pair.md").absolute())
        self.assertEqual(row.metadata["chunk_path"], durable_pair)
        self.assertEqual(row.metadata["obsidian_path"], durable_pair)
        self.assertEqual(row.metadata["source"], "pair.md")
        self.assertIn(context, row.document)
        self.assertIn("**User:**\n\nQuestion", row.document)
        self.assertIn("**Assistant:**\n\nAnswer", row.document)
        self.assertEqual(row.embedding_text, f"{context}\n\nQuestion")

    def test_chain_and_private_metadata_are_preserved(self):
        source = "~/Documents/raw/private.md"
        (self.archive / "pair.md").write_text(
            _cleaned_pair(source=source, private=True), encoding="utf-8"
        )
        session_id = rebuild.derive_session_id(source)
        self.chain.write_text(json.dumps({
            "session_to_chain": {session_id: "chain-1"},
            "chains": [{"chain_id": "chain-1", "chain_label": "Example chain"}],
        }), encoding="utf-8")

        plan = self._plan()
        plan.require_valid()
        metadata = plan.records[0].metadata
        self.assertEqual(metadata["tag"], "private")
        self.assertTrue(metadata["tag_private"])
        self.assertEqual(metadata["chain_id"], "chain-1")
        self.assertEqual(metadata["chain_label"], "Example chain")

    def test_filtered_pair_gaps_preserve_turn_numbers_and_finalize_at_maximum(self):
        source = "~/Documents/raw/filtered.md"
        (self.archive / "pair-2.md").write_text(
            _cleaned_pair(source=source, pair=2, user="First survivor"),
            encoding="utf-8",
        )
        (self.archive / "pair-5.md").write_text(
            _cleaned_pair(source=source, pair=5, user="Last survivor"),
            encoding="utf-8",
        )

        plan = self._plan()
        plan.require_valid()
        self.assertEqual(
            [row.metadata["turn_index"] for row in plan.records], [2, 5]
        )
        self.assertEqual(
            [row.metadata["total_turns"] for row in plan.records], [5, 5]
        )
        self.assertEqual(
            [row.metadata["is_last_turn"] for row in plan.records], [False, True]
        )
        self.assertTrue(all(
            row.metadata["conversation_title"].startswith("First survivor")
            for row in plan.records
        ))

    def test_mixed_pair_privacy_promotes_entire_session_to_private(self):
        source = "~/Documents/raw/mixed-private.md"
        (self.archive / "pair-1.md").write_text(
            _cleaned_pair(source=source, pair=1, private=False),
            encoding="utf-8",
        )
        (self.archive / "pair-3.md").write_text(
            _cleaned_pair(source=source, pair=3, private=True),
            encoding="utf-8",
        )

        plan = self._plan()
        plan.require_valid()
        self.assertEqual(len(plan.records), 2)
        self.assertTrue(all(row.metadata["tag"] == "private" for row in plan.records))
        self.assertTrue(all(row.metadata["tag_private"] for row in plan.records))

    def test_live_marker_uses_exact_ownership_and_complete_retrieval_document(self):
        context = (
            "Local AI session on 2026-07-12, panel 'conv-1', model model-x. "
            "Turn 2 of an ongoing conversation."
        )
        path = self.conversations / "session-abc-pair-002_2026-07-12_12-30_question.md"
        path.write_text(_chunk(
            context=context,
            owner="conv-1",
            chunk_id="session-abc-pair-002",
        ), encoding="utf-8")
        self.manifest.write_text(json.dumps({
            "conversation_id": "conv-1",
            "chunk_id": "session-abc-pair-002",
            "chunk_path": str(path),
            "raw_path": "",
            "tag": "",
        }) + "\n", encoding="utf-8")

        plan = self._plan()
        plan.require_valid()
        self.assertEqual(plan.live_files, 1)
        row = plan.records[0]
        self.assertEqual(row.row_id, "session-abc-pair-002")
        self.assertEqual(row.metadata["conversation_id"], "conv-1")
        self.assertEqual(row.metadata["turn_index"], 2)
        self.assertIn(context, row.document)
        self.assertIn("**User:**\n\nQuestion", row.document)
        self.assertIn("**Assistant:**\n\nAnswer", row.document)
        self.assertEqual(row.embedding_text, f"{context}\n\nQuestion")

    def test_latest_matching_manifest_owner_replays_unmarked_legacy_chunk(self):
        context = (
            "Local AI session on 2026-07-12, panel 'conv-1', model model-x. "
            "Turn 1 of an ongoing conversation."
        )
        path = self.conversations / "2026-07-12_12-30_question.md"
        path.write_text(_chunk(context=context), encoding="utf-8")
        old = {
            "conversation_id": "other-conv",
            "chunk_id": "session-old-pair-001",
            "chunk_path": str(path),
            "raw_path": "",
            "tag": "",
        }
        current = {
            "conversation_id": "conv-1",
            "chunk_id": "session-current-pair-001",
            "chunk_path": str(path),
            "raw_path": "",
            "tag": "",
        }
        self.manifest.write_text(
            json.dumps(old) + "\n" + json.dumps(current) + "\n",
            encoding="utf-8",
        )

        plan = self._plan()
        plan.require_valid()
        self.assertEqual(
            {row.row_id for row in plan.records},
            {"session-old-pair-001", "session-current-pair-001"},
        )
        self.assertEqual(plan.shadowed_manifest_entries, 0)

    def test_marker_manifest_disagreement_fails_closed(self):
        context = (
            "Local AI session on 2026-07-12, panel 'conv-1', model model-x. "
            "Turn 1 of an ongoing conversation."
        )
        path = self.conversations / "session-abc-pair-001_2026-07-12_12-30_q.md"
        path.write_text(_chunk(
            context=context, owner="conv-1", chunk_id="session-abc-pair-001"
        ), encoding="utf-8")
        self.manifest.write_text(json.dumps({
            "conversation_id": "conv-1",
            "chunk_id": "session-different-pair-001",
            "chunk_path": str(path),
            "raw_path": "",
            "tag": "",
        }) + "\n", encoding="utf-8")

        plan = self._plan()
        with self.assertRaises(rebuild.RebuildError):
            plan.require_valid()

    def test_latest_manifest_record_wins_for_reused_chunk_id(self):
        paths = [
            self.conversations / "2026-07-12_12-30_first.md",
            self.conversations / "2026-07-12_12-31_second.md",
        ]
        for index, path in enumerate(paths, 1):
            context = (
                f"Local AI session on 2026-07-12, panel 'conv-{index}', "
                f"model model-x. Turn 1 of an ongoing conversation."
            )
            path.write_text(_chunk(context=context, user=f"Question {index}"), encoding="utf-8")
        self.manifest.write_text("".join(
            json.dumps({
                "conversation_id": f"conv-{index}",
                "chunk_id": "session-c63500-pair-001",
                "chunk_path": str(path),
                "raw_path": "",
                "tag": "",
            }) + "\n"
            for index, path in enumerate(paths, 1)
        ), encoding="utf-8")

        plan = self._plan()
        plan.require_valid()
        self.assertEqual(len(plan.records), 1)
        self.assertEqual(plan.records[0].row_id, "session-c63500-pair-001")
        self.assertEqual(plan.records[0].metadata["conversation_id"], "conv-2")
        self.assertEqual(plan.shadowed_manifest_entries, 1)

    def test_stealth_source_is_never_planned(self):
        context = (
            "Local AI session on 2026-07-12, panel 'conv-1', model model-x. "
            "Turn 1 of an ongoing conversation."
        )
        path = self.conversations / "2026-07-12_12-30_q.md"
        path.write_text(_chunk(context=context), encoding="utf-8")
        self.manifest.write_text(json.dumps({
            "conversation_id": "conv-1",
            "chunk_id": "session-x-pair-001",
            "chunk_path": str(path),
            "raw_path": "",
            "tag": "stealth",
        }) + "\n", encoding="utf-8")

        plan = self._plan()
        self.assertFalse(any(row.metadata.get("tag") == "stealth" for row in plan.records))
        with self.assertRaises(rebuild.RebuildError):
            plan.require_valid()

    def test_non_chat_recovery_and_continuity_artifacts_are_ignored(self):
        (self.conversations / "recovered.md").write_text(
            "---\nstatus: errored\nrecovery: orphan_pending\n---\n# Interrupted\n",
            encoding="utf-8",
        )
        (self.conversations / "continuity.md").write_text(
            "# Session continuity\n\nNot a conversation chunk.\n",
            encoding="utf-8",
        )
        plan = self._plan()
        plan.require_valid()
        self.assertEqual(len(plan.records), 0)
        self.assertEqual(len(plan.ignored_files), 2)

    def test_unmanifested_canonical_chat_is_ignored(self):
        context = (
            "Local AI session on 2026-07-12, panel 'legacy', model model-x. "
            "Turn 1 of an ongoing conversation."
        )
        (self.conversations / "2026-07-12_12-30_legacy.md").write_text(
            _chunk(context=context), encoding="utf-8"
        )
        plan = self._plan()
        plan.require_valid()
        self.assertEqual(plan.live_files, 0)
        self.assertEqual(len(plan.ignored_files), 1)

    def test_symlink_source_is_rejected(self):
        outside = self.root / "outside.md"
        outside.write_text(_cleaned_pair(), encoding="utf-8")
        (self.archive / "pair.md").symlink_to(outside)
        plan = self._plan()
        with self.assertRaises(rebuild.RebuildError):
            plan.require_valid()

    def test_execute_is_idempotent_and_resume_uses_checkpoint(self):
        record = rebuild.ReplayRecord(
            row_id="row-1",
            document="document",
            metadata={"type": "chat", "tag": "", "conversation_id": "conv"},
            source_path="source.md",
            source_kind="test",
            embedding_text="orientation",
        )
        plan = rebuild.ConversationReplayPlan(records=[record])
        target = self.root / "fresh-chroma"
        collection = _FakeCollection()
        profile = {
            "provider": "test",
            "model": "test-model",
            "dimension": 3,
            "physical_collection": "conversations_test",
        }
        with mock.patch.object(rebuild, "_profile", return_value=profile):
            first = rebuild.execute_conversation_replay(
                plan,
                target_chromadb_path=target,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=lambda texts: [[0.0, 0.0, 0.0] for _ in texts],
            )
            second = rebuild.execute_conversation_replay(
                plan,
                target_chromadb_path=target,
                resume=True,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=lambda texts: [[0.0, 0.0, 0.0] for _ in texts],
            )
        self.assertEqual(first["target_count"], 1)
        self.assertEqual(second["target_count"], 1)
        self.assertEqual(len(collection.rows), 1)

    def test_resume_rejects_corrupted_checkpoint_prefix_payload(self):
        record = rebuild.ReplayRecord(
            row_id="row-1",
            document="document",
            metadata={"type": "chat", "tag": "", "conversation_id": "conv"},
            source_path="source.md",
            source_kind="test",
            embedding_text="orientation",
        )
        plan = rebuild.ConversationReplayPlan(records=[record])
        target = self.root / "fresh-chroma"
        collection = _FakeCollection()
        profile = {
            "provider": "test",
            "model": "test-model",
            "dimension": 3,
            "physical_collection": "conversations_test",
        }
        with mock.patch.object(rebuild, "_profile", return_value=profile):
            rebuild.execute_conversation_replay(
                plan,
                target_chromadb_path=target,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=lambda texts: [[0.0, 0.0, 0.0] for _ in texts],
            )
            collection.rows[record.row_id] = (
                "corrupted document",
                record.metadata,
            )
            with self.assertRaisesRegex(
                rebuild.RebuildError,
                "checkpoint-resumed conversation prefix payload differs",
            ):
                rebuild.execute_conversation_replay(
                    plan,
                    target_chromadb_path=target,
                    resume=True,
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=lambda texts: [[0.0, 0.0, 0.0] for _ in texts],
                )

    def test_final_conversation_validation_rejects_payload_corruption(self):
        record = rebuild.ReplayRecord(
            row_id="row-1",
            document="document",
            metadata={"type": "chat", "tag": "", "conversation_id": "conv"},
            source_path="source.md",
            source_kind="test",
            embedding_text="orientation",
        )
        plan = rebuild.ConversationReplayPlan(records=[record])
        collection = _FinalReadCorruptingCollection()
        profile = {
            "provider": "test",
            "model": "test-model",
            "dimension": 3,
            "physical_collection": "conversations_test",
        }
        with mock.patch.object(rebuild, "_profile", return_value=profile):
            with self.assertRaisesRegex(
                rebuild.RebuildError,
                "final conversation validation payload differs",
            ):
                rebuild.execute_conversation_replay(
                    plan,
                    target_chromadb_path=self.root / "fresh-chroma",
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=lambda texts: [[0.0, 0.0, 0.0] for _ in texts],
                )

    def test_dry_run_never_opens_chroma_or_embedder(self):
        with mock.patch.object(
            rebuild, "execute_conversation_replay"
        ) as execute:
            result = rebuild.main([
                "conversations",
                "--historical-archive", str(self.archive),
                "--conversations-root", str(self.conversations),
                "--manifest", str(self.manifest),
                "--chain-index", str(self.chain),
                "--sessions-root", str(self.sessions),
                "--target-chromadb-path", str(self.root / "unused"),
                "--dry-run",
            ])
        self.assertEqual(result, 0)
        execute.assert_not_called()


class DerivedCorpusSourceRebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engrams = self.root / "Engrams"
        self.resources = self.root / "Resources"
        self.mental = self.root / "mental-models"
        self.msi_mirror = self.root / "MSI News"
        for path in (
            self.engrams, self.resources, self.mental, self.msi_mirror,
        ):
            path.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _note(*, type_="engram", body="A durable claim with enough detail to index."):
        return (
            "---\n"
            "nexus:\n"
            f"type: {type_}\n"
            "tags:\n"
            "date created: 2026-07-12\n"
            "date modified: 2026-07-12\n"
            "---\n\n"
            f"# Example\n\n{body}\n"
        )

    def _knowledge_plan(self):
        return rebuild.build_knowledge_replay_plan(
            engrams_root=self.engrams,
            resources_root=self.resources,
            mental_models_root=self.mental,
            msi_news_root=self.msi_mirror,
        )

    def _long_knowledge_plan(self, name="semantic.md"):
        body = "\n\n".join(
            f"## Section {index}\n\n" + (f"semantic-{index} " * 650)
            for index in range(1, 5)
        )
        path = self.resources / name
        path.write_text(
            self._note(type_="resource", body=body), encoding="utf-8",
        )
        return path, self._knowledge_plan()

    @staticmethod
    def _profile(*, model="qwen/qwen3-embedding-8b"):
        return {
            "provider": "openrouter",
            "model": model,
            "dimension": 4096,
            "physical_collection": "knowledge_qwen",
        }

    @staticmethod
    def _semantic_embedder(thesis, calls):
        def embed(texts):
            calls.append(list(texts))
            vectors = []
            for text in texts:
                if text == thesis or "Section 1" in text or "Section 4" in text:
                    prefix = [1.0, 0.0]
                elif "Section 2" in text:
                    prefix = [0.0, 1.0]
                elif "Section 3" in text:
                    prefix = [-1.0, 0.0]
                else:
                    prefix = [0.5, 0.5]
                vectors.append(prefix + ([0.0] * 4094))
            return vectors
        return embed

    def test_knowledge_plan_preserves_hcp_ids_and_msi_overrides_filter(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        long_body = "\n\n".join(
            f"## Section {index}\n\n" + (f"paragraph-{index} " * 180)
            for index in range(1, 14)
        )
        resource_path = self.resources / "long-resource.md"
        resource_path.write_text(
            self._note(type_="resource", body=long_body), encoding="utf-8",
        )
        (self.mental / "lens.md").write_text(
            self._note(type_="engram", body="A mental model for testing."),
            encoding="utf-8",
        )
        (self.msi_mirror / "article.md").write_text(
            "# Headline\n\nArticle prose retained for retrieval and testing.\n\n"
            "## Sources\n\nSECRET CITATION APPARATUS THAT MUST BE REMOVED.\n",
            encoding="utf-8",
        )

        with mock.patch(
            "orchestrator.embedding.get_embedding_function",
            side_effect=AssertionError("planning opened embedder"),
        ):
            plan = self._knowledge_plan()
        plan.require_valid()
        records = list(rebuild._iter_source_plan_records(plan))
        self.assertFalse(any(
            record.source_path == str(resource_path.absolute())
            for record in records
        ))
        msi_record = next(
            record for record in records
            if record.source_kind == "knowledge_msi_news"
        )
        self.assertNotIn("SECRET CITATION", msi_record.document)
        self.assertEqual(msi_record.metadata["type"], "resource")
        self.assertTrue(msi_record.metadata["tag_msi-news"])
        self.assertEqual(plan.hcp_sources, 1)
        self.assertGreaterEqual(plan.hcp_records, 2)
        self.assertEqual(
            plan.semantic_payload_status,
            "pending_exact_hcp_materialization",
        )
        self.assertEqual(
            plan.record_count_status,
            "provisional_pending_exact_hcp_materialization",
        )
        self.assertEqual(plan.payload_fingerprint, "")

    def test_long_knowledge_records_match_canonical_hcp_storage_shape(self):
        from orchestrator.tools import hcp, knowledge_index

        long_body = "\n\n".join(
            f"## Part {index}\n\n" + (f"content-{index} " * 220)
            for index in range(1, 12)
        )
        path = self.resources / "parity.md"
        path.write_text(
            self._note(type_="resource", body=long_body), encoding="utf-8",
        )
        source = rebuild.SourceSpec(
            path=path.absolute(),
            root=self.resources.absolute(),
            source_kind="knowledge_resource",
            identity=rebuild._source_identity(path),
        )
        prepared = rebuild._prepare_knowledge_source(source)
        scores = [
            (1.0, 0.80, 0.55)[index % 3]
            for index in range(len(prepared.raw_chunks))
        ]
        rebuilt = rebuild._knowledge_source_records(
            source, similarity_scores=scores, prepared=prepared,
        )
        capture = _KnowledgeCaptureCollection()
        stats = {"indexed": 0, "skipped": 0, "errors": 0}

        def exact_scorer(_thesis):
            score_iter = iter(scores)
            return lambda _text: next(score_iter)

        with mock.patch.object(
            knowledge_index, "_nomic_embed", return_value=None,
        ), mock.patch.object(
            hcp, "make_similarity_scorer", side_effect=exact_scorer,
        ):
            knowledge_index.index_file(capture, str(path), stats, verbose=False)

        self.assertEqual(
            [record.row_id for record in rebuilt.records], capture.ids,
        )
        self.assertEqual(
            [record.document for record in rebuilt.records], capture.documents,
        )
        self.assertEqual(
            [record.metadata for record in rebuilt.records], capture.metadatas,
        )
        self.assertEqual(stats["indexed"], 1)

    def test_exact_hcp_materialization_batches_inputs_and_reuses_cached_scores(self):
        path, plan = self._long_knowledge_plan()
        summary = plan.summary()
        self.assertEqual(
            summary["semantic_payload_status"],
            "pending_exact_hcp_materialization",
        )
        self.assertEqual(
            summary["record_count_status"],
            "provisional_pending_exact_hcp_materialization",
        )
        self.assertEqual(summary["payload_fingerprint"], "")

        source = next(item for item in plan.sources if item.path == path.absolute())
        prepared = rebuild._prepare_knowledge_source(source)
        thesis = prepared.structural_index.document_thesis
        expected_inputs = [thesis] + [
            chunk.content[:4000] for chunk in prepared.raw_chunks
        ]
        target = self.root / "inactive-chroma"
        calls = []
        profile = self._profile()
        exact = rebuild._materialize_exact_source_plan(
            plan,
            target=target,
            profile=profile,
            embedder=self._semantic_embedder(thesis, calls),
            batch_size=2,
        )
        self.assertEqual(
            [text for batch in calls for text in batch], expected_inputs,
        )
        self.assertTrue(all(len(batch) <= 2 for batch in calls))
        self.assertEqual(plan.semantic_payload_status, "exact_materialized")
        self.assertEqual(plan.record_count_status, "exact")
        self.assertEqual(plan.payload_fingerprint, exact.payload_fingerprint)
        self.assertTrue(exact.payload_fingerprint)

        records = list(rebuild._iter_materialized_source_records(
            plan, target=target, profile=profile, materialization=exact,
        ))
        long_records = [
            record for record in records if record.source_path == str(path.absolute())
        ]
        self.assertEqual(len(long_records), len(prepared.raw_chunks))
        self.assertIn("[ROLE]", long_records[0].document)
        self.assertNotIn("[SECTION]", long_records[2].document)

        second = rebuild._materialize_exact_source_plan(
            plan,
            target=target,
            profile=profile,
            embedder=lambda _texts: (_ for _ in ()).throw(
                AssertionError("cached materialization re-embedded HCP")
            ),
            batch_size=2,
        )
        self.assertEqual(second, exact)

    def test_exact_hcp_cache_rejects_profile_and_source_changes_without_embedding(self):
        path, plan = self._long_knowledge_plan()
        source = next(item for item in plan.sources if item.path == path.absolute())
        thesis = rebuild._prepare_knowledge_source(source).structural_index.document_thesis
        target = self.root / "inactive-chroma"
        profile = self._profile()
        rebuild._materialize_exact_source_plan(
            plan,
            target=target,
            profile=profile,
            embedder=self._semantic_embedder(thesis, []),
            batch_size=8,
        )
        calls = []
        with self.assertRaisesRegex(rebuild.RebuildError, "source inventory/profile"):
            rebuild._materialize_exact_source_plan(
                plan,
                target=target,
                profile=self._profile(model="different-model"),
                embedder=lambda texts: calls.append(list(texts)),
                batch_size=8,
            )
        self.assertEqual(calls, [])

        path.write_text(
            self._note(type_="resource", body=("changed source material " * 900)),
            encoding="utf-8",
        )
        changed_plan = self._knowledge_plan()
        with self.assertRaisesRegex(rebuild.RebuildError, "source inventory/profile"):
            rebuild._materialize_exact_source_plan(
                changed_plan,
                target=target,
                profile=profile,
                embedder=lambda texts: calls.append(list(texts)),
                batch_size=8,
            )
        self.assertEqual(calls, [])

    def test_exact_hcp_cache_corruption_fails_closed_without_embedding(self):
        path, plan = self._long_knowledge_plan()
        source = next(item for item in plan.sources if item.path == path.absolute())
        thesis = rebuild._prepare_knowledge_source(source).structural_index.document_thesis
        target = self.root / "inactive-chroma"
        profile = self._profile()
        rebuild._materialize_exact_source_plan(
            plan,
            target=target,
            profile=profile,
            embedder=self._semantic_embedder(thesis, []),
            batch_size=8,
        )
        cache_path = next(
            (target / ".ora-source-materialization" / "knowledge").glob("*.json")
        )
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache["scores"][0] = 0.123456
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
        calls = []
        with self.assertRaisesRegex(rebuild.RebuildError, "checksum is invalid"):
            rebuild._materialize_exact_source_plan(
                plan,
                target=target,
                profile=profile,
                embedder=lambda texts: calls.append(list(texts)),
                batch_size=8,
            )
        self.assertEqual(calls, [])

    def test_dedicated_msi_plan_uses_articles_root_and_not_sibling_columns(self):
        articles = self.root / "site" / "src" / "content" / "articles"
        columns = self.root / "site" / "src" / "content" / "columns"
        articles.mkdir(parents=True)
        columns.mkdir(parents=True)
        for name in ("one.md", "two.md"):
            (articles / name).write_text(
                f"Headline {name}\n" + ("article body " * 10),
                encoding="utf-8",
            )
        (columns / "column.md").write_text(
            "Column headline\n" + ("column body " * 10), encoding="utf-8",
        )

        plan = rebuild.build_msi_articles_replay_plan(
            articles_root=articles,
            composer_path=self.root / "unused-composer.py",
            composer=_MSIComposer(),
        )
        plan.require_valid()
        records = list(rebuild._iter_source_plan_records(plan))
        self.assertEqual({record.row_id for record in records}, {"one", "two"})
        self.assertEqual(plan.planned_records, 2)
        self.assertTrue(all("columns" not in record.source_path for record in records))
        rejected = rebuild.build_msi_articles_replay_plan(
            articles_root=columns,
            composer_path=self.root / "unused-composer.py",
            composer=_MSIComposer(),
        )
        with self.assertRaises(rebuild.RebuildError):
            rejected.require_valid()

    def test_partition_inventory_detects_all_markdown_inventory_mutations(self):
        path = self.resources / "bound.md"
        path.write_text(self._note(type_="resource"), encoding="utf-8")

        cases = ("added", "removed", "renamed", "identity_changed")
        for mutation in cases:
            with self.subTest(mutation=mutation):
                plan = self._knowledge_plan()
                self.assertEqual(len(plan.partitions), 4)
                self.assertTrue(any(
                    partition.root == self.mental.absolute()
                    and partition.inventory == ()
                    for partition in plan.partitions
                ))
                added = self.mental / "added.md"
                renamed = self.resources / "renamed.md"
                original = path.read_text(encoding="utf-8")
                if mutation == "added":
                    added.write_text(self._note(), encoding="utf-8")
                elif mutation == "removed":
                    path.unlink()
                elif mutation == "renamed":
                    path.rename(renamed)
                else:
                    path.write_text(
                        self._note(
                            type_="resource",
                            body="Identity-changing replacement content.",
                        ),
                        encoding="utf-8",
                    )
                with self.assertRaisesRegex(
                    rebuild.RebuildError, "source inventory changed",
                ):
                    rebuild._assert_source_inventory_unchanged(plan)
                if added.exists():
                    added.unlink()
                if renamed.exists():
                    renamed.rename(path)
                if not path.exists():
                    path.write_text(original, encoding="utf-8")
                elif mutation == "identity_changed":
                    path.write_text(original, encoding="utf-8")

    def test_empty_knowledge_partition_addition_fails_before_materialization(self):
        plan = self._knowledge_plan()
        (self.mental / "late.md").write_text(self._note(), encoding="utf-8")
        profile = self._profile()
        with mock.patch.object(rebuild, "_source_profile", return_value=profile), \
             mock.patch.object(rebuild, "_materialize_exact_source_plan") as materialize:
            with self.assertRaisesRegex(
                rebuild.RebuildError, "source inventory changed.*added",
            ):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=self.root / "fresh-chroma",
                    client_factory=lambda _path: (_ for _ in ()).throw(
                        AssertionError("source change opened Chroma")
                    ),
                    embedder=lambda _texts: (_ for _ in ()).throw(
                        AssertionError("source change opened embedder")
                    ),
                )
        materialize.assert_not_called()

    def test_msi_addition_during_materialization_fails_before_chroma_open(self):
        articles = self.root / "site" / "src" / "content" / "articles"
        articles.mkdir(parents=True)
        (articles / "one.md").write_text(
            "Headline one\n" + ("article body " * 10), encoding="utf-8",
        )
        plan = rebuild.build_msi_articles_replay_plan(
            articles_root=articles,
            composer_path=self.root / "unused-composer.py",
            composer=_MSIComposer(),
        )
        original_materialize = rebuild._materialize_exact_source_plan

        def mutate_after_materialization(*args, **kwargs):
            result = original_materialize(*args, **kwargs)
            (articles / "late.md").write_text(
                "Late headline\n" + ("late article body " * 10),
                encoding="utf-8",
            )
            return result

        client_calls = []
        with mock.patch.object(
            rebuild, "_source_profile", return_value=self._profile(),
        ), mock.patch.object(
            rebuild,
            "_materialize_exact_source_plan",
            side_effect=mutate_after_materialization,
        ):
            with self.assertRaisesRegex(
                rebuild.RebuildError, "source inventory changed.*added",
            ):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=self.root / "fresh-msi-chroma",
                    client_factory=lambda path: client_calls.append(path),
                    embedder=lambda texts: [[0.0] * 4096 for _text in texts],
                )
        self.assertEqual(client_calls, [])

    def test_source_addition_during_replay_cannot_write_complete_report(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        plan = self._knowledge_plan()
        target = self.root / "fresh-chroma"
        collection = _EmbeddingFakeCollection()

        def embed(texts):
            (self.resources / "late.md").write_text(
                self._note(type_="resource"), encoding="utf-8",
            )
            return [[0.0] * 4096 for _text in texts]

        with mock.patch.object(
            rebuild, "_source_profile", return_value=self._profile(),
        ):
            with self.assertRaisesRegex(
                rebuild.RebuildError, "source inventory changed.*added",
            ):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=target,
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=embed,
                )
        self.assertEqual(collection.count(), 1)
        self.assertFalse((target / "knowledge-replay-report.json").exists())

    def test_execute_batches_explicit_4096_vectors_and_resume_skips_existing(self):
        for index in range(3):
            (self.engrams / f"claim-{index}.md").write_text(
                self._note(body=f"Durable claim number {index} with context."),
                encoding="utf-8",
            )
        plan = self._knowledge_plan()
        plan.require_valid()
        target = self.root / "fresh-chroma"
        collection = _EmbeddingFakeCollection()
        calls = []

        def embed(texts):
            calls.append(list(texts))
            return [[float(index)] * 4096 for index, _text in enumerate(texts)]

        profile = {
            "provider": "openrouter",
            "model": "qwen/qwen3-embedding-8b",
            "dimension": 4096,
            "physical_collection": "knowledge_qwen",
        }
        with mock.patch.object(rebuild, "_source_profile", return_value=profile):
            first = rebuild.execute_source_replay(
                plan,
                target_chromadb_path=target,
                batch_size=2,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=embed,
            )
            call_count = len(calls)
            second = rebuild.execute_source_replay(
                plan,
                target_chromadb_path=target,
                batch_size=2,
                resume=True,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=embed,
            )
        self.assertEqual(first["target_count"], 3)
        self.assertEqual(collection.upsert_sizes, [2, 1])
        self.assertEqual(len(calls), call_count)
        self.assertEqual(second["embedded_records"], 0)
        self.assertEqual(second["resumed_records"], 3)
        self.assertTrue(all(len(vector) == 4096 for vector in collection.embeddings.values()))
        self.assertTrue((target / "knowledge-replay-checkpoint.json").is_file())
        self.assertTrue((target / "knowledge-replay-report.json").is_file())

    def test_concurrent_embeddings_commit_and_checkpoint_in_record_order(self):
        for index in range(4):
            (self.engrams / f"claim-{index}.md").write_text(
                self._note(body=f"Durable claim number {index} with context."),
                encoding="utf-8",
            )
        plan = self._knowledge_plan()
        expected_ids = [
            record.row_id for record in rebuild._iter_source_plan_records(plan)
        ]
        target = self.root / "fresh-concurrent-chroma"
        caller_thread = threading.get_ident()
        event_log = []
        collection_threads = []

        class OrderedCollection(_EmbeddingFakeCollection):
            def get(inner_self, *, ids, include):
                collection_threads.append(threading.get_ident())
                return super().get(ids=ids, include=include)

            def upsert(inner_self, *, ids, embeddings, documents, metadatas):
                collection_threads.append(threading.get_ident())
                event_log.append(("upsert", list(ids)))
                return super().upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )

            def count(inner_self):
                collection_threads.append(threading.get_ident())
                return super().count()

        collection = OrderedCollection()
        embed_barrier = threading.Barrier(2)
        embed_lock = threading.Lock()
        active = 0
        maximum_active = 0
        next_call = 0
        completed = []
        embed_threads = []

        def embed(texts):
            nonlocal active, maximum_active, next_call
            with embed_lock:
                call_index = next_call
                next_call += 1
                active += 1
                maximum_active = max(maximum_active, active)
                embed_threads.append(threading.get_ident())
            try:
                if call_index < 2:
                    embed_barrier.wait(timeout=5)
                if call_index == 0:
                    time.sleep(0.05)
                completed.append(call_index)
                return [[float(call_index)] * 4096 for _text in texts]
            finally:
                with embed_lock:
                    active -= 1

        original_atomic_json = rebuild._atomic_json

        def recording_atomic_json(path, value):
            if path.name == "knowledge-replay-checkpoint.json":
                self.assertEqual(threading.get_ident(), caller_thread)
                event_log.append(("checkpoint", value["next_index"]))
            return original_atomic_json(path, value)

        with mock.patch.object(
            rebuild, "_source_profile", return_value=self._profile(),
        ), mock.patch.object(
            rebuild, "_atomic_json", side_effect=recording_atomic_json,
        ):
            report = rebuild.execute_source_replay(
                plan,
                target_chromadb_path=target,
                batch_size=1,
                embedding_workers=2,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=embed,
            )

        self.assertEqual(report["target_count"], 4)
        self.assertEqual(maximum_active, 2)
        self.assertEqual(completed[:2], [1, 0])
        self.assertTrue(all(thread != caller_thread for thread in embed_threads))
        self.assertEqual(set(collection_threads), {caller_thread})
        self.assertEqual(event_log, [
            ("upsert", [expected_ids[0]]), ("checkpoint", 1),
            ("upsert", [expected_ids[1]]), ("checkpoint", 2),
            ("upsert", [expected_ids[2]]), ("checkpoint", 3),
            ("upsert", [expected_ids[3]]), ("checkpoint", 4),
        ])

    def test_concurrent_embedding_failure_drains_and_resumes_from_checkpoint(self):
        for index in range(4):
            (self.engrams / f"claim-{index}.md").write_text(
                self._note(body=f"Durable claim number {index} with context."),
                encoding="utf-8",
            )
        plan = self._knowledge_plan()
        expected_ids = [
            record.row_id for record in rebuild._iter_source_plan_records(plan)
        ]
        target = self.root / "interrupted-concurrent-chroma"
        collection = _EmbeddingFakeCollection()
        first_wave = threading.Barrier(3)
        drained = threading.Event()

        def interrupted_embed(texts):
            text = texts[0]
            if any(f"number {index}" in text for index in range(3)):
                first_wave.wait(timeout=5)
            if "number 1" in text:
                raise RuntimeError("synthetic concurrent interruption")
            if "number 2" in text:
                time.sleep(0.05)
                drained.set()
            return [[0.0] * 4096 for _text in texts]

        with mock.patch.object(
            rebuild, "_source_profile", return_value=self._profile(),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "synthetic concurrent interruption",
            ):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=target,
                    batch_size=1,
                    embedding_workers=3,
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=interrupted_embed,
                )

        self.assertTrue(drained.is_set())
        self.assertEqual(collection.upsert_sizes, [1])
        self.assertEqual(list(collection.rows), [expected_ids[0]])
        checkpoint = json.loads(
            (target / "knowledge-replay-checkpoint.json").read_text(
                encoding="utf-8",
            )
        )
        self.assertEqual(checkpoint["next_index"], 1)
        self.assertFalse((target / "knowledge-replay-report.json").exists())

        resumed_inputs = []

        def resumed_embed(texts):
            resumed_inputs.extend(texts)
            return [[1.0] * 4096 for _text in texts]

        with mock.patch.object(
            rebuild, "_source_profile", return_value=self._profile(),
        ):
            report = rebuild.execute_source_replay(
                plan,
                target_chromadb_path=target,
                batch_size=1,
                embedding_workers=2,
                resume=True,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=resumed_embed,
            )
        self.assertEqual(report["target_count"], 4)
        self.assertEqual(report["resumed_records"], 1)
        self.assertEqual(len(resumed_inputs), 3)
        self.assertFalse(any("number 0" in text for text in resumed_inputs))
        self.assertEqual(list(collection.rows), expected_ids)

    def test_default_embedding_worker_is_synchronous_and_does_not_open_pool(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        plan = self._knowledge_plan()
        collection = _EmbeddingFakeCollection()
        caller_thread = threading.get_ident()
        embed_threads = []

        def embed(texts):
            embed_threads.append(threading.get_ident())
            return [[0.0] * 4096 for _text in texts]

        with mock.patch.object(
            rebuild, "_source_profile", return_value=self._profile(),
        ), mock.patch.object(
            rebuild.ThreadPoolExecutor,
            "__init__",
            side_effect=AssertionError("default replay opened a worker pool"),
        ):
            report = rebuild.execute_source_replay(
                plan,
                target_chromadb_path=self.root / "default-worker-chroma",
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=embed,
            )
        self.assertEqual(report["target_count"], 1)
        self.assertEqual(embed_threads, [caller_thread])

    def test_embedding_workers_cli_default_and_explicit_wiring(self):
        target = self.root / "cli-target"
        default_args = rebuild._parser().parse_args([
            "knowledge", "--target-chromadb-path", str(target),
        ])
        self.assertEqual(default_args.embedding_workers, 1)

        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        with mock.patch.object(
            rebuild, "execute_source_replay", return_value={"status": "complete"},
        ) as execute, mock.patch("builtins.print"):
            result = rebuild.main([
                "knowledge",
                "--engrams-root", str(self.engrams),
                "--resources-root", str(self.resources),
                "--mental-models-root", str(self.mental),
                "--msi-news-root", str(self.msi_mirror),
                "--target-chromadb-path", str(target),
                "--embedding-workers", "4",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(execute.call_args.kwargs["embedding_workers"], 4)

    def test_source_resume_rejects_corrupted_checkpoint_prefix_without_embedding(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        plan = self._knowledge_plan()
        target = self.root / "fresh-chroma"
        collection = _EmbeddingFakeCollection()
        embedding_calls = []

        def embed(texts):
            embedding_calls.append(list(texts))
            return [[0.0] * 4096 for _text in texts]

        profile = {
            "provider": "openrouter",
            "model": "qwen/qwen3-embedding-8b",
            "dimension": 4096,
            "physical_collection": "knowledge_qwen",
        }
        with mock.patch.object(rebuild, "_source_profile", return_value=profile):
            rebuild.execute_source_replay(
                plan,
                target_chromadb_path=target,
                client_factory=lambda _path: object(),
                collection_factory=lambda _client, _profile: collection,
                embedder=embed,
            )
            calls_before_resume = len(embedding_calls)
            row_id = next(iter(collection.rows))
            _document, metadata = collection.rows[row_id]
            collection.rows[row_id] = ("corrupted document", metadata)
            with self.assertRaisesRegex(
                rebuild.RebuildError,
                "checkpoint-resumed knowledge prefix payload differs",
            ):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=target,
                    resume=True,
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=embed,
                )
        self.assertEqual(len(embedding_calls), calls_before_resume)

    def test_final_source_validation_rejects_metadata_corruption(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        plan = self._knowledge_plan()
        collection = _FinalMetadataCorruptingCollection()
        profile = {
            "provider": "openrouter",
            "model": "qwen/qwen3-embedding-8b",
            "dimension": 4096,
            "physical_collection": "knowledge_qwen",
        }
        with mock.patch.object(rebuild, "_source_profile", return_value=profile):
            with self.assertRaisesRegex(
                rebuild.RebuildError,
                "final knowledge validation payload differs",
            ):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=self.root / "fresh-chroma",
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=lambda texts: [[0.0] * 4096 for _text in texts],
                )

    def test_wrong_embedding_dimension_fails_before_upsert(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        plan = self._knowledge_plan()
        target = self.root / "fresh-chroma"
        collection = _EmbeddingFakeCollection()
        profile = {
            "provider": "openrouter",
            "model": "qwen/qwen3-embedding-8b",
            "dimension": 4096,
            "physical_collection": "knowledge_qwen",
        }
        with mock.patch.object(rebuild, "_source_profile", return_value=profile):
            with self.assertRaises(rebuild.RebuildError):
                rebuild.execute_source_replay(
                    plan,
                    target_chromadb_path=target,
                    client_factory=lambda _path: object(),
                    collection_factory=lambda _client, _profile: collection,
                    embedder=lambda _texts: [[0.0] * 1024],
                )
        self.assertEqual(collection.count(), 0)

    def test_non_finite_embeddings_fail_after_numeric_conversion(self):
        record = rebuild.ReplayRecord(
            row_id="unsafe-vector",
            document="document",
            metadata={},
            source_path="source.md",
            source_kind="knowledge_resource",
        )
        for value in (
            float("nan"), float("inf"), float("-inf"),
            "NaN", "Infinity", "-Infinity",
        ):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(
                    rebuild.RebuildError, "non-finite value",
                ):
                    rebuild._validate_embeddings(
                        [[0.0, value, 1.0]], records=[record], dimension=3,
                    )

    def test_source_symlink_directory_and_active_target_overlap_fail_closed(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "escaped.md").write_text(self._note(), encoding="utf-8")
        (self.resources / "escape").symlink_to(outside, target_is_directory=True)
        plan = self._knowledge_plan()
        with self.assertRaises(rebuild.RebuildError):
            plan.require_valid()

        active = self.root / "active-chroma"
        active.mkdir()
        with mock.patch.object(rebuild.rp, "chromadb_dir", return_value=active):
            with self.assertRaises(rebuild.RebuildError):
                rebuild._validate_target(active / "nested-rebuild", resume=False)

    def test_knowledge_dry_run_never_opens_chroma_or_embedder(self):
        (self.engrams / "claim.md").write_text(
            self._note(), encoding="utf-8",
        )
        with mock.patch.object(rebuild, "execute_source_replay") as execute, \
             mock.patch.object(rebuild, "_source_profile") as profile:
            result = rebuild.main([
                "knowledge",
                "--engrams-root", str(self.engrams),
                "--resources-root", str(self.resources),
                "--mental-models-root", str(self.mental),
                "--msi-news-root", str(self.msi_mirror),
                "--target-chromadb-path", str(self.root / "unused"),
                "--dry-run",
            ])
        self.assertEqual(result, 0)
        execute.assert_not_called()
        profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
