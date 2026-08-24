"""Curated user-invocable framework registry.

This module is the boundary between framework files that the runtime may load
internally and framework files a user may see or invoke. File existence in
``frameworks/book`` is deliberately not treated as permission to expose a
framework.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "framework-invocability.json"
)

GEAR4_INTERNAL_STAGE_IDS = {
    "f-analysis-breadth",
    "f-analysis-depth",
    "f-consult",
    "f-evaluate",
    "f-revise",
    "f-verify",
    "f-consolidate",
    "f-format",
}


class FrameworkInvocabilityError(ValueError):
    """Raised when a framework token is not user-invocable."""


@dataclass(frozen=True)
class FrameworkInvocabilityRegistry:
    invocable_by_key: dict[str, str]
    pickable_ids: set[str]
    internal_only_ids: set[str]


def _normalize_key(value: str) -> str:
    name = Path((value or "").strip()).name
    if name.endswith(".md"):
        name = name[:-3]
    return name.lower()


def _filename(value: str) -> str:
    name = Path((value or "").strip()).name
    return name if name.endswith(".md") else f"{name}.md"


@lru_cache(maxsize=1)
def load_framework_invocability_registry() -> FrameworkInvocabilityRegistry:
    with open(CONFIG_PATH) as f:
        raw = json.load(f) or {}

    invocable_by_key: dict[str, str] = {}
    for item in raw.get("invocable_frameworks", []) or []:
        filename = _filename(item)
        stem = _normalize_key(filename)
        invocable_by_key[stem] = filename

    for alias, target in (raw.get("aliases", {}) or {}).items():
        target_key = _normalize_key(target)
        target_filename = invocable_by_key.get(target_key)
        if target_filename:
            invocable_by_key[_normalize_key(alias)] = target_filename

    pickable_values = raw.get("pickable_frameworks")
    if pickable_values is None:
        pickable_values = raw.get("invocable_frameworks", []) or []
    pickable_ids = {
        _normalize_key(item)
        for item in pickable_values
    }

    internal_only_ids = {
        _normalize_key(item)
        for item in raw.get("internal_only_frameworks", []) or []
    }
    internal_only_ids.update(GEAR4_INTERNAL_STAGE_IDS)

    for internal_id in internal_only_ids:
        invocable_by_key.pop(internal_id, None)
        pickable_ids.discard(internal_id)

    return FrameworkInvocabilityRegistry(
        invocable_by_key=invocable_by_key,
        pickable_ids=pickable_ids,
        internal_only_ids=internal_only_ids,
    )


def reset_framework_invocability_registry_cache() -> None:
    load_framework_invocability_registry.cache_clear()


def is_internal_only_framework(value: str) -> bool:
    registry = load_framework_invocability_registry()
    return _normalize_key(value) in registry.internal_only_ids


def _internal_only_message(value: str) -> str:
    key = _normalize_key(value)
    display = key or value
    if key in GEAR4_INTERNAL_STAGE_IDS:
        return (
            f"{display} is an internal Gear 4 F-* pipeline stage spec, not a "
            "user-invocable framework. The pipeline loads F-* stages "
            "automatically; use a public framework such as `/framework pff "
            "F-Design ...` when you want to run framework work directly."
        )
    return (
        f"{display} is an internal pipeline support spec, not a "
        "user-invocable framework."
    )


def resolve_user_invocable_framework(value: str) -> str:
    """Return the canonical framework filename for a user-facing token.

    Accepts public IDs, canonical filename stems with or without ``.md``,
    plus configured aliases. The returned filename is the internal framework
    identity used by the parser and executor.
    Raises ``FrameworkInvocabilityError`` when the token is internal-only or
    not listed in the curated registry.
    """
    key = _normalize_key(value)
    if not key:
        raise FrameworkInvocabilityError(
            "missing framework name; usage: /framework <name> [<query>]"
        )

    registry = load_framework_invocability_registry()
    if key in registry.internal_only_ids:
        raise FrameworkInvocabilityError(_internal_only_message(value))

    filename = registry.invocable_by_key.get(key)
    if filename:
        return filename

    raise FrameworkInvocabilityError(
        f"{value} is not registered as a user-invocable framework. "
        "Framework files must be listed in config/framework-invocability.json "
        "before they can be run with /framework."
    )


def is_user_invocable_framework(value: str) -> bool:
    try:
        resolve_user_invocable_framework(value)
    except FrameworkInvocabilityError:
        return False
    return True


def is_user_pickable_framework(value: str) -> bool:
    registry = load_framework_invocability_registry()
    key = _normalize_key(value)
    return key in registry.pickable_ids and key not in registry.internal_only_ids


def user_invocable_framework_ids() -> list[str]:
    """Return the public IDs for all user-invocable framework files.

    Public aliases in the pickable registry replace the legacy filename stem
    when one exists. Internal callers can still pass either public IDs or
    canonical filename stems to ``resolve_user_invocable_framework``.
    """
    registry = load_framework_invocability_registry()
    public_id_by_filename = {}
    for public_id in registry.pickable_ids:
        filename = registry.invocable_by_key.get(public_id)
        if filename:
            public_id_by_filename.setdefault(filename, public_id)
    ids = {
        public_id_by_filename.get(filename, _normalize_key(filename))
        for filename in registry.invocable_by_key.values()
    }
    return sorted(ids)


def user_pickable_framework_ids() -> list[str]:
    registry = load_framework_invocability_registry()
    return sorted(registry.pickable_ids)
