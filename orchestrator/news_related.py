"""News-to-news related-article retrieval.

Three-signal retrieval over the msi_news_articles ChromaDB collection per the
News-to-News Cross-Linking design (2026-05-14):

  Signal 1: source_cluster_id exact match → relation="continues", strength=1.0
  Signal 2: cosine similarity ≥ 0.5  → relation="related",  strength=cosine
  Signal 3: optional small-model arbitration when the first two disagree
            (cluster_id matches but content has diverged; OR cluster_id misses
             but cosine ≥ 0.85 suggesting same story under a different cluster).

Per the §1.4.7 voice-corpus pattern this implements: cross-linking is publication
coherence; cross-importing is voice-convergence failure. The retrieval surfaces
link candidates; the article-generator framework writes the article — it does
not borrow analytical framing from the prior articles surfaced here.

Returns a list of Related records ranked by:
  display_score = 0.7 × strength + 0.3 × recency_factor
where recency_factor = exp(-days_since_publish / 60).

`continues` entries always group above `related` regardless of display_score
(the layout renders them in separate sub-sections).

The candidate article itself is excluded from results when `candidate_slug` is
provided — relevant for the run-script use case where the candidate is being
indexed in the same publication cycle.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Optional


CHROMADB_PATH = os.path.expanduser("~/ora/chromadb/")
COLLECTION_NAME = "msi_news_articles"

# Liberal floor per error-toward-too-many-cross-links principle. Display
# ranking dominates; weak matches simply rank low.
COSINE_THRESHOLD_RELATED = 0.5

# Strong-similarity threshold for triggering Signal 3 arbitration when
# cluster_id misses (potential same-story-different-cluster case).
COSINE_THRESHOLD_ARBITRATION = 0.85

# Half-life in days for the recency decay factor in display ranking.
RECENCY_HALF_LIFE_DAYS = 60.0

# Top N candidates returned (liberal — display layer trims to top 5 + expand).
DEFAULT_TOP_N = 20


@dataclass
class Related:
    """A related-news candidate surfaced by retrieval."""

    slug: str
    headline: str
    publish_date: str           # ISO YYYY-MM-DD
    relation: str               # "continues" | "related"
    strength: float             # cluster_id match = 1.0; semantic = cosine
    display_score: float        # 0.7 × strength + 0.3 × recency_factor

    def as_frontmatter_entry(self) -> dict[str, Any]:
        """Shape suitable for emission in the article frontmatter."""
        return {
            "slug": self.slug,
            "headline": self.headline,
            "publish_date": self.publish_date,
            "relation": self.relation,
            "strength": round(self.strength, 4),
        }


# ---------------------------------------------------------------------------
# Recency
# ---------------------------------------------------------------------------


def _parse_iso_date(s: str) -> Optional[date]:
    """Parse YYYY-MM-DD (the publish_date format) → date. Returns None on failure."""
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _recency_factor(publish_date_str: str, reference: date) -> float:
    """exp(-days_since_publish / 60). 1.0 if same day; decays with age."""
    pub = _parse_iso_date(publish_date_str)
    if pub is None:
        return 0.0
    days = (reference - pub).days
    if days < 0:
        days = 0
    return math.exp(-days / RECENCY_HALF_LIFE_DAYS)


def _display_score(strength: float, publish_date_str: str, reference: date) -> float:
    return 0.7 * strength + 0.3 * _recency_factor(publish_date_str, reference)


# ---------------------------------------------------------------------------
# Signal 1: source_cluster_id exact match
# ---------------------------------------------------------------------------


def _signal_cluster_match(
    collection,
    source_cluster_id: str,
    candidate_slug: Optional[str],
    reference_date: date,
) -> list[Related]:
    """Return all prior articles sharing the given source_cluster_id."""
    if not source_cluster_id:
        return []

    try:
        result = collection.get(where={"source_cluster_id": source_cluster_id})
    except Exception:
        return []

    out: list[Related] = []
    ids = result.get("ids") or []
    metas = result.get("metadatas") or []
    for _doc_id, meta in zip(ids, metas):
        slug = meta.get("slug", "")
        if candidate_slug and slug == candidate_slug:
            continue
        publish_date = meta.get("publish_date", "")
        strength = 1.0
        out.append(Related(
            slug=slug,
            headline=meta.get("headline", ""),
            publish_date=publish_date,
            relation="continues",
            strength=strength,
            display_score=_display_score(strength, publish_date, reference_date),
        ))
    return out


# ---------------------------------------------------------------------------
# Signal 2: cosine similarity
# ---------------------------------------------------------------------------


def _cosine_from_distance(distance: float) -> float:
    """ChromaDB returns L2 distance by default for the cosine metric collection.

    The collection is created with metric `cosine`, so the distance is in
    [0, 2] where 0 = identical. similarity = 1 - distance.
    """
    return max(0.0, 1.0 - float(distance))


def _signal_semantic_match(
    collection,
    query_text: str,
    candidate_slug: Optional[str],
    reference_date: date,
    top_n: int,
) -> list[Related]:
    """Return top-N semantic matches above the COSINE_THRESHOLD_RELATED floor."""
    if not query_text.strip():
        return []

    try:
        # Query returns up to `n_results` documents ordered by ascending distance.
        result = collection.query(
            query_texts=[query_text],
            n_results=top_n + 5,  # buffer for self-exclusion
        )
    except Exception:
        return []

    metas_lists = result.get("metadatas") or [[]]
    distances_lists = result.get("distances") or [[]]
    metas = metas_lists[0] if metas_lists else []
    distances = distances_lists[0] if distances_lists else []

    out: list[Related] = []
    for meta, dist in zip(metas, distances):
        slug = meta.get("slug", "")
        if candidate_slug and slug == candidate_slug:
            continue
        sim = _cosine_from_distance(dist)
        if sim < COSINE_THRESHOLD_RELATED:
            continue
        publish_date = meta.get("publish_date", "")
        out.append(Related(
            slug=slug,
            headline=meta.get("headline", ""),
            publish_date=publish_date,
            relation="related",
            strength=sim,
            display_score=_display_score(sim, publish_date, reference_date),
        ))
    return out


# ---------------------------------------------------------------------------
# Signal 3: small-model arbitration (optional)
# ---------------------------------------------------------------------------


def _maybe_arbitrate(
    cluster_matches: list[Related],
    semantic_matches: list[Related],
    candidate_meta: dict[str, Any],
    arbiter: Optional[Callable[[dict[str, Any], dict[str, Any]], str]],
) -> list[Related]:
    """Run signal-3 arbitration on edge cases. Best-effort; falls through on failure.

    Two disagreement cases:
      A. A semantic match is very high (≥ 0.85) but did not appear in the
         cluster_id match set — could be the same story under a different
         cluster_id. Promote relation to "continues" if arbiter agrees.
      B. (Future) A cluster_id match has very low cosine similarity — could
         indicate the chain has drifted topically. Not currently demoted;
         publishers value continuity over similarity for chain coherence.

    If arbiter is None or raises, the inputs are returned unchanged.
    """
    if arbiter is None:
        return semantic_matches

    cluster_slugs = {r.slug for r in cluster_matches}
    adjusted: list[Related] = []
    for r in semantic_matches:
        if r.slug in cluster_slugs:
            adjusted.append(r)
            continue
        if r.strength < COSINE_THRESHOLD_ARBITRATION:
            adjusted.append(r)
            continue
        try:
            verdict = arbiter(candidate_meta, {
                "slug": r.slug,
                "headline": r.headline,
                "publish_date": r.publish_date,
            })
            if verdict == "continues":
                # Promote: same story under different cluster_id.
                r = Related(
                    slug=r.slug,
                    headline=r.headline,
                    publish_date=r.publish_date,
                    relation="continues",
                    strength=r.strength,
                    display_score=r.display_score,
                )
        except Exception:
            pass
        adjusted.append(r)
    return adjusted


# ---------------------------------------------------------------------------
# Top-level retrieval entry point
# ---------------------------------------------------------------------------


def find_related_news(
    *,
    candidate_slug: Optional[str] = None,
    source_cluster_id: str = "",
    headline: str = "",
    lede: str = "",
    nut_graf: str = "",
    body: str = "",
    publish_date: str = "",
    collection=None,
    arbiter: Optional[Callable[[dict[str, Any], dict[str, Any]], str]] = None,
    top_n: int = DEFAULT_TOP_N,
    reference_date: Optional[date] = None,
) -> list[Related]:
    """Find related news articles for a candidate article.

    Args:
        candidate_slug: filename-without-.md of the candidate, for self-exclusion.
            Pass None when the candidate isn't yet in the collection (the
            common case during article generation).
        source_cluster_id: GDELT-derived cluster id; the strong continuation signal.
        headline, lede, nut_graf, body: candidate article content; combined into
            the query text for semantic match.
        publish_date: ISO date of the candidate; defaults reference_date to this.
        collection: ChromaDB collection. If None, opens the production collection
            at ~/ora/chromadb/ (lazily; allows tests to inject).
        arbiter: optional callable(candidate_meta, prior_meta) -> "continues"
            | "related" for Signal 3 arbitration on high-similarity edge cases.
        top_n: how many candidates to return. Liberal default (20) per the
            error-toward-too-many-cross-links design; display layer trims.
        reference_date: the "today" anchor for recency factor. Defaults to
            parsed publish_date, else today.

    Returns:
        Ranked list of Related, deduplicated by slug (continues > related
        when same slug appears in both signals), ordered with all `continues`
        first (by display_score desc), then all `related` (by display_score desc).
        Returns [] when the collection is empty or candidate has no content.
    """
    # Reference date for recency calculations.
    if reference_date is None:
        reference_date = _parse_iso_date(publish_date) or date.today()

    if collection is None:
        collection = _open_default_collection()
        if collection is None:
            return []

    # Signal 1
    cluster_matches = _signal_cluster_match(
        collection, source_cluster_id, candidate_slug, reference_date,
    )

    # Signal 2
    query_parts = [headline, lede, nut_graf, body[:3000]]
    query_text = "\n\n".join(p for p in query_parts if p)
    semantic_matches = _signal_semantic_match(
        collection, query_text, candidate_slug, reference_date, top_n,
    )

    # Signal 3
    candidate_meta = {
        "slug": candidate_slug or "",
        "headline": headline,
        "publish_date": publish_date,
        "source_cluster_id": source_cluster_id,
    }
    semantic_matches = _maybe_arbitrate(
        cluster_matches, semantic_matches, candidate_meta, arbiter,
    )

    # Merge with continues-wins deduplication.
    by_slug: dict[str, Related] = {}
    for r in cluster_matches:
        by_slug[r.slug] = r
    for r in semantic_matches:
        existing = by_slug.get(r.slug)
        if existing is None:
            by_slug[r.slug] = r
        elif existing.relation == "continues":
            # continues wins; keep the cluster-match record (strength 1.0)
            # but lift display_score with semantic if higher (rare edge case).
            if r.display_score > existing.display_score:
                by_slug[r.slug] = Related(
                    slug=existing.slug,
                    headline=existing.headline,
                    publish_date=existing.publish_date,
                    relation="continues",
                    strength=existing.strength,
                    display_score=r.display_score,
                )
        else:
            # both related; keep highest strength
            if r.strength > existing.strength:
                by_slug[r.slug] = r

    # Order: continues first (by display_score desc), then related (by display_score desc).
    continues = sorted(
        (r for r in by_slug.values() if r.relation == "continues"),
        key=lambda r: r.display_score, reverse=True,
    )
    related = sorted(
        (r for r in by_slug.values() if r.relation == "related"),
        key=lambda r: r.display_score, reverse=True,
    )
    combined = continues + related
    return combined[:top_n]


def _open_default_collection():
    """Open the production msi_news_articles collection. Lazy-imports chromadb."""
    try:
        import chromadb
        from orchestrator.embedding import get_or_create_collection
    except Exception:
        return None
    try:
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        return get_or_create_collection(client, COLLECTION_NAME)
    except Exception:
        return None
