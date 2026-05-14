"""MSI data-visualization rendering pipeline (Phase 4 of the data-viz handoff).

Operational executor that turns FRED time-series data into publication-
ready SVG charts. Composes:

  Phase 2:  ``integrations/fred_api.py``  → fetches the data
  Phase 4:  this module                   → transforms + builds the
                                            Vega-Lite envelope
  Existing: ``server/static/ora-visual-compiler/tools/render-envelope.js``
                                          → renders SVG (jsdom + Vega-Lite
                                            + accessibility + adversarial
                                            review)

Inputs are a ``FigureRequest`` (FRED series + transformation + viz type
+ caption + output dir). Output is a ``FigureResult`` with the rendered
SVG path, the envelope used, the FRED attribution line, and a
``figureSchema`` dict ready for the Astro article frontmatter.

What this module DOES NOT do:
  - Decide which chart to render (that's Phase 3 — article-classifier)
  - Decide style standards (that's Phase 7 — spec authoring; defaults
    encoded here are publication-house defaults until Phase 7 lands)
  - Index into ChromaDB (figures are content for articles, not engrams)

Per:
  - Reference — MSI Data Source Catalog.md (default viz per indicator)
  - Reference — MSI Distributional Honesty Research Library.md
    (Reports 3.1, 3.6, 3.9 — methodological + visualization standards)
  - Reference — MSI Image Style Specification.md v2.0 (visual identity)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

# Local module imports — adapt to whichever sys.path config invokes us
try:
    from integrations.fred_api import (
        FredError, Observation, SeriesData, SeriesQuery,
        attribution_line, fetch_series,
    )
except ImportError:
    from orchestrator.integrations.fred_api import (
        FredError, Observation, SeriesData, SeriesQuery,
        attribution_line, fetch_series,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RENDER_ENVELOPE_JS = os.path.expanduser(
    "~/ora/server/static/ora-visual-compiler/tools/render-envelope.js"
)
DEFAULT_OUTPUT_DIR = os.path.expanduser(
    "~/sites/mainstreetindependent/public/figures/"
)
NODE_BIN = "node"
RENDER_TIMEOUT_SECONDS = 60

# Transformations the chart emitter supports. The Series-Catalog's
# "Common transformations" field lists these by name — any new one
# requires implementation here.
TRANSFORMATIONS = {
    "raw",          # Identity — observation values as-is
    "yoy_pct",      # YoY % change (12-month for monthly, 4-quarter for quarterly)
    "first_diff",   # First difference (period over period)
    "ytd",          # Year-to-date cumulative
}

# Chart types this module emits. Each maps to a Vega-Lite envelope shape.
# Phase 4 minimal supports timeseries; comparison + scatter come next.
CHART_TYPES = {
    "timeseries",
    # "comparison",   # bar chart of N series at one point in time
    # "scatter",      # X-Y scatter, two series correlated
    # "distribution", # histogram of one series
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FigureRequest:
    """Specification for a chart to render.

    ``series_query`` — what to fetch from FRED.
    ``chart_type`` — which chart shape to render (timeseries / etc).
    ``transformation`` — how to frame the data before rendering.
    ``title`` — chart title (overrides FRED metadata title when set).
    ``caption`` — short editorial caption beneath the chart (≤125 chars
                  per imageSchema convention).
    ``slug`` — output filename stem (no extension); auto-derived from
              series_id + transformation when not set.
    ``article_slug`` — when this figure belongs to a specific article,
                      the article's slug; controls output subdirectory.
    ``mode_context`` — Vega-Lite envelope's mode_context field. Defaults
                      to ``"data_visualization"``.
    """
    series_query: SeriesQuery
    chart_type: str = "timeseries"
    transformation: str = "raw"
    title: str | None = None
    caption: str | None = None
    slug: str | None = None
    article_slug: str | None = None
    mode_context: str = "data_visualization"


@dataclass
class FigureResult:
    """What ``render_figure`` returns on success.

    ``svg_path`` — absolute path to the rendered SVG.
    ``url`` — Astro-relative URL (``/figures/...``).
    ``envelope`` — the Vega-Lite envelope that was rendered.
    ``attribution`` — the standard MSI source-attribution string.
    ``figure_schema`` — dict ready for the Astro article frontmatter.
    """
    success: bool
    svg_path: str = ""
    url: str = ""
    envelope: dict = field(default_factory=dict)
    attribution: str = ""
    figure_schema: dict = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""


# ---------------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------------

def apply_transformation(observations: list[Observation],
                         transformation: str,
                         frequency: str | None = None) -> list[Observation]:
    """Transform a list of Observations per the named transformation.

    ``frequency`` is one of FRED's frequency codes (M / Q / A / D / W);
    used to pick the right lookback for YoY% (12 months for M, 4
    quarters for Q, 1 year for A). When ``frequency`` is None we infer
    from the average gap between observation dates.

    Observations with None values pass through as None values in the
    output (missing data marker preserved).

    Raises ValueError on unknown transformation.
    """
    if transformation == "raw":
        return list(observations)

    if transformation not in TRANSFORMATIONS:
        raise ValueError(
            f"Unknown transformation '{transformation}'. "
            f"Supported: {sorted(TRANSFORMATIONS)}"
        )

    if not observations:
        return []

    if transformation == "first_diff":
        out = [Observation(date=observations[0].date, value=None)]
        for prev, curr in zip(observations, observations[1:]):
            if prev.value is None or curr.value is None:
                out.append(Observation(date=curr.date, value=None))
            else:
                out.append(Observation(date=curr.date,
                                       value=curr.value - prev.value))
        return out

    if transformation == "yoy_pct":
        # Pick lookback period
        lookback = _infer_yoy_lookback(observations, frequency)
        out = []
        for i, curr in enumerate(observations):
            if i < lookback:
                out.append(Observation(date=curr.date, value=None))
                continue
            prior = observations[i - lookback]
            if prior.value is None or curr.value is None or prior.value == 0:
                out.append(Observation(date=curr.date, value=None))
                continue
            pct = (curr.value - prior.value) / abs(prior.value) * 100.0
            out.append(Observation(date=curr.date, value=pct))
        return out

    if transformation == "ytd":
        # Year-to-date cumulative within each calendar year.
        out = []
        current_year = ""
        running = 0.0
        for obs in observations:
            year = obs.date[:4]
            if year != current_year:
                current_year = year
                running = 0.0
            if obs.value is None:
                out.append(Observation(date=obs.date, value=None))
                continue
            running += obs.value
            out.append(Observation(date=obs.date, value=running))
        return out

    # Should be unreachable due to TRANSFORMATIONS guard above.
    raise ValueError(f"Transformation '{transformation}' unimplemented")


def _infer_yoy_lookback(observations: list[Observation],
                        frequency: str | None) -> int:
    """Return the lookback offset for YoY % calculation.

    Priority: explicit frequency > inferred from date gaps.
    """
    if frequency:
        f = frequency.upper()
        if f.startswith("M"):
            return 12
        if f.startswith("Q"):
            return 4
        if f.startswith("A") or f.startswith("Y"):
            return 1
        if f.startswith("W"):
            return 52
        if f.startswith("D"):
            return 365

    # Infer from gaps. Look at first two non-null observations.
    if len(observations) < 3:
        return 1
    a = observations[0].date
    b = observations[1].date
    try:
        from datetime import date
        d1 = date.fromisoformat(a)
        d2 = date.fromisoformat(b)
        gap_days = (d2 - d1).days
        if gap_days >= 350:
            return 1            # annual
        if gap_days >= 80:
            return 4            # quarterly
        if gap_days >= 20:
            return 12           # monthly
        if gap_days >= 5:
            return 52           # weekly
        return 365              # daily
    except Exception:
        return 12  # safe default — treat as monthly


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------

def build_timeseries_envelope(series_data: SeriesData,
                              request: FigureRequest,
                              transformed_observations: list[Observation]
                              ) -> dict:
    """Build a complete Vega-Lite envelope for a timeseries chart.

    The envelope conforms to the visual compiler's schema (see
    config/visual-schemas/specs/time_series.json + the universal
    envelope.json). Returns a dict ready to feed render-envelope.js.

    Skips observations with None values (Vega-Lite handles gaps cleanly
    when missing points are absent rather than null).
    """
    points = [
        {"t": o.date, "v": o.value}
        for o in transformed_observations
        if o.value is not None
    ]

    title = request.title or _default_title(series_data, request)
    units_label = _units_label(series_data, request.transformation)

    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": points},
        "mark": {"type": "line", "tooltip": True},
        "encoding": {
            "x": {
                "field": "t",
                "type": "temporal",
                "title": "Date",
            },
            "y": {
                "field": "v",
                "type": "quantitative",
                "title": units_label,
            },
        },
        "caption": {
            "source": _caption_source(series_data),
            "period": _caption_period(transformed_observations),
            "n": len(points),
            "units": units_label,
        },
    }

    semantic = _build_semantic_description(
        series_data, request, transformed_observations, points,
    )

    envelope = {
        "schema_version": "0.2",
        "id": _slug(request, series_data),
        "type": "time_series",
        "mode_context": request.mode_context,
        "relation_to_prose": "integrated",
        "spec": spec,
        "semantic_description": semantic,
        "title": title,
    }

    return envelope


def _default_title(series_data: SeriesData, request: FigureRequest) -> str:
    """Compose a chart title from series metadata + transformation hint."""
    base = series_data.metadata.title if series_data.metadata else series_data.series_id
    tform = request.transformation
    if tform == "raw":
        return base
    if tform == "yoy_pct":
        return f"{base} (year-over-year % change)"
    if tform == "first_diff":
        return f"{base} (period-over-period change)"
    if tform == "ytd":
        return f"{base} (year-to-date cumulative)"
    return base


def _units_label(series_data: SeriesData, transformation: str) -> str:
    """Y-axis units label appropriate for the transformation."""
    if transformation == "yoy_pct":
        return "Percent (YoY)"
    if transformation == "first_diff":
        if series_data.metadata and series_data.metadata.units_short:
            return f"Change in {series_data.metadata.units_short}"
        return "Change"
    if series_data.metadata and series_data.metadata.units_short:
        return series_data.metadata.units_short
    return "Value"


def _caption_source(series_data: SeriesData) -> str:
    """Caption-block source string per Vega-Lite envelope convention."""
    if series_data.metadata and series_data.metadata.title:
        return f"FRED, {series_data.metadata.title} ({series_data.series_id})"
    return f"FRED, series {series_data.series_id}"


def _caption_period(observations: list[Observation]) -> str:
    """Caption-block period string covering the rendered data range."""
    valued = [o for o in observations if o.value is not None]
    if not valued:
        return "—"
    return f"{valued[0].date} to {valued[-1].date}"


def _build_semantic_description(series_data: SeriesData,
                                request: FigureRequest,
                                transformed: list[Observation],
                                points: list[dict]) -> dict:
    """Build the Lundgard-Satyanarayan accessibility description.

    All four levels are populated as non-null strings (the visual
    compiler's schema rejects null at L3 and L4). L1 elemental and
    L2 statistical are computed from the data. L3 perceptual is
    derived from the data shape (trend direction, range, monotonicity
    flags). L4 contextual is a publication-neutral framing — when a
    future Phase 3 article-classifier integration lands, the classifier
    can override L4 with article-specific context. short_alt is hard-
    capped at 125 chars per imageSchema convention.
    """
    n = len(points)
    title = request.title or _default_title(series_data, request)
    units = _units_label(series_data, request.transformation)
    series_title = (series_data.metadata.title
                    if series_data.metadata else series_data.series_id)

    if not points:
        return {
            "level_1_elemental": f"Empty time-series chart titled '{title}'.",
            "level_2_statistical": "No data to summarize.",
            "level_3_perceptual": "Chart contains no data points.",
            "level_4_contextual": (
                f"No data available for {series_title} in the requested range."
            ),
            "short_alt": f"Empty chart: {title}.",
            "data_table_fallback": None,
        }

    values = [p["v"] for p in points]
    v_min = min(values)
    v_max = max(values)
    v_first = values[0]
    v_last = values[-1]
    t_first = points[0]["t"]
    t_last = points[-1]["t"]

    direction = "rising" if v_last > v_first else ("falling" if v_last < v_first else "flat")
    delta = v_last - v_first
    pct_change = (delta / abs(v_first) * 100.0) if v_first != 0 else None

    l1 = (
        f"Line chart titled '{title}' showing {n} observations of "
        f"{units} from {t_first} to {t_last}."
    )

    l2_parts = [
        f"Range: {v_min:.2f} to {v_max:.2f}",
        f"start: {v_first:.2f}",
        f"end: {v_last:.2f}",
        f"net change: {delta:+.2f}",
    ]
    if pct_change is not None:
        l2_parts.append(f"({pct_change:+.1f}%)")
    l2 = "; ".join(l2_parts) + "."

    # L3 perceptual: shape-of-data observation. Counts monotonic runs
    # (sign-changes in first differences) to characterize as monotonic
    # vs oscillating. Magnitude characterized by range / mean ratio.
    sign_changes = 0
    prev_diff = None
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        if d == 0:
            continue
        sign = 1 if d > 0 else -1
        if prev_diff is not None and sign != prev_diff:
            sign_changes += 1
        prev_diff = sign

    if sign_changes <= max(2, n // 10):
        shape = f"approximately monotonic {direction}"
    elif sign_changes <= n // 3:
        shape = f"{direction} overall with moderate fluctuation"
    else:
        shape = f"oscillating ({sign_changes} direction reversals) with net {direction} trend"

    mean_v = sum(values) / len(values)
    range_ratio = (v_max - v_min) / abs(mean_v) if mean_v else 0
    if range_ratio < 0.1:
        magnitude = "tight range"
    elif range_ratio < 0.5:
        magnitude = "moderate variation"
    else:
        magnitude = "wide variation"

    l3 = f"The series is {shape}, with {magnitude} relative to the mean."

    # L4 contextual: publication-neutral framing of what the chart
    # represents. The article body (and a future Phase 3 classifier-
    # produced override) carries the analytical interpretation; this
    # level just states what the chart enables the reader to see.
    direction_phrase = (
        "increased" if v_last > v_first else
        "decreased" if v_last < v_first else
        "remained roughly flat"
    )
    if pct_change is not None and abs(pct_change) >= 1.0:
        magnitude_phrase = f" by approximately {abs(pct_change):.0f}%"
    else:
        magnitude_phrase = ""
    l4 = (
        f"Shows how {series_title} {direction_phrase}{magnitude_phrase} "
        f"between {t_first} and {t_last}. See accompanying article body "
        f"for analytical interpretation."
    )

    short_alt = (
        f"{title}: {direction} from {v_first:.2f} to {v_last:.2f} "
        f"({t_first} to {t_last})."
    )
    # short_alt is hard-capped at 125 chars per imageSchema convention
    if len(short_alt) > 125:
        short_alt = short_alt[:122] + "..."

    return {
        "level_1_elemental": l1,
        "level_2_statistical": l2,
        "level_3_perceptual": l3,
        "level_4_contextual": l4,
        "short_alt": short_alt,
        "data_table_fallback": None,
    }


def _slug(request: FigureRequest, series_data: SeriesData) -> str:
    """Generate a stable, filesystem-safe slug for the figure."""
    if request.slug:
        base = request.slug
    else:
        sid = series_data.series_id.lower()
        tform = request.transformation
        base = f"fig-{sid}-{tform}"
    # Sanitize
    base = re.sub(r"[^a-z0-9_-]", "-", base.lower())
    base = re.sub(r"-+", "-", base).strip("-")
    return base or "fig-untitled"


# ---------------------------------------------------------------------------
# SVG rendering via the visual compiler CLI
# ---------------------------------------------------------------------------

def render_envelope_to_svg(envelope: dict, *,
                           timeout: int = RENDER_TIMEOUT_SECONDS) -> str:
    """Pipe an envelope dict through render-envelope.js and return SVG.

    Raises ``RuntimeError`` with a structured message on compiler
    failure (validation error, renderer error, adversarial block,
    empty SVG) or CLI-level failure (Node missing, jsdom boot, schema
    missing).
    """
    if not os.path.exists(RENDER_ENVELOPE_JS):
        raise RuntimeError(
            f"Visual compiler CLI not found at {RENDER_ENVELOPE_JS}. "
            f"Repository may be incomplete."
        )

    envelope_json = json.dumps(envelope)
    try:
        proc = subprocess.run(
            [NODE_BIN, RENDER_ENVELOPE_JS],
            input=envelope_json,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Node.js not available ({exc}). "
            f"Install Node and ensure 'node' is on PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Visual compiler timed out after {timeout}s rendering "
            f"envelope id={envelope.get('id', '?')}"
        ) from exc

    if proc.returncode != 0:
        # render-envelope.js writes a structured JSON error record to stderr
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(
            f"Visual compiler exit {proc.returncode} for envelope "
            f"id={envelope.get('id', '?')}: {stderr[:500]}"
        )

    svg = proc.stdout
    if not svg or not svg.strip().startswith(("<?xml", "<svg")):
        raise RuntimeError(
            f"Visual compiler returned non-SVG output for envelope "
            f"id={envelope.get('id', '?')}: {svg[:200]}"
        )

    return svg


# ---------------------------------------------------------------------------
# Top-level entry: render_figure
# ---------------------------------------------------------------------------

def render_figure(request: FigureRequest, *,
                  output_dir: str = DEFAULT_OUTPUT_DIR,
                  series_data: SeriesData | None = None) -> FigureResult:
    """Top-level: fetch + transform + envelope + render + write SVG.

    ``series_data`` may be passed to skip the FRED fetch (useful when
    the caller already fetched, or for testing).

    Returns ``FigureResult`` with ``success=True`` on full pipeline
    completion, ``success=False`` plus error_code/error_message on any
    failure. Failures are categorized by the FRED taxonomy when the
    error originates from the data fetch; "render_failed" for compiler
    errors; "invalid_request" for validation errors.
    """
    # Validation
    if request.chart_type not in CHART_TYPES:
        return FigureResult(
            success=False,
            error_code="invalid_request",
            error_message=(
                f"Unsupported chart_type '{request.chart_type}'. "
                f"Supported: {sorted(CHART_TYPES)}"
            ),
        )
    if request.transformation not in TRANSFORMATIONS:
        return FigureResult(
            success=False,
            error_code="invalid_request",
            error_message=(
                f"Unknown transformation '{request.transformation}'. "
                f"Supported: {sorted(TRANSFORMATIONS)}"
            ),
        )

    # Step 1: Fetch (unless caller provided)
    if series_data is None:
        try:
            series_data = fetch_series(request.series_query)
        except FredError as exc:
            return FigureResult(
                success=False,
                error_code=exc.code,
                error_message=f"FRED fetch failed: {exc.message}",
            )

    # Step 2: Transform
    frequency = series_data.metadata.frequency_short if series_data.metadata else None
    try:
        transformed = apply_transformation(
            series_data.observations, request.transformation, frequency=frequency,
        )
    except ValueError as exc:
        return FigureResult(
            success=False,
            error_code="invalid_request",
            error_message=str(exc),
        )

    # Step 3: Build envelope
    envelope = build_timeseries_envelope(series_data, request, transformed)

    # Step 4: Render via visual compiler
    try:
        svg = render_envelope_to_svg(envelope)
    except RuntimeError as exc:
        return FigureResult(
            success=False,
            envelope=envelope,
            error_code="render_failed",
            error_message=str(exc),
        )

    # Step 5: Write SVG to disk
    target_dir = output_dir
    if request.article_slug:
        target_dir = os.path.join(output_dir, request.article_slug)
    os.makedirs(target_dir, exist_ok=True)

    slug = _slug(request, series_data)
    svg_filename = f"{slug}.svg"
    svg_path = os.path.join(target_dir, svg_filename)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    # Step 6: Build figureSchema for Astro
    attribution = attribution_line(series_data)
    url_prefix = "/figures/"
    if request.article_slug:
        url_prefix = f"/figures/{request.article_slug}/"
    url = url_prefix + svg_filename

    fig_schema = {
        "url": url,
        "alt": envelope["semantic_description"]["short_alt"],
        "caption": (request.caption or _default_caption(series_data, request)),
        "credit": "Main Street Independent (algorithmic)",
        "source": _caption_source(series_data),
        "source_url": f"https://fred.stlouisfed.org/series/{series_data.series_id}",
        "source_retrieval_date": (series_data.retrieved_at[:10]
                                  if series_data.retrieved_at else ""),
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "chart_type": "timeseries",
        "data_window": _caption_period(transformed),
        "transformation": request.transformation,
        "ai_authored": True,
        "ai_model": "msi-data-viz-pipeline-v1",
    }

    return FigureResult(
        success=True,
        svg_path=svg_path,
        url=url,
        envelope=envelope,
        attribution=attribution,
        figure_schema=fig_schema,
    )


def _default_caption(series_data: SeriesData, request: FigureRequest) -> str:
    """Default caption when none supplied. Caps at 125 chars."""
    base = series_data.metadata.title if series_data.metadata else series_data.series_id
    tform = request.transformation
    if tform == "yoy_pct":
        cap = f"{base}, year-over-year percent change."
    elif tform == "first_diff":
        cap = f"{base}, period-over-period change."
    elif tform == "ytd":
        cap = f"{base}, year-to-date cumulative."
    else:
        cap = f"{base}."
    if len(cap) > 125:
        cap = cap[:122] + "..."
    return cap


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: data_viz_render.py <SERIES_ID> [transformation] [start_date]")
        print("  transformation: raw | yoy_pct | first_diff | ytd (default: raw)")
        print("  start_date: YYYY-MM-DD (default: series start)")
        print("Example: data_viz_render.py UNRATE raw 2020-01-01")
        sys.exit(1)

    series_id = sys.argv[1]
    transformation = sys.argv[2] if len(sys.argv) > 2 else "raw"
    start = sys.argv[3] if len(sys.argv) > 3 else None

    request = FigureRequest(
        series_query=SeriesQuery(
            series_id=series_id,
            observation_start=start,
        ),
        chart_type="timeseries",
        transformation=transformation,
    )

    result = render_figure(request)
    if result.success:
        print(f"Rendered: {result.svg_path}")
        print(f"URL:      {result.url}")
        print(f"Source:   {result.attribution}")
        print(f"Alt:      {result.figure_schema['alt']}")
    else:
        print(f"FAILED [{result.error_code}]: {result.error_message}")
        sys.exit(1)
