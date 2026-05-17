"""Provenance — single source of truth for type→weight mapping.

Phase 5.1 of the Ora YAML Schema initiative. Consumed by:
    - orchestrator/rag_engine.py — multiplies similarity by type_weight
      and recency_factor when ranking chunks.
    - orchestrator/tools/web_corroboration.py — uses EXTERNAL_WEIGHTS to
      score live-web classifications.
    - orchestrator/tools/cluster_recency.py — uses DECAY_ELIGIBLE_TYPES
      to gate the decay function.

Authoritative reference: Reference — Ora YAML Schema §4 (type vocabulary
+ weights), §5 (provenance hierarchy), §6.5 (weight-modifier tags).
Last revised 2026-05-10 (rev 5.1 — `superseded` temporal-state tag).

Vault tier — eleven types. Weights:
    engram                              → 1.0   (user-authored, no decay)
    engram + ai-derived tag             → 0.9   (AI-side cleaned-pair atomic)
    engram + source-derived tag         → 0.9   (DP-of-external-doc atomic)
    resource                            → 0.8   (vetted external, no decay)
    resource + superseded tag           → 0.6   (older version of evolving story)
    chat, transcript                    → 0.6   (conversation/recording, decays)
    web                                 → 0.1   (manually saved web, decays)
    framework, mode, reference,
      working, matrix, supervision      → None  (not retrieved)

External tier (live web fetches; never written to vault by default):
    whitelisted   → 0.7   (matches Reference — Trusted Web Sources)
    corroborated  → 0.3   (≥2 unaffiliated occurrences in result set)
    single        → 0.15  (one non-farm source)
    excluded      → 0.0   (link farm / blacklisted; filtered before ranking)

AHI grounding (load-bearing): AI-derived and source-derived engrams
carry a 0.9 modifier so AI-authored and external-author claims never
outrank user-authored engrams at retrieval. Curation by the user does
not transfer authorship; the claim still belongs to its originator.

News-supersession grounding (rev 5.1): `superseded` resources stay in
retrieval (weight modifier, not filter) because news stories develop
but they don't replace history. Older articles are historical, not
wrong; `archived` (filter) is the wrong mechanic for news while
`superseded` (weight modifier) preserves the historical record at
reduced retrieval weight.
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


# Tags applied to resources (typically news articles) that lower the
# effective retrieval weight to signal temporal-state. Per §6.5 of the
# YAML Schema rev 5.1. These are weight modifiers, not filters: chunks
# stay retrievable but at reduced weight.
TEMPORAL_STATE_TAGS: dict[str, float] = {
    "superseded":     0.6,   # newer article in same evolving story exists
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
    """Look up the effective retrieval weight for a chunk.

    Combines the type's base weight with any weight-modifier tags
    present (per §6.5). Two tag families act as modifiers:
      - PROVENANCE_MODIFIER_TAGS (`ai-derived`, `source-derived`) —
        applied to engrams to signal not-user-authored provenance.
      - TEMPORAL_STATE_TAGS (`superseded`) — applied to resources to
        signal that a newer version of the story exists.

    When any modifier tag applies, the lower of the base weight and
    the modifier weight wins (defensive: if multiple modifiers apply,
    the minimum across all of them is taken).

    Returns the effective weight as a float for retrievable chunks, or
    None for chunks the ranker should skip (types with weight None,
    unknown types, or None input). The caller is expected to filter
    None weights out before scoring.

    Backward compatible: callers passing only chunk_type still work;
    new callers pass tags to apply modifier tags.
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
        ] + [
            TEMPORAL_STATE_TAGS[t]
            for t in tags
            if t in TEMPORAL_STATE_TAGS
        ]
        if modifier_weights:
            return min(base, min(modifier_weights))
    return base


__all__ = [
    "TYPE_WEIGHTS",
    "PROVENANCE_MODIFIER_TAGS",
    "TEMPORAL_STATE_TAGS",
    "DECAY_ELIGIBLE_TYPES",
    "EXTERNAL_WEIGHTS",
    "weight_for",
]
