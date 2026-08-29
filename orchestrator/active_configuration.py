"""active_configuration — read/write the user's chosen active configuration.

The "active" configuration is the named configuration in
``config/configurations/`` that ``Router.run_pipeline()`` falls back
to when no per-request ``config_name`` is specified. The pointer is
stored in ``~/ora/data/active-configuration.json`` so it survives
restarts; on a fresh install (no pointer file), the fallback chain
matches the legacy hardcoded default per context.

Toggles (``adversarial_diversity``, ``vision_only``, ``min_context_1m``)
live ON the configuration file itself in a top-level ``toggles`` block.
When a configuration is loaded and the block is missing, sensible
defaults are inferred from the cells (adversarial = True if gear4.breadth
is populated) and the auto-populate metadata (vision_only and
min_context_1m from the ``_auto_populate_metadata`` block when it exists,
otherwise False).

This module is the single read/write surface for both pieces of state.
The Models pane's header uses it; the per-request dispatch path falls
back to ``get_active_name()`` when ``config_name`` is None.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
from pathlib import Path
from typing import Callable

try:
    from . import runtime_paths as rp
except ImportError:  # direct script-style import from sys.path
    import runtime_paths as rp  # type: ignore

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
DATA_DIR = ORA_HOME / "data"
ACTIVE_POINTER_PATH = DATA_DIR / "active-configuration.json"
PRESET_TOGGLES_PATH = DATA_DIR / "preset-toggles.json"
CONFIGURATIONS_DIR = ORA_HOME / "config" / "configurations"
MODELS_JSON_PATH = rp.models_json_path()
_DEFAULT_CONFIGURATIONS_DIR = CONFIGURATIONS_DIR
RUNTIME_CONFIGURATIONS_DIR = rp.RUNTIME_CONFIGURATIONS_DIR
_RUNTIME_OVERLAY_CONFIG_NAMES = set(getattr(
    rp, "RUNTIME_OVERLAY_CONFIGURATION_NAMES", rp.PRESET_NAMES))

# When the pointer file is missing entirely (fresh install), fall back
# to this name. Matches the historic Router default for "interactive"
# context, so existing behavior is preserved end-to-end.
DEFAULT_ACTIVE_NAME = "user-pipeline"

AUTOMATIC_RAM_TARGET_RATIO = 0.80
HARD_RAM_CAP_RATIO = 0.85

_lock = threading.RLock()
_LOCAL_MODELS_UNSET = object()

# Why the most recent bake attempt did not produce a given preset, keyed by
# preset name.
#
# A preset the Models pane cannot show used to arrive as a bare ``null`` with
# no cause attached: "never attempted" and "the picker raised" were the same
# blank card. ``bake_missing_presets`` now writes the exact reason here and
# clears it the moment that preset exists, so ``list_configurations`` can hand
# the pane something to print. It is a cache of the last attempt, not a record
# to keep — the pane re-attempts every missing preset on every load, so a
# fresh cause replaces the old one on each pass.
_bake_errors: dict[str, str] = {}


def _print_line(message: str) -> None:
    """Where a bake's prose goes when the caller does not say otherwise.

    Under the server — which is nearly always — stdout *is* the log, so a
    plain print is the right and only dependency-free answer. Callers that
    keep a log of their own, such as the installer, hand ``bake_missing_presets``
    a writer instead of relying on where this happens to land.
    """
    print(message, flush=True)


def preset_bake_errors() -> dict[str, str]:
    """Return the exact per-preset causes left by the last bake attempt.

    Keys are preset names; values are single-line human-readable causes
    (``"ValueError: Unknown preset: speed…"``, ``"config/model-catalog.json is
    missing"``). An entry is cleared the moment a bake produces that preset,
    or finds it already there and leaves it alone.

    One case leaves an entry against a preset that is perfectly fine: when a
    bake cannot start at all — no catalog, no preset definitions, no picker —
    the cause is recorded against every preset that bake had selected,
    including any that already exist on disk, because nothing was attempted
    for any of them. ``list_configurations`` reports a cause only for a slot
    that is actually empty, so those extra entries never reach the pane.
    """
    return dict(_bake_errors)


def _get_system_ram_gb() -> float:
    try:
        from .platform_check import get_system_ram_gb
    except ImportError:  # direct script-style import from sys.path
        from platform_check import get_system_ram_gb  # type: ignore
    return float(get_system_ram_gb())


def _load_local_models() -> list[dict]:
    """Return the latest discovered local inventory or fail closed."""
    try:
        with open(MODELS_JSON_PATH) as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise ValueError(
            f"local model inventory is unavailable: {MODELS_JSON_PATH} is missing"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"local model inventory is unavailable: could not read "
            f"{MODELS_JSON_PATH}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("local model inventory is malformed: root must be an object")
    if "local_models" not in data:
        raise ValueError(
            "local model inventory is malformed: local_models is missing"
        )
    return data["local_models"]


def _installed_local_models(local_models=_LOCAL_MODELS_UNSET) -> dict[str, dict]:
    """Validate and index the authoritative installed inventory by routing id."""
    rows = _load_local_models() if local_models is _LOCAL_MODELS_UNSET else local_models
    if not isinstance(rows, list):
        raise ValueError(
            "local model inventory is malformed: local_models must be a list"
        )
    installed: dict[str, dict] = {}
    seen_ids: set[str] = set()
    for index, model in enumerate(rows):
        if not isinstance(model, dict):
            raise ValueError(
                f"local model inventory is malformed: row {index} must be an object"
            )
        model_id = model.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(
                f"local model inventory is malformed: row {index} has no valid id"
            )
        model_id = model_id.strip()
        if model_id in seen_ids:
            raise ValueError(
                f"local model inventory is malformed: duplicate id {model_id!r}"
            )
        seen_ids.add(model_id)

        raw_ram = model.get("ram_gb")
        if isinstance(raw_ram, bool):
            raise ValueError(
                f"local model inventory is malformed: {model_id!r} has invalid ram_gb"
            )
        try:
            ram_gb = float(raw_ram)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"local model inventory is malformed: {model_id!r} has invalid ram_gb"
            ) from exc
        if not math.isfinite(ram_gb) or ram_gb < 0:
            raise ValueError(
                f"local model inventory is malformed: {model_id!r} has invalid ram_gb"
            )

        if "path" in model:
            raw_path = model.get("path")
        elif "model_path" in model:
            raw_path = model.get("model_path")
        else:
            raw_path = None
        if raw_path is not None:
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(
                    f"local model inventory is malformed: {model_id!r} has invalid path"
                )
            try:
                available = Path(raw_path).expanduser().resolve(strict=False).is_dir()
            except (OSError, RuntimeError):
                available = False
            if not available:
                continue

        installed[model_id] = {**model, "id": model_id, "ram_gb": ram_gb}
    return installed


def _profile_model_ids(profile: dict) -> list[str]:
    """Collect each model reachable from a routing cell exactly once."""
    seen: set[str] = set()
    ordered: list[str] = []
    roles = profile.get("roles")

    def add(value) -> None:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            ordered.append(value)

    def resolve_role(role) -> dict:
        if not isinstance(role, str) or not role:
            raise ValueError(
                "Model Profile role reference must be a non-empty string"
            )
        if not isinstance(roles, dict):
            raise ValueError(
                f"Model Profile role reference {role!r} has no roles object"
            )
        target = roles.get(role)
        if not isinstance(target, dict):
            raise ValueError(
                f"Model Profile role reference {role!r} does not name an object"
            )
        # Match Router._resolve_configuration_cell exactly: the routing
        # cell's role selects one top-level role object.  A role field on that
        # returned object is metadata; Router executes the object's own chain.
        return target

    def collect_cell(cell: dict) -> None:
        role = cell.get("role")
        if role:
            cell = resolve_role(role)
        elif "role" in cell and cell["role"] not in (None, ""):
            # Router treats other falsy values as an inline cell. Reject them
            # here instead of allowing malformed role metadata to bypass the
            # shared profile validation contract.
            resolve_role(cell["role"])
        add(cell.get("primary"))
        add(cell.get("vision_substitute"))
        fallback = cell.get("fallback")
        if isinstance(fallback, list):
            for model_id in fallback:
                add(model_id)

    visiting: set[int] = set()

    def visit(node) -> None:
        if not isinstance(node, dict):
            return
        identity = id(node)
        if identity in visiting:
            raise ValueError("Model Profile cells contain a reference cycle")
        visiting.add(identity)
        try:
            children = [value for value in node.values()
                        if isinstance(value, dict)]
            if any(key in node for key in (
                "primary", "fallback", "vision_substitute", "role",
            )):
                collect_cell(node)
            for value in children:
                visit(value)
        finally:
            visiting.remove(identity)

    visit(profile.get("cells") or {})
    return ordered


def profile_ram_allocation(
    profile: dict,
    *,
    system_ram_gb: float | None = None,
    local_models=_LOCAL_MODELS_UNSET,
) -> dict:
    """Describe whole-profile local RAM allocation from installed model sizes."""
    if not isinstance(profile, dict):
        raise ValueError("Model Profile must be a JSON object for RAM validation")
    try:
        system_ram = float(
            system_ram_gb if system_ram_gb is not None else _get_system_ram_gb()
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("system RAM is unavailable for Model Profile validation") from exc
    if not math.isfinite(system_ram) or system_ram <= 0:
        raise ValueError("system RAM is unavailable for Model Profile validation")
    installed = _installed_local_models(local_models)
    local_ids = [model_id for model_id in _profile_model_ids(profile)
                 if model_id in installed]
    allocated = sum(installed[model_id]["ram_gb"] for model_id in local_ids)
    automatic_target = max(0.0, system_ram * AUTOMATIC_RAM_TARGET_RATIO)
    hard_cap = max(0.0, system_ram * HARD_RAM_CAP_RATIO)
    return {
        "system_ram_gb": system_ram,
        "automatic_target_gb": automatic_target,
        "hard_cap_gb": hard_cap,
        "active_local_model_ids": local_ids,
        "allocated_local_ram_gb": allocated,
        "headroom_to_hard_cap_gb": hard_cap - allocated,
    }


def validate_profile_allocation(
    profile: dict,
    *,
    system_ram_gb: float | None = None,
    local_models=_LOCAL_MODELS_UNSET,
) -> dict:
    """Reject a profile only when its unique installed locals exceed 85%."""
    allocation = profile_ram_allocation(
        profile, system_ram_gb=system_ram_gb, local_models=local_models)
    allocated = allocation["allocated_local_ram_gb"]
    hard_cap = allocation["hard_cap_gb"]
    if allocated > hard_cap:
        raise ValueError(
            "Model Profile local RAM allocation "
            f"({allocated:g} GB) exceeds the 85% hard cap "
            f"({hard_cap:g} GB). Reuse or remove a local model before saving."
        )
    return allocation


def _apply_free_local_overlay(
    config: dict,
    *,
    local_models=_LOCAL_MODELS_UNSET,
    system_ram_gb: float | None = None,
    toggles: dict | None = None,
) -> dict:
    """Overlay compatible installed locals onto a cloud-baked Free profile."""
    installed = _installed_local_models(local_models)
    effective_toggles = toggles or {}
    vision_only = bool(effective_toggles.get("vision_only"))
    adversarial = bool(effective_toggles.get("adversarial_diversity"))

    try:
        system_ram = float(
            system_ram_gb if system_ram_gb is not None else _get_system_ram_gb()
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("system RAM is unavailable for Free local selection") from exc
    if not math.isfinite(system_ram) or system_ram <= 0:
        raise ValueError("system RAM is unavailable for Free local selection")
    target = system_ram * AUTOMATIC_RAM_TARGET_RATIO
    hard_cap = system_ram * HARD_RAM_CAP_RATIO

    candidates: dict[str, list[dict]] = {"big": [], "fast": [], "small": []}
    for model in installed.values():
        if not model.get("enabled", True):
            continue
        if model.get("status", "active") != "active":
            continue
        try:
            context_window = float(model.get("context_window") or 0)
            parameters_b = float(model.get("parameters_b"))
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(context_window)
            or context_window <= 0
            or not math.isfinite(parameters_b)
            or parameters_b <= 0
        ):
            continue
        if vision_only and model.get("vision_capable") is not True:
            continue
        # The 1M-context floor deliberately does NOT apply to installed
        # locals. No local model ships a ~1M window — the largest here is
        # 262k — so honouring the floor on this side is equivalent to "never
        # overlay a local", which silently voids this whole function whenever
        # the toggle is on. It is also enforced on locals only: the cloud
        # bake this overlays does not re-select on the floor, so a Free
        # preset routinely carries 128k cloud picks while a 262k local was
        # rejected for being too short. The floor stays a cloud-selectivity
        # control; RAM, vision and family diversity remain the local gates.
        if parameters_b > 50:
            category = "big"
        elif parameters_b >= 12:
            category = "fast"
        else:
            category = "small"
        candidates[category].append({**model, "parameters_b": parameters_b})
    for rows in candidates.values():
        rows.sort(key=lambda row: (-row["parameters_b"], row["id"]))

    selected: dict[str, dict] = {}
    used_ids: set[str] = set()
    allocated = 0.0

    def fits(model: dict) -> bool:
        if model["id"] in used_ids:
            return True
        proposed = allocated + float(model["ram_gb"])
        return proposed <= target and proposed <= hard_cap

    def select_largest(label: str, category: str, *, family_not=None) -> None:
        nonlocal allocated
        for model in candidates[category]:
            if model["id"] in used_ids:
                continue
            family = model.get("training_family") or model.get("provider")
            if family_not is not None and (
                not family or str(family).strip().lower() == family_not
            ):
                continue
            if not fits(model):
                continue
            selected[label] = model
            used_ids.add(model["id"])
            allocated += float(model["ram_gb"])
            return

    # Core local coverage comes first. Pair slots are filled only after these
    # three have had their chance at the shared automatic-RAM target.
    select_largest("big 1", "big")
    select_largest("fast 1", "fast")
    select_largest("small", "small")

    if adversarial:
        if "big 1" in selected:
            first = selected["big 1"]
            family = first.get("training_family") or first.get("provider")
            if family:
                select_largest(
                    "big 2", "big", family_not=str(family).strip().lower())
        if "fast 1" in selected:
            first = selected["fast 1"]
            family = first.get("training_family") or first.get("provider")
            if family:
                select_largest(
                    "fast 2", "fast", family_not=str(family).strip().lower())
    else:
        if "big 1" in selected:
            selected["big 2"] = selected["big 1"]
        if "fast 1" in selected:
            selected["fast 2"] = selected["fast 1"]

    local_ids = set(installed)
    cells = config.setdefault("cells", {})
    for label, model in selected.items():
        for path in SLOT_LABEL_TO_PATHS[label]:
            node = cells
            for key in path[:-1]:
                child = node.get(key)
                if not isinstance(child, dict):
                    child = {}
                    node[key] = child
                node = child
            cell = node.get(path[-1])
            if not isinstance(cell, dict):
                cell = {"primary": None, "fallback": []}
                node[path[-1]] = cell
            displaced = cell.get("primary")
            cloud_fallbacks: list[str] = []
            for model_id in [displaced, *(cell.get("fallback") or [])]:
                if (
                    isinstance(model_id, str)
                    and model_id
                    and model_id not in local_ids
                    and model_id not in cloud_fallbacks
                ):
                    cloud_fallbacks.append(model_id)
            cell["primary"] = model["id"]
            cell["fallback"] = cloud_fallbacks

    config["diversity_override"] = adversarial
    validate_profile_allocation(
        config, system_ram_gb=system_ram, local_models=list(installed.values()))
    return config


def get_active_name(*, strict: bool = False) -> str:
    """Return the active configuration name.

    Reads ``~/ora/data/active-configuration.json``. When the file is
    missing or malformed, returns ``DEFAULT_ACTIVE_NAME`` so dispatch
    keeps working on fresh installs that haven't yet picked anything.
    """
    if not ACTIVE_POINTER_PATH.exists():
        if strict:
            raise ValueError(
                f"active Model Profile pointer is missing: {ACTIVE_POINTER_PATH}"
            )
        return DEFAULT_ACTIVE_NAME
    try:
        with open(ACTIVE_POINTER_PATH) as f:
            data = json.load(f)
        name = data.get("name") if isinstance(data, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, json.JSONDecodeError) as exc:
        if strict:
            raise ValueError(
                f"active Model Profile pointer is unreadable: {exc}"
            ) from exc
    if strict:
        raise ValueError("active Model Profile pointer is malformed")
    return DEFAULT_ACTIVE_NAME


def set_active_name(name: str) -> None:
    """Persist a new active configuration name.

    Validates that a configuration file by that name exists under
    ``config/configurations/`` before writing the pointer — prevents
    pointing the dispatch path at a non-existent config and breaking
    the next chat request.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("active Model Profile name must be a non-empty string")
    name = name.strip()
    target = _config_path(name)
    if not target.exists():
        raise ValueError(
            f"no Model Profile named {name!r} at {target}; "
            "pick an existing name or create one first"
        )
    with _lock:
        with rp.locked_file(ACTIVE_POINTER_PATH):
            validate_profile_allocation(_load_config(name))
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            rp.atomic_write_text(
                ACTIVE_POINTER_PATH,
                json.dumps({"name": name}, indent=2) + "\n",
                mode=0o644,
            )


def _runtime_overlay_active() -> bool:
    return CONFIGURATIONS_DIR == _DEFAULT_CONFIGURATIONS_DIR


def _config_path(name: str, *, for_write: bool = False) -> Path:
    if (
        not isinstance(name, str)
        or not name.strip()
        or name != name.strip()
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise ValueError("Model Profile name must be one exact path-safe leaf")
    if _runtime_overlay_active() and name in _RUNTIME_OVERLAY_CONFIG_NAMES:
        runtime = RUNTIME_CONFIGURATIONS_DIR / f"{name}.json"
        if for_write or runtime.exists():
            return runtime
    return CONFIGURATIONS_DIR / f"{name}.json"


def _configuration_dirs_for_read() -> list[Path]:
    dirs = [CONFIGURATIONS_DIR]
    if _runtime_overlay_active() and RUNTIME_CONFIGURATIONS_DIR.exists():
        dirs.append(RUNTIME_CONFIGURATIONS_DIR)
    return dirs


def _catalog_path() -> Path:
    if _runtime_overlay_active():
        return rp.model_catalog_path()
    return ORA_HOME / "config" / "model-catalog.json"


def _registry_path() -> Path:
    if _runtime_overlay_active():
        return rp.model_registry_path()
    return ORA_HOME / "config" / "model-registry.json"


def _load_config(name: str) -> dict:
    path = _config_path(name)
    if not path.exists():
        raise FileNotFoundError(f"no Model Profile named {name!r} at {path}")
    with open(path) as f:
        return json.load(f)


def _save_config(name: str, config: dict, *, _locked: bool = False) -> None:
    path = _config_path(name, for_write=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2) + "\n"
    if _locked:
        rp.atomic_write_text(path, payload, mode=0o644)
        return
    with rp.locked_file(path):
        rp.atomic_write_text(path, payload, mode=0o644)


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
            "min_context_1m": bool(saved.get(
                "min_context_1m", defaults["min_context_1m"])),
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
    path = _config_path(name, for_write=True)
    with _lock, rp.locked_file(path):
        config = _load_config(name)
        existing = config.get("toggles") if isinstance(config.get("toggles"), dict) else {}
        merged = dict(existing)
        for key in ("adversarial_diversity", "vision_only", "min_context_1m"):
            if key in toggles:
                merged[key] = bool(toggles[key])
        config["toggles"] = merged
        _save_config(name, config, _locked=True)
    return get_toggles(name)


def _infer_defaults(config: dict) -> dict:
    cells = config.get("cells") or {}
    analysis = cells.get("analysis") or {}
    gear4 = analysis.get("gear4") or {}
    breadth = gear4.get("breadth")
    adversarial = bool(breadth and isinstance(breadth, dict) and breadth.get("primary"))
    meta = config.get("_auto_populate_metadata") or {}
    vision_only = bool(meta.get("vision_only", False))
    # min_context_1m default: inferred from the bake metadata's min_context
    # (set when the preset was baked with the context floor on). Any truthy
    # value means the floor was applied; absent/None/0 → False.
    min_context_1m = bool(meta.get("min_context"))
    return {
        "adversarial_diversity": adversarial,
        "vision_only": vision_only,
        "min_context_1m": min_context_1m,
    }


# ── Preset baking — populate missing presets from the catalog ────────────


def get_preset_toggles() -> dict:
    """Return the global preset toggle state.

    Toggles are GLOBAL to the four presets (Adversarial Diversity,
    Vision-capable only, 1M context): turning Vision on at the top of
    the Models pane while a preset is active updates this global state
    and re-bakes all four presets with vision_only=True. The 1M-context
    toggle (min_context_1m) re-bakes them with a ~1M context floor so
    the picks fit long prompts.

    Custom configurations keep their own per-config toggle state via
    get_toggles/set_toggles.

    Defaults when no pointer file exists: all toggles off.
    """
    if not PRESET_TOGGLES_PATH.exists():
        return {"adversarial_diversity": False, "vision_only": False,
                "min_context_1m": False}
    try:
        with open(PRESET_TOGGLES_PATH) as f:
            data = json.load(f)
        return {
            "adversarial_diversity": bool(data.get("adversarial_diversity", False)),
            "vision_only": bool(data.get("vision_only", False)),
            "min_context_1m": bool(data.get("min_context_1m", False)),
        }
    except (OSError, json.JSONDecodeError):
        return {"adversarial_diversity": False, "vision_only": False,
                "min_context_1m": False}


def set_preset_toggles(
    toggles: dict,
    *,
    rebake: bool = False,
    custom_profile_name: str | None = None,
) -> dict:
    """Persist the global preset toggle state. Partial update OK —
    either key may be omitted to leave that toggle unchanged.

    When ``rebake`` is true, keep the same cross-process toggle lock through
    the forced preset bake. When ``custom_profile_name`` is supplied, merge
    the same partial toggle update into that named profile before releasing
    the global lock. The named-profile writer nests its own lock in the
    accepted global-toggle -> named-profile order, so overlapping requests
    cannot leave preset state from one request and custom state from another.
    """
    if not isinstance(toggles, dict):
        raise ValueError("toggles payload must be an object")
    with _lock, rp.locked_file(PRESET_TOGGLES_PATH):
        current = get_preset_toggles()
        for key in ("adversarial_diversity", "vision_only", "min_context_1m"):
            if key in toggles:
                current[key] = bool(toggles[key])
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        rp.atomic_write_text(
            PRESET_TOGGLES_PATH,
            json.dumps(current, indent=2) + "\n",
            mode=0o644,
        )
        if rebake:
            _bake_missing_presets_locked(force=True)
        if custom_profile_name is not None:
            try:
                set_toggles(custom_profile_name, toggles)
            except FileNotFoundError:
                pass
    return current


def bake_missing_presets(
    force: bool = False,
    *,
    preset_names: tuple[str, ...] | list[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list:
    """Bake presets from one toggle snapshot under the toggle sidecar lock.

    Standalone inventory/catalog-triggered bakes share this lock with toggle
    updates, so an older snapshot cannot finish after a later toggle request
    and restore stale preset documents.
    """
    with _lock, rp.locked_file(PRESET_TOGGLES_PATH):
        return _bake_missing_presets_locked(
            force=force, preset_names=preset_names, log=log,
        )


def _bake_missing_presets_locked(
    force: bool = False,
    *,
    preset_names: tuple[str, ...] | list[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list:
    """Run the auto-populate engine for any preset that doesn't have a
    configuration file on disk.

    Reads the global preset toggle state (vision_only,
    adversarial_diversity, min_context_1m) and applies it:
      * vision_only → passed to populate_configuration so the picker
        filters to vision-capable models only.
      * min_context_1m → passed as min_context=900000 so the picker
        filters to ~1M-context models (graceful degrade per slot).
      * adversarial_diversity=False → post-bake, copy gear4.depth's
        primary + fallback into gear4.breadth AND mirror gear3.depth
        into gear3.breadth, so "the top model fills all slots" rather
        than enforcing diversity across both the Big and Fast pairs.

    Returns the list of preset names that were baked (empty when
    everything was already present). When ``force=True``, re-bakes
    every preset regardless of file existence — used by
    set_preset_toggles to refresh picks after a toggle flip, and by the
    installer once it has settled which catalog the machine will use.
    A forced bake that lands on top of an existing preset file logs one
    line naming that file, because it replaces whatever was in it —
    including slots the user picked by hand.

    Nothing here fails silently. Every reason a preset can come out
    missing — an absent catalog, an unreadable one, a picker that raised
    on one preset alone — is recorded against that preset name in
    ``preset_bake_errors()`` and written out as a line of prose, so the
    caller and the Models pane can both say *why* a card is empty.

    ``log`` is where those lines go. Left alone they are printed, which
    under the server is exactly right — stdout is the server log. The
    installer calls this in-process, though, where printing lands on the
    terminal and nowhere else, and install.log is the file the install
    tells the user to read afterwards; a warning that a forced bake has
    just overwritten hand-picked slots is worth little if it is missing
    from there. So the installer passes its own writer and the same lines
    reach both. Nothing about *when* a line is written depends on this —
    only where it goes.
    """
    say = log if log is not None else _print_line
    if preset_names is None:
        selected_presets = list(PRESET_ORDER)
    else:
        requested = set(preset_names)
        unknown = requested.difference(PRESET_ORDER)
        if unknown:
            raise ValueError(f"unknown preset names: {sorted(unknown)!r}")
        selected_presets = [name for name in PRESET_ORDER if name in requested]

    def _abort(reason: str) -> list:
        """Record one whole-bake failure against every preset it stopped."""
        for name in selected_presets:
            _bake_errors[name] = reason
        say(f"[presets] bake could not run — {reason}")
        return []

    presets_path = ORA_HOME / "config" / "configuration-presets.json"
    catalog_path = _catalog_path()
    if not presets_path.exists():
        return _abort(f"preset definitions are missing: {presets_path}")
    if not catalog_path.exists():
        return _abort(
            f"the model catalog is missing: {catalog_path}. Run "
            f"`python3 scripts/refresh-catalog.py` to fetch it."
        )

    # Dynamic import — the script's hyphen-in-filename means we can't
    # do a normal `import auto_populate_configuration`.
    import importlib.util
    script_path = ORA_HOME / "scripts" / "auto-populate-configuration.py"
    if not script_path.exists():
        return _abort(f"the model picker is missing: {script_path}")
    spec = importlib.util.spec_from_file_location(
        "_ora_auto_populate", str(script_path))
    ap_module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(ap_module)
    except Exception as exc:
        return _abort(
            f"the model picker at {script_path} would not load — "
            f"{type(exc).__name__}: {exc}"
        )

    try:
        with open(catalog_path) as f:
            catalog_data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return _abort(
            f"the model catalog at {catalog_path} could not be read — "
            f"{type(exc).__name__}: {exc}"
        )
    catalog = list((catalog_data or {}).get("models", []) or [])
    if not catalog:
        return _abort(f"the model catalog at {catalog_path} lists no models")
    try:
        with open(presets_path) as f:
            presets_config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return _abort(
            f"the preset definitions at {presets_path} could not be read — "
            f"{type(exc).__name__}: {exc}"
        )

    global_toggles = get_preset_toggles()
    vision_only = global_toggles["vision_only"]
    adversarial = global_toggles["adversarial_diversity"]
    # 1M-context floor: when min_context_1m is on, pass a 900000 context
    # floor into populate_configuration so every slot picks ~1M-context
    # models (slots with no eligible candidate degrade gracefully — the
    # picker skips the floor for that slot and notes it in the loosening
    # log). Mirrors the vision_only threading exactly.
    min_context = 900000 if global_toggles["min_context_1m"] else None

    # Cross-reference the registry via the script's shared helper:
    # reachability gate (only probe-verified models are pick-eligible),
    # output_tokens_per_second (Fast slot sort key) and reasoning_model
    # (Fast slot exclusion). Before 2026-06-11 this path skipped the
    # reachability set entirely, so server-side re-bakes could pick
    # unprobed models the CLI would have excluded.
    try:
        xref = ap_module.registry_crossref(
            _registry_path())
    except Exception:
        # registry_crossref is itself fail-soft; this only fires on a
        # version-skewed scripts/ copy lacking the function. Degrade to
        # no filtering rather than aborting every preset bake.
        xref = {}
    tokens_per_sec: dict = dict(xref.get("tokens_per_sec") or {})
    # Speed-preset sort key: time-to-first-token in ms (OpenRouter or_ttft_ms
    # preferred, AA latency_ttft_seconds × 1000 fallback). Threaded into
    # populate_configuration exactly like tokens_per_sec. .get with default
    # so a version-skewed registry_crossref lacking the key degrades to no
    # latency signal rather than KeyError-ing the whole bake.
    latency_ms: dict = dict(xref.get("latency_ms") or {})
    reasoning_model_ids: set = set(xref.get("reasoning_model_ids") or set())
    registry_ids: set = set(xref.get("registry_ids") or set())
    unreachable_ids: set = set(xref.get("unreachable_ids") or set())
    vision_verified_ids: set = set(xref.get("vision_verified_ids") or set())
    # Vendor-catalogue-authoritative pool restriction: when the inversion is
    # active, the Models pane serves each keyed vendor's NATIVE catalogue, so a
    # pick that's in the base registry but absent from that inventory (and not
    # aliased to it) renders DEPRECATED. registry_crossref builds the set of
    # pane-resolvable ids; passing it restricts the picks to models the pane can
    # show. .get with default so a version-skewed scripts/ copy lacking the key
    # degrades to no VA restriction (base-registry filter still applies).
    va_resolvable_ids: set = set(xref.get("va_resolvable_ids") or set())
    # Hard identity floor: only catalog ids that serialize to an actual
    # routing endpoint may enter a generated primary/fallback chain.
    routing_endpoint_ids: set = set(xref.get("routing_endpoint_ids") or set())
    # Serialize native endpoint ids, not the legacy OpenRouter aliases that
    # may have supplied pricing/intelligence data to the catalog picker.
    canonical_aliases: dict = dict(xref.get("canonical_aliases") or {})

    # Connected ChatGPT/Codex models are runtime-only endpoints, so append
    # their exact-counterpart selection projections in memory and explicitly
    # mirror their ids through every catalog gate. Nothing here is written to
    # the catalog or registry; generated profiles serialize endpoint ids only.
    try:
        try:
            from . import codex_subscription
        except ImportError:
            import codex_subscription  # type: ignore
        subscription_candidates = codex_subscription.selector_candidates()
    except Exception:
        subscription_candidates = []
    if subscription_candidates:
        catalog.extend(subscription_candidates)
        subscription_ids = {
            candidate["id"] for candidate in subscription_candidates
        }
        registry_ids.update(subscription_ids)
        routing_endpoint_ids.update(subscription_ids)
        va_resolvable_ids.update(subscription_ids)
        unreachable_ids.difference_update(subscription_ids)
        for candidate in subscription_candidates:
            model_id = candidate["id"]
            throughput = candidate.get("output_tokens_per_second")
            if throughput is None:
                throughput = candidate.get("or_throughput_tps")
            if throughput is not None:
                tokens_per_sec[model_id] = float(throughput)
            ttft_ms = candidate.get("or_ttft_ms")
            if ttft_ms is None and candidate.get("latency_ttft_seconds") is not None:
                ttft_ms = float(candidate["latency_ttft_seconds"]) * 1000.0
            if ttft_ms is not None:
                latency_ms[model_id] = float(ttft_ms)
            if (candidate.get("reasoning_model") is True
                    or candidate.get("forced_reasoning") is True):
                reasoning_model_ids.add(model_id)

    baked: list = []
    for preset_name in selected_presets:
        # Skip if a config file already claims this preset, unless
        # force-rebake is requested.
        target_path = _config_path(preset_name, for_write=True)
        already = target_path.exists() or _existing_for_lineage(preset_name)
        if already and not force:
            # The preset exists, so whatever went wrong last time no
            # longer describes the card the user is looking at.
            _bake_errors.pop(preset_name, None)
            continue
        if force and target_path.exists():
            # Regenerating over an existing file is the intent of force —
            # a toggle flip or an install has just changed which models are
            # eligible, and the picks have to be redone. What was wrong was
            # doing it in silence: someone who hand-picked models into this
            # preset loses them here, and until now nothing said so.
            say(
                f"[presets] {preset_name}: replacing the existing configuration "
                f"at {target_path} with freshly picked models — any hand-picked "
                f"slots in it are overwritten"
            )
        try:
            config = ap_module.populate_configuration(
                preset_name, catalog, presets_config,
                vision_only=vision_only,
                unreachable_ids=unreachable_ids,
                tokens_per_sec=tokens_per_sec,
                latency_ms=latency_ms,
                reasoning_model_ids=reasoning_model_ids,
                registry_ids=registry_ids,
                vision_verified_ids=vision_verified_ids,
                va_resolvable_ids=va_resolvable_ids,
                routing_endpoint_ids=routing_endpoint_ids,
                canonical_aliases=canonical_aliases,
                min_context=min_context)
            config["name"] = preset_name
            # Adversarial OFF: top model fills both Big AND Fast pairs.
            # When Adversarial is on (or not specified), keep the
            # diversity-enforced pair the picker produced.
            if not adversarial:
                cells = config.get("cells") or {}
                gear4 = (cells.get("analysis") or {}).get("gear4") or {}
                depth = gear4.get("depth")
                if isinstance(depth, dict):
                    gear4["breadth"] = {
                        "primary": depth.get("primary"),
                        "fallback": list(depth.get("fallback") or []),
                        "vision_substitute": depth.get("vision_substitute"),
                    }
                # Mirror for Fast: gear3.breadth ← gear3.depth.
                gear3 = (cells.get("analysis") or {}).get("gear3") or {}
                fast_depth = gear3.get("depth")
                if isinstance(fast_depth, dict):
                    gear3["breadth"] = {
                        "primary": fast_depth.get("primary"),
                        "fallback": list(fast_depth.get("fallback") or []),
                        "vision_substitute": fast_depth.get("vision_substitute"),
                    }
            # Stash the global toggle state on the config too so the
            # UI's per-config toggle reader picks it up immediately
            # without needing to consult the global file separately.
            config["toggles"] = dict(global_toggles)
            if preset_name == "free":
                _apply_free_local_overlay(
                    config,
                    local_models=_load_local_models(),
                    system_ram_gb=_get_system_ram_gb(),
                    toggles=global_toggles,
                )
            _save_config(preset_name, config)
            baked.append(preset_name)
            _bake_errors.pop(preset_name, None)
        except Exception as exc:
            # Per-preset failures stay isolated — one bad preset must not
            # block the other three. What changed is that the cause is
            # kept: it goes to the server log and into preset_bake_errors,
            # so the card the pane draws for this preset names the reason
            # instead of shrugging.
            cause = f"{type(exc).__name__}: {exc}"
            _bake_errors[preset_name] = cause
            say(f"[presets] {preset_name} did not bake — {cause}")
            continue
    return baked


def _existing_for_lineage(lineage: str) -> bool:
    """True when any file in CONFIGURATIONS_DIR carries this preset_lineage."""
    for directory in _configuration_dirs_for_read():
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                with open(path) as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get("preset_lineage") == lineage:
                    return True
            except (OSError, json.JSONDecodeError):
                continue
    return False


# ── Configuration creation / deletion / rename ───────────────────────────


def duplicate_configuration(source_name: str, new_name: str | None = None) -> str:
    """Copy an existing configuration into a new file.

    Returns the name actually used. When ``new_name`` is None, picks
    the next available ``Model Profile NN`` (NN auto-incrementing).
    The copy inherits everything from the source including toggles
    and slot picks; its ``preset_lineage`` is set to ``custom`` and
    ``description`` carries a "copied from <source>" note.

    Raises ``FileNotFoundError`` when the source doesn't exist;
    ``ValueError`` when ``new_name`` is provided but already taken.
    """
    source_path = _config_path(source_name)
    if not source_path.exists():
        raise FileNotFoundError(
            f"source Model Profile {source_name!r} not found at {source_path}")
    if new_name is None or not new_name.strip():
        new_name = _next_auto_name()
    new_name = new_name.strip()
    target_path = _config_path(new_name, for_write=True)
    if target_path.exists():
        raise ValueError(f"Model Profile {new_name!r} already exists; "
                         f"pick a different name or delete the existing one")
    with _lock, rp.locked_file(target_path):
        if target_path.exists():
            raise ValueError(f"Model Profile {new_name!r} already exists; "
                             f"pick a different name or delete the existing one")
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
        _save_config(new_name, copy, _locked=True)
    return new_name


def create_blank_configuration(new_name: str | None = None) -> str:
    """Create an empty custom configuration with no slot picks.

    The result is red-bordered in the UI (incomplete) until the user
    fills in the four baseline slots — see ``_is_baseline_complete``.
    The ``_incomplete: True`` marker on the config persists until the
    user satisfies that check via slot edits; legacy customs lack the
    marker and are NOT flagged as incomplete (the marker is the only
    incomplete signal — missing slots alone are not enough).
    Returns the name actually used.
    """
    if new_name is None or not new_name.strip():
        new_name = _next_auto_name()
    new_name = new_name.strip()
    target_path = _config_path(new_name, for_write=True)
    if target_path.exists():
        raise ValueError(f"Model Profile {new_name!r} already exists")
    with _lock, rp.locked_file(target_path):
        if target_path.exists():
            raise ValueError(f"Model Profile {new_name!r} already exists")
        config = {
            "name": new_name,
            "description": "Custom Model Profile created from the Models pane.",
            "preset_lineage": "custom",
            "_incomplete": True,
            "cells": {
                "utility": {
                    "step1_cleanup": {"primary": None, "fallback": []},
                    "classification": {"primary": None, "fallback": []},
                    "rag_planner": {"primary": None, "fallback": []},
                    "gear2_rag_lookup": {"primary": None, "fallback": []},
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
        _save_config(new_name, config, _locked=True)
    return new_name


def _is_baseline_complete(config: dict) -> bool:
    """A configuration is baseline-complete when the card-visible
    primary slots are filled: big 1 (gear4.depth.primary), fast 1
    (gear3.depth.primary), small (utility.step1_cleanup.primary),
    AND big 2 (gear4.breadth.primary)
    when Adversarial Diversity is on (when off the data side mirrors
    big 1 into its breadth counterpart automatically, so that is
    implicitly complete). Fast 2 is an internal Gear-3 breadth slot and
    no longer a card-visible baseline requirement. Image generation is NOT part of
    completeness — it left the configuration schema 2026-06-11 (the
    Visual tab / routing-config slots chain owns image-model choice).
    """
    cells = (config or {}).get("cells") or {}
    big1 = (((cells.get("analysis") or {}).get("gear4") or {}).get("depth") or {}).get("primary")
    big2 = (((cells.get("analysis") or {}).get("gear4") or {}).get("breadth") or {}).get("primary") \
        if isinstance(((cells.get("analysis") or {}).get("gear4") or {}).get("breadth"), dict) else None
    fast1 = (((cells.get("analysis") or {}).get("gear3") or {}).get("depth") or {}).get("primary")
    small = ((cells.get("utility") or {}).get("step1_cleanup") or {}).get("primary")
    saved_toggles = config.get("toggles") if isinstance(config.get("toggles"), dict) else {}
    inferred = _infer_defaults(config)
    adversarial = bool(saved_toggles.get("adversarial_diversity",
                                         inferred.get("adversarial_diversity", False)))
    if not big1 or not fast1 or not small:
        return False
    if adversarial and not big2:
        return False
    return True


def delete_configuration(name: str) -> None:
    """Delete a custom configuration.

    Safety checks (raise ValueError on violation):
      - Cannot delete system configurations (background-default,
        user-pipeline — the migrated defaults that anchor dispatch)
        or the four named presets (free / budget / speed / premium).

    The previous "cannot delete the currently-active" guard has been
    relaxed: deleting the active configuration auto-reverts the
    active pointer to ``free`` (the default-first-run preset). The
    caller is responsible for re-fetching the active state after a
    delete so the UI's "ACTIVE" flag tracks the new pointer.
    """
    if name in {"background-default", "user-pipeline"}:
        raise ValueError(
            f"{name!r} is a system Model Profile and cannot be deleted")
    if name in PRESET_ORDER:
        raise ValueError(
            f"{name!r} is a system preset and cannot be deleted")
    path = _config_path(name)
    if not path.exists():
        raise FileNotFoundError(f"no Model Profile named {name!r}")
    with _lock, rp.locked_file(path):
        if not path.exists():
            raise FileNotFoundError(f"no Model Profile named {name!r}")
        with rp.locked_file(ACTIVE_POINTER_PATH):
            was_active = (name == get_active_name())
            path.unlink()
            if was_active:
                # Free is baked on Models-pane open. Preserve the historical
                # stale-pointer fallback if it is unexpectedly unavailable.
                try:
                    validate_profile_allocation(_load_config("free"))
                    DATA_DIR.mkdir(parents=True, exist_ok=True)
                    rp.atomic_write_text(
                        ACTIVE_POINTER_PATH,
                        json.dumps({"name": "free"}, indent=2) + "\n",
                        mode=0o644,
                    )
                except Exception:
                    pass


def _next_auto_name() -> str:
    """Pick the next available 'Model Profile NN' name (zero-padded
    to 2 digits)."""
    used_numbers: set[int] = set()
    for directory in _configuration_dirs_for_read():
        if directory.exists():
            # Retain old auto-names as issued history while all newly-created
            # profiles use the public G1.16 term.
            for pattern in ("Configuration *.json", "Model Profile *.json"):
                for path in directory.glob(pattern):
                    match = re.fullmatch(r"(?:Configuration|Model Profile) (\d+)", path.stem)
                    if match:
                        used_numbers.add(int(match.group(1)))
    for n in range(1, 1000):
        candidate = f"Model Profile {n:02d}"
        if n not in used_numbers:
            return candidate
    raise RuntimeError("ran out of auto-incremented Model Profile NN names")


# ── Configuration listing for the Models pane ────────────────────────────

# Canonical preset order. Matches the user-locked left-to-right order in
# the Models pane (Free on the left so the default-first-run choice
# anchors the upper-left corner; Premium on the right as the upgrade).
PRESET_ORDER = ["free", "budget", "speed", "premium"]

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
          "speed":   <summary> | null,
          "premium": <summary> | null,
        },
        "preset_errors": {"<preset>": "<exact cause>", ...},
        "customs": [<summary>, ...],
        "active_name": "<name>",
        "active_toggles": {<resolved toggles>},
      }

    A preset slot is the configuration whose ``preset_lineage`` matches
    the preset name; we prefer the canonical-named file (``free.json``,
    ``budget.json``, etc.) and fall back to any file carrying that
    lineage tag. ``null`` when no file claims that lineage.

    ``preset_errors`` carries one line per ``null`` slot saying why the
    last bake attempt did not fill it — an absent catalog, an unreadable
    one, or the exact exception the picker raised for that preset. A slot
    that has a summary never appears there, and a slot that is null with
    no recorded attempt is simply absent.

    Customs are any configuration files NOT matched as a preset and
    not in SYSTEM_CONFIGS (background-default is the automation-side
    fallback, not a user-facing card).

    Each summary carries the three slot picks the pane shows on the
    card: ``big1`` (gear4 depth primary), ``big2`` (gear4 breadth
    primary, may be null), ``small`` (utility step1_cleanup primary).
    """
    readable_dirs = [d for d in _configuration_dirs_for_read() if d.exists()]
    if not readable_dirs:
        return {
            "presets": {p: None for p in PRESET_ORDER},
            "preset_errors": _errors_for_missing({p: None for p in PRESET_ORDER}),
            "customs": [],
            "active_name": get_active_name(),
            "active_toggles": _empty_toggles(),
        }

    # Load every configuration once. Skip malformed; the UI shows a
    # diagnostic in the section that wanted it. Runtime preset files are
    # loaded after seed files, so refreshed preset picks replace checked-in
    # defaults without appearing as separate customs.
    loaded = {}
    for directory in readable_dirs:
        for path in sorted(directory.glob("*.json")):
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
        "preset_errors": _errors_for_missing(presets),
        "customs": customs,
        "active_name": active_name,
        "active_toggles": active_toggles,
    }


def _errors_for_missing(presets: dict) -> dict:
    """Pair every empty preset slot with the cause its last bake recorded."""
    errors = preset_bake_errors()
    return {
        name: errors[name]
        for name, summary in presets.items()
        if summary is None and name in errors
    }


def _summarize(name: str, config: dict) -> dict:
    """Boil a configuration down to the fields the pane card renders.

    Includes per-slot fallback chains so the right-side fallback
    popout can render without a second fetch per card.
    """
    cells = config.get("cells") or {}
    utility = cells.get("utility") or {}
    analysis = cells.get("analysis") or {}
    gear4 = analysis.get("gear4") or {}

    small_cell = utility.get("step1_cleanup") or {}
    big1_cell = gear4.get("depth") or {}
    big2_cell = gear4.get("breadth")
    big2_primary = (big2_cell or {}).get("primary") if isinstance(big2_cell, dict) else None
    big2_fallback = list((big2_cell or {}).get("fallback") or []) if isinstance(big2_cell, dict) else []

    # Fast pair (2026-05-23): gear3.depth + gear3.breadth. Same shape as the
    # Big pair above. Customs that haven't picked Fast yet read as null,
    # which the UI treats as an empty slot waiting to be filled.
    gear3 = analysis.get("gear3") or {}
    fast1_cell = gear3.get("depth") if isinstance(gear3.get("depth"), dict) else {}
    fast2_cell = gear3.get("breadth")
    fast1_primary = (fast1_cell or {}).get("primary")
    fast1_fallback = list((fast1_cell or {}).get("fallback") or [])
    fast2_primary = (fast2_cell or {}).get("primary") if isinstance(fast2_cell, dict) else None
    fast2_fallback = list((fast2_cell or {}).get("fallback") or []) if isinstance(fast2_cell, dict) else []

    toggles_resolved = _infer_defaults(config)
    saved_toggles = config.get("toggles") if isinstance(config.get("toggles"), dict) else {}
    for key in ("adversarial_diversity", "vision_only", "min_context_1m"):
        if key in saved_toggles:
            toggles_resolved[key] = bool(saved_toggles[key])

    post = cells.get("post_analysis") or {}
    consolidation = (post.get("consolidation") or {}).get("primary")
    verification = (post.get("verification") or {}).get("primary")
    visual = big1_cell.get("vision_substitute")  # any cell has it; sample big1
    # Utility override (expand-view): single cell, step1_cleanup. Reads
    # the same cell the SMALL row reports — display value tracks small
    # until the user picks utility independently, at which point both
    # rows continue to show the same value (the override is invisible
    # in the per-cell read; that's intentional given the small→three-
    # cell fan-out). The pick semantics differ: SMALL writes all three
    # utility cells; UTILITY writes only step1_cleanup.
    utility_override = small_cell.get("primary")

    return {
        "name": name,
        "preset_lineage": config.get("preset_lineage"),
        "description": config.get("description") or "",
        "big1": big1_cell.get("primary"),
        "big2": big2_primary,
        "fast1": fast1_primary,
        "fast2": fast2_primary,
        "small": small_cell.get("primary"),
        "big1_fallback": list(big1_cell.get("fallback") or []),
        "big2_fallback": big2_fallback,
        "fast1_fallback": fast1_fallback,
        "fast2_fallback": fast2_fallback,
        "small_fallback": list(small_cell.get("fallback") or []),
        # Expand-view fields (post-analysis cells + visual substitute
        # + utility step-1 cell). 2026-05-22: labels renamed
        # (consolidator → consolidate, verifier → verify). Formatter
        # dropped from the UI per "no format step" — the pipeline step
        # still runs internally with the inherited big-1 model.
        # Utility added as the fourth expand-view row.
        "consolidate": consolidation,
        "verify": verification,
        "utility": utility_override,
        "visual": visual,
        "toggles": toggles_resolved,
        # `incomplete` is now derived live from the cell tree rather than
        # read off a one-shot intent marker: any configuration missing
        # one of its baseline primaries is red-bordered in the UI and
        # gated against activation. The legacy `_incomplete` marker
        # behaves as a hint but no longer needs to be cleared by
        # set_slot_primary — completeness is recomputed every read.
        "incomplete": not _is_baseline_complete(config),
        # Flat list of every primary referenced in the config (any cell
        # at any depth). The UI walks this against the live registry to
        # decide whether to render the yellow deprecated-model border —
        # the per-row deprecation chip handles the per-cell display.
        "all_primaries": _collect_all_primaries(config),
        # Per-cell loosening notes from the auto-populate bake
        # (_auto_populate_metadata.loosening_log): cell path → list of
        # human-readable reasons a constraint (e.g. vision_only) was
        # relaxed for that cell. The pane renders a footnote on the
        # card when non-empty so the user knows why a slot holds a
        # model that doesn't match the toggles. Customs read as {} —
        # duplicate_configuration strips the auto-populate metadata.
        "loosening_log": _loosening_log(config),
    }


def _loosening_log(config: dict) -> dict:
    """Extract the auto-populate loosening log, normalized to
    {cell_path: [note, ...]}. Malformed shapes degrade to {}."""
    meta = config.get("_auto_populate_metadata")
    if not isinstance(meta, dict):
        return {}
    log = meta.get("loosening_log")
    if not isinstance(log, dict):
        return {}
    out: dict = {}
    for cell, notes in log.items():
        if isinstance(notes, str):
            notes = [notes]
        if not isinstance(notes, list):
            continue
        cleaned = [n for n in notes if isinstance(n, str) and n.strip()]
        if cleaned:
            out[str(cell)] = cleaned
    return out


def _collect_all_primaries(config: dict) -> list[str]:
    """Walk every cell in the config and return the de-duplicated set of
    model ids assigned as a primary. Used by the UI to detect whether
    any cell references a model that has dropped out of the registry."""
    seen: set = set()
    out: list = []

    def visit(node):
        if isinstance(node, dict):
            primary = node.get("primary")
            if isinstance(primary, str) and primary not in seen:
                seen.add(primary)
                out.append(primary)
            for k, v in node.items():
                if k == "primary":
                    continue
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(config.get("cells") or {})
    return out


def _empty_toggles() -> dict:
    return {"adversarial_diversity": False, "vision_only": False,
            "min_context_1m": False}


# ── Slot pick — assign a model to a configuration's visible slot ─────────

# Card-level slot label → list of cells.* paths the pick writes to.
# The "small + 2 big" abstraction the Models pane shows hides the full
# slot graph; one pick fans out to multiple internal cells so the
# expand view (step 11) doesn't have to be open for the basic picker
# to do the obvious thing.
SLOT_LABEL_TO_PATHS = {
    "big 1": [
        ["analysis", "gear4", "depth"],
        # gear3.depth handed off to Fast 1 (2026-05-23) per the four-gear
        # architecture: Big lives only in Gear 4; Fast owns Gear 3 + the
        # Gear 2 RAG lookup. See the parallel boot.py dispatch update.
        ["post_analysis", "consolidation"],
        ["post_analysis", "verification"],
        ["post_analysis", "formatter"],
    ],
    "big 2": [
        ["analysis", "gear4", "breadth"],
    ],
    # Fast: mid-tier speed-optimized slot. Fast 1 fills both gear3.depth
    # (sequential adversarial) and utility.gear2_rag_lookup (single-pass
    # retrieval). Fast 2 fills gear3.breadth when adversarial diversity
    # is on; mirrors of how Big 1 / Big 2 fan into gear4.
    "fast 1": [
        ["analysis", "gear3", "depth"],
        ["utility", "gear2_rag_lookup"],
    ],
    "fast 2": [
        ["analysis", "gear3", "breadth"],
    ],
    "small": [
        ["utility", "step1_cleanup"],
        ["utility", "classification"],
        ["utility", "rag_planner"],
    ],
    # Expand-view slots: individual overrides that break the default
    # inheritance from a card-body slot. Picking any of these writes
    # to a single cell; the next big-1 / small pick will overwrite
    # them (user re-picks here if they want the override to stick).
    # 2026-05-22: labels renamed (consolidator → consolidate,
    # verifier → verify) to match the publisher's expand-view spec.
    # ``formatter`` retired from the UI per "no format step" — the
    # pipeline still runs the formatter step internally, just always
    # with the inherited big-1 model. ``utility`` added as a single-
    # cell override for step1_cleanup (mirrors how consolidate /
    # verify override post-analysis cells).
    "consolidate": [["post_analysis", "consolidation"]],
    "verify":      [["post_analysis", "verification"]],
    "utility":     [["utility", "step1_cleanup"]],
}


# Visual substitute is special — it's a field on EVERY cell, not a
# cell of its own. set_visual_substitute writes the picked model to
# every cell's vision_substitute field so text-only primaries route
# their image-bearing inputs through one consistent fallback.
def set_visual_substitute(name: str, model_id: str) -> dict:
    """Assign a model to every cell's vision_substitute field."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id must be a non-empty string")
    model_id = model_id.strip()
    target_path = _config_path(name, for_write=True)
    with _lock, rp.locked_file(target_path):
        config = _load_config(name)
        cells = config.setdefault("cells", {})
        _walk_and_set_vision_substitute(cells, model_id)
        validate_profile_allocation(config)
        _save_config(name, config, _locked=True)
    return config


def _walk_and_set_vision_substitute(node, model_id):
    if not isinstance(node, dict):
        return
    if "primary" in node:
        node["vision_substitute"] = model_id
        return
    for v in node.values():
        _walk_and_set_vision_substitute(v, model_id)


def set_slot_primary(name: str, slot_label: str, model_id: str) -> dict:
    """Assign a model to a visible slot on a configuration.

    ``slot_label`` is one of "big 1" / "big 2" / "fast 1" / "fast 2" /
    "small". The helper fans the pick out to every internal cell path
    that label maps to (see SLOT_LABEL_TO_PATHS) so post-analysis slots
    that "inherit big 1" — and the gear3 cells that Fast 1 covers —
    track the change without the user opening the expand view.

    Returns the updated configuration dict.
    """
    if slot_label not in SLOT_LABEL_TO_PATHS:
        raise ValueError(f"unknown slot label: {slot_label!r}")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id must be a non-empty string")
    model_id = model_id.strip()

    target_path = _config_path(name, for_write=True)
    with _lock, rp.locked_file(target_path):
        config = _load_config(name)
        cells = config.setdefault("cells", {})
        for path in SLOT_LABEL_TO_PATHS[slot_label]:
            node = cells
            for key in path[:-1]:
                if not isinstance(node.get(key), dict):
                    node[key] = {}
                node = node[key]
            existing = node.get(path[-1])
            if isinstance(existing, dict):
                existing["primary"] = model_id
            else:
                node[path[-1]] = {
                    "primary": model_id,
                    "fallback": [],
                }
        # Clear the _incomplete marker once the four baseline slots are
        # all filled. This is one-way: once cleared, future slot edits
        # (e.g. user blanks a slot to test something) do NOT re-flag the
        # configuration as incomplete — the marker is the "started from
        # scratch, not yet finished" signal, not a live completeness
        # check.
        if config.get("_incomplete") and _is_baseline_complete(config):
            config.pop("_incomplete", None)
        validate_profile_allocation(config)
        _save_config(name, config, _locked=True)
    return config


# Popout-section label → single cell path. Fallback writes target one
# cell only (no fan-out): the popout edits the chain that lives behind
# the specific big/fast/small position, not the SMALL / BIG-1 / FAST-1 fan-out
# set the card-body rows trigger.
POPOUT_LABEL_TO_CELL = {
    "large": ["analysis", "gear4", "depth"],
    "fast": ["analysis", "gear3", "depth"],
    "small": ["utility", "step1_cleanup"],
}


def set_slot_fallback(name: str, popout_label: str, index: int, model_id: str) -> dict:
    """Replace one fallback position in a popout-section's chain.

    ``popout_label`` is one of "large" / "fast" / "small" — the
    sections the fallback popout renders. ``index`` is the 0-based
    position inside the cell's ``fallback`` list. ``model_id`` is the
    replacement. Pass an empty string to remove the position
    (compacts the list, shifting later entries up).

    Writes a single cell only (no fan-out). The card-body SMALL /
    BIG 1 rows handle the fan-out path for primary picks; fallback
    chains live per-cell.

    Returns the updated configuration dict.
    """
    if popout_label not in POPOUT_LABEL_TO_CELL:
        raise ValueError(f"unknown popout label: {popout_label!r}")
    try:
        index = int(index)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"index must be an integer, got {index!r}") from exc
    if index < 0:
        raise ValueError(f"fallback index must be >= 0, got {index}")
    if not isinstance(model_id, str):
        raise ValueError("model_id must be a string")
    model_id = model_id.strip()  # empty → delete

    path = POPOUT_LABEL_TO_CELL[popout_label]
    target_path = _config_path(name, for_write=True)
    with _lock, rp.locked_file(target_path):
        config = _load_config(name)
        cells = config.setdefault("cells", {})
        node = cells
        for key in path[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        cell = node.get(path[-1])
        if not isinstance(cell, dict):
            cell = {"primary": None, "fallback": []}
            node[path[-1]] = cell
        fallback = cell.setdefault("fallback", [])
        if not isinstance(fallback, list):
            fallback = []
            cell["fallback"] = fallback
        if not model_id:
            # Delete the position (compacts list)
            if 0 <= index < len(fallback):
                fallback.pop(index)
        else:
            # Replace at index, extending the list if needed
            while len(fallback) <= index:
                fallback.append(None)
            fallback[index] = model_id
            # Strip trailing Nones (housekeeping)
            while fallback and fallback[-1] is None:
                fallback.pop()
        validate_profile_allocation(config)
        _save_config(name, config, _locked=True)
    return config


__all__ = [
    "get_active_name",
    "set_active_name",
    "get_toggles",
    "set_toggles",
    "get_preset_toggles",
    "set_preset_toggles",
    "bake_missing_presets",
    "preset_bake_errors",
    "list_configurations",
    "duplicate_configuration",
    "create_blank_configuration",
    "delete_configuration",
    "set_slot_primary",
    "set_slot_fallback",
    "POPOUT_LABEL_TO_CELL",
    "set_visual_substitute",
    "profile_ram_allocation",
    "validate_profile_allocation",
    "AUTOMATIC_RAM_TARGET_RATIO",
    "HARD_RAM_CAP_RATIO",
    "DEFAULT_ACTIVE_NAME",
    "PRESET_ORDER",
    "SLOT_LABEL_TO_PATHS",
]
