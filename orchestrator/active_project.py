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

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
DATA_DIR = ORA_HOME / "data"
ACTIVE_PROJECT_POINTER = DATA_DIR / "active-project.json"

# The synthetic default project. Never stored on a conversation (an empty
# ``project_ids`` == Commons); resolves to an empty nexus on export.
DEFAULT = "commons"
LEGACY_DEFAULT = "general"  # pre-2026-07-11 id; still recognized everywhere

# Deprecated compatibility alias.  ``GENERAL`` was the public constant before
# the sentinel rename; keep its historical value so out-of-tree imports do not
# fail or silently change meaning.
GENERAL = LEGACY_DEFAULT

_lock = threading.RLock()


def canonicalize_project_nexus(nexus: str | None) -> str:
    """Return the canonical runtime project id for an input value.

    The default project's current and legacy ids are compared
    case-insensitively and always collapse to ``"commons"``.  Real project
    ids are only stripped: callers that validate project slugs remain
    responsible for that validation.
    """
    slug = (nexus or "").strip()
    if not slug or slug.lower() in (DEFAULT, LEGACY_DEFAULT):
        return DEFAULT
    return slug


def project_nexus_fields(nexus: str | None) -> dict[str, str]:
    """Return an expand-phase wire/persistence representation.

    New readers use ``canonical_nexus``.  Pre-rename readers ignore that key
    and read ``nexus``, where Commons deliberately remains ``"general"``.
    Real project ids are identical in both fields.
    """
    canonical = canonicalize_project_nexus(nexus)
    legacy_safe = LEGACY_DEFAULT if canonical == DEFAULT else canonical
    return {"nexus": legacy_safe, "canonical_nexus": canonical}


def _write_active_project_unlocked(slug: str) -> None:
    """Write a canonical id atomically while the sidecar lock is held."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVE_PROJECT_POINTER.with_name(
        f".{ACTIVE_PROJECT_POINTER.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with open(tmp, "w") as f:
            json.dump(project_nexus_fields(slug), f, indent=2)
            f.write("\n")
        os.replace(tmp, ACTIVE_PROJECT_POINTER)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def get_active_project() -> str:
    """Return the canonical active project id.

    ``canonical_nexus`` is preferred when present.  This function is a pure
    read: migration is deliberately handled by
    :func:`migrate_active_project_pointer` before the server starts accepting
    requests.  Keeping reads side-effect-free prevents a stale reader from
    overwriting a concurrent explicit project selection.
    """
    try:
        with _lock:
            if not ACTIVE_PROJECT_POINTER.exists():
                return DEFAULT
            with open(ACTIVE_PROJECT_POINTER) as f:
                data = json.load(f)
            if isinstance(data, dict):
                canonical_value = data.get("canonical_nexus")
                legacy_value = data.get("nexus")
                source = (
                    canonical_value
                    if isinstance(canonical_value, str) and canonical_value.strip()
                    else legacy_value
                )
            else:
                source = None
            if isinstance(source, str) and source.strip():
                return canonicalize_project_nexus(source)
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT


def migrate_active_project_pointer() -> bool:
    """Expand an existing pointer to the dual old/new-reader representation.

    This is an explicit startup migration, not a read-path side effect.  The
    server invokes it before worker threads and HTTP requests begin, so a
    legacy-only ``general`` pointer and PR-218's canonical-only ``commons``
    pointer both become rollback-safe without racing a live selection.

    Returns ``True`` when the pointer was rewritten, otherwise ``False``.
    Missing or malformed pointers remain untouched and continue to resolve to
    Commons through :func:`get_active_project`.
    """
    with _lock:
        try:
            with _rp.locked_file(ACTIVE_PROJECT_POINTER):
                if not ACTIVE_PROJECT_POINTER.exists():
                    return False
                try:
                    with open(ACTIVE_PROJECT_POINTER) as f:
                        data = json.load(f)
                except (OSError, json.JSONDecodeError):
                    return False
                if not isinstance(data, dict):
                    return False
                canonical_value = data.get("canonical_nexus")
                legacy_value = data.get("nexus")
                source = (
                    canonical_value
                    if isinstance(canonical_value, str) and canonical_value.strip()
                    else legacy_value
                )
                if not isinstance(source, str) or not source.strip():
                    return False
                canonical = canonicalize_project_nexus(source)
                expected = project_nexus_fields(canonical)
                if all(data.get(key) == value for key, value in expected.items()):
                    return False
                _write_active_project_unlocked(canonical)
        except (OSError, TimeoutError):
            return False
        return True


def set_active_project(nexus: str | None) -> None:
    """Persist the active project nexus (atomic write).

    ``"commons"`` / ``"general"`` (legacy) / empty / ``None`` reset to the
    default. Validation that a given project actually exists is
    intentionally NOT done here yet — the project record + creation flow
    land in a later G1.33 sub-step; until then any non-empty slug is
    accepted so the switcher can be wired first.
    """
    slug = canonicalize_project_nexus(nexus)
    with _lock:
        with _rp.locked_file(ACTIVE_PROJECT_POINTER):
            _write_active_project_unlocked(slug)


def resolve_project_ids(nexus: str | None) -> list[str]:
    """Map an active-project nexus to the ``project_ids`` stamped on a NEW
    conversation. Commons (default / empty / legacy "general") -> ``[]``
    (the implicit baseline, never stored)."""
    slug = canonicalize_project_nexus(nexus)
    if slug == DEFAULT:
        return []
    return [slug]


__all__ = [
    "DEFAULT",
    "LEGACY_DEFAULT",
    "GENERAL",
    "ACTIVE_PROJECT_POINTER",
    "canonicalize_project_nexus",
    "project_nexus_fields",
    "get_active_project",
    "migrate_active_project_pointer",
    "set_active_project",
    "resolve_project_ids",
]
