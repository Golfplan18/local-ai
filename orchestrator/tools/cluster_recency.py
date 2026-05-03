"""Cluster-recency decay — Phase 5.4.

Per Reference — Ora YAML Schema §6 (rev 3, 2026-04-30) and Reference —
Conversational RAG for Persistent AI Memory §4 (2026-04-30):

    factor = max(FLOOR, 1.0 - (newer_count_in_cluster × DECAY_PER_NEWER))
    score_contribution = similarity × type_weight × factor

A chunk's cluster is its `topic_primary` field (Conv RAG §2). Decay
measures how outdated a chunk is *within its cluster* — not in absolute
time. A chunk from 2024 in a quiet cluster (no newer entries) keeps
full weight; the same chunk in an active cluster (many newer entries)
decays toward FLOOR.

Decay applies only to types in `provenance.DECAY_ELIGIBLE_TYPES`
({incubator, chat, transcript, working, web}). All other types return
1.0 — vetted material does not decay.

Defaults: DECAY_PER_NEWER = 0.05, FLOOR = 0.2. Calibrate after first
runs (Conv RAG §4 notes the worked example uses these defaults).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Iterable

# Allow direct execution / test discovery without package context.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
if _ORCHESTRATOR not in sys.path:
    sys.path.insert(0, _ORCHESTRATOR)

from provenance import DECAY_ELIGIBLE_TYPES  # noqa: E402


DECAY_PER_NEWER: float = 0.05
FLOOR: float = 0.2


def recency_factor(chunk: dict[str, Any], all_chunks: Iterable[dict[str, Any]]) -> float:
    """Compute the cluster-recency decay factor for a chunk.

    Args:
        chunk: the chunk being scored. Expected fields: `type`,
            `topic_primary`, `timestamp_utc`.
        all_chunks: the candidate pool (typically a ChromaDB query
            result). Used to determine how many newer chunks exist in
            the same cluster.

    Returns:
        A float in [FLOOR, 1.0]. Decay-ineligible types, missing
        `topic_primary`, or missing chunk timestamp all short-circuit
        to 1.0 (no decay).
    """
    chunk_type = chunk.get("type")
    if chunk_type not in DECAY_ELIGIBLE_TYPES:
        return 1.0

    cluster = chunk.get("topic_primary")
    if not cluster:
        # No cluster identity → singleton, no decay (Schema §6).
        return 1.0

    chunk_ts = chunk.get("timestamp_utc")
    if not chunk_ts:
        # Without a timestamp on the chunk being scored, "newer than"
        # is undefined; conservative behavior is no decay.
        return 1.0

    newer_count = 0
    for other in all_chunks:
        if other is chunk:
            continue
        if other.get("topic_primary") != cluster:
            continue
        other_ts = other.get("timestamp_utc")
        if not other_ts:
            continue
        if other_ts > chunk_ts:  # ISO 8601 strings sort lexicographically
            newer_count += 1

    factor = 1.0 - (newer_count * DECAY_PER_NEWER)
    return max(FLOOR, factor)


__all__ = [
    "recency_factor",
    "DECAY_PER_NEWER",
    "FLOOR",
]
