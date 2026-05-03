"""Tests for the Phase 5.6 ranker additions to orchestrator/rag_engine.py.

Per Reference — Ora YAML Schema §4 + §5 + §6 + §15 (rev 3, 2026-04-30):

    score = similarity × type_weight × recency_factor

For external (live web) chunks the cascade is:
    score = similarity × EXTERNAL_WEIGHTS[classify_web_source(url, ...)]

The new ranker replaces the positional five-bucket priority stack with
a unified type-weighted ranking. Results are formatted with provenance
markers — each chunk's source line carries `[type: ... | weight: ... |
source: ...]` so downstream consumers see the ranking decision.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import rag_engine  # noqa: E402
from tools import web_corroboration  # noqa: E402

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


def _vault_chunk(chunk_type, similarity, *, source="x.md", topic=None, ts=None,
                 document="body"):
    return {
        "id":         f"id_{source}",
        "document":   document,
        "similarity": similarity,
        "metadata":   {
            "type":          chunk_type,
            "source":        source,
            "topic_primary": topic,
            "timestamp_utc": ts,
        },
    }


def _external_chunk(url, similarity, *, document="external body"):
    return {
        "id":         f"ext_{url}",
        "url":        url,
        "document":   document,
        "similarity": similarity,
        "metadata":   {"source": url},
    }


# ---------------------------------------------------------------------------
# rank_vault_chunks — type weight × recency × similarity
# ---------------------------------------------------------------------------


class TestRankVaultChunks(unittest.TestCase):
    """The core ranker: similarity × type_weight × recency_factor."""

    def test_engram_outranks_resource_at_equal_similarity(self):
        # Schema §4: engram weight 1.0, resource weight 0.7. With no
        # decay applied (no topic_primary), score is just similarity ×
        # type_weight.
        engram = _vault_chunk("engram",   similarity=0.5, source="engram.md")
        resource = _vault_chunk("resource", similarity=0.5, source="resource.md")
        ranked = rag_engine.rank_vault_chunks([engram, resource])
        self.assertEqual(ranked[0]["metadata"]["source"], "engram.md")
        self.assertEqual(ranked[1]["metadata"]["source"], "resource.md")
        self.assertAlmostEqual(ranked[0]["score"], 0.5, places=6)
        self.assertAlmostEqual(ranked[1]["score"], 0.35, places=6)

    def test_engram_outranks_chat_at_equal_similarity(self):
        engram = _vault_chunk("engram", similarity=0.5, source="engram.md")
        chat   = _vault_chunk("chat",   similarity=0.5, source="chat.md")
        ranked = rag_engine.rank_vault_chunks([engram, chat])
        self.assertEqual(ranked[0]["metadata"]["source"], "engram.md")

    def test_high_similarity_resource_can_outrank_low_similarity_engram(self):
        # Score is multiplicative, not lexicographic — a resource with
        # much higher similarity should beat a marginal engram.
        engram   = _vault_chunk("engram",   similarity=0.10, source="weak_engram.md")
        resource = _vault_chunk("resource", similarity=0.95, source="strong_resource.md")
        ranked = rag_engine.rank_vault_chunks([engram, resource])
        # 0.95 × 0.7 = 0.665; 0.10 × 1.0 = 0.10
        self.assertEqual(ranked[0]["metadata"]["source"], "strong_resource.md")

    def test_chat_in_active_cluster_decays(self):
        # Conv RAG §4 worked example: chat with 10 newer in-cluster
        # chunks decays to factor 0.5. score = sim × 0.3 × 0.5
        target = _vault_chunk(
            "chat", similarity=1.0,
            source="old_chat.md",
            topic="consciousness", ts="2024-01-01T00:00:00Z",
        )
        newer = [
            _vault_chunk(
                "chat", similarity=0.8,
                source=f"newer_{i}.md",
                topic="consciousness",
                ts=f"2026-04-{i:02d}T10:00:00Z",
            )
            for i in range(1, 11)
        ]
        ranked = rag_engine.rank_vault_chunks([target] + newer)
        target_scored = next(c for c in ranked if c["metadata"]["source"] == "old_chat.md")
        # 1.0 × 0.3 × 0.5 = 0.15
        self.assertAlmostEqual(target_scored["score"], 0.15, places=6)
        self.assertAlmostEqual(target_scored["recency"], 0.5, places=6)
        self.assertAlmostEqual(target_scored["weight"], 0.3, places=6)

    def test_chat_in_busy_cluster_decays_to_floor(self):
        target = _vault_chunk(
            "chat", similarity=1.0,
            source="old_chat.md",
            topic="topic-x", ts="2024-01-01T00:00:00Z",
        )
        # 30 newer in cluster — far past the floor cutoff.
        newer = [
            _vault_chunk(
                "chat", similarity=0.5,
                source=f"newer_{i}.md", topic="topic-x",
                ts=f"2026-04-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
            )
            for i in range(30)
        ]
        ranked = rag_engine.rank_vault_chunks([target] + newer)
        target_scored = next(c for c in ranked if c["metadata"]["source"] == "old_chat.md")
        # Floor is 0.2; score = 1.0 × 0.3 × 0.2 = 0.06
        self.assertAlmostEqual(target_scored["recency"], 0.2, places=6)
        self.assertAlmostEqual(target_scored["score"], 0.06, places=6)

    def test_engram_same_age_as_decaying_chat_retains_full_weight(self):
        # Engrams are decay-ineligible: even with 10 newer in-cluster
        # chunks, the engram doesn't decay.
        engram = _vault_chunk(
            "engram", similarity=1.0,
            source="ancient_engram.md",
            topic="topic-x", ts="2024-01-01T00:00:00Z",
        )
        chat = _vault_chunk(
            "chat", similarity=1.0,
            source="ancient_chat.md",
            topic="topic-x", ts="2024-01-01T00:00:00Z",
        )
        newer_chats = [
            _vault_chunk(
                "chat", similarity=0.5,
                source=f"newer_{i}.md", topic="topic-x",
                ts=f"2026-04-{i:02d}T10:00:00Z",
            )
            for i in range(1, 11)
        ]
        ranked = rag_engine.rank_vault_chunks([engram, chat] + newer_chats)
        engram_scored = next(c for c in ranked if c["metadata"]["source"] == "ancient_engram.md")
        chat_scored   = next(c for c in ranked if c["metadata"]["source"] == "ancient_chat.md")

        self.assertEqual(engram_scored["recency"], 1.0)  # no decay
        self.assertEqual(engram_scored["score"], 1.0)
        self.assertAlmostEqual(chat_scored["recency"], 0.5, places=6)
        self.assertAlmostEqual(chat_scored["score"], 0.15, places=6)

    def test_matrix_chunks_dropped(self):
        engram = _vault_chunk("engram", similarity=0.5, source="engram.md")
        matrix = _vault_chunk("matrix", similarity=0.99, source="matrix.md")
        ranked = rag_engine.rank_vault_chunks([engram, matrix])
        sources = [c["metadata"]["source"] for c in ranked]
        self.assertIn("engram.md", sources)
        self.assertNotIn("matrix.md", sources)

    def test_supervision_chunks_dropped(self):
        engram      = _vault_chunk("engram",      similarity=0.5, source="engram.md")
        supervision = _vault_chunk("supervision", similarity=0.99, source="claude_md.md")
        ranked = rag_engine.rank_vault_chunks([engram, supervision])
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["metadata"]["source"], "engram.md")

    def test_unknown_type_dropped(self):
        engram  = _vault_chunk("engram",        similarity=0.5, source="engram.md")
        unknown = _vault_chunk("nonexistent",   similarity=0.99, source="bad.md")
        ranked = rag_engine.rank_vault_chunks([engram, unknown])
        sources = [c["metadata"]["source"] for c in ranked]
        self.assertNotIn("bad.md", sources)

    def test_ranked_descending(self):
        chunks = [
            _vault_chunk("chat",     similarity=0.9, source="a.md"),
            _vault_chunk("engram",   similarity=0.5, source="b.md"),
            _vault_chunk("resource", similarity=0.7, source="c.md"),
        ]
        ranked = rag_engine.rank_vault_chunks(chunks)
        scores = [c["score"] for c in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_score_weight_recency_fields_present(self):
        chunk = _vault_chunk("engram", similarity=0.5, source="x.md")
        ranked = rag_engine.rank_vault_chunks([chunk])
        self.assertIn("score",   ranked[0])
        self.assertIn("weight",  ranked[0])
        self.assertIn("recency", ranked[0])


# ---------------------------------------------------------------------------
# External tier scoring
# ---------------------------------------------------------------------------


class TestScoreExternalChunks(unittest.TestCase):
    """External (live web) chunks use EXTERNAL_WEIGHTS classification."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        path = os.path.join(self.tmpdir, "trusted.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("""## High Provenance

```
arxiv.org/abs/*
pubmed.ncbi.nlm.nih.gov/*
```

## Medium Provenance

```
bbc.com/news/*
```

## Excluded

```
*.medium.com/*
```
""")
        self.registry = web_corroboration.TrustedSourcesRegistry(path)

    def test_whitelisted_external(self):
        chunk = _external_chunk("https://arxiv.org/abs/2401.00001", similarity=0.5)
        scored = rag_engine.score_external_chunks(
            [chunk], all_urls=[chunk["url"]], registry=self.registry,
        )
        self.assertEqual(scored[0]["classification"], "whitelisted")
        self.assertAlmostEqual(scored[0]["weight"], 0.7, places=6)
        # 0.5 × 0.7 = 0.35
        self.assertAlmostEqual(scored[0]["score"], 0.35, places=6)

    def test_corroborated_external(self):
        chunk = _external_chunk("https://bbc.com/news/world", similarity=0.5)
        scored = rag_engine.score_external_chunks(
            [chunk], all_urls=[chunk["url"]], registry=self.registry,
        )
        self.assertEqual(scored[0]["classification"], "corroborated")
        self.assertAlmostEqual(scored[0]["weight"], 0.3, places=6)
        self.assertAlmostEqual(scored[0]["score"], 0.15, places=6)

    def test_single_external(self):
        chunk = _external_chunk("https://random.example.com/article", similarity=0.5)
        scored = rag_engine.score_external_chunks(
            [chunk], all_urls=[chunk["url"]], registry=self.registry,
        )
        self.assertEqual(scored[0]["classification"], "single")
        self.assertAlmostEqual(scored[0]["weight"], 0.15, places=6)

    def test_excluded_external_dropped(self):
        chunk = _external_chunk("https://user.medium.com/article", similarity=0.99)
        scored = rag_engine.score_external_chunks(
            [chunk], all_urls=[chunk["url"]], registry=self.registry,
        )
        # Excluded → dropped from the ranked list (weight 0.0).
        self.assertEqual(scored, [])

    def test_external_chunks_sorted_descending(self):
        chunks = [
            _external_chunk("https://random.com/a", similarity=0.99),    # single, 0.15
            _external_chunk("https://arxiv.org/abs/x", similarity=0.30), # whitelisted, 0.7
        ]
        scored = rag_engine.score_external_chunks(
            chunks, all_urls=[c["url"] for c in chunks], registry=self.registry,
        )
        # 0.30 × 0.7 = 0.21 vs 0.99 × 0.15 = 0.1485
        self.assertEqual(scored[0]["url"], "https://arxiv.org/abs/x")


# ---------------------------------------------------------------------------
# Provenance-marker formatting
# ---------------------------------------------------------------------------


class TestFormatContextWithProvenance(unittest.TestCase):
    """Formatted output carries provenance markers per the handoff."""

    def test_marker_format(self):
        chunks = [{
            "id":         "id_x",
            "document":   "Body of the engram chunk.",
            "metadata":   {"type": "engram", "source": "engram_active.md"},
            "score":      1.0,
            "weight":     1.0,
            "recency":    1.0,
        }]
        out = rag_engine.format_context_with_provenance(chunks)
        self.assertIn("[type: engram", out)
        self.assertIn("weight: 1.0", out)
        self.assertIn("source: engram_active.md", out)
        self.assertIn("Body of the engram chunk.", out)

    def test_multiple_chunks_each_have_markers(self):
        chunks = [
            {
                "id": "1", "document": "First.",
                "metadata": {"type": "engram", "source": "a.md"},
                "score": 1.0, "weight": 1.0, "recency": 1.0,
            },
            {
                "id": "2", "document": "Second.",
                "metadata": {"type": "resource", "source": "b.md"},
                "score": 0.5, "weight": 0.7, "recency": 1.0,
            },
        ]
        out = rag_engine.format_context_with_provenance(chunks)
        self.assertIn("a.md", out)
        self.assertIn("b.md", out)
        # Each marker line appears once
        self.assertEqual(out.count("[type: engram"), 1)
        self.assertEqual(out.count("[type: resource"), 1)

    def test_external_classification_marker(self):
        # External chunks have classification + weight, no decay.
        chunks = [{
            "id": "ext1", "document": "From the web.",
            "url": "https://arxiv.org/abs/x",
            "metadata": {"source": "https://arxiv.org/abs/x"},
            "classification": "whitelisted",
            "score": 0.35, "weight": 0.7,
        }]
        out = rag_engine.format_context_with_provenance(chunks)
        self.assertIn("classification: whitelisted", out)
        self.assertIn("source: https://arxiv.org/abs/x", out)

    def test_max_chars_truncates_at_boundary(self):
        # Each chunk is ~100 chars body + ~50 char marker. With max_chars=500
        # we expect ~3-4 chunks before the budget cuts off the rest.
        chunks = [{
            "id": str(i),
            "document": "X" * 100,
            "metadata": {"type": "engram", "source": f"chunk_{i}.md"},
            "score": 1.0, "weight": 1.0, "recency": 1.0,
        } for i in range(20)]
        out = rag_engine.format_context_with_provenance(chunks, max_chars=500)
        # All 20 chunks would be ~3000 chars total; truncation kicks in.
        self.assertLess(len(out), 700)
        # But the top chunk (chunk_0) is always included.
        self.assertIn("chunk_0.md", out)
        # The last chunk should not have made it.
        self.assertNotIn("chunk_19.md", out)

    def test_top_chunk_always_included_even_when_oversized(self):
        # If the first chunk alone exceeds budget, we still include it
        # (callers shouldn't get an empty result when they have content).
        chunks = [{
            "id": "0",
            "document": "X" * 5000,
            "metadata": {"type": "engram", "source": "huge.md"},
            "score": 1.0, "weight": 1.0, "recency": 1.0,
        }]
        out = rag_engine.format_context_with_provenance(chunks, max_chars=500)
        self.assertIn("huge.md", out)

    def test_empty_input(self):
        self.assertEqual(rag_engine.format_context_with_provenance([]), "")


# ---------------------------------------------------------------------------
# End-to-end: type_filter excludes specified types
# ---------------------------------------------------------------------------


class TestAssembleRankedContextEndToEnd(unittest.TestCase):
    """End-to-end: query → rank → format with type_filter applied at search."""

    def setUp(self):
        from tools import knowledge_search
        self.tmpdir = tempfile.mkdtemp()
        self.chromadb_path = os.path.join(self.tmpdir, "chromadb")
        self._original = knowledge_search.CHROMADB_PATH
        knowledge_search.CHROMADB_PATH = self.chromadb_path

        import chromadb
        from orchestrator.embedding import get_or_create_collection as _bind_ef
        client = chromadb.PersistentClient(path=self.chromadb_path)
        col = _bind_ef(client, "knowledge")
        col.add(
            ids=["k_engram", "k_chat", "k_framework", "k_resource"],
            documents=[
                "Engram about consciousness — vetted user position.",
                "Chat about consciousness from last week.",
                "Framework for processing documents.",
                "Resource chunk about epistemology.",
            ],
            metadatas=[
                {"type": "engram",    "source": "engram.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "chat",      "source": "chat.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "framework", "source": "framework.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
                {"type": "resource",  "source": "resource.md",
                 "tag_archived": False, "tag_incubating": False, "tag_private": False},
            ],
        )

    def tearDown(self):
        from tools import knowledge_search
        knowledge_search.CHROMADB_PATH = self._original
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_type_filter_framework_only(self):
        # Mode with type_filter: [framework] returns no engrams or chats.
        out = rag_engine.assemble_ranked_context(
            query="consciousness epistemology framework",
            type_filter=["framework"],
            n_results=10,
        )
        self.assertIn("framework.md", out)
        self.assertNotIn("engram.md", out)
        self.assertNotIn("chat.md", out)
        self.assertNotIn("resource.md", out)

    def test_no_type_filter_includes_all_retrievable_types(self):
        out = rag_engine.assemble_ranked_context(
            query="consciousness epistemology framework",
            n_results=10,
        )
        self.assertIn("engram.md", out)
        self.assertIn("framework.md", out)


if __name__ == "__main__":
    unittest.main()
