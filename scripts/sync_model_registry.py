#!/usr/bin/env python3
"""sync_model_registry — populate Ora's curated model registry.

Subcommands:

  sync     Pull OpenRouter / LiteLLM / Chatbot Arena, merge, write
           ``config/model-registry.json``. By default runs probes for
           any model whose vision capability could not be resolved
           from LiteLLM. Pass ``--no-probe`` to skip probing.

  probe    Run the empirical vision-capability probe against models
           in the registry. Default: only models where
           ``vision_capable`` is null. ``--revalidate`` re-probes
           models LiteLLM had already flagged true (sanity layer).

  audit    Print a summary: total models, coverage by source,
           probe verdicts, source disagreements.

The registry is the single source of truth for model capabilities at
runtime. Boot.py reads it via ``orchestrator/model_registry.py`` and
falls back to ``config/routing-config.json`` only when the registry
is missing or malformed.

Source-of-truth precedence per field:
  vision_capable      → empirical probe (when run) > LiteLLM explicit
                        true/false > OpenRouter ``architecture.input_modalities``
  intelligence_score  → Chatbot Arena ELO (authoritative)
  context_length      → OpenRouter (operational)
  pricing             → OpenRouter (operational)

No manual overrides. The registry is fully derived; if a value is
wrong, fix the source or the empirical probe. Per-field provenance is
preserved so any disagreement is traceable.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
REGISTRY_PATH = ORA_HOME / "config" / "model-registry.json"
DISCREPANCY_PATH = ORA_HOME / "data" / "model-registry-discrepancies.jsonl"
PROBE_ASSETS = ORA_HOME / "scripts" / "probe_assets"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
LITELLM_JSON_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
ARENA_CSV_URL = (
    "https://huggingface.co/datasets/mathewhe/chatbot-arena-elo/"
    "resolve/main/elo.csv"
)
AA_MODELS_URL = "https://artificialanalysis.ai/models"
AA_TEXT_TO_IMAGE_URL = "https://artificialanalysis.ai/image/leaderboard/text-to-image"
AA_IMAGE_EDITING_URL = "https://artificialanalysis.ai/image/leaderboard/editing"
AA_TEXT_TO_VIDEO_URL = "https://artificialanalysis.ai/video/leaderboard/text-to-video"
AA_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

REGISTRY_SCHEMA_VERSION = 1
ARENA_DIGITS = ("3", "7")


# ──────────────────────────────────────────────────────────────────────────
# Tiny HTTP fetch helpers (avoid dependency on `requests`)
# ──────────────────────────────────────────────────────────────────────────


def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ora-sync/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_openrouter_models() -> list[dict]:
    raw = _fetch(OPENROUTER_MODELS_URL)
    payload = json.loads(raw)
    return payload.get("data") or []


def fetch_litellm_models() -> dict:
    raw = _fetch(LITELLM_JSON_URL)
    data = json.loads(raw)
    # The top-level "sample_spec" key is a meta entry; skip it.
    return {k: v for k, v in data.items() if k != "sample_spec"}


def fetch_arena_rows() -> list[dict]:
    raw = _fetch(ARENA_CSV_URL)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    return rows


def _fetch_aa_html(url: str = AA_MODELS_URL) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": AA_USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_aa_models() -> list[dict]:
    """Scrape the artificialanalysis.ai /models page and extract its
    embedded model array.

    AA renders the page server-side with Next.js. The data we want is
    in the RSC payload: a series of ``self.__next_f.push([1, "..."])``
    calls whose concatenated escaped-string content carries a
    ``"defaultData":[ ... ]`` array of model entries with
    intelligence_index, modalities, pricing, latency fields, etc.

    No API key required — the page is publicly served. Cost per fetch:
    one HTTP GET (~8 MB) per sync. With the install-default once-per-day
    cadence (or model-selection-screen-triggered), per-instance load is
    trivial even at very large install counts.

    Schema is informally documented — if AA changes their RSC payload
    or moves the data into a separate API call, this function fails and
    AA enrichment goes silent. The registry's other sources (OpenRouter,
    LiteLLM, Chatbot Arena) remain unaffected.
    """
    raw_html = _fetch_aa_html().decode("utf-8", errors="ignore")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', raw_html)
    combined = ""
    for c in chunks:
        try:
            combined += c.encode().decode("unicode_escape")
        except UnicodeDecodeError:
            continue
    start = combined.find('"defaultData":[')
    if start < 0:
        return []
    arr_start = start + len('"defaultData":')
    close = _find_matching_bracket(combined, arr_start)
    if close < 0:
        return []
    try:
        return json.loads(combined[arr_start: close + 1])
    except json.JSONDecodeError:
        return []


def _aa_combined_payload(url: str) -> str:
    """Fetch an AA leaderboard page and return its concatenated
    Next.js RSC payload as a single unicode-unescaped string. Shared
    by the text-to-image, image-editing, and text-to-video readers
    below (and could be reused by ``fetch_aa_models`` in a future
    refactor)."""
    raw_html = _fetch_aa_html(url).decode("utf-8", errors="ignore")
    chunks = re.findall(
        r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', raw_html
    )
    combined = ""
    for c in chunks:
        try:
            combined += c.encode().decode("unicode_escape")
        except UnicodeDecodeError:
            continue
    return combined


def _extract_aa_leaderboard_rows(combined: str) -> list[dict]:
    """Walk every ``"values":{...}`` object in the merged payload and
    return the ones that look like leaderboard rows (have ``elo``,
    ``appearances``, and ``name``). Deduped by ``id``; sorted by
    ``rank`` ascending.

    The Elo-style leaderboards (text-to-image, image-editing,
    text-to-video, image-to-video) all use the same row shape:

        {
          "id": "<uuid>",
          "name": "<display name>",
          "url": "/image/model-families/...",
          "rank": 0,
          "elo": 1339.17,
          "appearances": 10032,
          "creator": {"id": "...", "name": "OpenAI", ...}
        }

    If AA changes the shape (key rename, removed elo, etc.), this
    function silently returns an empty list and the caller's
    enrichment goes blank — same fail-soft posture as
    ``fetch_aa_models``.
    """
    out: list[dict] = []
    needle = '"values":{'
    i = 0
    n = len(combined)
    while True:
        i = combined.find(needle, i)
        if i < 0:
            break
        start = i + len('"values":')  # position of opening "{"
        # Bracket-match the object, honoring nested objects + JSON strings.
        depth = 0
        j = start
        in_str = False
        esc = False
        while j < n:
            ch = combined[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(combined[start:j + 1])
                            if (isinstance(obj, dict)
                                    and "elo" in obj
                                    and "appearances" in obj
                                    and "name" in obj):
                                out.append(obj)
                        except json.JSONDecodeError:
                            pass
                        break
            j += 1
        i = j + 1

    # Dedupe by id (rows appear multiple times in the streamed payload).
    seen: set = set()
    unique: list[dict] = []
    for r in out:
        rid = r.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        unique.append(r)

    unique.sort(key=lambda r: r.get("rank", 99999))
    return unique


def fetch_aa_text_to_image() -> list[dict]:
    """Scrape AA's text-to-image arena leaderboard. Returns one dict
    per ranked image-generation model with id / name / creator /
    elo / rank / appearances / url. Non-fatal on failure (returns []).
    """
    return _extract_aa_leaderboard_rows(_aa_combined_payload(AA_TEXT_TO_IMAGE_URL))


def fetch_aa_image_editing() -> list[dict]:
    """Scrape AA's image-editing arena leaderboard. Returns one dict
    per ranked image-editing model. Same row shape as
    ``fetch_aa_text_to_image``. Non-fatal on failure (returns [])."""
    return _extract_aa_leaderboard_rows(_aa_combined_payload(AA_IMAGE_EDITING_URL))


def fetch_aa_text_to_video() -> list[dict]:
    """Scrape AA's text-to-video arena leaderboard. Returns one dict
    per ranked text-to-video model. Same row shape as
    ``fetch_aa_text_to_image``. Non-fatal on failure (returns [])."""
    return _extract_aa_leaderboard_rows(_aa_combined_payload(AA_TEXT_TO_VIDEO_URL))


def _find_matching_bracket(s: str, open_idx: int) -> int:
    """Return the index of the ``]`` that closes the array opened at
    ``open_idx``, honoring nested arrays and JSON strings."""
    depth = 0
    i = open_idx
    in_str = False
    esc = False
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


# ──────────────────────────────────────────────────────────────────────────
# AA API path (parallel to the scrape path above)
# ──────────────────────────────────────────────────────────────────────────
#
# AA's official REST API at https://artificialanalysis.ai/api/v2/ returns
# the same intelligence + leaderboard data the scrape extracts from the
# public pages. Trade-offs:
#
#   + Resilient to AA UI redesigns — the API is versioned.
#   + Documented schema; rate-limited to 1,000 requests/day on the free
#     tier (a sync uses 4 — one per endpoint — so essentially unbounded).
#   + Won't trip AA's automated-traffic detection at scale.
#   - Requires a key. Generate one at https://artificialanalysis.ai/ →
#     account → API keys; store via Settings → External APIs (which
#     writes to keyring under ``ora/aa-api-key``).
#   - A few fields the public page exposes aren't in the API response:
#     ``reasoning_model``, ``agentic_index``, ``model_family_slug``,
#     ``input_modality_image``, and the scrape's
#     ``end_to_end_response_time_metrics`` total time (only
#     time-to-first-token is exposed). None have a downstream consumer
#     at the time the API path landed. The previously-listed
#     ``is_open_weights`` and ``knowledge_cutoff_date`` are also missing
#     from the API but the producer side has been dropped registry-wide
#     (commits ca0268ae and d6a5855f) so they're no longer a gap.
#
# Functions below return the SAME shape ``fetch_aa_models()`` and
# ``fetch_aa_text_to_image()`` etc. return, so ``_project_aa_view``,
# ``build_aa_overlay``, and ``_build_media_entry`` need zero changes —
# the path choice is invisible to them.

AA_API_BASE_URL = "https://artificialanalysis.ai/api/v2/"
AA_API_LLMS_PATH = "data/llms/models"
AA_API_T2I_PATH = "data/media/text-to-image"
AA_API_EDIT_PATH = "data/media/image-editing"
AA_API_T2V_PATH = "data/media/text-to-video"


def _aa_api_get(path: str, api_key: str, timeout: int = 30) -> dict:
    """GET an AA API endpoint and parse the JSON envelope.

    AA wraps responses as ``{"status": 200, "data": [...]}``. Returns the
    full parsed envelope so callers can inspect status. Raises on HTTP /
    network error so callers can decide their own fallback policy.
    """
    url = AA_API_BASE_URL + path.lstrip("/")
    req = urllib.request.Request(
        url,
        headers={"x-api-key": api_key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _aa_chat_api_to_scrape_shape(rec: dict) -> dict:
    """Normalize one record from ``/api/v2/data/llms/models`` into the
    shape ``fetch_aa_models()`` returns from scraping the public page.

    The shape ``_project_aa_view`` reads is the contract:
      - top-level: ``name``, ``slug``, ``release_date``,
        ``intelligence_index``, ``coding_index``, ``math_index``, and
        the optional ``model_family_slug`` / ``agentic_index`` /
        ``input_modality_image`` / ``reasoning_model`` fields
      - nested: ``end_to_end_response_time_metrics.total_time``,
        ``time_to_first_answer_token_metrics.total_time``,
        ``timescaleData.median_output_speed``
      - canonical-id key: ``model_creators.slug`` paired with ``slug``

    Fields the API doesn't expose are set to None. Downstream reads via
    ``dict.get`` so the explicit None is documentation, not load-bearing
    — keeping it records the API ↔ scrape field gap for future readers.
    """
    ev = rec.get("evaluations") or {}
    creator = rec.get("model_creator") or {}
    ttft = rec.get("median_time_to_first_token_seconds")
    tps = rec.get("median_output_tokens_per_second")
    return {
        # passthrough
        "id": rec.get("id"),
        "name": rec.get("name"),
        "slug": rec.get("slug"),
        "release_date": rec.get("release_date"),
        "pricing": rec.get("pricing"),
        # flattened scoring (scrape has these at top level; API nests
        # them under ``evaluations``)
        "intelligence_index": ev.get("artificial_analysis_intelligence_index"),
        "coding_index": ev.get("artificial_analysis_coding_index"),
        "math_index": ev.get("artificial_analysis_math_index"),
        # singular → plural rename so ``_aa_canonical_or_id`` reads the
        # creator slug from the place it expects
        "model_creators": (
            {
                "id": creator.get("id"),
                "name": creator.get("name"),
                "slug": creator.get("slug"),
            }
            if creator
            else None
        ),
        # nested-form synthesis so ``_project_aa_view`` picks them up
        # via the same dict path the scrape returns
        "time_to_first_answer_token_metrics": (
            {"total_time": ttft} if ttft is not None else None
        ),
        "timescaleData": (
            {"median_output_speed": tps} if tps is not None else None
        ),
        # Not exposed by the API. ``_project_aa_view`` reads each via
        # ``dict.get`` so writing None is documentation (records the
        # API↔scrape field gap) rather than load-bearing. The previously
        # bridged ``is_open_weights`` and ``knowledge_cutoff_date`` were
        # dropped registry-wide in commits ca0268ae and d6a5855f; they
        # don't need a placeholder here anymore.
        "model_family_slug": None,
        "agentic_index": None,
        "input_modality_image": None,
        "reasoning_model": None,
        "end_to_end_response_time_metrics": None,
        "deleted": False,
    }


def fetch_aa_models_via_api(api_key: str) -> list[dict]:
    """API counterpart to ``fetch_aa_models()``. Returns the same
    shape so ``_project_aa_view``, ``_aa_canonical_or_id``, and
    ``build_aa_overlay`` are path-agnostic.

    Raises on HTTP / network error; ``cmd_sync`` decides whether to
    fall back to the scrape path.
    """
    envelope = _aa_api_get(AA_API_LLMS_PATH, api_key)
    records = envelope.get("data") or []
    return [_aa_chat_api_to_scrape_shape(r) for r in records]


def _aa_media_api_to_scrape_shape(rec: dict) -> dict:
    """Normalize one media-leaderboard record from the API into the row
    shape ``_extract_aa_leaderboard_rows`` produces and
    ``_build_media_entry`` reads.

    The deltas are minimal:
      - API: ``model_creator`` (singular) → scrape: ``creator``
      - API: no ``url`` field. Scrape carries
        ``/image/model-families/...``; ``_build_media_entry`` writes it
        into the provenance bag but no other consumer uses it.
    """
    creator = rec.get("model_creator") or {}
    return {
        "id": rec.get("id"),
        "name": rec.get("name"),
        "url": None,
        "rank": rec.get("rank"),
        "elo": rec.get("elo"),
        "appearances": rec.get("appearances"),
        "creator": (
            {"id": creator.get("id"), "name": creator.get("name")}
            if creator
            else None
        ),
    }


def _fetch_aa_media_via_api(path: str, api_key: str) -> list[dict]:
    envelope = _aa_api_get(path, api_key)
    records = envelope.get("data") or []
    rows = [_aa_media_api_to_scrape_shape(r) for r in records]
    rows.sort(key=lambda r: r.get("rank") if r.get("rank") is not None else 99999)
    return rows


def fetch_aa_text_to_image_via_api(api_key: str) -> list[dict]:
    """API counterpart to ``fetch_aa_text_to_image()``. Same shape."""
    return _fetch_aa_media_via_api(AA_API_T2I_PATH, api_key)


def fetch_aa_image_editing_via_api(api_key: str) -> list[dict]:
    """API counterpart to ``fetch_aa_image_editing()``. Same shape."""
    return _fetch_aa_media_via_api(AA_API_EDIT_PATH, api_key)


def fetch_aa_text_to_video_via_api(api_key: str) -> list[dict]:
    """API counterpart to ``fetch_aa_text_to_video()``. Same shape."""
    return _fetch_aa_media_via_api(AA_API_T2V_PATH, api_key)


# ──────────────────────────────────────────────────────────────────────────
# Source view extractors
# ──────────────────────────────────────────────────────────────────────────


def openrouter_view(model: dict) -> dict:
    """Project an OpenRouter API entry into our registry's per-source view."""
    arch = model.get("architecture") or {}
    input_mods = arch.get("input_modalities") or []
    pricing = model.get("pricing") or {}
    return {
        "id": model.get("id"),
        "display_name": model.get("name"),
        "context_length": model.get("context_length"),
        "input_modalities": input_mods,
        "output_modalities": arch.get("output_modalities") or [],
        "vision_claimed": ("image" in input_mods),
        "supported_parameters": model.get("supported_parameters") or [],
        "pricing": {
            "input_per_token": _maybe_float(pricing.get("prompt")),
            "output_per_token": _maybe_float(pricing.get("completion")),
        },
        "hugging_face_id": model.get("hugging_face_id"),
        "fetched_at": _now_iso(),
    }


def _maybe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def litellm_lookup(model_id: str, litellm: dict, index: dict | None = None) -> dict | None:
    """Return the LiteLLM entry for an OpenRouter model id.

    Strategy:
      1) Exact: openrouter/<id> → <id> → bare last-segment
      2) Token-set exact match against the bare last-segment
      3) Token-set superset match (LiteLLM key carries extra date/version
         tokens, e.g., ``claude-3-5-haiku-20241022`` vs our
         ``claude-3.5-haiku``)
    """
    candidates = [
        f"openrouter/{model_id}",
        model_id,
        model_id.split("/")[-1],
    ]
    for k in candidates:
        if k in litellm:
            entry = dict(litellm[k])
            entry["_lookup_key"] = k
            entry["_match_type"] = "exact"
            return entry
    if index is None:
        return None
    tokens = frozenset(tokenize_model_name(model_id.split("/")[-1]))
    if not tokens:
        return None
    # Exact token-set match
    for tk, ents in index.items():
        if tk == tokens:
            key, entry = ents[0]
            out = dict(entry); out["_lookup_key"] = key; out["_match_type"] = "tokens-exact"
            return out
    # Superset match — we are a subset of a LiteLLM key with extra tokens
    best: tuple | None = None
    for tk, ents in index.items():
        if tokens.issubset(tk):
            extra = len(tk) - len(tokens)
            if best is None or extra < best[0]:
                best = (extra, ents[0])
    if best is not None:
        key, entry = best[1]
        out = dict(entry); out["_lookup_key"] = key; out["_match_type"] = "tokens-superset"
        return out
    return None


def build_litellm_token_index(litellm: dict) -> dict[frozenset, list[tuple[str, dict]]]:
    """Index every LiteLLM key by its tokenized last-segment, for fuzzy lookup."""
    index: dict[frozenset, list[tuple[str, dict]]] = {}
    for key, entry in litellm.items():
        if not isinstance(entry, dict):
            continue
        last = key.split("/")[-1]
        tokens = frozenset(tokenize_model_name(last))
        if not tokens:
            continue
        index.setdefault(tokens, []).append((key, entry))
    return index


def litellm_view(entry: dict | None) -> dict:
    if entry is None:
        return {"present": False, "supports_vision": None}
    sv = entry.get("supports_vision")
    return {
        "present": True,
        "lookup_key": entry.get("_lookup_key"),
        "supports_vision": sv if isinstance(sv, bool) else None,
        "supports_function_calling": entry.get("supports_function_calling"),
        "supports_tool_choice": entry.get("supports_tool_choice"),
        "max_input_tokens": entry.get("max_input_tokens"),
        "max_output_tokens": entry.get("max_output_tokens"),
    }


# ──────────────────────────────────────────────────────────────────────────
# Arena name mapping
# ──────────────────────────────────────────────────────────────────────────

# Static fallback for organization → OpenRouter vendor prefix.
# Auto-built at sync time by scanning OpenRouter's vendor prefixes
# and matching tokens; this list is just the seed for known cases
# where the heuristic might fail.
_ORG_TO_VENDOR_HINTS = {
    "google": "google",
    "openai": "openai",
    "anthropic": "anthropic",
    "meta": "meta-llama",
    "meta-ai": "meta-llama",
    "mistral": "mistralai",
    "mistral-ai": "mistralai",
    "alibaba": "qwen",
    "deepseek": "deepseek",
    "xai": "x-ai",
    "x-ai": "x-ai",
    "moonshot": "moonshotai",
    "moonshot-ai": "moonshotai",
    "nvidia": "nvidia",
    "cohere": "cohere",
    "ai21": "ai21",
    "perplexity": "perplexity",
    "stepfun": "stepfun-ai",
    "stepfun-ai": "stepfun-ai",
}


def _normalize_org(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def build_org_to_vendor_map(openrouter_ids: list[str]) -> dict[str, str]:
    """Derive the org-name → OpenRouter-vendor-prefix mapping.

    Starts from ``_ORG_TO_VENDOR_HINTS`` and augments by matching any
    additional Arena ``Organization`` values whose normalized form
    appears as a substring of an OpenRouter vendor prefix.
    """
    vendors = sorted({mid.split("/", 1)[0] for mid in openrouter_ids if "/" in mid})
    mapping = dict(_ORG_TO_VENDOR_HINTS)
    for vendor in vendors:
        # Add the vendor to the map under its own normalized form
        norm = _normalize_org(vendor)
        mapping.setdefault(norm, vendor)
    return mapping


# Used by version-disambiguation in map_arena_to_openrouter to prefer
# the most-recent dated variant when multiple OpenRouter IDs match the
# same Arena entry. Tokenization itself strips these — this regex is
# only for the tiebreak ranking.
_DATE_TAG = re.compile(r"\b\d{6,8}\b")


# Date / version-suffix patterns to strip BEFORE tokenization.
# Order matters: longest patterns first.
_PRE_TOKEN_STRIP = (
    # Parenthesized suffix groups (Arena: "Claude Opus 4 (20250514)")
    re.compile(r"\([^)]*\)"),
    # YYYY-MM-DD and YYYYMMDD date forms
    re.compile(r"\b\d{4}[-_]\d{2}[-_]\d{2}\b"),
    re.compile(r"\b\d{8}\b"),
    # MM-DD / MMDD tail dates (e.g., "Grok-4-0709", "Grok-3-Preview-02-24")
    re.compile(r"[-_]\d{2}[-_]\d{2}\b"),
    re.compile(r"[-_]\d{4}\b(?!\d)"),  # trailing 4-digit date (e.g., "-0709")
    # YYYY-MM forms
    re.compile(r"\b\d{4}[-_]\d{2}\b"),
    re.compile(r"\b\d{6}\b"),
    # Year-only tokens (be careful — only kill 4-digit years 2020-2030)
    re.compile(r"\b20[23]\d\b"),
)

# Brand-name synonyms to normalize. Pre-tokenization substitution.
_BRAND_NORMALIZE = (
    (re.compile(r"\bchatgpt\b", re.I), "gpt"),
    # Bedrock / vertex provider prefixes (e.g., "us.anthropic.")
    (re.compile(r"\b(?:us|eu|ap)\.anthropic\b", re.I), "anthropic"),
)

_NOISE_TOKENS = {
    # "chat" and "latest" were previously listed here but caused the
    # matcher to collapse meaningful OpenAI ids — gpt-5-chat lost its
    # distinguishing token and got Jaccard-fit to gpt-5-5 (xhigh),
    # inheriting the latter's score. Removed 2026-05-22 along with
    # the normalized-canonical pass to keep "-chat" / "-latest" /
    # "-image" / "-pro" suffixes meaningful enough to break ties on
    # their own.
    "instruct", "preview", "exp", "experimental", "stable",
    "base", "thinking", "reasoner", "model", "ai", "version",
    "release", "tuned", "v1", "v2", "v3", "v4", "v5",
}


def tokenize_model_name(name: str) -> set[str]:
    """Lowercase, normalize brand synonyms, strip dates / parenthetical
    suffixes, then split into semantic tokens for Jaccard scoring.

    Chunk L (2026-05-20): rewrote to close the algorithmic gaps the
    coverage audit surfaced — gpt-4o was unmatched because Arena lists
    "ChatGPT-4o-latest (2025-03-26)" and the prior tokenizer kept
    'chatgpt' + 'latest' + '2025' + '03' + '26' as separate tokens,
    bloating the union and crashing the Jaccard score.

    2026-05-22: version-number preservation fix. Earlier the tokenizer
    dropped all-digit tokens, which collapsed AA's hyphen-form slugs
    like "gpt-5-1" / "gpt-5-2" / "gpt-5-5" into the single token
    "{gpt}" — every OpenAI variant tied at Jaccard 0.5 against
    OpenRouter ids, and the first AA candidate in iteration order
    silently won. GPT-5.1 / 5.2 / 5.4 etc. all ended up assigned
    GPT-5.5's intelligence score. Two changes close it:

      (a) Normalize dots to hyphens BEFORE splitting so
          "gpt-5.1" and "gpt-5-1" tokenize identically.
      (b) Keep short numeric tokens (1-3 digits) as version
          components. Only drop 4+ digit tokens that look like
          years/date codes.
    """
    if not name:
        return set()
    raw = name.lower()
    # Normalize brand synonyms first (e.g., ChatGPT → gpt)
    for pat, repl in _BRAND_NORMALIZE:
        raw = pat.sub(repl, raw)
    # Strip parenthesized / dated suffixes before token-splitting
    for pat in _PRE_TOKEN_STRIP:
        raw = pat.sub(" ", raw)
    # Normalize dots to hyphens so "gpt-5.1" and "gpt-5-1" produce
    # identical token sets — both yield {gpt, 5, 1}.
    raw = raw.replace(".", "-")
    # Split on any non-alphanumeric run.
    tokens = re.split(r"[^a-z0-9]+", raw)
    out: set[str] = set()
    for t in tokens:
        if not t:
            continue
        if t in _NOISE_TOKENS:
            continue
        # Drop all-digit tokens of 4+ chars (years, date codes like
        # "2024" / "0613" / "20240806"). Short digit-only tokens like
        # "5" / "13" / "72" survive as version / size components —
        # losing them was what crashed the GPT-5.1-vs-5.5 disambiguation.
        if t.isdigit() and len(t) >= 4:
            continue
        # Split compound family+version tokens like "qwen2.5" into
        # "qwen" + "2" + "5" so they match hyphen-form IDs.
        m = re.match(r"^([a-z]+)(\d[\d-]*)$", t)
        if m:
            family, ver = m.group(1), m.group(2)
            if family not in _NOISE_TOKENS:
                out.add(family)
            # Split the version digits the same way as standalone tokens
            for part in ver.split("-"):
                if not part:
                    continue
                if part.isdigit() and len(part) >= 4:
                    continue
                out.add(part)
            continue
        out.add(t)
    return out


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def map_arena_to_openrouter(
    arena_row: dict,
    or_ids_by_vendor: dict[str, list[str]],
    org_to_vendor: dict[str, str],
) -> str | None:
    """Pick the best OpenRouter id for an Arena row, or None."""
    org = arena_row.get("Organization") or ""
    model_name = arena_row.get("Model") or ""
    if not model_name:
        return None
    # Resolve vendor
    vendor_key = _normalize_org(org)
    vendor = org_to_vendor.get(vendor_key)
    if vendor is None:
        # Try one-step fuzzy: any vendor whose normalized form starts
        # with the org's first significant token.
        for k, v in org_to_vendor.items():
            if vendor_key and (k.startswith(vendor_key) or vendor_key.startswith(k)):
                vendor = v
                break
    if vendor is None:
        return None
    candidates = or_ids_by_vendor.get(vendor, [])
    if not candidates:
        return None
    arena_tokens = tokenize_model_name(model_name)
    best_id: str | None = None
    best_score = 0.0
    best_date = ""
    for or_id in candidates:
        or_tokens = tokenize_model_name(or_id.split("/", 1)[-1])
        score = jaccard(arena_tokens, or_tokens)
        # Date tiebreak: newer is better
        date_match = _DATE_TAG.search(or_id)
        date_str = date_match.group(0) if date_match else ""
        if score > best_score or (score == best_score and date_str > best_date):
            best_score = score
            best_id = or_id
            best_date = date_str
    return best_id if best_score >= 0.5 else None


# AA model_creators.slug → OpenRouter vendor prefix. Most match
# directly; the few that don't are normalized via _ORG_TO_VENDOR_HINTS.
_AA_CREATOR_SLUG_REMAP = {
    "meta": "meta-llama",
    "alibaba": "qwen",
}


def _aa_canonical_or_id(m: dict) -> str | None:
    """Synthesize the most-likely OpenRouter id for an AA entry.
    ``<creator_slug>/<model_slug>``, with the small vendor remap."""
    creators = m.get("model_creators") or {}
    csl = creators.get("slug") if isinstance(creators, dict) else None
    msl = m.get("slug")
    if not (csl and msl):
        return None
    vendor = _AA_CREATOR_SLUG_REMAP.get(csl, csl)
    return f"{vendor}/{msl}"


def _project_aa_view(m: dict) -> dict:
    """Project an AA model dict into the registry's per-source view."""
    e2e = m.get("end_to_end_response_time_metrics") or {}
    ttft = m.get("time_to_first_answer_token_metrics") or {}
    tsd = m.get("timescaleData") or {}
    return {
        "aa_name": m.get("name"),
        "aa_slug": m.get("slug"),
        "aa_model_family_slug": m.get("model_family_slug"),
        "aa_intelligence_index": _maybe_float(m.get("intelligence_index")),
        "aa_coding_index": _maybe_float(m.get("coding_index")),
        "aa_agentic_index": _maybe_float(m.get("agentic_index")),
        "aa_math_index": _maybe_float(m.get("math_index")),
        "aa_input_modality_image": m.get("input_modality_image"),
        "aa_reasoning_model": m.get("reasoning_model"),
        "aa_release_date": m.get("release_date"),
        "latency_total_seconds": _maybe_float(e2e.get("total_time")),
        "latency_ttft_seconds": _maybe_float(ttft.get("total_time")),
        "output_tokens_per_second": _maybe_float(tsd.get("median_output_speed")),
        "fetched_at": _now_iso(),
    }


def build_aa_overlay(
    aa_models: list[dict], openrouter_ids: list[str]
) -> dict[str, dict]:
    """Return {openrouter_id: aa_view_dict}.

    Three-pass matching:
      1. Direct canonical id match — AA's ``<creator_slug>/<model_slug>``
         (after the small vendor remap) often matches an OpenRouter id
         verbatim (``openai/gpt-4o-2024-08-06`` etc.). Highest-precision,
         zero-Jaccard pass.
      2. Normalized canonical match — replace "." with "-" in OR id and
         try again. Picks up ``openai/gpt-5.5`` ↔ AA ``openai/gpt-5-5``
         which the verbatim pass misses on punctuation alone. (Added
         2026-05-22 to stop these cases from falling through to fuzzy.)
      3. Within-vendor Jaccard fallback — for OR ids that didn't match
         the first two passes, score against AA candidates with the
         same vendor; pick best above 0.65 threshold (raised from 0.5
         2026-05-22 to drop spurious cross-family matches). On ties at
         the top, prefer the AA candidate with the highest
         intelligence_index — collapses AA's xhigh/high/medium/low
         reasoning-effort variants to the strongest one per OR id.
    """
    # Pass 1 index — every AA model's canonical id
    aa_by_canonical: dict[str, dict] = {}
    aa_by_vendor: dict[str, list[dict]] = {}
    for m in aa_models:
        if m.get("deleted"):
            continue
        cid = _aa_canonical_or_id(m)
        if cid:
            aa_by_canonical[cid] = m
            vendor, _ = cid.split("/", 1)
            aa_by_vendor.setdefault(vendor, []).append(m)
    # Pass 2 index — normalized canonical (dot → hyphen, lowercased)
    aa_by_norm_canonical: dict[str, dict] = {
        cid.replace(".", "-").lower(): m for cid, m in aa_by_canonical.items()
    }

    overlay: dict[str, dict] = {}
    direct_hits = 0
    norm_hits = 0
    fuzzy_hits = 0
    for oid in openrouter_ids:
        # Pass 1: direct canonical match
        if oid in aa_by_canonical:
            overlay[oid] = _project_aa_view(aa_by_canonical[oid])
            overlay[oid]["match_type"] = "canonical"
            direct_hits += 1
            continue
        # Pass 2: normalized canonical (dot → hyphen). Handles
        # openai/gpt-5.5 ↔ openai/gpt-5-5 etc. without going to fuzzy.
        norm = oid.replace(".", "-").lower()
        if norm in aa_by_norm_canonical:
            overlay[oid] = _project_aa_view(aa_by_norm_canonical[norm])
            overlay[oid]["match_type"] = "canonical-normalized"
            norm_hits += 1
            continue
        # Pass 2: within-vendor Jaccard fallback
        if "/" not in oid:
            continue
        vendor, _ = oid.split("/", 1)
        candidates = aa_by_vendor.get(vendor, [])
        if not candidates:
            continue
        or_tokens = tokenize_model_name(oid.split("/", 1)[-1])
        if not or_tokens:
            continue
        # Two-stage candidate pick:
        #  1. Find the maximum Jaccard score across all AA candidates
        #     in this vendor.
        #  2. Among candidates tied at that maximum, pick the one with
        #     the HIGHEST intelligence_index. This collapses AA's
        #     reasoning-effort variants (xhigh / high / medium / low)
        #     to one OpenRouter id while picking the strongest
        #     configuration — so ``openai/gpt-5.5`` gets gpt-5-5
        #     (xhigh) at 60.24 rather than whichever variant came
        #     first in iteration order. Models with no intelligence
        #     score sort to the bottom of the tie.
        best_score = 0.0
        for m in candidates:
            aa_name = m.get("slug") or m.get("name") or ""
            aa_tokens = tokenize_model_name(aa_name)
            if not aa_tokens:
                continue
            score = jaccard(or_tokens, aa_tokens)
            if score > best_score:
                best_score = score
        # Threshold raised from 0.5 → 0.7 on 2026-05-22 to drop
        # spurious cross-family matches (gpt-5-image → gpt-5-5,
        # gpt-5-chat → gpt-5-5, etc.) that previously inherited the
        # wrong AA intelligence score. Legitimate matches almost
        # always score >0.8 via the canonical-normalized pass above,
        # so the fuzzy fallback only needs to catch the genuinely
        # close-but-not-canonical cases — those benefit from a
        # stricter cutoff.
        if best_score < 0.7:
            continue
        # Round to 3 decimals so near-ties (0.6666 vs 0.6667) tiebreak
        # together rather than splitting hairs on floating-point noise.
        EPS = 1e-3
        tied = []
        for m in candidates:
            aa_name = m.get("slug") or m.get("name") or ""
            aa_tokens = tokenize_model_name(aa_name)
            if not aa_tokens:
                continue
            if abs(jaccard(or_tokens, aa_tokens) - best_score) <= EPS:
                tied.append(m)
        if not tied:
            continue

        def _intel_key(mm):
            v = mm.get("intelligence_index")
            return float(v) if isinstance(v, (int, float)) else -1.0

        best = max(tied, key=_intel_key)
        overlay[oid] = _project_aa_view(best)
        overlay[oid]["match_type"] = "jaccard"
        overlay[oid]["match_score"] = round(best_score, 3)
        fuzzy_hits += 1
    print(f"[sync]   AA → OpenRouter: {direct_hits} direct + {norm_hits} normalized + {fuzzy_hits} fuzzy = {len(overlay)} total", flush=True)
    return overlay


# ──────────────────────────────────────────────────────────────────────────
# AA media leaderboards (text-to-image, image-editing, text-to-video) →
# standalone registry entries. These models don't have OpenRouter or
# LiteLLM presence, so they're added directly to ``registry["models"]``
# after ``merge_sources`` runs. Keyed by ``aa-img:<uuid>``,
# ``aa-edit:<uuid>``, ``aa-vid:<uuid>`` to avoid colliding with OpenRouter
# model ids. The same physical model can appear under multiple keys
# (e.g. GPT Image 1.5 has separate Elo scores on the text-to-image and
# image-editing leaderboards — that's two registry entries, scored
# independently per capability).
# ──────────────────────────────────────────────────────────────────────────

# Each media row maps to: ID-prefix + category-label
_MEDIA_CATEGORY_SPEC = {
    "image_generation": ("aa-img", "Image generation"),
    "image_editing":    ("aa-edit", "Image editing"),
    "text_to_video":    ("aa-vid", "Text-to-video"),
}


def _build_media_entry(row: dict, category: str, fetched_at: str) -> tuple[str, dict] | None:
    """Convert one AA leaderboard row into a registry-shape entry.
    Returns ``(model_id, entry)`` or ``None`` if the row is malformed.
    """
    spec = _MEDIA_CATEGORY_SPEC.get(category)
    if spec is None:
        return None
    prefix, _label = spec
    uuid = row.get("id")
    if not uuid:
        return None
    model_id = f"{prefix}:{uuid}"
    creator = (row.get("creator") or {}).get("name") or "Unknown"
    # AA leaderboard row carries pricing in "pricePer1kImages" (USD
    # per 1,000 generations) — matches the leaderboard's API Pricing
    # column verbatim. ``openWeightsUrl`` is non-null when the model
    # has an open-weights release (Black Forest Labs / HiDream /
    # etc.). ``released`` is an ISO date string for release_date.
    price_per_1k = row.get("pricePer1kImages")
    open_weights_url = row.get("openWeightsUrl")
    entry: dict = {
        "id": model_id,
        "display_name": row.get("name") or model_id,
        "provider": "artificial-analysis",
        "category": category,
        # Vision/context/etc. don't apply to image-gen output models;
        # leave them None so the existing UI filters degrade cleanly.
        "vision_capable": None,
        "vision_verified_by": None,
        "context_length": None,
        "supports_function_calling": None,
        "supports_tool_choice": None,
        # Structured pricing — sibling shape to chat's
        # ``pricing.input_per_token`` / ``output_per_token`` but with
        # a different unit. None when AA shows "Coming soon" / "No API
        # available" / null. Auto-populate's cost math knows to read
        # this field for category != "chat" entries.
        "pricing": {"per_1k_images": price_per_1k} if price_per_1k is not None else None,
        "hugging_face_id": None,
        # Elo plays the role intelligence_score plays for chat models —
        # store it in the same field so cross-cutting code (preset
        # ranking, "sort by intelligence") Just Works for image models.
        "intelligence_score": row.get("elo"),
        "intelligence_rank": row.get("rank"),
        "intelligence_votes": row.get("appearances"),
        "aa_intelligence_index": None,
        "aa_coding_index": None,
        "aa_agentic_index": None,
        "aa_math_index": None,
        "latency_total_seconds": None,
        "latency_ttft_seconds": None,
        "output_tokens_per_second": None,
        "reasoning_model": None,
        # AA's "released" field is an ISO date string; carry it
        # through so the UI can show "Apr 2026" etc.
        "release_date": row.get("released"),
        "is_open_weights": bool(open_weights_url),
        "last_synced_at": fetched_at,
        "vendor": creator,
        "_provenance": {
            "aa_leaderboard": {
                "category": category,
                "url": row.get("url"),
                "aa_uuid": uuid,
                "creator_id": (row.get("creator") or {}).get("id"),
                "open_weights_url": open_weights_url,
                "fetched_at": fetched_at,
            }
        },
    }
    return model_id, entry


def build_media_entries(
    text_to_image_rows: list[dict],
    image_editing_rows: list[dict],
    text_to_video_rows: list[dict],
    fetched_at: str,
) -> dict[str, dict]:
    """Build the full set of media-leaderboard registry entries.
    Returns ``{model_id: entry}`` ready to merge into
    ``registry["models"]``."""
    out: dict[str, dict] = {}
    for rows, category in (
        (text_to_image_rows, "image_generation"),
        (image_editing_rows, "image_editing"),
        (text_to_video_rows, "text_to_video"),
    ):
        for row in rows or []:
            built = _build_media_entry(row, category, fetched_at)
            if built is None:
                continue
            mid, entry = built
            out[mid] = entry
    return out


def build_arena_overlay(
    arena_rows: list[dict], openrouter_ids: list[str]
) -> dict[str, dict]:
    """Return {openrouter_id: arena_overlay_dict}.

    Chunk L (2026-05-20): rewrote to walk OR-ids and find each one's
    best Arena match, rather than walking Arena-rows and overwriting.
    The old Arena→OR direction collapsed multiple Arena variants of a
    family (e.g., the four GPT-4o dated variants) onto a single
    OpenRouter id, leaving the other family members null. The new
    direction lets ``openai/gpt-4o``, ``openai/gpt-4o-2024-05-13``,
    ``openai/gpt-4o-2024-08-06``, etc. each independently get scored
    against the Arena entries that match them best.
    """
    org_to_vendor = build_org_to_vendor_map(openrouter_ids)

    # Group Arena rows by mapped OpenRouter vendor for cheap lookup.
    arena_by_vendor: dict[str, list[dict]] = {}
    for row in arena_rows:
        org = row.get("Organization") or ""
        if not org:
            continue
        norm = _normalize_org(org)
        vendor = org_to_vendor.get(norm)
        if vendor is None:
            # Last-ditch fuzzy: any vendor key starting with the norm,
            # or norm starting with the vendor key.
            for k, v in org_to_vendor.items():
                if k and norm and (k.startswith(norm) or norm.startswith(k)):
                    vendor = v
                    break
        if vendor is None:
            continue
        arena_by_vendor.setdefault(vendor, []).append(row)

    overlay: dict[str, dict] = {}
    for oid in openrouter_ids:
        if "/" not in oid:
            continue
        vendor, _ = oid.split("/", 1)
        candidates = arena_by_vendor.get(vendor, [])
        if not candidates:
            continue
        or_tokens = tokenize_model_name(oid.split("/", 1)[-1])
        if not or_tokens:
            continue
        best_row: dict | None = None
        best_score = 0.0
        for row in candidates:
            arena_tokens = tokenize_model_name(row.get("Model") or "")
            if not arena_tokens:
                continue
            score = jaccard(arena_tokens, or_tokens)
            if score > best_score:
                best_score = score
                best_row = row
        if best_row is None or best_score < 0.5:
            continue
        score = best_row.get("Arena Score")
        rank = best_row.get("Rank* (UB)")
        try:
            score_val: float | None = float(score) if score else None
        except ValueError:
            score_val = None
        try:
            rank_val: int | None = int(rank) if rank else None
        except ValueError:
            rank_val = None
        overlay[oid] = {
            "arena_model_name": best_row.get("Model"),
            "arena_organization": best_row.get("Organization"),
            "intelligence_score": score_val,
            "intelligence_rank": rank_val,
            "votes": int(best_row["Votes"]) if (best_row.get("Votes") or "").isdigit() else None,
            "match_score": round(best_score, 3),
            "fetched_at": _now_iso(),
        }
    return overlay


# ──────────────────────────────────────────────────────────────────────────
# Merge: build the registry from the source views
# ──────────────────────────────────────────────────────────────────────────


def merge_sources(
    openrouter_models: list[dict],
    litellm: dict,
    arena_overlay: dict[str, dict],
    aa_overlay: dict[str, dict] | None = None,
    existing_registry: dict | None = None,
) -> dict:
    """Return the full registry dict ready for writing.

    When ``existing_registry`` is provided, empirical-probe results
    from prior runs are preserved (the probe is the most authoritative
    source for vision_capable; throwing it away on every sync would
    waste API tokens and force re-probing every refresh).
    """
    aa_overlay = aa_overlay or {}
    models: dict[str, dict] = {}
    ll_index = build_litellm_token_index(litellm)
    prior_models = (existing_registry or {}).get("models") or {}
    for ormodel in openrouter_models:
        or_view = openrouter_view(ormodel)
        model_id = or_view["id"]
        if not model_id:
            continue
        ll_entry = litellm_lookup(model_id, litellm, ll_index)
        ll_view = litellm_view(ll_entry)
        arena = arena_overlay.get(model_id)
        aa = aa_overlay.get(model_id)
        vision = _resolve_vision_capable(or_view, ll_view)

        # Preserve prior empirical probe verdict if present — it's the
        # most authoritative source and shouldn't be discarded on
        # every re-sync.
        prior = prior_models.get(model_id) or {}
        prior_probe = (prior.get("_provenance") or {}).get("empirical_probe")
        prior_verified_by = prior.get("vision_verified_by")
        if prior_probe and prior_verified_by == "empirical_probe":
            probed_value = prior_probe.get("vision_capable")
            if probed_value is not None:
                vision = {"value": probed_value, "source": "empirical_probe"}

        # Preserve other probe verdicts that aren't rederivable from the
        # raw catalog fetches — reachability and vendor audit cost real
        # API round-trips and shouldn't be wiped on a routine re-sync.
        prior_reach = (prior.get("_provenance") or {}).get("reachability")
        prior_vendor_audit = (prior.get("_provenance") or {}).get("vendor_audit")

        provenance = {
            "openrouter": {
                "input_modalities": or_view["input_modalities"],
                "vision_claimed": or_view["vision_claimed"],
                "fetched_at": or_view["fetched_at"],
            },
            "litellm": ll_view,
            "arena": arena,
            "artificialanalysis": aa,
        }
        if prior_probe:
            provenance["empirical_probe"] = prior_probe
        if prior_reach:
            provenance["reachability"] = prior_reach
        if prior_vendor_audit:
            provenance["vendor_audit"] = prior_vendor_audit

        models[model_id] = {
            "id": model_id,
            "display_name": or_view["display_name"],
            "provider": "openrouter",
            "vision_capable": vision["value"],
            "vision_verified_by": vision["source"],
            "context_length": or_view["context_length"],
            "supports_function_calling": ll_view.get("supports_function_calling"),
            "supports_tool_choice": ll_view.get("supports_tool_choice"),
            "pricing": or_view["pricing"],
            "hugging_face_id": or_view.get("hugging_face_id"),
            # Chatbot Arena intelligence
            "intelligence_score": arena["intelligence_score"] if arena else None,
            "intelligence_rank": arena["intelligence_rank"] if arena else None,
            "intelligence_votes": arena["votes"] if arena else None,
            # Artificial Analysis enrichment (intelligence + latency + tps)
            "aa_intelligence_index": aa["aa_intelligence_index"] if aa else None,
            "aa_coding_index": aa["aa_coding_index"] if aa else None,
            "aa_agentic_index": aa["aa_agentic_index"] if aa else None,
            "aa_math_index": aa["aa_math_index"] if aa else None,
            "latency_total_seconds": aa["latency_total_seconds"] if aa else None,
            "latency_ttft_seconds": aa["latency_ttft_seconds"] if aa else None,
            "output_tokens_per_second": aa["output_tokens_per_second"] if aa else None,
            "reasoning_model": aa["aa_reasoning_model"] if aa else None,
            "release_date": aa["aa_release_date"] if aa else None,
            "last_synced_at": _now_iso(),
            "_provenance": provenance,
        }
        # Mirror reach + vendor verdicts at the top level so the UI can
        # read them without diving into _provenance. Carried forward from
        # the prior registry so a re-sync doesn't wipe live probe data.
        if prior_reach:
            models[model_id]["reachable"] = prior_reach.get("reachable")
            models[model_id]["reachable_rate_limited"] = bool(prior_reach.get("rate_limited"))
            models[model_id]["reachable_probed_at"] = prior_reach.get("probed_at")
        if prior_vendor_audit:
            models[model_id]["vendor_listed"] = prior_vendor_audit.get("vendor_listed")
            models[model_id]["vendor_audited_at"] = prior_vendor_audit.get("audited_at")
    # Post-process: ``:free`` suffix variants inherit from their paid base
    # (same underlying model, billing-tier-only differentiation).
    inherited = _apply_free_suffix_inheritance(models)
    if inherited:
        print(f"[sync]   :free suffix inheritance applied to {inherited} model fields", flush=True)
    return {
        "$schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "model_count": len(models),
        "models": models,
    }


# Fields safe to inherit from <base> onto <base>:free. NOT pricing
# (that's the whole point of the :free tier) and NOT routing-specific
# operational fields. The semantic + capability + intelligence +
# performance fields are the same underlying model.
_FREE_INHERITABLE_FIELDS = (
    "vision_capable",  # but NOT vision_verified_by (its provenance differs)
    "intelligence_score", "intelligence_rank", "intelligence_votes",
    "aa_intelligence_index", "aa_coding_index", "aa_agentic_index",
    "aa_math_index", "latency_total_seconds", "latency_ttft_seconds",
    "output_tokens_per_second",
    "supports_function_calling", "supports_tool_choice",
    "reasoning_model", "release_date",
)


def _apply_free_suffix_inheritance(models: dict) -> int:
    """For every ``<base>:free`` id in the registry, inherit non-pricing
    fields from ``<base>`` when the paid variant exists and the :free
    field is null. Same underlying model — billing-tier differentiation
    only. Returns the count of fields inherited (for the log line)."""
    count = 0
    for mid, m in models.items():
        if not mid.endswith(":free"):
            continue
        base_id = mid[: -len(":free")]
        base = models.get(base_id)
        if base is None:
            continue
        for field in _FREE_INHERITABLE_FIELDS:
            if m.get(field) is None and base.get(field) is not None:
                m[field] = base[field]
                count += 1
        m["_inherited_from_base"] = base_id
    return count


def _resolve_vision_capable(or_view: dict, ll_view: dict) -> dict:
    """Decide the vision_capable value, returning {'value': bool|None,
    'source': str}.

    Rules (no probe at this stage — probe runs as a separate pass):
      1. LiteLLM explicit True or False wins (high-confidence per-field).
      2. OpenRouter ``architecture.input_modalities.includes('image')``
         is the provisional fallback when LiteLLM is silent.
      3. If neither source has an opinion, value=None (unknown —
         empirical probe will resolve).

    The empirical probe (separate pass) overrides any of these.
    """
    ll_sv = ll_view.get("supports_vision")
    if ll_sv is True or ll_sv is False:
        return {"value": ll_sv, "source": "litellm"}
    if or_view.get("vision_claimed"):
        return {"value": True, "source": "openrouter_provisional"}
    if or_view.get("input_modalities"):
        # OpenRouter declared modalities but didn't include 'image'
        return {"value": False, "source": "openrouter_modalities"}
    return {"value": None, "source": None}


# ──────────────────────────────────────────────────────────────────────────
# Empirical probe
# ──────────────────────────────────────────────────────────────────────────


def _load_openrouter_client():
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai SDK not installed; cannot probe. Run `pip install openai`."
        ) from e
    key = (
        os.environ.get("OPENROUTER_API_KEY", "")
        or _try_keyring("ora", "openrouter-api-key")
        or ""
    )
    if not key:
        raise RuntimeError("no OpenRouter API key available (env OPENROUTER_API_KEY or keyring 'ora/openrouter-api-key')")
    return OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")


def _try_keyring(service: str, key: str) -> str:
    try:
        import keyring
        return keyring.get_password(service, key) or ""
    except Exception:
        return ""


def _probe_image_data_url(digit: str) -> str:
    path = PROBE_ASSETS / f"digit_{digit}.png"
    data = path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def probe_one(client, model_id: str) -> dict:
    """Run a two-digit probe against one model. Returns a 3-state verdict.

    Per-digit outcome ∈ {'pass', 'fail', 'inconclusive'}.
      pass:   response contains the expected digit on a word boundary
      fail:   response is non-empty and does NOT contain the digit
              (model "saw" something but got it wrong / hallucinated)
      inconclusive: HTTP / SDK error, empty content with
              finish_reason='length' (reasoning ran out of tokens),
              empty content with no finish info, or any other state
              where we can't conclude

    Aggregate verdict ∈ {True, False, None}:
      True  : both digits passed
      False : at least one digit failed with a substantive response
              (text-only models that explicitly can't process images
              also land here when the provider returns a 4xx
              "No endpoints support image input" — that's a definitive
              text-only signal, not inconclusive)
      None  : both digits inconclusive (probe couldn't determine)

    Models marked None are NOT overridden in the registry; their
    pre-probe value sticks until a future probe pass resolves them.
    """
    prompt = (
        "What single digit appears in this image? "
        "Reply with only the digit, no other text."
    )
    details = []
    for digit in ARENA_DIGITS:
        per = {"digit": digit}
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": _probe_image_data_url(digit)}},
                    ],
                }],
                max_tokens=300,  # reasoning models need headroom
                extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora probe"},
            )
            choice = resp.choices[0] if resp.choices else None
            raw = (choice.message.content if choice and choice.message else None) or ""
            per["raw"] = raw
            per["finish_reason"] = getattr(choice, "finish_reason", None) if choice else None
            per["error"] = None
        except Exception as e:
            per["raw"] = ""
            per["finish_reason"] = None
            per["error"] = str(e)[:300]
        per["outcome"] = _probe_outcome(per, digit)
        details.append(per)

    outcomes = [d["outcome"] for d in details]
    if all(o == "pass" for o in outcomes):
        verdict: bool | None = True
    elif any(o == "fail" for o in outcomes):
        verdict = False
    else:
        verdict = None  # all inconclusive
    return {
        "model_id": model_id,
        "vision_capable": verdict,
        "probed_at": _now_iso(),
        "probes": details,
    }


# Provider-returned 4xx phrasing that explicitly says "no image support"
# for the model. These count as definitive text-only signal.
_DEFINITIVE_TEXT_ONLY_PATTERNS = (
    "no endpoints found that support image",
    "no endpoints that support image",
    "does not support image",
    "does not support multimodal",
)


def _probe_outcome(per: dict, digit: str) -> str:
    """Apply the three-state pass/fail/inconclusive logic."""
    err = (per.get("error") or "").lower()
    raw = per.get("raw") or ""
    stripped = raw.strip()
    finish = per.get("finish_reason")

    # 1. Definitive text-only signal from the provider error message
    if err and any(p in err for p in _DEFINITIVE_TEXT_ONLY_PATTERNS):
        return "fail"

    # 2. Other 4xx / SDK errors → inconclusive (couldn't tell)
    if err:
        return "inconclusive"

    # 3. Empty content with finish='length' → ran out of tokens
    #    (reasoning model spent all output budget on invisible
    #    thinking). Inconclusive — we don't know if it could see.
    if not stripped and finish == "length":
        return "inconclusive"

    # 4. Empty content with finish='stop' → model produced nothing
    #    despite being asked. Counts as failure (model declined
    #    or produced no visible response).
    if not stripped:
        # No content, no finish=length excuse → fail
        return "fail"

    # 5. Substantive response — does it contain the expected digit?
    if re.search(rf"(?<!\d){digit}(?!\d)", stripped):
        return "pass"

    # 6. Substantive response without the digit → fail
    return "fail"


# ──────────────────────────────────────────────────────────────────────────
# Discrepancy ledger
# ──────────────────────────────────────────────────────────────────────────


def append_discrepancy(entry: dict) -> None:
    DISCREPANCY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCREPANCY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ──────────────────────────────────────────────────────────────────────────
# AA path resolution (scrape vs api)
# ──────────────────────────────────────────────────────────────────────────
#
# Resolution order (first match wins):
#   1. ``--aa-path scrape|api`` CLI flag (if passed)
#   2. ``ORA_AA_PATH`` env var (scrape|api)
#   3. user setting ``external_apis.aa_path`` from user-settings.json
#   4. default "scrape" — friction-free, no key required
#
# Hard-fail rule: when the resolved path is "api" but no key is
# configured, ``cmd_sync`` aborts with a pointer to Settings → External
# APIs instead of silently falling back. The user picked API; they
# should know it's not working.
#
# Operational-fallback rule: when the resolved path is "api" and the
# key IS configured but a specific endpoint call errors (network /
# 4xx / 5xx), that one fetch falls back to the scrape path. The other
# endpoints still try the API. Each fallback is logged so the user can
# see what happened on the next sync.


def _resolve_aa_path(args) -> str:
    """Decide which AA path to use this run. Returns "scrape" or "api"."""
    cli_path = getattr(args, "aa_path", None)
    if cli_path in ("scrape", "api"):
        return cli_path
    env_path = (os.environ.get("ORA_AA_PATH") or "").strip().lower()
    if env_path in ("scrape", "api"):
        return env_path
    # User-settings is the persistent surface the Settings panel writes.
    # Import lazily so this script still runs in environments where
    # orchestrator/ isn't on the path (it normally is, via ORA_HOME).
    try:
        sys.path.insert(0, str(ORA_HOME))
        from orchestrator import user_settings  # type: ignore
        stored = user_settings.get_setting("external_apis.aa_path")
        if stored in ("scrape", "api"):
            return stored
    except Exception:
        pass
    return "scrape"


def _load_aa_api_key() -> str:
    """Read the AA API key from env (``AA_API_KEY``) or keyring
    (``ora/aa-api-key``). Returns "" when unset."""
    return (
        os.environ.get("AA_API_KEY", "").strip()
        or _try_keyring("ora", "aa-api-key")
        or ""
    )


def _fetch_aa_with_fallback(api_fn, scrape_fn, api_key: str, aa_path: str, label: str):
    """Dispatch one AA fetch by resolved path. Returns ``(rows, source)``
    where source ∈ {"api", "api→scrape", "scrape"}.

    When ``aa_path == "api"`` and ``api_fn`` raises, falls back to
    ``scrape_fn`` for this one endpoint only. When the scrape itself
    raises (or no api_key on the api path despite the cmd_sync gate),
    returns ([], source) so the registry still builds from the other
    sources.
    """
    if aa_path == "api" and api_key:
        try:
            rows = api_fn(api_key)
            print(f"[sync]   {label}: {len(rows)} rows via API", flush=True)
            return rows, "api"
        except Exception as e:
            print(
                f"[sync]   {label}: API fetch failed ({e}); "
                f"falling back to scrape for this endpoint",
                flush=True,
            )
            try:
                rows = scrape_fn()
                print(f"[sync]   {label}: {len(rows)} rows via scrape (fallback)", flush=True)
                return rows, "api→scrape"
            except Exception as e2:
                print(f"[sync]   {label}: scrape fallback also failed ({e2}); proceeding without", flush=True)
                return [], "api→scrape"
    # Scrape path (default, or API path without key when cmd_sync allowed it).
    try:
        rows = scrape_fn()
        print(f"[sync]   {label}: {len(rows)} rows via scrape", flush=True)
        return rows, "scrape"
    except Exception as e:
        print(f"[sync]   {label}: scrape failed ({e}); proceeding without", flush=True)
        return [], "scrape"


# ──────────────────────────────────────────────────────────────────────────
# Subcommands
# ──────────────────────────────────────────────────────────────────────────


def cmd_sync(args) -> int:
    print("[sync] fetching OpenRouter /api/v1/models …", flush=True)
    or_models = fetch_openrouter_models()
    print(f"[sync]   {len(or_models)} models", flush=True)
    print("[sync] fetching LiteLLM model_prices_and_context_window.json …", flush=True)
    litellm = fetch_litellm_models()
    print(f"[sync]   {len(litellm)} entries", flush=True)
    print("[sync] fetching Chatbot Arena ELO CSV …", flush=True)
    arena_rows = fetch_arena_rows()
    print(f"[sync]   {len(arena_rows)} rows", flush=True)

    # Resolve AA path (scrape default, or api when explicitly chosen).
    aa_path = _resolve_aa_path(args)
    aa_key = _load_aa_api_key() if aa_path == "api" else ""
    if aa_path == "api" and not aa_key:
        print(
            "[sync] AA path = api, but no key is configured.\n"
            "       Set your AA API key in Settings → External APIs\n"
            "       (or via `keyring set ora aa-api-key`), or switch\n"
            "       the AA source toggle back to Scrape, then re-sync.",
            flush=True,
        )
        return 1
    print(f"[sync] AA path: {aa_path}{' (key loaded)' if aa_key else ''}", flush=True)

    aa_models, aa_chat_source = _fetch_aa_with_fallback(
        fetch_aa_models_via_api, fetch_aa_models, aa_key, aa_path, "AA chat models"
    )
    t2i_rows, aa_t2i_source = _fetch_aa_with_fallback(
        fetch_aa_text_to_image_via_api, fetch_aa_text_to_image,
        aa_key, aa_path, "AA text-to-image",
    )
    edit_rows, aa_edit_source = _fetch_aa_with_fallback(
        fetch_aa_image_editing_via_api, fetch_aa_image_editing,
        aa_key, aa_path, "AA image-editing",
    )
    t2v_rows, aa_t2v_source = _fetch_aa_with_fallback(
        fetch_aa_text_to_video_via_api, fetch_aa_text_to_video,
        aa_key, aa_path, "AA text-to-video",
    )

    # Aggregate AA source label for the registry: "api" if all four
    # used the API cleanly, "scrape" if all four used the scrape,
    # "mixed" otherwise (one fell back). The Models pane reads this
    # to badge the last sync's source.
    aa_sources = {aa_chat_source, aa_t2i_source, aa_edit_source, aa_t2v_source}
    if aa_sources == {"api"}:
        aa_source_summary = "api"
    elif aa_sources == {"scrape"}:
        aa_source_summary = "scrape"
    else:
        aa_source_summary = "mixed"

    or_ids = [m.get("id") for m in or_models if m.get("id")]
    arena_overlay = build_arena_overlay(arena_rows, or_ids)
    print(f"[sync]   Arena → OpenRouter matches: {len(arena_overlay)}", flush=True)
    aa_overlay = build_aa_overlay(aa_models, or_ids) if aa_models else {}

    # Read existing registry to preserve empirical-probe verdicts.
    existing = None
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH) as f:
                existing = json.load(f)
            preserved = sum(
                1 for m in (existing.get("models") or {}).values()
                if (m.get("_provenance") or {}).get("empirical_probe")
            )
            if preserved:
                print(f"[sync]   preserving {preserved} prior empirical-probe verdicts", flush=True)
        except (OSError, json.JSONDecodeError):
            existing = None

    registry = merge_sources(
        or_models, litellm, arena_overlay,
        aa_overlay=aa_overlay,
        existing_registry=existing,
    )

    # Splice the AA media-leaderboard entries into the registry's models
    # dict. These have no OpenRouter or LiteLLM presence; they stand on
    # their own. Categorized by ``category`` field; keyed by ``aa-img:`` /
    # ``aa-edit:`` / ``aa-vid:`` prefix so they can't collide with
    # OpenRouter ids.
    media_entries = build_media_entries(
        t2i_rows, edit_rows, t2v_rows,
        fetched_at=registry.get("generated_at") or "",
    )
    chat_count = registry["model_count"]
    registry["models"].update(media_entries)
    registry["model_count"] = len(registry["models"])
    if media_entries:
        media_count = len(media_entries)
        print(
            f"[sync]   spliced {media_count} media-leaderboard entries "
            f"({chat_count} chat + {media_count} media = "
            f"{registry['model_count']} total)",
            flush=True,
        )

    # Stamp the AA source so the Models pane can badge the last sync's
    # path ("via Scrape" / "via API" / "Mixed"). "mixed" indicates the
    # API path was selected but at least one endpoint fell back.
    registry["aa_source"] = aa_source_summary

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
    print(f"[sync] wrote {REGISTRY_PATH} ({registry['model_count']} models)", flush=True)

    # Quick summary
    vc_true = sum(1 for m in registry["models"].values() if m["vision_capable"] is True)
    vc_false = sum(1 for m in registry["models"].values() if m["vision_capable"] is False)
    vc_null = sum(1 for m in registry["models"].values() if m["vision_capable"] is None)
    arena_count = sum(1 for m in registry["models"].values() if m.get("intelligence_score") is not None)
    aa_count = sum(1 for m in registry["models"].values() if m.get("aa_intelligence_index") is not None)
    any_intel = sum(
        1 for m in registry["models"].values()
        if m.get("intelligence_score") is not None or m.get("aa_intelligence_index") is not None
    )
    latency_count = sum(1 for m in registry["models"].values() if m.get("latency_total_seconds") is not None)
    tps_count = sum(1 for m in registry["models"].values() if m.get("output_tokens_per_second") is not None)
    total = registry["model_count"]
    print(
        f"[sync] vision_capable: true={vc_true} false={vc_false} null={vc_null} "
        f"(null = need probe)",
        flush=True,
    )
    print(
        f"[sync] intelligence coverage: "
        f"Arena ELO {arena_count}/{total} ({100*arena_count/total:.0f}%), "
        f"AA intelligence_index {aa_count}/{total} ({100*aa_count/total:.0f}%), "
        f"either {any_intel}/{total} ({100*any_intel/total:.0f}%)",
        flush=True,
    )
    print(
        f"[sync] latency/performance: ttft+e2e {latency_count}/{total} ({100*latency_count/total:.0f}%), "
        f"tokens/sec {tps_count}/{total} ({100*tps_count/total:.0f}%)",
        flush=True,
    )

    unverified = _count_unverified_positive(registry)
    if not args.no_probe and unverified > 0:
        print(
            f"[sync] running probe for {unverified} positive-vision claims "
            f"that have not been empirically verified …",
            flush=True,
        )
        _run_probe(args, mode="unverified_positive")

    # Reachability probe — opt-in. Costs ~15 minutes and a few cents of
    # API tokens against the full 358-chat-model catalog, so it doesn't
    # run on every sync. The user invokes it via the Models pane button
    # (or `python scripts/sync_model_registry.py reach`) when they want
    # to re-verify which models actually respond. Verdicts persist
    # between runs via the field-preservation logic in `_build_registry`.
    if getattr(args, "with_reach", False):
        with open(REGISTRY_PATH) as f:
            registry = json.load(f)
        reach_args = argparse.Namespace(
            revalidate=False,
            only_unknown=False,
            stale_days=7,
            limit=args.limit,
        )
        print("[sync] running reachability probe …", flush=True)
        _run_reach_probe(registry, reach_args)

    # Vendor-direct audit — fast (3 HTTP calls, <5s, free) and runs by
    # default unless --no-vendor-audit. Cheap to keep current.
    if not getattr(args, "no_vendor_audit", False):
        with open(REGISTRY_PATH) as f:
            registry = json.load(f)
        print("[sync] running vendor-direct audit …", flush=True)
        _run_vendor_audit(registry, argparse.Namespace())

    return 0


def cmd_probe(args) -> int:
    mode = "revalidate" if args.revalidate else "unverified_positive"
    return _run_probe(args, mode=mode)


def _count_unverified_positive(registry: dict) -> int:
    """Models with vision_capable=True but NOT yet verified by the
    empirical probe. Both OpenRouter and LiteLLM have been observed
    to make false-positive claims (kimi-k2.6 is in both with
    vision=True but returns empty content on any image input).
    Every positive claim therefore needs empirical confirmation."""
    return sum(
        1 for m in registry["models"].values()
        if m["vision_capable"] is True
        and m["vision_verified_by"] != "empirical_probe"
    )


def _run_probe(args, mode: str) -> int:
    """mode: 'unverified_positive' (kimi-class — probe only when OR
    claims vision and LiteLLM is silent), 'revalidate' (probe every
    vision-claiming model regardless of source — periodic sanity check),
    or 'all_null' (legacy — null vision flag only).
    """
    if not REGISTRY_PATH.exists():
        print(f"[probe] registry missing at {REGISTRY_PATH}; run `sync` first", flush=True)
        return 1
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    client = _load_openrouter_client()
    targets = []
    for mid, entry in registry["models"].items():
        if mode == "all_null" and entry["vision_capable"] is not None:
            continue
        if mode == "unverified_positive":
            if entry["vision_capable"] is not True:
                continue
            if entry["vision_verified_by"] == "empirical_probe":
                continue
        if mode == "revalidate":
            if entry["vision_capable"] is not True:
                continue
        targets.append(mid)
    if args.limit:
        targets = targets[: args.limit]
    print(f"[probe] probing {len(targets)} models", flush=True)
    confirmed = overridden = inconclusive = 0
    for i, mid in enumerate(targets, 1):
        result = probe_one(client, mid)
        entry = registry["models"][mid]
        prior = entry["vision_capable"]
        new_value = result["vision_capable"]
        # Always record the probe attempt for forensic audit, even when
        # inconclusive — future runs can see the prior attempts.
        entry["_provenance"]["empirical_probe"] = result
        if new_value is None:
            # Inconclusive — keep the prior value. Log so audit can see.
            inconclusive += 1
            verdict_str = "? inconclusive"
            marker = "  (keeping prior)"
        else:
            if prior != new_value:
                append_discrepancy({
                    "kind": "probe_overrode_claim",
                    "model_id": mid,
                    "prior_value": prior,
                    "prior_source": entry["vision_verified_by"],
                    "new_value": new_value,
                    "probe_detail": result["probes"],
                    "at": _now_iso(),
                })
                overridden += 1
                marker = "  (overrode prior)"
            else:
                confirmed += 1
                marker = "  (confirmed)"
            entry["vision_capable"] = new_value
            entry["vision_verified_by"] = "empirical_probe"
            verdict_str = "✓ vision" if new_value else "✗ text-only"
        print(f"[probe] {i}/{len(targets)} {mid:50s} → {verdict_str}{marker}", flush=True)
        time.sleep(0.5)  # gentle on the API; not strictly necessary
    registry["last_probe_at"] = _now_iso()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
    print(
        f"[probe] done. confirmed={confirmed} overridden={overridden} "
        f"inconclusive={inconclusive}",
        flush=True,
    )
    return 0


# ─── Reachability probe ───────────────────────────────────────────────────
#
# Separate from the vision probe. The vision probe sends an image and checks
# whether the model can read a digit — useful for the kimi-k2.6 false-vision
# class, but tells us nothing about whether a model responds at all. This
# probe sends a 1-character prompt with max_tokens=1 and classifies the
# response by HTTP status:
#
#   200            → reachable (model returned a completion)
#   429            → reachable, but rate-limited at probe time (common on
#                    free-tier models; the endpoint exists, the bucket was
#                    just empty). Flagged separately so the UI can surface it.
#   401 / 403      → auth issue, not the model's fault — inconclusive
#   404 / 410      → not deployable — model doesn't exist or is sunset
#   400 (other)    → request rejected by the provider — not deployable
#   5xx            → provider downtime — inconclusive (sticky null until next run)
#   network error  → our-side / DNS / timeout — inconclusive
#
# 429-aware retry: one 3s backoff before recording the verdict, so half the
# transient rate-limit hits resolve on second attempt. Per-model cost on
# OpenRouter is effectively zero (1 input + 1 output token).

_REACH_RETRY_DELAY_SEC = 3.0
_REACH_PROMPT = "hi"
# OpenAI's auto-routing meta-models (gpt-chat-latest, ~openai/gpt-*) reject
# max_tokens below a provider-set minimum (currently 16). Setting the probe
# to 16 sidesteps the false 400 without materially raising cost — cheapest
# tiers still bill fractions of a cent per call.
_REACH_MAX_TOKENS = 16

def _classify_reachability_error(err: Exception) -> tuple[bool, str | None, str, int | None]:
    """Map an OpenAI SDK exception to (reachable_verdict, rate_limited, error_kind, status_code).

    reachable_verdict: True / False / None (None = inconclusive, retry next run)
    rate_limited: True only when the status code was 429.
    error_kind: short token for the UI / logs.
    status_code: HTTP status if known.
    """
    status = getattr(err, "status_code", None)
    if status is None:
        # The OpenAI SDK exposes the HTTP status on most error types via
        # .status_code; fall back to parsing the message for numeric codes.
        msg = str(err)
        for code in (429, 404, 410, 403, 401, 400, 500, 502, 503, 504):
            if f"Error code: {code}" in msg or f" {code} " in msg:
                status = code
                break
    if status == 429:
        return True, True, "rate_limited", 429
    if status in (404, 410):
        return False, False, "not_found", status
    if status in (401, 403):
        return None, False, "unauthorized", status
    if status == 400:
        return False, False, "bad_request", 400
    if status and 500 <= status < 600:
        return None, False, "server_error", status
    return None, False, "network", status


_REACH_REQUEST_TIMEOUT_SEC = 30.0


def reach_probe_one(client, model_id: str) -> dict:
    """Send a 1-token completion. Returns the reachability record."""
    def attempt():
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": _REACH_PROMPT}],
                max_tokens=_REACH_MAX_TOKENS,
                timeout=_REACH_REQUEST_TIMEOUT_SEC,
                extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora reach probe"},
            )
            # Any non-error response → reachable. We don't care about content
            # (reasoning models often return empty content with finish_reason=length
            # at max_tokens=1; the endpoint still responded).
            return {
                "reachable": True,
                "rate_limited": False,
                "status_code": 200,
                "error_kind": None,
                "error_message": None,
            }
        except Exception as e:
            verdict, rate_limited, kind, status = _classify_reachability_error(e)
            return {
                "reachable": verdict,
                "rate_limited": rate_limited,
                "status_code": status,
                "error_kind": kind,
                "error_message": str(e)[:300],
            }

    record = attempt()
    if record.get("rate_limited"):
        # One retry after a short backoff catches half the transient 429s.
        time.sleep(_REACH_RETRY_DELAY_SEC)
        retry = attempt()
        if retry["reachable"] is True and not retry["rate_limited"]:
            record = retry
            record["retried_after_429"] = True
        else:
            record["retried_after_429"] = True

    record["probed_at"] = _now_iso()
    return record


def cmd_reach(args) -> int:
    """Run the reachability probe against every chat model in the registry
    (or a stale-only subset). Records ``_provenance.reachability`` per model.
    """
    if not REGISTRY_PATH.exists():
        print(f"[reach] registry missing at {REGISTRY_PATH}; run `sync` first", flush=True)
        return 1
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    return _run_reach_probe(registry, args)


def _run_reach_probe(registry: dict, args) -> int:
    client = _load_openrouter_client()
    models = registry.get("models") or {}
    targets: list[str] = []
    stale_after_days = getattr(args, "stale_days", 7) or 7
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=stale_after_days)
    revalidate = bool(getattr(args, "revalidate", False))
    only_unknown = bool(getattr(args, "only_unknown", False))

    for mid, m in models.items():
        # Skip media-category models — they aren't called through the same
        # chat-completions endpoint, so this probe's interpretation doesn't
        # apply. They'll get their own reachability check if we add one.
        if (m.get("category") or "chat") != "chat":
            continue
        prov = m.get("_provenance") or {}
        prior = prov.get("reachability") or {}
        prior_at_raw = prior.get("probed_at")
        prior_at = None
        if prior_at_raw:
            try:
                prior_at = datetime.fromisoformat(prior_at_raw.replace("Z", "+00:00"))
            except Exception:
                prior_at = None
        is_stale = (prior_at is None) or (prior_at < stale_cutoff)
        if revalidate:
            targets.append(mid)
        elif only_unknown:
            if prior.get("reachable") is None:
                targets.append(mid)
        elif is_stale:
            targets.append(mid)

    limit = getattr(args, "limit", 0) or 0
    if limit > 0:
        targets = targets[:limit]

    if not targets:
        print("[reach] no models need probing (use --revalidate to force).", flush=True)
        return 0

    print(f"[reach] probing {len(targets)} chat models …", flush=True)
    reachable = 0
    rate_limited = 0
    unreachable = 0
    inconclusive = 0
    for i, mid in enumerate(targets, start=1):
        rec = reach_probe_one(client, mid)
        prov = models[mid].setdefault("_provenance", {})
        prov["reachability"] = rec
        # Top-level mirror for quick consumer-side checks (frontend, auto-populate).
        models[mid]["reachable"] = rec.get("reachable")
        models[mid]["reachable_rate_limited"] = bool(rec.get("rate_limited"))
        models[mid]["reachable_probed_at"] = rec.get("probed_at")

        if rec["reachable"] is True and rec.get("rate_limited"):
            rate_limited += 1
            tag = "⏱ rate-limited"
        elif rec["reachable"] is True:
            reachable += 1
            tag = "✓ reachable"
        elif rec["reachable"] is False:
            unreachable += 1
            tag = f"✗ {rec.get('error_kind') or 'unreachable'}"
        else:
            inconclusive += 1
            tag = f"… {rec.get('error_kind') or 'inconclusive'}"
        print(f"[reach] {i}/{len(targets)} {mid:55s} → {tag}", flush=True)
        # Checkpoint every 25 models so a Ctrl-C / network hang doesn't
        # lose all in-progress probe data. The final write below still
        # runs at the end; this is just a backstop.
        if i % 25 == 0:
            registry["last_reach_probe_at"] = _now_iso()
            with open(REGISTRY_PATH, "w") as f:
                json.dump(registry, f, indent=2, sort_keys=False)
        time.sleep(0.2)  # gentle on the API

    registry["last_reach_probe_at"] = _now_iso()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
    print(
        f"[reach] done. reachable={reachable} rate_limited={rate_limited} "
        f"unreachable={unreachable} inconclusive={inconclusive}",
        flush=True,
    )
    return 0


# ─── Vendor-direct model audit ────────────────────────────────────────────
#
# Cross-checks each chat model in the registry against the vendor's own
# /models endpoint, using the API key stored in the macOS keyring
# (service "ora", per orchestrator/user_settings.py). Vendors covered:
#
#   anthropic  →  GET https://api.anthropic.com/v1/models
#   openai     →  GET https://api.openai.com/v1/models
#   gemini     →  GET https://generativelanguage.googleapis.com/v1beta/models
#
# Each chat model in the registry has an id like ``openai/gpt-5.5`` or
# ``anthropic/claude-opus-4.7``. We strip the vendor prefix and check
# whether the bare id appears in the vendor's authoritative list.
#
# Possible verdicts written to ``vendor_listed``:
#   True   — vendor confirms the model exists in their catalog
#   False  — vendor's list is loaded and the model is NOT there
#            (AA may have invented it, or it was deprecated by the vendor)
#   None   — couldn't check (no API key, no /models endpoint for vendor,
#            or fetch error). Sticky null until next run resolves.

import urllib.request
import urllib.error


def _vendor_keys() -> dict[str, str]:
    """Pull the three vendor-direct keys we can audit against."""
    out: dict[str, str] = {}
    for prov in ("anthropic", "openai", "gemini"):
        key = (
            os.environ.get(f"{prov.upper()}_API_KEY", "")
            or _try_keyring("ora", f"{prov}-api-key")
            or ""
        )
        if key:
            out[prov] = key
    return out


def _http_get_json(url: str, headers: dict | None = None, timeout: float = 30.0) -> dict | None:
    """Minimal JSON GET. Returns parsed body or raises on error."""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_anthropic_models(api_key: str) -> set[str]:
    """Fetch Anthropic's /v1/models. Returns set of bare model ids
    (e.g. ``claude-opus-4-20250514``, ``claude-3-5-sonnet-20241022``)."""
    ids: set[str] = set()
    next_after = None
    for _ in range(20):  # bounded — pagination
        url = "https://api.anthropic.com/v1/models?limit=1000"
        if next_after:
            url += f"&after_id={next_after}"
        body = _http_get_json(url, headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        })
        for item in (body.get("data") or []):
            mid = item.get("id")
            if mid:
                ids.add(mid)
        if body.get("has_more"):
            next_after = body.get("last_id")
            continue
        break
    return ids


def fetch_openai_models(api_key: str) -> set[str]:
    """Fetch OpenAI's /v1/models. Returns set of bare model ids."""
    body = _http_get_json("https://api.openai.com/v1/models",
                          headers={"Authorization": f"Bearer {api_key}"})
    return {item.get("id") for item in (body.get("data") or []) if item.get("id")}


def fetch_gemini_models(api_key: str) -> set[str]:
    """Fetch Google Gemini's /v1beta/models. Returns set of bare ids
    (Gemini reports them as ``models/gemini-3.0-pro``; strip the prefix
    so they match the OR-side ``gemini-3.0-pro`` slugs)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=1000"
    body = _http_get_json(url)
    out: set[str] = set()
    for item in (body.get("models") or []):
        name = item.get("name") or ""
        if name.startswith("models/"):
            name = name[len("models/"):]
        if name:
            out.add(name)
    # Pagination: handle nextPageToken if present
    next_token = body.get("nextPageToken")
    while next_token:
        url2 = (
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            f"&pageSize=1000&pageToken={next_token}"
        )
        body = _http_get_json(url2)
        for item in (body.get("models") or []):
            name = item.get("name") or ""
            if name.startswith("models/"):
                name = name[len("models/"):]
            if name:
                out.add(name)
        next_token = body.get("nextPageToken")
    return out


# OR-id-prefix → vendor key in our keychain map. Other OR prefixes
# (``x-ai``, ``moonshotai``, ``deepseek``, ``qwen``, ``meta-llama``, etc.)
# have no native /models endpoint we audit against — they stay as
# vendor_listed=null.
_OR_PREFIX_TO_VENDOR = {
    "openai":    "openai",
    "anthropic": "anthropic",
    "google":    "gemini",
}


def _bare_id_for_vendor(or_id: str, vendor: str) -> str | None:
    """Strip the OR provider prefix from an OR id. Returns the bare id
    that should match what the vendor's /models endpoint reports."""
    if "/" not in or_id:
        return None
    prefix, bare = or_id.split("/", 1)
    # Strip "~latest" mirror prefix Used by OR for vendor-mirror aliases
    if prefix.startswith("~"):
        prefix = prefix[1:]
    if prefix != vendor and prefix != _OR_PREFIX_TO_VENDOR.get(vendor, vendor):
        # The OR prefix doesn't match this vendor; skip
        return None
    # Drop any ``:free`` / ``:beta`` suffix appended by OR for variant routing
    if ":" in bare:
        bare = bare.split(":", 1)[0]
    return bare


def _vendor_audit_one(or_id: str, vendor_lists: dict[str, set[str]]) -> dict | None:
    """Check a single OR id against the loaded vendor lists. Returns a
    record (dict) or None if no vendor audit applies to this id."""
    if "/" not in or_id:
        return None
    or_prefix = or_id.split("/", 1)[0].lstrip("~")
    vendor = _OR_PREFIX_TO_VENDOR.get(or_prefix)
    if not vendor:
        return None
    if vendor not in vendor_lists:
        # Have a vendor mapping but no key/list for it — inconclusive.
        return {
            "vendor": vendor,
            "vendor_listed": None,
            "reason": "no_vendor_key_or_list",
            "audited_at": _now_iso(),
        }
    bare = _bare_id_for_vendor(or_id, vendor)
    if not bare:
        return None
    listed = bare in vendor_lists[vendor]
    if not listed:
        # Try a less-strict partial-match: maybe the vendor lists a
        # dated variant (e.g., claude-3-5-sonnet-20241022) when OR
        # uses the date-stripped form (claude-3-5-sonnet). If any
        # vendor id starts with the bare id followed by a hyphen and
        # digits, accept that as a match.
        prefix_match = any(
            v == bare or v.startswith(bare + "-")
            for v in vendor_lists[vendor]
        )
        listed = prefix_match
    return {
        "vendor": vendor,
        "vendor_listed": bool(listed),
        "bare_id": bare,
        "audited_at": _now_iso(),
    }


def cmd_vendor_audit(args) -> int:
    """Cross-check chat models against vendor /models endpoints."""
    if not REGISTRY_PATH.exists():
        print(f"[vendor-audit] registry missing at {REGISTRY_PATH}; run `sync` first", flush=True)
        return 1
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    return _run_vendor_audit(registry, args)


def _run_vendor_audit(registry: dict, args) -> int:
    keys = _vendor_keys()
    if not keys:
        print("[vendor-audit] no vendor API keys present in keyring "
              "(anthropic/openai/gemini). Set them in Settings → External APIs.",
              flush=True)
        return 0

    # Fetch each vendor's list once.
    vendor_lists: dict[str, set[str]] = {}
    for vendor, api_key in keys.items():
        try:
            if vendor == "anthropic":
                ids = fetch_anthropic_models(api_key)
            elif vendor == "openai":
                ids = fetch_openai_models(api_key)
            elif vendor == "gemini":
                ids = fetch_gemini_models(api_key)
            else:
                continue
            vendor_lists[vendor] = ids
            print(f"[vendor-audit] {vendor}: fetched {len(ids)} model ids",
                  flush=True)
        except Exception as exc:
            print(f"[vendor-audit] {vendor}: fetch failed ({exc}); skipping.",
                  flush=True)

    if not vendor_lists:
        print("[vendor-audit] no vendor lists fetched; nothing to audit.",
              flush=True)
        return 1

    models = registry.get("models") or {}
    confirmed = 0
    phantom = 0
    inconclusive = 0
    skipped = 0
    for mid, m in models.items():
        if (m.get("category") or "chat") != "chat":
            skipped += 1
            continue
        rec = _vendor_audit_one(mid, vendor_lists)
        if rec is None:
            # No audit applies (non-audited vendor like x-ai). Skip silently.
            continue
        prov = m.setdefault("_provenance", {})
        prov["vendor_audit"] = rec
        m["vendor_listed"] = rec.get("vendor_listed")
        m["vendor_audited_at"] = rec.get("audited_at")
        verdict = rec.get("vendor_listed")
        if verdict is True:
            confirmed += 1
        elif verdict is False:
            phantom += 1
            print(f"[vendor-audit] ✗ phantom: {mid} (vendor={rec['vendor']}, bare={rec.get('bare_id')})",
                  flush=True)
        else:
            inconclusive += 1

    registry["last_vendor_audit_at"] = _now_iso()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
    print(
        f"[vendor-audit] done. confirmed={confirmed} phantom={phantom} "
        f"inconclusive={inconclusive} non-audited-vendor-skipped (silent)",
        flush=True,
    )
    return 0


def cmd_audit(args) -> int:
    if not REGISTRY_PATH.exists():
        print(f"[audit] registry missing at {REGISTRY_PATH}", flush=True)
        return 1
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    total = registry["model_count"]
    models = registry["models"]
    vc_true = sum(1 for m in models.values() if m["vision_capable"] is True)
    vc_false = sum(1 for m in models.values() if m["vision_capable"] is False)
    vc_null = sum(1 for m in models.values() if m["vision_capable"] is None)
    intel = sum(1 for m in models.values() if m["intelligence_score"] is not None)
    by_source = {}
    for m in models.values():
        by_source[m["vision_verified_by"]] = by_source.get(m["vision_verified_by"], 0) + 1
    print(f"Registry: {REGISTRY_PATH}")
    print(f"Generated at: {registry['generated_at']}")
    print(f"Total models: {total}")
    print()
    print("vision_capable distribution:")
    print(f"  true:   {vc_true}")
    print(f"  false:  {vc_false}")
    print(f"  null:   {vc_null}  (needs probe)")
    print()
    print("vision_verified_by:")
    for k, v in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {k!s:30s} {v}")
    print()
    print(f"intelligence_score populated: {intel}/{total}")
    print()
    if DISCREPANCY_PATH.exists():
        with open(DISCREPANCY_PATH) as f:
            lines = f.readlines()
        print(f"Discrepancy ledger: {DISCREPANCY_PATH} — {len(lines)} entries")
        recent = [json.loads(l) for l in lines[-5:]]
        print("Last 5 discrepancies:")
        for d in recent:
            print(f"  {d.get('at','?')} {d.get('kind','?')} {d.get('model_id','?')}")
    else:
        print("Discrepancy ledger: empty (no overrides logged yet)")
    return 0


# ──────────────────────────────────────────────────────────────────────────
# Misc
# ──────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    p = argparse.ArgumentParser(description="Ora curated model registry sync.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_sync = sub.add_parser("sync", help="Pull all sources, merge, write registry. Probes unverified models by default.")
    sp_sync.add_argument("--no-probe", action="store_true", help="Skip the empirical vision probe pass.")
    sp_sync.add_argument("--with-reach", action="store_true", help="Run the reachability probe (opt-in; ~15 min, a few cents of tokens).")
    sp_sync.add_argument("--no-vendor-audit", action="store_true", help="Skip the vendor-direct /models audit (fast, free — kept on by default).")
    sp_sync.add_argument("--limit", type=int, default=0, help="(probe) Limit probe to this many models.")
    sp_sync.add_argument(
        "--aa-path", choices=("scrape", "api"), default=None,
        help="Override AA data source for this run. Default reads "
             "ORA_AA_PATH env var, then the stored Settings choice, then 'scrape'. "
             "API path requires a key in keyring ('ora/aa-api-key') or AA_API_KEY env var.",
    )
    sp_sync.set_defaults(func=cmd_sync)

    sp_probe = sub.add_parser("probe", help="Run empirical vision probes against unverified models.")
    sp_probe.add_argument("--revalidate", action="store_true", help="Re-probe models LiteLLM already flagged true.")
    sp_probe.add_argument("--limit", type=int, default=0, help="Limit probe to this many models.")
    sp_probe.set_defaults(func=cmd_probe)

    sp_vendor = sub.add_parser("vendor-audit", help="Cross-check chat models against vendor /models endpoints (Anthropic / OpenAI / Gemini).")
    sp_vendor.set_defaults(func=cmd_vendor_audit)

    sp_reach = sub.add_parser("reach", help="Run reachability probes (1-token call, 429-aware) against chat models.")
    sp_reach.add_argument("--revalidate", action="store_true", help="Re-probe every chat model, ignoring prior verdicts.")
    sp_reach.add_argument("--only-unknown", action="store_true", help="Probe only models whose reachable verdict is currently null.")
    sp_reach.add_argument("--stale-days", type=int, default=7, help="Re-probe models whose prior record is older than this (default 7).")
    sp_reach.add_argument("--limit", type=int, default=0, help="Limit probe to this many models.")
    sp_reach.set_defaults(func=cmd_reach)

    sp_audit = sub.add_parser("audit", help="Print a registry summary.")
    sp_audit.set_defaults(func=cmd_audit)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
