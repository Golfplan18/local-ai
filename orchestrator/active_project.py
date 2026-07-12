"""Active-project pointer (G1.33).

Mirrors ``active_configuration.py``: a single pointer file at
``~/ora/data/active-project.json`` records which project NEW conversations
bind to. The default is the synthetic ``Commons`` project (sentinel
``"commons"``), which maps to an EMPTY ``project_ids`` list — and therefore
an empty ``nexus:`` on vault export per the Schema §10 domain-general
convention.

Nexus-id rename (2026-07-11): the sentinel used to be ``"general"``; it is
now ``"commons"``, matching the display name set in the prior
display-string-only pass (PR #211). ``LEGACY_DEFAULT`` keeps every
comparison honoring the old value too, permanently — not a one-time
migration — because it is already live in on-disk pointer files, browser
``localStorage``, and any not-yet-redeployed cloud instance.

The switcher (sidebar, top) sets this pointer; conversation membership is
stamped at creation by passing the resolved ``project_ids`` to
``conversation_memory.save_turn_spatial_state`` (which honors it on first
save only). A later sub-step will let the frontend send the project
explicitly with the new-conversation request to remove any reliance on the
global pointer at save time.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
DATA_DIR = ORA_HOME / "data"
ACTIVE_PROJECT_POINTER = DATA_DIR / "active-project.json"

# The synthetic default project. Never stored on a conversation (an empty
# ``project_ids`` == Commons); resolves to an empty nexus on export.
DEFAULT = "commons"
LEGACY_DEFAULT = "general"  # pre-2026-07-11 id; still recognized everywhere

_lock = threading.RLock()


def get_active_project() -> str:
    """Return the active project nexus, or ``"commons"`` when unset/malformed."""
    if not ACTIVE_PROJECT_POINTER.exists():
        return DEFAULT
    try:
        with open(ACTIVE_PROJECT_POINTER) as f:
            data = json.load(f)
        nexus = data.get("nexus") if isinstance(data, dict) else None
        if isinstance(nexus, str) and nexus.strip():
            return nexus.strip()
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT


def set_active_project(nexus: str | None) -> None:
    """Persist the active project nexus (atomic write).

    ``"commons"`` / ``"general"`` (legacy) / empty / ``None`` reset to the
    default. Validation that a given project actually exists is
    intentionally NOT done here yet — the project record + creation flow
    land in a later G1.33 sub-step; until then any non-empty slug is
    accepted so the switcher can be wired first.
    """
    slug = (nexus or "").strip() or DEFAULT
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ACTIVE_PROJECT_POINTER.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({"nexus": slug}, f, indent=2)
            f.write("\n")
        os.replace(tmp, ACTIVE_PROJECT_POINTER)


def resolve_project_ids(nexus: str | None) -> list[str]:
    """Map an active-project nexus to the ``project_ids`` stamped on a NEW
    conversation. Commons (default / empty / legacy "general") -> ``[]``
    (the implicit baseline, never stored)."""
    if not nexus:
        return []
    slug = nexus.strip()
    if not slug or slug.lower() in (DEFAULT, LEGACY_DEFAULT):
        return []
    return [slug]


__all__ = [
    "DEFAULT",
    "LEGACY_DEFAULT",
    "ACTIVE_PROJECT_POINTER",
    "get_active_project",
    "set_active_project",
    "resolve_project_ids",
]
