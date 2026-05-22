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
from datetime import datetime, timezone
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
        "knowledge_cutoff": model.get("knowledge_cutoff"),
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
    "instruct", "chat", "preview", "exp", "experimental", "stable",
    "latest", "base", "thinking", "reasoner", "model", "ai", "version",
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

    Additionally, compound version tokens like "qwen2.5" are split into
    family + version components so they match OpenRouter's hyphen-form
    "qwen-2.5". The number-then-letters/letters-then-numbers boundary
    triggers a split (preserving the numeric token).
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
    # Split on non-alphanumeric (but keep dots, for "2.5"-style versions)
    tokens = re.split(r"[^a-z0-9.]+", raw)
    out: set[str] = set()
    for t in tokens:
        if not t:
            continue
        # Drop all-digit tokens — leftover date / size fragments
        # ("2024", "13", "0125", etc.). Numeric size markers like
        # "72b" and version markers like "2.5" survive because they
        # contain non-digits.
        if t.isdigit():
            continue
        if t in _NOISE_TOKENS:
            continue
        # Split compound family+version tokens like "qwen2.5" into
        # "qwen" + "2.5" so they match hyphen-form IDs.
        m = re.match(r"^([a-z]+)(\d[\d.]*)$", t)
        if m:
            family, ver = m.group(1), m.group(2)
            if family not in _NOISE_TOKENS:
                out.add(family)
            out.add(ver)
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
        "aa_is_open_weights": m.get("is_open_weights"),
        "aa_reasoning_model": m.get("reasoning_model"),
        "aa_release_date": m.get("release_date"),
        "aa_knowledge_cutoff_date": m.get("knowledge_cutoff_date"),
        "latency_total_seconds": _maybe_float(e2e.get("total_time")),
        "latency_ttft_seconds": _maybe_float(ttft.get("total_time")),
        "output_tokens_per_second": _maybe_float(tsd.get("median_output_speed")),
        "fetched_at": _now_iso(),
    }


def build_aa_overlay(
    aa_models: list[dict], openrouter_ids: list[str]
) -> dict[str, dict]:
    """Return {openrouter_id: aa_view_dict}.

    Two-pass matching:
      1. Direct canonical id match — AA's ``<creator_slug>/<model_slug>``
         (after the small vendor remap) often matches an OpenRouter id
         verbatim (``openai/gpt-4o-2024-08-06`` etc.). High-precision,
         zero-Jaccard pass.
      2. Within-vendor Jaccard fallback — for OR ids that didn't match
         on canonical id, score against AA candidates with the same
         vendor; pick best above 0.5 threshold.
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

    overlay: dict[str, dict] = {}
    direct_hits = 0
    fuzzy_hits = 0
    for oid in openrouter_ids:
        # Pass 1: direct canonical match
        if oid in aa_by_canonical:
            overlay[oid] = _project_aa_view(aa_by_canonical[oid])
            overlay[oid]["match_type"] = "canonical"
            direct_hits += 1
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
        best: dict | None = None
        best_score = 0.0
        for m in candidates:
            aa_name = m.get("slug") or m.get("name") or ""
            aa_tokens = tokenize_model_name(aa_name)
            if not aa_tokens:
                continue
            score = jaccard(or_tokens, aa_tokens)
            if score > best_score:
                best_score = score
                best = m
        if best is not None and best_score >= 0.5:
            overlay[oid] = _project_aa_view(best)
            overlay[oid]["match_type"] = "jaccard"
            overlay[oid]["match_score"] = round(best_score, 3)
            fuzzy_hits += 1
    print(f"[sync]   AA → OpenRouter: {direct_hits} direct + {fuzzy_hits} fuzzy = {len(overlay)} total", flush=True)
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
        "pricing": None,
        "knowledge_cutoff": None,
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
        "is_open_weights": None,
        "reasoning_model": None,
        "release_date": None,
        "last_synced_at": fetched_at,
        "vendor": creator,
        "_provenance": {
            "aa_leaderboard": {
                "category": category,
                "url": row.get("url"),
                "aa_uuid": uuid,
                "creator_id": (row.get("creator") or {}).get("id"),
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
            "knowledge_cutoff": or_view.get("knowledge_cutoff"),
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
            "is_open_weights": aa["aa_is_open_weights"] if aa else None,
            "reasoning_model": aa["aa_reasoning_model"] if aa else None,
            "release_date": aa["aa_release_date"] if aa else None,
            "last_synced_at": _now_iso(),
            "_provenance": provenance,
        }
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
    "is_open_weights", "reasoning_model", "release_date",
    "knowledge_cutoff",
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
    print("[sync] fetching Artificial Analysis (public /models page) …", flush=True)
    try:
        aa_models = fetch_aa_models()
        print(f"[sync]   {len(aa_models)} AA models", flush=True)
    except Exception as e:
        # AA scrape failures are non-fatal — registry still works
        # with the other sources. Log and proceed with empty overlay.
        print(f"[sync]   AA fetch failed (proceeding without): {e}", flush=True)
        aa_models = []

    # AA media leaderboards (image gen, image editing, text-to-video).
    # Same fail-soft posture: any one failing leaves the others alone.
    print("[sync] fetching Artificial Analysis media leaderboards …", flush=True)
    try:
        t2i_rows = fetch_aa_text_to_image()
        print(f"[sync]   {len(t2i_rows)} text-to-image rows", flush=True)
    except Exception as e:
        print(f"[sync]   text-to-image fetch failed (proceeding without): {e}", flush=True)
        t2i_rows = []
    try:
        edit_rows = fetch_aa_image_editing()
        print(f"[sync]   {len(edit_rows)} image-editing rows", flush=True)
    except Exception as e:
        print(f"[sync]   image-editing fetch failed (proceeding without): {e}", flush=True)
        edit_rows = []
    try:
        t2v_rows = fetch_aa_text_to_video()
        print(f"[sync]   {len(t2v_rows)} text-to-video rows", flush=True)
    except Exception as e:
        print(f"[sync]   text-to-video fetch failed (proceeding without): {e}", flush=True)
        t2v_rows = []

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
    sp_sync.add_argument("--no-probe", action="store_true", help="Skip the empirical probe pass.")
    sp_sync.add_argument("--limit", type=int, default=0, help="(probe) Limit probe to this many models.")
    sp_sync.set_defaults(func=cmd_sync)

    sp_probe = sub.add_parser("probe", help="Run empirical probes against unverified models.")
    sp_probe.add_argument("--revalidate", action="store_true", help="Re-probe models LiteLLM already flagged true.")
    sp_probe.add_argument("--limit", type=int, default=0, help="Limit probe to this many models.")
    sp_probe.set_defaults(func=cmd_probe)

    sp_audit = sub.add_parser("audit", help="Print a registry summary.")
    sp_audit.set_defaults(func=cmd_audit)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
