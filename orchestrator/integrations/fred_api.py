"""FRED (Federal Reserve Economic Data) API integration.

Fetches economic time-series data from the St. Louis Fed's FRED API
for use by the MSI data-visualization pipeline. This is the data-fetch
primitive that the chart-emitter pipeline (Phase 4) consumes; the
article-classifier (Phase 3) decides which series to fetch based on
article content + the Distributional Honesty Research Library.

Endpoint
--------

``https://api.stlouisfed.org/fred/series/observations``

The API is free; an API key is required (free registration at
https://fred.stlouisfed.org/docs/api/api_key.html). Rate limits are
generous — 120 requests per 60 seconds — well within publication
needs.

Authentication
--------------

API key resolved at call time:
1. ``$FRED_API_KEY`` environment variable (highest priority)
2. macOS Keychain via the ``keyring`` library:
   service ``"ora"``, username ``"fred-api-key"``

The keychain pattern matches the rest of Ora's integration modules
(openai_images, civitai_images, gemini_images).

Error mapping
-------------

Errors translated to a small taxonomy for upstream handling:

  * ``data_unavailable``  — FRED returned 200 but no observations
                            (series exists but has no data in the
                            requested range)
  * ``series_not_found``  — FRED returned 400/404 with "series does
                            not exist" or similar
  * ``quota_exceeded``    — FRED returned 429 (rate limit hit)
  * ``network_error``     — connection / timeout / non-API HTTP error
  * ``model_unavailable`` — missing API key, auth failure, unexpected
                            error

Cache layer
-----------

File-based cache at ``~/ora/cache/fred/``. Cache key is a hash of
(series_id, observation_start, observation_end, frequency, units).
TTL is 12 hours by default — most FRED series update monthly, so a
12-hour cache is well within freshness needs while avoiding redundant
API calls during a publication's daily article cycle.

Cache files are JSON; readable, editable, deletable. Setting
``$ORA_FRED_NO_CACHE=1`` disables cache reads (writes still happen).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRED_BASE_URL = "https://api.stlouisfed.org/fred"
DEFAULT_CACHE_DIR = os.path.expanduser("~/ora/cache/fred/")
DEFAULT_CACHE_TTL_SECONDS = 12 * 3600  # 12 hours
DEFAULT_TIMEOUT_SECONDS = 30
USER_AGENT = "Ora/1.0 (Main Street Independent data-viz pipeline)"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SeriesQuery:
    """Specification for a FRED data fetch.

    ``series_id`` is the FRED series identifier (e.g., ``"GDPC1"``,
    ``"FEDFUNDS"``, ``"UNRATE"``). The other fields are FRED API
    parameters that shape the response.
    """
    series_id: str
    observation_start: str | None = None  # YYYY-MM-DD; default = series start
    observation_end: str | None = None    # YYYY-MM-DD; default = today
    frequency: str | None = None          # d/w/bw/m/q/sa/a or None for native
    aggregation_method: str = "avg"       # avg / sum / eop (when frequency aggregation applies)
    units: str | None = None              # lin / chg / ch1 / pch / pc1 / pca / cch / cca / log
    limit: int = 100000                   # max observations (FRED max)


@dataclass
class Observation:
    """A single (date, value) pair from a FRED series.

    ``value`` is None when FRED returned "." (the missing-value marker).
    """
    date: str   # YYYY-MM-DD
    value: float | None


@dataclass
class SeriesMetadata:
    """Metadata for a FRED series — the 'about' fields the API returns
    on the /fred/series endpoint. Useful for chart titles, axis labels,
    and the standard 'Source: FRED, series X, retrieved YYYY-MM-DD'
    attribution line."""
    id: str
    title: str
    units: str
    units_short: str
    frequency: str
    frequency_short: str
    seasonal_adjustment: str
    last_updated: str
    notes: str = ""


@dataclass
class SeriesData:
    """Pure data fetch result. Returned by ``fetch_series``.

    The chart-emitter pipeline (Phase 4) consumes this to build
    Vega-Lite envelopes; the article-classifier (Phase 3) consumes it
    to verify a series actually has data for the article's claim period.
    """
    series_id: str
    observations: list[Observation]
    metadata: SeriesMetadata | None = None
    retrieved_at: str = ""
    cache_hit: bool = False
    query: SeriesQuery | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FredError(Exception):
    """Base class for FRED integration errors. Carries an error code from
    the small taxonomy documented at module-level (data_unavailable,
    series_not_found, quota_exceeded, network_error, model_unavailable)
    so upstream handlers can route errors uniformly."""

    def __init__(self, code: str, message: str, series_id: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.series_id = series_id


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Resolve the FRED API key from env or keychain."""
    key = os.environ.get("FRED_API_KEY") or ""
    if key:
        return key
    try:
        import keyring
        return keyring.get_password("ora", "fred-api-key") or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

def _cache_key(query: SeriesQuery) -> str:
    """Build a stable hash key for caching a query result."""
    raw = json.dumps(asdict(query), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _cache_path(cache_dir: str, query: SeriesQuery) -> str:
    return os.path.join(cache_dir, f"{query.series_id}_{_cache_key(query)}.json")


def _read_cache(query: SeriesQuery, cache_dir: str, ttl_seconds: int) -> SeriesData | None:
    """Return cached SeriesData if present and within TTL, else None.
    Disabled when ``$ORA_FRED_NO_CACHE=1`` is set."""
    if os.environ.get("ORA_FRED_NO_CACHE") == "1":
        return None
    path = _cache_path(cache_dir, query)
    if not os.path.exists(path):
        return None
    try:
        age = time.time() - os.path.getmtime(path)
        if age > ttl_seconds:
            return None
        with open(path, "r") as f:
            payload = json.load(f)
        return _deserialize_series_data(payload, query)
    except Exception:
        return None  # cache miss on any read error


def _write_cache(data: SeriesData, cache_dir: str):
    """Write SeriesData to cache. Failures are silent — caching is
    best-effort, never blocking."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        path = _cache_path(cache_dir, data.query)
        payload = {
            "series_id": data.series_id,
            "observations": [asdict(o) for o in data.observations],
            "metadata": asdict(data.metadata) if data.metadata else None,
            "retrieved_at": data.retrieved_at,
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def _deserialize_series_data(payload: dict, query: SeriesQuery) -> SeriesData:
    """Reconstruct SeriesData from a cached JSON payload."""
    observations = [Observation(**o) for o in payload.get("observations", [])]
    metadata_payload = payload.get("metadata")
    metadata = SeriesMetadata(**metadata_payload) if metadata_payload else None
    return SeriesData(
        series_id=payload["series_id"],
        observations=observations,
        metadata=metadata,
        retrieved_at=payload.get("retrieved_at", ""),
        cache_hit=True,
        query=query,
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http_get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """GET ``url``, parse JSON response, return dict.

    Raises FredError with the appropriate taxonomy code on HTTP errors,
    network errors, or invalid JSON. Caller is responsible for
    series-level error interpretation (e.g., empty observations =
    data_unavailable).
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8")
        except Exception:
            pass

        if exc.code == 429:
            raise FredError(
                "quota_exceeded",
                f"FRED rate limit hit (HTTP 429). Body: {body_text[:200]}",
            ) from exc
        if exc.code in (400, 404):
            # FRED returns 400 with "series does not exist" for unknown IDs
            if "does not exist" in body_text.lower() or exc.code == 404:
                raise FredError(
                    "series_not_found",
                    f"Series not found (HTTP {exc.code}): {body_text[:200]}",
                ) from exc
            raise FredError(
                "model_unavailable",
                f"FRED HTTP {exc.code}: {body_text[:200]}",
            ) from exc
        if exc.code in (401, 403):
            raise FredError(
                "model_unavailable",
                f"FRED auth failure (HTTP {exc.code}). Check FRED_API_KEY. "
                f"Body: {body_text[:200]}",
            ) from exc
        raise FredError(
            "model_unavailable",
            f"FRED unexpected HTTP {exc.code}: {body_text[:200]}",
        ) from exc
    except urllib.error.URLError as exc:
        raise FredError(
            "network_error",
            f"FRED network error: {exc.reason}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise FredError(
            "model_unavailable",
            f"FRED returned non-JSON response: {exc}",
        ) from exc
    except TimeoutError as exc:
        raise FredError(
            "network_error",
            f"FRED request timed out after {timeout}s",
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_series(query: SeriesQuery, *,
                 cache_dir: str = DEFAULT_CACHE_DIR,
                 cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
                 fetch_metadata: bool = True) -> SeriesData:
    """Fetch a FRED series by its ID and parameters.

    Returns a SeriesData with observations and (optionally) metadata.
    Reads from cache when fresh; on cache miss, fetches from FRED and
    writes the result to cache.

    Raises FredError on any failure with a taxonomy-coded ``code``
    attribute for upstream routing.
    """
    if not query.series_id or not isinstance(query.series_id, str):
        raise FredError("model_unavailable",
                        "fetch_series requires a non-empty series_id string")

    # Cache check
    cached = _read_cache(query, cache_dir, cache_ttl_seconds)
    if cached is not None:
        return cached

    api_key = _get_api_key()
    if not api_key:
        raise FredError(
            "model_unavailable",
            "No FRED API key configured. Set $FRED_API_KEY or store via "
            "keyring service='ora', username='fred-api-key'. Free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html",
            series_id=query.series_id,
        )

    # Build observations URL
    obs_params = {
        "series_id": query.series_id,
        "api_key": api_key,
        "file_type": "json",
        "limit": str(query.limit),
    }
    if query.observation_start:
        obs_params["observation_start"] = query.observation_start
    if query.observation_end:
        obs_params["observation_end"] = query.observation_end
    if query.frequency:
        obs_params["frequency"] = query.frequency
        obs_params["aggregation_method"] = query.aggregation_method
    if query.units:
        obs_params["units"] = query.units

    obs_url = f"{FRED_BASE_URL}/series/observations?{urllib.parse.urlencode(obs_params)}"

    try:
        obs_payload = _http_get_json(obs_url)
    except FredError as exc:
        # Annotate with series_id for upstream context
        exc.series_id = query.series_id
        raise

    raw_observations = obs_payload.get("observations", [])
    observations = [
        Observation(
            date=o.get("date", ""),
            value=_parse_value(o.get("value", ".")),
        )
        for o in raw_observations
    ]

    # Filter out observations with no date (defensive)
    observations = [o for o in observations if o.date]

    if not observations:
        raise FredError(
            "data_unavailable",
            f"FRED returned no observations for series {query.series_id} "
            f"in the requested range",
            series_id=query.series_id,
        )

    # Optional metadata fetch
    metadata = None
    if fetch_metadata:
        metadata = _fetch_metadata(query.series_id, api_key)

    data = SeriesData(
        series_id=query.series_id,
        observations=observations,
        metadata=metadata,
        retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        cache_hit=False,
        query=query,
    )
    _write_cache(data, cache_dir)
    return data


def _fetch_metadata(series_id: str, api_key: str) -> SeriesMetadata | None:
    """Fetch series metadata from /fred/series. Returns None on any
    failure — metadata is informational, not load-bearing."""
    try:
        meta_url = f"{FRED_BASE_URL}/series?series_id={series_id}&api_key={api_key}&file_type=json"
        payload = _http_get_json(meta_url)
        seriess = payload.get("seriess", [])
        if not seriess:
            return None
        s = seriess[0]
        return SeriesMetadata(
            id=s.get("id", series_id),
            title=s.get("title", ""),
            units=s.get("units", ""),
            units_short=s.get("units_short", ""),
            frequency=s.get("frequency", ""),
            frequency_short=s.get("frequency_short", ""),
            seasonal_adjustment=s.get("seasonal_adjustment", ""),
            last_updated=s.get("last_updated", ""),
            notes=s.get("notes", ""),
        )
    except Exception:
        return None


def _parse_value(raw: Any) -> float | None:
    """Parse a FRED observation value. FRED uses '.' as the missing-
    value marker. Returns None for missing values; float for valid
    numbers."""
    if raw is None or raw == "." or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Convenience: standard MSI source-attribution string
# ---------------------------------------------------------------------------

def attribution_line(data: SeriesData) -> str:
    """Build the standard MSI source-attribution string for a chart.

    Format: ``"Source: FRED, series GDPC1 (Real Gross Domestic Product),
    retrieved 2026-05-13."``
    """
    series_id = data.series_id
    title_part = f" ({data.metadata.title})" if data.metadata and data.metadata.title else ""
    retrieved = data.retrieved_at[:10] if data.retrieved_at else "today"
    return f"Source: FRED, series {series_id}{title_part}, retrieved {retrieved}."


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: fred_api.py <SERIES_ID> [start_date] [end_date]")
        print("Example: fred_api.py GDPC1 2020-01-01")
        sys.exit(1)

    series_id = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else None
    end = sys.argv[3] if len(sys.argv) > 3 else None

    query = SeriesQuery(
        series_id=series_id,
        observation_start=start,
        observation_end=end,
    )

    try:
        data = fetch_series(query)
        print(f"Series: {data.series_id}")
        if data.metadata:
            print(f"  Title: {data.metadata.title}")
            print(f"  Units: {data.metadata.units}")
            print(f"  Frequency: {data.metadata.frequency}")
            print(f"  Last updated: {data.metadata.last_updated}")
        print(f"Observations: {len(data.observations)}")
        if data.observations:
            print(f"  First: {data.observations[0].date} = {data.observations[0].value}")
            print(f"  Last:  {data.observations[-1].date} = {data.observations[-1].value}")
        print(f"Cache hit: {data.cache_hit}")
        print(f"\n{attribution_line(data)}")
    except FredError as exc:
        print(f"ERROR [{exc.code}]: {exc.message}")
        sys.exit(1)
