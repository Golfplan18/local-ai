#!/usr/bin/env python3
"""Refresh the direct-API model registry from each provider's /models endpoint.

Currently covers Anthropic, OpenAI, and Google (Gemini). Each provider
exposes a list-models endpoint that returns its current catalog; this
script reconciles those against the existing endpoints registered in
~/ora/config/routing-config.json:

  - New models discovered upstream → appended as endpoints (status=active,
    tier auto-classified via name heuristic).
  - Endpoints whose model_id no longer appears upstream → marked
    status=deprecated. Preserved on disk so the user's bucket-slot
    references stay readable and the UI can surface a deprecation warning.
  - Endpoints already present → left alone (user-customized tiers and
    enabled flags are preserved).

Usage:
    python3 ~/ora/scripts/refresh-direct-apis.py [all|anthropic|openai|google]
    python3 ~/ora/scripts/refresh-direct-apis.py --dry-run

Keys read from the same keychain entries _call_openai/_call_claude use:
    ora/anthropic-api-key
    ora/openai-api-key
    ora/gemini-api-key
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date

WORKSPACE      = os.path.expanduser("~/ora")
ROUTING_CONFIG = os.path.join(WORKSPACE, "config/routing-config.json")


# ── Keychain access ─────────────────────────────────────────────────────────

def _key(name: str) -> str:
    try:
        import keyring
        return keyring.get_password("ora", name) or ""
    except Exception:
        return os.environ.get(name.upper().replace("-", "_"), "")


# ── Tier heuristics ─────────────────────────────────────────────────────────
#
# Vendor names rev quickly — these patterns are forgiving on top-of-line
# variants ("opus-4-7", "opus-5", "opus-latest" all → premium). Unknown
# models default to "mid" so they're picker-visible without contaminating
# the premium bucket.

def _classify_anthropic(model_id: str) -> str:
    s = model_id.lower()
    if "opus"   in s: return "premium"
    if "sonnet" in s: return "mid"
    if "haiku"  in s: return "fast"
    return "mid"


def _classify_openai(model_id: str) -> str:
    s = model_id.lower()
    if re.match(r"^(o[1-9]\b|gpt-[5-9]\b|gpt-[5-9]\.\d+(?:-pro)?$)", s):
        return "premium"
    if "mini" in s or "turbo" in s or "3.5" in s:
        return "fast"
    if s.startswith("gpt-4o") or s.startswith("gpt-4-turbo") or s.startswith("gpt-5"):
        return "mid"
    return "mid"


def _classify_google(model_id: str) -> str:
    s = model_id.lower()
    if "lite" in s or "nano" in s: return "fast"
    if "pro"  in s and "flash" not in s: return "premium"
    if "flash" in s and "lite" not in s: return "mid"
    return "mid"


# ── Display-name fallback (when API doesn't provide one) ────────────────────

_GREEK_RE = re.compile(r"^[a-z]+-([0-9]+(?:\.[0-9]+)*)")

def _humanize_openai(model_id: str) -> str:
    """`gpt-5.4-thinking` → "GPT-5.4 Thinking"."""
    parts = model_id.replace("_", "-").split("-")
    out = []
    for p in parts:
        if p.lower() == "gpt":            out.append("GPT")
        elif p.startswith(("o", "O")) and len(p) <= 2 and p[1:].isdigit():
            out.append(p.upper())
        elif re.match(r"^\d", p):         out.append(p)
        else:                              out.append(p.capitalize())
    return " ".join(out)


# ── Provider fetchers ───────────────────────────────────────────────────────
#
# Each returns a list of canonical entries: {model_id, display_name}.
# Filtering for chat-class text models happens here (we skip embeddings,
# image, audio, etc. — those have their own pickers in the Visual tab).

def _http_json(url: str, headers: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# Models with these substrings are non-text variants; they belong in the
# Visual / Speech / Transcription tabs (built in later steps), not in the
# Buckets picker. Vendors keep adding more — keep this list current.
NON_TEXT_SUBSTRINGS = (
    "audio", "realtime", "transcribe", "-tts", "image",
    "search-api", "search-preview", "codex", "robotics", "computer-use",
    "whisper", "embedding", "dall-e",
)

# Date-suffix snapshots: `gpt-4o-2024-08-06`, `claude-opus-4-1-20250805`,
# `gpt-3-5-turbo-0125` (4-digit MMDD form). We keep the stable alias only
# — pinned versions clutter the picker and vendors rev them faster than
# humans want to track.
DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{8}$|-\d{4}$")


def _is_non_text(model_id: str) -> bool:
    """Non-text modality? (Not "is dated?" — dated pins are kept so
    existing endpoints with vendor-canonical pinned IDs still match.)"""
    s = model_id.lower()
    return any(needle in s for needle in NON_TEXT_SUBSTRINGS)


def fetch_anthropic() -> list[dict]:
    key = _key("anthropic-api-key")
    if not key:
        raise RuntimeError("No Anthropic key — run 'External APIs → Add new provider' in Ora.")
    data = _http_json(
        "https://api.anthropic.com/v1/models?limit=1000",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    models = []
    for m in data.get("data", []):
        mid = m.get("id") or ""
        if not mid.startswith("claude-"):
            continue
        if _is_non_text(mid):
            continue
        models.append({
            "model_id":     mid,
            "display_name": m.get("display_name") or mid,
        })
    return models


def fetch_openai() -> list[dict]:
    key = _key("openai-api-key")
    if not key:
        raise RuntimeError("No OpenAI key — run 'External APIs → Add new provider' in Ora.")
    data = _http_json(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    skip_prefixes = ("babbage", "davinci", "omni-moderation",
                     "text-embedding-", "tts-",
                     # gpt-3.5 family is pre-modern; users don't want it
                     # cluttering the picker. Both naming conventions:
                     "gpt-3.5", "gpt-3-5")
    skip_contains_strict = ("-instruct",)
    models = []
    for m in data.get("data", []):
        mid = m.get("id") or ""
        if any(mid.startswith(p) for p in skip_prefixes): continue
        if any(c in mid for c in skip_contains_strict):   continue
        if _is_non_text(mid):                              continue
        if not (mid.startswith("gpt-") or re.match(r"^o[1-9]", mid)): continue
        # Bare "gpt-4" (no -o, -1, -turbo) is legacy. Anything that
        # passes the modern-family check above without those qualifiers
        # is by definition the bare legacy model.
        if mid == "gpt-4":                                 continue
        models.append({
            "model_id":     mid,
            "display_name": _humanize_openai(mid),
        })
    return models


def fetch_google() -> list[dict]:
    key = _key("gemini-api-key")
    if not key:
        raise RuntimeError("No Google key — run 'External APIs → Add new provider' in Ora.")
    data = _http_json(
        f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key={key}",
        headers={},
    )
    models = []
    for m in data.get("models", []):
        name = m.get("name") or ""          # e.g. "models/gemini-2.5-pro"
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" not in methods: continue
        if "embedContent" in methods:        continue
        if "/gemini-" not in name:           continue
        short = name.split("/")[-1]
        if _is_non_text(short):              continue
        # Also strip Google's preview-suffix variants — `-customtools`,
        # `-preview-tts`, etc. (preview itself is kept; new flagships
        # often arrive there.)
        if "customtools" in short or "preview-tts" in short:
            continue
        models.append({
            "model_id":     name,            # keep the "models/..." prefix
            "display_name": m.get("displayName") or short,
        })
    return models


# ── Reconciliation ──────────────────────────────────────────────────────────

# How each provider name maps to the Ora endpoint fields.
PROVIDERS = {
    "anthropic": {
        "fetch":          fetch_anthropic,
        "service":        "claude",
        "provider":       "anthropic",
        "training":       "claude",
        "credential":     "ora/anthropic-api-key",
        "classifier":     _classify_anthropic,
        "id_prefix":      "anthropic-api",
        "display_suffix": " (API)",
        "vision_capable": True,
    },
    "openai": {
        "fetch":          fetch_openai,
        "service":        "openai",
        "provider":       "openai",
        "training":       "gpt",
        "credential":     "ora/openai-api-key",
        "classifier":     _classify_openai,
        "id_prefix":      "openai-api",
        "display_suffix": " (API)",
        "vision_capable": True,
    },
    "google": {
        "fetch":          fetch_google,
        "service":        "gemini",
        "provider":       "google",
        "training":       "gemini",
        "credential":     "ora/gemini-api-key",
        "classifier":     _classify_google,
        "id_prefix":      "gemini-api",
        "display_suffix": " (API)",
        "vision_capable": True,
    },
}


def _endpoint_id_for(model_id: str, prefix: str) -> str:
    """Stable, slug-safe endpoint id derived from the model id."""
    slug = model_id.lower()
    slug = slug.replace("models/", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{prefix}-{slug}"


def _base_alias(model_id: str) -> str:
    """Strip a trailing date pin so dated snapshots normalize to their stable
    alias. `claude-haiku-4-5-20251001` → `claude-haiku-4-5`."""
    return DATE_SUFFIX_RE.sub("", model_id)


def reconcile_provider(routing: dict, name: str, fetched: list[dict],
                       cred: dict) -> dict:
    """Apply one provider's fetched-models list to routing-config endpoints.

    Match strategy is order-independent and tolerates dated pins:
      1. Exact model_id match → kept.
      2. base_alias(existing.model_id) ∈ fetched_bases → kept (user pinned
         a stable model that the vendor still publishes).
      3. Otherwise → deprecated.

    New endpoints are only added for stable aliases (no date suffix) and
    only when neither the stable alias nor any existing endpoint already
    covers that model.

    Returns a per-provider summary: {added, restored, deprecated, kept}.
    """
    p = PROVIDERS[name]
    endpoints = routing.setdefault("endpoints", [])
    existing_for_service = [
        e for e in endpoints
        if e.get("type") == "api" and e.get("service") == p["service"]
        and e.get("model_id")
    ]

    # The fetched list now contains both stable aliases (no date suffix)
    # AND dated pins (since some vendors — notably Anthropic for non-current
    # families — only publish dated IDs). We use both for matching, and
    # only stable aliases for "new endpoint" candidates.
    fetched_ids   = {m["model_id"] for m in fetched}
    fetched_bases = {_base_alias(m["model_id"]) for m in fetched}

    # ── Pass 1: classify existing endpoints (kept / restored / deprecated)
    added, restored, kept, deprecated = [], [], [], []
    bases_covered_by_existing: set[str] = set()
    for ep in existing_for_service:
        mid  = ep.get("model_id") or ""
        base = _base_alias(mid)
        # Match if any of:
        #   - the exact id is still published
        #   - existing-base appears among fetched ids/bases (covers
        #     "existing has dated pin, fetched has stable alias of same base"
        #     and the symmetric case).
        if mid in fetched_ids or base in fetched_bases or base in fetched_ids:
            bases_covered_by_existing.add(base)
            if ep.get("status") == "deprecated":
                ep["status"] = "active"
                restored.append(ep.get("id"))
            else:
                kept.append(ep.get("id"))
        else:
            if ep.get("status") != "deprecated":
                ep["status"] = "deprecated"
                deprecated.append(ep.get("id"))

    # ── Pass 2: add stable aliases (no date suffix) the user doesn't
    # already cover. Dated pins are not added as new endpoints — picker
    # noise — but existing endpoints with dated model_ids are preserved.
    for m in fetched:
        mid  = m["model_id"]
        base = _base_alias(mid)
        if mid != base:
            continue
        if base in bases_covered_by_existing:
            continue

        endpoint_id = _endpoint_id_for(mid, p["id_prefix"])
        tier = p["classifier"](mid)
        bases_covered_by_existing.add(base)
        endpoints.append({
            "id":               endpoint_id,
            "type":             "api",
            "service":          p["service"],
            "model_id":         mid,
            "display_name":     (m["display_name"] or mid) + p["display_suffix"],
            "provider":         p["provider"],
            "training_family": p["training"],
            "tier":             tier,
            "status":           "active",
            "enabled":          True,
            "credential_key":  p["credential"],
            "verified":         str(date.today()),
            "capabilities": {
                "tool_access":         True,
                "file_system_access":  False,
                "web_access":          False,
                "retrieval_approach":  "pre-assembled",
            },
            "vision_capable":   p["vision_capable"],
            "_auto_discovered": True,
        })
        added.append(endpoint_id)

    return {"added": added, "restored": restored,
            "deprecated": deprecated, "kept": kept,
            "total_after": len([e for e in endpoints if e.get("service") == p["service"]])}


def _load_routing() -> dict:
    with open(ROUTING_CONFIG) as f:
        return json.load(f)


def _save_routing(cfg: dict):
    with open(ROUTING_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("provider", nargs="?", default="all",
                   choices=["all", "anthropic", "openai", "google"])
    p.add_argument("--dry-run", action="store_true",
                   help="Print summary; don't write routing-config.json.")
    args = p.parse_args()

    routing = _load_routing()
    targets = (["anthropic", "openai", "google"] if args.provider == "all"
               else [args.provider])

    summaries = {}
    for name in targets:
        try:
            fetched = PROVIDERS[name]["fetch"]()
        except urllib.error.HTTPError as e:
            print(f"[refresh-direct-apis] {name}: HTTP {e.code} — {e.reason}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[refresh-direct-apis] {name}: {e}", file=sys.stderr)
            continue
        summaries[name] = reconcile_provider(routing, name, fetched, {})

    # Print summary
    for name, s in summaries.items():
        print(f"\n[{name}]")
        print(f"  total endpoints after refresh: {s['total_after']}")
        print(f"  added:      {len(s['added'])}  {s['added'] or ''}")
        print(f"  restored:   {len(s['restored'])}  {s['restored'] or ''}")
        print(f"  deprecated: {len(s['deprecated'])}  {s['deprecated'] or ''}")
        print(f"  unchanged:  {len(s['kept'])}")

    if args.dry_run:
        print("\n[refresh-direct-apis] dry-run — routing-config.json untouched")
        return

    if summaries:
        _save_routing(routing)
        print(f"\n[refresh-direct-apis] wrote {ROUTING_CONFIG}")


if __name__ == "__main__":
    main()
