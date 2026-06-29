"""Project records (G1.33) — the conversation-container metadata layer.

A project's record lives in its pointer file ``~/ora/data/projects/<nexus>.json``
— the SAME file the plugin registry uses ("unify the two meanings"). The two
views coexist over one set of files:

  * plugin view (``project_registry.list_projects``): pointers that carry a
    ``root`` → an ``ora-project.json`` manifest (tools / frameworks / slash
    commands).
  * container view (this module): every pointer, read for the conversation-
    container fields below — ``name``, ``status``, ``last_accessed_at``, and
    the inert default slots. A project may be BOTH (a plugin that also holds
    conversations) or container-only (no ``root``).

``General`` is synthetic — never a pointer file. An empty conversation
``project_ids`` == General, and General is the all-inclusive view (a thread in
project X is still visible under General).
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

POINTER_DIR = Path(os.path.expanduser("~/ora/data/projects"))

# Same rule the plugin registry enforces on a manifest nexus.
_NEXUS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

GENERAL_NEXUS = "general"
PROJECT_STATUSES = ("active", "inactive", "archived")
RESERVED_NEXUS = {GENERAL_NEXUS, ""}

# Inert default slots added now (G1.33 decision 3): wired as the model-profile,
# style, and persona sub-steps land. ``private`` and the profile are honored
# earliest; style/persona stay inert until G1.36/G1.37.
_DEFAULT_SLOTS: dict[str, Any] = {
    "default_model_profile": None,
    "interaction_style": None,
    "output_style": None,
    "persona": None,
    "model_locks": {},
    "private": False,
}

_lock = threading.RLock()


class ProjectMetaError(Exception):
    pass


def _pointer_path(nexus: str, pointer_dir: Path | None = None) -> Path:
    return (pointer_dir or POINTER_DIR) / f"{nexus}.json"


def slugify_nexus(name: str) -> str:
    """Derive a lowercase kebab-case nexus slug from a display name."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def general_meta() -> dict[str, Any]:
    """The synthetic, all-inclusive default project."""
    return {
        "nexus": GENERAL_NEXUS,
        "name": "General",
        "status": "active",
        "is_default": True,
        "is_plugin": False,
        "created": None,
        "last_accessed_at": None,
        **dict(_DEFAULT_SLOTS),
    }


def _normalize_meta(nexus: str, data: dict) -> dict[str, Any]:
    name = data.get("name")
    status = data.get("status")
    meta: dict[str, Any] = {
        "nexus": nexus,
        "name": name.strip() if isinstance(name, str) and name.strip() else nexus,
        "status": status if status in PROJECT_STATUSES else "active",
        "is_default": False,
        "is_plugin": bool(data.get("root")),
        "created": data.get("created"),
        "last_accessed_at": data.get("last_accessed_at"),
    }
    for key, default in _DEFAULT_SLOTS.items():
        meta[key] = data.get(key, default)
    return meta


def read_project_meta(nexus: str, pointer_dir: Path | None = None) -> dict[str, Any] | None:
    if nexus == GENERAL_NEXUS:
        return general_meta()
    pf = _pointer_path(nexus, pointer_dir)
    if not pf.is_file():
        return None
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_meta(nexus, data)


def list_project_meta(pointer_dir: Path | None = None) -> list[dict[str, Any]]:
    """All projects: General first, then real projects by recency
    (``last_accessed_at`` desc, unset last)."""
    pdir = pointer_dir or POINTER_DIR
    out: list[dict[str, Any]] = []
    if pdir.is_dir():
        for pf in pdir.glob("*.json"):
            nexus = pf.stem
            if not _NEXUS_RE.match(nexus):
                continue
            meta = read_project_meta(nexus, pointer_dir)
            if meta:
                out.append(meta)
    out.sort(key=lambda m: (m.get("last_accessed_at") or ""), reverse=True)
    return [general_meta()] + out


def _write_pointer(nexus: str, data: dict, pointer_dir: Path | None = None) -> Path:
    pdir = pointer_dir or POINTER_DIR
    pdir.mkdir(parents=True, exist_ok=True)
    pf = _pointer_path(nexus, pointer_dir)
    tmp = pf.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, pf)
    return pf


def create_project(name: str, pointer_dir: Path | None = None) -> dict[str, Any]:
    """Create a container project record from a display name.

    Derives a kebab nexus from the name, refuses reserved/colliding nexuses,
    and writes the pointer. The vault project folder + graceful MOM run in the
    creation flow (a later sub-step), not here — this is the record only.
    """
    nexus = slugify_nexus(name)
    if not nexus or not _NEXUS_RE.match(nexus):
        raise ProjectMetaError(f"could not derive a valid nexus from name {name!r}")
    if nexus in RESERVED_NEXUS:
        raise ProjectMetaError(f"{nexus!r} is reserved")
    with _lock:
        if _pointer_path(nexus, pointer_dir).exists():
            raise ProjectMetaError(f"a project named {nexus!r} already exists")
        now = datetime.now().isoformat(timespec="seconds")
        data = {
            "nexus": nexus,
            "name": (name or nexus).strip(),
            "status": "active",
            "created": now,
            "last_accessed_at": now,
            **dict(_DEFAULT_SLOTS),
        }
        _write_pointer(nexus, data, pointer_dir)
    return _normalize_meta(nexus, data)


def _update_pointer(nexus: str, mutate, pointer_dir: Path | None = None) -> dict[str, Any] | None:
    if nexus == GENERAL_NEXUS:
        return general_meta()  # synthetic — nothing to persist
    with _lock:
        pf = _pointer_path(nexus, pointer_dir)
        if not pf.is_file():
            return None
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        data.setdefault("nexus", nexus)
        mutate(data)
        _write_pointer(nexus, data, pointer_dir)
    return _normalize_meta(nexus, data)


def set_project_status(nexus: str, status: str, pointer_dir: Path | None = None) -> dict[str, Any] | None:
    if status not in PROJECT_STATUSES:
        raise ProjectMetaError(f"status must be one of {PROJECT_STATUSES}; got {status!r}")
    return _update_pointer(nexus, lambda d: d.__setitem__("status", status), pointer_dir)


def touch_project(nexus: str, pointer_dir: Path | None = None) -> dict[str, Any] | None:
    """Bump ``last_accessed_at`` (drives the switcher's recency sort)."""
    now = datetime.now().isoformat(timespec="seconds")
    return _update_pointer(nexus, lambda d: d.__setitem__("last_accessed_at", now), pointer_dir)


# Fields the management modal / API may patch on a project record.
_UPDATABLE_FIELDS = {
    "name", "status", "default_model_profile", "interaction_style",
    "output_style", "persona", "model_locks", "private", "last_accessed_at",
}


def update_project_meta(
    nexus: str, updates: dict, pointer_dir: Path | None = None
) -> dict[str, Any] | None:
    """Patch whitelisted fields on a project record. Unknown fields are ignored;
    an invalid ``status``/``name`` raises. General is synthetic (no-op)."""
    clean = {k: v for k, v in (updates or {}).items() if k in _UPDATABLE_FIELDS}
    if "status" in clean and clean["status"] not in PROJECT_STATUSES:
        raise ProjectMetaError(
            f"status must be one of {PROJECT_STATUSES}; got {clean['status']!r}"
        )
    if "name" in clean:
        nm = clean["name"]
        if not isinstance(nm, str) or not nm.strip():
            raise ProjectMetaError("name must be a non-empty string")
        clean["name"] = nm.strip()
    return _update_pointer(nexus, lambda d: d.update(clean), pointer_dir)


# ---------------------------------------------------------------------------
# Vault project folder (G1.33: a project's outputs land in its own folder,
# not the vault root). Best-effort — folder creation never blocks the record.
# ---------------------------------------------------------------------------

DEFAULT_VAULT_PROJECTS_DIR = Path.home() / "Documents" / "vault" / "Projects"


def _safe_folder_name(name: str) -> str:
    """Human-readable, filesystem-safe folder name (drop path separators)."""
    cleaned = re.sub(r"[\\/]+", " ", (name or "").strip()).strip()
    return cleaned or "Untitled"


def ensure_project_folder(name: str, vault_projects_dir: Path | None = None) -> Path | None:
    """Best-effort: create ``<vault>/Projects/<name>/`` so a project's outputs
    don't pile up in the vault root. Returns the path, or None if creation
    failed (e.g. the server lacks Full-Disk-Access to ~/Documents) — never
    raises, so project creation is not blocked by folder creation."""
    base = vault_projects_dir or DEFAULT_VAULT_PROJECTS_DIR
    try:
        folder = Path(base) / _safe_folder_name(name)
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    except OSError:
        return None


__all__ = [
    "POINTER_DIR",
    "GENERAL_NEXUS",
    "PROJECT_STATUSES",
    "DEFAULT_VAULT_PROJECTS_DIR",
    "ProjectMetaError",
    "slugify_nexus",
    "general_meta",
    "read_project_meta",
    "list_project_meta",
    "create_project",
    "set_project_status",
    "touch_project",
    "update_project_meta",
    "ensure_project_folder",
]
