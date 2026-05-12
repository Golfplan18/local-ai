#!/usr/bin/env python3
"""Parameter sweep: load all days once, run cascade at multiple parameter
settings, print a comparison table.

Usage:
    python3 sweep.py 2026-03-09 2026-03-10 ... 2026-03-15
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import datetime

from calibration import (
    CalibrationParams,
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


def run_cascade_in_memory(stories, params: CalibrationParams) -> int:
    current = stories
    for fn in (
        stage_a_national_importance,
        stage_b_source_verification,
        stage_c_newsworthiness_signals,
        stage_d_substantive_theme,
        stage_e_diversity_cap,
        stage_f_final_cap,
    ):
        current, _ = fn(current, params)
    return len(current)


def is_weekend(date_str: str) -> bool:
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5


@dataclass
class Variation:
    label: str
    params: CalibrationParams


def make_variations(base: CalibrationParams) -> list[Variation]:
    return [
        Variation("Baseline (outlets≥2, ment≥10, sources≥3, gold≥1.0)", base),

        # Outlets≥5 family — for the link-list UI (top-5 above-fold)
        Variation("outlets≥5 (1 param dialed)",
                  replace(base, min_distinct_outlets=5)),
        Variation("outlets≥5 + ment≥20 (2 params)",
                  replace(base, min_distinct_outlets=5, min_total_num_mentions=20)),
        Variation("outlets≥5 + ment≥20 + gold≥2.0 (3 params)",
                  replace(base, min_distinct_outlets=5, min_total_num_mentions=20,
                          min_abs_goldstein=2.0)),
        Variation("outlets≥5 + ment≥20 + gold≥2.0 + sources≥5 (4 params)",
                  replace(base, min_distinct_outlets=5, min_total_num_mentions=20,
                          min_abs_goldstein=2.0, min_distinct_sources_total=5)),
        Variation("outlets≥5 + ment≥30 + gold≥2.0 + sources≥5 (4 params, tighter)",
                  replace(base, min_distinct_outlets=5, min_total_num_mentions=30,
                          min_abs_goldstein=2.0, min_distinct_sources_total=5)),
        Variation("outlets≥5 + ment≥30 + gold≥3.0 + sources≥7 (4 params, max)",
                  replace(base, min_distinct_outlets=5, min_total_num_mentions=30,
                          min_abs_goldstein=3.0, min_distinct_sources_total=7)),

        # For reference — the 4-param option you flagged with outlets≥3
        Variation("outlets≥3 + ment≥30 + gold≥2.0 + sources≥5 (your earlier flag)",
                  replace(base, min_distinct_outlets=3, min_total_num_mentions=30,
                          min_abs_goldstein=2.0, min_distinct_sources_total=5)),
    ]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: sweep.py YYYY-MM-DD [YYYY-MM-DD ...]\n")
        return 2
    dates = argv[1:]

    print(f"Loading {len(dates)} day(s)...", file=sys.stderr)
    per_day_stories = {}
    for d in dates:
        day = load_day(d)
        articles = join_events_to_gkg(day)
        stories = cluster_into_stories(articles)
        per_day_stories[d] = stories
        print(f"  {d}: {len(stories):,} initial stories", file=sys.stderr)

    base = CalibrationParams()
    variations = make_variations(base)

    weekdays = [d for d in dates if not is_weekend(d)]
    weekends = [d for d in dates if is_weekend(d)]

    # Header
    print()
    header = f"{'VARIATION':<55}  "
    for d in dates:
        dow = datetime.strptime(d, "%Y-%m-%d").strftime("%a")
        header += f"{dow:>6s}  "
    header += f"{'WkAvg':>7s}  {'WeAvg':>7s}  {'AllAvg':>7s}"
    print(header)
    print("-" * len(header))

    for v in variations:
        counts = {d: run_cascade_in_memory(per_day_stories[d], v.params) for d in dates}
        wk = [counts[d] for d in weekdays]
        we = [counts[d] for d in weekends]
        all_vals = list(counts.values())

        row = f"{v.label:<55}  "
        for d in dates:
            row += f"{counts[d]:>6d}  "
        row += f"{sum(wk)/len(wk):>7.1f}  " if wk else f"{'-':>7s}  "
        row += f"{sum(we)/len(we):>7.1f}  " if we else f"{'-':>7s}  "
        row += f"{sum(all_vals)/len(all_vals):>7.1f}"
        print(row)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
