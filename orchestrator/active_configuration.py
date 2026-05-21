"""active_configuration — read/write the user's chosen active configuration.

The "active" configuration is the named configuration in
``config/configurations/`` that ``Router.run_pipeline()`` falls back
to when no per-request ``config_name`` is specified. The pointer is
stored in ``~/ora/data/active-configuration.json`` so it survives
restarts; on a fresh install (no pointer file), the fallback chain
matches the legacy hardcoded default per context.

Toggles (``adversarial_diversity``, ``vision_only``) live ON the
configuration file itself in a top-level ``toggles`` block. When a
configuration is loaded and the block is missing, sensible defaults
are inferred from the cells (adversarial = True if gear4.breadth is
populated) and the auto-populate metadata (vision_only from the
``_auto_populate_metadata`` block when it exists, otherwise False).

This module is the single read/write surface for both pieces of state.
The Models pane's header uses it; the per-request dispatch path falls
back to ``get_active_name()`` when ``config_name`` is None.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
DATA_DIR = ORA_HOME / "data"
ACTIVE_POINTER_PATH = DATA_DIR / "active-configuration.json"
CONFIGURATIONS_DIR = ORA_HOME / "config" / "configurations"

# When the pointer file is missing entirely (fresh install), fall back
# to this name. Matches the historic Router default for "interactive"
# context, so existing behavior is preserved end-to-end.
DEFAULT_ACTIVE_NAME = "user-pipeline"

_lock = threading.RLock()


def get_active_name() -> str:
    """Return the active configuration name.

    Reads ``~/ora/data/active-configuration.json``. When the file is
    missing or malformed, returns ``DEFAULT_ACTIVE_NAME`` so dispatch
    keeps working on fresh installs that haven't yet picked anything.
    """
    if not ACTIVE_POINTER_PATH.exists():
        return DEFAULT_ACTIVE_NAME
    try:
        with open(ACTIVE_POINTER_PATH) as f:
            data = json.load(f)
        name = data.get("name") if isinstance(data, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_ACTIVE_NAME


def set_active_name(name: str) -> None:
    """Persist a new active configuration name.

    Validates that a configuration file by that name exists under
    ``config/configurations/`` before writing the pointer — prevents
    pointing the dispatch path at a non-existent config and breaking
    the next chat request.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("active configuration name must be a non-empty string")
    name = name.strip()
    target = CONFIGURATIONS_DIR / f"{name}.json"
    if not target.exists():
        raise ValueError(
            f"no configuration named {name!r} at {target}; "
            "pick an existing name or create one first"
        )
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ACTIVE_POINTER_PATH.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({"name": name}, f, indent=2)
            f.write("\n")
        os.replace(tmp, ACTIVE_POINTER_PATH)


def _config_path(name: str) -> Path:
    return CONFIGURATIONS_DIR / f"{name}.json"


def _load_config(name: str) -> dict:
    path = _config_path(name)
    if not path.exists():
        raise FileNotFoundError(f"no configuration named {name!r} at {path}")
    with open(path) as f:
        return json.load(f)


def _save_config(name: str, config: dict) -> None:
    path = _config_path(name)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def get_toggles(name: str) -> dict:
    """Return the toggle state for a configuration.

    Reads the configuration's ``toggles`` block when present;
    otherwise infers defaults from the existing cells +
    _auto_populate_metadata so legacy configs (no toggle block) report
    a reasonable initial state without write-back.

    Defaults:
      ``adversarial_diversity``: True when cells.analysis.gear4.breadth
        is populated (the breadth slot being filled means the parallel
        adversarial workhorse pair was provisioned); False otherwise.
      ``vision_only``: read from ``_auto_populate_metadata.vision_only``
        when set; False otherwise.
    """
    config = _load_config(name)
    saved = config.get("toggles")
    if isinstance(saved, dict):
        # Trust the saved values; fill any missing keys from defaults
        # so partial saves don't strand the UI in a half-state.
        defaults = _infer_defaults(config)
        return {
            "adversarial_diversity": bool(saved.get(
                "adversarial_diversity", defaults["adversarial_diversity"])),
            "vision_only": bool(saved.get(
                "vision_only", defaults["vision_only"])),
        }
    return _infer_defaults(config)


def set_toggles(name: str, toggles: dict) -> dict:
    """Persist the toggle state into the configuration file.

    Writes a top-level ``toggles`` block; preserves all other fields.
    Returns the resolved toggle dict (the same shape get_toggles()
    returns) for the caller to echo back to the UI.
    """
    if not isinstance(toggles, dict):
        raise ValueError("toggles payload must be an object")
    with _lock:
        config = _load_config(name)
        existing = config.get("toggles") if isinstance(config.get("toggles"), dict) else {}
        merged = dict(existing)
        for key in ("adversarial_diversity", "vision_only"):
            if key in toggles:
                merged[key] = bool(toggles[key])
        config["toggles"] = merged
        _save_config(name, config)
    return get_toggles(name)


def _infer_defaults(config: dict) -> dict:
    cells = config.get("cells") or {}
    analysis = cells.get("analysis") or {}
    gear4 = analysis.get("gear4") or {}
    breadth = gear4.get("breadth")
    adversarial = bool(breadth and isinstance(breadth, dict) and breadth.get("primary"))
    meta = config.get("_auto_populate_metadata") or {}
    vision_only = bool(meta.get("vision_only", False))
    return {
        "adversarial_diversity": adversarial,
        "vision_only": vision_only,
    }


# ── Configuration creation / deletion / rename ───────────────────────────


def duplicate_configuration(source_name: str, new_name: str | None = None) -> str:
    """Copy an existing configuration into a new file.

    Returns the name actually used. When ``new_name`` is None, picks
    the next available ``Configuration NN`` (NN auto-incrementing).
    The copy inherits everything from the source including toggles
    and slot picks; its ``preset_lineage`` is set to ``custom`` and
    ``description`` carries a "copied from <source>" note.

    Raises ``FileNotFoundError`` when the source doesn't exist;
    ``ValueError`` when ``new_name`` is provided but already taken.
    """
    source_path = _config_path(source_name)
    if not source_path.exists():
        raise FileNotFoundError(
            f"source configuration {source_name!r} not found at {source_path}")
    if new_name is None or not new_name.strip():
        new_name = _next_auto_name()
    new_name = new_name.strip()
    if _config_path(new_name).exists():
        raise ValueError(f"configuration {new_name!r} already exists; "
                         f"pick a different name or delete the existing one")
    with _lock:
        with open(source_path) as f:
            source = json.load(f)
        copy = dict(source)
        copy["name"] = new_name
        copy["preset_lineage"] = "custom"
        copy["description"] = (
            f"Copied from {source_name!r} via the Models pane Customize "
            f"action. Original lineage: {source.get('preset_lineage') or 'n/a'}.")
        # Strip the auto-populate metadata — the copy is no longer the
        # output of an auto-populate run and the timestamps would
        # mislead about when picks were last refreshed.
        copy.pop("_auto_populate_metadata", None)
        _save_config(new_name, copy)
    return new_name


def create_blank_configuration(new_name: str | None = None) -> str:
    """Create an empty custom configuration with no slot picks.

    The result is red-bordered in the UI (incomplete) until the user
    fills in at least one small + two large picks. Returns the name
    actually used.
    """
    if new_name is None or not new_name.strip():
        new_name = _next_auto_name()
    new_name = new_name.strip()
    if _config_path(new_name).exists():
        raise ValueError(f"configuration {new_name!r} already exists")
    with _lock:
        config = {
            "name": new_name,
            "description": "Custom configuration created from the Models pane.",
            "preset_lineage": "custom",
            "cells": {
                "utility": {
                    "step1_cleanup": {"primary": None, "fallback": []},
                    "classification": {"primary": None, "fallback": []},
                    "rag_planner": {"primary": None, "fallback": []},
                },
                "analysis": {
                    "gear4": {
                        "depth": {"primary": None, "fallback": []},
                        "breadth": None,
                    },
                    "gear3": {
                        "depth": {"primary": None, "fallback": []},
                        "breadth": None,
                    },
                },
                "post_analysis": {
                    "consolidation": {"primary": None, "fallback": []},
                    "verification": {"primary": None, "fallback": []},
                    "formatter": {"primary": None, "fallback": []},
                },
            },
        }
        _save_config(new_name, config)
    return new_name


def delete_configuration(name: str) -> None:
    """Delete a custom configuration.

    Safety checks (raise ValueError on violation):
      - Cannot delete the currently-active configuration. The user
        must pick a different one first.
      - Cannot delete system configurations (background-default,
        user-pipeline — the migrated defaults that anchor dispatch).
    """
    if name in {"background-default", "user-pipeline"}:
        raise ValueError(
            f"{name!r} is a system configuration and cannot be deleted")
    if name == get_active_name():
        raise ValueError(
            f"{name!r} is currently active; activate a different "
            "configuration before deleting this one")
    path = _config_path(name)
    if not path.exists():
        raise FileNotFoundError(f"no configuration named {name!r}")
    with _lock:
        path.unlink()


def _next_auto_name() -> str:
    """Pick the next available 'Configuration NN' name (zero-padded
    to 2 digits)."""
    existing = set()
    if CONFIGURATIONS_DIR.exists():
        for path in CONFIGURATIONS_DIR.glob("Configuration *.json"):
            existing.add(path.stem)
    for n in range(1, 1000):
        candidate = f"Configuration {n:02d}"
        if candidate not in existing:
            return candidate
    raise RuntimeError("ran out of auto-incremented Configuration NN names")


# ── Configuration listing for the Models pane ────────────────────────────

# Canonical preset order. Matches the user-locked left-to-right order in
# the Models pane (Free on the left so the default-first-run choice
# anchors the upper-left corner; Premium on the right as the upgrade).
PRESET_ORDER = ["free", "budget", "optimum", "premium"]

# Configurations excluded from the Custom-Previous grid because they
# serve a system role rather than a user-saved customization.
SYSTEM_CONFIGS = {"background-default"}


def list_configurations() -> dict:
    """Return everything the Models pane needs to render in one shot.

    Shape:
      {
        "presets": {
          "free":    <summary> | null,
          "budget":  <summary> | null,
          "optimum": <summary> | null,
          "premium": <summary> | null,
        },
        "customs": [<summary>, ...],
        "active_name": "<name>",
        "active_toggles": {<resolved toggles>},
      }

    A preset slot is the configuration whose ``preset_lineage`` matches
    the preset name; we prefer the canonical-named file (``free.json``,
    ``optimum.json``, etc.) and fall back to any file carrying that
    lineage tag. ``null`` when no file claims that lineage.

    Customs are any configuration files NOT matched as a preset and
    not in SYSTEM_CONFIGS (background-default is the automation-side
    fallback, not a user-facing card).

    Each summary carries the three slot picks the pane shows on the
    card: ``big1`` (gear4 depth primary), ``big2`` (gear4 breadth
    primary, may be null), ``small`` (utility step1_cleanup primary).
    """
    if not CONFIGURATIONS_DIR.exists():
        return {
            "presets": {p: None for p in PRESET_ORDER},
            "customs": [],
            "active_name": get_active_name(),
            "active_toggles": _empty_toggles(),
        }

    # Load every configuration once. Skip malformed; the UI shows a
    # diagnostic in the section that wanted it.
    loaded = {}
    for path in sorted(CONFIGURATIONS_DIR.glob("*.json")):
        try:
            with open(path) as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(config, dict):
            loaded[path.stem] = config

    # Bucket presets vs customs.
    presets: dict = {p: None for p in PRESET_ORDER}
    used_files: set = set()
    for preset_name in PRESET_ORDER:
        # 1. Canonical-named file wins (e.g., free.json declaring preset_lineage=free)
        if preset_name in loaded:
            presets[preset_name] = _summarize(preset_name, loaded[preset_name])
            used_files.add(preset_name)
            continue
        # 2. Otherwise pick any file claiming this preset_lineage.
        for fname, config in loaded.items():
            if fname in used_files:
                continue
            if config.get("preset_lineage") == preset_name:
                presets[preset_name] = _summarize(fname, config)
                used_files.add(fname)
                break

    customs = []
    for fname, config in loaded.items():
        if fname in used_files or fname in SYSTEM_CONFIGS:
            continue
        customs.append(_summarize(fname, config))

    active_name = get_active_name()
    try:
        active_toggles = get_toggles(active_name)
    except FileNotFoundError:
        active_toggles = _empty_toggles()

    return {
        "presets": presets,
        "customs": customs,
        "active_name": active_name,
        "active_toggles": active_toggles,
    }


def _summarize(name: str, config: dict) -> dict:
    """Boil a configuration down to the fields the pane card renders."""
    cells = config.get("cells") or {}
    utility = cells.get("utility") or {}
    analysis = cells.get("analysis") or {}
    gear4 = analysis.get("gear4") or {}

    small_cell = utility.get("step1_cleanup") or {}
    big1_cell = gear4.get("depth") or {}
    big2_cell = gear4.get("breadth")
    big2_primary = (big2_cell or {}).get("primary") if isinstance(big2_cell, dict) else None

    toggles_resolved = _infer_defaults(config)
    saved_toggles = config.get("toggles") if isinstance(config.get("toggles"), dict) else {}
    for key in ("adversarial_diversity", "vision_only"):
        if key in saved_toggles:
            toggles_resolved[key] = bool(saved_toggles[key])

    return {
        "name": name,
        "preset_lineage": config.get("preset_lineage"),
        "description": config.get("description") or "",
        "big1": big1_cell.get("primary"),
        "big2": big2_primary,
        "small": small_cell.get("primary"),
        "toggles": toggles_resolved,
    }


def _empty_toggles() -> dict:
    return {"adversarial_diversity": False, "vision_only": False}


__all__ = [
    "get_active_name",
    "set_active_name",
    "get_toggles",
    "set_toggles",
    "list_configurations",
    "duplicate_configuration",
    "create_blank_configuration",
    "delete_configuration",
    "DEFAULT_ACTIVE_NAME",
    "PRESET_ORDER",
]
