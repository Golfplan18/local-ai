"""Tests for context header + thread continuity (Phase 1.9)."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import (  # noqa: E402
    Platform,
    RawChat,
    RawChatMetadata,
    RawTurn,
)
from orchestrator.historical.context_header import (  # noqa: E402
    ContextHeader,
    THREAD_OVERLAP_THRESHOLD,
    ThreadTracker,
    build_context_header,
    build_filename,
    build_pair_context,
    build_session_context,
    extract_keywords,
    keyword_set,
)
from orchestrator.historical.pair_cleanup import CleanedPair  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cleaned_pair(pair_num: int,
                        user: str,
                        ai: str,
                        when: datetime) -> CleanedPair:
    return CleanedPair(
        pair_num=pair_num,
        when=when,
        cleaned_user_input=user,
        cleaned_ai_response=ai,
    )


def _make_raw_chat(title: str, n_pairs: int) -> RawChat:
    when = datetime(2025, 7, 14, 21, 0, 0)
    md = RawChatMetadata(
        title=title, platform=Platform.CHATGPT,
        created_at=when, total_messages=n_pairs * 2,
    )
    turns: list[RawTurn] = []
    for i in range(n_pairs):
        turns.append(RawTurn(role="user",
                              content=f"User question {i+1} about quantum mechanics",
                              timestamp=when, raw_text=""))
        turns.append(RawTurn(role="assistant",
                              content=f"Answer {i+1}",
                              timestamp=when, raw_text=""))
    return RawChat(source_path="test.md", metadata=md, turns=turns)


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


class TestKeywords(unittest.TestCase):

    def test_extract_keywords_drops_stopwords(self):
        kws = extract_keywords("the quick brown fox jumps over the lazy dog")
        self.assertNotIn("the", kws)
        self.assertIn("quick", kws)
        self.assertIn("brown", kws)

    def test_extract_keywords_dedupes(self):
        kws = extract_keywords("apple apple apple banana banana")
        self.assertEqual(kws.count("apple"), 1)
        self.assertEqual(kws.count("banana"), 1)

    def test_extract_keywords_max_n(self):
        kws = extract_keywords(
            "alpha beta gamma delta epsilon zeta eta theta", max_n=3,
        )
        self.assertEqual(len(kws), 3)


# ---------------------------------------------------------------------------
# Thread tracker
# ---------------------------------------------------------------------------


class TestThreadTracker(unittest.TestCase):

    def test_first_pair_starts_thread_001(self):
        t = ThreadTracker(conversation_id="conv-1")
        tid = t.assign({"quantum", "mechanics"})
        self.assertTrue(tid.startswith("thread_"))
        self.assertTrue(tid.endswith("_001"))

    def test_same_topic_keeps_thread(self):
        t = ThreadTracker(conversation_id="conv-1")
        tid1 = t.assign({"quantum", "mechanics", "wave"})
        tid2 = t.assign({"quantum", "mechanics", "particle"})
        # ≥30% overlap → same thread.
        self.assertEqual(tid1, tid2)

    def test_topic_shift_advances_thread(self):
        t = ThreadTracker(conversation_id="conv-1")
        tid1 = t.assign({"quantum", "mechanics"})
        tid2 = t.assign({"baking", "bread", "yeast"})
        self.assertNotEqual(tid1, tid2)
        self.assertTrue(tid2.endswith("_002"))

    def test_thread_id_stable_for_same_conversation(self):
        t1 = ThreadTracker(conversation_id="conv-x")
        t2 = ThreadTracker(conversation_id="conv-x")
        a = t1.assign({"a", "b"})
        b = t2.assign({"a", "b"})
        # Same conversation_id + same starting state → same thread id.
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# Filename
# ---------------------------------------------------------------------------


class TestFilename(unittest.TestCase):

    def test_filename_has_date_time_slug(self):
        when = datetime(2025, 7, 14, 21, 5, 0)
        cp = _make_cleaned_pair(1, "Tell me about quantum mechanics", "answer", when)
        f = build_filename(when, cp)
        self.assertTrue(f.startswith("2025-07-14_21-05_"))
        self.assertTrue(f.endswith(".md"))
        self.assertIn("quantum", f)

    def test_filename_fallback_when_empty_user_input(self):
        when = datetime(2025, 1, 1, 0, 0, 0)
        cp = _make_cleaned_pair(1, "", "ok response", when)
        f = build_filename(when, cp)
        self.assertTrue(f.endswith(".md"))


# ---------------------------------------------------------------------------
# Context paragraphs
# ---------------------------------------------------------------------------


class TestSessionContext(unittest.TestCase):

    def test_session_context_includes_title_and_platform(self):
        chat = _make_raw_chat("Quantum Discussion", n_pairs=3)
        text = build_session_context(chat)
        self.assertIn("Quantum Discussion", text)
        self.assertIn("chatgpt", text.lower())
        self.assertIn("3", text)


class TestPairContext(unittest.TestCase):

    def test_first_pair_no_prior(self):
        chat = _make_raw_chat("Test", n_pairs=2)
        when = datetime(2025, 7, 14, 21, 0, 0)
        cp = _make_cleaned_pair(1, "tell me about waves", "ok", when)
        text = build_pair_context(
            chat, pair_index=0, cleaned_pair=cp,
            prior_cleaned_pair=None,
            thread_id="thread_xxx_001",
            is_thread_start=False,
        )
        self.assertIn("Pair 1", text)

    def test_thread_start_text(self):
        chat = _make_raw_chat("Test", n_pairs=2)
        when = datetime(2025, 7, 14, 21, 0, 0)
        prior = _make_cleaned_pair(1, "talk about waves", "ok", when)
        current = _make_cleaned_pair(2, "now baking yeast bread", "ok", when)
        text = build_pair_context(
            chat, pair_index=1, cleaned_pair=current,
            prior_cleaned_pair=prior,
            thread_id="thread_xxx_002",
            is_thread_start=True,
        )
        self.assertIn("new thread", text.lower())

    def test_thread_continuation_text(self):
        chat = _make_raw_chat("Test", n_pairs=2)
        when = datetime(2025, 7, 14, 21, 0, 0)
        prior = _make_cleaned_pair(1, "topic A discussion", "ok", when)
        current = _make_cleaned_pair(2, "more topic A please", "ok", when)
        text = build_pair_context(
            chat, pair_index=1, cleaned_pair=current,
            prior_cleaned_pair=prior,
            thread_id="thread_xxx_001",
            is_thread_start=False,
        )
        self.assertIn("Continues thread", text)


# ---------------------------------------------------------------------------
# Combined header
# ---------------------------------------------------------------------------


class TestBuildContextHeader(unittest.TestCase):

    def test_first_pair_starts_thread(self):
        chat = _make_raw_chat("Quantum Chat", n_pairs=3)
        when = datetime(2025, 7, 14, 21, 0, 0)
        cps = [
            _make_cleaned_pair(1, "Tell me about quantum waves",
                                 "Quantum waves are...", when),
            _make_cleaned_pair(2, "More about quantum waves please",
                                 "Sure, more details on waves...", when),
            _make_cleaned_pair(3, "Now switching to bread baking yeast",
                                 "Baking is...", when),
        ]
        tracker = ThreadTracker(conversation_id="conv-quantum")
        h0 = build_context_header(chat, 0, cps, tracker)
        h1 = build_context_header(chat, 1, cps, tracker)
        h2 = build_context_header(chat, 2, cps, tracker)
        # Pair 1: starts thread 001
        self.assertTrue(h0.thread_id.endswith("_001"))
        # Pair 2: continues thread 001 (high keyword overlap)
        self.assertEqual(h0.thread_id, h1.thread_id)
        # Pair 3: switches to thread 002 (low overlap with bread topic)
        self.assertNotEqual(h1.thread_id, h2.thread_id)
        self.assertTrue(h2.is_thread_start)

    def test_filename_links_set(self):
        chat = _make_raw_chat("Test", n_pairs=3)
        when = datetime(2025, 7, 14, 21, 0, 0)
        cps = [
            _make_cleaned_pair(i + 1, f"input {i+1}", f"response {i+1}", when)
            for i in range(3)
        ]
        tracker = ThreadTracker(conversation_id="conv-x")
        h0 = build_context_header(chat, 0, cps, tracker)
        h1 = build_context_header(chat, 1, cps, tracker)
        h2 = build_context_header(chat, 2, cps, tracker)
        self.assertEqual(h0.prior_pair_file, "")
        self.assertNotEqual(h0.next_pair_file, "")
        self.assertEqual(h0.next_pair_file, h1.pair_filename)
        self.assertEqual(h1.prior_pair_file, h0.pair_filename)
        self.assertEqual(h1.next_pair_file, h2.pair_filename)
        self.assertEqual(h2.next_pair_file, "")


if __name__ == "__main__":
    unittest.main()
