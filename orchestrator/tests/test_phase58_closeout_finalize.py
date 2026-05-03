"""Tests for Phase 5.8 close-out finalization.

Per the Q3 plan in the Phase 5 handoff: total_turns and is_last_turn
are initialized at save time and finalized when the conversation closes.
The finalization walks all chunks for the conversation, sets
total_turns to the highest observed turn_index, and marks
is_last_turn=True on the chunk(s) at that index.

Stealth conversations purge instead of finalize (covered by existing
close_conversation tests; this file targets non-stealth finalization).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.conversation_closeout import _finalize_conversation_chunks  # noqa: E402

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


class TestFinalizeConversationChunks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        # Seed a conversations collection with three turns of one
        # conversation, plus an unrelated chunk that must not be touched.
        import chromadb
        from orchestrator.embedding import get_or_create_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "conversations")
        col.add(
            ids=["c-1-001", "c-1-002", "c-1-003", "c-2-001"],
            documents=["q1", "q2", "q3", "other"],
            metadatas=[
                {"conversation_id": "conv-1", "turn_index": 1,
                 "total_turns": 1, "is_last_turn": False, "type": "chat"},
                {"conversation_id": "conv-1", "turn_index": 2,
                 "total_turns": 2, "is_last_turn": False, "type": "chat"},
                {"conversation_id": "conv-1", "turn_index": 3,
                 "total_turns": 3, "is_last_turn": False, "type": "chat"},
                {"conversation_id": "conv-2", "turn_index": 1,
                 "total_turns": 1, "is_last_turn": False, "type": "chat"},
            ],
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_meta(self, conversation_id):
        import chromadb
        from orchestrator.embedding import get_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "conversations")
        return col.get(where={"conversation_id": conversation_id})

    def test_total_turns_updated_on_all_chunks(self):
        from pathlib import Path
        result = _finalize_conversation_chunks(
            "conv-1", chromadb_path=Path(self.chromadb_path),
        )
        self.assertEqual(result["chunks_updated"], 3)
        self.assertEqual(result["final_turn"], 3)

        records = self._read_meta("conv-1")
        for meta in records["metadatas"]:
            self.assertEqual(meta["total_turns"], 3)

    def test_is_last_turn_set_on_final_chunk_only(self):
        from pathlib import Path
        _finalize_conversation_chunks(
            "conv-1", chromadb_path=Path(self.chromadb_path),
        )
        records = self._read_meta("conv-1")
        for meta in records["metadatas"]:
            if meta["turn_index"] == 3:
                self.assertTrue(meta["is_last_turn"])
            else:
                self.assertFalse(meta["is_last_turn"])

    def test_other_conversation_not_touched(self):
        from pathlib import Path
        _finalize_conversation_chunks(
            "conv-1", chromadb_path=Path(self.chromadb_path),
        )
        records = self._read_meta("conv-2")
        meta = records["metadatas"][0]
        # conv-2 still has its initial state.
        self.assertEqual(meta["total_turns"], 1)
        self.assertFalse(meta["is_last_turn"])

    def test_no_chunks_returns_zero(self):
        from pathlib import Path
        result = _finalize_conversation_chunks(
            "conv-nonexistent", chromadb_path=Path(self.chromadb_path),
        )
        self.assertEqual(result["chunks_updated"], 0)
        self.assertEqual(result["final_turn"], 0)


class TestCloseConversationDispatchToFinalize(unittest.TestCase):
    """The close-out endpoint dispatches to _finalize for non-stealth
    conversations. Stealth purges instead (covered elsewhere)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        self.sessions_root = os.path.join(self.tmpdir, "sessions")
        os.makedirs(self.sessions_root)

        # Create a conversation envelope with empty (standard) tag.
        import json
        conv_dir = os.path.join(self.sessions_root, "conv-std-001")
        os.makedirs(conv_dir)
        with open(os.path.join(conv_dir, "conversation.json"), "w") as f:
            json.dump({"conversation_id": "conv-std-001", "tag": ""}, f)

        # Seed two chunks for it.
        import chromadb
        from orchestrator.embedding import get_or_create_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "conversations")
        col.add(
            ids=["std-001", "std-002"],
            documents=["q1", "q2"],
            metadatas=[
                {"conversation_id": "conv-std-001", "turn_index": 1,
                 "total_turns": 1, "is_last_turn": False, "type": "chat"},
                {"conversation_id": "conv-std-001", "turn_index": 2,
                 "total_turns": 2, "is_last_turn": False, "type": "chat"},
            ],
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_close_finalizes_standard_conversation(self):
        from pathlib import Path
        from orchestrator.conversation_closeout import close_conversation
        result = close_conversation(
            "conv-std-001",
            sessions_root=Path(self.sessions_root),
            chromadb_path=Path(self.chromadb_path),
        )
        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["tag"], "")
        # finalize sub-result
        self.assertIn("finalize", result)
        self.assertEqual(result["finalize"]["chunks_updated"], 2)
        self.assertEqual(result["finalize"]["final_turn"], 2)


if __name__ == "__main__":
    unittest.main()
