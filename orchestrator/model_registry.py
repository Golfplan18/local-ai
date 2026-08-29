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

# A genuinely unknown model window must not inherit the largest window Ora
# commonly routes.  This is an admission floor, not a claim about the model.
CONSERVATIVE_ADMISSION_CONTEXT_WINDOW = 32_000
# Compatibility name for callers that need the shared unknown-capacity value.
DEFAULT_CONTEXT_WINDOW = CONSERVATIVE_ADMISSION_CONTEXT_WINDOW
CONTEXT_CAPACITY_KEYS = ("context_window", "context_length", "max_context_length")


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _identifier_forms(value: object) -> set[str]:
    """Return safe exact/alias forms for a model identifier.

    The registry contains OpenRouter ids while runtime endpoints may carry a
    provider-native label (for example ``MiniMax-M3``), a leading ``~`` or an
    unpinned ``-latest`` alias. These forms are identity-preserving aliases;
    this helper deliberately does not fuzzy-match model families.
    """
    if not isinstance(value, str) or not value.strip():
        return set()
    raw = value.strip()
    if raw.lower().startswith("openrouter:"):
        raw = raw.split(":", 1)[1].strip()
    raw = raw.lstrip("~")
    forms = {raw.casefold()}
    if "/" in raw:
        forms.add(raw.rsplit("/", 1)[1].casefold())
    if raw.casefold().endswith("-latest"):
        base = raw[:-len("-latest")]
        forms.add(base.casefold())
        if "/" in base:
            forms.add(base.rsplit("/", 1)[1].casefold())
    return forms


def _exact_identifier(value: object) -> str | None:
    """Return the unexpanded, case-insensitive form of an exact model id."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.lower().startswith("openrouter:"):
        raw = raw.split(":", 1)[1].strip()
    return raw.casefold() or None


def _alias_resolution_identifier(value: object) -> object:
    """Normalize the explicit ``~``/``-latest`` alias to its base id."""
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    if raw.lower().startswith("openrouter:"):
        raw = raw.split(":", 1)[1].strip()
    raw = raw.lstrip("~")
    if raw.casefold().endswith("-latest"):
        raw = raw[:-len("-latest")]
    return raw


def _record_identifiers(record: dict, key: str) -> set[str]:
    values: list[object] = [key]
    for field in ("id", "model_id", "native_model_id"):
        values.append(record.get(field))
    aliases = record.get("also_known_as") or []
    if isinstance(aliases, (list, tuple, set)):
        values.extend(aliases)
    else:
        values.append(aliases)
    provenance = record.get("_provenance") or {}
    if isinstance(provenance, dict):
        for source in provenance.values():
            if not isinstance(source, dict):
                continue
            for field in ("lookup_key", "model_id", "aa_name", "name"):
                values.append(source.get(field))
    forms: set[str] = set()
    for value in values:
        forms.update(_identifier_forms(value))
    return forms


def _matching_registry_records(model_id: str | None) -> list[dict]:
    """Return every registry record matching an exact id or declared alias."""
    requested = _identifier_forms(model_id)
    if not requested:
        return []
    models = load_registry().get("models") or {}
    # Prefer exact ids before considering provider-less leaves and declared
    # aliases. An exact qualified id is authoritative even when another
    # record happens to advertise the same provider-native alias.
    exact_requested = _exact_identifier(model_id)
    if exact_requested:
        exact_matches = []
        for key, record in models.items():
            if not isinstance(record, dict):
                continue
            exact_values = [
                key,
                record.get("id"),
                record.get("model_id"),
                record.get("native_model_id"),
            ]
            if any(_exact_identifier(value) == exact_requested
                   for value in exact_values):
                if all(record is not existing for existing in exact_matches):
                    exact_matches.append(record)
        if exact_matches:
            return exact_matches

    matches = [
        record for key, record in models.items()
        if isinstance(record, dict) and requested.intersection(
            _record_identifiers(record, key))
    ]
    unique_matches = []
    for record in matches:
        if all(record is not existing for existing in unique_matches):
            unique_matches.append(record)
    return unique_matches


def lookup(model_id: str | None) -> dict | None:
    """Return the registry record for an exact or unique declared alias."""
    matches = _matching_registry_records(model_id)
    return matches[0] if len(matches) == 1 else None


def model_ids_equivalent(left: str | None, right: str | None) -> bool:
    """Whether two runtime ids are the same exact/declared model alias."""
    left_matches = _matching_registry_records(_alias_resolution_identifier(left))
    right_matches = _matching_registry_records(_alias_resolution_identifier(right))
    if len(left_matches) > 1 or len(right_matches) > 1:
        return False
    if len(left_matches) == 1 and len(right_matches) == 1:
        return left_matches[0] is right_matches[0]
    left_forms = _identifier_forms(left)
    right_forms = _identifier_forms(right)
    return bool(left_forms and right_forms and left_forms.intersection(right_forms))


def context_window_for_model(
    model_id: str | None, default: int = DEFAULT_CONTEXT_WINDOW,
) -> int:
    """Return registry context capacity for a model, or ``default``."""
    record = lookup(model_id)
    if not record:
        return default
    for key in CONTEXT_CAPACITY_KEYS:
        capacity = _positive_int(record.get(key))
        if capacity is not None:
            return capacity
    provenance = record.get("_provenance") or {}
    candidates: list[int] = []
    if isinstance(provenance, dict):
        for source in provenance.values():
            if isinstance(source, dict):
                candidates.extend(
                    _positive_int(source.get(key))
                    for key in ("max_input_tokens", "context_length")
                )
    capacities = [value for value in candidates if value is not None]
    # When sources disagree and the curated top-level record has not resolved
    # the discrepancy, admit only the smallest declared window.
    return min(capacities, default=default)


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




def overlay_routing_config(rc: dict) -> dict:
    """Mutate-and-return a routing-config dict, overlaying registry
    values onto each endpoint's capability fields.

    Currently overlays:
      vision_capable — registry's empirically-verified value overrides
                       the routing-config flag (the source of the
                       2026-05-20 kimi-k2.6 bug).
      context_window — registry/catalog capacity fills a missing endpoint
                       value while preserving any explicit capacity value.
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
        reg = None
        registry_model_id = None
        # Endpoint ``id`` is sometimes only Ora's transport handle (for
        # example ``openai-api-gpt4o``).  Keep walking until an identifier
        # actually resolves instead of letting that handle hide the canonical
        # provider model id carried beside it.
        for identifier in (ep.get("id"), ep.get("model_id"), ep.get("model")):
            if not identifier:
                continue
            candidate = lookup(str(identifier))
            if candidate is not None:
                reg = candidate
                registry_model_id = str(identifier)
                break
        if reg is None:
            continue
        registry_capacity = context_window_for_model(
            registry_model_id, default=DEFAULT_CONTEXT_WINDOW)
        declared_capacities = [
            _positive_int(ep.get(key)) for key in CONTEXT_CAPACITY_KEYS
        ]
        capacities = [value for value in declared_capacities if value is not None]
        # Keep an explicit endpoint capacity truthful, including a smaller
        # value. MSI analysis filters that value at its own boundary; ordinary
        # routing must still be able to represent it accurately.
        if not capacities:
            ep["context_window"] = registry_capacity
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
    configurations (premium / budget / speed / free) live on disk;
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
    "CONSERVATIVE_ADMISSION_CONTEXT_WINDOW",
    "DEFAULT_CONTEXT_WINDOW",
    "load_registry",
    "reload",
    "lookup",
    "model_ids_equivalent",
    "context_window_for_model",
    "vision_capable",
    "intelligence_score",
    "overlay_routing_config",
    "compute_picks",
    "stats",
]
