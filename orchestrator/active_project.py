"""Active-project pointer (G1.33).

Mirrors ``active_configuration.py``: a single pointer file at
``~/ora/data/active-project.json`` records which project NEW conversations
bind to. The default is the synthetic ``General`` project (sentinel
``"general"``), which maps to an EMPTY ``project_ids`` list — and therefore
an empty ``nexus:`` on vault export per the Schema §10 domain-general
convention.

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
# ``project_ids`` == General); resolves to an empty nexus on export.
GENERAL = "general"

_lock = threading.RLock()


def get_active_project() -> str:
    """Return the active project nexus, or ``"general"`` when unset/malformed."""
    if not ACTIVE_PROJECT_POINTER.exists():
        return GENERAL
    try:
        with open(ACTIVE_PROJECT_POINTER) as f:
            data = json.load(f)
        nexus = data.get("nexus") if isinstance(data, dict) else None
        if isinstance(nexus, str) and nexus.strip():
            return nexus.strip()
    except (OSError, json.JSONDecodeError):
        pass
    return GENERAL


def set_active_project(nexus: str | None) -> None:
    """Persist the active project nexus (atomic write).

    ``"general"`` / empty / ``None`` reset to the default. Validation that a
    given project actually exists is intentionally NOT done here yet — the
    project record + creation flow land in a later G1.33 sub-step; until
    then any non-empty slug is accepted so the switcher can be wired first.
    """
    slug = (nexus or "").strip() or GENERAL
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = ACTIVE_PROJECT_POINTER.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({"nexus": slug}, f, indent=2)
            f.write("\n")
        os.replace(tmp, ACTIVE_PROJECT_POINTER)


def resolve_project_ids(nexus: str | None) -> list[str]:
    """Map an active-project nexus to the ``project_ids`` stamped on a NEW
    conversation. General (default / empty) -> ``[]`` (the implicit baseline,
    never stored)."""
    if not nexus:
        return []
    slug = nexus.strip()
    if not slug or slug.lower() == GENERAL:
        return []
    return [slug]


__all__ = [
    "GENERAL",
    "ACTIVE_PROJECT_POINTER",
    "get_active_project",
    "set_active_project",
    "resolve_project_ids",
]
