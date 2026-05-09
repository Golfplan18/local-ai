"""Engram Cleaning Framework — detection phase.

Walks the relationship-graph.db `contradicts` edges, prioritizes per the
active strategy, and writes a triage queue file the user edits with
resolution markers.

See `Framework — Engram Cleaning` (vault canonical) for the full spec.

Usage:
    python3 run_engram_cleaning_detection.py [--limit N] [--strategy <name>]

Strategies:
    bidirectional (default) — pairs where both A→B and B→A contradicts edges
                              exist (strongest signal)
    random                  — uniform random sample (unbiased corpus check)

Output: ~/Documents/vault/Working — Engram Cleaning Queue.md
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sqlite3
import sys
from datetime import datetime
from typing import Optional

import yaml


ENGRAMS_DIR = os.path.expanduser("~/Documents/vault/Engrams")
GRAPH_DB = os.path.expanduser("~/ora/data/relationship-graph.db")
QUEUE_FILE = os.path.expanduser("~/Documents/vault/Working — Engram Cleaning Queue.md")
LOG_FILE = os.path.expanduser("~/Documents/vault/Working — Engram Cleaning Log.md")


_LOG_PAIR_RE = re.compile(
    r"- \*\*Source:\*\* \[\[([^\]]+)\]\]\n- \*\*Target:\*\* \[\[([^\]]+)\]\]"
)


def _parse_log_for_pair_keys(log_text: str) -> set[tuple[str, str]]:
    """Extract canonical (sorted) source-target slug tuples from log markdown."""
    pairs: set[tuple[str, str]] = set()
    for m in _LOG_PAIR_RE.finditer(log_text):
        a, b = m.group(1).strip(), m.group(2).strip()
        pairs.add(tuple(sorted([a, b])))
    return pairs


def _load_resolved_pair_set() -> set[tuple[str, str]]:
    """Load all (source_slug, target_slug) tuples from the resolution log.

    Returns canonical-order tuples (sorted) so they can be compared against
    detection-time canonical tuples regardless of which side was source.
    Empty set if the log file does not exist yet.
    """
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return _parse_log_for_pair_keys(f.read())


def build_engram_index() -> tuple[dict, dict]:
    """Walk Engrams/ and build {slug: meta}, {h1: meta} indexes.

    `slug` is the filename minus `.md`. `h1` is the first H1 heading
    in the body. `meta` carries slug, h1, filename, path, frontmatter.
    """
    by_slug: dict[str, dict] = {}
    by_h1: dict[str, dict] = {}

    paths = sorted(glob.glob(os.path.join(ENGRAMS_DIR, "*.md")))
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2]
            h1_match = re.search(r"^# (.+)$", body, re.MULTILINE)
            if not h1_match:
                continue
            h1 = h1_match.group(1).strip()
            filename = os.path.basename(path)
            slug = filename[:-3]
            entry = {
                "slug": slug,
                "h1": h1,
                "filename": filename,
                "path": path,
                "frontmatter": fm,
            }
            by_slug[slug] = entry
            # Multiple engrams may share an H1 if Phase 5 produced near-duplicates.
            # The first wins — duplicates are subject to dedup elsewhere.
            if h1 not in by_h1:
                by_h1[h1] = entry
        except Exception:
            continue

    return by_slug, by_h1


def is_archived(meta: dict) -> bool:
    tags = meta["frontmatter"].get("tags") or []
    return "archived" in tags


def provenance_tag(meta: dict) -> str:
    tags = meta["frontmatter"].get("tags") or []
    if "ai-derived" in tags:
        return "ai-derived"
    if "source-derived" in tags:
        return "source-derived"
    return "user"


def detect_bidirectional(
    by_slug: dict, by_h1: dict, limit: int = 25,
    resolved_set: Optional[set[tuple[str, str]]] = None,
) -> list[tuple[dict, dict]]:
    """Pairs where both A→B and B→A contradicts edges exist (high confidence).

    `resolved_set` is a set of canonical (sorted) slug tuples that have been
    resolved in past runs (loaded from the resolution log). Pairs in that set
    are skipped — preventing the same pairs from resurfacing run after run.
    """
    if resolved_set is None:
        resolved_set = set()

    conn = sqlite3.connect(GRAPH_DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT source, target FROM relationships "
        "WHERE type='contradicts' AND confidence='high'"
    )
    edges = cur.fetchall()
    conn.close()

    edge_set: set[tuple[str, str]] = set(edges)

    pairs: list[tuple[dict, dict]] = []
    seen: set[tuple[str, str]] = set()

    for source_slug, target_claim in edges:
        a = by_slug.get(source_slug)
        if not a:
            continue
        b = by_h1.get(target_claim)
        if not b:
            continue
        if is_archived(a) or is_archived(b):
            continue

        # Reverse edge check: (b.slug, a.h1) must also exist
        if (b["slug"], a["h1"]) not in edge_set:
            continue

        canonical = tuple(sorted([a["slug"], b["slug"]]))
        if canonical in seen or canonical in resolved_set:
            continue
        seen.add(canonical)

        pairs.append((a, b))
        if len(pairs) >= limit:
            break

    return pairs


def detect_random(
    by_slug: dict, by_h1: dict, limit: int = 25,
    resolved_set: Optional[set[tuple[str, str]]] = None,
) -> list[tuple[dict, dict]]:
    """Uniform random sample of high-confidence contradicts pairs."""
    import random

    if resolved_set is None:
        resolved_set = set()

    conn = sqlite3.connect(GRAPH_DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT source, target FROM relationships "
        "WHERE type='contradicts' AND confidence='high'"
    )
    edges = cur.fetchall()
    conn.close()

    random.shuffle(edges)
    pairs: list[tuple[dict, dict]] = []
    seen: set[tuple[str, str]] = set()

    for source_slug, target_claim in edges:
        a = by_slug.get(source_slug)
        b = by_h1.get(target_claim)
        if not a or not b:
            continue
        if is_archived(a) or is_archived(b):
            continue

        canonical = tuple(sorted([a["slug"], b["slug"]]))
        if canonical in seen or canonical in resolved_set:
            continue
        seen.add(canonical)

        pairs.append((a, b))
        if len(pairs) >= limit:
            break

    return pairs


def format_queue(pairs: list[tuple[dict, dict]], strategy: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    out: list[str] = []
    out.append(
        f"""---
nexus:
  - ora
type: working
tags:
  - engram-cleaning
date created: {today}
date modified: {today}
---

# Engram Cleaning Queue — {today}

*Generated by Framework — Engram Cleaning detection phase. Strategy: `{strategy}`. Pairs: {len(pairs)}.*

For each pair below, edit the **Resolution** line. Replace `[pending]` with one of:
- `[changed-mind:source-supersedes-target]` — source claim is your current position; target is older thinking
- `[changed-mind:target-supersedes-source]` — target claim is your current position; source is older thinking
- `[hypocrisy]` — both are positions you hold; the contradiction reflects motivated reasoning or genuine tension to examine
- `[wrong:source]` — source is incorrect; archive it
- `[wrong:target]` — target is incorrect; archive it
- `[skip]` — defer; remove from this queue without action

When done, run the resolver: `python3 ~/ora/orchestrator/historical/run_engram_cleaning_resolver.py`

---
"""
    )

    for a, b in pairs:
        a_dm = a["frontmatter"].get("date modified", "?")
        b_dm = b["frontmatter"].get("date modified", "?")
        a_prov = provenance_tag(a)
        b_prov = provenance_tag(b)

        # Truncate source claim for heading display
        a_h1_short = a["h1"][:80] + ("..." if len(a["h1"]) > 80 else "")

        out.append(
            f"""## [pending] {a_h1_short}

- **Source:** [[{a['slug']}]] (modified {a_dm}, provenance: {a_prov})
  *{a['h1']}*
- **Target:** [[{b['slug']}]] (modified {b_dm}, provenance: {b_prov})
  *{b['h1']}*
- **Confidence:** high
- **Strategy:** {strategy}

**Resolution:** [pending]

---
"""
        )

    return "\n".join(out)


def run_detection(strategy: str = "bidirectional", limit: int = 25,
                  write_queue: bool = True,
                  include_skipped: bool = False) -> dict:
    """Public callable for the slash-command handler and CLI.

    By default, pairs that appear in the resolution log are filtered out
    (so previously-resolved pairs don't resurface). Pass ``include_skipped=True``
    to disable that filter and re-surface every candidate pair.

    Returns a dict with: strategy, limit, engram_count, pairs_count,
    resolved_filtered_count, queue_path (if write_queue=True),
    pairs (raw list when write_queue=False).
    """
    by_slug, by_h1 = build_engram_index()
    resolved_set = set() if include_skipped else _load_resolved_pair_set()

    if strategy == "bidirectional":
        pairs = detect_bidirectional(
            by_slug, by_h1, limit=limit, resolved_set=resolved_set
        )
    else:
        pairs = detect_random(
            by_slug, by_h1, limit=limit, resolved_set=resolved_set
        )

    result: dict = {
        "strategy": strategy,
        "limit": limit,
        "engram_count": len(by_slug),
        "pairs_count": len(pairs),
        "resolved_filtered_count": len(resolved_set),
    }

    if write_queue:
        queue_md = format_queue(pairs, strategy=strategy)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write(queue_md)
        result["queue_path"] = QUEUE_FILE
    else:
        result["pairs"] = pairs

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25, help="Max pairs to surface")
    ap.add_argument(
        "--strategy",
        default="bidirectional",
        choices=["bidirectional", "random"],
        help="Prioritization strategy",
    )
    ap.add_argument(
        "--include-skipped",
        action="store_true",
        help="Re-surface previously-resolved pairs (default: filter them via the log)",
    )
    args = ap.parse_args()

    print(f"Building engram index from {ENGRAMS_DIR}...")
    result = run_detection(
        strategy=args.strategy,
        limit=args.limit,
        write_queue=True,
        include_skipped=args.include_skipped,
    )
    print(f"  {result['engram_count']} engrams indexed")
    if not args.include_skipped:
        print(f"  Filtered {result['resolved_filtered_count']} previously-resolved pairs from log")
    print(f"  Surfaced {result['pairs_count']} pairs")
    print(f"\nWrote queue to: {result['queue_path']}")
    print("\nNext step: review the queue and edit each pair's Resolution line,")
    print("then run the resolver:")
    print("  python3 ~/ora/orchestrator/historical/run_engram_cleaning_resolver.py")


if __name__ == "__main__":
    main()
