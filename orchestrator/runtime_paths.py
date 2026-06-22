"""Runtime overlay paths for generated model-routing state.

Checked-in files under ``config/`` are seed defaults. Live model refreshes are
derived from outside provider catalogs, so the server writes them under
``data/runtime/`` and readers prefer those runtime copies when present.
"""
from __future__ import annotations

import os
from pathlib import Path

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
CONFIG_DIR = ORA_HOME / "config"
DATA_DIR = ORA_HOME / "data"
RUNTIME_ROOT = Path(os.environ.get("ORA_RUNTIME_ROOT") or (DATA_DIR / "runtime"))
RUNTIME_CONFIG_DIR = RUNTIME_ROOT / "config"
RUNTIME_DATA_DIR = RUNTIME_ROOT / "data"
RUNTIME_CONFIGURATIONS_DIR = RUNTIME_CONFIG_DIR / "configurations"

PRESET_NAMES = ("free", "budget", "optimum", "premium")
RUNTIME_OVERLAY_CONFIGURATION_NAMES = PRESET_NAMES + ("user-pipeline",)


def seed_path(*parts: str) -> Path:
    return ORA_HOME.joinpath(*parts)


def runtime_path(*parts: str) -> Path:
    return RUNTIME_ROOT.joinpath(*parts)


def overlay_path(*parts: str) -> Path:
    """Return the runtime copy when it exists, otherwise the seed path."""
    runtime = runtime_path(*parts)
    return runtime if runtime.exists() else seed_path(*parts)


def env_or_seed(env_name: str, *seed_parts: str) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else seed_path(*seed_parts)


def env_or_runtime(env_name: str, *runtime_parts: str) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else runtime_path(*runtime_parts)


def model_registry_path() -> Path:
    value = os.environ.get("ORA_MODEL_REGISTRY_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "model-registry.json")


def model_catalog_path() -> Path:
    value = os.environ.get("ORA_MODEL_CATALOG_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "model-catalog.json")


def vendor_authoritative_registry_path() -> Path:
    value = os.environ.get("ORA_VENDOR_AUTH_REGISTRY_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "model-registry.vendor-authoritative.json")


def routing_config_path() -> Path:
    value = os.environ.get("ORA_ROUTING_CONFIG_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "routing-config.json")


def routing_config_write_path() -> Path:
    value = os.environ.get("ORA_ROUTING_CONFIG_PATH")
    if value:
        return Path(value)
    runtime = runtime_path("config", "routing-config.json")
    return runtime if runtime.exists() else seed_path("config", "routing-config.json")


def configuration_seed_path(name: str) -> Path:
    return CONFIG_DIR / "configurations" / f"{name}.json"


def configuration_runtime_path(name: str) -> Path:
    return RUNTIME_CONFIGURATIONS_DIR / f"{name}.json"


def configuration_path(name: str, *, for_write: bool = False) -> Path:
    if name in RUNTIME_OVERLAY_CONFIGURATION_NAMES:
        runtime = configuration_runtime_path(name)
        if for_write or runtime.exists():
            return runtime
    return configuration_seed_path(name)


def configuration_dirs_for_read() -> list[Path]:
    dirs = [CONFIG_DIR / "configurations"]
    if RUNTIME_CONFIGURATIONS_DIR.exists():
        dirs.append(RUNTIME_CONFIGURATIONS_DIR)
    return dirs


def runtime_refresh_env() -> dict[str, str]:
    """Environment overlay used by the server-side model refresh chain."""
    return {
        "ORA_MODEL_REGISTRY_PATH": str(RUNTIME_CONFIG_DIR / "model-registry.json"),
        "ORA_MODEL_REGISTRY_DISCREPANCY_PATH": str(
            RUNTIME_DATA_DIR / "model-registry-discrepancies.jsonl"
        ),
        "ORA_MODEL_CATALOG_PATH": str(RUNTIME_CONFIG_DIR / "model-catalog.json"),
        "ORA_MODEL_CATALOG_CHANGES_PATH": str(
            RUNTIME_DATA_DIR / "model-catalog-changes.jsonl"
        ),
        "ORA_VENDOR_AUTH_REGISTRY_PATH": str(
            RUNTIME_CONFIG_DIR / "model-registry.vendor-authoritative.json"
        ),
        "ORA_ROUTING_CONFIG_PATH": str(RUNTIME_CONFIG_DIR / "routing-config.json"),
        "ORA_CONFIGURATIONS_DIR": str(RUNTIME_CONFIGURATIONS_DIR),
    }


def ensure_runtime_dirs() -> None:
    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIGURATIONS_DIR.mkdir(parents=True, exist_ok=True)
