"""Tests for Phase 5 — atomic extraction with reverse-walk dedup."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.embedding import install_test_stub  # noqa: E402
from orchestrator.historical.phase5_atomic_extraction import (  # noqa: E402
    AtomicCandidate,
    DEDUP_SIM_THRESHOLD,
    PairResult,
    _atomic_uid,
    _slugify,
    _vault_path_for,
    build_atomic_note,
    call_sonnet_extract,
    check_and_register,
)


install_test_stub()


# ---------------------------------------------------------------------------
# Slug + path helpers
# ---------------------------------------------------------------------------


class TestSlug(unittest.TestCase):

    def test_basic(self):
        self.assertEqual(_slugify("Premature abstraction increases cost"),
                         "premature-abstraction-increases-cost")

    def test_punctuation_stripped(self):
        self.assertEqual(_slugify("AI's Future: Reality"),
                         "ai-s-future-reality")

    def test_max_words(self):
        s = _slugify("This Title Has Many Many Many Many Many Many Words", max_words=4)
        self.assertEqual(s, "this-title-has-many")

    def test_empty(self):
        self.assertEqual(_slugify(""), "untitled")
        self.assertEqual(_slugify("###"), "untitled")


class TestVaultPath(unittest.TestCase):

    def test_year_subfolder(self):
        c = AtomicCandidate(
            title="Climate Bill Passes Senate", note_type="fact", body="-",
            source_side="user", confidence="high",
            cleaned_pair_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="gemini",
            chain_id="", chain_label="",
        )
        path = _vault_path_for(c, vault_root="/v/Engrams/Historical")
        self.assertEqual(str(path),
                         "/v/Engrams/Historical/2025/2025-07-14_climate-bill-passes-senate.md")


# ---------------------------------------------------------------------------
# Note builder
# ---------------------------------------------------------------------------


class TestBuildAtomicNote(unittest.TestCase):

    def test_note_structure(self):
        c = AtomicCandidate(
            title="Premature abstraction increases maintenance cost",
            note_type="causal",
            body="- Abstractions designed before requirements stabilize lock in wrong assumptions\n- Future changes route through the abstraction even when wrong",
            source_side="user", confidence="high",
            cleaned_pair_path="/x.md", pair_num=5,
            when=datetime(2025, 7, 14, 10, 0),
            source_chat="~/Documents/conversations/raw/test.md",
            source_platform="claude", chain_id="chain-abc",
            chain_label="programming",
        )
        body = build_atomic_note(c)
        self.assertIn("type: engram", body)
        self.assertIn("- atomic", body)
        self.assertIn("- causal", body)
        self.assertIn("source_pair_num: 5", body)
        self.assertIn("chain_id: chain-abc", body)
        self.assertIn("source_side: user", body)
        self.assertIn("confidence: high", body)
        self.assertIn("seen_count: 1", body)
        self.assertIn("# Premature abstraction", body)
        self.assertIn("Abstractions designed before requirements stabilize", body)
        self.assertIn("## Source", body)


# ---------------------------------------------------------------------------
# Sonnet extraction (mocked)
# ---------------------------------------------------------------------------


class TestCallSonnetExtract(unittest.TestCase):

    def test_parses_clean_json_array(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text=json.dumps([
                {"title": "X causes Y", "type": "causal",
                 "body": "- X is upstream of Y\n- Y depends on X",
                 "source_side": "user", "confidence": "high"},
            ]),
            input_tokens=200, output_tokens=80, cost_usd=0.001, error="",
        )
        candidates, ti, to, cost, err = call_sonnet_extract(
            "user prompt", "ai response", client=client,
        )
        self.assertEqual(err, "")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "X causes Y")
        self.assertEqual(ti, 200)
        self.assertEqual(to, 80)

    def test_filters_invalid_types(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text=json.dumps([
                {"title": "Valid", "type": "causal", "body": "-",
                 "source_side": "user", "confidence": "high"},
                {"title": "Invalid", "type": "made_up_type", "body": "-",
                 "source_side": "user", "confidence": "high"},
            ]),
            input_tokens=200, output_tokens=80, cost_usd=0.001, error="",
        )
        candidates, _, _, _, err = call_sonnet_extract(
            "u", "a", client=client,
        )
        self.assertEqual(err, "")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "Valid")

    def test_strips_markdown_fences(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text='```json\n[{"title": "T", "type": "fact", "body": "-",\
"source_side": "ai", "confidence": "low"}]\n```',
            input_tokens=200, output_tokens=80, cost_usd=0.001, error="",
        )
        candidates, _, _, _, err = call_sonnet_extract(
            "u", "a", client=client,
        )
        self.assertEqual(err, "")
        self.assertEqual(len(candidates), 1)

    def test_empty_array_means_no_atomics(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text="[]", input_tokens=200, output_tokens=10,
            cost_usd=0.001, error="",
        )
        candidates, _, _, _, err = call_sonnet_extract(
            "u", "a", client=client,
        )
        self.assertEqual(err, "")
        self.assertEqual(candidates, [])

    def test_invalid_json_returns_error(self):
        client = MagicMock()
        client.call.return_value = MagicMock(
            text="not valid", input_tokens=200, output_tokens=10,
            cost_usd=0.001, error="",
        )
        candidates, _, _, _, err = call_sonnet_extract(
            "u", "a", client=client,
        )
        self.assertEqual(candidates, [])
        self.assertIn("json", err)


# ---------------------------------------------------------------------------
# Dedup behavior
# ---------------------------------------------------------------------------


class TestDedup(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        # Create a fresh in-memory chromadb collection
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        self.chroma = chromadb.PersistentClient(path=os.path.join(self.tmp, "cdb"))
        self.col = get_or_create_collection(self.chroma, "atomic_dedup_test")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _candidate(self, title="X causes Y") -> AtomicCandidate:
        return AtomicCandidate(
            title=title, note_type="causal",
            body=f"- {title} body line\n- Supporting detail",
            source_side="user", confidence="high",
            cleaned_pair_path="/x.md", pair_num=1,
            when=datetime(2025, 7, 14),
            source_chat="x", source_platform="claude",
            chain_id="", chain_label="",
        )

    def test_first_candidate_writes_note(self):
        c = self._candidate()
        result, written = check_and_register(
            c, collection=self.col, vault_root=self.vault,
        )
        self.assertFalse(result.is_duplicate)
        self.assertTrue(written)
        self.assertTrue(os.path.exists(written))
        # Collection now has 1 entry.
        self.assertEqual(self.col.count(), 1)

    def test_identical_candidate_dedups(self):
        c1 = self._candidate()
        c2 = self._candidate()  # same title + body → identical embedding
        result1, _ = check_and_register(
            c1, collection=self.col, vault_root=self.vault,
        )
        result2, written2 = check_and_register(
            c2, collection=self.col, vault_root=self.vault,
        )
        self.assertFalse(result1.is_duplicate)
        self.assertTrue(result2.is_duplicate)
        self.assertGreaterEqual(result2.matched_similarity, DEDUP_SIM_THRESHOLD)
        self.assertIsNone(written2)
        # Still one note in the collection (duplicate just bumped seen_count).
        self.assertEqual(self.col.count(), 1)

    def test_different_candidates_both_written(self):
        c1 = self._candidate(title="Climate bill passed Senate")
        c2 = self._candidate(title="Quantum mechanics is non-local")
        result1, w1 = check_and_register(c1, collection=self.col, vault_root=self.vault)
        result2, w2 = check_and_register(c2, collection=self.col, vault_root=self.vault)
        self.assertFalse(result1.is_duplicate)
        self.assertFalse(result2.is_duplicate)
        self.assertTrue(w1)
        self.assertTrue(w2)
        self.assertNotEqual(w1, w2)
        self.assertEqual(self.col.count(), 2)


if __name__ == "__main__":
    unittest.main()
