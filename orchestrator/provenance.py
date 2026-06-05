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

Vault tier (rev 5.2, 2026-06-05). Weights:
    engram                              → 1.0   (a kept atomic note — user-side OR
                                                  AI-side; no decay)
    resource                            → 0.8   (vetted reference material the user
                                                  curated, incl. trusted websites; no decay)
    resource + superseded tag           → 0.6   (older version of evolving story)
    chat, transcript                    → 0.6   (conversation/recording; the backup /
                                                  shaping layer; decays)
    web                                 → 0.1   (manually saved web, decays)
    framework, mode, reference,
      working, matrix, supervision      → None  (not retrieved)

External tier (live web fetches; never written to vault by default):
    whitelisted   → 0.8   (matches Reference — Trusted Web Sources; a cleared site
                           is curated reference, so it weights at the resource tier)
    corroborated  → 0.3   (≥2 unaffiliated occurrences in result set)
    single        → 0.15  (one non-farm source)
    excluded      → 0.0   (link farm / blacklisted; filtered before ranking)

AHI grounding (load-bearing): retrieval trust follows the user's observational
standing — whether the user has reviewed and KEPT a claim — not which keyboard
typed it. The former `ai-derived` / `source-derived` 0.9 caps were RETIRED
2026-06-05: a kept engram is the user's adopted thinking regardless of whether
the words originated with the AI, and the extraction quality gate already weeds
out AI content the user pushed back on. (Those tags may persist on notes as a
provenance record; they no longer affect weight.) Likewise a website the user
has cleared onto the trusted list is curated reference, so it weights as a
resource (0.8), not a discounted external source. See `Working — RAG Sources and
Provenance Rework 2026-06-05`.

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
    "engram":      1.0,    # user-side OR AI-side; authorship no longer modifies weight
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


# Engram provenance-modifier tags (`ai-derived`, `source-derived`) were RETIRED
# 2026-06-05. They capped AI-/external-authored engrams to 0.9, but retrieval
# trust now follows review-status (a kept engram is the user's adopted thinking)
# rather than authorship side. The tags may persist on notes as a provenance
# record; they no longer modify weight. Left as an empty dict (not removed) so
# the modifier mechanism remains available for any future weight modifier.
PROVENANCE_MODIFIER_TAGS: dict[str, float] = {}


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
    "whitelisted":  0.8,   # cleared site = curated reference (resource tier)
    "corroborated": 0.3,
    "single":       0.15,
    "excluded":     0.0,
}


def weight_for(chunk_type: Optional[str],
               tags: Optional[list[str]] = None) -> Optional[float]:
    """Look up the effective retrieval weight for a chunk.

    Combines the type's base weight with any weight-modifier tags
    present (per §6.5). The modifier families:
      - PROVENANCE_MODIFIER_TAGS — empty since 2026-06-05 (the engram
        `ai-derived` / `source-derived` caps were retired; authorship no
        longer modifies weight).
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
