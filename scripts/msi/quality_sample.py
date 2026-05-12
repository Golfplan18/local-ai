#!/usr/bin/env python3
"""Quality sample report: dump every story that survives the chosen calibration
settings, with enough metadata per story to sanity-check that the cascade is
keeping the right stories.

Usage:
    python3 quality_sample.py 2026-03-12
"""

from __future__ import annotations

import sys
from collections import Counter
from urllib.parse import urlparse

from calibration import (
    CalibrationParams,
    Story,
    cluster_into_stories,
    join_events_to_gkg,
    load_day,
    stage_a_national_importance,
    stage_b_source_verification,
    stage_c_newsworthiness_signals,
    stage_d_substantive_theme,
    stage_e_diversity_cap,
    stage_f_final_cap,
)

# Committed calibration settings (the 4-parameter setting per 2026-05-11 decision)
CHOSEN_PARAMS = CalibrationParams(
    min_distinct_outlets=5,
    min_total_num_mentions=30,
    min_abs_goldstein=2.0,
    min_distinct_sources_total=5,
)

# Outlets whose presence in a story's source list helps the reader trust the cluster.
# Used to format the "domains" line in priority order. Loose first-pass; will be
# replaced once the formal display_rank list is added to source-reliability-tiers.json.
PRIORITY_OUTLETS_ORDER = [
    "apnews.com", "reuters.com", "nytimes.com", "washingtonpost.com",
    "wsj.com", "bloomberg.com", "bbc.com", "bbc.co.uk", "npr.org",
    "pbs.org", "abcnews.go.com", "cbsnews.com", "nbcnews.com",
    "politico.com", "thehill.com", "axios.com", "cnn.com",
    "msnbc.com", "foxnews.com", "usatoday.com", "theatlantic.com",
    "newyorker.com", "propublica.org", "kffhealthnews.org",
    "calmatters.org", "bellingcat.com", "icij.org", "lawfaremedia.org",
    "scotusblog.com", "stat-news.com", "vox.com",
]


def slug_from_url(url: str) -> str:
    """Extract a readable slug from the URL — the last path segment, cleaned."""
    try:
        path = urlparse(url).path
    except ValueError:
        return ""
    seg = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
    seg = seg.split(".")[0]
    if "-" in seg or "_" in seg:
        seg = seg.replace("-", " ").replace("_", " ")
    if len(seg) > 12:
        return seg
    return ""


def domain_priority_key(domain: str) -> tuple[int, str]:
    try:
        return (PRIORITY_OUTLETS_ORDER.index(domain), domain)
    except ValueError:
        return (len(PRIORITY_OUTLETS_ORDER), domain)


def format_story_block(story: Story, idx: int) -> str:
    sorted_domains = sorted(story.distinct_domains, key=domain_priority_key)
    top_persons = ", ".join(story.aggregated_persons[:3]) or "—"
    top_orgs = ", ".join(story.aggregated_orgs[:3]) or "—"
    top_themes = ", ".join(t for t in story.aggregated_themes[:5] if t)
    domains_line = ", ".join(sorted_domains[:8])
    if len(sorted_domains) > 8:
        domains_line += f" (+{len(sorted_domains) - 8} more)"

    sample_urls = [a.url for a in story.articles[:3]]
    slugs = [slug_from_url(u) for u in sample_urls]
    slug_line = " | ".join(s for s in slugs if s)[:160]

    lines = [
        f"[{idx:>3d}] outlets:{len(story.distinct_outlets):>2d}  "
        f"ment:{story.total_num_mentions:>4d}  "
        f"src:{story.total_num_sources:>3d}  "
        f"|gold|:{story.max_abs_goldstein:>4.1f}  "
        f"|  primary entity: {story.primary_entity[:50]}",
        f"      domains:  {domains_line}",
        f"      persons:  {top_persons}",
        f"      orgs:     {top_orgs}",
        f"      themes:   {top_themes}",
    ]
    if slug_line:
        lines.append(f"      slug:     {slug_line}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: quality_sample.py YYYY-MM-DD\n")
        return 2
    date_str = argv[1]

    print(f"Loading {date_str}...", file=sys.stderr)
    day = load_day(date_str)
    articles = join_events_to_gkg(day)
    stories = cluster_into_stories(articles)
    print(f"  {len(stories):,} initial stories", file=sys.stderr)

    current = stories
    for fn in (
        stage_a_national_importance,
        stage_b_source_verification,
        stage_c_newsworthiness_signals,
        stage_d_substantive_theme,
        stage_e_diversity_cap,
        stage_f_final_cap,
    ):
        current, _ = fn(current, CHOSEN_PARAMS)

    final = current
    final.sort(
        key=lambda s: (
            s.total_num_mentions
            + 5 * s.max_abs_goldstein
            + len(s.distinct_outlets)
        ),
        reverse=True,
    )

    print(f"\n=== {date_str} — {len(final)} stories pass the calibrated filter ===")
    print(f"Settings: outlets≥{CHOSEN_PARAMS.min_distinct_outlets}, "
          f"mentions≥{CHOSEN_PARAMS.min_total_num_mentions}, "
          f"|Goldstein|≥{CHOSEN_PARAMS.min_abs_goldstein}, "
          f"sources≥{CHOSEN_PARAMS.min_distinct_sources_total}\n")

    for i, s in enumerate(final, start=1):
        print(format_story_block(s, i))
        print()

    # Brief summary stats
    avg_outlets = sum(len(s.distinct_outlets) for s in final) / len(final) if final else 0
    avg_mentions = sum(s.total_num_mentions for s in final) / len(final) if final else 0
    theme_counter: Counter[str] = Counter()
    for s in final:
        theme_counter.update(s.aggregated_themes[:3])

    print("=" * 78)
    print(f"SUMMARY for {date_str}:")
    print(f"  Final story count:           {len(final)}")
    print(f"  Avg outlets per story:       {avg_outlets:.1f}")
    print(f"  Avg total mentions per story: {avg_mentions:.1f}")
    print(f"  Top themes across all stories:")
    for theme, count in theme_counter.most_common(15):
        print(f"    {count:>4d}  {theme}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
