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
import json
from pathlib import Path

import keyring


ORA = Path(__file__).resolve().parent.parent
CATALOG_PATH = ORA / "config" / "model-catalog.json"
ROUTING_PATH = ORA / "config" / "routing-config.json"
REGISTRY_PATH = ORA / "config" / "model-registry.json"


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


def main() -> int:
    catalog = json.loads(CATALOG_PATH.read_text())
    routing = json.loads(ROUTING_PATH.read_text())

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

    routing["endpoints"] = list(by_id.values())

    # Atomic replace: this script now runs from the server's registry
    # refresh while threaded Flask handlers read (and occasionally
    # write) routing-config.json — a torn read of a half-written file
    # must not be possible. (Last-writer-wins races with /config POSTs
    # remain; the window is the subprocess's ~0.5s runtime.)
    import os
    tmp_path = str(ROUTING_PATH) + ".tmp"
    Path(tmp_path).write_text(json.dumps(routing, indent=2) + "\n")
    os.replace(tmp_path, ROUTING_PATH)

    print(f"Catalog text-output models:  {len(text_models)}")
    print(f"Endpoints added:             {added}")
    print(f"Endpoints overwritten:       {overwritten}")
    print(f"  via direct vendor API:     {direct_count}")
    print(f"  via OpenRouter:            {openrouter_count}")
    print(f"Total endpoints after sync:  {len(routing['endpoints'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
