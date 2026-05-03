"""Phase 5.9 validation tests.

The Phase 5 handoff lists explicit acceptance criteria for the new
type-weighted ranker (5.6) and the synthesis-layer provenance
communication. This file collects them as a single validation suite
that maps each criterion to a passing test.

Retrieval ranking:
  - Engram outranks contradicting resources in synthesis context.
  - Old chat in active cluster decays to floor; same chat in quiet
    cluster retains nominal weight.
  - Mode with type_filter: [framework] returns no engrams or chats.
  - Engram with same age as decaying chat retains full weight.

Synthesis-layer provenance communication:
  - Synthesis where engram contradicts resource consensus → assembled
    context places the engram first (the synthesis model sees the
    higher-provenance position before lower-tier sources).
  - Gear 4 consolidator preference → assembled context for the
    consolidator places higher-provenance chunks first.
  - Direct inspection of context package → every chunk has a visible
    provenance marker.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

import rag_engine  # noqa: E402

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()


def _vault_chunk(chunk_type, similarity, source, *, document="body",
                 topic=None, ts=None):
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


# ---------------------------------------------------------------------------
# Retrieval ranking acceptance criteria
# ---------------------------------------------------------------------------


class TestRankingAcceptance(unittest.TestCase):

    def test_engram_outranks_contradicting_resource(self):
        """When an engram and a resource carry conflicting positions on
        the same topic, the engram (1.0) outranks the resource (0.7)."""
        engram = _vault_chunk(
            "engram", similarity=0.7, source="user_position.md",
            document="Consciousness IS reducible to physical processes.",
            topic="consciousness",
        )
        resource = _vault_chunk(
            "resource", similarity=0.7, source="external_paper.md",
            document="Consciousness is NOT reducible to physical processes.",
            topic="consciousness",
        )
        ranked = rag_engine.rank_vault_chunks([engram, resource])
        self.assertEqual(ranked[0]["metadata"]["source"], "user_position.md")
        # Score gap: engram 0.7 × 1.0 vs resource 0.7 × 0.7 = 0.7 vs 0.49.
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])

    def test_chat_in_active_cluster_vs_quiet_cluster(self):
        """Same-age chat decays to floor in an active cluster but retains
        nominal weight in a quiet cluster."""
        # Active cluster: 30 newer chunks → factor floors at 0.2.
        active_target = _vault_chunk(
            "chat", similarity=1.0, source="active_old.md",
            topic="active-topic", ts="2024-01-01T00:00:00Z",
        )
        active_busy = [
            _vault_chunk(
                "chat", similarity=0.5, source=f"active_newer_{i}.md",
                topic="active-topic",
                ts=f"2026-04-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00Z",
            )
            for i in range(30)
        ]
        active_ranked = rag_engine.rank_vault_chunks([active_target] + active_busy)
        active_scored = next(c for c in active_ranked
                             if c["metadata"]["source"] == "active_old.md")

        # Quiet cluster: zero newer chunks → factor 1.0.
        quiet_target = _vault_chunk(
            "chat", similarity=1.0, source="quiet_old.md",
            topic="quiet-topic", ts="2024-01-01T00:00:00Z",
        )
        quiet_ranked = rag_engine.rank_vault_chunks([quiet_target])
        quiet_scored = quiet_ranked[0]

        # Active: factor 0.2, score = 1.0 × 0.3 × 0.2 = 0.06
        self.assertAlmostEqual(active_scored["recency"], 0.2, places=6)
        self.assertAlmostEqual(active_scored["score"], 0.06, places=6)
        # Quiet: factor 1.0, score = 1.0 × 0.3 × 1.0 = 0.3
        self.assertEqual(quiet_scored["recency"], 1.0)
        self.assertAlmostEqual(quiet_scored["score"], 0.3, places=6)
        # The "quiet" chat outranks the same-age "active" chat.
        self.assertGreater(quiet_scored["score"], active_scored["score"])

    def test_engram_decay_immune_when_chat_decays(self):
        """An engram with the same age as a decaying chat keeps full
        weight (decay-ineligible type)."""
        engram = _vault_chunk(
            "engram", similarity=1.0, source="ancient_engram.md",
            topic="topic-x", ts="2024-01-01T00:00:00Z",
        )
        chat = _vault_chunk(
            "chat", similarity=1.0, source="ancient_chat.md",
            topic="topic-x", ts="2024-01-01T00:00:00Z",
        )
        newer_chats = [
            _vault_chunk(
                "chat", similarity=0.5, source=f"newer_{i}.md",
                topic="topic-x", ts=f"2026-04-{i:02d}T10:00:00Z",
            )
            for i in range(1, 11)
        ]
        ranked = rag_engine.rank_vault_chunks([engram, chat] + newer_chats)
        engram_scored = next(c for c in ranked
                             if c["metadata"]["source"] == "ancient_engram.md")
        chat_scored = next(c for c in ranked
                           if c["metadata"]["source"] == "ancient_chat.md")

        self.assertEqual(engram_scored["recency"], 1.0)
        self.assertAlmostEqual(chat_scored["recency"], 0.5, places=6)
        self.assertGreater(engram_scored["score"], chat_scored["score"])

    def test_type_filter_framework_excludes_engrams_and_chats(self):
        """A mode declaring type_filter: [framework] retrieves only
        framework chunks — engrams, chats, etc. are filtered out at
        knowledge_search.knowledge_search_raw."""
        from tools import knowledge_search
        tmpdir = tempfile.mkdtemp()
        try:
            chromadb_path = os.path.join(tmpdir, "chromadb")
            original = knowledge_search.CHROMADB_PATH
            knowledge_search.CHROMADB_PATH = chromadb_path
            try:
                import chromadb
                from orchestrator.embedding import get_or_create_collection as _bind_ef
                client = chromadb.PersistentClient(path=chromadb_path)
                col = _bind_ef(client, "knowledge")
                col.add(
                    ids=["engram", "chat", "framework"],
                    documents=[
                        "Engram about adversarial review.",
                        "Chat about adversarial review.",
                        "Framework spec for adversarial review.",
                    ],
                    metadatas=[
                        {"type": "engram", "source": "engram.md",
                         "tag_archived": False, "tag_incubating": False,
                         "tag_private": False},
                        {"type": "chat", "source": "chat.md",
                         "tag_archived": False, "tag_incubating": False,
                         "tag_private": False},
                        {"type": "framework", "source": "framework.md",
                         "tag_archived": False, "tag_incubating": False,
                         "tag_private": False},
                    ],
                )

                out = rag_engine.assemble_ranked_context(
                    query="adversarial review",
                    type_filter=["framework"],
                    n_results=10,
                )
                self.assertIn("framework.md", out)
                self.assertNotIn("engram.md", out)
                self.assertNotIn("chat.md", out)
            finally:
                knowledge_search.CHROMADB_PATH = original
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Synthesis-layer provenance communication
# ---------------------------------------------------------------------------


class TestSynthesisProvenanceCommunication(unittest.TestCase):
    """Synthesis-layer behavior is mediated by what the consuming model
    sees in the assembled context. These tests verify the assembled
    package places higher-provenance chunks first AND every chunk
    carries a visible provenance marker."""

    def test_engram_first_when_engram_contradicts_resource_consensus(self):
        """The synthesis model receives engram before resources. With
        engram first and tagged with weight 1.0 in the marker, a
        well-behaved consumer reflects the user's vetted position."""
        engram = _vault_chunk(
            "engram", similarity=0.5, source="user_position.md",
            document="Consciousness is reducible.",
        )
        resources = [
            _vault_chunk(
                "resource", similarity=0.6,
                source=f"external_{i}.md",
                document="Consciousness is NOT reducible.",
            )
            for i in range(3)
        ]
        ranked = rag_engine.rank_vault_chunks([engram] + resources)
        out = rag_engine.format_context_with_provenance(ranked)
        # Engram appears before any resource in the assembled text.
        engram_pos = out.index("user_position.md")
        for i in range(3):
            res_pos = out.index(f"external_{i}.md")
            self.assertLess(engram_pos, res_pos,
                            f"engram should precede external_{i}.md")
        # Engram's marker shows its provenance weight 1.0.
        self.assertIn("[type: engram | weight: 1.0", out)

    def test_consolidator_sees_higher_provenance_first(self):
        """For a Gear 4 consolidator, the assembled context for the
        synthesis step ranks higher-provenance reasoning above lower."""
        chunks = [
            _vault_chunk("framework", similarity=0.4, source="framework_spec.md"),
            _vault_chunk("chat",      similarity=0.9, source="recent_chat.md"),
            _vault_chunk("engram",    similarity=0.5, source="vetted_position.md"),
        ]
        ranked = rag_engine.rank_vault_chunks(chunks)
        out = rag_engine.format_context_with_provenance(ranked)
        # framework (1.0×0.4=0.40) and engram (1.0×0.5=0.50) outrank
        # chat (0.3×0.9=0.27). Consolidator sees the higher-provenance
        # pair first.
        engram_pos    = out.index("vetted_position.md")
        framework_pos = out.index("framework_spec.md")
        chat_pos      = out.index("recent_chat.md")
        self.assertLess(engram_pos, chat_pos)
        self.assertLess(framework_pos, chat_pos)

    def test_every_chunk_has_visible_provenance_marker(self):
        """Direct inspection of the context package: every retrieved
        chunk carries [type: ... | weight: ... | source: ...]."""
        chunks = [
            _vault_chunk("engram",    similarity=0.5, source="a.md"),
            _vault_chunk("framework", similarity=0.5, source="b.md"),
            _vault_chunk("resource",  similarity=0.5, source="c.md"),
            _vault_chunk("chat",      similarity=0.5, source="d.md"),
            _vault_chunk("incubator", similarity=0.5, source="e.md"),
        ]
        ranked = rag_engine.rank_vault_chunks(chunks)
        out = rag_engine.format_context_with_provenance(ranked)
        for source in ("a.md", "b.md", "c.md", "d.md", "e.md"):
            line_with_marker = next(
                (ln for ln in out.splitlines() if source in ln),
                None,
            )
            self.assertIsNotNone(line_with_marker,
                                 f"no marker line for {source}")
            self.assertIn("[type:", line_with_marker)
            self.assertIn("weight:", line_with_marker)
            self.assertIn("source:", line_with_marker)


if __name__ == "__main__":
    unittest.main()
