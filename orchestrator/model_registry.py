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

try:
    from . import runtime_paths as rp
except ImportError:  # direct script-style import from sys.path
    import runtime_paths as rp  # type: ignore

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
REGISTRY_PATH = ORA_HOME / "config" / "model-registry.json"
_DEFAULT_REGISTRY_PATH = REGISTRY_PATH


def _registry_path() -> Path:
    if REGISTRY_PATH != _DEFAULT_REGISTRY_PATH:
        return Path(REGISTRY_PATH)
    return rp.model_registry_path()

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
        registry_path = _registry_path()
        if registry_path.exists():
            try:
                with open(registry_path) as f:
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


def aa_intelligence_index(model_id: str) -> float | None:
    """Return Artificial Analysis's intelligence_index (0-100 scale)
    for a model, or None when AA doesn't list it. Used as a fallback
    ranking metric when Chatbot Arena ELO is unavailable — see the
    coverage audit notes in scripts/sync_model_registry.py."""
    entry = lookup(model_id)
    if entry is None:
        return None
    return entry.get("aa_intelligence_index")


def latency_ttft_seconds(model_id: str) -> float | None:
    """Return Artificial Analysis's median time-to-first-token (seconds)
    for a model, or None when not measured. Useful for selecting
    interactive-feel models — lower is better."""
    entry = lookup(model_id)
    if entry is None:
        return None
    return entry.get("latency_ttft_seconds")


def output_tokens_per_second(model_id: str) -> float | None:
    """Return AA's median output throughput (tokens/sec) for a model,
    or None when not measured. Higher is better; useful for ranking
    when generating long outputs."""
    entry = lookup(model_id)
    if entry is None:
        return None
    return entry.get("output_tokens_per_second")


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
        # AA intelligence + latency + throughput fields — surface for
        # model-selection UI even when Chatbot Arena ELO isn't present.
        if reg.get("aa_intelligence_index") is not None:
            ep["aa_intelligence_index"] = reg["aa_intelligence_index"]
        if reg.get("latency_ttft_seconds") is not None:
            ep["latency_ttft_seconds"] = reg["latency_ttft_seconds"]
        if reg.get("latency_total_seconds") is not None:
            ep["latency_total_seconds"] = reg["latency_total_seconds"]
        if reg.get("output_tokens_per_second") is not None:
            ep["output_tokens_per_second"] = reg["output_tokens_per_second"]
        overlaid += 1
    rc["_registry_overlaid_count"] = overlaid
    return rc


def compute_picks(configurations_dir: Path | None = None) -> dict:
    """Return the set of model ids that earn the PICK badge.

    A model earns PICK if it appears as a ``primary`` or in any
    ``fallback`` list inside any configuration file under
    ``config/configurations/``. The intent is that the four preset
    configurations (premium / optimum / budget / free) live on disk;
    the PICK set is the union of every preset's primary + fallback
    picks across every slot.

    ``vision_substitute`` ids are NOT included — vision substitute is a
    text-to-vision fallback for the image-input path, not a primary
    recommendation, and surfacing it as PICK would dilute the badge.

    When fewer than four preset files exist (fresh install, before the
    refresh trigger has baked them), the PICK set is necessarily
    smaller. The UI shows the PICK badge on whatever's currently
    derivable; the registry refresh trigger (Chunk 10 step 14) is what
    populates the four preset files so the badge reaches its expected
    ~40-60 distinct models (~12-17% of a 358-model registry).

    Returns a dict with:
      ``picks``: sorted list of model ids (stable for diffing)
      ``by_model``: per-model endorsement detail (preset_lineages +
                    configurations seen in)
      ``configurations_scanned``: filenames considered
      ``configurations_dir``: absolute path that was scanned
    """
    configuration_files: list[Path] = []
    if configurations_dir is None:
        by_stem: dict[str, Path] = {}
        for directory in rp.configuration_dirs_for_read():
            if directory.exists():
                for path in sorted(directory.glob("*.json")):
                    by_stem[path.stem] = path
        configuration_files = [by_stem[k] for k in sorted(by_stem)]
        configurations_dir_label = " + ".join(
            str(d) for d in rp.configuration_dirs_for_read() if d.exists()
        )
    else:
        configurations_dir_label = str(configurations_dir)
        if configurations_dir.exists():
            configuration_files = sorted(configurations_dir.glob("*.json"))

    by_model: dict[str, dict] = {}
    scanned: list[str] = []

    if not configuration_files:
        return {
            "picks": [],
            "by_model": {},
            "configurations_scanned": [],
            "configurations_dir": configurations_dir_label,
        }

    for path in configuration_files:
        try:
            with open(path) as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError):
            # Malformed file — skip silently. The endpoint reports
            # the list of files actually scanned so callers can spot
            # the gap if they need to.
            continue
        if not isinstance(config, dict):
            continue
        scanned.append(path.name)
        lineage = config.get("preset_lineage")
        for model_id in _walk_config_for_picks(config.get("cells") or {}):
            entry = by_model.setdefault(model_id, {
                "preset_lineages": [],
                "configurations": [],
            })
            if lineage and lineage not in entry["preset_lineages"]:
                entry["preset_lineages"].append(lineage)
            if path.name not in entry["configurations"]:
                entry["configurations"].append(path.name)

    return {
        "picks": sorted(by_model.keys()),
        "by_model": by_model,
        "configurations_scanned": scanned,
        "configurations_dir": configurations_dir_label,
    }


def _walk_config_for_picks(cells) -> set:
    """Walk a configuration's nested cells structure and collect every
    model id that appears as a ``primary`` or in a ``fallback`` list.

    The cells dict has variable depth (utility cells are flat;
    analysis splits into gear3/gear4; post_analysis is flat again).
    We recurse on dicts until we find a slot dict — recognised by the
    presence of a ``primary`` key — and harvest from there.
    """
    found: set = set()

    def visit(node):
        if not isinstance(node, dict):
            return
        if "primary" in node:
            # Slot dict — harvest primary + fallback. vision_substitute
            # deliberately excluded (see compute_picks docstring).
            primary = node.get("primary")
            if primary:
                found.add(primary)
            for f in (node.get("fallback") or []):
                if f:
                    found.add(f)
            return
        # Nested category dict — recurse.
        for v in node.values():
            visit(v)

    visit(cells)
    return found


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
        "registry_path": str(_registry_path()),
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
    "compute_picks",
    "stats",
]
