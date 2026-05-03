"""Tests for the Phase 2 batch CLI (chain detection + chunk emission)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.embedding import install_test_stub  # noqa: E402
from orchestrator.historical.path2_cli import (  # noqa: E402
    _empty_manifest,
    build_sessions_from_archive,
    load_manifest,
    manifest_record_session,
    run_chain_detection,
    run_chunk_emission,
    save_manifest,
)
from orchestrator.historical.path2_orchestrator import (  # noqa: E402
    SessionEmissionResult,
)
from orchestrator.tests.test_path2_orchestrator import (  # noqa: E402
    _write_cleaned_pair,
)

install_test_stub()


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class TestManifest(unittest.TestCase):

    def test_save_load_roundtrip(self):
        m = _empty_manifest()
        m["completed_sessions"]["~/foo.md"] = {"chunks_written": 5}
        m["totals"] = {"sessions_completed": 1, "chunks_written": 5,
                        "chunks_indexed": 5, "chunks_skipped": 0}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_manifest(m, path=path)
            loaded = load_manifest(path)
            self.assertEqual(loaded["completed_sessions"]["~/foo.md"]["chunks_written"], 5)
            self.assertEqual(loaded["totals"]["sessions_completed"], 1)
        finally:
            os.unlink(path)

    def test_record_session_updates_totals(self):
        m = _empty_manifest()
        result = SessionEmissionResult(
            source_chat="~/foo.md",
            session_id="abc123",
            chain_id="chain-xyz",
            chain_label="topic",
            pairs_total=3,
            chunks_written=3,
            chunks_indexed=3,
            chunks_skipped=0,
        )
        manifest_record_session(m, "~/foo.md", result)
        self.assertIn("~/foo.md", m["completed_sessions"])
        self.assertEqual(m["totals"]["sessions_completed"], 1)
        self.assertEqual(m["totals"]["chunks_written"], 3)


# ---------------------------------------------------------------------------
# Stage A — chain detection on a small synthetic archive
# ---------------------------------------------------------------------------


class TestChainDetectionEndToEnd(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cp_dir = os.path.join(self.tmp, "cleaned-pairs")
        self.chain_path = os.path.join(self.tmp, "chain-index.json")
        os.makedirs(self.cp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_session(self, source_chat: str, n_pairs: int = 2,
                        topic: str = "American Jesus discussion"):
        for i in range(1, n_pairs + 1):
            _write_cleaned_pair(
                self.cp_dir,
                pair_num=i,
                timestamp=f"2025-08-12T10:{i:02d}:00",
                user_input=topic,
                ai_response="Cleaned reply.",
                source_chat=source_chat,
                thread_id=f"thread_{abs(hash(source_chat)) % 10**8:08x}_{i:03d}",
            )

    def test_detect_chains_persists_index(self):
        # Three sessions, two with shared topic in filename.
        self._write_session("~/raw/American Jesus Notes 1.md")
        self._write_session("~/raw/American Jesus Notes 2.md")
        self._write_session("~/raw/Unrelated Topic.md", topic="weather")
        result = run_chain_detection(
            cleaned_pair_dir=self.cp_dir,
            chain_index_path=self.chain_path,
            progress_to_stderr=False,
        )
        self.assertEqual(result["sessions"], 3)
        self.assertGreater(result["chains"], 0)
        # Index file written.
        self.assertTrue(os.path.exists(self.chain_path))
        idx = json.loads(open(self.chain_path).read())
        self.assertEqual(idx["session_count"], 3)
        self.assertIn("session_to_chain", idx)


# ---------------------------------------------------------------------------
# Stage B — chunk emission with chain-id assignment
# ---------------------------------------------------------------------------


class TestChunkEmissionEndToEnd(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cp_dir = os.path.join(self.tmp, "cleaned-pairs")
        self.conv_dir = os.path.join(self.tmp, "conversations")
        self.chroma = os.path.join(self.tmp, "chromadb")
        self.chain_path = os.path.join(self.tmp, "chain-index.json")
        self.manifest = os.path.join(self.tmp, "manifest.json")
        os.makedirs(self.cp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_pipeline_chains_then_emits(self):
        # Two related sessions + one unrelated, then run both stages.
        for i in range(1, 3):
            _write_cleaned_pair(
                self.cp_dir,
                pair_num=i,
                timestamp=f"2025-08-12T10:{i:02d}:00",
                user_input="American Jesus narrative discussion topic.",
                ai_response="Reply.",
                source_chat="~/raw/American Jesus Notes Alpha.md",
                thread_id=f"thread_aaaa{i:04d}_001",
            )
        for i in range(1, 3):
            _write_cleaned_pair(
                self.cp_dir,
                pair_num=i,
                timestamp=f"2025-08-13T10:{i:02d}:00",
                user_input="American Jesus narrative discussion topic.",
                ai_response="Reply.",
                source_chat="~/raw/American Jesus Notes Beta.md",
                thread_id=f"thread_bbbb{i:04d}_001",
            )
        _write_cleaned_pair(
            self.cp_dir,
            pair_num=1,
            timestamp="2025-08-14T10:00:00",
            user_input="Weather forecast for tomorrow.",
            ai_response="Sunny.",
            source_chat="~/raw/Weather Talk.md",
            thread_id="thread_cccc0001_001",
        )
        # Stage A.
        chain_stats = run_chain_detection(
            cleaned_pair_dir=self.cp_dir,
            chain_index_path=self.chain_path,
            progress_to_stderr=False,
        )
        sessions_to_paths = chain_stats["sessions_to_paths"]
        # Stage B.
        emit_stats = run_chunk_emission(
            sessions_to_paths,
            chain_index_path=self.chain_path,
            conversations_dir=self.conv_dir,
            chromadb_path=self.chroma,
            manifest_path=self.manifest,
            max_workers=1,
            progress_to_stderr=False,
        )
        # Five chunk files should land in conv_dir (2+2+1).
        chunk_files = [f for f in os.listdir(self.conv_dir) if f.endswith(".md")]
        self.assertEqual(len(chunk_files), 5)
        # Manifest tracks all 3 sessions.
        m = load_manifest(self.manifest)
        self.assertEqual(len(m["completed_sessions"]), 3)
        # Stage B reports its work.
        self.assertEqual(emit_stats["sessions_processed"], 3)
        self.assertEqual(emit_stats["chunks_written"], 5)


# ---------------------------------------------------------------------------
# Build sessions from archive
# ---------------------------------------------------------------------------


class TestBuildSessions(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cp_dir = os.path.join(self.tmp, "cleaned-pairs")
        os.makedirs(self.cp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_sessions_groups_by_source_chat(self):
        for i in (1, 2):
            _write_cleaned_pair(
                self.cp_dir, pair_num=i,
                timestamp=f"2025-08-12T10:{i:02d}:00",
                user_input=f"Q{i}", ai_response=f"A{i}",
                source_chat="~/raw/A.md", thread_id=f"thread_aa{i:04d}_001",
            )
        _write_cleaned_pair(
            self.cp_dir, pair_num=1,
            timestamp="2025-08-13T10:00:00",
            user_input="Q", ai_response="A",
            source_chat="~/raw/B.md", thread_id="thread_bb000001_001",
        )
        sessions, sessions_to_paths = build_sessions_from_archive(
            cleaned_pair_dir=self.cp_dir, progress_to_stderr=False,
        )
        self.assertEqual(len(sessions), 2)
        self.assertEqual(len(sessions_to_paths["~/raw/A.md"]), 2)
        self.assertEqual(len(sessions_to_paths["~/raw/B.md"]), 1)


if __name__ == "__main__":
    unittest.main()
