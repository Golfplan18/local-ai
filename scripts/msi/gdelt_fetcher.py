#!/usr/bin/env python3
"""GDELT 2.0 historical fetcher for the MSI smoke-test pipeline.

Fetches the 96 fifteen-minute Event and GKG (Global Knowledge Graph) files
that GDELT 2.0 publishes per day, parses them into structured records,
and caches downloaded zips to avoid re-fetching.

Module API:
    fetch_gdelt_for_date(date_str: str) -> dict
        Returns {"events": [...], "gkg": [...], "missing_intervals": [...]}.

CLI:
    python3 gdelt_fetcher.py YYYY-MM-DD
"""

from __future__ import annotations

import csv
import io
import json
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

# GKG records carry very long Themes / Locations / Persons fields. Python csv
# defaults to a 128 KB field cap; some GDELT rows blow past that.
csv.field_size_limit(sys.maxsize)

GDELT_BASE = "http://data.gdeltproject.org/gdeltv2"
USER_AGENT = (
    "MainStreetIndependent/1.0 "
    "(+https://mainstreetindependent.com/about; "
    "contact@mainstreetindependent.com)"
)
CACHE_DIR = Path.home() / "ora" / "scripts" / "msi" / "cache" / "gdelt"
INTER_REQUEST_SLEEP_SEC = 0.2
RETRY_BACKOFF_SEC = (1, 3, 9)
REQUEST_TIMEOUT_SEC = 30

EVENT_COLUMNS = [
    "GLOBALEVENTID", "SQLDATE", "MonthYear", "Year", "FractionDate",
    "Actor1Code", "Actor1Name", "Actor1CountryCode", "Actor1KnownGroupCode",
    "Actor1EthnicCode", "Actor1Religion1Code", "Actor1Religion2Code",
    "Actor1Type1Code", "Actor1Type2Code", "Actor1Type3Code",
    "Actor2Code", "Actor2Name", "Actor2CountryCode", "Actor2KnownGroupCode",
    "Actor2EthnicCode", "Actor2Religion1Code", "Actor2Religion2Code",
    "Actor2Type1Code", "Actor2Type2Code", "Actor2Type3Code",
    "IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode",
    "QuadClass", "GoldsteinScale",
    "NumMentions", "NumSources", "NumArticles", "AvgTone",
    "Actor1Geo_Type", "Actor1Geo_FullName", "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code", "Actor1Geo_ADM2Code",
    "Actor1Geo_Lat", "Actor1Geo_Long", "Actor1Geo_FeatureID",
    "Actor2Geo_Type", "Actor2Geo_FullName", "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code", "Actor2Geo_ADM2Code",
    "Actor2Geo_Lat", "Actor2Geo_Long", "Actor2Geo_FeatureID",
    "ActionGeo_Type", "ActionGeo_FullName", "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code", "ActionGeo_ADM2Code",
    "ActionGeo_Lat", "ActionGeo_Long", "ActionGeo_FeatureID",
    "DATEADDED", "SOURCEURL",
]

GKG_COLUMNS = [
    "GKGRECORDID", "DATE", "SourceCollectionIdentifier", "SourceCommonName",
    "DocumentIdentifier", "Counts", "V2Counts", "Themes", "V2Themes",
    "Locations", "V2Locations", "Persons", "V2Persons",
    "Organizations", "V2Organizations", "V2Tone", "Dates", "GCAM",
    "SharingImage", "RelatedImages", "SocialImageEmbeds",
    "SocialVideoEmbeds", "Quotations", "AllNames", "Amounts",
    "TranslationInfo", "Extras",
]


def enumerate_intervals(date_str: str) -> list[str]:
    """Return the 96 GDELT 2.0 fifteen-minute timestamps for the given date.

    Args:
        date_str: ISO date string YYYY-MM-DD.

    Returns:
        List of timestamps in GDELT format YYYYMMDDHHMMSS.
    """
    base = datetime.strptime(date_str, "%Y-%m-%d")
    return [
        (base + timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
        for i in range(96)
    ]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_zip(
    url: str,
    cache_path: Path,
    session: requests.Session,
) -> tuple[bytes | None, bool]:
    """Download a GDELT zip with cache + retry/backoff.

    Returns:
        (bytes_or_none, was_cache_hit). bytes_or_none is None on 404.
    """
    if cache_path.exists():
        return cache_path.read_bytes(), True

    last_error = None
    for attempt, backoff in enumerate([0, *RETRY_BACKOFF_SEC]):
        if backoff:
            time.sleep(backoff)
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
            if resp.status_code == 404:
                return None, False
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            resp.raise_for_status()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(resp.content)
            return resp.content, False
        except requests.RequestException as e:
            last_error = str(e)
            continue
    raise RuntimeError(f"Failed to fetch {url} after retries: {last_error}")


def _parse_csv(raw_zip: bytes, columns: list[str]) -> list[dict]:
    """Unzip a single-CSV GDELT archive and parse with the given column names."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        names = zf.namelist()
        if not names:
            return []
        with zf.open(names[0]) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter="\t")
            return [dict(zip(columns, row)) for row in reader if row]


def parse_events_csv(raw_zip: bytes) -> list[dict]:
    return _parse_csv(raw_zip, EVENT_COLUMNS)


def parse_gkg_csv(raw_zip: bytes) -> list[dict]:
    return _parse_csv(raw_zip, GKG_COLUMNS)


def fetch_gdelt_for_date(
    date_str: str,
    *,
    include_events: bool = True,
    include_gkg: bool = True,
    progress: bool = True,
) -> dict:
    """Fetch and parse all GDELT 2.0 files for one calendar date.

    Args:
        date_str: ISO date YYYY-MM-DD.
        include_events: download and parse the .export.CSV.zip event files.
        include_gkg: download and parse the .gkg.csv.zip Knowledge Graph files.
        progress: print a one-line progress indicator to stderr.

    Returns:
        {
            "date": <date_str>,
            "events": [<dict>, ...],         # all events for the day
            "gkg": [<dict>, ...],            # all GKG records for the day
            "missing_intervals": [<ts>, ...] # 15-min timestamps with no file
        }
    """
    intervals = enumerate_intervals(date_str)
    cache_root = CACHE_DIR / date_str
    cache_root.mkdir(parents=True, exist_ok=True)
    sess = _session()

    events: list[dict] = []
    gkg: list[dict] = []
    missing: list[str] = []

    total_steps = len(intervals) * (int(include_events) + int(include_gkg))
    step = 0

    for ts in intervals:
        interval_missing = False

        if include_events:
            url = f"{GDELT_BASE}/{ts}.export.CSV.zip"
            cache = cache_root / f"{ts}.export.CSV.zip"
            raw, was_cached = fetch_zip(url, cache, sess)
            if not was_cached:
                time.sleep(INTER_REQUEST_SLEEP_SEC)
            step += 1
            if raw is None:
                interval_missing = True
            else:
                events.extend(parse_events_csv(raw))
            if progress:
                _emit_progress(step, total_steps, ts, "events")

        if include_gkg:
            url = f"{GDELT_BASE}/{ts}.gkg.csv.zip"
            cache = cache_root / f"{ts}.gkg.csv.zip"
            raw, was_cached = fetch_zip(url, cache, sess)
            if not was_cached:
                time.sleep(INTER_REQUEST_SLEEP_SEC)
            step += 1
            if raw is None:
                interval_missing = True
            else:
                gkg.extend(parse_gkg_csv(raw))
            if progress:
                _emit_progress(step, total_steps, ts, "gkg")

        if interval_missing:
            missing.append(ts)

    if progress:
        sys.stderr.write("\n")

    return {
        "date": date_str,
        "events": events,
        "gkg": gkg,
        "missing_intervals": missing,
    }


def _emit_progress(step: int, total: int, ts: str, kind: str) -> None:
    pct = (step / total) * 100 if total else 0
    sys.stderr.write(f"\rgdelt {ts} {kind:6s}  [{step:3d}/{total}]  {pct:5.1f}%   ")
    sys.stderr.flush()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: gdelt_fetcher.py YYYY-MM-DD\n")
        return 2
    date_str = argv[1]
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        sys.stderr.write(f"invalid date {date_str!r}; expected YYYY-MM-DD\n")
        return 2

    result = fetch_gdelt_for_date(date_str)

    summary = {
        "date": result["date"],
        "event_count": len(result["events"]),
        "gkg_count": len(result["gkg"]),
        "missing_interval_count": len(result["missing_intervals"]),
        "missing_intervals_sample": result["missing_intervals"][:5],
        "cache_dir": str(CACHE_DIR / date_str),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
