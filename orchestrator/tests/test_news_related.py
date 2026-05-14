#!/usr/bin/env python3
"""Tests for news_related.py — three-signal news-to-news related-article retrieval."""
from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCHESTRATOR))

from orchestrator import embedding, news_related  # noqa: E402
from orchestrator.news_related import (  # noqa: E402
    Related,
    _display_score,
    _maybe_arbitrate,
    _parse_iso_date,
    _recency_factor,
    _signal_cluster_match,
    _signal_semantic_match,
    find_related_news,
)


# ---------------------------------------------------------------------------
# Pure-Python unit tests (no chromadb required)
# ---------------------------------------------------------------------------


class TestRecencyFactor(unittest.TestCase):

    def test_same_day(self):
        self.assertAlmostEqual(_recency_factor("2026-05-14", date(2026, 5, 14)), 1.0)

    def test_60_days_old_is_half(self):
        # half-life is 60 days
        f = _recency_factor("2026-03-15", date(2026, 5, 14))
        self.assertAlmostEqual(f, math.exp(-1.0), places=4)

    def test_unparseable_date(self):
        self.assertEqual(_recency_factor("not-a-date", date(2026, 5, 14)), 0.0)

    def test_future_date_clamped(self):
        # Future dates should not boost recency above 1.0.
        f = _recency_factor("2026-06-14", date(2026, 5, 14))
        self.assertEqual(f, 1.0)


class TestDisplayScore(unittest.TestCase):

    def test_continues_dominates_via_strength(self):
        # Strength 1.0 (continues) on an old article should still beat
        # strength 0.6 (related) on a fresh article when reference is the
        # candidate's date.
        ref = date(2026, 5, 14)
        s_old_continues = _display_score(1.0, "2026-01-01", ref)
        s_new_related = _display_score(0.6, "2026-05-14", ref)
        self.assertGreater(s_old_continues, s_new_related)


class TestParseISODate(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(_parse_iso_date("2026-05-14"), date(2026, 5, 14))

    def test_with_tail(self):
        self.assertEqual(_parse_iso_date("2026-05-14T12:00:00"), date(2026, 5, 14))

    def test_invalid(self):
        self.assertIsNone(_parse_iso_date("nope"))

    def test_empty(self):
        self.assertIsNone(_parse_iso_date(""))


# ---------------------------------------------------------------------------
# Arbitration
# ---------------------------------------------------------------------------


class TestArbitration(unittest.TestCase):

    def test_promotes_high_similarity_to_continues(self):
        cluster_matches = []  # cluster_id miss
        sem_matches = [Related(
            slug="prior", headline="Prior story",
            publish_date="2026-05-13",
            relation="related", strength=0.92, display_score=0.7,
        )]

        def arbiter(_a, _b):
            return "continues"

        out = _maybe_arbitrate(cluster_matches, sem_matches, {}, arbiter=arbiter)
        self.assertEqual(out[0].relation, "continues")

    def test_no_op_when_arbiter_returns_related(self):
        sem_matches = [Related(
            slug="prior", headline="P", publish_date="2026-05-13",
            relation="related", strength=0.92, display_score=0.7,
        )]
        out = _maybe_arbitrate([], sem_matches, {}, arbiter=lambda a, b: "related")
        self.assertEqual(out[0].relation, "related")

    def test_no_op_below_arbitration_threshold(self):
        sem_matches = [Related(
            slug="prior", headline="P", publish_date="2026-05-13",
            relation="related", strength=0.6, display_score=0.5,
        )]
        # arbiter would have promoted, but strength 0.6 < arbitration threshold 0.85
        out = _maybe_arbitrate([], sem_matches, {}, arbiter=lambda a, b: "continues")
        self.assertEqual(out[0].relation, "related")

    def test_no_op_when_already_in_cluster_matches(self):
        cluster = [Related(
            slug="prior", headline="P", publish_date="2026-05-13",
            relation="continues", strength=1.0, display_score=0.9,
        )]
        sem = [Related(
            slug="prior", headline="P", publish_date="2026-05-13",
            relation="related", strength=0.9, display_score=0.65,
        )]
        # Arbiter shouldn't be called; the slug already in cluster_matches.
        out = _maybe_arbitrate(cluster, sem, {}, arbiter=lambda a, b: "related")
        self.assertEqual(out[0].relation, "related")  # unchanged

    def test_arbiter_exception_falls_through(self):
        sem = [Related(
            slug="prior", headline="P", publish_date="2026-05-13",
            relation="related", strength=0.92, display_score=0.7,
        )]
        def crashing_arbiter(_a, _b):
            raise RuntimeError("model unreachable")
        # Should not raise; original record returned.
        out = _maybe_arbitrate([], sem, {}, arbiter=crashing_arbiter)
        self.assertEqual(out[0].relation, "related")

    def test_no_arbiter_is_noop(self):
        sem = [Related(
            slug="prior", headline="P", publish_date="2026-05-13",
            relation="related", strength=0.99, display_score=0.85,
        )]
        out = _maybe_arbitrate([], sem, {}, arbiter=None)
        self.assertEqual(out[0].relation, "related")


# ---------------------------------------------------------------------------
# Related dataclass / frontmatter shape
# ---------------------------------------------------------------------------


class TestRelatedFrontmatterShape(unittest.TestCase):

    def test_as_frontmatter_entry(self):
        r = Related(
            slug="2026-05-13-foo", headline="Foo", publish_date="2026-05-13",
            relation="continues", strength=0.999, display_score=0.7,
        )
        entry = r.as_frontmatter_entry()
        self.assertEqual(set(entry.keys()), {"slug", "headline", "publish_date", "relation", "strength"})
        self.assertEqual(entry["relation"], "continues")
        self.assertEqual(entry["strength"], 0.999)

    def test_strength_rounded(self):
        r = Related(
            slug="x", headline="X", publish_date="2026-05-14",
            relation="related", strength=0.123456789, display_score=0.5,
        )
        self.assertEqual(r.as_frontmatter_entry()["strength"], 0.1235)


# ---------------------------------------------------------------------------
# Integration tests with a real (in-memory) ChromaDB collection
# ---------------------------------------------------------------------------


def _make_meta(*, slug: str, source_cluster_id: str, headline: str,
               publish_date: str, lede: str = ""):
    return {
        "path": f"/fake/{slug}.md",
        "slug": slug,
        "source_cluster_id": source_cluster_id,
        "headline": headline,
        "publish_date": publish_date,
        "lede_excerpt": lede,
    }


class TestSignalsAgainstChromaDB(unittest.TestCase):
    """Build a tiny in-memory collection, exercise signals individually."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="news_related_test_")
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        os.makedirs(self.chromadb_path, exist_ok=True)

        embedding.install_test_stub()

        import chromadb
        from orchestrator.embedding import get_or_create_collection
        self.client = chromadb.PersistentClient(path=self.chromadb_path)
        self.col = get_or_create_collection(self.client, "msi_news_articles_test")

    def tearDown(self):
        embedding.uninstall_test_stub()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _add(self, slug, source_cluster_id, headline, publish_date, body):
        self.col.add(
            ids=[f"/fake/{slug}.md"],
            documents=[body],
            metadatas=[_make_meta(
                slug=slug, source_cluster_id=source_cluster_id,
                headline=headline, publish_date=publish_date,
            )],
        )

    def test_signal_cluster_match_returns_continues(self):
        self._add("a", "C1", "First piece", "2026-05-12", "first body")
        self._add("b", "C1", "Second piece", "2026-05-13", "second body")
        self._add("c", "C2", "Unrelated", "2026-05-14", "unrelated body")

        out = _signal_cluster_match(self.col, "C1", candidate_slug=None,
                                     reference_date=date(2026, 5, 14))
        slugs = sorted(r.slug for r in out)
        self.assertEqual(slugs, ["a", "b"])
        for r in out:
            self.assertEqual(r.relation, "continues")
            self.assertEqual(r.strength, 1.0)

    def test_signal_cluster_match_self_excluded(self):
        self._add("a", "C1", "Self", "2026-05-14", "self body")
        self._add("b", "C1", "Other", "2026-05-12", "other body")

        out = _signal_cluster_match(self.col, "C1", candidate_slug="a",
                                     reference_date=date(2026, 5, 14))
        self.assertEqual([r.slug for r in out], ["b"])

    def test_signal_cluster_match_empty_when_no_id(self):
        self._add("a", "C1", "x", "2026-05-14", "x")
        out = _signal_cluster_match(self.col, "", candidate_slug=None,
                                     reference_date=date(2026, 5, 14))
        self.assertEqual(out, [])

    def test_signal_semantic_match_returns_high_similarity_match(self):
        # The deterministic SHA256 stub returns identical vectors for identical text.
        # Querying with the same exact text as a stored doc should yield cosine=1.0.
        self._add("a", "C1", "Apple text", "2026-05-13", "apple banana cherry text content")
        self._add("b", "C2", "Banana text", "2026-05-14", "totally different content unrelated entirely")

        out = _signal_semantic_match(
            self.col, "apple banana cherry text content",
            candidate_slug=None, reference_date=date(2026, 5, 14),
            top_n=10,
        )
        # Doc 'a' should be the closest cosine match (identical text).
        slugs = [r.slug for r in out]
        self.assertEqual(slugs[0], "a")
        # Strength is cosine similarity in [0, 1].
        self.assertGreater(out[0].strength, 0.99)
        for r in out:
            self.assertEqual(r.relation, "related")

    def test_signal_semantic_match_self_excluded(self):
        self._add("a", "C1", "h", "2026-05-14", "the candidate's own body content")
        self._add("b", "C2", "h2", "2026-05-13", "the candidate's own body content")

        out = _signal_semantic_match(
            self.col, "the candidate's own body content",
            candidate_slug="a", reference_date=date(2026, 5, 14),
            top_n=10,
        )
        slugs = [r.slug for r in out]
        self.assertNotIn("a", slugs)

    def test_signal_semantic_match_empty_query_returns_empty(self):
        self._add("a", "C1", "x", "2026-05-14", "x")
        out = _signal_semantic_match(
            self.col, "", candidate_slug=None,
            reference_date=date(2026, 5, 14), top_n=10,
        )
        self.assertEqual(out, [])


class TestFindRelatedNews(unittest.TestCase):
    """End-to-end find_related_news with all signals composed."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="news_related_test_")
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        os.makedirs(self.chromadb_path, exist_ok=True)

        embedding.install_test_stub()

        import chromadb
        from orchestrator.embedding import get_or_create_collection
        self.client = chromadb.PersistentClient(path=self.chromadb_path)
        self.col = get_or_create_collection(self.client, "msi_news_articles_test")

    def tearDown(self):
        embedding.uninstall_test_stub()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _add(self, slug, source_cluster_id, headline, publish_date, body):
        self.col.add(
            ids=[f"/fake/{slug}.md"],
            documents=[body],
            metadatas=[_make_meta(
                slug=slug, source_cluster_id=source_cluster_id,
                headline=headline, publish_date=publish_date,
            )],
        )

    def test_empty_corpus_returns_empty_list(self):
        out = find_related_news(
            candidate_slug="any", source_cluster_id="C1",
            headline="h", lede="l", nut_graf="n", body="b",
            publish_date="2026-05-14", collection=self.col,
        )
        self.assertEqual(out, [])

    def test_cluster_match_only(self):
        self._add("prior-1", "C1", "Earlier piece in chain", "2026-05-12",
                  "totally different content from candidate")
        self._add("unrelated", "C2", "Unrelated piece", "2026-05-13",
                  "noise noise noise different vocabulary")

        out = find_related_news(
            candidate_slug="now", source_cluster_id="C1",
            headline="x y z", lede="", nut_graf="", body="",
            publish_date="2026-05-14", collection=self.col,
        )
        slugs = [r.slug for r in out]
        self.assertIn("prior-1", slugs)
        # 'unrelated' might or might not appear via semantic; that's fine.
        prior = next(r for r in out if r.slug == "prior-1")
        self.assertEqual(prior.relation, "continues")
        self.assertEqual(prior.strength, 1.0)

    def test_continues_groups_before_related(self):
        self._add("prior-continues", "C1", "Same chain", "2026-05-13",
                  "completely different vocabulary apple banana")
        self._add("prior-related", "C2", "Related piece", "2026-05-13",
                  "the exact candidate query body content here")

        out = find_related_news(
            candidate_slug="now", source_cluster_id="C1",
            headline="the exact candidate query body content here",
            lede="", nut_graf="", body="",
            publish_date="2026-05-14", collection=self.col,
        )
        slugs = [r.slug for r in out]
        # continues group always comes before related group.
        self.assertEqual(slugs[0], "prior-continues")
        # 'prior-related' may surface via semantic match; if so it's after continues.
        if "prior-related" in slugs:
            self.assertLess(slugs.index("prior-continues"), slugs.index("prior-related"))

    def test_dedup_continues_wins_over_related(self):
        # Same article surfaced by BOTH cluster_id and semantic similarity.
        # Continues should win; the result should appear only once.
        self._add("dual", "C1", "Dual signal piece", "2026-05-13",
                  "the exact candidate query body content")

        out = find_related_news(
            candidate_slug="now", source_cluster_id="C1",
            headline="the exact candidate query body content",
            lede="", nut_graf="", body="",
            publish_date="2026-05-14", collection=self.col,
        )
        slugs = [r.slug for r in out]
        self.assertEqual(slugs.count("dual"), 1)
        dual = next(r for r in out if r.slug == "dual")
        self.assertEqual(dual.relation, "continues")
        self.assertEqual(dual.strength, 1.0)

    def test_self_excluded_across_signals(self):
        self._add("self", "C1", "Self piece", "2026-05-14",
                  "the candidate's own body content")
        self._add("other", "C1", "Other in same cluster", "2026-05-13",
                  "different vocabulary entirely")

        out = find_related_news(
            candidate_slug="self", source_cluster_id="C1",
            headline="the candidate's own body content",
            lede="", nut_graf="", body="",
            publish_date="2026-05-14", collection=self.col,
        )
        slugs = [r.slug for r in out]
        self.assertNotIn("self", slugs)
        self.assertIn("other", slugs)

    def test_top_n_caps_results(self):
        for i in range(15):
            self._add(f"art-{i}", "C1", f"Article {i}", "2026-05-13",
                      f"body-{i} the exact candidate query body content")

        out = find_related_news(
            candidate_slug="now", source_cluster_id="C1",
            headline="the exact candidate query body content",
            lede="", nut_graf="", body="",
            publish_date="2026-05-14", collection=self.col,
            top_n=5,
        )
        self.assertLessEqual(len(out), 5)


if __name__ == "__main__":
    unittest.main()
