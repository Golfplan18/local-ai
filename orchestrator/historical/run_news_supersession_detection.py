"""News Supersession Framework — detection phase.

Walks the Resources/ directory, clusters articles by ChromaDB embedding
similarity within the same tag-type (news / opinion / resource), and
identifies supersession candidate pairs — newer articles that may
supersede older versions of the same evolving story.

See `Framework — News Supersession` (vault canonical) for the full spec.

Usage:
    python3 run_news_supersession_detection.py [--limit N] [--similarity T]
                                                [--strategy <name>]
                                                [--include-resolved]

Strategies:
    topic-cluster (default) — embedding-similarity cluster within
                              tag-type + date-sort within cluster
                              (Approach A primary; Approach B entity-
                              overlap filter as secondary check)
    recent                  — restrict to articles modified in last 30 days
    random                  — uniform random sample of eligible pairs

Output: ~/Documents/vault/Projects/MSI/Working — News Supersession Queue.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml


VAULT_ROOT = os.path.expanduser("~/Documents/vault")
RESOURCES_DIR = os.path.join(VAULT_ROOT, "Resources")
QUEUE_FILE = os.path.join(
    VAULT_ROOT, "Projects", "MSI", "Working — News Supersession Queue.md"
)
LOG_FILE = os.path.join(
    VAULT_ROOT, "Projects", "MSI", "Working — News Supersession Log.md"
)

CHROMADB_PATH = os.path.expanduser("~/ora/chromadb")
COLLECTION_NAME = "knowledge"

DEFAULT_SIMILARITY = 0.80
DEFAULT_LIMIT = 25

# PROVISIONAL tuning constant (uncalibrated first guess — retune freely).
# detect_topic_cluster does 2 ChromaDB round-trips per eligible Resources/
# file; with no cap it scans the entire corpus every run regardless of
# --limit. Once collected candidates reach limit * this factor, the scan
# stops early — bounding per-run cost to a fixed ceiling as Resources/
# grows (relevant now that the automated weekly sweep runs this
# unattended, see supersession_sweep.py) at the cost of ranking only
# among the first ~limit*factor found rather than a guaranteed global
# top-N by similarity. Same oversample-then-truncate pattern detect_random
# already uses in this file. Override: ORA_NEWS_OVERSAMPLE_FACTOR.
CANDIDATE_OVERSAMPLE_FACTOR = int(
    os.environ.get("ORA_NEWS_OVERSAMPLE_FACTOR", "20")
)

# Tag types eligible for supersession; the cross-tag-type guard keeps
# each tag-type clustered separately (news doesn't supersede opinion).
ELIGIBLE_TAG_TYPES = ("news", "opinion", "resource")


# ---------------------------------------------------------------------------
# Resource index
# ---------------------------------------------------------------------------


def _detect_tag_type(tags: list[str]) -> Optional[str]:
    """Return the eligible tag-type for an article, or None if ineligible."""
    for t in ELIGIBLE_TAG_TYPES:
        if t in tags:
            return t
    return None


def _parse_date(value) -> Optional[str]:
    """Normalize a YAML date value to YYYY-MM-DD string, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        # Already string; trust format if it looks ISO
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", value)
        return m.group(1) if m else None
    # datetime.date or datetime.datetime
    try:
        return value.strftime("%Y-%m-%d")
    except Exception:
        return None


def build_resources_index() -> dict:
    """Walk Resources/ and build {path: meta} index.

    Skips files lacking eligible tags, lacking dates, or already carrying
    `archived` or `superseded` tags (those should not surface in detection).
    """
    by_path: dict[str, dict] = {}

    for fpath in sorted(Path(RESOURCES_DIR).glob("*.md")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2]

            tags = fm.get("tags") or []
            tag_type = _detect_tag_type(tags)
            if tag_type is None:
                continue

            # Skip already-archived or already-superseded
            if "archived" in tags or "superseded" in tags:
                continue

            # Title — H1 if present, else filename stem
            h1_match = re.search(r"^# (.+)$", body, re.MULTILINE)
            h1 = h1_match.group(1).strip() if h1_match else fpath.stem

            # Date — prefer date created; fall back to filename prefix
            date_str = _parse_date(fm.get("date created"))
            if not date_str:
                m = re.match(r"(\d{4}-\d{2}-\d{2})", fpath.stem)
                date_str = m.group(1) if m else None
            if not date_str:
                continue

            by_path[str(fpath)] = {
                "path": str(fpath),
                "slug": fpath.stem,
                "filename": fpath.name,
                "h1": h1,
                "tag_type": tag_type,
                "tags": tags,
                "date_created": date_str,
            }
        except Exception:
            continue

    return by_path


# ---------------------------------------------------------------------------
# Log-based filter (skip previously-resolved pairs)
# ---------------------------------------------------------------------------


_LOG_PAIR_RE = re.compile(
    r"- \*\*Source:\*\* \[\[([^\]]+)\]\]\n- \*\*Target:\*\* \[\[([^\]]+)\]\]"
)


def _parse_log_for_pair_keys(log_text: str) -> set[tuple[str, str]]:
    """Extract canonical (sorted) slug tuples from log markdown."""
    pairs: set[tuple[str, str]] = set()
    for m in _LOG_PAIR_RE.finditer(log_text):
        a, b = m.group(1).strip(), m.group(2).strip()
        pairs.add(tuple(sorted([a, b])))
    return pairs


def _load_resolved_pair_set() -> set[tuple[str, str]]:
    """Load all (slug, slug) tuples from the resolution log.

    Returns canonical-order tuples (sorted) so detection-time canonical
    tuples can be compared regardless of which side was source.
    """
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return _parse_log_for_pair_keys(f.read())


# ---------------------------------------------------------------------------
# Entity overlap (Approach B — secondary filter)
# ---------------------------------------------------------------------------


_STOP_CAPITALS = {
    "The", "And", "For", "But", "With", "From", "This", "That",
    "These", "Those", "When", "Where", "How", "Why",
}


def _extract_entities(text: str) -> set[str]:
    """Approximate named-entity extraction: capitalized tokens, filtered."""
    tokens = re.findall(r"\b[A-Z][a-zA-Z]+\b", text)
    return {t for t in tokens if len(t) > 2 and t not in _STOP_CAPITALS}


def entity_overlap(a_h1: str, b_h1: str) -> int:
    """Count overlapping capitalized entities between two titles."""
    return len(_extract_entities(a_h1) & _extract_entities(b_h1))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def detect_topic_cluster(
    by_path: dict,
    similarity_threshold: float,
    limit: int,
    resolved_set: Optional[set[tuple[str, str]]] = None,
    recent_only: bool = False,
    source_paths: Optional[set[str]] = None,
) -> list[dict]:
    """Surface supersession candidate pairs via topic clustering.

    For each Resources/ file, queries ChromaDB for nearest neighbors at
    similarity ≥ threshold within the same tag-type. Forms candidate
    pairs (older, newer) and applies entity-overlap filter to drop
    false-positive clusters.
    """
    if resolved_set is None:
        resolved_set = set()

    try:
        import chromadb
    except ImportError as e:
        # A normal exception, not sys.exit(1): this function is called both
        # from the CLI (main() below, which prints and exits) and from the
        # scheduled sweep (orchestrator/tools/supersession_sweep.py), whose
        # fail-open contract needs a catchable Exception — sys.exit raises
        # SystemExit, a BaseException that "except Exception" does not catch,
        # so it would escape the sweep's per-task guard and abort the whole
        # maintenance_scheduler.sweep() pass instead of just this task.
        raise RuntimeError(
            "chromadb not available. Install with: pip install chromadb"
        ) from e

    # Resolve the logical collection name through orchestrator.embedding —
    # the physical collection is machine-specific (config/chromadb.json).
    # Opening the physical "knowledge" collection directly reads the empty
    # pre-2026-05-29-migration collection and silently reports 0 candidates.
    sys.path.insert(0, os.path.expanduser("~/ora"))
    from orchestrator.embedding import get_collection
    from orchestrator.tools.knowledge_index import get_document_embedding

    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    col = get_collection(client, COLLECTION_NAME)

    candidates: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    # Query results identify physical Chroma records, not logical files.
    # Normalize the resource index once so chunk metadata paths can be
    # resolved back to their source note regardless of harmless path syntax
    # differences (for example ``..`` components).
    normalized_by_path = {
        os.path.abspath(os.path.expanduser(indexed_path)): meta
        for indexed_path, meta in by_path.items()
    }

    # Recent filter cutoff
    cutoff = datetime.now() - timedelta(days=30)

    normalized_sources = None
    if source_paths is not None:
        normalized_sources = {
            os.path.abspath(os.path.expanduser(p)) for p in source_paths
        }

    for path, meta in by_path.items():
        if (normalized_sources is not None
                and os.path.abspath(os.path.expanduser(path)) not in normalized_sources):
            continue
        if recent_only:
            try:
                d = datetime.fromisoformat(meta["date_created"])
                if d < cutoff:
                    continue
            except Exception:
                continue

        # Query for nearest neighbors via a document-level embedding.  Long
        # files have multiple physical records, so the helper mean-pools all
        # chunk embeddings into one vector instead of assuming id == path.
        # ChromaDB returns numpy arrays; truth-test via len() to avoid
        # the "truth value of an array with more than one element is
        # ambiguous" error.
        try:
            embedding = get_document_embedding(col, path)
            if embedding is None:
                print(f"  no chromadb embedding for {path}; skipping",
                      file=sys.stderr)
                continue

            neighbors = col.query(
                query_embeddings=[embedding],
                n_results=20,
                include=["distances", "metadatas"],
            )
        except Exception as e:
            # Surface failures rather than silently dropping every doc.
            # In smoke testing this was masking a numpy-truthiness bug
            # that caused all 2,632 resources to silently skip.
            print(f"  neighbor query failed for {path}: {e}",
                  file=sys.stderr)
            continue

        distances = neighbors.get("distances")
        if distances is None or len(distances) == 0 or len(distances[0]) == 0:
            continue

        for i, distance in enumerate(neighbors["distances"][0]):
            similarity = 1.0 - distance  # cosine distance → similarity
            if similarity < similarity_threshold:
                break  # results sorted by distance ascending

            neighbor_id = neighbors["ids"][0][i]

            # Nearest-neighbor ids are physical record ids.  For a chunked
            # file that is ``<path>#chunk-N`` and therefore is not a key in
            # by_path.  Chroma's always-present path metadata is the logical
            # identity.  Keep the id fallback for legacy single records and
            # lightweight test fakes that do not return metadatas.
            neighbor_path = None
            metadata_rows = neighbors.get("metadatas")
            if (metadata_rows is not None and len(metadata_rows) > 0
                    and metadata_rows[0] is not None
                    and i < len(metadata_rows[0])):
                record_meta = metadata_rows[0][i]
                if isinstance(record_meta, dict) and record_meta.get("path"):
                    neighbor_path = os.path.abspath(
                        os.path.expanduser(str(record_meta["path"]))
                    )

            source_path = os.path.abspath(os.path.expanduser(path))
            if neighbor_path == source_path:
                continue  # self

            if neighbor_path is not None:
                neighbor_meta = normalized_by_path.get(neighbor_path)
            else:
                # Old single-record layout (and existing fakes): id == path.
                neighbor_meta = by_path.get(neighbor_id)
                if neighbor_meta is None:
                    neighbor_meta = normalized_by_path.get(
                        os.path.abspath(os.path.expanduser(neighbor_id))
                    )
            if neighbor_meta is None:
                continue  # not in Resources/ or filtered out

            # Cross-tag-type guard
            if neighbor_meta["tag_type"] != meta["tag_type"]:
                continue

            # Date order
            d_meta = meta["date_created"]
            d_neighbor = neighbor_meta["date_created"]
            if d_meta == d_neighbor:
                continue  # same-day; deferred per spec
            if d_meta < d_neighbor:
                older, newer = meta, neighbor_meta
            else:
                older, newer = neighbor_meta, meta

            # Dedupe pair
            pair_key = tuple(sorted([older["slug"], newer["slug"]]))
            if pair_key in seen_pairs:
                continue
            if pair_key in resolved_set:
                continue
            seen_pairs.add(pair_key)

            # Entity-overlap check (Approach B as filter)
            overlap = entity_overlap(older["h1"], newer["h1"])
            if overlap < 1:
                continue

            # Date gap
            try:
                date_gap = (
                    datetime.fromisoformat(newer["date_created"]) -
                    datetime.fromisoformat(older["date_created"])
                ).days
            except Exception:
                date_gap = 0

            candidates.append({
                "older": older,
                "newer": newer,
                "similarity": similarity,
                "entity_overlap": overlap,
                "date_gap_days": date_gap,
            })

        # Bound total scan cost — see CANDIDATE_OVERSAMPLE_FACTOR comment.
        # Checked once per resource (outer loop), after that resource's
        # full neighbor list has been processed.
        if len(candidates) >= limit * CANDIDATE_OVERSAMPLE_FACTOR:
            break

    # Sort by similarity descending; cap at limit
    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    return candidates[:limit]


def detect_random(
    by_path: dict,
    similarity_threshold: float,
    limit: int,
    resolved_set: Optional[set[tuple[str, str]]] = None,
) -> list[dict]:
    """Uniform random sample drawn from topic-cluster candidates."""
    import random
    all_candidates = detect_topic_cluster(
        by_path, similarity_threshold,
        limit=200,  # over-sample then random
        resolved_set=resolved_set,
    )
    random.shuffle(all_candidates)
    return all_candidates[:limit]


# ---------------------------------------------------------------------------
# Queue format
# ---------------------------------------------------------------------------


def format_queue(
    candidates: list[dict],
    strategy: str,
    similarity_threshold: float,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    out: list[str] = []
    out.append(
        f"""---
nexus:
  - ora
type: working
tags:
  - news-supersession
date created: {today}
date modified: {today}
---

# News Supersession Queue — {today}

*Generated by Framework — News Supersession detection phase. Strategy: `{strategy}`. Similarity threshold: {similarity_threshold}. Pairs: {len(candidates)}.*

For each pair below, edit the **Resolution** line. Replace `[pending]` with one of:
- `[changed-mind:source-supersedes-target]` — source article is the current version of the story; target is older
- `[changed-mind:target-supersedes-source]` — target article is the current version of the story; source is older
- `[wrong:source]` — source article is factually wrong; archive (different from older — use only when incorrect, not just outdated)
- `[wrong:target]` — target article is factually wrong; archive
- `[skip]` — defer; not a real supersession (different angles on related events, false-positive cluster, etc.)

When done, run the resolver: `python3 ~/ora/orchestrator/historical/run_news_supersession_resolver.py`

---
"""
    )

    for pair in candidates:
        older = pair["older"]
        newer = pair["newer"]
        # Source = newer (current version), Target = older (the superseded candidate)
        # in the default convention; user can flip via target-supersedes-source.
        source = newer
        target = older

        title_short = source["h1"][:80] + ("..." if len(source["h1"]) > 80 else "")

        out.append(
            f"""## [pending] {title_short}

- **Source:** [[{source['slug']}]] ({source['date_created']}, tag: {source['tag_type']})
  *{source['h1']}*
- **Target:** [[{target['slug']}]] ({target['date_created']}, tag: {target['tag_type']})
  *{target['h1']}*
- **Cluster signal:** similarity {pair['similarity']:.3f}, entity overlap {pair['entity_overlap']}, date gap {pair['date_gap_days']} days
- **Strategy:** {strategy}

**Resolution:** [pending]

---
"""
        )

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_detection(
    strategy: str = "topic-cluster",
    limit: int = DEFAULT_LIMIT,
    similarity: float = DEFAULT_SIMILARITY,
    write_queue: bool = True,
    include_resolved: bool = False,
) -> dict:
    """Public callable for the slash-command handler and CLI."""
    by_path = build_resources_index()

    resolved_set = set() if include_resolved else _load_resolved_pair_set()

    if strategy == "topic-cluster":
        candidates = detect_topic_cluster(
            by_path, similarity, limit,
            resolved_set=resolved_set,
        )
    elif strategy == "recent":
        candidates = detect_topic_cluster(
            by_path, similarity, limit,
            resolved_set=resolved_set,
            recent_only=True,
        )
    elif strategy == "random":
        candidates = detect_random(
            by_path, similarity, limit,
            resolved_set=resolved_set,
        )
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    result: dict = {
        "strategy": strategy,
        "limit": limit,
        "similarity": similarity,
        "resource_count": len(by_path),
        "pairs_count": len(candidates),
        "resolved_filtered_count": len(resolved_set),
    }

    if write_queue:
        queue_md = format_queue(candidates, strategy, similarity)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write(queue_md)
        result["queue_path"] = QUEUE_FILE
    else:
        result["pairs"] = candidates

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--similarity", type=float, default=DEFAULT_SIMILARITY)
    ap.add_argument(
        "--strategy",
        default="topic-cluster",
        choices=["topic-cluster", "recent", "random"],
    )
    ap.add_argument(
        "--include-resolved",
        action="store_true",
        help="Re-surface previously-resolved pairs (default: filter via log)",
    )
    args = ap.parse_args()

    print(f"Building Resources/ index from {RESOURCES_DIR}...")
    try:
        result = run_detection(
            strategy=args.strategy,
            limit=args.limit,
            similarity=args.similarity,
            write_queue=True,
            include_resolved=args.include_resolved,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"  {result['resource_count']} eligible resources indexed")
    if not args.include_resolved:
        print(f"  Filtered {result['resolved_filtered_count']} previously-resolved pairs from log")
    print(f"  Surfaced {result['pairs_count']} supersession candidates")
    print(f"\nWrote queue to: {result['queue_path']}")
    print("\nNext step: review the queue and edit each pair's Resolution line,")
    print("then run the resolver:")
    print("  python3 ~/ora/orchestrator/historical/run_news_supersession_resolver.py")


if __name__ == "__main__":
    main()
