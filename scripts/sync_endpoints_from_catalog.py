#!/usr/bin/env python3
"""Sync routing-config.json endpoints from model-catalog.json.

For each text-output catalog model:
  - Generate one endpoint with id == catalog id.
  - If provider in (openai, anthropic, google) AND vendor API key in keyring,
    use direct service with stripped model name + openrouter_fallback_model_id.
  - Else use openrouter.

Overwrites any existing routing-config entry with the same ID (catalog is
canonical). Preserves all other entries (legacy flat IDs, local MLX).

Run after the Models pane changes the catalog so the pipeline's endpoint
universe stays in sync with what the UI offers.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import keyring


ORA = Path(__file__).resolve().parent.parent
CATALOG_PATH = Path(
    os.environ.get("ORA_MODEL_CATALOG_PATH")
    or (ORA / "config" / "model-catalog.json")
)
ROUTING_PATH = Path(
    os.environ.get("ORA_ROUTING_CONFIG_PATH")
    or (ORA / "config" / "routing-config.json")
)
ROUTING_SEED_PATH = ORA / "config" / "routing-config.json"
REGISTRY_PATH = Path(
    os.environ.get("ORA_MODEL_REGISTRY_PATH")
    or (ORA / "config" / "model-registry.json")
)
VENDOR_AUTH_PATH = Path(
    os.environ.get("ORA_VENDOR_AUTH_REGISTRY_PATH")
    or (ORA / "config" / "model-registry.vendor-authoritative.json")
)
CONFIGURATIONS_DIR = Path(
    os.environ.get("ORA_CONFIGURATIONS_DIR")
    or (ORA / "config" / "configurations")
)

sys.path.insert(0, str(ORA / "orchestrator"))
try:
    import provider_registry as _preg
    import vendor_catalog_registry as _vcr
except Exception:  # pragma: no cover
    _preg = None
    _vcr = None


def load_vendor_listed() -> dict:
    """Map model id → vendor_listed verdict from the registry's
    vendor-direct audit (True / False / None=not audited)."""
    try:
        reg = json.loads(REGISTRY_PATH.read_text())
    except Exception:
        return {}
    return {
        mid: m.get("vendor_listed")
        for mid, m in (reg.get("models") or {}).items()
    }


DIRECT_SERVICES = {
    "openai":    {"service": "openai", "keyring_name": "openai-api-key"},
    "anthropic": {"service": "claude", "keyring_name": "anthropic-api-key"},
    "google":    {"service": "gemini", "keyring_name": "gemini-api-key"},
}


_KEY_CACHE: dict[str, bool] = {}


def has_key(name: str) -> bool:
    # Memoized: called once per direct-eligible catalog model (~100+),
    # but there are only 3 distinct keys — each keyring lookup is a
    # macOS security-framework IPC round-trip, and a locked Keychain
    # can stall each one.
    if name not in _KEY_CACHE:
        try:
            _KEY_CACHE[name] = bool(keyring.get_password("ora", name))
        except Exception:
            _KEY_CACHE[name] = False
    return _KEY_CACHE[name]


def strip_vendor(catalog_id: str) -> str:
    return catalog_id.split("/", 1)[1] if "/" in catalog_id else catalog_id


def direct_model_name(provider: str, catalog_id: str) -> str:
    stripped = strip_vendor(catalog_id)
    if provider == "anthropic":
        # Anthropic API uses dashes throughout: claude-opus-4.7 → claude-opus-4-7
        return stripped.replace(".", "-")
    if provider == "google":
        # Gemini API expects the "models/" prefix
        return f"models/{stripped}"
    return stripped


def build_endpoint(model: dict, vendor_listed: dict | None = None) -> dict:
    cid = model["id"]
    provider = model.get("provider", "")
    vision = bool(model.get("vision_capable", False))
    context = model.get("context_window") or 0

    ep = {
        "id": cid,
        "type": "api",
        "status": "active",
        "enabled": True,
        "provider": provider,
        "display_name": model.get("display_name", cid),
        "context_window": context,
        "vision_capable": vision,
        "capabilities": {
            "tool_access": True,
            "file_system_access": False,
            "web_access": True,
            "retrieval_approach": "pre-assembled",
        },
        "openrouter_pricing": model.get("openrouter_pricing") or {},
        "tier": model.get("family_tier") or "",
        "is_free": bool(model.get("is_free", False)),
    }

    # Direct dispatch requires (a) the vendor's API key, and (b) the
    # registry's vendor audit NOT having confirmed the id is absent from
    # the vendor's own /models list. OpenRouter-only variants (e.g.
    # anthropic/claude-opus-4.8-fast, google/...-customtools) carry
    # vendor_listed=False — dispatching those direct guarantees a 404 +
    # per-call fallback round-trip, so they route straight to OpenRouter.
    # vendor_listed=None (audit unavailable) still allows direct.
    listed = (vendor_listed or {}).get(cid)
    direct = DIRECT_SERVICES.get(provider)
    if direct and has_key(direct["keyring_name"]) and listed is not False:
        ep["service"] = direct["service"]
        ep["model_id"] = direct_model_name(provider, cid)
        ep["openrouter_fallback_model_id"] = cid
        ep["dispatch"] = "direct"
    else:
        ep["service"] = "openrouter"
        ep["model_id"] = cid
        ep["dispatch"] = "openrouter"

    return ep


def _read_routing_config() -> dict:
    path = ROUTING_PATH if ROUTING_PATH.exists() else ROUTING_SEED_PATH
    return json.loads(path.read_text())


# ── vendor-catalogue-authoritative path (flag-gated) ─────────────────────────

def build_direct_endpoint(entry: dict) -> dict:
    """Build a direct endpoint from a vendor-authoritative native entry.

    The model id is the vendor's OWN native id (from its /models) — no strip /
    guess — so dispatch needs no translation. Native vendors (Anthropic / OpenAI
    / Google) use their service; the rest use the generic openai_compatible
    branch keyed by base_url + credential_key.
    """
    vid = entry["vendor"]
    p = (_preg.by_id(vid) if _preg else None) or {}
    nid = entry["native_model_id"]
    ep = {
        "id": entry["id"],
        "type": "api",
        "status": "active",
        "enabled": True,
        "provider": vid,
        "display_name": entry.get("display_name") or nid,
        "context_window": entry.get("context_length") or 0,
        "vision_capable": bool(entry.get("vision_capable") or entry.get("vision")),
        "capabilities": {
            "tool_access": True,
            "file_system_access": False,
            "web_access": True,
            "retrieval_approach": "pre-assembled",
        },
        "tier": entry.get("tier") or "",
        "is_free": False,
        "model_id": nid,
        "dispatch": "direct",
        "credential_key": f"ora/{p.get('keyring_username', vid + '-api-key')}",
    }
    if p.get("dispatch") == "native":
        ep["service"] = p.get("native_service")
    else:
        ep["service"] = vid                    # generic openai_compatible service id
        ep["base_url"] = p.get("base_url")
    # carry display metadata the picker (PR-C) will surface
    if entry.get("pricing"):
        ep["vendor_pricing"] = entry["pricing"]
    if entry.get("intelligence_index") is not None:
        ep["intelligence_index"] = entry["intelligence_index"]
    if entry.get("output_tokens_per_second") is not None:
        ep["tokens_per_second"] = entry["output_tokens_per_second"]
    return ep


def build_supplement_endpoint(entry: dict) -> dict:
    """OpenRouter endpoint for a KEPT supplement model — a :free tier or an
    allow-listed open model the native API doesn't serve. Dispatches via
    OpenRouter using the full OR id (no direct key / markup applies; :free is
    free). The inversion removed these, so they must be re-added."""
    orid = entry["id"]
    return {
        "id": orid,
        "type": "api",
        "status": "active",
        "enabled": True,
        "provider": orid.split("/", 1)[0],
        "display_name": entry.get("display_name") or orid,
        "context_window": entry.get("context_length") or 0,
        "vision_capable": bool(entry.get("vision_capable")),
        "capabilities": {
            "tool_access": True,
            "file_system_access": False,
            "web_access": True,
            "retrieval_approach": "pre-assembled",
        },
        "tier": entry.get("tier") or "",
        "is_free": bool(entry.get("is_free") or orid.endswith(":free")),
        "model_id": orid,
        "service": "openrouter",
        "supplement": True,
    }


def _referenced_text(routing: dict) -> str:
    """Everything an endpoint id could be *referenced* from (slots,
    slot_assignments, configurations, …) — so a still-used OpenRouter endpoint
    is kept as a dispatchable legacy rather than silently removed."""
    parts = []
    r = dict(routing)
    r.pop("endpoints", None)
    parts.append(json.dumps(r))
    if CONFIGURATIONS_DIR.is_dir():
        for f in CONFIGURATIONS_DIR.glob("*.json"):
            try:
                parts.append(f.read_text())
            except Exception:
                pass
    return "\n".join(parts)


def apply_vendor_authoritative(by_id: dict, routing: dict) -> dict:
    """When the flag is on: replace each catalogue-authoritative vendor's
    OpenRouter endpoints with its native direct endpoints. Referenced OR
    endpoints are kept (dispatchable legacy); unreferenced ones are removed."""
    if not (_vcr and _preg):
        return {"skipped": "registry modules unavailable"}
    if not VENDOR_AUTH_PATH.exists():
        return {"skipped": "no vendor-authoritative artifact (run "
                           "build_vendor_authoritative_registry.py first)"}
    models = json.loads(VENDOR_AUTH_PATH.read_text()).get("models") or {}
    natives = _vcr.native_direct_entries(models)
    if not natives:
        return {"skipped": "artifact has no native direct entries"}

    native_eps = {e["id"]: build_direct_endpoint(e) for e in natives}
    # Supplement = OpenRouter-only models kept for a native vendor (:free tiers +
    # allow-listed open models). Keep their endpoints if present and ADD any the
    # inversion previously removed, so they stay dispatchable via OpenRouter.
    supplement_eps = {e["id"]: build_supplement_endpoint(e) for e in models.values()
                      if isinstance(e, dict) and e.get("supplement") and e.get("id")}
    supplement_ids = set(supplement_eps)
    auth_vendors = {e["vendor"] for e in natives}
    prefix_to_vendor = {}
    for vid in auth_vendors:
        for pfx in _vcr._prefixes(vid):
            prefix_to_vendor[pfx] = vid
    ref = _referenced_text(routing)

    def _vendor_of(eid, ep):
        p = (ep.get("provider") or "").lstrip("~")
        if p in auth_vendors:
            return p
        if p in prefix_to_vendor:           # provider field is an OpenRouter prefix
            return prefix_to_vendor[p]
        if "/" in (eid or ""):
            head = eid.split("/", 1)[0].lstrip("~")
            if head.startswith("openrouter:"):   # openrouter:google/... dispatch shape
                head = head[len("openrouter:"):]
            return prefix_to_vendor.get(head)
        return None

    removed, kept_legacy = [], []
    for eid in list(by_id.keys()):
        if eid in native_eps:
            continue
        ep = by_id[eid]
        # Only de-dup OpenRouter API endpoints. Never touch local MLX, native
        # direct, or subscription endpoints — even if they're the same vendor
        # family (e.g. a local Qwen model).
        if ep.get("type") != "api" or ep.get("service") != "openrouter":
            continue
        if _vendor_of(eid, ep) in auth_vendors:
            if eid in supplement_ids:
                continue                          # kept supplement — leave in place
            # Reference test on the WHOLE quoted JSON token, not a raw substring
            # — otherwise `minimax/minimax-m2` looks "referenced" merely because
            # `minimax/minimax-m2.5` is, and a dead endpoint survives the de-dup.
            if ('"' + eid + '"') in ref or ('"openrouter:' + eid + '"') in ref:
                kept_legacy.append(eid)
            else:
                del by_id[eid]
                removed.append(eid)
    for eid, ep in native_eps.items():
        by_id[eid] = ep
    added_supp = []
    for eid, ep in supplement_eps.items():
        existing = by_id.get(eid)
        # add if missing (inversion dropped it), or fix a stale non-OpenRouter
        # endpoint on a supplement id (a :free tier can't dispatch via a native
        # service). Leave a correct existing openrouter endpoint untouched.
        if existing is None or existing.get("service") != "openrouter":
            by_id[eid] = ep
            added_supp.append(eid)

    return {
        "authoritative_vendors": sorted(auth_vendors),
        "native_endpoints_added": len(native_eps),
        "openrouter_removed": len(removed),
        "openrouter_supplement_total": len(supplement_ids),
        "openrouter_supplement_added": len(added_supp),
        "kept_legacy_referenced": kept_legacy,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print the diff and write nothing")
    args = ap.parse_args()

    catalog = json.loads(CATALOG_PATH.read_text())
    routing = _read_routing_config()

    models = catalog.get("models", [])
    text_models = [
        m for m in models if "text" in (m.get("output_modalities") or [])
    ]

    vendor_listed = load_vendor_listed()
    catalog_endpoints = {
        m["id"]: build_endpoint(m, vendor_listed) for m in text_models
    }

    existing = routing.get("endpoints", [])
    by_id = {(e.get("id") or e.get("name")): e for e in existing}

    overwritten = 0
    added = 0
    direct_count = 0
    openrouter_count = 0
    for cid, new_ep in catalog_endpoints.items():
        if cid in by_id:
            overwritten += 1
        else:
            added += 1
        if new_ep["dispatch"] == "direct":
            direct_count += 1
        else:
            openrouter_count += 1
        by_id[cid] = new_ep

    # Vendor-catalogue-authoritative inversion (flag-gated, default off): replace
    # each keyed authoritative vendor's OpenRouter endpoints with its native
    # direct endpoints. No-op unless ORA_VENDOR_CATALOG_AUTHORITATIVE is on.
    va = {"skipped": "flag off"}
    if _vcr and _vcr.enabled():
        va = apply_vendor_authoritative(by_id, routing)

    routing["endpoints"] = list(by_id.values())

    if args.dry_run:
        print("DRY RUN — nothing written.")
    else:
        # Atomic replace: this script runs from the server's registry refresh
        # while threaded Flask handlers read (and occasionally write)
        # routing-config.json — a torn read of a half-written file must not be
        # possible. (Last-writer-wins races with /config POSTs remain; the
        # window is the subprocess's ~0.5s runtime.)
        ROUTING_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = str(ROUTING_PATH) + ".tmp"
        Path(tmp_path).write_text(json.dumps(routing, indent=2) + "\n")
        os.replace(tmp_path, ROUTING_PATH)

    print(f"Catalog text-output models:  {len(text_models)}")
    print(f"Endpoints added:             {added}")
    print(f"Endpoints overwritten:       {overwritten}")
    print(f"  via direct vendor API:     {direct_count}")
    print(f"  via OpenRouter:            {openrouter_count}")
    if _vcr and _vcr.enabled():
        if "skipped" in va:
            print(f"Vendor-authoritative:        SKIPPED ({va['skipped']})")
        else:
            print(f"Vendor-authoritative ON:     {', '.join(va['authoritative_vendors'])}")
            print(f"  native direct endpoints:   {va['native_endpoints_added']}")
            print(f"  OpenRouter removed:        {va['openrouter_removed']}")
            print(f"  kept legacy (referenced):  {len(va['kept_legacy_referenced'])}"
                  + (f" → {va['kept_legacy_referenced'][:8]}" if va['kept_legacy_referenced'] else ""))
    print(f"Total endpoints after sync:  {len(routing['endpoints'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
