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


__all__ = [
    "get_active_name",
    "set_active_name",
    "get_toggles",
    "set_toggles",
    "DEFAULT_ACTIVE_NAME",
]
