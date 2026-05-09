"""Provenance — single source of truth for type→weight mapping.

Phase 5.1 of the Ora YAML Schema initiative. Consumed by:
    - orchestrator/rag_engine.py — multiplies similarity by type_weight
      and recency_factor when ranking chunks.
    - orchestrator/tools/web_corroboration.py — uses EXTERNAL_WEIGHTS to
      score live-web classifications.
    - orchestrator/tools/cluster_recency.py — uses DECAY_ELIGIBLE_TYPES
      to gate the decay function.

Authoritative reference: Reference — Ora YAML Schema §4 (type vocabulary
+ weights), §5 (provenance hierarchy), §6.5 (provenance-modifier tags).
Last revised 2026-05-09 (rev 5).

Vault tier — eleven types. Weights:
    engram                              → 1.0   (user-authored, no decay)
    engram + ai-derived tag             → 0.9   (AI-side cleaned-pair atomic)
    engram + source-derived tag         → 0.9   (DP-of-external-doc atomic)
    resource                            → 0.8   (vetted external, no decay)
    chat, transcript                    → 0.6   (conversation/recording, decays)
    web                                 → 0.1   (manually saved web, decays)
    framework, mode, reference,
      working, matrix, supervision      → None  (not retrieved)

External tier (live web fetches; never written to vault by default):
    whitelisted   → 0.7   (matches Registry — Trusted Web Sources)
    corroborated  → 0.3   (≥2 unaffiliated occurrences in result set)
    single        → 0.15  (one non-farm source)
    excluded      → 0.0   (link farm / blacklisted; filtered before ranking)

AHI grounding (load-bearing): AI-derived and source-derived engrams
carry a 0.9 modifier so AI-authored and external-author claims never
outrank user-authored engrams at retrieval. Curation by the user does
not transfer authorship; the claim still belongs to its originator.
"""

from __future__ import annotations

from typing import Optional


TYPE_WEIGHTS: dict[str, Optional[float]] = {
    "engram":      1.0,    # tag-modified per PROVENANCE_MODIFIER_TAGS below
    "resource":    0.8,
    "chat":        0.6,
    "transcript":  0.6,
    "web":         0.1,
    "framework":   None,   # not retrieved
    "mode":        None,
    "reference":   None,
    "working":     None,
    "matrix":      None,
    "supervision": None,
}


# Tags applied to engrams that lower the effective retrieval weight to
# signal not-user-authored provenance. Per §6.5 of the YAML Schema.
PROVENANCE_MODIFIER_TAGS: dict[str, float] = {
    "ai-derived":     0.9,   # AI-side of cleaned-pair conversations
    "source-derived": 0.9,   # DP atomic extracted from external document
}


DECAY_ELIGIBLE_TYPES: set[str] = {
    "chat",
    "transcript",
    "web",
}


EXTERNAL_WEIGHTS: dict[str, float] = {
    "whitelisted":  0.7,
    "corroborated": 0.3,
    "single":       0.15,
    "excluded":     0.0,
}


def weight_for(chunk_type: Optional[str],
               tags: Optional[list[str]] = None) -> Optional[float]:
    """Look up the effective provenance weight for a chunk.

    Combines the type's base weight with any provenance-modifier tags
    present (per §6.5). When a modifier tag applies, the lower of the
    base weight and the modifier weight wins.

    Returns the effective weight as a float for retrievable chunks, or
    None for chunks the ranker should skip (types with weight None,
    unknown types, or None input). The caller is expected to filter
    None weights out before scoring.

    Backward compatible: callers passing only chunk_type still work;
    new callers pass tags to apply provenance-modifier tags.
    """
    if chunk_type is None:
        return None
    base = TYPE_WEIGHTS.get(chunk_type)
    if base is None:
        return None
    if tags:
        modifier_weights = [
            PROVENANCE_MODIFIER_TAGS[t]
            for t in tags
            if t in PROVENANCE_MODIFIER_TAGS
        ]
        if modifier_weights:
            return min(base, min(modifier_weights))
    return base


__all__ = [
    "TYPE_WEIGHTS",
    "PROVENANCE_MODIFIER_TAGS",
    "DECAY_ELIGIBLE_TYPES",
    "EXTERNAL_WEIGHTS",
    "weight_for",
]
