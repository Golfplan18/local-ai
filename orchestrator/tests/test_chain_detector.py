"""Tests for chain detection (Phase 2B).

Verifies:
  - Title-keyword extraction strips platform/date/stop words
  - Topic-fingerprint extraction returns capitalized noun phrases
  - Method 1 (title overlap) links sessions sharing distinctive keywords
  - Method 2 (phrase overlap) links sessions sharing key phrases
  - The two methods compose via union-find into connected components
  - Chain ids are stable across re-runs
  - Singleton sessions still get their own chain
  - Persistence round-trips correctly
"""

from __future__ import annotations

import json
import os
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

from orchestrator.historical.chain_detector import (  # noqa: E402
    Chain,
    Session,
    derive_session_id,
    detect_chains,
    extract_title_keywords,
    extract_session_key_phrases,
    load_chain_index,
    normalize_phrase,
    save_chain_index,
)


def _make_session(
    source_chat: str,
    title_keywords: set[str],
    key_phrases: list[str],
    pair_count: int = 5,
    when: datetime = datetime(2025, 6, 15, 10, 0),
) -> Session:
    sid = derive_session_id(source_chat)
    return Session(
        session_id         = sid,
        source_chat        = source_chat,
        source_platform    = "claude",
        title_keywords     = title_keywords,
        key_phrases        = key_phrases,
        fingerprint        = "|".join(sorted(p.lower() for p in key_phrases)),
        cleaned_pair_paths = [f"/tmp/pair-{i}.md" for i in range(pair_count)],
        first_when         = when,
        last_when          = when,
    )


# ---------------------------------------------------------------------------
# Filename keyword extraction
# ---------------------------------------------------------------------------


class TestTitleKeywordExtraction(unittest.TestCase):

    def test_strips_claude_platform_prefix(self):
        kws = extract_title_keywords("Claude 20260417 American Jesus Outline.md")
        self.assertNotIn("claude", kws)
        self.assertIn("american", kws)
        self.assertIn("jesus", kws)

    def test_strips_chatgpt_platform_prefix(self):
        kws = extract_title_keywords("ChatGPT 20250918 Trumps crap.md")
        self.assertNotIn("chatgpt", kws)
        self.assertIn("trumps", kws)
        self.assertIn("crap", kws)

    def test_strips_date_prefix(self):
        kws = extract_title_keywords("Gemini 20250722 American Jesus.md")
        self.assertNotIn("20250722", kws)
        self.assertIn("american", kws)

    def test_drops_stop_words_and_short_tokens(self):
        # 'and' / 'for' / 'with' / 2-char tokens / 'review' all dropped.
        kws = extract_title_keywords(
            "Claude 20260417 Notes on AI for Claude Code Review.md",
        )
        self.assertNotIn("and", kws)
        self.assertNotIn("for", kws)
        self.assertNotIn("on", kws)
        self.assertNotIn("ai", kws)
        self.assertNotIn("review", kws)
        self.assertIn("notes", kws)

    def test_handles_underscore_and_punctuation(self):
        kws = extract_title_keywords("Some-File_Name (part 1).md")
        self.assertIn("some", kws)
        self.assertIn("file", kws)
        self.assertIn("name", kws)

    def test_empty_input_returns_empty_set(self):
        self.assertEqual(extract_title_keywords(""), set())

    def test_strips_truncation_marker(self):
        # Web Clipper sometimes truncates titles to "...md"
        kws = extract_title_keywords(
            "Claude 20260417 Building an AI swarm system with....md",
        )
        self.assertIn("building", kws)
        self.assertIn("swarm", kws)
        self.assertIn("system", kws)


# ---------------------------------------------------------------------------
# Key-phrase extraction (delegates to vault_indexer.extract_key_phrases)
# ---------------------------------------------------------------------------


class TestKeyPhraseExtraction(unittest.TestCase):

    def test_extracts_capitalized_phrases(self):
        title = "Discussion about American Jesus"
        body  = "We talked about American Jesus and the Bible Quotes for it."
        phrases = extract_session_key_phrases(title, body, max_n=10)
        # 'American Jesus' should appear as a capitalized noun phrase.
        normalized = [normalize_phrase(p) for p in phrases]
        self.assertIn("american jesus", normalized)


# ---------------------------------------------------------------------------
# Method 1 — title-keyword overlap
# ---------------------------------------------------------------------------


class TestMethod1TitleOverlap(unittest.TestCase):

    def test_two_sessions_sharing_two_keywords_chain_together(self):
        s1 = _make_session(
            "Claude 20250722 American Jesus Outline.md",
            title_keywords={"american", "jesus", "outline"},
            key_phrases=[],
        )
        s2 = _make_session(
            "Gemini 20250808 American Jesus Bible Quotes.md",
            title_keywords={"american", "jesus", "bible", "quotes"},
            key_phrases=[],
        )
        chains = detect_chains([s1, s2])
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].session_count, 2)

    def test_two_sessions_sharing_one_keyword_do_not_chain(self):
        # Default threshold is 2 shared title keywords.
        s1 = _make_session(
            "doc-american-history.md",
            title_keywords={"american", "history"},
            key_phrases=[],
        )
        s2 = _make_session(
            "doc-american-cuisine.md",
            title_keywords={"american", "cuisine"},
            key_phrases=[],
        )
        chains = detect_chains([s1, s2])
        # Both should land in their own singleton chains.
        self.assertEqual(len(chains), 2)
        for c in chains:
            self.assertEqual(c.session_count, 1)


# ---------------------------------------------------------------------------
# Method 2 — topic-fingerprint overlap
# ---------------------------------------------------------------------------


class TestMethod2PhraseOverlap(unittest.TestCase):

    def test_two_sessions_sharing_four_phrases_chain_together(self):
        # Default threshold is 4 shared phrases.
        s1 = _make_session(
            "doc-a.md",
            title_keywords={"random"},  # no title overlap
            key_phrases=["American Jesus", "Diklis Chump", "Bible Quotes",
                         "Mark Sabbath", "Other Phrase A"],
        )
        s2 = _make_session(
            "doc-b.md",
            title_keywords={"different"},
            key_phrases=["American Jesus", "Diklis Chump", "Bible Quotes",
                         "Mark Sabbath", "Other Phrase B"],
        )
        chains = detect_chains([s1, s2])
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].session_count, 2)

    def test_two_sessions_sharing_three_phrases_do_not_chain(self):
        # Default threshold is 4 shared phrases — 3 is below it.
        s1 = _make_session(
            "doc-a.md",
            title_keywords={"x"},
            key_phrases=["American Jesus", "Diklis Chump", "Bible Quotes",
                         "Other A"],
        )
        s2 = _make_session(
            "doc-b.md",
            title_keywords={"y"},
            key_phrases=["American Jesus", "Diklis Chump", "Bible Quotes",
                         "Other B"],
        )
        chains = detect_chains([s1, s2])
        self.assertEqual(len(chains), 2)


# ---------------------------------------------------------------------------
# Composition — methods 1+2 combined via union-find
# ---------------------------------------------------------------------------


class TestComposition(unittest.TestCase):

    def test_three_sessions_chain_via_transitive_links(self):
        # A links to B via title; B links to C via phrases; therefore
        # A, B, C are all in the same chain. Phrase threshold is 4.
        a = _make_session(
            "American Jesus Notes.md",
            title_keywords={"american", "jesus", "notes"},
            key_phrases=["American Jesus", "Outline"],
        )
        b = _make_session(
            "American Jesus More.md",
            title_keywords={"american", "jesus", "more"},
            key_phrases=["American Jesus", "Diklis Chump",
                         "Bible Quotes", "Parable Placement",
                         "Mark Sabbath"],
        )
        c = _make_session(
            "Diklis Chump Stuff.md",
            title_keywords={"diklis", "chump", "stuff"},
            key_phrases=["Diklis Chump", "Bible Quotes",
                         "Parable Placement", "Mark Sabbath",
                         "Other Phrase"],
        )
        chains = detect_chains([a, b, c])
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].session_count, 3)


# ---------------------------------------------------------------------------
# Singletons — sessions with no edges still get a chain
# ---------------------------------------------------------------------------


class TestSingletons(unittest.TestCase):

    def test_orphan_session_gets_own_chain(self):
        s = _make_session(
            "Standalone Topic.md",
            title_keywords={"standalone", "topic"},
            key_phrases=["Standalone", "Topic"],
        )
        chains = detect_chains([s])
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].session_count, 1)
        self.assertEqual(chains[0].session_ids, [s.session_id])

    def test_empty_session_list_returns_empty_chains(self):
        self.assertEqual(detect_chains([]), [])


# ---------------------------------------------------------------------------
# Stability — ids must be reproducible across runs
# ---------------------------------------------------------------------------


class TestStability(unittest.TestCase):

    def test_chain_id_stable_across_reordering(self):
        s1 = _make_session(
            "American Jesus Notes.md",
            title_keywords={"american", "jesus", "notes"},
            key_phrases=["American Jesus"],
        )
        s2 = _make_session(
            "American Jesus More.md",
            title_keywords={"american", "jesus", "more"},
            key_phrases=["American Jesus"],
        )
        chains_a = detect_chains([s1, s2])
        chains_b = detect_chains([s2, s1])  # reversed input order
        self.assertEqual(chains_a[0].chain_id, chains_b[0].chain_id)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence(unittest.TestCase):

    def test_save_and_load_roundtrip(self):
        s1 = _make_session(
            "American Jesus Notes.md",
            title_keywords={"american", "jesus", "notes"},
            key_phrases=["American Jesus"],
        )
        s2 = _make_session(
            "American Jesus More.md",
            title_keywords={"american", "jesus", "more"},
            key_phrases=["American Jesus"],
        )
        chains = detect_chains([s1, s2])
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_chain_index(chains, [s1, s2], path=path)
            loaded = load_chain_index(path)
            self.assertEqual(loaded["session_count"], 2)
            self.assertEqual(loaded["chain_count"], 1)
            self.assertEqual(len(loaded["chains"]), 1)
            # session_to_chain lookup table is populated for both sessions.
            self.assertIn(s1.session_id, loaded["session_to_chain"])
            self.assertIn(s2.session_id, loaded["session_to_chain"])
            self.assertEqual(
                loaded["session_to_chain"][s1.session_id],
                loaded["session_to_chain"][s2.session_id],
            )
        finally:
            os.unlink(path)

    def test_load_missing_file_returns_empty_index(self):
        empty = load_chain_index("/nonexistent/path/chain-index.json")
        self.assertEqual(empty["session_count"], 0)
        self.assertEqual(empty["chain_count"], 0)


# ---------------------------------------------------------------------------
# Chain label heuristic
# ---------------------------------------------------------------------------


class TestChainLabel(unittest.TestCase):

    def test_label_picks_most_common_shared_term(self):
        s1 = _make_session(
            "American Jesus Notes.md",
            title_keywords={"american", "jesus", "notes"},
            key_phrases=["American Jesus"],
        )
        s2 = _make_session(
            "American Jesus Outline.md",
            title_keywords={"american", "jesus", "outline"},
            key_phrases=["American Jesus"],
        )
        chains = detect_chains([s1, s2])
        # "american" or "jesus" or "american jesus" — any of these would
        # be reasonable, but it must NOT be a session-unique term.
        self.assertIn(chains[0].chain_label,
                      {"american", "jesus", "american jesus"})


if __name__ == "__main__":
    unittest.main()
