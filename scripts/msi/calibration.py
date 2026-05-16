#!/usr/bin/env python3
"""MSI cluster construction + filter-cascade calibration analyzer.

Loads N cached days of GDELT events + GKG records, joins them into per-article
records, clusters articles into stories, and runs a tunable filter cascade
reporting how many stories survive each stage. Used to calibrate the
newsworthiness pipeline before committing to the smoke test.

CLI:
    python3 calibration.py 2026-03-09 2026-03-10 ... 2026-03-15

The default parameters are an opinionated first-pass calibration. Override
via CLI args (see --help) or by editing CalibrationParams.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from gdelt_fetcher import fetch_gdelt_for_date

# ----------------------------------------------------------------------------
# Parameter object
# ----------------------------------------------------------------------------

@dataclass
class CalibrationParams:
    # Stage A — National-importance heuristic
    require_us_in_event_geo: bool = True
    require_us_in_gkg_locations: bool = False
    include_intl_with_us_actor: bool = True

    # Stage B — Source verification
    min_distinct_outlets: int = 2
    require_national_tier_outlet: bool = True
    # When > 0, also require this many distinct outlets from the
    # national_tier_outlet_set (i.e. cluster must hit N approved free
    # services). Used by MSI to enforce the publisher's "5 free
    # services" corroboration requirement; any 5 from the approved
    # list qualify (different per story is fine). Distinct from
    # min_distinct_outlets (which counts ALL outlets including
    # long-tail aggregators).
    min_distinct_national_outlets: int = 0
    national_tier_outlet_set: tuple[str, ...] = (
        "nytimes.com", "washingtonpost.com", "wsj.com", "apnews.com",
        "reuters.com", "bloomberg.com", "politico.com", "thehill.com",
        "axios.com", "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com",
        "usatoday.com", "npr.org", "pbs.org", "theatlantic.com",
        "newyorker.com", "propublica.org", "motherjones.com",
        "reason.com", "nationalreview.com", "washingtonexaminer.com",
        "msnbc.com", "foxnews.com", "vox.com", "slate.com",
    )

    # Stage C — Newsworthiness signals (GDELT-derived)
    min_total_num_mentions: int = 10
    min_distinct_sources_total: int = 3
    min_abs_goldstein: float = 1.0

    # Stage D — Theme substantiveness
    require_substantive_theme: bool = True
    nonsubstantive_themes_dominant_threshold: float = 0.7  # if 70%+ themes are weather/sports/celeb, drop

    # Stage E — Diversity cap
    max_pct_per_top_entity: float = 0.25

    # Stage F — Final cap (None = no cap)
    max_articles_per_day: int | None = None


# ----------------------------------------------------------------------------
# Loading + joining
# ----------------------------------------------------------------------------

def load_day(date_str: str) -> dict:
    """Load one cached day; trivial wrapper around fetch_gdelt_for_date."""
    return fetch_gdelt_for_date(date_str, progress=False)


@dataclass
class Article:
    """One article = one URL = one GKG record + 0..N events from that URL."""
    url: str
    source_domain: str
    source_common_name: str
    themes: list[str] = field(default_factory=list)
    persons: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    locations_country_codes: set[str] = field(default_factory=set)
    tone_polarity: float = 0.0
    word_count: int = 0
    events: list[dict] = field(default_factory=list)
    date: str = ""


def _parse_semicolon_pairs(s: str) -> list[str]:
    """Parse 'Name,offset;Name,offset;...' format into [Name, ...]."""
    if not s:
        return []
    out = []
    for chunk in s.split(";"):
        if not chunk:
            continue
        name = chunk.rsplit(",", 1)[0].strip()
        if name:
            out.append(name)
    return out


def _parse_v2_locations_country_codes(s: str) -> set[str]:
    """Pull 2-letter country codes (FIPS 10-4) from V2Locations field.

    Format per item: type#name#countrycode#adm1code#adm2code#lat#lon#featureid#charoffset
    """
    if not s:
        return set()
    codes = set()
    for chunk in s.split(";"):
        parts = chunk.split("#")
        if len(parts) >= 3 and parts[2]:
            codes.add(parts[2])
    return codes


def _parse_tone_polarity(s: str) -> float:
    """Pull polarity (the third comma-separated value) from V2Tone field.

    Format: pos_score,neg_score,polarity,activity_ref,group_ref,wordcount,grouped
    """
    if not s:
        return 0.0
    parts = s.split(",")
    try:
        return float(parts[2]) if len(parts) >= 3 else 0.0
    except ValueError:
        return 0.0


def _parse_word_count(s: str) -> int:
    if not s:
        return 0
    parts = s.split(",")
    try:
        return int(float(parts[5])) if len(parts) >= 6 else 0
    except ValueError:
        return 0


def _domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def join_events_to_gkg(day: dict) -> dict[str, Article]:
    """Build per-article records by joining events to GKG on URL."""
    articles: dict[str, Article] = {}
    date = day["date"]

    # Index GKG by DocumentIdentifier (URL)
    for g in day["gkg"]:
        url = g.get("DocumentIdentifier", "")
        if not url:
            continue
        articles[url] = Article(
            url=url,
            source_domain=_domain_of(url),
            source_common_name=g.get("SourceCommonName", ""),
            themes=[t.strip() for t in g.get("Themes", "").split(";") if t.strip()],
            persons=_parse_semicolon_pairs(g.get("V2Persons", "")),
            organizations=_parse_semicolon_pairs(g.get("V2Organizations", "")),
            locations_country_codes=_parse_v2_locations_country_codes(g.get("V2Locations", "")),
            tone_polarity=_parse_tone_polarity(g.get("V2Tone", "")),
            word_count=_parse_word_count(g.get("V2Tone", "")),
            date=date,
        )

    # Attach events
    orphan_events = 0
    for e in day["events"]:
        url = e.get("SOURCEURL", "")
        if not url:
            continue
        if url in articles:
            articles[url].events.append(e)
        else:
            orphan_events += 1

    return articles


# ----------------------------------------------------------------------------
# Story clustering — group articles about the same story
# ----------------------------------------------------------------------------

# Generic anchors — entities that should not be the primary cluster key.
# Major US cities, all 50 states, common country names, and generic political/civic
# terms get mis-extracted by GDELT's NER as persons or surface as orgs but make
# poor cluster anchors (they absorb unrelated stories that happen to share the
# geography). When the top person is on this list, fall through to the next one.
GENERIC_ANCHOR_BLOCKLIST: frozenset[str] = frozenset(
    s.lower() for s in (
        # US cities (top ~50)
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
        "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
        "Fort Worth", "Columbus", "Charlotte", "Indianapolis", "San Francisco",
        "Seattle", "Denver", "Washington", "Boston", "El Paso", "Nashville",
        "Detroit", "Oklahoma City", "Portland", "Las Vegas", "Memphis", "Louisville",
        "Baltimore", "Milwaukee", "Albuquerque", "Tucson", "Fresno", "Sacramento",
        "Mesa", "Kansas City", "Atlanta", "Long Beach", "Colorado Springs", "Raleigh",
        "Miami", "Virginia Beach", "Omaha", "Oakland", "Minneapolis", "Tulsa",
        "Arlington", "Tampa", "New Orleans", "Wichita", "Cleveland", "Bakersfield",
        "Aurora", "Anaheim", "Honolulu", "Santa Ana", "Riverside", "Corpus Christi",
        "Lexington", "Stockton", "Henderson", "Saint Paul", "St. Louis", "Cincinnati",
        "Pittsburgh", "Greensboro", "Anchorage", "Plano", "Lincoln", "Orlando",
        "Irvine", "Newark", "Toledo", "Durham", "Chula Vista", "Fort Wayne",
        "Jersey City", "St. Petersburg", "Laredo", "Madison", "Chandler", "Buffalo",
        # US states
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
        "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
        "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
        "New Mexico", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee",
        "Texas", "Utah", "Vermont", "Virginia", "West Virginia", "Wisconsin", "Wyoming",
        # Countries (most-frequent generic references)
        "United States", "U.S.", "USA", "America", "American", "China", "Russia",
        "Iran", "Israel", "Mexico", "Canada", "United Kingdom", "Britain", "England",
        "France", "Germany", "Japan", "India", "Brazil", "Australia", "South Korea",
        "North Korea", "Ukraine", "Saudi Arabia", "Egypt", "Turkey", "Italy", "Spain",
        # Generic political / civic terms
        "Capitol Hill", "Wall Street", "Main Street", "Silicon Valley",
        "Hollywood", "Beltway",
    )
)


# First-name diminutives -> canonical given name. Applied during cluster-key
# canonicalization so "Mike Bouchard" and "Michael Bouchard" merge.
NAME_DIMINUTIVES: dict[str, str] = {
    "alex": "alexander", "ali": "alison", "andy": "andrew", "anthony": "anthony",
    "barb": "barbara", "ben": "benjamin", "bernie": "bernard", "betty": "elizabeth",
    "bill": "william", "billy": "william", "bob": "robert", "bobby": "robert",
    "bruce": "bruce", "cathy": "catherine", "charlie": "charles", "chris": "christopher",
    "chuck": "charles", "dan": "daniel", "dave": "david", "deb": "deborah",
    "debbie": "deborah", "dennis": "dennis", "dick": "richard", "don": "donald",
    "doug": "douglas", "ed": "edward", "eddie": "edward", "fred": "frederick",
    "freddy": "frederick", "frank": "francis", "gabe": "gabriel", "gary": "gary",
    "george": "george", "greg": "gregory", "hank": "henry", "harry": "harold",
    "jack": "john", "jake": "jacob", "jan": "janet", "jeff": "jeffrey",
    "jen": "jennifer", "jenny": "jennifer", "jim": "james", "jimmy": "james",
    "joe": "joseph", "joey": "joseph", "jon": "jonathan", "josh": "joshua",
    "judy": "judith", "julie": "julia", "kate": "katherine", "kathy": "katherine",
    "katie": "katherine", "ken": "kenneth", "kenny": "kenneth", "larry": "lawrence",
    "len": "leonard", "liz": "elizabeth", "lou": "louis", "marge": "margaret",
    "marty": "martin", "matt": "matthew", "max": "maxwell", "meg": "margaret",
    "mike": "michael", "mickey": "michael", "nate": "nathan", "nick": "nicholas",
    "pam": "pamela", "pat": "patrick", "patty": "patricia", "paul": "paul",
    "pete": "peter", "phil": "philip", "ralph": "ralph", "ray": "raymond",
    "rich": "richard", "rick": "richard", "rob": "robert", "ron": "ronald",
    "ronnie": "ronald", "sam": "samuel", "sandy": "sandra", "scott": "scott",
    "sid": "sidney", "stan": "stanley", "steve": "steven", "sue": "susan",
    "ted": "edward", "teddy": "edward", "terry": "terence", "theo": "theodore",
    "tim": "timothy", "tom": "thomas", "tommy": "thomas", "tony": "anthony",
    "vic": "victor", "vince": "vincent", "walt": "walter", "will": "william",
    "willy": "william",
}

NAME_SUFFIXES: frozenset[str] = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


def canonicalize_person_name(name: str) -> str:
    """Return canonical clustering key for a person name.

    Steps:
      1. Lowercase, strip punctuation except apostrophes.
      2. Drop middle initials and middle names (keep first + last + optional suffix).
      3. Expand diminutives in the first name (Mike -> Michael).

    Example:
      "Mike Bouchard"            -> "michael bouchard"
      "Michael R. Bouchard"      -> "michael bouchard"
      "Michael R Bouchard"       -> "michael bouchard"
      "Robert F. Kennedy Jr."    -> "robert kennedy jr"
      "Joe Biden"                -> "joseph biden"
    """
    if not name:
        return ""
    cleaned = re.sub(r"[^\w\s'-]", " ", name.lower())
    parts = [p for p in cleaned.split() if p]
    if not parts:
        return ""

    # Detect suffix
    suffix = ""
    if parts[-1] in NAME_SUFFIXES:
        suffix = parts[-1]
        parts = parts[:-1]

    if len(parts) == 0:
        return ""
    if len(parts) == 1:
        # Single-token entity — just expand if known diminutive
        first = NAME_DIMINUTIVES.get(parts[0], parts[0])
        return first if not suffix else f"{first} {suffix}"

    first = parts[0]
    last = parts[-1]
    first = NAME_DIMINUTIVES.get(first, first)

    if suffix:
        return f"{first} {last} {suffix}"
    return f"{first} {last}"


# Themes that suggest sports / celebrity / weather / lifestyle — non-substantive
NONSUBSTANTIVE_THEME_PREFIXES = (
    "SOC_SPORTS", "SOC_POPCULTURE", "SOC_GENERALCRIME", "ENT_",
    "WB_2433_ENVIRONMENTAL_AND_NATURAL_RESOURCES_MANAGEMENT_NATURAL_DISASTERS",
    "NATURAL_DISASTER_WEATHER", "WEATHER", "CELEBRITY",
    "TAX_FNCACT_ATHLETE", "TAX_FNCACT_ACTOR", "TAX_FNCACT_SINGER",
    "TAX_FNCACT_FOOTBALLER", "TAX_FNCACT_BASKETBALL", "TAX_SPORT",
)

SUBSTANTIVE_THEME_PREFIXES = (
    "GOV_", "USPEC_POLITICS", "ELECTION", "POLITICS_",
    "EPU_", "ECON_", "TAX_ECONOMIC",
    "MILITARY_", "SECURITY_SERVICES", "ARMEDCONFLICT", "TERROR",
    "CRIME_CARTELS", "ORGANIZED_CRIME", "BLACK_MARKET",
    "WB_649_AGRICULTURE", "WB_1462_HUMAN_RIGHTS",
    "ENV_", "MANMADE_DISASTER", "INFRASTRUCTURE_BAD_",
    "HEALTH_PANDEMIC", "EPIDEMIC", "DISEASE",
    "REL_", "RELIGION_",
    "IMMIGRATION", "REFUGEES", "ASYLUM",
    "EDUCATION", "LABOR", "UNION",
    "SUPREME_COURT", "JUDICIAL_PROCESS", "TRIAL", "INDICTMENT",
    "PROTEST", "STRIKE",
)


@dataclass
class Story:
    """Cluster of articles about the same news story."""
    cluster_id: str
    primary_entity: str      # the entity used to cluster these
    articles: list[Article] = field(default_factory=list)

    # Aggregated fields populated post-construction
    distinct_outlets: set[str] = field(default_factory=set)
    distinct_domains: set[str] = field(default_factory=set)
    total_num_mentions: int = 0
    total_num_sources: int = 0
    max_abs_goldstein: float = 0.0
    avg_tone_polarity: float = 0.0
    has_us_in_event_geo: bool = False
    has_us_in_gkg_locations: bool = False
    aggregated_themes: list[str] = field(default_factory=list)
    aggregated_persons: list[str] = field(default_factory=list)
    aggregated_orgs: list[str] = field(default_factory=list)
    has_national_tier_outlet: bool = False


def _pick_anchor_entity(article: Article) -> tuple[str, str]:
    """Pick the article's clustering anchor.

    Walks the persons list first, then orgs, skipping any entity on the generic
    blocklist (cities/states/countries that GDELT mis-extracts as persons).
    Returns (canonical_key, display_name) — canonical_key is normalized for
    clustering; display_name preserves the original capitalization for reporting.
    """
    for p in article.persons:
        if p.lower() in GENERIC_ANCHOR_BLOCKLIST:
            continue
        canon = canonicalize_person_name(p)
        if canon:
            return canon, p
    for o in article.organizations:
        if o.lower() in GENERIC_ANCHOR_BLOCKLIST:
            continue
        # Orgs aren't diminutive-expanded, just lowercased and trimmed.
        canon = " ".join(o.lower().split())
        if canon:
            return canon, o
    return "", ""


def cluster_into_stories(
    articles: dict[str, Article],
    *,
    min_persons_for_clustering: int = 1,
) -> list[Story]:
    """Cluster articles into stories via shared top entity.

    Each article's anchor is its top-mentioned person (or fallback org), skipping
    entries on the generic-anchor blocklist (city/state/country names) and
    canonicalizing person names so "Mike Bouchard" and "Michael Bouchard" merge.
    Fast O(N) approximation good enough for calibration; production replaces this
    with proper entity resolution + LSH.
    """
    by_canonical_anchor: dict[str, tuple[str, list[Article]]] = {}
    for a in articles.values():
        canon, display = _pick_anchor_entity(a)
        if not canon:
            continue
        if canon not in by_canonical_anchor:
            by_canonical_anchor[canon] = (display, [])
        by_canonical_anchor[canon][1].append(a)

    stories: list[Story] = []
    for canon, (display, group) in by_canonical_anchor.items():
        if len(group) < min_persons_for_clustering:
            continue
        story = Story(
            cluster_id=f"{canon}::{group[0].date}",
            primary_entity=display,
        )
        for a in group:
            story.articles.append(a)
        _aggregate_story(story)
        stories.append(story)

    return stories


def _aggregate_story(story: Story) -> None:
    domains = set()
    outlets = set()
    themes_counter: Counter[str] = Counter()
    persons_counter: Counter[str] = Counter()
    orgs_counter: Counter[str] = Counter()
    total_mentions = 0
    total_sources = 0
    max_abs_g = 0.0
    tones = []
    has_us_event = False
    has_us_gkg = False

    for a in story.articles:
        domains.add(a.source_domain)
        outlets.add(a.source_common_name)
        themes_counter.update(a.themes)
        persons_counter.update(a.persons)
        orgs_counter.update(a.organizations)
        if "US" in a.locations_country_codes:
            has_us_gkg = True
        for e in a.events:
            try:
                total_mentions += int(e.get("NumMentions") or 0)
                total_sources += int(e.get("NumSources") or 0)
                g = float(e.get("GoldsteinScale") or 0.0)
                if abs(g) > max_abs_g:
                    max_abs_g = abs(g)
            except ValueError:
                pass
            for geo_field in ("Actor1Geo_CountryCode", "Actor2Geo_CountryCode", "ActionGeo_CountryCode"):
                if e.get(geo_field) == "US":
                    has_us_event = True
                    break
        tones.append(a.tone_polarity)

    story.distinct_outlets = outlets
    story.distinct_domains = domains
    story.total_num_mentions = total_mentions
    story.total_num_sources = total_sources
    story.max_abs_goldstein = max_abs_g
    story.avg_tone_polarity = sum(tones) / len(tones) if tones else 0.0
    story.has_us_in_event_geo = has_us_event
    story.has_us_in_gkg_locations = has_us_gkg
    story.aggregated_themes = [t for t, _ in themes_counter.most_common(20)]
    story.aggregated_persons = [p for p, _ in persons_counter.most_common(10)]
    story.aggregated_orgs = [o for o, _ in orgs_counter.most_common(10)]


# ----------------------------------------------------------------------------
# Filter stages — each takes stories + params, returns (passed, dropped)
# ----------------------------------------------------------------------------

@dataclass
class StageResult:
    name: str
    in_count: int
    out_count: int
    dropped: int
    sample_kept: list[str] = field(default_factory=list)
    sample_dropped: list[str] = field(default_factory=list)


def _story_label(s: Story) -> str:
    top_persons = "/".join(s.aggregated_persons[:2]) or s.primary_entity
    top_themes = "/".join(s.aggregated_themes[:2])
    return f"[{len(s.articles)}art {len(s.distinct_outlets)}outl] {top_persons} :: {top_themes}"


def stage_a_national_importance(
    stories: list[Story], params: CalibrationParams
) -> tuple[list[Story], StageResult]:
    kept = []
    dropped = []
    for s in stories:
        ok = True
        if params.require_us_in_event_geo and not s.has_us_in_event_geo:
            ok = False
        if params.require_us_in_gkg_locations and not s.has_us_in_gkg_locations:
            ok = False
        (kept if ok else dropped).append(s)
    return kept, StageResult(
        name="A. National importance",
        in_count=len(stories),
        out_count=len(kept),
        dropped=len(dropped),
        sample_kept=[_story_label(s) for s in kept[:5]],
        sample_dropped=[_story_label(s) for s in dropped[:5]],
    )


def stage_b_source_verification(
    stories: list[Story], params: CalibrationParams
) -> tuple[list[Story], StageResult]:
    national_set = set(params.national_tier_outlet_set)
    kept = []
    dropped = []
    for s in stories:
        national_matches = s.distinct_domains & national_set
        s.has_national_tier_outlet = bool(national_matches)
        ok = len(s.distinct_outlets) >= params.min_distinct_outlets
        if params.require_national_tier_outlet and not s.has_national_tier_outlet:
            ok = False
        if params.min_distinct_national_outlets > 0 and \
                len(national_matches) < params.min_distinct_national_outlets:
            ok = False
        (kept if ok else dropped).append(s)
    return kept, StageResult(
        name="B. Source verification",
        in_count=len(stories),
        out_count=len(kept),
        dropped=len(dropped),
        sample_kept=[_story_label(s) for s in kept[:5]],
        sample_dropped=[_story_label(s) for s in dropped[:5]],
    )


def stage_c_newsworthiness_signals(
    stories: list[Story], params: CalibrationParams
) -> tuple[list[Story], StageResult]:
    kept = []
    dropped = []
    for s in stories:
        ok = (
            s.total_num_mentions >= params.min_total_num_mentions
            and s.total_num_sources >= params.min_distinct_sources_total
            and s.max_abs_goldstein >= params.min_abs_goldstein
        )
        (kept if ok else dropped).append(s)
    return kept, StageResult(
        name="C. Newsworthiness signals (mentions/sources/Goldstein)",
        in_count=len(stories),
        out_count=len(kept),
        dropped=len(dropped),
        sample_kept=[_story_label(s) for s in kept[:5]],
        sample_dropped=[_story_label(s) for s in dropped[:5]],
    )


def _theme_substantiveness_ratio(themes: list[str]) -> float:
    """Return ratio of non-substantive themes."""
    if not themes:
        return 0.0
    nonsub = sum(
        1 for t in themes
        if any(t.startswith(p) for p in NONSUBSTANTIVE_THEME_PREFIXES)
    )
    return nonsub / len(themes)


def _has_substantive_theme(themes: list[str]) -> bool:
    return any(
        any(t.startswith(p) for p in SUBSTANTIVE_THEME_PREFIXES)
        for t in themes
    )


def stage_d_substantive_theme(
    stories: list[Story], params: CalibrationParams
) -> tuple[list[Story], StageResult]:
    if not params.require_substantive_theme:
        return stories, StageResult("D. Substantive theme (skipped)", len(stories), len(stories), 0)
    kept = []
    dropped = []
    for s in stories:
        nonsub_ratio = _theme_substantiveness_ratio(s.aggregated_themes)
        has_sub = _has_substantive_theme(s.aggregated_themes)
        ok = has_sub and nonsub_ratio < params.nonsubstantive_themes_dominant_threshold
        (kept if ok else dropped).append(s)
    return kept, StageResult(
        name="D. Substantive theme (politics/econ/policy/justice)",
        in_count=len(stories),
        out_count=len(kept),
        dropped=len(dropped),
        sample_kept=[_story_label(s) for s in kept[:5]],
        sample_dropped=[_story_label(s) for s in dropped[:5]],
    )


def stage_e_diversity_cap(
    stories: list[Story], params: CalibrationParams
) -> tuple[list[Story], StageResult]:
    """Sort stories by combined newsworthiness score; apply per-entity cap."""
    if not stories:
        return [], StageResult("E. Diversity cap", 0, 0, 0)

    sorted_stories = sorted(
        stories,
        key=lambda s: (
            s.total_num_mentions
            + 5 * s.max_abs_goldstein
            + len(s.distinct_outlets)
        ),
        reverse=True,
    )
    target_after = len(sorted_stories)  # diversity is a re-ordering + cap, not a hard cut yet
    cap_per_entity = max(1, int(target_after * params.max_pct_per_top_entity))
    seen: Counter[str] = Counter()
    kept = []
    dropped = []
    for s in sorted_stories:
        ent = s.primary_entity
        if seen[ent] >= cap_per_entity:
            dropped.append(s)
            continue
        kept.append(s)
        seen[ent] += 1
    return kept, StageResult(
        name=f"E. Diversity cap ({int(params.max_pct_per_top_entity*100)}%/entity)",
        in_count=len(stories),
        out_count=len(kept),
        dropped=len(dropped),
        sample_kept=[_story_label(s) for s in kept[:5]],
        sample_dropped=[_story_label(s) for s in dropped[:5]],
    )


def stage_f_final_cap(
    stories: list[Story], params: CalibrationParams
) -> tuple[list[Story], StageResult]:
    if params.max_articles_per_day is None:
        return stories, StageResult("F. Final cap (none)", len(stories), len(stories), 0)
    n = min(params.max_articles_per_day, len(stories))
    kept = stories[:n]
    dropped = stories[n:]
    return kept, StageResult(
        name=f"F. Final cap ({params.max_articles_per_day}/day)",
        in_count=len(stories),
        out_count=len(kept),
        dropped=len(dropped),
        sample_kept=[_story_label(s) for s in kept[:5]],
        sample_dropped=[_story_label(s) for s in dropped[:3]],
    )


# ----------------------------------------------------------------------------
# Cascade runner + reporting
# ----------------------------------------------------------------------------

@dataclass
class DayReport:
    date: str
    raw_event_count: int
    raw_gkg_count: int
    article_count: int
    initial_story_count: int
    stages: list[StageResult] = field(default_factory=list)
    final_count: int = 0


def run_cascade_for_day(date_str: str, params: CalibrationParams) -> DayReport:
    day = load_day(date_str)
    articles = join_events_to_gkg(day)
    stories = cluster_into_stories(articles)

    report = DayReport(
        date=date_str,
        raw_event_count=len(day["events"]),
        raw_gkg_count=len(day["gkg"]),
        article_count=len(articles),
        initial_story_count=len(stories),
    )

    current = stories
    for stage_fn in (
        stage_a_national_importance,
        stage_b_source_verification,
        stage_c_newsworthiness_signals,
        stage_d_substantive_theme,
        stage_e_diversity_cap,
        stage_f_final_cap,
    ):
        current, result = stage_fn(current, params)
        report.stages.append(result)

    report.final_count = len(current)
    return report


def format_report(report: DayReport, *, with_samples: bool = True) -> str:
    lines = [
        f"=== {report.date} ===",
        f"  raw events:    {report.raw_event_count:>10,}",
        f"  raw GKG:       {report.raw_gkg_count:>10,}",
        f"  articles:      {report.article_count:>10,} (after URL join)",
        f"  initial stories: {report.initial_story_count:>8,} (after entity clustering)",
        "",
    ]
    for st in report.stages:
        pct_kept = (st.out_count / st.in_count * 100) if st.in_count else 0.0
        lines.append(
            f"  {st.name:<58s}  {st.in_count:>7,}  ->  {st.out_count:>5,}  "
            f"({pct_kept:5.1f}% kept, -{st.dropped:,})"
        )
    lines.append("")
    lines.append(f"  FINAL: {report.final_count} stories")
    if with_samples and report.stages:
        last = report.stages[-1]
        if last.sample_kept:
            lines.append("  Sample kept:")
            for s in last.sample_kept:
                lines.append(f"    + {s}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def parse_cli_params(argv: list[str]) -> tuple[CalibrationParams, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+", help="Date(s) YYYY-MM-DD")
    parser.add_argument("--min-mentions", type=int)
    parser.add_argument("--min-sources", type=int)
    parser.add_argument("--min-outlets", type=int)
    parser.add_argument("--min-goldstein", type=float)
    parser.add_argument("--no-require-national-tier", action="store_true")
    parser.add_argument("--no-require-us-event-geo", action="store_true")
    parser.add_argument("--require-us-gkg-locations", action="store_true")
    parser.add_argument("--no-require-substantive-theme", action="store_true")
    parser.add_argument("--diversity-pct", type=float)
    parser.add_argument("--max-per-day", type=int)
    parser.add_argument("--no-samples", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text report")
    args = parser.parse_args(argv)

    p = CalibrationParams()
    if args.min_mentions is not None:
        p.min_total_num_mentions = args.min_mentions
    if args.min_sources is not None:
        p.min_distinct_sources_total = args.min_sources
    if args.min_outlets is not None:
        p.min_distinct_outlets = args.min_outlets
    if args.min_goldstein is not None:
        p.min_abs_goldstein = args.min_goldstein
    if args.no_require_national_tier:
        p.require_national_tier_outlet = False
    if args.no_require_us_event_geo:
        p.require_us_in_event_geo = False
    if args.require_us_gkg_locations:
        p.require_us_in_gkg_locations = True
    if args.no_require_substantive_theme:
        p.require_substantive_theme = False
    if args.diversity_pct is not None:
        p.max_pct_per_top_entity = args.diversity_pct
    if args.max_per_day is not None:
        p.max_articles_per_day = args.max_per_day

    return p, args.dates


def main(argv: list[str]) -> int:
    args = sys.argv[1:]
    if not args:
        sys.stderr.write("usage: calibration.py YYYY-MM-DD [YYYY-MM-DD ...]\n")
        return 2

    json_mode = "--json" in args
    no_samples = "--no-samples" in args

    params, dates = parse_cli_params(args)

    print("PARAMETERS:")
    for k, v in asdict(params).items():
        if k == "national_tier_outlet_set":
            print(f"  {k}: <{len(v)} outlets>")
        else:
            print(f"  {k}: {v}")
    print()

    reports = [run_cascade_for_day(d, params) for d in dates]

    for r in reports:
        if json_mode:
            print(json.dumps({
                "date": r.date,
                "raw_event_count": r.raw_event_count,
                "article_count": r.article_count,
                "initial_story_count": r.initial_story_count,
                "stages": [
                    {"name": s.name, "in": s.in_count, "out": s.out_count}
                    for s in r.stages
                ],
                "final_count": r.final_count,
            }))
        else:
            print(format_report(r, with_samples=not no_samples))
            print()

    if len(reports) > 1 and not json_mode:
        finals = [r.final_count for r in reports]
        weekday_finals = [r.final_count for r in reports if not _is_weekend(r.date)]
        weekend_finals = [r.final_count for r in reports if _is_weekend(r.date)]
        print("=== SUMMARY ===")
        print(f"  Total days:     {len(reports)}")
        print(f"  Avg final/day:  {sum(finals)/len(finals):.1f}")
        print(f"  Min final/day:  {min(finals)}")
        print(f"  Max final/day:  {max(finals)}")
        if weekday_finals:
            print(f"  Weekday avg:    {sum(weekday_finals)/len(weekday_finals):.1f}  (n={len(weekday_finals)})")
        if weekend_finals:
            print(f"  Weekend avg:    {sum(weekend_finals)/len(weekend_finals):.1f}  (n={len(weekend_finals)})")

    return 0


def _is_weekend(date_str: str) -> bool:
    from datetime import datetime
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5


if __name__ == "__main__":
    sys.exit(main(sys.argv))
