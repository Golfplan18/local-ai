"""Tests for orchestrator/tools/cluster_recency.py — Phase 5.4.

Per Reference — Ora YAML Schema §6 (rev 3, 2026-04-30) the RAG ranker
applies linear cluster-recency decay to chunks of decay-eligible types:

    factor = max(FLOOR, 1.0 - (newer_count_in_cluster × DECAY_PER_NEWER))

where:
    - cluster identity is the chunk's `topic_primary` field
    - newer = strictly later timestamp
    - decay-eligible types: {incubator, chat, transcript, working, web}
    - all other types return 1.0 (no decay)

Defaults: DECAY_PER_NEWER = 0.05, FLOOR = 0.2.
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

from tools import cluster_recency  # noqa: E402


def _chunk(chunk_type, topic, ts, **extra):
    """Helper: build a minimal chunk dict for testing."""
    return {
        "type":          chunk_type,
        "topic_primary": topic,
        "timestamp_utc": ts,
        **extra,
    }


# ---------------------------------------------------------------------------
# Decay-ineligible types always return 1.0
# ---------------------------------------------------------------------------


class TestDecayIneligibleTypes(unittest.TestCase):
    """Vetted types and navigation types never decay (Schema §4)."""

    def setUp(self):
        # A busy cluster — if decay applied, factor would drop.
        self.busy_cluster = [
            _chunk("chat", "topic-x", f"2026-04-{i:02d}T10:00:00Z")
            for i in range(1, 16)
        ]

    def test_engram_no_decay(self):
        chunk = _chunk("engram", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_framework_no_decay(self):
        chunk = _chunk("framework", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_mode_no_decay(self):
        chunk = _chunk("mode", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_reference_no_decay(self):
        chunk = _chunk("reference", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_resource_no_decay(self):
        chunk = _chunk("resource", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_matrix_no_decay(self):
        chunk = _chunk("matrix", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_supervision_no_decay(self):
        chunk = _chunk("supervision", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)

    def test_unknown_type_no_decay(self):
        # Defensive: unknown type → no decay rather than crash.
        chunk = _chunk("nonexistent-type", "topic-x", "2026-01-01T00:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, self.busy_cluster), 1.0)


# ---------------------------------------------------------------------------
# Decay-eligible types: the formula
# ---------------------------------------------------------------------------


class TestDecayFormula(unittest.TestCase):
    """factor = max(FLOOR, 1.0 - newer_count × DECAY_PER_NEWER)."""

    def test_no_newer_in_cluster_returns_one(self):
        chunk = _chunk("chat", "topic-quiet", "2026-04-30T10:00:00Z")
        all_chunks = [chunk]
        self.assertEqual(cluster_recency.recency_factor(chunk, all_chunks), 1.0)

    def test_one_newer_chunk(self):
        chunk = _chunk("chat", "topic-x", "2026-04-29T10:00:00Z")
        newer = _chunk("chat", "topic-x", "2026-04-30T10:00:00Z")
        # 1.0 - 1 × 0.05 = 0.95
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, [chunk, newer]),
            0.95, places=6,
        )

    def test_five_newer_chunks(self):
        chunk = _chunk("chat", "topic-x", "2026-04-01T10:00:00Z")
        all_chunks = [chunk] + [
            _chunk("chat", "topic-x", f"2026-04-{i:02d}T10:00:00Z")
            for i in range(2, 7)  # 5 newer
        ]
        # 1.0 - 5 × 0.05 = 0.75
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks),
            0.75, places=6,
        )

    def test_ten_newer_chunks_matches_doc_example(self):
        # Conv RAG §4 worked example: 10 newer → factor 0.5.
        chunk = _chunk("chat", "consciousness-hard-problem", "2024-01-01T00:00:00Z")
        all_chunks = [chunk] + [
            _chunk("chat", "consciousness-hard-problem", f"2026-04-{i:02d}T10:00:00Z")
            for i in range(1, 11)  # 10 newer
        ]
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks),
            0.5, places=6,
        )

    def test_floor_clamps_at_minimum(self):
        chunk = _chunk("chat", "topic-x", "2024-01-01T00:00:00Z")
        # 100 newer → 1.0 - 100 × 0.05 = -4.0; clamp to 0.2
        all_chunks = [chunk] + [
            _chunk("chat", "topic-x", f"2026-04-30T{i:02d}:00:00Z")
            for i in range(0, 24)
        ]
        # +24 from above; add more to push past floor
        all_chunks += [
            _chunk("chat", "topic-x", f"2026-05-{i:02d}T00:00:00Z")
            for i in range(1, 31)
        ]
        # Total: 54 newer
        result = cluster_recency.recency_factor(chunk, all_chunks)
        self.assertEqual(result, 0.2)

    def test_at_floor_boundary(self):
        # 16 newer × 0.05 = 0.80; 1.0 - 0.80 = 0.20 (exactly at floor)
        chunk = _chunk("chat", "topic-x", "2026-04-01T10:00:00Z")
        all_chunks = [chunk] + [
            _chunk("chat", "topic-x", f"2026-04-{i:02d}T10:00:00Z")
            for i in range(2, 18)  # 16 newer
        ]
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks),
            0.2, places=6,
        )

    def test_just_above_floor(self):
        # 15 newer × 0.05 = 0.75; 1.0 - 0.75 = 0.25
        chunk = _chunk("chat", "topic-x", "2026-04-01T10:00:00Z")
        all_chunks = [chunk] + [
            _chunk("chat", "topic-x", f"2026-04-{i:02d}T10:00:00Z")
            for i in range(2, 17)  # 15 newer
        ]
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks),
            0.25, places=6,
        )


# ---------------------------------------------------------------------------
# Cluster scoping
# ---------------------------------------------------------------------------


class TestClusterScoping(unittest.TestCase):
    """Newer chunks only count when they share the chunk's topic_primary."""

    def test_no_topic_primary_returns_one(self):
        # Per Schema §6, a chunk without topic_primary is a singleton —
        # no cluster, no decay.
        chunk = _chunk("chat", None, "2026-04-30T10:00:00Z")
        newer = _chunk("chat", "topic-x", "2026-05-01T10:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, [chunk, newer]), 1.0)

    def test_empty_topic_primary_returns_one(self):
        chunk = _chunk("chat", "", "2026-04-30T10:00:00Z")
        newer = _chunk("chat", "topic-x", "2026-05-01T10:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, [chunk, newer]), 1.0)

    def test_different_cluster_does_not_count(self):
        chunk = _chunk("chat", "topic-x", "2026-04-29T10:00:00Z")
        all_chunks = [
            chunk,
            _chunk("chat", "topic-y", "2026-05-01T10:00:00Z"),  # different cluster
            _chunk("chat", "topic-z", "2026-05-02T10:00:00Z"),  # different cluster
        ]
        self.assertEqual(cluster_recency.recency_factor(chunk, all_chunks), 1.0)

    def test_mixed_clusters_only_same_counts(self):
        chunk = _chunk("chat", "topic-x", "2026-04-29T10:00:00Z")
        all_chunks = [
            chunk,
            _chunk("chat", "topic-x", "2026-04-30T10:00:00Z"),  # same, newer (counts)
            _chunk("chat", "topic-y", "2026-05-01T10:00:00Z"),  # different (skip)
            _chunk("chat", "topic-x", "2026-05-02T10:00:00Z"),  # same, newer (counts)
        ]
        # 2 newer in same cluster → 1.0 - 2 × 0.05 = 0.90
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks),
            0.90, places=6,
        )


# ---------------------------------------------------------------------------
# Timestamp handling
# ---------------------------------------------------------------------------


class TestTimestampHandling(unittest.TestCase):
    """Chunks with missing or equal timestamps."""

    def test_chunk_without_timestamp_returns_one(self):
        chunk = {"type": "chat", "topic_primary": "topic-x"}
        newer = _chunk("chat", "topic-x", "2026-05-01T10:00:00Z")
        # Without a timestamp on the chunk being scored, "newer than X" is
        # undefined; conservative behavior is no decay.
        self.assertEqual(cluster_recency.recency_factor(chunk, [chunk, newer]), 1.0)

    def test_other_chunk_without_timestamp_skipped(self):
        chunk = _chunk("chat", "topic-x", "2026-04-29T10:00:00Z")
        all_chunks = [
            chunk,
            {"type": "chat", "topic_primary": "topic-x"},  # no timestamp; skip
            _chunk("chat", "topic-x", "2026-04-30T10:00:00Z"),  # 1 newer
        ]
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks),
            0.95, places=6,
        )

    def test_equal_timestamp_does_not_count_as_newer(self):
        chunk = _chunk("chat", "topic-x", "2026-04-30T10:00:00Z")
        same = _chunk("chat", "topic-x", "2026-04-30T10:00:00Z")
        # Strict newer; equal does not count.
        self.assertEqual(cluster_recency.recency_factor(chunk, [chunk, same]), 1.0)

    def test_self_not_counted_as_newer(self):
        # When the chunk being scored is also in all_chunks, it shouldn't
        # somehow count itself as newer than itself.
        chunk = _chunk("chat", "topic-x", "2026-04-30T10:00:00Z")
        self.assertEqual(cluster_recency.recency_factor(chunk, [chunk]), 1.0)


# ---------------------------------------------------------------------------
# Decay-eligible type coverage
# ---------------------------------------------------------------------------


class TestDecayEligibleCoverage(unittest.TestCase):
    """All five decay-eligible types decay identically."""

    def _busy_cluster(self, chunk_type, count=10):
        chunk = _chunk(chunk_type, "topic-x", "2024-01-01T00:00:00Z")
        all_chunks = [chunk] + [
            _chunk(chunk_type, "topic-x", f"2026-04-{i:02d}T10:00:00Z")
            for i in range(1, count + 1)
        ]
        return chunk, all_chunks

    def test_chat_decays(self):
        chunk, all_chunks = self._busy_cluster("chat")
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks), 0.5, places=6,
        )

    def test_transcript_decays_like_chat(self):
        chunk, all_chunks = self._busy_cluster("transcript")
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks), 0.5, places=6,
        )

    def test_incubator_decays(self):
        chunk, all_chunks = self._busy_cluster("incubator")
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks), 0.5, places=6,
        )

    def test_working_decays(self):
        chunk, all_chunks = self._busy_cluster("working")
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks), 0.5, places=6,
        )

    def test_web_decays(self):
        chunk, all_chunks = self._busy_cluster("web")
        self.assertAlmostEqual(
            cluster_recency.recency_factor(chunk, all_chunks), 0.5, places=6,
        )


# ---------------------------------------------------------------------------
# Invariants the ranker depends on
# ---------------------------------------------------------------------------


class TestInvariants(unittest.TestCase):
    """Properties the Phase 5.6 ranker assumes."""

    def test_monotonic_in_newer_count(self):
        """More newer chunks → equal-or-lower factor; never higher."""
        chunk = _chunk("chat", "topic-x", "2026-04-01T00:00:00Z")
        prior_factor = 1.0
        for n in range(0, 25):
            others = [
                _chunk("chat", "topic-x", f"2026-04-{i:02d}T10:00:00Z")
                for i in range(2, 2 + n)
            ]
            factor = cluster_recency.recency_factor(chunk, [chunk] + others)
            self.assertLessEqual(factor, prior_factor + 1e-9)
            prior_factor = factor

    def test_factor_in_range(self):
        """Factor always in [FLOOR, 1.0]."""
        chunk = _chunk("chat", "topic-x", "2024-01-01T00:00:00Z")
        for n in (0, 1, 5, 10, 20, 100):
            others = [
                _chunk("chat", "topic-x", f"2026-04-30T{(i % 24):02d}:00:00Z")
                for i in range(n)
            ]
            factor = cluster_recency.recency_factor(chunk, [chunk] + others)
            self.assertGreaterEqual(factor, cluster_recency.FLOOR - 1e-9)
            self.assertLessEqual(factor, 1.0 + 1e-9)

    def test_constants_match_schema_defaults(self):
        # Schema §6: DECAY_PER_NEWER = 0.05, FLOOR = 0.2.
        self.assertEqual(cluster_recency.DECAY_PER_NEWER, 0.05)
        self.assertEqual(cluster_recency.FLOOR, 0.2)


if __name__ == "__main__":
    unittest.main()
