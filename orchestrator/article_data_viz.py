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
    },
    {
        "series_id": "GDI",
        "name": "Gross Domestic Income (real)",
        "category": "macro_headline",
        "topics": ["distributional-methodology"],
        "covers": "wage-income side of GDP; pair with GDP for divergence stories",
        "default_transformation": "raw",
    },
    {
        "series_id": "PAYEMS",
        "name": "Total Nonfarm Payrolls",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "monthly jobs report headline; jobs added/lost",
        "default_transformation": "first_diff",
    },
    {
        "series_id": "UNRATE",
        "name": "Unemployment Rate (U-3)",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "official unemployment rate; load-bearing pair with LFPR + EPOP",
        "default_transformation": "raw",
    },
    {
        "series_id": "U6RATE",
        "name": "Unemployment Rate (U-6, broader)",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "broader underemployment incl. discouraged + involuntary part-time",
        "default_transformation": "raw",
    },
    {
        "series_id": "CIVPART",
        "name": "Labor Force Participation Rate",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "share of population in labor force; the silent denominator behind U-3",
        "default_transformation": "raw",
    },
    {
        "series_id": "LNS12300060",
        "name": "Prime-age (25-54) Employment-Population Ratio",
        "category": "employment_labor",
        "topics": ["labor-market-measurement", "demographics-generations"],
        "covers": "preferred slack measure; bypasses participation problem in U-3",
        "default_transformation": "raw",
    },
    {
        "series_id": "JTSQUL",
        "name": "JOLTS Quits Rate",
        "category": "employment_labor",
        "topics": ["labor-standards", "worker-power"],
        "covers": "voluntary separations as % of employment; worker bargaining power signal",
        "default_transformation": "raw",
    },
    {
        "series_id": "ICSA",
        "name": "Initial Jobless Claims",
        "category": "employment_labor",
        "topics": ["labor-market-measurement"],
        "covers": "weekly real-time labor-market signal; AI-displacement early warning",
        "default_transformation": "raw",
    },
    # --- Wage growth ---
    {
        "series_id": "FRBATLWGT3MMAUMHWGO",
        "name": "Atlanta Fed Wage Growth Tracker (median, 3-month MA)",
        "category": "employment_labor",
        "topics": ["labor-standards", "worker-power"],
        "covers": "composition-adjusted wage growth for median continuously-employed worker",
        "default_transformation": "raw",
    },
    {
        "series_id": "OPHNFB",
        "name": "Nonfarm Business Productivity (output per hour)",
        "category": "macro_headline",
        "topics": ["labor-standards", "labor-economics"],
        "covers": "productivity-wage decoupling chart anchor; pair with real wages",
        "default_transformation": "raw",
    },
    # --- Rates & yields ---
    {
        "series_id": "FEDFUNDS",
        "name": "Federal Funds Rate (effective, monthly avg)",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "Fed policy lever; FOMC rate decisions; mortgage transmission stories",
        "default_transformation": "raw",
    },
    {
        "series_id": "DGS10",
        "name": "10-Year Treasury Yield",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "benchmark long-term yield; sets mortgage rates and corp borrowing",
        "default_transformation": "raw",
    },
    {
        "series_id": "T10Y2Y",
        "name": "10-Year minus 2-Year Treasury Spread",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "yield-curve recession-prediction signal; pair with Sahm/NY-Fed-prob",
        "default_transformation": "raw",
    },
    {
        "series_id": "DFII10",
        "name": "10-Year Real Yield (TIPS)",
        "category": "rates_yields",
        "topics": ["monetary-policy"],
        "covers": "real cost of capital; long-run redistribution signal",
        "default_transformation": "raw",
    },
    {
        "series_id": "MORTGAGE30US",
        "name": "30-Year Fixed Mortgage Rate",
        "category": "rates_yields",
        "topics": ["housing", "monetary-policy"],
        "covers": "household-affordability rate; pair with median home price",
        "default_transformation": "raw",
    },
    {
        "series_id": "WALCL",
        "name": "Federal Reserve Total Assets (Balance Sheet)",
        "category": "rates_yields",
        "topics": ["monetary-policy", "financial-regulation"],
        "covers": "QE/QT scale; redistribution-policy indicator post-2008",
        "default_transformation": "raw",
    },
    # --- Inflation ---
    {
        "series_id": "CPIAUCSL",
        "name": "Consumer Price Index (all urban consumers)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement"],
        "covers": "headline CPI; year-over-year inflation reporting",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "CPILFESL",
        "name": "Core CPI (all items less food and energy)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement"],
        "covers": "core CPI; the underlying-inflation reading the Fed watches; pair with shelter",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "PCEPI",
        "name": "PCE Price Index (Fed's preferred inflation gauge)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement", "monetary-policy"],
        "covers": "Fed inflation target reference; pair with CPI for divergence stories",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "PCEPILFE",
        "name": "Core PCE (PCE less food and energy)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement", "monetary-policy"],
        "covers": "Fed's actual operational inflation target; the headline-vs-target divergence anchor",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "MICH",
        "name": "U. Michigan 1-year Inflation Expectations (median)",
        "category": "prices_inflation",
        "topics": ["inflation-measurement"],
        "covers": "household 1-year-ahead inflation expectations; surfaces anchoring/de-anchoring",
        "default_transformation": "raw",
    },
    # --- Housing ---
    {
        "series_id": "CSUSHPISA",
        "name": "Case-Shiller U.S. National Home Price Index (SA)",
        "category": "housing",
        "topics": ["housing", "asset-prices"],
        "covers": "national house-price index; the asset-side of the asset-vs-wage framing",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "MSPUS",
        "name": "Median Sales Price of Houses Sold",
        "category": "housing",
        "topics": ["housing"],
        "covers": "raw dollar median home price; preferred over indices when affordability is the story",
        "default_transformation": "raw",
    },
    {
        "series_id": "HOUST",
        "name": "Housing Starts (Total, Privately-Owned)",
        "category": "housing",
        "topics": ["housing"],
        "covers": "supply-side construction signal; pair with MSPUS for affordability narratives",
        "default_transformation": "raw",
    },
    # --- Consumer ---
    {
        "series_id": "RSAFS",
        "name": "Advance Retail Sales (Retail + Food Services)",
        "category": "consumer",
        "topics": ["consumer-spending"],
        "covers": "monthly retail sales headline; consumer-demand pulse; distributional-honesty caveat applies",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "UMCSENT",
        "name": "U. Michigan Consumer Sentiment",
        "category": "consumer",
        "topics": ["consumer-spending", "distributional-methodology"],
        "covers": "household-sentiment index; the workers'-mood gap vs. macro headlines (K-shaped framing)",
        "default_transformation": "raw",
    },
    {
        "series_id": "PSAVERT",
        "name": "Personal Saving Rate",
        "category": "consumer",
        "topics": ["consumer-spending", "distributional-methodology"],
        "covers": "household saving as % of disposable income; surfaces pandemic-era depletion story",
        "default_transformation": "raw",
    },
    # --- Trade ---
    {
        "series_id": "DTWEXBGS",
        "name": "Trade-Weighted U.S. Dollar Index (Broad)",
        "category": "trade",
        "topics": ["trade", "monetary-policy"],
        "covers": "broad dollar strength; sets the cost of imports and the value of overseas earnings",
        "default_transformation": "raw",
    },
    {
        "series_id": "NETEXP",
        "name": "Net Exports of Goods and Services",
        "category": "trade",
        "topics": ["trade"],
        "covers": "trade balance; structural deficit story; pair with USD index for revaluation effects",
        "default_transformation": "raw",
    },
    # --- Money & Credit ---
    {
        "series_id": "M2SL",
        "name": "M2 Money Stock",
        "category": "money_credit",
        "topics": ["monetary-policy"],
        "covers": "broad money supply; reject the simplistic M2-causes-inflation frame, use for velocity context",
        "default_transformation": "yoy_pct",
    },
    {
        "series_id": "TOTBKCR",
        "name": "Bank Credit, All Commercial Banks",
        "category": "money_credit",
        "topics": ["financial-regulation", "monetary-policy"],
        "covers": "commercial-bank credit aggregate; lending channel of monetary transmission",
        "default_transformation": "yoy_pct",
    },
    # --- Markets ---
    {
        "series_id": "SP500",
        "name": "S&P 500 Index",
        "category": "markets",
        "topics": ["asset-prices", "distributional-methodology"],
        "covers": "large-cap equity benchmark; the asset-vs-wage framing (point 3); top-10%-of-households exposure",
        "default_transformation": "raw",
    },
    {
        "series_id": "NASDAQCOM",
        "name": "NASDAQ Composite Index",
        "category": "markets",
        "topics": ["asset-prices"],
        "covers": "tech-heavy equity index; rate-sensitive cohort; pair with DFII10 for valuation stories",
        "default_transformation": "raw",
    },
    {
        "series_id": "DJIA",
        "name": "Dow Jones Industrial Average",
        "category": "markets",
        "topics": ["asset-prices"],
        "covers": "30-stock price-weighted blue-chip index; populist headline reference, less analytical signal",
        "default_transformation": "raw",
    },
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

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
                                 ) -> ArticleVizAnalysis:
    """Classify an article and return a list of data-viz opportunities.

    Calls the model (sidebar slot) once with the article summary +
    indicator catalog and parses the JSON response into a structured
    analysis. When ``call_fn`` is None, returns an empty analysis with
    an error message (caller is expected to wire the model invocation).
    """
    if call_fn is None:
        return ArticleVizAnalysis(
            warrants_charts=False,
            error="No call_fn provided; classifier requires a model-invocation function",
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
                               ) -> ArticleVizResult:
    """End-to-end: classify the article, render every accepted opportunity,
    return the figureSchema list ready to drop into the article frontmatter.

    Failure modes:
      - Classifier returns no opportunities → success=True, figures=[].
        This is the editorially-correct behavior for non-economic
        articles.
      - Individual figure render fails → that figure is dropped; other
        figures still attempted; success=True if at least one rendered.
      - All figures fail → success=False with error_message aggregated.
      - Classifier itself fails → success=False, analysis carries the error.
    """
    analysis = analyze_article_for_data_viz(
        article_data, call_fn=call_fn, endpoint=endpoint,
    )

    if analysis.error:
        return ArticleVizResult(success=False, analysis=analysis,
                                error=analysis.error)

    if not analysis.warrants_charts or not analysis.opportunities:
        return ArticleVizResult(success=True, analysis=analysis, figures=[])

    figure_results = []
    figures_schema = []

    # Compute observation_start from time_range_years
    from datetime import date
    today = date.today()
    default_start = f"{today.year - 5}-01-01"

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
            ),
            chart_type=opp.chart_type,
            transformation=opp.transformation,
            article_slug=article_slug,
            caption=(opp.justification[:125] if opp.justification else None),
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
