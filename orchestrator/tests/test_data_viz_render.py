#!/usr/bin/env python3
"""Tests for data_viz_render.py — the FRED → Vega-Lite → SVG pipeline.

Live tests (which call the visual compiler subprocess + need a FRED
key) are gated behind ORA_LIVE_DATA_VIZ=1.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(ORCHESTRATOR / "integrations"))

import data_viz_render as dvr  # noqa: E402
from data_viz_render import (  # noqa: E402
    FigureRequest,
    FigureResult,
    apply_transformation,
    build_timeseries_envelope,
    render_figure,
)
from fred_api import (  # noqa: E402
    Observation,
    SeriesData,
    SeriesMetadata,
    SeriesQuery,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_unrate_data() -> SeriesData:
    """Sample monthly UNRATE-like series, 24 observations 2024-2025."""
    obs = []
    base = 3.7
    for i in range(24):
        year = 2024 + (i // 12)
        month = (i % 12) + 1
        date = f"{year}-{month:02d}-01"
        # Mild upward drift with noise
        value = base + (i * 0.05) + ((i % 5) - 2) * 0.1
        obs.append(Observation(date=date, value=round(value, 2)))
    return SeriesData(
        series_id="UNRATE",
        observations=obs,
        metadata=SeriesMetadata(
            id="UNRATE",
            title="Unemployment Rate",
            units="Percent",
            units_short="%",
            frequency="Monthly",
            frequency_short="M",
            seasonal_adjustment="Seasonally Adjusted",
            last_updated="2025-12-30",
        ),
        retrieved_at="2026-05-13T15:00:00Z",
        cache_hit=False,
    )


def _sample_quarterly_data() -> SeriesData:
    """Sample quarterly GDP-like series, 8 quarters 2024-2025."""
    obs = []
    base = 21500.0
    for i in range(8):
        year = 2024 + (i // 4)
        quarter_month = (i % 4) * 3 + 1  # Jan, Apr, Jul, Oct
        date = f"{year}-{quarter_month:02d}-01"
        value = base + (i * 100.0)
        obs.append(Observation(date=date, value=round(value, 2)))
    return SeriesData(
        series_id="GDPC1",
        observations=obs,
        metadata=SeriesMetadata(
            id="GDPC1",
            title="Real Gross Domestic Product",
            units="Billions of Chained 2017 Dollars",
            units_short="Bil. of Chn. 2017 $",
            frequency="Quarterly",
            frequency_short="Q",
            seasonal_adjustment="SAAR",
            last_updated="2025-10-30",
        ),
        retrieved_at="2026-05-13T15:00:00Z",
    )


# ---------------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------------

class TestApplyTransformation(unittest.TestCase):

    def test_raw_returns_input_unchanged(self):
        data = _sample_unrate_data()
        out = apply_transformation(data.observations, "raw")
        self.assertEqual(len(out), len(data.observations))
        for original, transformed in zip(data.observations, out):
            self.assertEqual(original.date, transformed.date)
            self.assertEqual(original.value, transformed.value)

    def test_first_diff_first_obs_is_none(self):
        data = _sample_unrate_data()
        out = apply_transformation(data.observations, "first_diff")
        self.assertEqual(len(out), len(data.observations))
        self.assertIsNone(out[0].value)
        # Second observation is delta from first
        expected = data.observations[1].value - data.observations[0].value
        self.assertAlmostEqual(out[1].value, expected, places=4)

    def test_first_diff_handles_missing_values(self):
        obs = [
            Observation(date="2024-01-01", value=100.0),
            Observation(date="2024-02-01", value=None),
            Observation(date="2024-03-01", value=110.0),
        ]
        out = apply_transformation(obs, "first_diff")
        self.assertIsNone(out[0].value)  # always None
        self.assertIsNone(out[1].value)  # missing → None
        self.assertIsNone(out[2].value)  # prev was None → None

    def test_yoy_pct_monthly_lookback_12(self):
        data = _sample_unrate_data()  # 24 monthly obs
        out = apply_transformation(data.observations, "yoy_pct", frequency="M")
        # First 12 should be None (no prior year)
        for i in range(12):
            self.assertIsNone(out[i].value, f"obs {i} should be None")
        # 13th should be valid YoY
        self.assertIsNotNone(out[12].value)
        # Sanity check: a positive drift should produce positive YoY
        self.assertGreater(out[12].value, 0)

    def test_yoy_pct_quarterly_lookback_4(self):
        data = _sample_quarterly_data()  # 8 quarterly obs
        out = apply_transformation(data.observations, "yoy_pct", frequency="Q")
        # First 4 should be None
        for i in range(4):
            self.assertIsNone(out[i].value)
        # 5th should be valid
        self.assertIsNotNone(out[4].value)

    def test_yoy_pct_handles_zero_prior(self):
        obs = [
            Observation(date="2024-01-01", value=0.0),
            Observation(date="2024-02-01", value=10.0),
            Observation(date="2024-03-01", value=20.0),
        ]
        # With monthly inferred, lookback would be 12 — too small for the
        # series, so all should be None. Force lookback by using frequency.
        out = apply_transformation(obs, "yoy_pct", frequency="M")
        # All None because none of them have a prior 12 months back
        for o in out:
            self.assertIsNone(o.value)

    def test_ytd_resets_at_year_boundary(self):
        obs = [
            Observation(date="2024-11-01", value=10.0),
            Observation(date="2024-12-01", value=20.0),
            Observation(date="2025-01-01", value=5.0),
            Observation(date="2025-02-01", value=15.0),
        ]
        out = apply_transformation(obs, "ytd")
        self.assertEqual(out[0].value, 10.0)   # 2024 starts at 10
        self.assertEqual(out[1].value, 30.0)   # 10+20
        self.assertEqual(out[2].value, 5.0)    # year boundary — reset
        self.assertEqual(out[3].value, 20.0)   # 5+15

    def test_unknown_transformation_raises(self):
        with self.assertRaises(ValueError):
            apply_transformation([], "unsupported_xform")

    def test_empty_observations_returns_empty(self):
        for tform in ("raw", "first_diff", "yoy_pct", "ytd"):
            self.assertEqual(apply_transformation([], tform), [])


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------

class TestBuildTimeseriesEnvelope(unittest.TestCase):

    def test_envelope_has_required_top_level_fields(self):
        data = _sample_unrate_data()
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
        )
        env = build_timeseries_envelope(data, request, data.observations)
        for field in ("schema_version", "id", "type", "mode_context",
                      "relation_to_prose", "spec", "semantic_description",
                      "title"):
            self.assertIn(field, env, f"missing field: {field}")
        self.assertEqual(env["type"], "time_series")
        self.assertEqual(env["schema_version"], "0.2")

    def test_spec_has_vega_lite_shape(self):
        data = _sample_unrate_data()
        request = FigureRequest(series_query=SeriesQuery(series_id="UNRATE"))
        env = build_timeseries_envelope(data, request, data.observations)
        spec = env["spec"]
        self.assertIn("$schema", spec)
        self.assertIn("data", spec)
        self.assertIn("values", spec["data"])
        self.assertIn("mark", spec)
        self.assertIn("encoding", spec)
        self.assertIn("x", spec["encoding"])
        self.assertIn("y", spec["encoding"])
        self.assertIn("caption", spec)

    def test_data_values_use_t_v_keys(self):
        data = _sample_unrate_data()
        request = FigureRequest(series_query=SeriesQuery(series_id="UNRATE"))
        env = build_timeseries_envelope(data, request, data.observations)
        values = env["spec"]["data"]["values"]
        self.assertGreater(len(values), 0)
        for v in values[:3]:
            self.assertIn("t", v)
            self.assertIn("v", v)

    def test_none_values_filtered_from_data(self):
        obs = [
            Observation(date="2024-01-01", value=10.0),
            Observation(date="2024-02-01", value=None),
            Observation(date="2024-03-01", value=20.0),
        ]
        data = SeriesData(
            series_id="X",
            observations=obs,
            metadata=SeriesMetadata(
                id="X", title="Test", units="u", units_short="u",
                frequency="Monthly", frequency_short="M",
                seasonal_adjustment="", last_updated="",
            ),
        )
        request = FigureRequest(series_query=SeriesQuery(series_id="X"))
        env = build_timeseries_envelope(data, request, data.observations)
        values = env["spec"]["data"]["values"]
        self.assertEqual(len(values), 2)  # None filtered
        for v in values:
            self.assertIsNotNone(v["v"])

    def test_semantic_description_levels_populated(self):
        data = _sample_unrate_data()
        request = FigureRequest(series_query=SeriesQuery(series_id="UNRATE"))
        env = build_timeseries_envelope(data, request, data.observations)
        sem = env["semantic_description"]
        # All four levels populated as non-null strings — the visual
        # compiler's schema rejects null at L3/L4. L4 may be overridden
        # by a future Phase 3 article-classifier with article-specific
        # context; the default here is publication-neutral framing.
        self.assertIsNotNone(sem["level_1_elemental"])
        self.assertIsNotNone(sem["level_2_statistical"])
        self.assertIsNotNone(sem["level_3_perceptual"])
        self.assertIsNotNone(sem["level_4_contextual"])
        self.assertIsInstance(sem["level_3_perceptual"], str)
        self.assertIsInstance(sem["level_4_contextual"], str)
        # short_alt populated and ≤125 chars
        self.assertIsNotNone(sem["short_alt"])
        self.assertLessEqual(len(sem["short_alt"]), 125)

    def test_yoy_title_includes_yoy_label(self):
        data = _sample_unrate_data()
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
            transformation="yoy_pct",
        )
        transformed = apply_transformation(
            data.observations, "yoy_pct", frequency="M",
        )
        env = build_timeseries_envelope(data, request, transformed)
        self.assertIn("year-over-year", env["title"])

    def test_id_slug_is_filesystem_safe(self):
        data = _sample_unrate_data()
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
            transformation="yoy_pct",
        )
        env = build_timeseries_envelope(data, request, data.observations)
        # Slug should be lowercase, no spaces, no special chars
        slug = env["id"]
        import re
        self.assertTrue(re.match(r"^[a-z0-9_-]+$", slug),
                        f"unsafe slug: {slug}")


# ---------------------------------------------------------------------------
# render_envelope_to_svg — mocked subprocess
# ---------------------------------------------------------------------------

class TestRenderEnvelopeToSvg(unittest.TestCase):

    def test_success_returns_svg(self):
        envelope = {"id": "fig-test", "type": "time_series"}
        fake_svg = '<?xml version="1.0"?>\n<svg></svg>'
        fake_proc = mock.MagicMock(returncode=0, stdout=fake_svg, stderr="")
        with mock.patch("subprocess.run", return_value=fake_proc):
            with mock.patch("os.path.exists", return_value=True):
                svg = dvr.render_envelope_to_svg(envelope)
        # The renderer injects a portable <style> block; the original
        # content must still be present and the SVG must be well-formed.
        self.assertTrue(svg.startswith('<?xml version="1.0"?>\n<svg>'))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn("<style>", svg)
        self.assertIn(".mark-line path", svg)

    def test_missing_compiler_raises(self):
        envelope = {"id": "fig-test"}
        with mock.patch("os.path.exists", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                dvr.render_envelope_to_svg(envelope)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_compiler_nonzero_exit_raises(self):
        envelope = {"id": "fig-test"}
        fake_proc = mock.MagicMock(returncode=1, stdout="",
                                   stderr='{"error":"validation failed"}')
        with mock.patch("subprocess.run", return_value=fake_proc):
            with mock.patch("os.path.exists", return_value=True):
                with self.assertRaises(RuntimeError) as ctx:
                    dvr.render_envelope_to_svg(envelope)
        self.assertIn("compiler exit 1", str(ctx.exception).lower())

    def test_non_svg_output_raises(self):
        envelope = {"id": "fig-test"}
        fake_proc = mock.MagicMock(returncode=0, stdout="not really svg",
                                   stderr="")
        with mock.patch("subprocess.run", return_value=fake_proc):
            with mock.patch("os.path.exists", return_value=True):
                with self.assertRaises(RuntimeError) as ctx:
                    dvr.render_envelope_to_svg(envelope)
        self.assertIn("non-svg", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# render_figure — full pipeline with mocks
# ---------------------------------------------------------------------------

class TestRenderFigure(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="ora-test-figures-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_invalid_chart_type_returns_error(self):
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
            chart_type="not_a_real_type",
        )
        result = render_figure(request, output_dir=self.tmp_dir)
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_request")

    def test_invalid_transformation_returns_error(self):
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
            transformation="not_real",
        )
        result = render_figure(request, output_dir=self.tmp_dir,
                               series_data=_sample_unrate_data())
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "invalid_request")

    def test_full_pipeline_with_caller_provided_data(self):
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
        )
        fake_svg = '<?xml version="1.0"?>\n<svg></svg>'
        fake_proc = mock.MagicMock(returncode=0, stdout=fake_svg, stderr="")
        with mock.patch("subprocess.run", return_value=fake_proc), \
             mock.patch("os.path.exists", side_effect=lambda p: True):
            result = render_figure(
                request, output_dir=self.tmp_dir,
                series_data=_sample_unrate_data(),
            )

        self.assertTrue(result.success, result.error_message)
        self.assertTrue(result.svg_path.endswith(".svg"))
        self.assertTrue(os.path.exists(result.svg_path))
        with open(result.svg_path) as f:
            written = f.read()
        # Portable <style> block injected; raw envelope content still present.
        self.assertTrue(written.startswith('<?xml version="1.0"?>\n<svg>'))
        self.assertTrue(written.endswith("</svg>"))
        self.assertIn("<style>", written)

        # Envelope
        self.assertEqual(result.envelope["type"], "time_series")
        # Attribution
        self.assertIn("Source: FRED", result.attribution)
        # figureSchema completeness
        for field in ("url", "alt", "caption", "credit", "source",
                      "source_url", "source_retrieval_date", "license",
                      "chart_type", "data_window", "transformation",
                      "ai_authored", "ai_model"):
            self.assertIn(field, result.figure_schema, f"missing: {field}")
        self.assertEqual(result.figure_schema["chart_type"], "timeseries")
        self.assertEqual(result.figure_schema["transformation"], "raw")

    def test_article_slug_writes_to_subdirectory(self):
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
            article_slug="2026-05-13-jobs-report",
        )
        fake_svg = '<?xml version="1.0"?>\n<svg></svg>'
        fake_proc = mock.MagicMock(returncode=0, stdout=fake_svg, stderr="")
        with mock.patch("subprocess.run", return_value=fake_proc), \
             mock.patch("os.path.exists", side_effect=lambda p: True):
            result = render_figure(
                request, output_dir=self.tmp_dir,
                series_data=_sample_unrate_data(),
            )

        self.assertTrue(result.success)
        self.assertIn("2026-05-13-jobs-report", result.svg_path)
        self.assertTrue(result.url.startswith("/figures/2026-05-13-jobs-report/"))

    def test_fred_error_propagates_with_code(self):
        # Import FredError from the same module instance dvr uses, so the
        # except clause's class identity check matches. (Going through
        # `from fred_api import FredError` would create a different class
        # via a different sys.path resolution and the except wouldn't catch.)
        FredErrorCls = dvr.FredError
        request = FigureRequest(
            series_query=SeriesQuery(series_id="MADEUP"),
        )
        with mock.patch.object(dvr, "fetch_series",
                               side_effect=FredErrorCls("series_not_found",
                                                        "no such series",
                                                        series_id="MADEUP")):
            result = render_figure(request, output_dir=self.tmp_dir)
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "series_not_found")

    def test_compiler_failure_returns_error_with_envelope(self):
        request = FigureRequest(
            series_query=SeriesQuery(series_id="UNRATE"),
        )
        fake_proc = mock.MagicMock(returncode=1, stdout="",
                                   stderr="adversarial block")
        with mock.patch("subprocess.run", return_value=fake_proc), \
             mock.patch("os.path.exists", side_effect=lambda p: True):
            result = render_figure(
                request, output_dir=self.tmp_dir,
                series_data=_sample_unrate_data(),
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "render_failed")
        # Envelope is preserved on render failure (useful for debugging)
        self.assertEqual(result.envelope.get("type"), "time_series")


# ---------------------------------------------------------------------------
# Live test (opt-in)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.environ.get("ORA_LIVE_DATA_VIZ") == "1",
    "Live data-viz test disabled (set ORA_LIVE_DATA_VIZ=1 to enable; "
    "requires FRED_API_KEY and node + visual compiler installed).",
)
class TestRenderFigureLive(unittest.TestCase):

    def test_render_unrate_end_to_end(self):
        tmp_dir = tempfile.mkdtemp(prefix="ora-live-data-viz-")
        try:
            request = FigureRequest(
                series_query=SeriesQuery(
                    series_id="UNRATE",
                    observation_start="2024-01-01",
                ),
                chart_type="timeseries",
                transformation="raw",
            )
            result = render_figure(request, output_dir=tmp_dir)
            self.assertTrue(result.success, result.error_message)
            self.assertTrue(os.path.exists(result.svg_path))
            with open(result.svg_path) as f:
                svg = f.read()
            self.assertIn("<svg", svg)
            self.assertGreater(len(svg), 1000)  # rendered chart should be substantial
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
