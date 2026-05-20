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


_DATE_TAG = re.compile(r"\b\d{6,8}\b")
_VERSION_TAG = re.compile(r"\b(?:v\d+|\d+\.\d+(?:\.\d+)?|\d+)\b")
_NOISE_TOKENS = {
    "instruct", "chat", "preview", "exp", "experimental", "stable",
    "latest", "base", "thinking", "reasoner", "model", "ai", "version",
    "release",
}


def tokenize_model_name(name: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, drop noise + dates, keep
    semantic tokens for Jaccard scoring."""
    if not name:
        return set()
    raw = name.lower()
    raw = _DATE_TAG.sub(" ", raw)
    tokens = re.split(r"[^a-z0-9.]+", raw)
    out: set[str] = set()
    for t in tokens:
        if not t or t in _NOISE_TOKENS:
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


def build_arena_overlay(
    arena_rows: list[dict], openrouter_ids: list[str]
) -> dict[str, dict]:
    """Return {openrouter_id: arena_overlay_dict}."""
    or_ids_by_vendor: dict[str, list[str]] = {}
    for oid in openrouter_ids:
        if "/" not in oid:
            continue
        vendor, _ = oid.split("/", 1)
        or_ids_by_vendor.setdefault(vendor, []).append(oid)
    org_to_vendor = build_org_to_vendor_map(openrouter_ids)

    overlay: dict[str, dict] = {}
    for row in arena_rows:
        mapped = map_arena_to_openrouter(row, or_ids_by_vendor, org_to_vendor)
        if mapped is None:
            continue
        score = row.get("Arena Score")
        rank = row.get("Rank* (UB)")
        try:
            score_val: float | None = float(score) if score else None
        except ValueError:
            score_val = None
        try:
            rank_val: int | None = int(rank) if rank else None
        except ValueError:
            rank_val = None
        # If multiple Arena rows map to the same OpenRouter id (versioned
        # variants vs canonical), keep the higher ELO.
        cur = overlay.get(mapped)
        if cur and cur.get("intelligence_score") and score_val is not None:
            if cur["intelligence_score"] >= score_val:
                continue
        overlay[mapped] = {
            "arena_model_name": row.get("Model"),
            "arena_organization": row.get("Organization"),
            "intelligence_score": score_val,
            "intelligence_rank": rank_val,
            "votes": int(row["Votes"]) if (row.get("Votes") or "").isdigit() else None,
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
) -> dict:
    """Return the full registry dict ready for writing."""
    models: dict[str, dict] = {}
    ll_index = build_litellm_token_index(litellm)
    for ormodel in openrouter_models:
        or_view = openrouter_view(ormodel)
        model_id = or_view["id"]
        if not model_id:
            continue
        ll_entry = litellm_lookup(model_id, litellm, ll_index)
        ll_view = litellm_view(ll_entry)
        arena = arena_overlay.get(model_id)
        vision = _resolve_vision_capable(or_view, ll_view)
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
            "intelligence_score": arena["intelligence_score"] if arena else None,
            "intelligence_rank": arena["intelligence_rank"] if arena else None,
            "intelligence_votes": arena["votes"] if arena else None,
            "last_synced_at": _now_iso(),
            "_provenance": {
                "openrouter": {
                    "input_modalities": or_view["input_modalities"],
                    "vision_claimed": or_view["vision_claimed"],
                    "fetched_at": or_view["fetched_at"],
                },
                "litellm": ll_view,
                "arena": arena,
            },
        }
    return {
        "$schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "model_count": len(models),
        "models": models,
    }


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

    or_ids = [m.get("id") for m in or_models if m.get("id")]
    arena_overlay = build_arena_overlay(arena_rows, or_ids)
    print(f"[sync]   Arena → OpenRouter matches: {len(arena_overlay)}", flush=True)

    registry = merge_sources(or_models, litellm, arena_overlay)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=False)
    print(f"[sync] wrote {REGISTRY_PATH} ({registry['model_count']} models)", flush=True)

    # Quick summary
    vc_true = sum(1 for m in registry["models"].values() if m["vision_capable"] is True)
    vc_false = sum(1 for m in registry["models"].values() if m["vision_capable"] is False)
    vc_null = sum(1 for m in registry["models"].values() if m["vision_capable"] is None)
    intel = sum(1 for m in registry["models"].values() if m["intelligence_score"] is not None)
    print(
        f"[sync] vision_capable: true={vc_true} false={vc_false} null={vc_null} "
        f"(null = need probe)",
        flush=True,
    )
    print(f"[sync] intelligence_score populated: {intel}/{registry['model_count']}", flush=True)

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
