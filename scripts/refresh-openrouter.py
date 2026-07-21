#!/usr/bin/env python3
"""Refresh the local OpenRouter model catalog.

OpenRouter exposes its full model directory at
``https://openrouter.ai/api/v1/models`` — no auth required for the
listing itself. This script fetches the catalog, normalizes each
entry into a compact shape the Ora UI can consume, groups by output
modality and vendor, and writes the result to:

    ~/ora/config/openrouter-catalog.json

The Buckets / Visual / Transcription / Speech tabs read this file
through the ``/config/openrouter/catalog`` server endpoint to populate
their model pickers.

Usage:
    python3 ~/ora/scripts/refresh-openrouter.py            # fetch + write
    python3 ~/ora/scripts/refresh-openrouter.py --dry-run  # print, no write

Invoked explicitly or by the authenticated model-registry refresh API. The
retired scheduled-tasks system cannot execute it. On network / parse errors,
the existing catalog file is left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

WORKSPACE      = os.path.expanduser("~/ora")
CATALOG_PATH   = os.path.join(WORKSPACE, "config/openrouter-catalog.json")
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter exposes the catalog per output-modality. Specialized
# modalities fetched FIRST so dual-output models (e.g. ``gpt-image-1``
# with output ``image,text``) get tagged with their specialized role.
# The bare-text slice runs last and only catches pure text-output models.
MODALITY_QUERIES = [
    ("image",         "image"),          # 20 (includes dual image+text)
    ("video",         "video"),          # 13
    ("audio",         "audio"),          # 5  (native audio understanding)
    ("speech",        "speech"),         # 8  (TTS)
    ("transcription", "transcription"),  # 6  (STT / Whisper-class)
    ("rerank",        "rerank"),         # 3
    ("embeddings",    "embedding"),      # 25
    ("",              "text"),           # remaining text-output models
]


def _fetch_one(query_value: str, timeout: int = 30) -> list[dict]:
    """Fetch one modality slice from OpenRouter."""
    url = OPENROUTER_URL
    if query_value:
        url += f"?output_modalities={urllib.parse.quote(query_value)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Ora-Catalog-Refresher/1.0",
            "Accept":     "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("data") or []


def _fetch_catalog(timeout: int = 30) -> list[dict]:
    """Pull every modality slice and merge, de-duplicating by id.

    A small fraction of entries appear in multiple slices (e.g. dual-output
    models). The first slice that contains an entry wins, and the tag
    attached to that slice becomes the canonical modality for the entry.
    """
    seen = {}
    for query_value, tag in MODALITY_QUERIES:
        try:
            entries = _fetch_one(query_value, timeout=timeout)
        except urllib.error.HTTPError as e:
            print(f"[refresh-openrouter] {tag} slice failed "
                  f"(HTTP {e.code}); continuing", file=sys.stderr)
            continue
        for e in entries:
            mid = e.get("id")
            if not mid or mid in seen:
                continue
            e["_ora_modality"] = tag
            seen[mid] = e
    return list(seen.values())


def _vendor_of(model_id: str) -> str:
    """OpenRouter IDs are always ``<vendor>/<model>``."""
    return model_id.split("/", 1)[0] if "/" in model_id else "unknown"


def _classify_modality(entry: dict) -> str:
    """Use the modality tag attached during the merge pass — that's the
    authoritative bucket (came from the query parameter we used to fetch
    the entry). Fall back to architecture inspection only if the tag is
    missing, which shouldn't happen in normal flow."""
    tag = entry.get("_ora_modality")
    if tag:
        return tag
    arch = entry.get("architecture", {}) or {}
    output = arch.get("output_modalities") or arch.get("modality") or ""
    if isinstance(output, list):
        output = ",".join(output)
    output = str(output).lower()
    for needle, label in [
        ("transcription", "transcription"), ("speech", "speech"),
        ("rerank", "rerank"), ("embedding", "embedding"),
        ("video", "video"), ("audio", "audio"),
        ("image", "image"),
    ]:
        if needle in output:
            return label
    return "text"


def _price(val) -> float | None:
    """Pricing fields come back as strings like '0.000003'. Convert
    to dollars-per-million-tokens for the UI ($5/M is friendlier than
    $0.000005/token). Returns None for unset / unparseable values."""
    if val in (None, "", "0", 0):
        return 0.0 if val == "0" or val == 0 else None
    try:
        return round(float(val) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def _extract_input_modalities(entry: dict) -> list[str]:
    """Read ``architecture.input_modalities`` from a raw OpenRouter entry.

    OpenRouter exposes per-model ``architecture`` data with an
    ``input_modalities`` array like ``["text", "image"]`` for multimodal
    models or ``["text"]`` for text-only. Some older entries don't have
    the field — fall back to parsing the ``modality`` shorthand
    ("text+image->text", "text->text", etc.) when present, else default
    to ``["text"]``.

    The result drives the picker's "vision-capable only" filter and the
    ``slots.image_generates`` chain's ability to be validated against
    actual model capabilities at refresh time.
    """
    arch = entry.get("architecture", {}) or {}
    raw = arch.get("input_modalities")
    if isinstance(raw, list) and raw:
        return [str(m).lower() for m in raw]

    # Parse the "text+image->text" shorthand when the array form is absent.
    mod = arch.get("modality") or ""
    if isinstance(mod, str) and "->" in mod:
        lhs = mod.split("->", 1)[0]
        parts = [p.strip().lower() for p in lhs.split("+") if p.strip()]
        if parts:
            return parts

    return ["text"]


def _normalize(entry: dict) -> dict:
    """Reduce a raw OpenRouter model entry to the shape the UI needs."""
    pricing = entry.get("pricing", {}) or {}
    top_provider = entry.get("top_provider", {}) or {}
    model_id = entry.get("id", "")
    input_mods = _extract_input_modalities(entry)
    return {
        "id":                  model_id,
        "vendor":              _vendor_of(model_id),
        "display_name":        entry.get("name") or model_id,
        "modality":            _classify_modality(entry),
        # New (2026-05-16): what the model ACCEPTS as input. Distinct from
        # `modality` which is OUTPUT-derived. Drives the picker filter for
        # vision-capable models and validates the image_generates slot
        # chain at refresh time.
        "input_modalities":    input_mods,
        "accepts_image":       "image" in input_mods,
        "context_length":      entry.get("context_length")
                                or top_provider.get("context_length"),
        "max_completion":      top_provider.get("max_completion_tokens"),
        "description":         (entry.get("description") or "").strip(),
        "pricing_per_million": {
            "prompt":      _price(pricing.get("prompt")),
            "completion":  _price(pricing.get("completion")),
            "image":       _price(pricing.get("image")),
            "request":     _price(pricing.get("request")),
        },
        "created":             entry.get("created"),
    }


def _group(models: list[dict]) -> dict:
    """Build vendor + modality indices the UI can use without re-grouping.

    Three indices:
      * ``by_modality``       — keyed by OUTPUT modality (text, image, ...).
      * ``by_vendor``         — keyed by vendor prefix (openai, anthropic, ...).
      * ``by_input_modality`` — keyed by INPUT modality. A model accepting
        ``["text", "image"]`` appears under BOTH ``text`` and ``image``.
        Drives the picker's "vision-capable only" filter for the
        image_generates / vision_extraction slot configuration.
    """
    by_modality: dict[str, list[str]] = {}
    by_vendor:   dict[str, list[str]] = {}
    by_input_modality: dict[str, list[str]] = {}
    for m in models:
        by_modality.setdefault(m["modality"], []).append(m["id"])
        by_vendor.setdefault(m["vendor"],     []).append(m["id"])
        for in_mod in m.get("input_modalities") or []:
            by_input_modality.setdefault(in_mod, []).append(m["id"])
    # Stable order within each group: vendor → display name.
    by_lookup = {m["id"]: m for m in models}
    def _sort_key(mid: str) -> tuple:
        m = by_lookup[mid]
        return (m["vendor"].lower(), m["display_name"].lower())
    for k in by_modality:
        by_modality[k].sort(key=_sort_key)
    for k in by_input_modality:
        by_input_modality[k].sort(key=_sort_key)
    for k in by_vendor:
        by_vendor[k].sort(key=lambda mid: by_lookup[mid]["display_name"].lower())
    return {
        "by_modality":       by_modality,
        "by_vendor":         by_vendor,
        "by_input_modality": by_input_modality,
    }


def build_catalog(raw_entries: list[dict]) -> dict:
    models = [_normalize(e) for e in raw_entries if e.get("id")]
    groups = _group(models)
    return {
        "fetched_at":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source":      OPENROUTER_URL,
        "model_count": len(models),
        "models":      models,
        **groups,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Print summary; don't write the catalog file.")
    args = p.parse_args()

    try:
        raw_entries = _fetch_catalog()
    except urllib.error.URLError as e:
        print(f"[refresh-openrouter] network error: {e}", file=sys.stderr)
        sys.exit(2)
    except (ValueError, KeyError) as e:
        print(f"[refresh-openrouter] parse error: {e}", file=sys.stderr)
        sys.exit(3)

    catalog = build_catalog(raw_entries)
    summary = {k: len(v) for k, v in catalog["by_modality"].items()}
    in_summary = {k: len(v) for k, v in catalog["by_input_modality"].items()}

    print(f"[refresh-openrouter] fetched {catalog['model_count']} models")
    print("  output modality:")
    for modality, n in sorted(summary.items(), key=lambda kv: -kv[1]):
        print(f"    {modality:>14}: {n}")
    print("  input modality (image-input is the load-bearing filter for")
    print("                   vision-extraction slot eligibility):")
    for modality, n in sorted(in_summary.items(), key=lambda kv: -kv[1]):
        print(f"    {modality:>14}: {n}")

    if args.dry_run:
        print("[refresh-openrouter] dry-run — catalog file untouched")
        return

    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=2)
        f.write("\n")
    print(f"[refresh-openrouter] wrote {CATALOG_PATH}")


if __name__ == "__main__":
    main()
