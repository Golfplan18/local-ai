"""model_registry — runtime reader for the curated model registry.

The registry at ``config/model-registry.json`` is the source of truth
for model capabilities (vision_capable, context_length, intelligence_score,
pricing) — populated by ``scripts/sync_model_registry.py`` from
OpenRouter, LiteLLM, Chatbot Arena, and an empirical probe.

This module exposes one thin reader and one overlay function. Boot.py
loads the routing-config, then calls ``overlay_routing_config`` to
merge registry values onto each endpoint dict — so the rest of the
pipeline sees corrected capability flags through the same dict shape
it already uses, with zero call-site changes.

When the registry is missing or malformed, the overlay is a no-op and
the pipeline falls back to whatever ``routing-config.json`` declares.
This means a fresh-clone install works even before any sync has run
(though it'll have stale capability flags until the first sync lands).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
REGISTRY_PATH = ORA_HOME / "config" / "model-registry.json"

# Cached registry — load once at startup, refreshed by `reload()`.
# Read access is wrapped in a lock-free pattern: writes replace the
# whole dict atomically, readers see a consistent snapshot.
_registry: dict | None = None
_load_lock = threading.Lock()


def load_registry(force: bool = False) -> dict:
    """Return the parsed registry dict.

    Reads `config/model-registry.json` on first call (or when
    ``force=True``). Returns the empty registry shape ``{"$schema_version":
    1, "models": {}}`` when the file is missing or unreadable — so
    callers can rely on the structure regardless of install state.
    """
    global _registry
    if _registry is not None and not force:
        return _registry
    with _load_lock:
        if _registry is not None and not force:
            return _registry
        registry = _empty_registry()
        if REGISTRY_PATH.exists():
            try:
                with open(REGISTRY_PATH) as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("models"), dict):
                    registry = data
            except (OSError, json.JSONDecodeError):
                # Malformed or unreadable — fall back to empty.
                # Caller's overlay becomes a no-op; routing-config wins.
                pass
        _registry = registry
        return _registry


def reload() -> dict:
    """Force a re-read of the registry file. Returns the new registry."""
    return load_registry(force=True)


def lookup(model_id: str) -> dict | None:
    """Return the registry entry for a model id, or None when not found."""
    if not model_id:
        return None
    return load_registry().get("models", {}).get(model_id)


def vision_capable(model_id: str, default: Any = None) -> Any:
    """Return the registry's authoritative vision_capable value for a
    model id, or ``default`` when the registry has no entry / the field
    is null. Most callers should pass the routing-config's existing flag
    as the default so the overlay degrades gracefully."""
    entry = lookup(model_id)
    if entry is None:
        return default
    val = entry.get("vision_capable")
    return val if val is not None else default


def intelligence_score(model_id: str) -> float | None:
    """Return the Chatbot Arena ELO for a model id, or None."""
    entry = lookup(model_id)
    if entry is None:
        return None
    return entry.get("intelligence_score")


def overlay_routing_config(rc: dict) -> dict:
    """Mutate-and-return a routing-config dict, overlaying registry
    values onto each endpoint's capability fields.

    Currently overlays:
      vision_capable — registry's empirically-verified value overrides
                       the routing-config flag (the source of the
                       2026-05-20 kimi-k2.6 bug).
      intelligence_score — added as a new endpoint field for downstream
                       consumers that want to rank-order models.

    The mutation is in-place AND returned for fluent style. No-ops
    when the registry is empty or the routing-config doesn't have an
    `endpoints` list.
    """
    registry = load_registry()
    models = registry.get("models") or {}
    if not models:
        return rc
    endpoints = rc.get("endpoints")
    if not isinstance(endpoints, list):
        return rc
    overlaid = 0
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        model_id = ep.get("id") or ep.get("model_id") or ep.get("model")
        if not model_id:
            continue
        reg = models.get(model_id)
        if reg is None:
            continue
        # Vision capability: registry wins when it has a non-null value.
        vc = reg.get("vision_capable")
        if vc is not None:
            ep["vision_capable"] = vc
            ep["_vision_capable_source"] = reg.get("vision_verified_by")
        # Intelligence score: add if available.
        intel = reg.get("intelligence_score")
        if intel is not None:
            ep["intelligence_score"] = intel
            ep["intelligence_rank"] = reg.get("intelligence_rank")
        overlaid += 1
    rc["_registry_overlaid_count"] = overlaid
    return rc


def stats() -> dict:
    """Return a small dict summarising the loaded registry — useful
    for the server's health / status surface."""
    registry = load_registry()
    models = registry.get("models") or {}
    total = len(models)
    vc_true = sum(1 for m in models.values() if m.get("vision_capable") is True)
    vc_false = sum(1 for m in models.values() if m.get("vision_capable") is False)
    vc_null = total - vc_true - vc_false
    intel = sum(1 for m in models.values() if m.get("intelligence_score") is not None)
    return {
        "registry_path": str(REGISTRY_PATH),
        "loaded": total > 0,
        "model_count": total,
        "vision_capable_true": vc_true,
        "vision_capable_false": vc_false,
        "vision_capable_null": vc_null,
        "intelligence_score_count": intel,
        "generated_at": registry.get("generated_at"),
        "last_probe_at": registry.get("last_probe_at"),
    }


def _empty_registry() -> dict:
    return {
        "$schema_version": 1,
        "generated_at": None,
        "model_count": 0,
        "models": {},
    }


__all__ = [
    "load_registry",
    "reload",
    "lookup",
    "vision_capable",
    "intelligence_score",
    "overlay_routing_config",
    "stats",
]
