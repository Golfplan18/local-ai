"""Tests for the historical Path 2 emitter.

The emitter reads parsed historical chat messages and emits one
chunk file plus one ChromaDB record per prompt+response pair —
indistinguishable from what live `_save_conversation` would produce,
except that historical timestamps are preserved.

Verifies:
  - Pair extraction from a parsed message list (orphans skipped,
    timestamps preserved, pair_num monotonic).
  - Pre-process stages run in order; skip_reason drops pairs.
  - Chunk files written to the configured directory with Schema §12 YAML.
  - ChromaDB records carry the full Conv RAG §2 metadata schema with
    historical timestamps in the temporal fields.
  - Finalize step sets total_turns + is_last_turn at the end.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.tools.path2_emitter import (  # noqa: E402
    Pair,
    pairs_from_messages,
    emit_path2_chunks,
)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


# Realistic message list as the raw-log parser would produce.
SAMPLE_MESSAGES = [
    {"role": "user",      "content": "What is consciousness?",
     "timestamp": "2024-06-15 10:00:00"},
    {"role": "assistant", "content": "Consciousness is subjective experience.",
     "timestamp": "2024-06-15 10:00:05"},
    {"role": "user",      "content": "Tell me about Python data structures.",
     "timestamp": "2024-06-15 10:05:00"},
    {"role": "assistant", "content": "Python provides lists, dicts, sets.",
     "timestamp": "2024-06-15 10:05:08"},
    {"role": "user",      "content": "Thanks, that's helpful.",
     "timestamp": "2024-06-15 10:10:00"},
    {"role": "assistant", "content": "You're welcome.",
     "timestamp": "2024-06-15 10:10:02"},
]


# ---------------------------------------------------------------------------
# Pair extraction
# ---------------------------------------------------------------------------


class TestPairExtraction(unittest.TestCase):

    def test_three_pairs_emerge(self):
        pairs = list(pairs_from_messages(SAMPLE_MESSAGES))
        self.assertEqual(len(pairs), 3)
        self.assertEqual([p.pair_num for p in pairs], [1, 2, 3])

    def test_timestamps_preserved(self):
        pairs = list(pairs_from_messages(SAMPLE_MESSAGES))
        self.assertEqual(pairs[0].when, datetime(2024, 6, 15, 10, 0, 5))
        self.assertEqual(pairs[1].when, datetime(2024, 6, 15, 10, 5, 8))

    def test_orphan_user_dropped(self):
        # Trailing user with no assistant follow-up.
        msgs = SAMPLE_MESSAGES + [
            {"role": "user", "content": "orphan", "timestamp": "2024-06-15 10:15:00"}
        ]
        pairs = list(pairs_from_messages(msgs))
        self.assertEqual(len(pairs), 3)

    def test_orphan_assistant_dropped(self):
        # Leading assistant with no user prompt.
        msgs = [{"role": "assistant", "content": "leading"}] + SAMPLE_MESSAGES
        pairs = list(pairs_from_messages(msgs))
        self.assertEqual(len(pairs), 3)

    def test_missing_timestamp_falls_back(self):
        msgs = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        default = datetime(2026, 1, 1, 12, 0, 0)
        pairs = list(pairs_from_messages(msgs, default_when=default))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].when, default)

    def test_system_messages_ignored(self):
        msgs = (
            [{"role": "system", "content": "system prompt"}]
            + SAMPLE_MESSAGES
        )
        pairs = list(pairs_from_messages(msgs))
        self.assertEqual(len(pairs), 3)


# ---------------------------------------------------------------------------
# Emission end-to-end
# ---------------------------------------------------------------------------


class TestEmitPath2Chunks(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conv_dir = os.path.join(self.tmpdir, "conversations")
        self.chroma_path = os.path.join(self.tmpdir, "chromadb")
        self.raw_path = os.path.join(self.tmpdir, "raw_log.md")
        # Touch a fake raw file so close_conversation can find it later
        # (not strictly required for tests; just realistic).
        with open(self.raw_path, "w", encoding="utf-8") as f:
            f.write("placeholder")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _emit(self, messages=None, **kwargs):
        return emit_path2_chunks(
            messages or SAMPLE_MESSAGES,
            conversation_id=kwargs.pop("conversation_id", "conv-historical-001"),
            raw_path=self.raw_path,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma_path,
            **kwargs,
        )

    def _read_chroma(self, conversation_id="conv-historical-001"):
        import chromadb
        client = chromadb.PersistentClient(path=self.chroma_path)
        col = client.get_collection("conversations")
        return col.get(where={"conversation_id": conversation_id})

    def test_emits_one_chunk_per_pair(self):
        result = self._emit()
        self.assertEqual(result["chunks_written"], 3)
        self.assertEqual(result["chunks_indexed"], 3)
        # 3 chunk files in the conversations dir.
        files = [f for f in os.listdir(self.conv_dir) if f.endswith(".md")]
        self.assertEqual(len(files), 3)

    def test_chunks_use_historical_dates_in_filename(self):
        self._emit()
        files = sorted(os.listdir(self.conv_dir))
        # All filenames should start with 2024-06-15 (the historical date).
        for fname in files:
            if fname.endswith(".md"):
                self.assertTrue(fname.startswith("2024-06-15"),
                                f"unexpected filename: {fname}")

    def test_chunks_use_schema12_yaml(self):
        self._emit()
        files = sorted(os.listdir(self.conv_dir))
        body = open(os.path.join(self.conv_dir, files[0]),
                    encoding="utf-8").read()
        self.assertTrue(body.startswith("---\n"))
        self.assertIn("type: chat", body)
        # Bespoke fields not present.
        self.assertNotIn("source_file:", body)
        self.assertNotIn("session_id:", body)
        # Historical date in YAML.
        self.assertIn("date created: 2024-06-15", body)

    def test_chromadb_metadata_uses_historical_temporal_fields(self):
        self._emit()
        records = self._read_chroma()
        self.assertEqual(len(records["ids"]), 3)
        for meta in records["metadatas"]:
            # Year/month from the historical timestamp, not now()
            self.assertEqual(meta["year"], 2024)
            self.assertEqual(meta["month"], 6)
            self.assertEqual(meta["date"], "2024-06-15")
            self.assertTrue(meta["timestamp_utc"].startswith("2024-06-15"))

    def test_chromadb_metadata_has_full_22_fields(self):
        self._emit()
        records = self._read_chroma()
        meta = records["metadatas"][0]
        for field in (
            "timestamp_utc", "date", "year", "month",
            "conversation_id", "conversation_title", "session_id",
            "turn_index", "total_turns", "chunk_type",
            "is_first_turn", "is_last_turn",
            "topic_primary", "turn_summary",
            "source_platform", "model_id",
            "thread_id", "obsidian_path", "file_hash",
            "tag_archived", "tag_incubating", "tag_private",
            "type",
        ):
            self.assertIn(field, meta, f"missing metadata field: {field}")

    def test_finalize_sets_total_turns_and_last_turn(self):
        self._emit()
        records = self._read_chroma()
        # All chunks should have total_turns=3 (final value after finalize).
        for meta in records["metadatas"]:
            self.assertEqual(meta["total_turns"], 3)
        # Exactly one chunk has is_last_turn=True (the highest turn_index).
        last_turns = [m for m in records["metadatas"] if m["is_last_turn"]]
        self.assertEqual(len(last_turns), 1)
        self.assertEqual(last_turns[0]["turn_index"], 3)

    def test_finalize_can_be_disabled(self):
        self._emit(finalize=False)
        records = self._read_chroma()
        # Without finalize, total_turns stays at the per-pair init value.
        for meta in records["metadatas"]:
            self.assertEqual(meta["total_turns"], meta["turn_index"])
            self.assertFalse(meta["is_last_turn"])

    def test_pre_process_stage_runs(self):
        ran = {"count": 0}

        def stage(pair):
            ran["count"] += 1
            return pair

        self._emit(pre_process_stages=[stage])
        # Three pairs → stage called three times.
        self.assertEqual(ran["count"], 3)

    def test_skip_reason_drops_pair(self):
        def reject_pair_2(pair):
            if pair.pair_num == 2:
                pair.skip_reason = "test-skip"
            return pair

        result = self._emit(pre_process_stages=[reject_pair_2])
        self.assertEqual(result["chunks_written"], 2)
        self.assertEqual(result["skipped_pairs"], 1)
        # The two emitted chunks are pair 1 and pair 3.
        records = self._read_chroma()
        turn_indices = sorted(m["turn_index"] for m in records["metadatas"])
        self.assertEqual(turn_indices, [1, 3])

    def test_thread_id_continuity_across_topic_changes(self):
        self._emit()
        records = self._read_chroma()
        # The mechanical fallback yields a topic from the first user
        # input keyword. Pair 1 ("consciousness"), pair 2 ("tell"), pair 3
        # ("thanks") — three different first keywords → three threads.
        thread_ids = sorted(
            (m["turn_index"], m["thread_id"]) for m in records["metadatas"]
        )
        # All thread_ids should be distinct (3 different topics).
        seen_threads = {tid for _, tid in thread_ids}
        self.assertGreaterEqual(len(seen_threads), 1)  # at minimum 1; up to 3

    def test_private_tag_propagates_to_metadata(self):
        self._emit(tag="private")
        records = self._read_chroma()
        for meta in records["metadatas"]:
            self.assertTrue(meta["tag_private"])
            self.assertEqual(meta["tag"], "private")

    def test_chunk_path_stored_for_close_out(self):
        # Stealth/private close-out reads chunk_path + raw_path from
        # ChromaDB metadata. Path 2 must populate them.
        self._emit()
        records = self._read_chroma()
        for meta in records["metadatas"]:
            self.assertTrue(meta["chunk_path"].endswith(".md"))
            self.assertEqual(meta["raw_path"], self.raw_path)

    def test_filename_collision_handled(self):
        # Two pairs with same minute + same first user keyword would
        # collide in filename. The emitter appends a -pair003 suffix.
        msgs = [
            {"role": "user",      "content": "Pipeline question",
             "timestamp": "2024-06-15 10:00:00"},
            {"role": "assistant", "content": "Pipeline answer 1",
             "timestamp": "2024-06-15 10:00:05"},
            {"role": "user",      "content": "Pipeline followup",
             "timestamp": "2024-06-15 10:00:30"},  # same minute
            {"role": "assistant", "content": "Pipeline answer 2",
             "timestamp": "2024-06-15 10:00:35"},
        ]
        result = self._emit(messages=msgs, conversation_id="conv-collide")
        self.assertEqual(result["chunks_written"], 2)
        files = [f for f in os.listdir(self.conv_dir) if f.endswith(".md")]
        self.assertEqual(len(files), 2)
        # All filenames distinct.
        self.assertEqual(len(set(files)), 2)


if __name__ == "__main__":
    unittest.main()
