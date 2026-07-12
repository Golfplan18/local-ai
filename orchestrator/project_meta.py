"""Project records (G1.33) — the conversation-container metadata layer.

A project's record lives in its pointer file ``~/ora/data/projects/<nexus>.json``
— the SAME file the plugin registry uses ("unify the two meanings"). The two
views coexist over one set of files:

  * plugin view (``project_registry.list_projects``): pointers that carry a
    ``root`` → an ``ora-project.json`` manifest (tools / frameworks / slash
    commands).
  * container view (this module): every pointer, read for the conversation-
    container fields below — editable ``display_name``, rollback-safe legacy
    ``name``, immutable ``folder_name``, ``status``, ``last_accessed_at``, and
    the inert default slots. The public metadata shape still exposes the
    editable label as ``name``. A project may be BOTH (a plugin that also holds
    conversations) or container-only (no ``root``).

``Commons`` is synthetic — never a pointer file. An empty conversation
``project_ids`` == Commons, and Commons is the all-inclusive view (a thread in
project X is still visible under Commons).

Nexus-id rename (2026-07-11): the internal sentinel used to be ``"general"``;
it is now ``"commons"``, matching the display name set in the prior
display-string-only pass (PR #211). ``LEGACY_DEFAULT_NEXUS`` keeps every
comparison honoring the old value too, permanently — not a one-time
migration — because it is already live in on-disk pointer files, browser
``localStorage``, and any not-yet-redeployed cloud instance.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

try:
    from active_project import (
        DEFAULT as DEFAULT_NEXUS,
        LEGACY_DEFAULT as LEGACY_DEFAULT_NEXUS,
        canonicalize_project_nexus,
    )
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator.active_project import (
        DEFAULT as DEFAULT_NEXUS,
        LEGACY_DEFAULT as LEGACY_DEFAULT_NEXUS,
        canonicalize_project_nexus,
    )

# Project metadata and plugin pointers are one store.  Derive it from the same
# ORA_HOME-aware runtime root as the active-project pointer so a relocated
# checkout cannot read project records from a different installation.
POINTER_DIR = _rp.DATA_DIR / "projects"

# Same rule the plugin registry enforces on a manifest nexus.
_NEXUS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Deprecated compatibility alias.  It deliberately retains the historical
# value; callers should use ``DEFAULT_NEXUS`` for the canonical runtime id.
GENERAL_NEXUS = LEGACY_DEFAULT_NEXUS
PROJECT_STATUSES = ("active", "inactive", "archived")
# Both the current and legacy sentinel are reserved so neither a fresh nor a
# stale caller can ever create a real project that collides with the default.
RESERVED_NEXUS = {DEFAULT_NEXUS, LEGACY_DEFAULT_NEXUS, ""}

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


def _safe_folder_name(name: str) -> str:
    """Human-readable, filesystem-safe immutable project folder name."""
    cleaned = re.sub(r"[\\/]+", " ", (name or "").strip()).strip()
    return cleaned if cleaned and cleaned not in (".", "..") else "Untitled"


def default_project_meta() -> dict[str, Any]:
    """The synthetic, all-inclusive default project (Commons)."""
    return {
        "nexus": DEFAULT_NEXUS,
        "name": "Commons",
        "display_name": "Commons",
        "folder_name": None,
        "status": "active",
        "is_default": True,
        "is_plugin": False,
        "created": None,
        "last_accessed_at": None,
        **dict(_DEFAULT_SLOTS),
    }


def general_meta() -> dict[str, Any]:
    """Deprecated name for :func:`default_project_meta`."""
    return default_project_meta()


def _normalize_meta(nexus: str, data: dict) -> dict[str, Any]:
    expanded = dict(data)
    _expand_pointer_compat(nexus, expanded, force=False)
    legacy_name = expanded.get("name")
    display_name = expanded.get("display_name")
    status = data.get("status")
    meta: dict[str, Any] = {
        "nexus": nexus,
        # ``name`` remains the public/current display field. On disk, the
        # additive display_name carries it while legacy name stays folder-safe.
        "name": (
            display_name.strip()
            if isinstance(display_name, str) and display_name.strip()
            else (legacy_name.strip() if isinstance(legacy_name, str) and legacy_name.strip() else nexus)
        ),
        "display_name": (
            display_name.strip()
            if isinstance(display_name, str) and display_name.strip()
            else (legacy_name.strip() if isinstance(legacy_name, str) and legacy_name.strip() else nexus)
        ),
        "folder_name": _safe_folder_name(
            expanded.get("folder_name")
            if isinstance(expanded.get("folder_name"), str) and expanded.get("folder_name").strip()
            else (legacy_name if isinstance(legacy_name, str) and legacy_name.strip() else nexus)
        ),
        "status": status if status in PROJECT_STATUSES else "active",
        "is_default": False,
        "is_plugin": bool(data.get("root")),
        "created": data.get("created"),
        "last_accessed_at": data.get("last_accessed_at"),
    }
    for key, default in _DEFAULT_SLOTS.items():
        meta[key] = data.get(key, default)
    return meta


_CONTAINER_POINTER_FIELDS = frozenset({
    "name", "display_name", "folder_name", "status", "created",
    "last_accessed_at", *_DEFAULT_SLOTS.keys(),
})


def pointer_has_container_metadata(data: Any) -> bool:
    """Whether a shared project pointer contains container-owned state."""
    return isinstance(data, dict) and any(
        key in data for key in _CONTAINER_POINTER_FIELDS
    )


def _expand_pointer_compat(nexus: str, data: dict[str, Any], *, force: bool) -> bool:
    """Expand a shared pointer without breaking readers from the prior release.

    Prior readers use on-disk ``name`` both as the display label and to derive
    ``Projects/<name>``. Current readers therefore keep that legacy field fixed
    to the immutable folder identity and put the editable label in additive
    ``display_name``. The additive field is authoritative once present: an old
    release cannot safely express a display-only rename, so a raw legacy-name
    change made while rolled back is restored rather than guessed at.

    Pure plugin pointers stay minimal until a container mutation occurs, so
    unregister can still distinguish them from shared plugin/container records.
    """
    if not force and data.get("root") and not pointer_has_container_metadata(data):
        return False

    raw_name = data.get("name")
    has_raw_name = isinstance(raw_name, str) and bool(raw_name.strip())
    raw_name = raw_name.strip() if has_raw_name else nexus

    raw_folder = data.get("folder_name")
    has_folder = isinstance(raw_folder, str) and bool(raw_folder.strip())
    folder_name = _safe_folder_name(raw_folder if has_folder else raw_name)

    raw_display = data.get("display_name")
    has_display = isinstance(raw_display, str) and bool(raw_display.strip())
    display_name = raw_display.strip() if has_display else raw_name

    expected = {
        "name": folder_name,
        "display_name": display_name,
        "folder_name": folder_name,
    }
    changed = any(data.get(key) != value for key, value in expected.items())
    data.update(expected)
    return changed


def read_project_meta(nexus: str, pointer_dir: Path | None = None) -> dict[str, Any] | None:
    nexus = canonicalize_project_nexus(nexus)
    if nexus == DEFAULT_NEXUS:
        return default_project_meta()
    pf = _pointer_path(nexus, pointer_dir)
    if not pf.is_file():
        return None
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    expanded = dict(data)
    if _expand_pointer_compat(nexus, expanded, force=False):
        # Best-effort lazy expansion covers import/WSGI contexts that do not run
        # the normal server startup migration. Reread under the shared lock so a
        # concurrent plugin registration or metadata update cannot be replaced.
        with _lock:
            try:
                with _rp.locked_file(pf):
                    current = json.loads(pf.read_text(encoding="utf-8"))
                    if isinstance(current, dict):
                        if _expand_pointer_compat(nexus, current, force=False):
                            _write_pointer(nexus, current, pointer_dir)
                        expanded = current
            except (OSError, TimeoutError, json.JSONDecodeError):
                pass
    return _normalize_meta(nexus, expanded)


def list_project_meta(pointer_dir: Path | None = None) -> list[dict[str, Any]]:
    """All projects: Commons first, then real projects by recency.

    Reserved ``commons.json`` / ``general.json`` files are ignored.  They can
    only be stale pre-reservation collisions and must never produce a second
    default row or shadow the synthetic Commons project.
    """
    pdir = pointer_dir or POINTER_DIR
    out: list[dict[str, Any]] = []
    if pdir.is_dir():
        for pf in pdir.glob("*.json"):
            nexus = pf.stem
            if not _NEXUS_RE.match(nexus):
                continue
            if canonicalize_project_nexus(nexus) == DEFAULT_NEXUS:
                continue
            meta = read_project_meta(nexus, pointer_dir)
            if meta:
                out.append(meta)
    out.sort(key=lambda m: (m.get("last_accessed_at") or ""), reverse=True)
    return [default_project_meta()] + out


def _write_pointer(nexus: str, data: dict, pointer_dir: Path | None = None) -> Path:
    """Atomically replace a pointer while the caller holds its sidecar lock."""
    pdir = pointer_dir or POINTER_DIR
    pdir.mkdir(parents=True, exist_ok=True)
    pf = _pointer_path(nexus, pointer_dir)
    tmp = pf.with_name(
        f".{pf.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, pf)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return pf


def migrate_project_folder_names(pointer_dir: Path | None = None) -> int:
    """Expand legacy container pointers for old/new-reader compatibility.

    This migration runs before the server accepts requests. Editable labels move
    to additive ``display_name`` while legacy ``name`` remains equal to the
    immutable folder identity, so a temporary rollback continues reading and
    writing the same project folder. Pure plugin pointers remain minimal.

    Returns the number of pointers expanded. Malformed, reserved, or
    temporarily locked pointers are left untouched for a later startup.
    """
    pdir = pointer_dir or POINTER_DIR
    if not pdir.is_dir():
        return 0
    migrated = 0
    with _lock:
        for pf in sorted(pdir.glob("*.json")):
            nexus = pf.stem
            if not _NEXUS_RE.match(nexus):
                continue
            if canonicalize_project_nexus(nexus) == DEFAULT_NEXUS:
                continue
            try:
                with _rp.locked_file(pf):
                    data = json.loads(pf.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        continue
                    if not _expand_pointer_compat(nexus, data, force=False):
                        continue
                    _write_pointer(nexus, data, pdir)
                    migrated += 1
            except (OSError, TimeoutError, json.JSONDecodeError):
                continue
    return migrated


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
        pf = _pointer_path(nexus, pointer_dir)
        with _rp.locked_file(pf):
            if pf.exists():
                raise ProjectMetaError(f"a project named {nexus!r} already exists")
            now = datetime.now().isoformat(timespec="seconds")
            display_name = (name or nexus).strip()
            folder_name = _safe_folder_name(display_name)
            data = {
                "nexus": nexus,
                # Legacy readers derive the folder from name. Keep it frozen;
                # current readers surface the additive editable display_name.
                "name": folder_name,
                "display_name": display_name,
                "folder_name": folder_name,
                "status": "active",
                "created": now,
                "last_accessed_at": now,
                **dict(_DEFAULT_SLOTS),
            }
            _write_pointer(nexus, data, pointer_dir)
    return _normalize_meta(nexus, data)


def _update_pointer(nexus: str, mutate, pointer_dir: Path | None = None) -> dict[str, Any] | None:
    nexus = canonicalize_project_nexus(nexus)
    if nexus == DEFAULT_NEXUS:
        return default_project_meta()  # synthetic — nothing to persist
    with _lock:
        pf = _pointer_path(nexus, pointer_dir)
        try:
            with _rp.locked_file(pf):
                if not pf.is_file():
                    return None
                try:
                    data = json.loads(pf.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
                if not isinstance(data, dict):
                    return None
                data.setdefault("nexus", nexus)
                _expand_pointer_compat(nexus, data, force=True)
                mutate(data)
                _write_pointer(nexus, data, pointer_dir)
        except (OSError, TimeoutError):
            return None
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
    an invalid ``status``/``name`` raises. Commons is synthetic (no-op)."""
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

    def mutate(data: dict[str, Any]) -> None:
        if "name" in clean:
            # The API/public field stays `name`; persistence uses additive
            # display_name so a rolled-back reader keeps deriving paths from the
            # unchanged legacy name/folder identity.
            data["display_name"] = clean["name"]
        data.update({key: value for key, value in clean.items() if key != "name"})

    return _update_pointer(nexus, mutate, pointer_dir)


# ---------------------------------------------------------------------------
# Vault project folder (G1.33: a project's outputs land in its own folder,
# not the vault root). Best-effort — folder creation never blocks the record.
# ---------------------------------------------------------------------------

DEFAULT_VAULT_PROJECTS_DIR = _rp.VAULT / "Projects"


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


_FILE_INDEX_SKIP = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".DS_Store"}


def list_project_files(
    name: str | None,
    *,
    vault_projects_dir: Path | None = None,
    max_files: int = 500,
) -> dict[str, Any]:
    """Index a project's vault output folder or Commons' vault-root output.

    The file-management line is "out of Ora" (Q2 LOCKED): this is a read-only
    clickable index — the modal links each entry to Obsidian / Finder; there is
    no native CRUD. Returns ``exists: False`` when the folder is absent (e.g.
    cloud-ora has no vault). Files are newest-first; ``truncated`` flags a cap
    hit. A ``None`` name selects the vault root and indexes only its direct
    files: Commons output is saved directly there, while recursively walking
    the root would incorrectly absorb every real project's files and the rest
    of the vault. Never raises.
    """
    projects_base = Path(vault_projects_dir or DEFAULT_VAULT_PROJECTS_DIR)
    is_vault_root = name is None
    base = projects_base.parent if is_vault_root else projects_base / _safe_folder_name(name)
    if not base.is_dir():
        return {
            "exists": False,
            "folder": str(base),
            "files": [],
            "truncated": False,
            "is_vault_root": is_vault_root,
        }
    collected: list[dict[str, Any]] = []
    try:
        paths = base.iterdir() if is_vault_root else base.rglob("*")
        for p in paths:
            rel = p.relative_to(base)
            if any(part in _FILE_INDEX_SKIP for part in rel.parts):
                continue
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            collected.append({
                "name": p.name,
                "rel_path": str(rel),
                "abs_path": str(p),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            })
    except OSError:
        pass
    collected.sort(key=lambda f: f.get("mtime") or "", reverse=True)
    truncated = len(collected) > max_files
    return {
        "exists": True,
        "folder": str(base),
        "files": collected[:max_files],
        "truncated": truncated,
        "is_vault_root": is_vault_root,
    }


__all__ = [
    "POINTER_DIR",
    "DEFAULT_NEXUS",
    "LEGACY_DEFAULT_NEXUS",
    "GENERAL_NEXUS",
    "PROJECT_STATUSES",
    "DEFAULT_VAULT_PROJECTS_DIR",
    "ProjectMetaError",
    "slugify_nexus",
    "default_project_meta",
    "general_meta",
    "pointer_has_container_metadata",
    "migrate_project_folder_names",
    "read_project_meta",
    "list_project_meta",
    "create_project",
    "set_project_status",
    "touch_project",
    "update_project_meta",
    "ensure_project_folder",
    "list_project_files",
]
