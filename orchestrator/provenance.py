"""Provenance — single source of truth for type→weight mapping.

Phase 5.1 of the Ora YAML Schema initiative. Consumed by:
    - orchestrator/rag_engine.py (Phase 5.6) — multiplies similarity by
      type_weight and recency_factor when ranking chunks.
    - orchestrator/tools/web_corroboration.py (Phase 5.5) — uses
      EXTERNAL_WEIGHTS to score live-web classifications.
    - orchestrator/tools/cluster_recency.py (Phase 5.4) — uses
      DECAY_ELIGIBLE_TYPES to gate the decay function.

Authoritative reference: Reference — Ora YAML Schema §4 (type vocabulary
+ weights) and §5 (external tier classifications). Last revised
2026-04-30 (rev 3).

Vault tier — twelve types, mutually exclusive. Weights:
    engram, framework, mode, reference  → 1.0   (vetted, no decay)
    resource                             → 0.7   (vetted external, no decay)
    incubator                            → 0.4   (unreviewed, decays)
    chat, transcript                     → 0.3   (conversation/recording, decays)
    working                              → 0.2   (in-progress drafts, decays)
    web                                  → 0.1   (manually saved web, decays)
    matrix, supervision                  → None  (navigation/admin, not retrieved)

External tier (live web fetches, never written to vault by default):
    whitelisted   → 0.7   (matches Reference — Trusted Web Sources)
    corroborated  → 0.3   (≥2 unaffiliated occurrences in result set)
    single        → 0.15  (one non-farm source)
    excluded      → 0.0   (link farm / blacklisted; filtered before ranking)
"""

from __future__ import annotations

from typing import Optional


TYPE_WEIGHTS: dict[str, Optional[float]] = {
    "engram":      1.0,
    "framework":   1.0,
    "mode":        1.0,
    "reference":   1.0,
    "resource":    0.7,
    "incubator":   0.4,
    "chat":        0.3,
    "transcript":  0.3,
    "working":     0.2,
    "web":         0.1,
    "matrix":      None,
    "supervision": None,
}


DECAY_ELIGIBLE_TYPES: set[str] = {
    "incubator",
    "chat",
    "transcript",
    "working",
    "web",
}


EXTERNAL_WEIGHTS: dict[str, float] = {
    "whitelisted":  0.7,
    "corroborated": 0.3,
    "single":       0.15,
    "excluded":     0.0,
}


def weight_for(chunk_type: Optional[str]) -> Optional[float]:
    """Look up the provenance weight for a chunk's type.

    Returns the weight as a float for retrievable types, or None for
    types the ranker should skip (matrix, supervision, unknown values,
    None input). The caller is expected to filter None weights out
    before scoring.
    """
    if chunk_type is None:
        return None
    return TYPE_WEIGHTS.get(chunk_type)


__all__ = [
    "TYPE_WEIGHTS",
    "DECAY_ELIGIBLE_TYPES",
    "EXTERNAL_WEIGHTS",
    "weight_for",
]
