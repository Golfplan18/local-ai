"""Phase 3 — Article-analysis algorithm for the MSI data-viz pipeline.

Reads a published article's structured content (headline + lede +
nut_graf + atomic_claims) and decides which FRED data visualizations
(if any) materially aid reader understanding. For each opportunity,
invokes the Phase 4 chart emitter and returns the populated figureSchema
list ready to drop into the article frontmatter's `figures` field.

The classifier uses one local-model call (sidebar slot per the existing
slot architecture — Qwen3.5-27B; free, fast, deterministic-ish) per
article. The prompt frames it as: "Charts only when they materially
aid reader understanding of an economic claim. Geopolitics, criminal
justice, sports, and other non-quantitative subjects → return empty
list." This implements the publisher's guardrail from the 2026-05-12
handoff §3 ("a chart of meaningless data serves no one").

What this module DOES:
  - Decide if an article warrants charts (binary)
  - Select up to N indicators from the curated INDICATOR_CATALOG
  - Specify the transformation (raw / yoy_pct / first_diff / ytd)
    and a one-sentence editorial justification per opportunity
  - Invoke the Phase 4 chart emitter for each accepted opportunity
  - Return the figureSchema list and a per-opportunity result log

What this module DOES NOT do:
  - Author the article body (that's the article-generator framework)
  - Patch the article's .md file (the slash-command wrapper does that
    when it knows the article path)
  - Decide on illustrations/cartoons (that's render_news_image /
    render_hector_cartoon — independent paths, tried only when this
    classifier returns zero opportunities)

Per:
  - Handoff — MSI Data Visualization Pipeline 2026-05-12.md §3, §6, Phase 3
  - Reference — MSI Data Source Catalog.md (categories + linked-research)
  - Reference — MSI Distributional Honesty Research Library.md (Reports
    3.1, 3.9 — methodological + adversarial-review reference)
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

# Local module imports — adapt to whichever sys.path config invokes us
try:
    from data_viz_render import (
        FigureRequest, FigureResult, render_figure,
    )
    from integrations.fred_api import SeriesQuery
except ImportError:
    from orchestrator.data_viz_render import (
        FigureRequest, FigureResult, render_figure,
    )
    from orchestrator.integrations.fred_api import SeriesQuery


# ---------------------------------------------------------------------------
# Indicator catalog — curated subset of the data catalog's Categories 1-3
# ---------------------------------------------------------------------------
#
# This is the universe of FRED series the classifier may select from.
# Sourced from Reference — MSI Data Source Catalog.md Categories 1-3
# (the only categories built; Categories 4-9 will populate this catalog
# as they're authored). Each entry is intentionally compact — the model
# sees this list in the prompt and chooses among it.
#
# Adding a new indicator: append a dict here. The classifier prompt
# automatically picks up additions; no separate registration step.

INDICATOR_CATALOG = [
    # --- Macro Headline ---
    {
        "series_id": "GDPC1",
        "name": "Real Gross Domestic Product",
        "category": "macro_headline",
        "topics": ["beyond-gdp", "distributional-methodology"],
        "covers": "GDP growth, recession watch, 'is the economy growing'",
        "default_transformation": "raw",
        "linked_reports": ["1.1", "1.2", "1.4"],
        "framework_points": [1, 7, 8],
    },
    {
        "series_id": "GDI",
        "name": "Gross Domestic Income (real)",
        "category": "macro_headline",
        "topics": ["distributional-methodology"],
        "covers": "wage-income side of GDP; pair with GDP for divergence stories",
        "default_transformation": "raw",
        "linked_reports": ["1.1", "1.4"],
        "framework_points": [1, 6],
    },
    {
        "series_id": "PAYEMS",
        "name": "Total Nonfarm Payrolls",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "monthly jobs report headline; jobs added/lost",
        "default_transformation": "first_diff",
        "linked_reports": ["1.3"],
        "framework_points": [1, 7, 14],
    },
    {
        "series_id": "UNRATE",
        "name": "Unemployment Rate (U-3)",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "official unemployment rate; load-bearing pair with LFPR + EPOP",
        "default_transformation": "raw",
        "linked_reports": ["1.3"],
        "framework_points": [1, 7, 9],
    },
    {
        "series_id": "U6RATE",
        "name": "Unemployment Rate (U-6, broader)",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "broader underemployment incl. discouraged + involuntary part-time",
        "default_transformation": "raw",
        "linked_reports": ["1.3"],
        "framework_points": [9, 11],
    },
    {
        "series_id": "CIVPART",
        "name": "Labor Force Participation Rate",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "share of population in labor force; the silent denominator behind U-3",
        "default_transformation": "raw",
        "linked_reports": ["1.3"],
        "framework_points": [9, 11],
    },
    {
        "series_id": "LNS12300060",
        "name": "Prime-age (25-54) Employment-Population Ratio",
        "category": "employment_labor",
        "topics": ["labor-market-measurement", "demographics-generations"],
        "covers": "preferred slack measure; bypasses participation problem in U-3",
        "default_transformation": "raw",
        "linked_reports": ["1.3", "2.15"],
        "framework_points": [4, 9],
    },
    {
        "series_id": "JTSQUL",
        "name": "JOLTS Quits Rate",
        "category": "employment_labor",
        "topics": ["labor-standards", "worker-power"],
        "covers": "voluntary separations as % of employment; worker bargaining power signal",
        "default_transformation": "raw",
        "linked_reports": ["1.3", "2.11"],
        "framework_points": [2, 11],
    },
    {
        "series_id": "ICSA",
        "name": "Initial Jobless Claims",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "weekly real-time labor-market signal; AI-displacement early warning",
        "default_transformation": "raw",
        "linked_reports": ["1.3"],
        "framework_points": [7, 8],
    },
    # --- Wage growth ---
    {
        "series_id": "FRBATLWGT3MMAUMHWGO",
        "name": "Atlanta Fed Wage Growth Tracker (median, 3-month MA)",
        "category": "employment_labor",
        "topics": ["labor-standards", "worker-power"],
        "covers": "composition-adjusted wage growth for median continuously-employed worker",
        "default_transformation": "raw",
        "linked_reports": ["1.3", "2.11"],
        "framework_points": [2, 6],
    },
    {
        "series_id": "OPHNFB",
        "name": "Nonfarm Business Productivity (output per hour)",
        "category": "macro_headline",
        "topics": ["labor-standards", "labor-economics"],
        "covers": "productivity-wage decoupling chart anchor; pair with real wages",
        "default_transformation": "raw",
        "linked_reports": ["2.11"],
        "framework_points": [6],
    },
    # --- Rates & yields ---
    {
        "series_id": "FEDFUNDS",
        "name": "Federal Funds Rate (effective, monthly avg)",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "Fed policy lever; FOMC rate decisions; mortgage transmission stories",
        "default_transformation": "raw",
        "linked_reports": ["2.5"],
        "framework_points": [13],
    },
    {
        "series_id": "DGS10",
        "name": "10-Year Treasury Yield",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "benchmark long-term yield; sets mortgage rates and corp borrowing",
        "default_transformation": "raw",
        "linked_reports": ["2.5"],
        "framework_points": [13],
    },
    {
        "series_id": "T10Y2Y",
        "name": "10-Year minus 2-Year Treasury Spread",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "yield-curve recession-prediction signal; pair with Sahm/NY-Fed-prob",
        "default_transformation": "raw",
        "linked_reports": ["2.5"],
        "framework_points": [7, 13],
    },
    {
        "series_id": "DFII10",
        "name": "10-Year Real Yield (TIPS)",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "real cost of capital; long-run redistribution signal",
        "default_transformation": "raw",
        "linked_reports": ["2.5"],
        "framework_points": [13],
    },
    {
        "series_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Rate",
        "category": "rates_yields",
        "topics": ["housing", "monetary-policy"],
        "covers": "household-affordability rate; pair with median home price",
        "default_transformation": "raw",
        "linked_reports": ["2.5", "2.8"],
        "framework_points": [4, 13],
    },
    {
        "series_id": "WALCL",
        "name": "Federal Reserve Total Assets (Balance Sheet)",
        "category": "rates_yields",
        "topics": ["monetary-policy", "financial-regulation"],
        "covers": "QE/QT scale; redistribution-policy indicator post-2008",
        "default_transformation": "raw",
        "linked_reports": ["2.5", "2.14"],
        "framework_points": [11, 13],
    },
    # --- Inflation ---
    {
        "series_id": "CPIAUCSL",
        "name": "Consumer Price Index (all urban consumers)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement"],
        "covers": "headline CPI; year-over-year inflation reporting",
        "default_transformation": "yoy_pct",
        "linked_reports": ["1.5"],
        "framework_points": [3, 9],
    },
    {
        "series_id": "CPILFESL",
        "name": "Core CPI (all items less food and energy)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement"],
        "covers": "core CPI; the underlying-inflation reading the Fed watches; pair with shelter",
        "default_transformation": "yoy_pct",
        "linked_reports": ["1.5"],
        "framework_points": [3, 9],
    },
    {
        "series_id": "PCEPI",
        "name": "PCE Price Index (Fed's preferred inflation gauge)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement", "monetary-policy"],
        "covers": "Fed inflation target reference; pair with CPI for divergence stories",
        "default_transformation": "yoy_pct",
        "linked_reports": ["1.5", "2.5"],
        "framework_points": [3, 13],
    },
    {
        "series_id": "PCEPILFE",
        "name": "Core PCE (PCE less food and energy)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement", "monetary-policy"],
        "covers": "Fed's actual operational inflation target; the headline-vs-target divergence anchor",
        "default_transformation": "yoy_pct",
        "linked_reports": ["1.5", "2.5"],
        "framework_points": [3, 13],
    },
    {
        "series_id": "MICH",
        "name": "U. Michigan 1-year Inflation Expectations (median)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement"],
        "covers": "household 1-year-ahead inflation expectations; surfaces anchoring/de-anchoring",
        "default_transformation": "raw",
        "linked_reports": ["1.5"],
        "framework_points": [12],
    },
    # --- Housing ---
    {
        "series_id": "CSUSHPISA",
        "name": "Case-Shiller U.S. National Home Price Index (SA)",
        "category": "housing",
        "topics": ["housing", "asset-prices"],
        "covers": "national house-price index; the asset-side of the asset-vs-wage framing",
        "default_transformation": "yoy_pct",
        "linked_reports": ["2.8", "1.4"],
        "framework_points": [3, 4],
    },
    {
        "series_id": "MSPUS",
        "name": "Median Sales Price of Houses Sold",
        "category": "housing",
        "topics": ["housing"],
        "covers": "raw dollar median home price; preferred over indices when affordability is the story",
        "default_transformation": "raw",
        "linked_reports": ["2.8"],
        "framework_points": [4, 14],
    },
    {
        "series_id": "HOUST",
        "name": "Housing Starts (Total, Privately-Owned)",
        "category": "housing",
        "topics": ["housing"],
        "covers": "supply-side construction signal; pair with MSPUS for affordability narratives",
        "default_transformation": "raw",
        "linked_reports": ["2.8"],
        "framework_points": [14],
    },
    # --- Consumer ---
    {
        "series_id": "RSAFS",
        "name": "Advance Retail Sales (Retail + Food Services)",
        "category": "consumer",
        "topics": ["consumer-spending"],
        "covers": "monthly retail sales headline; consumer-demand pulse; distributional-honesty caveat applies",
        "default_transformation": "yoy_pct",
        "linked_reports": ["1.4"],
        "framework_points": [1, 10],
    },
    {
        "series_id": "UMCSENT",
        "name": "U. Michigan Consumer Sentiment",
        "category": "consumer",
        "topics": ["consumer-spending", "distributional-methodology"],
        "covers": "household-sentiment index; the workers'-mood gap vs. macro headlines (K-shaped framing)",
        "default_transformation": "raw",
        "linked_reports": ["1.4"],
        "framework_points": [1, 4, 10],
    },
    {
        "series_id": "PSAVERT",
        "name": "Personal Saving Rate",
        "category": "consumer",
        "topics": ["consumer-spending", "distributional-methodology"],
        "covers": "household saving as % of disposable income; surfaces pandemic-era depletion story",
        "default_transformation": "raw",
        "linked_reports": ["1.4"],
        "framework_points": [4, 10],
    },
    # --- Trade ---
    {
        "series_id": "DTWEXBGS",
        "name": "Trade-Weighted U.S. Dollar Index (Broad)",
        "category": "trade",
        "topics": ["trade", "monetary-policy"],
        "covers": "broad dollar strength; sets the cost of imports and the value of overseas earnings",
        "default_transformation": "raw",
        "linked_reports": ["2.6", "2.5"],
        "framework_points": [13],
    },
    {
        "series_id": "NETEXP",
        "name": "Net Exports of Goods and Services",
        "category": "trade",
        "topics": ["trade"],
        "covers": "trade balance; structural deficit story; pair with USD index for revaluation effects",
        "default_transformation": "raw",
        "linked_reports": ["2.6"],
        "framework_points": [1],
    },
    # --- Money & Credit ---
    {
        "series_id": "M2SL",
        "name": "M2 Money Stock",
        "category": "money_credit",
        "topics": ["monetary-policy"],
        "covers": "broad money supply; reject the simplistic M2-causes-inflation frame, use for velocity context",
        "default_transformation": "yoy_pct",
        "linked_reports": ["2.5"],
        "framework_points": [13],
    },
    {
        "series_id": "TOTBKCR",
        "name": "Bank Credit, All Commercial Banks",
        "category": "money_credit",
        "topics": ["financial-regulation", "monetary-policy"],
        "covers": "commercial-bank credit aggregate; lending channel of monetary transmission",
        "default_transformation": "yoy_pct",
        "linked_reports": ["2.5", "2.14"],
        "framework_points": [13],
    },
    # --- Markets ---
    {
        "series_id": "SP500",
        "name": "S&P 500 Index",
        "category": "markets",
        "topics": ["asset-prices", "distributional-methodology"],
        "covers": "large-cap equity benchmark; the asset-vs-wage framing (point 3); top-10%-of-households exposure",
        "default_transformation": "raw",
        "linked_reports": ["1.4", "2.5"],
        "framework_points": [3, 4],
    },
    {
        "series_id": "NASDAQCOM",
        "name": "NASDAQ Composite Index",
        "category": "markets",
        "topics": ["asset-prices"],
        "covers": "tech-heavy equity index; rate-sensitive cohort; pair with DFII10 for valuation stories",
        "default_transformation": "raw",
        "linked_reports": ["1.4", "2.5"],
        "framework_points": [3, 4],
    },
    {
        "series_id": "DJIA",
        "name": "Dow Jones Industrial Average",
        "category": "markets",
        "topics": ["asset-prices"],
        "covers": "30-stock price-weighted blue-chip index; populist headline reference, less analytical signal",
        "default_transformation": "raw",
        "linked_reports": ["1.4"],
        "framework_points": [3, 4],
    },
]


# ---------------------------------------------------------------------------
# Objective ranking — Phase 1: topic-overlap + name-match scoring
# ---------------------------------------------------------------------------
#
# Replaces the previous model-judgment classifier with a research-grounded
# scoring function. Indicators are ranked by:
#   (a) name_match: does the article's atomic_claims directly cite the
#       indicator (e.g., "Consumer Price Index" mentioned → CPIAUCSL).
#       Strongest signal — the article is explicitly about this measure.
#   (b) topic_overlap: do the indicator's topics (kebab-case) match the
#       article's primary_themes (snake_case, with synonym expansion to
#       bridge the two vocabularies)?
#
# Phase 2 will add semantic embedding-based claim matching; Phase 3 will
# add research-library citation alignment; Phase 4 will add framework-
# point scoring. The model becomes a NARRATOR of the rankings (writing
# per-pick justifications), not a JUDGE picking the indicators.

# Bridges article-side theme vocabulary (snake_case, narrative-derived)
# to catalog-side topic vocabulary (kebab-case, framework-derived).
# Each MSI primary_theme expands to one or more catalog topics. Extend
# this map as new article themes surface in the publication's coverage.
_THEME_TO_TOPICS: dict[str, list[str]] = {
    "inflation_measurement": ["inflation-measurement"],
    "monetary_policy": ["monetary-policy"],
    "shelter_inflation": ["housing", "inflation-measurement"],
    "k_shaped_consumer": ["distributional-methodology", "consumer-spending"],
    "fed_rate_path": ["monetary-policy"],
    "labor_market_measurement": ["labor-market-measurement"],
    "wage_growth": ["labor-standards", "worker-power"],
    "productivity_wage_decoupling": ["labor-standards", "labor-economics"],
    "asset_prices": ["asset-prices"],
    "housing_affordability": ["housing", "distributional-methodology"],
    "consumer_spending": ["consumer-spending"],
    "trade_deficit": ["trade"],
    "money_supply": ["monetary-policy"],
    "financial_regulation": ["financial-regulation"],
    "beyond_gdp": ["beyond-gdp", "distributional-methodology"],
    "demographics": ["demographics-generations"],
}


def _normalize_topic(token: str) -> str:
    """Normalize a topic/theme token to a canonical kebab-case form."""
    return token.lower().replace("_", "-").strip()


def _expand_article_topics(article_themes: list[str]) -> set[str]:
    """Expand article primary_themes into the catalog's topic vocabulary
    via the synonym map. Themes with no mapping fall through as-is
    (normalized to kebab-case)."""
    expanded: set[str] = set()
    for theme in article_themes or []:
        norm = _normalize_topic(theme)
        expanded.add(norm)
        # Apply synonym expansion on the un-normalized snake_case key too
        mapped = _THEME_TO_TOPICS.get(theme) or _THEME_TO_TOPICS.get(norm.replace("-", "_"))
        if mapped:
            for t in mapped:
                expanded.add(_normalize_topic(t))
    return expanded


def _diagnostic_phrases(entry: dict) -> set[str]:
    """Distinctive phrases that, if mentioned in article claims, mark
    the article as directly about this indicator.

    Includes: the FRED series_id; the full name; parenthetical contents
    (often abbreviations like "(U-3)" or "(PCE)"); all bigrams and
    trigrams from the name; all-caps tokens / tokens containing digits
    (likely existing abbreviations like "PCE", "U6", "M2"); and a
    synthesised first-letter acronym from the cleaned name when none
    already exists (e.g. Consumer Price Index → CPI).

    Phrases shorter than 3 characters are dropped — they create false
    positives via substring matches (e.g., "sa" inside "said").
    """
    phrases: set[str] = set()
    sid = (entry.get("series_id") or "").strip()
    if sid and len(sid) >= 3:
        phrases.add(sid.lower())
    name = (entry.get("name") or "")
    # Parenthetical contents — qualifiers and abbreviations.
    for match in re.findall(r"\(([^)]+)\)", name):
        for part in re.split(r"[,;]", match):
            part = part.strip()
            if part and len(part) >= 3:
                phrases.add(part.lower())
    # Cleaned name (parenthetical stripped).
    name_clean = re.sub(r"\([^)]*\)", "", name).strip()
    if name_clean:
        if len(name_clean) >= 3:
            phrases.add(name_clean.lower())
        words = [w for w in name_clean.split() if len(w) > 1]
        # Likely-abbreviation single tokens (all-caps or contains digit).
        already_has_acronym = False
        for w in words:
            if len(w) >= 3 and (w.isupper() or any(c.isdigit() for c in w)):
                phrases.add(w.lower())
                already_has_acronym = True
        # Synthesised first-letter acronym (only when no existing
        # acronym token; otherwise we'd duplicate-coin nonsense like
        # PPI from "PCE Price Index").
        if not already_has_acronym and words and all(w[0].isupper() for w in words):
            acronym = "".join(w[0] for w in words)
            if len(acronym) >= 3:
                phrases.add(acronym.lower())
        # All bigrams + trigrams in the name.
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}".lower()
            if len(bigram) >= 3:
                phrases.add(bigram)
        for i in range(len(words) - 2):
            phrases.add(f"{words[i]} {words[i+1]} {words[i+2]}".lower())
    return phrases


def _name_match_score(entry: dict, atomic_claims: list[dict]
                       ) -> tuple[float, list[str], list[int]]:
    """Score the indicator by how many atomic claims directly mention it.

    Returns (score, matched_phrase_list, matched_claim_indices).
    matched_claim_indices is the list of indices into atomic_claims that
    contributed to the score — used downstream by fact_check to compare
    article-prose values to FRED values per claim. Strongest possible
    signal: an article explicitly citing "Consumer Price Index" is
    self-evidently about CPI. Score is normalized: count_matched_claims /
    total_claims, with a floor of 0 when no claims.
    """
    if not atomic_claims:
        return (0.0, [], [])
    phrases = _diagnostic_phrases(entry)
    if not phrases:
        return (0.0, [], [])

    matched_claims = 0
    matched_phrases: set[str] = set()
    matched_indices: list[int] = []
    for i, claim in enumerate(atomic_claims):
        if not isinstance(claim, dict):
            continue
        text = (claim.get("text") or "").lower()
        claim_matched = False
        for phrase in phrases:
            if not phrase or len(phrase) < 3:
                continue
            # Word-boundary match — avoids false positives like
            # "total" matching "totally" or "sa" matching "said".
            if re.search(r"\b" + re.escape(phrase) + r"\b", text):
                matched_phrases.add(phrase)
                claim_matched = True
        if claim_matched:
            matched_claims += 1
            matched_indices.append(i)
    return (
        matched_claims / len(atomic_claims),
        sorted(matched_phrases),
        matched_indices,
    )


def _topic_overlap_score(entry: dict, article_themes: list[str]) -> tuple[float, list[str]]:
    """Score by overlap between indicator topics and article primary_themes
    (with synonym expansion). Returns (score, matched_topic_list)."""
    indicator_topics = {_normalize_topic(t) for t in (entry.get("topics") or [])}
    if not indicator_topics:
        return (0.0, [])
    article_topics = _expand_article_topics(article_themes or [])
    if not article_topics:
        return (0.0, [])
    matched = indicator_topics & article_topics
    return (float(len(matched)), sorted(matched))


# Weights for ranking. name_match dominates when an article is
# explicitly about an indicator; topic_overlap fills in when the article
# touches an indicator's themes without naming it directly; semantic_match
# catches indirect / conceptual mentions the keyword logic misses;
# library_match grounds picks in the Distributional Honesty Research
# Library — indicators linked to the same research reports an article
# engages get boosted. Tunable per editorial taste over time.
_RANK_WEIGHT_NAME_MATCH = 3.0
_RANK_WEIGHT_TOPIC_OVERLAP = 1.0
_RANK_WEIGHT_SEMANTIC_MATCH = 2.0
_RANK_WEIGHT_LIBRARY_MATCH = 1.5
_RANK_WEIGHT_FRAMEWORK_ALIGNMENT = 1.0


# The 15-point editorial framework (Reference — MSI Data Source
# Catalog.md). Each catalog indicator carries a framework_points
# field listing which of these points it serves; the article-side
# _THEME_TO_FRAMEWORK_POINTS map resolves article themes to the same
# point IDs. Overlap → score.
_FRAMEWORK_POINTS = {
    1: "The data ≠ the welfare of the people",
    2: "Wage growth and velocity of money drive the real economy",
    3: "Asset prices belong in the inflation conversation (OER critique)",
    4: "The K-shaped economy is the actual structure",
    5: "Right-wing private-sector-first policy is testable",
    6: "Productivity-wage decoupling since the late 1970s is load-bearing",
    7: "Skeptical of headline-friendly volatile metrics",
    8: "Real-world context is part of the story",
    9: "Honest about indicator limitations",
    10: "Language: 'workers' and 'households,' not 'the consumer'",
    11: "The system is rigged against workers in its details",
    12: "Reject the financial-media frame",
    13: "Fed and economic policy is political choice presented as technical certainty",
    14: "Show raw counts alongside computed rates whenever possible",
    15: "Reference points should be substantive, not analyst-derived",
}


_THEME_TO_FRAMEWORK_POINTS: dict[str, list[int]] = {
    "inflation_measurement": [3, 9],
    "shelter_inflation": [3],
    "monetary_policy": [13],
    "fed_rate_path": [13],
    "money_supply": [13],
    "labor_market_measurement": [1, 7, 9],
    "wage_growth": [2, 6],
    "productivity_wage_decoupling": [6, 2],
    "k_shaped_consumer": [4, 10],
    "asset_prices": [3, 4],
    "beyond_gdp": [1],
    "housing_affordability": [4],
    "consumer_spending": [10],
    "trade_deficit": [13],
    "financial_regulation": [13],
    "demographics": [4],
}


def _expand_article_framework_points(article_themes: list[str]) -> set[int]:
    """Resolve article primary_themes to framework-point IDs via
    _THEME_TO_FRAMEWORK_POINTS. Unknown themes contribute nothing."""
    expanded: set[int] = set()
    for theme in article_themes or []:
        key = theme.strip()
        if not key:
            continue
        mapped = (
            _THEME_TO_FRAMEWORK_POINTS.get(key)
            or _THEME_TO_FRAMEWORK_POINTS.get(
                _normalize_topic(key).replace("-", "_")
            )
        )
        if mapped:
            for p in mapped:
                expanded.add(p)
    return expanded


def _framework_alignment_score(entry: dict,
                                article_themes: list[str],
                                ) -> tuple[float, list[int]]:
    """Score by overlap between the indicator's framework_points and
    the article's theme-mapped framework points.

    Returns (score, matched_points_list). Score normalized:
    |overlap| / |indicator.framework_points|, capped at 1.0.
    An indicator with no framework_points always scores 0.
    """
    indicator_points = set(entry.get("framework_points") or [])
    if not indicator_points:
        return (0.0, [])
    article_points = _expand_article_framework_points(article_themes or [])
    if not article_points:
        return (0.0, [])
    overlap = indicator_points & article_points
    score = len(overlap) / len(indicator_points)
    return (min(1.0, score), sorted(overlap))



# Bridges article-side primary_themes to specific reports in the
# Distributional Honesty Research Library (Sources/MSI Research/
# Distributional Library/). Each indicator carries a linked_reports
# field listing the report IDs it's methodologically anchored in;
# this map gives the corresponding chain from article themes to those
# reports. Extend as new themes surface in coverage.
_THEME_TO_REPORTS: dict[str, list[str]] = {
    # Inflation
    "inflation_measurement": ["1.5"],
    "shelter_inflation": ["2.8", "1.5"],
    # Monetary policy
    "monetary_policy": ["2.5"],
    "fed_rate_path": ["2.5"],
    "money_supply": ["2.5"],
    # Labor
    "labor_market_measurement": ["1.3"],
    "wage_growth": ["2.11", "1.3"],
    "productivity_wage_decoupling": ["2.11"],
    # Distributional / structural
    "k_shaped_consumer": ["1.4", "1.1"],
    "asset_prices": ["1.4", "2.5"],
    "beyond_gdp": ["1.2", "1.1"],
    "housing_affordability": ["2.8", "1.4"],
    "consumer_spending": ["1.4"],
    # Trade
    "trade_deficit": ["2.6"],
    # Regulation
    "financial_regulation": ["2.14"],
    # Demographics
    "demographics": ["2.15"],
}


def _expand_article_reports(article_themes: list[str]) -> set[str]:
    """Resolve article primary_themes to a set of Distributional Library
    report IDs via _THEME_TO_REPORTS. Unknown themes contribute nothing."""
    expanded: set[str] = set()
    for theme in article_themes or []:
        key = theme.strip()
        if not key:
            continue
        # Try the snake_case key directly first, then a normalized form.
        mapped = (
            _THEME_TO_REPORTS.get(key)
            or _THEME_TO_REPORTS.get(_normalize_topic(key).replace("-", "_"))
        )
        if mapped:
            for r in mapped:
                expanded.add(r)
    return expanded


def _library_match_score(entry: dict,
                          article_themes: list[str],
                          ) -> tuple[float, list[str]]:
    """Score by overlap between the indicator's linked_reports and the
    set of reports the article's themes map into.

    Returns (score, matched_reports_list). Score is normalized:
    |overlap| / |indicator.linked_reports|, capped at 1.0. An indicator
    with no linked_reports always scores 0.
    """
    indicator_reports = set(entry.get("linked_reports") or [])
    if not indicator_reports:
        return (0.0, [])
    article_reports = _expand_article_reports(article_themes or [])
    if not article_reports:
        return (0.0, [])
    overlap = indicator_reports & article_reports
    score = len(overlap) / len(indicator_reports)
    return (min(1.0, score), sorted(overlap))


# ---------------------------------------------------------------------------
# Phase 2 — semantic embedding match
# ---------------------------------------------------------------------------
#
# Embeds each indicator's identity (name + covers description) and each
# article's atomic claims via the canonical Ora embedding stack
# (nomic-embed-text via Ollama, see orchestrator/embedding.py). Computes
# cosine similarity between each (claim, indicator) pair and uses the
# MAX similarity per indicator as the semantic_match score.
#
# Failure mode: if Ollama is unreachable, semantic_match returns 0 for
# all indicators. Pipeline degrades gracefully to Phase 1 scoring (name
# + topic) — no hard failure.

_SEMANTIC_CACHE_DIR = os.path.expanduser("~/ora/cache/data-viz-embeddings")
# Threshold below which cosine similarity is treated as noise.
# nomic-embed-text returns similarities ~0.3-0.5 for unrelated texts;
# we want scores to only credit meaningful semantic overlap.
_SEMANTIC_NOISE_FLOOR = 0.5
# Similarity at which the semantic_match score reaches 1.0 (clamped).
_SEMANTIC_SATURATION = 0.8


def _indicator_embedding_text(entry: dict) -> str:
    """Build the text representation an indicator should be embedded as.

    Combines name + covers — name carries the formal identity, covers
    carries the editorial framing ("Fed inflation target reference; pair
    with CPI for divergence stories") which is rich semantic signal.
    """
    parts: list[str] = []
    name = (entry.get("name") or "").strip()
    if name:
        parts.append(name)
    covers = (entry.get("covers") or "").strip()
    if covers:
        parts.append(covers)
    return ". ".join(parts)


def _catalog_content_hash() -> str:
    """SHA256-prefix of the catalog content; used to key the embedding
    cache so a catalog edit forces a fresh embedding pass."""
    import hashlib
    blob = json.dumps(
        [(e.get("series_id"), e.get("name"), e.get("covers"))
         for e in INDICATOR_CATALOG],
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    """Plain Python cosine similarity. Returns 0 on missing / zero vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    import math
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a list of texts via the canonical Ora embedding function.

    Returns the list of embeddings (one per input) on success, or
    None if the embedder is unavailable (Ollama down / model not pulled).
    On None, callers degrade gracefully — semantic_match becomes 0.
    """
    try:
        from orchestrator.embedding import get_embedding_function
    except ImportError:
        try:
            from embedding import get_embedding_function
        except ImportError:
            return None
    try:
        ef = get_embedding_function()
        result = ef(texts)
        if not result:
            return None
        # Normalize to plain lists (handle numpy returns)
        out: list[list[float]] = []
        for v in result:
            out.append(v.tolist() if hasattr(v, "tolist") else list(v))
        return out
    except Exception:
        return None


def _load_or_compute_indicator_embeddings() -> dict[str, list[float]] | None:
    """Load catalog embeddings from disk cache, or compute + cache them.

    Cache key is a hash of the catalog's (series_id, name, covers)
    tuples — any edit invalidates the cache automatically.

    Returns a dict mapping series_id → embedding vector, or None when
    the embedder is unavailable.
    """
    cache_key = _catalog_content_hash()
    cache_path = os.path.join(_SEMANTIC_CACHE_DIR, f"catalog-{cache_key}.json")

    # Try cache
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and payload.get("embeddings"):
                return payload["embeddings"]
    except Exception:
        pass  # fall through to recompute

    # Compute fresh
    series_ids = [e["series_id"] for e in INDICATOR_CATALOG]
    texts = [_indicator_embedding_text(e) for e in INDICATOR_CATALOG]
    vectors = _embed_texts(texts)
    if vectors is None or len(vectors) != len(series_ids):
        return None

    embeddings = dict(zip(series_ids, vectors))

    # Write cache (best-effort)
    try:
        os.makedirs(_SEMANTIC_CACHE_DIR, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"cache_key": cache_key, "embeddings": embeddings}, f)
    except Exception:
        pass

    return embeddings


def _semantic_match_score(entry: dict,
                          claim_embeddings: list[list[float]],
                          indicator_embedding: list[float] | None,
                          ) -> tuple[float, float]:
    """Compute the semantic match score for an indicator.

    Returns (normalized_score, raw_max_similarity). Score is the MAX
    cosine similarity across all claims, linearly rescaled so that:
      sim <= _SEMANTIC_NOISE_FLOOR     → 0.0
      sim >= _SEMANTIC_SATURATION       → 1.0
      linear interpolation in between.
    """
    if not indicator_embedding or not claim_embeddings:
        return (0.0, 0.0)
    max_sim = 0.0
    for claim_emb in claim_embeddings:
        sim = _cosine_similarity(claim_emb, indicator_embedding)
        if sim > max_sim:
            max_sim = sim
    span = _SEMANTIC_SATURATION - _SEMANTIC_NOISE_FLOOR
    if span <= 0:
        return (1.0 if max_sim >= _SEMANTIC_SATURATION else 0.0, max_sim)
    normalized = (max_sim - _SEMANTIC_NOISE_FLOOR) / span
    normalized = max(0.0, min(1.0, normalized))
    return (normalized, max_sim)


# ---------------------------------------------------------------------------
# Fact-check — compare article-body numbers against FRED ground truth
# ---------------------------------------------------------------------------
#
# AI-generated article prose can drift from the actual FRED data point
# (the test article said "3.1% YoY" while FRED says "3.78% YoY"). This
# module's job is to flag those discrepancies so an upstream
# article-generator self-correction step can pick them up. MSI is a
# zero-manual-labor publication; the fact-check writes a JSON log and
# surfaces a summary, but never blocks publication.
#
# Discrepancies are not auto-corrected here — that would require
# rewriting the body prose, which is out of scope for the data-viz
# pipeline (it's the article-generator's job). What this module
# produces is the evidence needed for that upstream fix.

# Match the first percent value in a claim's text. Captures "3.1 percent",
# "3.1%", "3.10 percent", "-1.8 percent", "0.5%". The number-then-percent
# pattern is the dominant form in MSI atomic_claims; dollar/index values
# are out of scope for v1.
_PERCENT_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:%|percent\b)",
    re.IGNORECASE,
)

# Predicates whose claims are NOT comparable to FRED point values.
# Articles use these to describe forward-looking probabilities,
# qualitative characterisations, or actions — not historical observed
# data. Listed explicitly so the fact-check skips them rather than
# emitting spurious discrepancies.
_NON_COMPARABLE_PREDICATES = frozenset({
    "priced_probability_of",
    "characterized_response_as",
    "stated_position_on",
    "announced_blockade_on",
    "maintained_policy_rate_at",  # range claim, not a single value
})


def _extract_first_percent(text: str) -> float | None:
    """Parse the first percent value from a claim's text. Returns the
    number as a float (no unit). None if no percent found."""
    if not text:
        return None
    m = _PERCENT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _fred_value_for_claim(entry: dict, claim_temporal,
                           *, as_of_date: str | None = None) -> float | None:
    """Fetch FRED + apply the indicator's default transformation + look
    up the observation at or just before the claim's temporal date.

    Accepts ``claim_temporal`` as either an ISO date string ("YYYY-MM-DD")
    or a ``datetime.date`` / ``datetime.datetime`` instance — PyYAML
    parses bare ISO dates in YAML frontmatter into date objects, so we
    handle both forms.

    Returns None when the indicator has no data near the claim date,
    when FRED is unreachable, or when the temporal field is missing.
    """
    from datetime import date as _date, datetime as _datetime
    if claim_temporal is None:
        return None
    if isinstance(claim_temporal, _datetime):
        target = claim_temporal.date()
    elif isinstance(claim_temporal, _date):
        target = claim_temporal
    elif isinstance(claim_temporal, str):
        try:
            target = _date.fromisoformat(claim_temporal[:10])
        except (TypeError, ValueError):
            return None
    else:
        return None

    # Fetch a window wide enough for YoY transformation (need >= 1 year
    # of prior data) and ending no later than today.
    observation_start = (
        _date(target.year - 2, max(1, target.month - 1), 1).isoformat()
    )

    try:
        from data_viz_render import apply_transformation
        from integrations.fred_api import fetch_series, SeriesQuery
    except ImportError:
        from orchestrator.data_viz_render import apply_transformation
        from orchestrator.integrations.fred_api import fetch_series, SeriesQuery

    sid = entry.get("series_id")
    if not sid:
        return None
    try:
        data = fetch_series(SeriesQuery(
            series_id=sid,
            observation_start=observation_start,
            as_of_date=as_of_date,
        ))
    except Exception:
        return None
    if not data or not data.observations:
        return None

    transformation = entry.get("default_transformation", "raw")
    try:
        transformed = apply_transformation(
            data.observations, transformation,
            frequency=getattr(data.metadata, "frequency", None) if data.metadata else None,
        )
    except Exception:
        return None

    # Pick the observation at or just before target.
    target_iso = target.isoformat()
    best_value: float | None = None
    for obs in transformed:
        if obs.value is None:
            continue
        if obs.date <= target_iso:
            best_value = obs.value
        else:
            break  # observations are date-ascending
    return best_value


@dataclass
class FactCheckResult:
    """Result of comparing one article claim to its FRED ground truth."""
    series_id: str
    claim_id: str
    claim_text_excerpt: str
    transformation: str
    article_value: float | None        # parsed from claim text (percent)
    fred_value: float | None           # from FRED at claim's temporal date
    discrepancy_pp: float | None       # absolute difference, percentage-point units
    within_tolerance: bool             # True when |diff| <= tolerance_pp
    note: str = ""                     # explanatory text (why skipped, etc.)


def fact_check_article_against_fred(article_data: dict,
                                     scored_indicators: list[ScoredIndicator],
                                     *,
                                     tolerance_pp: float = 0.5,
                                     as_of_date: str | None = None,
                                     ) -> list[FactCheckResult]:
    """Compare each picked indicator's matching claims to FRED values.

    For every (indicator, matched_claim) pair: parse the first percent
    value from the claim text, fetch FRED at the claim's temporal date,
    compare. Skips claims whose predicate is in
    ``_NON_COMPARABLE_PREDICATES`` (probability/range/qualitative claims),
    claims without a parseable percent, and claims without a temporal
    date.

    Returns a list of FactCheckResult dicts — never raises. FRED errors
    are absorbed into per-result ``note`` fields so the historical-
    forward pipeline never blocks on a transient API failure.

    ``as_of_date`` forwards the FRED vintage view to each per-claim
    fetch; when None, defaults to the article's publish_date (via
    _resolve_as_of_date). For the historical-forward run, fact-check
    must compare prose to the data that was AVAILABLE on the article's
    date, not today's revised data.
    """
    atomic_claims = article_data.get("atomic_claims") or []
    results: list[FactCheckResult] = []
    if as_of_date is None:
        as_of_date = _resolve_as_of_date(article_data)

    for scored in scored_indicators:
        sid = scored.entry.get("series_id", "?")
        transformation = scored.entry.get("default_transformation", "raw")
        if not scored.matched_claim_indices:
            continue
        for idx in scored.matched_claim_indices:
            if idx >= len(atomic_claims):
                continue
            claim = atomic_claims[idx]
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id", f"c_{idx:03d}"))
            text = claim.get("text") or ""
            excerpt = text[:150] + ("..." if len(text) > 150 else "")
            predicate = claim.get("predicate", "")
            if predicate in _NON_COMPARABLE_PREDICATES:
                results.append(FactCheckResult(
                    series_id=sid, claim_id=claim_id,
                    claim_text_excerpt=excerpt,
                    transformation=transformation,
                    article_value=None, fred_value=None,
                    discrepancy_pp=None, within_tolerance=True,
                    note=f"Skipped: predicate '{predicate}' is non-comparable.",
                ))
                continue
            article_value = _extract_first_percent(text)
            if article_value is None:
                results.append(FactCheckResult(
                    series_id=sid, claim_id=claim_id,
                    claim_text_excerpt=excerpt,
                    transformation=transformation,
                    article_value=None, fred_value=None,
                    discrepancy_pp=None, within_tolerance=True,
                    note="Skipped: no percent value parseable from claim text.",
                ))
                continue
            temporal = claim.get("temporal")
            fred_value = _fred_value_for_claim(
                scored.entry, temporal, as_of_date=as_of_date,
            )
            if fred_value is None:
                results.append(FactCheckResult(
                    series_id=sid, claim_id=claim_id,
                    claim_text_excerpt=excerpt,
                    transformation=transformation,
                    article_value=article_value, fred_value=None,
                    discrepancy_pp=None, within_tolerance=True,
                    note=(
                        f"Skipped: no FRED value available at "
                        f"{temporal} (series missing data or fetch failed)."
                    ),
                ))
                continue
            diff = abs(article_value - fred_value)
            results.append(FactCheckResult(
                series_id=sid, claim_id=claim_id,
                claim_text_excerpt=excerpt,
                transformation=transformation,
                article_value=article_value, fred_value=fred_value,
                discrepancy_pp=diff,
                within_tolerance=(diff <= tolerance_pp),
                note=(
                    "" if diff <= tolerance_pp
                    else f"Discrepancy {diff:.2f}pp exceeds tolerance {tolerance_pp}pp."
                ),
            ))

    return results


@dataclass
class ScoredIndicator:
    """An INDICATOR_CATALOG entry with its objective-ranking scores."""
    entry: dict
    name_match: float = 0.0
    topic_overlap: float = 0.0
    semantic_match: float = 0.0
    semantic_raw_max: float = 0.0          # raw cosine sim (pre-normalization)
    library_match: float = 0.0
    framework_alignment: float = 0.0
    total: float = 0.0
    matched_phrases: list[str] = field(default_factory=list)
    matched_topics: list[str] = field(default_factory=list)
    matched_reports: list[str] = field(default_factory=list)
    matched_framework_points: list[int] = field(default_factory=list)
    matched_claim_indices: list[int] = field(default_factory=list)  # which claims contributed to name_match

    def justification_text(self) -> str:
        """Auditable, deterministic justification string built from score
        components. No model call needed."""
        parts: list[str] = []
        if self.matched_phrases:
            shown = ", ".join(f'"{p}"' for p in self.matched_phrases[:2])
            parts.append(f"Article claims cite {shown}")
        if self.matched_topics:
            parts.append(f"Topic overlap: {', '.join(self.matched_topics)}")
        if self.semantic_match > 0 and not self.matched_phrases:
            # Surface semantic match prominently when it's the dominant
            # signal (no direct citation, but conceptually related).
            parts.append(
                f"Semantic similarity {self.semantic_raw_max:.2f} to article claims"
            )
        covers = self.entry.get("covers", "")
        if covers and not parts:
            parts.append(covers)
        elif covers:
            parts.append(covers.split(";")[0].strip())
        if self.matched_reports and not parts:
            parts.append(
                f"Anchored in Distributional Library report(s) "
                f"{', '.join(self.matched_reports)}"
            )
        elif self.matched_reports:
            parts.append(
                f"Research: report(s) {', '.join(self.matched_reports)}"
            )
        if self.matched_framework_points:
            parts.append(
                f"Framework points: {self.matched_framework_points}"
            )
        score_summary = (
            f"name={self.name_match:.2f}, topic={self.topic_overlap:.2f}, "
            f"sem={self.semantic_match:.2f}, lib={self.library_match:.2f}, "
            f"fw={self.framework_alignment:.2f}"
        )
        return ". ".join(parts) + f" [score: {score_summary}]"


def rank_indicators_for_article(article_data: dict, *,
                                 use_semantic: bool = True,
                                 ) -> list[ScoredIndicator]:
    """Objective ranking — score every INDICATOR_CATALOG entry against
    the article and return the list sorted descending by total score.

    Deterministic given the same catalog state + article + embedder
    state. Adaptive: as the catalog grows, the synonym map evolves, or
    the embedding model changes, the ranking shifts.

    When ``use_semantic=False`` or when the embedder is unavailable
    (Ollama down), the semantic_match dimension contributes 0 and the
    ranking degrades to Phase 1 (name + topic only).
    """
    metadata = article_data.get("metadata") or {}
    article_themes = metadata.get("primary_themes") or []
    atomic_claims = article_data.get("atomic_claims") or []

    # Phase 2 — semantic embeddings (best-effort; degrades to 0 if
    # Ollama is unavailable or use_semantic is False).
    indicator_embeddings: dict[str, list[float]] | None = None
    claim_embeddings: list[list[float]] = []
    if use_semantic and atomic_claims:
        claim_texts = [
            (c.get("text") or "").strip()
            for c in atomic_claims if isinstance(c, dict) and c.get("text")
        ]
        if claim_texts:
            indicator_embeddings = _load_or_compute_indicator_embeddings()
            if indicator_embeddings is not None:
                fetched = _embed_texts(claim_texts)
                if fetched is not None:
                    claim_embeddings = fetched

    scored: list[ScoredIndicator] = []
    for entry in INDICATOR_CATALOG:
        name_score, matched_phrases, matched_indices = _name_match_score(
            entry, atomic_claims,
        )
        topic_score, matched_topics = _topic_overlap_score(entry, article_themes)
        sem_score = 0.0
        sem_raw = 0.0
        if indicator_embeddings is not None and claim_embeddings:
            sid = entry.get("series_id")
            sem_score, sem_raw = _semantic_match_score(
                entry, claim_embeddings, indicator_embeddings.get(sid),
            )
        lib_score, matched_reports = _library_match_score(entry, article_themes)
        fw_score, matched_fw_points = _framework_alignment_score(
            entry, article_themes,
        )
        total = (
            _RANK_WEIGHT_NAME_MATCH * name_score
            + _RANK_WEIGHT_TOPIC_OVERLAP * topic_score
            + _RANK_WEIGHT_SEMANTIC_MATCH * sem_score
            + _RANK_WEIGHT_LIBRARY_MATCH * lib_score
            + _RANK_WEIGHT_FRAMEWORK_ALIGNMENT * fw_score
        )
        scored.append(ScoredIndicator(
            entry=entry,
            name_match=name_score,
            topic_overlap=topic_score,
            semantic_match=sem_score,
            semantic_raw_max=sem_raw,
            library_match=lib_score,
            framework_alignment=fw_score,
            total=total,
            matched_phrases=matched_phrases,
            matched_topics=matched_topics,
            matched_reports=matched_reports,
            matched_framework_points=matched_fw_points,
            matched_claim_indices=matched_indices,
        ))
    scored.sort(key=lambda s: -s.total)
    return scored


def analyze_article_via_ranking(article_data: dict, *,
                                max_indicators: int = 4,
                                min_score_threshold: float = 0.5,
                                use_semantic: bool = True,
                                ) -> ArticleVizAnalysis:
    """Objective-ranking analysis path — no model call.

    Ranks every catalog indicator against the article via the Phase 1
    scoring function. Picks the top ``max_indicators`` whose total
    score meets ``min_score_threshold``. Returns ``warrants_charts=False``
    when no indicator clears the threshold (correctly handles non-
    economic articles whose primary_themes don't engage any catalog
    topic).

    The justification text is deterministic and built from the score
    components — auditable. A future Phase 4 may add a model-narration
    step that rewrites the justifications in editorial voice without
    changing the picks.
    """
    ranked = rank_indicators_for_article(article_data, use_semantic=use_semantic)
    top = [s for s in ranked[:max_indicators] if s.total >= min_score_threshold]

    if not top:
        return ArticleVizAnalysis(
            warrants_charts=False,
            classifier_response_raw="[objective ranking; zero indicators cleared threshold]",
        )

    opportunities: list[VizOpportunity] = []
    for i, scored in enumerate(top):
        entry = scored.entry
        opportunities.append(VizOpportunity(
            series_id=entry["series_id"],
            transformation=entry.get("default_transformation", "raw"),
            chart_type="timeseries",
            narrative_role="quantifies",
            justification=scored.justification_text(),
            priority=i + 1,
        ))

    return ArticleVizAnalysis(
        warrants_charts=True,
        opportunities=opportunities,
        classifier_response_raw="[objective ranking; no model call]",
        picked_scored_indicators=top,
    )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

def _resolve_as_of_date(article_data: dict) -> str | None:
    """Resolve the FRED vintage ("as-of") date for this article.

    Priority:
      1. ``$ORA_FRED_AS_OF`` environment variable — used by the
         historical-forward run script to pin the entire pipeline to
         a specific past date globally.
      2. The article's ``publish_date`` field — for a one-off render
         of an article published in the past, this returns the
         vintage view that existed on the publish date.
      3. None — no vintage view, fetch latest data (today's revisions).

    Accepts strings (ISO YYYY-MM-DD) and date / datetime objects
    (PyYAML parses bare ISO dates in frontmatter into date instances).
    """
    env_override = os.environ.get("ORA_FRED_AS_OF", "").strip()
    if env_override:
        return env_override[:10]
    pd = (article_data or {}).get("publish_date")
    if pd is None:
        return None
    from datetime import date as _date, datetime as _datetime
    if isinstance(pd, _datetime):
        return pd.date().isoformat()
    if isinstance(pd, _date):
        return pd.isoformat()
    if isinstance(pd, str):
        s = pd.strip()
        if len(s) >= 10:
            return s[:10]
    return None


def _trim_caption(text: str | None, *, max_chars: int = 200) -> str | None:
    """Return a caption trimmed to a word boundary at most max_chars long.

    The classifier's justification is treated as the caption seed. A hard
    mid-word truncation (the prior 125-char cut) reads as broken English
    in published articles; this trim keeps captions readable.
    """
    if not text:
        return None
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Find the last whitespace at or before max_chars; fall back to a hard cut.
    head = text[:max_chars]
    last_space = head.rfind(" ")
    if last_space >= int(max_chars * 0.6):
        head = head[:last_space]
    return head.rstrip(",;:.- ") + "…"


@dataclass
class VizOpportunity:
    """A classifier-identified data-viz opportunity for an article."""
    series_id: str                          # FRED series ID (must be in INDICATOR_CATALOG)
    transformation: str                     # raw / yoy_pct / first_diff / ytd
    chart_type: str = "timeseries"
    narrative_role: str = "quantifies"      # confirms / quantifies / contextualizes / contrasts
    justification: str = ""                 # one-sentence editorial reason
    priority: int = 1                       # 1 = lead figure; higher = secondary
    time_range_years: int = 5               # default lookback


@dataclass
class ArticleVizAnalysis:
    """Result of analyze_article_for_data_viz."""
    warrants_charts: bool
    opportunities: list[VizOpportunity] = field(default_factory=list)
    classifier_response_raw: str = ""       # for debugging / audit
    error: str = ""                         # populated on classifier failure
    picked_scored_indicators: list = field(default_factory=list)  # ScoredIndicators that were picked — used by fact_check


@dataclass
class ArticleVizResult:
    """Result of render_figures_for_article — the end-to-end output."""
    success: bool
    figures: list[dict] = field(default_factory=list)        # list of figureSchema dicts
    analysis: ArticleVizAnalysis | None = None
    figure_results: list[FigureResult] = field(default_factory=list)  # per-opportunity detail
    error: str = ""


# ---------------------------------------------------------------------------
# Article extraction helpers
# ---------------------------------------------------------------------------

def extract_article_summary(article_data: dict, *, max_claims: int = 8) -> str:
    """Extract the classifier-prompt-relevant content from an article dict.

    Reads headline + lede + nut_graf + first N atomic_claims (or fewer
    if the article has fewer). Returns a compact text summary the
    classifier can fit alongside the indicator catalog in a single prompt.
    """
    parts = []
    headline = article_data.get("headline", "")
    if headline:
        parts.append(f"Headline: {headline}")

    lede = article_data.get("lede", "")
    if lede:
        # Trim multi-line ledes to a reasonable length
        lede_text = lede.strip().replace("\n", " ")
        if len(lede_text) > 800:
            lede_text = lede_text[:797] + "..."
        parts.append(f"Lede: {lede_text}")

    nut_graf = article_data.get("nut_graf") or ""
    if nut_graf:
        nut_text = nut_graf.strip().replace("\n", " ")
        if len(nut_text) > 800:
            nut_text = nut_text[:797] + "..."
        parts.append(f"Nut graf: {nut_text}")

    claims = article_data.get("atomic_claims", [])
    if claims:
        parts.append(f"Key claims (first {min(max_claims, len(claims))}):")
        for c in claims[:max_claims]:
            text = c.get("text") if isinstance(c, dict) else str(c)
            if text:
                parts.append(f"- {text.strip()}")

    return "\n".join(parts)


def parse_article_file(path: str) -> dict:
    """Parse a vault article .md file into a dict.

    Reads YAML frontmatter (between leading --- markers) and returns
    a dict that's compatible with extract_article_summary's expected
    shape.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return {"headline": "", "lede": "", "atomic_claims": []}

    # Find end of frontmatter
    end_marker = content.find("\n---", 4)
    if end_marker < 0:
        return {"headline": "", "lede": "", "atomic_claims": []}

    fm_text = content[3:end_marker].strip()

    # Use a best-effort YAML parse
    try:
        import yaml
        return yaml.safe_load(fm_text) or {}
    except ImportError:
        # Fall back to a tiny YAML subset parser if PyYAML unavailable
        return _minimal_yaml_parse(fm_text)


def _minimal_yaml_parse(text: str) -> dict:
    """Tiny YAML subset parser — only handles flat top-level keys with
    string values. Used as a fallback when PyYAML is unavailable."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?)$", line)
        if m:
            key, val = m.groups()
            out[key] = val.strip().strip('"').strip("'")
    return out


# ---------------------------------------------------------------------------
# Classifier prompt construction
# ---------------------------------------------------------------------------

def _build_classifier_prompt(article_summary: str) -> list[dict]:
    """Build the messages list for the classifier model call."""
    catalog_lines = []
    for entry in INDICATOR_CATALOG:
        topics = ", ".join(entry["topics"])
        catalog_lines.append(
            f"- {entry['series_id']} ({entry['name']}): {entry['covers']} "
            f"[topics: {topics}; default transformation: {entry['default_transformation']}]"
        )
    catalog_text = "\n".join(catalog_lines)

    system = (
        "You are the MSI data-visualization classifier. Given a news "
        "article's structured content, decide which FRED data series "
        "(if any) materially aid reader understanding of specific "
        "claims in the article.\n\n"
        "Guardrails:\n"
        "- Charts ONLY when they directly anchor a quantitative claim "
        "in the article. Pure geopolitics, criminal justice, sports, "
        "or non-quantitative subjects → return empty opportunities list.\n"
        "- A chart of meaningless data serves no one. If you are not "
        "confident the chart adds reader value, do not select it.\n"
        "- Select at most 4 series; lead with the single most relevant.\n"
        "- Editorial slant: surface labor-side, distributional, and "
        "asset-vs-wage indicators when the article touches them. The "
        "publication's framework treats aggregate output ≠ welfare and "
        "favors series that surface the productivity-wage decoupling, "
        "K-shaped consumer story, or Fed-policy-as-redistribution.\n\n"
        "Return ONLY valid JSON (no prose, no markdown fences). Schema:\n"
        '{\n'
        '  "warrants_charts": true|false,\n'
        '  "opportunities": [\n'
        '    {\n'
        '      "series_id": "<must be in catalog below>",\n'
        '      "transformation": "raw" | "yoy_pct" | "first_diff" | "ytd",\n'
        '      "narrative_role": "anchors" | "quantifies" | "contextualizes" | "contrasts",\n'
        '      "justification": "<one sentence>",\n'
        '      "priority": 1 | 2 | 3 | 4\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "Available indicators (you MUST select series_id from this list):\n"
        f"{catalog_text}"
    )

    user = (
        "Article to classify:\n\n"
        f"{article_summary}\n\n"
        "Return the JSON classification."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_classifier_response(raw: str) -> ArticleVizAnalysis:
    """Parse the classifier model's JSON response into an analysis.

    Robust to common model slop: strips code-fence markers, trims to
    the first '{...}' block, validates each opportunity against the
    INDICATOR_CATALOG before accepting.
    """
    cleaned = raw.strip()

    # Strip markdown code fences if present
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl > 0:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    # Find the first balanced JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < 0:
        return ArticleVizAnalysis(
            warrants_charts=False,
            classifier_response_raw=raw,
            error="No JSON object found in classifier response",
        )
    json_text = cleaned[start:end + 1]

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return ArticleVizAnalysis(
            warrants_charts=False,
            classifier_response_raw=raw,
            error=f"JSON parse error: {exc}",
        )

    warrants = bool(payload.get("warrants_charts", False))
    raw_opps = payload.get("opportunities", []) or []

    valid_series_ids = {e["series_id"] for e in INDICATOR_CATALOG}
    valid_transformations = {"raw", "yoy_pct", "first_diff", "ytd"}
    valid_roles = {"anchors", "quantifies", "contextualizes", "contrasts"}

    opportunities = []
    for o in raw_opps:
        if not isinstance(o, dict):
            continue
        series_id = o.get("series_id", "")
        if series_id not in valid_series_ids:
            continue  # silently drop unknown series
        transformation = o.get("transformation", "raw")
        if transformation not in valid_transformations:
            transformation = "raw"
        narrative_role = o.get("narrative_role", "quantifies")
        if narrative_role not in valid_roles:
            narrative_role = "quantifies"
        try:
            priority = int(o.get("priority", 1))
        except (TypeError, ValueError):
            priority = 1
        opportunities.append(VizOpportunity(
            series_id=series_id,
            transformation=transformation,
            narrative_role=narrative_role,
            justification=str(o.get("justification", "")).strip(),
            priority=priority,
        ))

    # Cap at 4, sort by priority
    opportunities.sort(key=lambda x: x.priority)
    opportunities = opportunities[:4]

    return ArticleVizAnalysis(
        warrants_charts=warrants and len(opportunities) > 0,
        opportunities=opportunities,
        classifier_response_raw=raw,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_article_for_data_viz(article_data: dict, *,
                                 call_fn: Callable | None = None,
                                 endpoint: dict | None = None,
                                 max_tokens: int = 2048,
                                 mode: str = "ranking",
                                 max_indicators: int = 4,
                                 min_score_threshold: float = 0.5,
                                 ) -> ArticleVizAnalysis:
    """Analyse an article and return a list of data-viz opportunities.

    Default mode is ``"ranking"`` — objective scoring against the
    indicator catalog with no model call (Phase 1: topic-overlap +
    name-match). Deterministic given catalog state + article state.
    Adaptive as the catalog and synonym map grow.

    Legacy mode ``"classifier"`` uses the previous model-judgment
    path (kept for tests + A/B comparison). Requires ``call_fn``.
    """
    if mode == "ranking":
        return analyze_article_via_ranking(
            article_data,
            max_indicators=max_indicators,
            min_score_threshold=min_score_threshold,
        )

    if call_fn is None:
        return ArticleVizAnalysis(
            warrants_charts=False,
            error="No call_fn provided; classifier mode requires a model-invocation function",
        )

    summary = extract_article_summary(article_data)
    if not summary.strip():
        return ArticleVizAnalysis(
            warrants_charts=False,
            error="Article has no headline / lede / claims to classify",
        )

    messages = _build_classifier_prompt(summary)

    try:
        raw = call_fn(messages, endpoint or {})
    except TypeError:
        # Some call_fn signatures may not accept endpoint kwarg
        raw = call_fn(messages)

    if not raw or not isinstance(raw, str):
        return ArticleVizAnalysis(
            warrants_charts=False,
            error=f"Classifier returned empty/non-string response: {type(raw).__name__}",
        )

    return _parse_classifier_response(raw)


def render_figures_for_article(article_data: dict, *,
                               call_fn: Callable | None = None,
                               endpoint: dict | None = None,
                               output_dir: str | None = None,
                               article_slug: str | None = None,
                               mode: str = "ranking",
                               max_indicators: int = 4,
                               min_score_threshold: float = 0.5,
                               ) -> ArticleVizResult:
    """End-to-end: analyse the article, render every accepted opportunity,
    return the figureSchema list ready to drop into the article frontmatter.

    Default mode is ``"ranking"`` — objective scoring against the
    catalog (Phase 1). ``mode="classifier"`` falls back to the legacy
    model-judgment path; requires ``call_fn``.

    Failure modes:
      - Analyser returns no opportunities → success=True, figures=[].
        This is the editorially-correct behavior for non-economic
        articles.
      - Individual figure render fails → that figure is dropped; other
        figures still attempted; success=True if at least one rendered.
      - All figures fail → success=False with error_message aggregated.
      - Analyser itself fails → success=False, analysis carries the error.
    """
    analysis = analyze_article_for_data_viz(
        article_data, call_fn=call_fn, endpoint=endpoint, mode=mode,
        max_indicators=max_indicators, min_score_threshold=min_score_threshold,
    )

    if analysis.error:
        return ArticleVizResult(success=False, analysis=analysis,
                                error=analysis.error)

    if not analysis.warrants_charts or not analysis.opportunities:
        return ArticleVizResult(success=True, analysis=analysis, figures=[])

    figure_results = []
    figures_schema = []

    # Resolve the FRED vintage date — for the historical-forward run
    # this anchors every fetch to the article's publish date so charts
    # reflect what was available then, not today's revised data.
    as_of = _resolve_as_of_date(article_data)

    # Compute observation_start. When as-of is set, anchor the 5-year
    # lookback window to the as-of date rather than today, so we don't
    # accidentally request observations beyond the vintage view.
    from datetime import date
    if as_of:
        try:
            anchor = date.fromisoformat(as_of[:10])
        except (TypeError, ValueError):
            anchor = date.today()
    else:
        anchor = date.today()
    default_start = f"{anchor.year - 5}-01-01"

    for opp in analysis.opportunities:
        # Look up catalog entry for default chart_type / narrative metadata
        catalog_entry = next(
            (e for e in INDICATOR_CATALOG if e["series_id"] == opp.series_id),
            None,
        )
        # If transformation default differs and opp.transformation is "raw"
        # (the model's lazy default), use catalog default instead.
        # Actually — respect the model's choice; the catalog default is
        # for when no analysis exists.

        request = FigureRequest(
            series_query=SeriesQuery(
                series_id=opp.series_id,
                observation_start=default_start,
                as_of_date=as_of,
            ),
            chart_type=opp.chart_type,
            transformation=opp.transformation,
            article_slug=article_slug,
            caption=_trim_caption(opp.justification, max_chars=200),
        )

        try:
            kwargs = {}
            if output_dir:
                kwargs["output_dir"] = output_dir
            result = render_figure(request, **kwargs)
        except Exception as exc:
            result = FigureResult(
                success=False,
                error_code="render_exception",
                error_message=str(exc),
            )

        figure_results.append(result)
        if result.success:
            figures_schema.append(result.figure_schema)

    overall_success = any(r.success for r in figure_results)
    error_msg = ""
    if not overall_success:
        codes = sorted({r.error_code for r in figure_results if not r.success})
        error_msg = f"All {len(figure_results)} figure renders failed: {codes}"

    return ArticleVizResult(
        success=overall_success,
        figures=figures_schema,
        analysis=analysis,
        figure_results=figure_results,
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: article_data_viz.py <article_path.md>")
        print("  Reads the article's YAML frontmatter, runs the classifier,")
        print("  prints the analysis. Does NOT render figures (dry-run mode).")
        sys.exit(1)

    article_path = sys.argv[1]
    if not os.path.exists(article_path):
        print(f"ERROR: file not found: {article_path}")
        sys.exit(1)

    article = parse_article_file(article_path)
    print(f"Parsed: {article.get('headline', '(no headline)')}")
    print()
    summary = extract_article_summary(article)
    print(f"Summary length: {len(summary)} chars")
    print()

    # Wire call_fn from boot
    sys.path.insert(0, os.path.expanduser("~/ora"))
    sys.path.insert(0, os.path.expanduser("~/ora/orchestrator"))
    sys.path.insert(0, os.path.expanduser("~/ora/orchestrator/integrations"))
    from boot import call_model, load_endpoints, get_slot_endpoint

    config = load_endpoints()
    endpoint = get_slot_endpoint(config, "sidebar")

    print(f"Endpoint: {endpoint.get('id', '?') if endpoint else 'NONE'}")
    print()
    print("Running classifier (dry-run; no figures rendered)...")
    analysis = analyze_article_for_data_viz(
        article, call_fn=call_model, endpoint=endpoint,
    )

    if analysis.error:
        print(f"ERROR: {analysis.error}")
        print()
        print("Raw response:")
        print(analysis.classifier_response_raw[:1000])
        sys.exit(1)

    print(f"Warrants charts: {analysis.warrants_charts}")
    print(f"Opportunities: {len(analysis.opportunities)}")
    for o in analysis.opportunities:
        print(f"  [{o.priority}] {o.series_id} ({o.transformation}) — "
              f"{o.narrative_role}")
        if o.justification:
            print(f"      {o.justification}")
