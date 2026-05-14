#!/usr/bin/env python3
"""Tests for the FRED API integration (orchestrator/integrations/fred_api.py).

Live calls gated behind ``ORA_LIVE_FRED=1`` env var so the default test
run uses mocked HTTP (live calls require a configured FRED API key and
should not fire on every test run).
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(ORCHESTRATOR / "integrations"))

import fred_api  # noqa: E402
from fred_api import (  # noqa: E402
    FredError,
    Observation,
    SeriesData,
    SeriesMetadata,
    SeriesQuery,
    attribution_line,
    fetch_series,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

SAMPLE_OBSERVATIONS_PAYLOAD = {
    "realtime_start": "2026-05-13",
    "realtime_end": "2026-05-13",
    "observation_start": "2020-01-01",
    "observation_end": "2026-05-13",
    "units": "lin",
    "output_type": 1,
    "file_type": "json",
    "order_by": "observation_date",
    "sort_order": "asc",
    "count": 4,
    "offset": 0,
    "limit": 100000,
    "observations": [
        {"realtime_start": "2026-05-13", "realtime_end": "2026-05-13",
         "date": "2024-01-01", "value": "21500.5"},
        {"realtime_start": "2026-05-13", "realtime_end": "2026-05-13",
         "date": "2024-04-01", "value": "21625.3"},
        {"realtime_start": "2026-05-13", "realtime_end": "2026-05-13",
         "date": "2024-07-01", "value": "."},  # Missing value
        {"realtime_start": "2026-05-13", "realtime_end": "2026-05-13",
         "date": "2024-10-01", "value": "21845.0"},
    ],
}

SAMPLE_SERIES_PAYLOAD = {
    "realtime_start": "2026-05-13",
    "realtime_end": "2026-05-13",
    "seriess": [{
        "id": "GDPC1",
        "realtime_start": "2026-05-13",
        "realtime_end": "2026-05-13",
        "title": "Real Gross Domestic Product",
        "observation_start": "1947-01-01",
        "observation_end": "2026-04-01",
        "frequency": "Quarterly",
        "frequency_short": "Q",
        "units": "Billions of Chained 2017 Dollars",
        "units_short": "Bil. of Chn. 2017 $",
        "seasonal_adjustment": "Seasonally Adjusted Annual Rate",
        "seasonal_adjustment_short": "SAAR",
        "last_updated": "2026-04-30 07:51:30-05",
        "popularity": 95,
        "notes": "BEA Account Code: A191RX",
    }],
}


class _FakeHTTPResponse:
    """Minimal urllib.request.urlopen response shim for tests."""
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def _fake_urlopen(payload):
    """Build a fake urlopen that returns the given JSON payload."""
    body = json.dumps(payload).encode("utf-8")
    def _fn(req, **kwargs):
        return _FakeHTTPResponse(body)
    return _fn


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestSeriesQueryConstruction(unittest.TestCase):

    def test_minimal_query_just_series_id(self):
        q = SeriesQuery(series_id="GDPC1")
        self.assertEqual(q.series_id, "GDPC1")
        self.assertIsNone(q.observation_start)
        self.assertIsNone(q.observation_end)
        self.assertIsNone(q.frequency)
        self.assertIsNone(q.units)
        self.assertEqual(q.aggregation_method, "avg")
        self.assertEqual(q.limit, 100000)

    def test_full_query_all_fields(self):
        q = SeriesQuery(
            series_id="UNRATE",
            observation_start="2020-01-01",
            observation_end="2026-05-01",
            frequency="m",
            aggregation_method="avg",
            units="pc1",
            limit=500,
        )
        self.assertEqual(q.series_id, "UNRATE")
        self.assertEqual(q.observation_start, "2020-01-01")
        self.assertEqual(q.units, "pc1")


class TestParseValue(unittest.TestCase):

    def test_numeric_string(self):
        self.assertEqual(fred_api._parse_value("21500.5"), 21500.5)

    def test_missing_marker_returns_none(self):
        self.assertIsNone(fred_api._parse_value("."))

    def test_empty_string_returns_none(self):
        self.assertIsNone(fred_api._parse_value(""))

    def test_none_returns_none(self):
        self.assertIsNone(fred_api._parse_value(None))

    def test_invalid_string_returns_none(self):
        self.assertIsNone(fred_api._parse_value("not-a-number"))

    def test_integer_string(self):
        self.assertEqual(fred_api._parse_value("0"), 0.0)
        self.assertEqual(fred_api._parse_value("100"), 100.0)


class TestFetchSeriesMocked(unittest.TestCase):
    """End-to-end mocked tests of fetch_series."""

    def setUp(self):
        self.cache_dir = "/tmp/ora-test-fred-cache-" + str(os.getpid())
        # Disable cache reads to ensure HTTP path runs each test
        os.environ["ORA_FRED_NO_CACHE"] = "1"

    def tearDown(self):
        os.environ.pop("ORA_FRED_NO_CACHE", None)
        if os.path.exists(self.cache_dir):
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_fetch_series_returns_data_with_observations(self):
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                # First call = observations, second = metadata
                m_urlopen.side_effect = [
                    _FakeHTTPResponse(json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()),
                    _FakeHTTPResponse(json.dumps(SAMPLE_SERIES_PAYLOAD).encode()),
                ]
                data = fetch_series(
                    SeriesQuery(series_id="GDPC1"),
                    cache_dir=self.cache_dir,
                )

        self.assertEqual(data.series_id, "GDPC1")
        self.assertEqual(len(data.observations), 4)
        self.assertEqual(data.observations[0].date, "2024-01-01")
        self.assertEqual(data.observations[0].value, 21500.5)
        # Missing value handled
        self.assertEqual(data.observations[2].date, "2024-07-01")
        self.assertIsNone(data.observations[2].value)
        # Last observation
        self.assertEqual(data.observations[-1].value, 21845.0)
        # Metadata
        self.assertIsNotNone(data.metadata)
        self.assertEqual(data.metadata.title, "Real Gross Domestic Product")
        self.assertEqual(data.metadata.frequency, "Quarterly")
        # Provenance
        self.assertFalse(data.cache_hit)
        self.assertTrue(data.retrieved_at)

    def test_fetch_series_without_metadata(self):
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.return_value = _FakeHTTPResponse(
                    json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()
                )
                data = fetch_series(
                    SeriesQuery(series_id="GDPC1"),
                    cache_dir=self.cache_dir,
                    fetch_metadata=False,
                )
        self.assertIsNone(data.metadata)
        self.assertEqual(len(data.observations), 4)

    def test_missing_api_key_raises_model_unavailable(self):
        with mock.patch.object(fred_api, "_get_api_key", return_value=None):
            with self.assertRaises(FredError) as ctx:
                fetch_series(SeriesQuery(series_id="GDPC1"),
                             cache_dir=self.cache_dir)
        self.assertEqual(ctx.exception.code, "model_unavailable")
        self.assertIn("FRED_API_KEY", str(ctx.exception))

    def test_empty_observations_raises_data_unavailable(self):
        empty_payload = {**SAMPLE_OBSERVATIONS_PAYLOAD, "observations": []}
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.return_value = _FakeHTTPResponse(
                    json.dumps(empty_payload).encode()
                )
                with self.assertRaises(FredError) as ctx:
                    fetch_series(SeriesQuery(series_id="UNKNOWN_SERIES"),
                                 cache_dir=self.cache_dir,
                                 fetch_metadata=False)
        self.assertEqual(ctx.exception.code, "data_unavailable")
        self.assertEqual(ctx.exception.series_id, "UNKNOWN_SERIES")

    def test_empty_series_id_raises_model_unavailable(self):
        with self.assertRaises(FredError) as ctx:
            fetch_series(SeriesQuery(series_id=""), cache_dir=self.cache_dir)
        self.assertEqual(ctx.exception.code, "model_unavailable")


class TestHTTPErrorMapping(unittest.TestCase):
    """The HTTP error → FRED error code translation table."""

    def test_429_maps_to_quota_exceeded(self):
        import urllib.error
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = urllib.error.HTTPError(
                    "url", 429, "Too Many Requests",
                    {}, mock.MagicMock(read=lambda: b"rate limit hit")
                )
                with self.assertRaises(FredError) as ctx:
                    fetch_series(SeriesQuery(series_id="GDPC1"))
        self.assertEqual(ctx.exception.code, "quota_exceeded")

    def test_400_does_not_exist_maps_to_series_not_found(self):
        import urllib.error
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = urllib.error.HTTPError(
                    "url", 400, "Bad Request",
                    {}, mock.MagicMock(read=lambda: b"The series does not exist.")
                )
                with self.assertRaises(FredError) as ctx:
                    fetch_series(SeriesQuery(series_id="MADEUP_SERIES"))
        self.assertEqual(ctx.exception.code, "series_not_found")

    def test_404_maps_to_series_not_found(self):
        import urllib.error
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = urllib.error.HTTPError(
                    "url", 404, "Not Found",
                    {}, mock.MagicMock(read=lambda: b"Not found")
                )
                with self.assertRaises(FredError) as ctx:
                    fetch_series(SeriesQuery(series_id="X"))
        self.assertEqual(ctx.exception.code, "series_not_found")

    def test_401_maps_to_model_unavailable(self):
        import urllib.error
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = urllib.error.HTTPError(
                    "url", 401, "Unauthorized",
                    {}, mock.MagicMock(read=lambda: b"Bad API key")
                )
                with self.assertRaises(FredError) as ctx:
                    fetch_series(SeriesQuery(series_id="GDPC1"))
        self.assertEqual(ctx.exception.code, "model_unavailable")
        self.assertIn("auth", str(ctx.exception).lower())

    def test_url_error_maps_to_network_error(self):
        import urllib.error
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = urllib.error.URLError("Connection refused")
                with self.assertRaises(FredError) as ctx:
                    fetch_series(SeriesQuery(series_id="GDPC1"))
        self.assertEqual(ctx.exception.code, "network_error")


class TestCache(unittest.TestCase):

    def setUp(self):
        self.cache_dir = "/tmp/ora-test-fred-cache-" + str(os.getpid())
        os.environ.pop("ORA_FRED_NO_CACHE", None)

    def tearDown(self):
        if os.path.exists(self.cache_dir):
            import shutil
            shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_cache_write_and_read_roundtrip(self):
        # First fetch — writes cache
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = [
                    _FakeHTTPResponse(json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()),
                    _FakeHTTPResponse(json.dumps(SAMPLE_SERIES_PAYLOAD).encode()),
                ]
                first = fetch_series(SeriesQuery(series_id="GDPC1"),
                                     cache_dir=self.cache_dir)
        self.assertFalse(first.cache_hit)

        # Second fetch — should hit cache, no HTTP calls made
        with mock.patch("urllib.request.urlopen") as m_urlopen:
            second = fetch_series(SeriesQuery(series_id="GDPC1"),
                                  cache_dir=self.cache_dir)
            m_urlopen.assert_not_called()
        self.assertTrue(second.cache_hit)
        self.assertEqual(len(second.observations), len(first.observations))
        self.assertEqual(second.observations[0].value, first.observations[0].value)
        self.assertEqual(second.metadata.title, first.metadata.title)

    def test_cache_disabled_via_env(self):
        # First fetch writes cache
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = [
                    _FakeHTTPResponse(json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()),
                    _FakeHTTPResponse(json.dumps(SAMPLE_SERIES_PAYLOAD).encode()),
                ]
                fetch_series(SeriesQuery(series_id="GDPC1"),
                             cache_dir=self.cache_dir)

        # Second fetch with cache disabled — should hit HTTP again
        os.environ["ORA_FRED_NO_CACHE"] = "1"
        try:
            with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
                with mock.patch("urllib.request.urlopen") as m_urlopen:
                    m_urlopen.side_effect = [
                        _FakeHTTPResponse(json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()),
                        _FakeHTTPResponse(json.dumps(SAMPLE_SERIES_PAYLOAD).encode()),
                    ]
                    data = fetch_series(SeriesQuery(series_id="GDPC1"),
                                        cache_dir=self.cache_dir)
                    self.assertEqual(m_urlopen.call_count, 2)  # observations + metadata
            self.assertFalse(data.cache_hit)
        finally:
            os.environ.pop("ORA_FRED_NO_CACHE", None)

    def test_cache_ttl_respected(self):
        # Write cache
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = [
                    _FakeHTTPResponse(json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()),
                    _FakeHTTPResponse(json.dumps(SAMPLE_SERIES_PAYLOAD).encode()),
                ]
                fetch_series(SeriesQuery(series_id="GDPC1"),
                             cache_dir=self.cache_dir)

        # Read with TTL=0 (cache should be considered expired)
        with mock.patch.object(fred_api, "_get_api_key", return_value="fake-key"):
            with mock.patch("urllib.request.urlopen") as m_urlopen:
                m_urlopen.side_effect = [
                    _FakeHTTPResponse(json.dumps(SAMPLE_OBSERVATIONS_PAYLOAD).encode()),
                    _FakeHTTPResponse(json.dumps(SAMPLE_SERIES_PAYLOAD).encode()),
                ]
                data = fetch_series(SeriesQuery(series_id="GDPC1"),
                                    cache_dir=self.cache_dir,
                                    cache_ttl_seconds=0)
                self.assertEqual(m_urlopen.call_count, 2)  # cache expired, fresh fetch
        self.assertFalse(data.cache_hit)


class TestAttributionLine(unittest.TestCase):

    def test_with_metadata(self):
        data = SeriesData(
            series_id="GDPC1",
            observations=[],
            metadata=SeriesMetadata(
                id="GDPC1", title="Real Gross Domestic Product",
                units="Billions of Chained 2017 Dollars", units_short="Bil.",
                frequency="Quarterly", frequency_short="Q",
                seasonal_adjustment="SAAR", last_updated="2026-04-30",
            ),
            retrieved_at="2026-05-13T15:30:00Z",
        )
        line = attribution_line(data)
        self.assertIn("Source: FRED", line)
        self.assertIn("GDPC1", line)
        self.assertIn("Real Gross Domestic Product", line)
        self.assertIn("2026-05-13", line)

    def test_without_metadata(self):
        data = SeriesData(
            series_id="UNRATE",
            observations=[],
            metadata=None,
            retrieved_at="2026-05-13T15:30:00Z",
        )
        line = attribution_line(data)
        self.assertIn("Source: FRED", line)
        self.assertIn("UNRATE", line)
        self.assertNotIn("(", line)  # no title parens


# ---------------------------------------------------------------------------
# Live test (opt-in)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    os.environ.get("ORA_LIVE_FRED") == "1",
    "Live FRED call disabled (set ORA_LIVE_FRED=1 to enable; requires "
    "FRED_API_KEY in env or keychain).",
)
class TestFredLive(unittest.TestCase):

    def test_fetch_unrate_returns_recent_observations(self):
        # UNRATE = unemployment rate; one of the most-watched FRED series.
        # Use a small cache dir per test.
        cache_dir = "/tmp/ora-live-fred-test"
        try:
            data = fetch_series(
                SeriesQuery(series_id="UNRATE",
                            observation_start="2024-01-01"),
                cache_dir=cache_dir,
            )
            self.assertGreater(len(data.observations), 0)
            self.assertEqual(data.series_id, "UNRATE")
            # Last observation should be a recent month
            last_date = data.observations[-1].date
            self.assertTrue(last_date.startswith("202"))
            # Metadata should be populated
            self.assertIsNotNone(data.metadata)
            self.assertIn("Unemployment", data.metadata.title)
        finally:
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
