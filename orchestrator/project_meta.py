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

import argparse
import copy
import json
import hashlib
import os
import re
import stat
import sys
import threading
import unicodedata
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

# Every surface that declares a new nexus (container creation, plugin
# manifests, and nexus rename) shares this policy.  Keeping it here prevents a
# plugin pointer from creating a filename that the container view cannot safely
# represent on Windows.
MAX_NEXUS_LENGTH = 64
NEXUS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# Compatibility alias for out-of-tree imports.  New code must use
# ``validate_nexus`` rather than matching the expression directly.
_NEXUS_RE = NEXUS_RE

# Deprecated compatibility alias.  It deliberately retains the historical
# value; callers should use ``DEFAULT_NEXUS`` for the canonical runtime id.
GENERAL_NEXUS = LEGACY_DEFAULT_NEXUS
PROJECT_STATUSES = ("active", "inactive", "archived")
# Both the current and legacy sentinel are reserved so neither a fresh nor a
# stale caller can ever create a real project that collides with the default.
WINDOWS_DEVICE_NEXUSES = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
})
RESERVED_NEXUS = frozenset({
    DEFAULT_NEXUS, LEGACY_DEFAULT_NEXUS, "", *WINDOWS_DEVICE_NEXUSES,
})

# Keep new project identities comfortably inside the legacy Windows MAX_PATH
# boundary even when long-path support is disabled.  The descendant reserve is
# for a generated output filename, collision suffix, and temporary suffix.
WINDOWS_PORTABLE_PATH_LIMIT = 240
MAX_FOLDER_COMPONENT_UNITS = 80
PROJECT_CHILD_RESERVE_UNITS = 120
_WINDOWS_INVALID_COMPONENT_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Project-object slots introduced by G1.33.  G1.16 makes the Model Profile and
# its runtime-authenticated locks authoritative; style is already active while
# Persona remains owned by the following bounded gate.
_DEFAULT_SLOTS: dict[str, Any] = {
    "default_model_profile": None,
    "interaction_style": None,
    "output_style": None,
    "persona": None,
    "model_locks": {},
    "private": False,
    # Rank in the user's priority order, ascending — 0 is most important.
    # ``None`` means unranked and sorts after every ranked project, so adding a
    # project never silently jumps the queue and an empty store keeps the
    # previous recency ordering. Lives on the record rather than in a separate
    # order file so it cannot drift from the set of projects that exist.
    "priority": None,
}

_lock = threading.RLock()


class ProjectMetaError(Exception):
    pass


class NexusValidationError(ValueError):
    pass


class ProjectStorageError(ProjectMetaError):
    pass


def _pointer_path(nexus: str, pointer_dir: Path | None = None) -> Path:
    return (pointer_dir or POINTER_DIR) / f"{nexus}.json"


def validate_nexus(value: Any) -> str:
    """Validate a newly declared nexus and return it unchanged."""
    if not isinstance(value, str) or not value:
        raise NexusValidationError("nexus must be a non-empty string")
    if len(value) > MAX_NEXUS_LENGTH:
        raise NexusValidationError(
            f"nexus must be at most {MAX_NEXUS_LENGTH} characters; got {len(value)}"
        )
    if not NEXUS_RE.fullmatch(value):
        raise NexusValidationError(
            "nexus must use lowercase letters, digits, hyphens, or underscores "
            "and start with a letter or digit"
        )
    if value in RESERVED_NEXUS:
        raise NexusValidationError(f"{value!r} is reserved")
    return value


def validate_existing_nexus_source(value: Any) -> str:
    """Validate an existing pointer name for remediation.

    Old Mac installations may already contain an overlength or DOS-device
    pointer.  It must remain renameable before Windows sync, while traversal
    and the two synthetic-default sentinels stay forbidden.
    """
    if not isinstance(value, str) or not value or not NEXUS_RE.fullmatch(value):
        raise NexusValidationError("existing nexus is not a path-safe lowercase slug")
    if value in {DEFAULT_NEXUS, LEGACY_DEFAULT_NEXUS}:
        raise NexusValidationError(f"{value!r} is reserved and cannot be renamed")
    return value


def is_valid_nexus(value: Any) -> bool:
    try:
        validate_nexus(value)
        return True
    except NexusValidationError:
        return False


def slugify_nexus(name: str) -> str:
    """Derive a lowercase kebab-case nexus slug from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug[:MAX_NEXUS_LENGTH].rstrip("-_")


def _legacy_folder_identity(name: str) -> str:
    """Frozen PR-227 folder derivation, used only when identity is absent."""
    cleaned = re.sub(r"[\\/]+", " ", (name or "").strip()).strip()
    return cleaned if cleaned and cleaned not in (".", "..") else "Untitled"


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _truncate_utf16(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    out: list[str] = []
    used = 0
    for char in value:
        width = _utf16_units(char)
        if used + width > limit:
            break
        out.append(char)
        used += width
    return "".join(out)


def _folder_component_budget(vault_root: Path) -> int:
    root = str(Path(vault_root).resolve()).rstrip("/\\")
    project_prefix = root + "\\Projects\\"
    matrix_prefix = root + r"\Matrix\Project Matrix "
    project_budget = (
        WINDOWS_PORTABLE_PATH_LIMIT
        - _utf16_units(project_prefix)
        - 1
        - PROJECT_CHILD_RESERVE_UNITS
    )
    matrix_budget = (
        WINDOWS_PORTABLE_PATH_LIMIT
        - _utf16_units(matrix_prefix)
        - _utf16_units(".md")
    )
    return min(MAX_FOLDER_COMPONENT_UNITS, project_budget, matrix_budget)


def _windows_device_component(value: str) -> bool:
    stem = value.rstrip(" .").split(".", 1)[0].casefold()
    return stem in WINDOWS_DEVICE_NEXUSES


def _portable_collision_key(value: str) -> str:
    """Conservative equality key for Windows/cloud-synced components."""
    return unicodedata.normalize("NFC", value).rstrip(" .").casefold()


def _folder_identity_error(value: Any, *, vault_root: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return "folder_name must be a non-empty string"
    if unicodedata.normalize("NFC", value) != value:
        return "folder_name is not Unicode NFC-normalized"
    if _WINDOWS_INVALID_COMPONENT_RE.search(value):
        return "folder_name contains a character Windows does not allow"
    if value in (".", "..") or value.endswith((" ", ".")):
        return "folder_name is not a portable path component"
    if _windows_device_component(value):
        return "folder_name uses a reserved Windows device name"
    budget = _folder_component_budget(vault_root)
    if budget < 1:
        return "vault path is too deep for a portable project folder"
    if _utf16_units(value) > budget:
        return f"folder_name exceeds the {budget}-UTF-16-unit path budget"
    return None


def validate_folder_identity(value: Any, *, vault_root: Path | None = None) -> str:
    """Validate a persisted folder identity without changing it."""
    root = Path(vault_root or _default_vault_projects_dir().parent)
    error = _folder_identity_error(value, vault_root=root)
    if error:
        raise ProjectStorageError(error)
    return value


def _pointer_folder_identity(nexus: str, data: dict[str, Any]) -> Any:
    if "folder_name" in data:
        return data.get("folder_name")
    raw_name = data.get("name")
    return _legacy_folder_identity(raw_name if isinstance(raw_name, str) else nexus)


def _occupied_folder_names(
    pointer_dir: Path, vault_projects_dir: Path, *, exclude_nexus: str | None = None,
) -> set[str]:
    occupied: set[str] = set()
    if pointer_dir.is_dir():
        for pf in pointer_dir.glob("*.json"):
            if exclude_nexus is not None and pf.stem == exclude_nexus:
                continue
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or not pointer_has_container_metadata(data):
                continue
            folder = _pointer_folder_identity(pf.stem, data)
            if isinstance(folder, str):
                occupied.add(_portable_collision_key(folder))
    if vault_projects_dir.is_dir():
        try:
            occupied.update(
                _portable_collision_key(p.name)
                for p in vault_projects_dir.iterdir()
            )
        except OSError:
            pass
    return occupied


def _portable_folder_base(display_name: str) -> str:
    value = unicodedata.normalize("NFC", display_name or "")
    value = _WINDOWS_INVALID_COMPONENT_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(" .")
    if not value or value in (".", ".."):
        value = "Untitled"
    if _windows_device_component(value):
        value = f"_{value}"
    return value


def allocate_folder_name(
    display_name: str,
    nexus: str,
    *,
    pointer_dir: Path | None = None,
    vault_projects_dir: Path | None = None,
    exclude_nexus: str | None = None,
) -> str:
    """Allocate one new, immutable, case-insensitively unique folder name."""
    try:
        validate_nexus(nexus)
    except NexusValidationError as exc:
        raise ProjectStorageError(str(exc)) from exc
    pdir = Path(pointer_dir or POINTER_DIR)
    projects = Path(vault_projects_dir or _default_vault_projects_dir())
    budget = _folder_component_budget(projects.parent)
    if budget < 8:
        raise ProjectStorageError("vault path is too deep for a portable project folder")
    base = _portable_folder_base(display_name)
    base = _truncate_utf16(base, budget).rstrip(" .") or "Untitled"
    occupied = _occupied_folder_names(
        pdir, projects, exclude_nexus=exclude_nexus,
    )
    if _portable_collision_key(base) not in occupied:
        return base

    # Keep the suffix bounded even when the nexus itself uses all 64 chars.
    # The digest is stable and still derived from the logical identity.
    suffix = " -- " + hashlib.sha256(nexus.encode("ascii")).hexdigest()[:8]
    prefix = _truncate_utf16(base, budget - _utf16_units(suffix)).rstrip(" .")
    candidate = (prefix or "Project") + suffix
    serial = 2
    while _portable_collision_key(candidate) in occupied:
        numbered = f"{suffix}-{serial}"
        prefix = _truncate_utf16(base, budget - _utf16_units(numbered)).rstrip(" .")
        candidate = (prefix or "Project") + numbered
        serial += 1
    return candidate


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
    """Project the public metadata shape without writing or sanitizing state."""
    legacy_name = data.get("name")
    display_name = data.get("display_name")
    folder_name = _pointer_folder_identity(nexus, data)
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
        # A present value is an opaque on-disk identity.  It may need an
        # explicit Windows migration, but a read must never mutate it.
        "folder_name": folder_name,
        "status": status if status in PROJECT_STATUSES else "active",
        "is_default": False,
        "is_plugin": bool(data.get("root")),
        "created": data.get("created"),
        "last_accessed_at": data.get("last_accessed_at"),
    }
    for key, default in _DEFAULT_SLOTS.items():
        meta[key] = data.get(key, default)
    categories, warnings = normalize_library_file_categories(data.get("library_file_categories"))
    meta["library_file_categories"] = categories
    meta["library_category_warnings"] = warnings
    return meta


def normalize_library_file_categories(value) -> tuple[list[dict], list[str]]:
    """Read optional exact metadata categories; invalid entries cannot hide Files."""
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], ["File categories must be a list; no categories were applied."]
    categories, warnings, seen = [], [], set()
    for entry in value:
        valid = isinstance(entry, dict) and set(entry) == {"id", "label", "match"}
        if valid:
            key, label, rule = entry["id"], entry["label"], entry["match"]
            valid = (isinstance(key, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key))
                     and key not in seen and isinstance(label, str) and bool(label.strip())
                     and isinstance(rule, dict) and bool(rule)
                     and set(rule) <= {"nexus", "type", "tags", "subtype"})
            if valid:
                valid = all((isinstance(item, str) and bool(item)) or
                            (isinstance(item, list) and bool(item) and all(isinstance(v, str) and bool(v) for v in item))
                            for item in rule.values())
        if not valid:
            warnings.append("An invalid File category was omitted; Files remain available.")
            continue
        seen.add(key)
        categories.append({"id": key, "label": label.strip(), "match": dict(rule)})
    return categories, warnings


def library_file_category_matches(metadata: dict, rule: dict) -> bool:
    for field, expected in rule.items():
        actual = metadata.get(field)
        if isinstance(expected, list):
            if not isinstance(actual, list) or not all(item in actual for item in expected):
                return False
        elif actual != expected:
            return False
    return True


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

    # A present folder_name is already a physical identity.  Never pass it
    # through the allocator/sanitizer: doing so would repoint a project during
    # an ordinary read or metadata update.
    folder_name = (
        data.get("folder_name")
        if "folder_name" in data
        else _legacy_folder_identity(raw_name)
    )

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
    # Reads are deliberately pure.  Additive old/new-reader fields are written
    # only by the explicit startup schema migration below; a read never changes
    # a persisted physical identity.
    return _normalize_meta(nexus, data)


def list_project_meta(
    pointer_dir: Path | None = None,
    *,
    skipped_authority: list[str] | None = None,
) -> list[dict[str, Any]]:
    """All projects: Commons first, then canonical priority and stable nexus.

    Reserved ``commons.json`` / ``general.json`` files are ignored.  They can
    only be stale pre-reservation collisions and must never produce a second
    default row or shadow the synthetic Commons project.  Default callers keep
    the display-oriented behavior of omitting malformed or unreadable pointer
    files; callers that make an inventory completeness claim can supply
    ``skipped_authority`` to receive those skipped filenames (or the pointer
    directory when enumeration itself fails) while preserving every safely
    parsed project row.  A missing optional pointer directory remains an empty
    project store rather than an authority failure.
    """
    pdir = pointer_dir or POINTER_DIR
    out: list[dict[str, Any]] = []
    try:
        scan = os.scandir(pdir)
    except FileNotFoundError:
        scan = None
    except OSError:
        scan = None
        if skipped_authority is not None:
            skipped_authority.append(str(pdir))
    if scan is not None:
        try:
            with scan:
                entries = iter(scan)
                while True:
                    try:
                        entry = next(entries)
                    except StopIteration:
                        break
                    except OSError:
                        if skipped_authority is not None:
                            skipped_authority.append(str(pdir))
                        break
                    if not Path(entry.name).match("*.json"):
                        continue
                    pf = pdir / entry.name
                    nexus = pf.stem
                    try:
                        validate_existing_nexus_source(nexus)
                    except NexusValidationError:
                        if skipped_authority is not None:
                            skipped_authority.append(pf.name)
                        continue
                    if canonicalize_project_nexus(nexus) == DEFAULT_NEXUS:
                        continue
                    meta = read_project_meta(nexus, pointer_dir)
                    if meta:
                        out.append(meta)
                    elif skipped_authority is not None:
                        skipped_authority.append(pf.name)
        except OSError:
            if skipped_authority is not None:
                skipped_authority.append(str(pdir))
    out.sort(key=_priority_sort_key)
    return [default_project_meta()] + out


def _priority_sort_key(meta: dict[str, Any]) -> tuple:
    """Rank ascending, unranked last, immutable nexus breaking ties.

    This is the order the sidebar, the dropdown, and any future work-selection
    pass read: the top of the list is the most important project.
    """
    priority = meta.get("priority")
    ranked = isinstance(priority, int) and priority >= 0
    return (
        0 if ranked else 1,
        priority if ranked else 0,
        meta["nexus"],
    )


def reorder_projects(
    order: list[str], pointer_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Assign ``priority`` 0..n-1 across ``order``; unlisted projects unranked.

    Reordering is expressed as the whole list rather than per-project patches so
    a drag can never leave two projects sharing a rank or a gap that later
    renumbering has to guess at.
    """
    seen: set[str] = set()
    rank = 0
    for nexus in order or []:
        try:
            canonical = validate_existing_nexus_source(nexus)
        except NexusValidationError:
            continue
        if canonical in seen or canonicalize_project_nexus(canonical) == DEFAULT_NEXUS:
            continue
        if update_project_meta(canonical, {"priority": rank}, pointer_dir) is None:
            continue  # vanished mid-reorder; skip rather than shift the rest
        seen.add(canonical)
        rank += 1
    # Anything omitted from the payload loses its rank, so the list the user
    # sees and the ranks on disk cannot disagree.
    for meta in list_project_meta(pointer_dir):
        nexus = meta.get("nexus")
        if (
            not meta.get("is_default")
            and nexus not in seen
            and meta.get("priority") is not None
        ):
            update_project_meta(nexus, {"priority": None}, pointer_dir)
    return list_project_meta(pointer_dir)


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


def _read_pointer_for_update(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectMetaError(
            f"cannot safely update malformed project pointer {path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ProjectMetaError(
            f"cannot safely update project pointer {path}: expected a JSON object"
        )
    return data


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
            try:
                validate_existing_nexus_source(nexus)
            except NexusValidationError:
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


def create_project(
    name: str,
    pointer_dir: Path | None = None,
    *,
    vault_projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Create a container project record from a display name.

    Derives a kebab nexus from the name, refuses reserved/colliding nexuses,
    and writes the pointer. The vault project folder + graceful MOM run in the
    creation flow (a later sub-step), not here — this is the record only.
    """
    nexus = slugify_nexus(name)
    try:
        validate_nexus(nexus)
    except NexusValidationError as exc:
        raise ProjectMetaError(
            f"could not derive a valid nexus from name {name!r}: {exc}"
        ) from exc
    with _lock:
        pf = _pointer_path(nexus, pointer_dir)
        with _rp.locked_file(pf):
            if pf.exists():
                raise ProjectMetaError(f"a project named {nexus!r} already exists")
            now = datetime.now().isoformat(timespec="seconds")
            display_name = (name or nexus).strip()
            folder_name = allocate_folder_name(
                display_name,
                nexus,
                pointer_dir=pointer_dir,
                vault_projects_dir=vault_projects_dir,
            )
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


def register_existing_container_project(
    nexus: str,
    display_name: str,
    folder_name: str,
    pointer_dir: Path | None = None,
    *,
    vault_projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Register an already-existing vault project folder as a container.

    This is the legacy Matrix/vault migration path: the canonical nexus is
    supplied explicitly rather than derived from the display name, and the
    folder must already exist under ``Projects/``. Existing plugin bindings
    (``root``) and unknown future fields are preserved. A conflicting pointer
    or frozen folder identity is rejected rather than repointed.
    """
    try:
        validate_nexus(nexus)
    except NexusValidationError as exc:
        raise ProjectMetaError(str(exc)) from exc
    if not isinstance(display_name, str) or not display_name.strip():
        raise ProjectMetaError("display_name must be a non-empty string")
    display_name = display_name.strip()
    try:
        folder_name = validate_folder_identity(
            folder_name,
            vault_root=Path(vault_projects_dir or _default_vault_projects_dir()).parent,
        )
    except ProjectStorageError as exc:
        raise ProjectMetaError(str(exc)) from exc
    folder = project_folder_path(folder_name, vault_projects_dir)
    if not folder.is_dir():
        raise ProjectMetaError(f"project folder does not exist: {folder}")

    pdir = pointer_dir or POINTER_DIR
    with _lock:
        pf = _pointer_path(nexus, pdir)
        with _rp.locked_file(pf):
            data = _read_pointer_for_update(pf)
            wanted_key = _portable_collision_key(folder_name)
            if Path(pdir).is_dir():
                for other in Path(pdir).glob("*.json"):
                    if other == pf:
                        continue
                    try:
                        other_data = _read_pointer_for_update(other)
                    except ProjectMetaError:
                        continue
                    if not pointer_has_container_metadata(other_data):
                        continue
                    other_folder = _pointer_folder_identity(other.stem, other_data)
                    if (
                        isinstance(other_folder, str)
                        and _portable_collision_key(other_folder) == wanted_key
                    ):
                        raise ProjectMetaError(
                            f"project folder {folder_name!r} is already owned by "
                            f"{other.stem!r}"
                        )
            existing_nexus = data.get("nexus")
            if (
                isinstance(existing_nexus, str)
                and existing_nexus.strip()
                and existing_nexus.strip() != nexus
            ):
                raise ProjectMetaError(
                    f"pointer {pf.name} declares conflicting nexus {existing_nexus!r}"
                )
            if pointer_has_container_metadata(data):
                existing_folder = _pointer_folder_identity(nexus, data)
                if existing_folder != folder_name:
                    raise ProjectMetaError(
                        f"project {nexus!r} already points at folder "
                        f"{existing_folder!r}, not {folder_name!r}"
                    )
            now = datetime.now().isoformat(timespec="seconds")
            data["nexus"] = nexus
            data["name"] = folder_name
            data["display_name"] = display_name
            data["folder_name"] = folder_name
            if data.get("status") not in PROJECT_STATUSES:
                data["status"] = "active"
            data.setdefault("created", now)
            data.setdefault("last_accessed_at", now)
            for key, default in _DEFAULT_SLOTS.items():
                data.setdefault(key, default)
            _write_pointer(nexus, data, pdir)
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
                if data.get("root") and not pointer_has_container_metadata(data):
                    # First container mutation of a pure plugin pointer is the
                    # point at which it receives a physical identity.  Allocate
                    # it under current policy rather than freezing a new legacy
                    # identity through the compatibility path.
                    folder_name = allocate_folder_name(
                        nexus, nexus, pointer_dir=pointer_dir,
                    )
                    data.update({
                        "name": folder_name,
                        "display_name": nexus,
                        "folder_name": folder_name,
                    })
                else:
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
    """Record project activity without changing canonical priority order."""
    now = datetime.now().isoformat(timespec="seconds")
    return _update_pointer(nexus, lambda d: d.__setitem__("last_accessed_at", now), pointer_dir)


# Fields the management modal / API may patch on a project record.
_UPDATABLE_FIELDS = {
    "name", "status", "interaction_style", "output_style", "persona",
    "private", "last_accessed_at", "priority", "library_file_categories",
}


def _clean_project_updates(updates: dict | None) -> dict[str, Any]:
    clean = {k: v for k, v in (updates or {}).items() if k in _UPDATABLE_FIELDS}
    if "status" in clean and clean["status"] not in PROJECT_STATUSES:
        raise ProjectMetaError(
            f"status must be one of {PROJECT_STATUSES}; got {clean['status']!r}"
        )
    if "priority" in clean and clean["priority"] is not None:
        try:
            clean["priority"] = max(0, int(clean["priority"]))
        except (TypeError, ValueError):
            raise ProjectMetaError(
                f"priority must be an integer or null; got {clean['priority']!r}"
            ) from None
    if "name" in clean:
        nm = clean["name"]
        if not isinstance(nm, str) or not nm.strip():
            raise ProjectMetaError("name must be a non-empty string")
        clean["name"] = nm.strip()
    if "library_file_categories" in clean:
        categories, warnings = normalize_library_file_categories(clean["library_file_categories"])
        if warnings:
            raise ProjectMetaError(" ".join(warnings))
        clean["library_file_categories"] = categories
    return clean


def _apply_project_updates(data: dict[str, Any], clean: dict[str, Any]) -> None:
    if "name" in clean:
        # The API/public field stays `name`; persistence uses additive
        # display_name so a rolled-back reader keeps deriving paths from the
        # unchanged legacy name/folder identity.
        data["display_name"] = clean["name"]
    data.update({key: value for key, value in clean.items() if key != "name"})


def update_project_meta(
    nexus: str, updates: dict, pointer_dir: Path | None = None
) -> dict[str, Any] | None:
    """Patch whitelisted fields on a project record. Unknown fields are ignored;
    an invalid ``status``/``name`` raises. Commons is synthetic (no-op)."""
    clean = _clean_project_updates(updates)

    def mutate(data: dict[str, Any]) -> None:
        _apply_project_updates(data, clean)

    return _update_pointer(nexus, mutate, pointer_dir)


def set_project_model_binding(
    nexus: str,
    profile_name: str | None,
    model_locks: dict,
    pointer_dir: Path | None = None,
    updates: dict | None = None,
) -> dict[str, Any] | None:
    """Persist the Model Profile name and its runtime-authenticated locks.

    These fields deliberately bypass ``update_project_meta``'s public patch
    whitelist.  Callers must first construct ``model_locks`` through
    ``model_profiles.capture_project_binding``; a browser cannot submit an
    invented snapshot or change the name without replacing the exact lock in
    the same atomic pointer write.
    """
    nexus = canonicalize_project_nexus(nexus)
    if profile_name is not None:
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ProjectMetaError("default_model_profile must be a non-empty string or null")
        profile_name = profile_name.strip()
        if not isinstance(model_locks, dict) or not model_locks:
            raise ProjectMetaError("a Model Profile binding requires non-empty model_locks")
        if model_locks.get("project_nexus") != nexus:
            raise ProjectMetaError(
                "Model Profile locks must be issued for this exact project nexus"
            )
    elif model_locks:
        raise ProjectMetaError("an unbound project cannot retain model_locks")
    clean = _clean_project_updates(updates)

    def mutate(data: dict[str, Any]) -> None:
        data["default_model_profile"] = profile_name
        data["model_locks"] = copy.deepcopy(model_locks)
        _apply_project_updates(data, clean)

    return _update_pointer(nexus, mutate, pointer_dir)


# ---------------------------------------------------------------------------
# Vault project folder (G1.33: a project's outputs land in its own folder,
# not the vault root). Best-effort — folder creation never blocks the record.
# ---------------------------------------------------------------------------

DEFAULT_VAULT_PROJECTS_DIR = _rp.VAULT / "Projects"
_INITIAL_DEFAULT_VAULT_PROJECTS_DIR = DEFAULT_VAULT_PROJECTS_DIR


def _default_vault_projects_dir() -> Path:
    """Resolve the vault at call time while preserving the test override hook."""
    configured = Path(DEFAULT_VAULT_PROJECTS_DIR)
    if configured != _INITIAL_DEFAULT_VAULT_PROJECTS_DIR:
        return configured
    accessor = getattr(_rp, "vault_dir", None)
    return (Path(accessor()) if callable(accessor) else _rp.VAULT) / "Projects"


def project_folder_path(
    folder_name: str, vault_projects_dir: Path | None = None,
) -> Path:
    """Return the exact, validated path for one persisted folder identity."""
    base = Path(vault_projects_dir or _default_vault_projects_dir())
    identity = validate_folder_identity(folder_name, vault_root=base.parent)
    candidate = base / identity
    try:
        candidate.resolve(strict=False).relative_to(base.resolve(strict=False))
    except ValueError as exc:  # defense in depth against platform path quirks
        raise ProjectStorageError("folder_name escapes the Projects directory") from exc
    return candidate


def ensure_project_folder(name: str, vault_projects_dir: Path | None = None) -> Path | None:
    """Best-effort: create ``<vault>/Projects/<name>/`` so a project's outputs
    don't pile up in the vault root. Returns the path, or None if creation
    failed (e.g. the server lacks Full-Disk-Access to Documents). An invalid
    persisted identity raises ``ProjectStorageError`` so callers can surface a
    migration-required state instead of silently choosing another folder."""
    folder = project_folder_path(name, vault_projects_dir)
    try:
        # A missing vault means storage is unavailable (for example cloud Ora),
        # not permission to manufacture a new directory tree at a guessed path.
        # ``Projects`` itself may be created inside an existing vault.
        if not folder.parent.parent.is_dir():
            return None
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    except OSError:
        return None


_FILE_INDEX_SKIP = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".DS_Store"}


def _enumerate_project_file_rows(
    base: Path, *, recursive: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """Enumerate safe file rows while reporting every scan/stat failure."""
    collected: list[dict[str, Any]] = []
    complete = True
    pending = [base]
    while pending:
        directory = pending.pop()
        try:
            scan = os.scandir(directory)
        except OSError:
            complete = False
            continue
        try:
            with scan:
                entries = iter(scan)
                while True:
                    try:
                        entry = next(entries)
                    except StopIteration:
                        break
                    except OSError:
                        complete = False
                        break

                    if entry.name in _FILE_INDEX_SKIP:
                        continue
                    path = directory / entry.name
                    try:
                        entry_stat = entry.stat(follow_symlinks=False)
                        is_symlink = stat.S_ISLNK(entry_stat.st_mode)
                        if is_symlink:
                            entry_stat = entry.stat(follow_symlinks=True)
                    except OSError:
                        complete = False
                        continue

                    if stat.S_ISDIR(entry_stat.st_mode):
                        if recursive and not is_symlink:
                            pending.append(path)
                        continue
                    if not stat.S_ISREG(entry_stat.st_mode):
                        continue

                    rel = path.relative_to(base)
                    collected.append({
                        "name": path.name,
                        "rel_path": str(rel),
                        "abs_path": str(path),
                        "size": entry_stat.st_size,
                        "mtime": datetime.fromtimestamp(
                            entry_stat.st_mtime
                        ).isoformat(timespec="seconds"),
                        "_mtime_ns": entry_stat.st_mtime_ns,
                    })
        except OSError:
            complete = False
    return collected, complete


def list_project_files(
    name: str | None,
    *,
    vault_projects_dir: Path | None = None,
    max_files: int | None = 500,
    offset: int = 0,
) -> dict[str, Any]:
    """Index a project's vault output folder or Commons' vault-root output.

    The file-management line is "out of Ora" (Q2 LOCKED): this is a read-only
    clickable index — the modal links each entry to Obsidian / Finder; there is
    no native CRUD. Returns ``exists: False`` when the folder is absent (e.g.
    cloud-ora has no vault). Files are newest-first with a path tie-break;
    ``offset`` and an integer ``max_files`` page the complete inventory, while
    ``max_files=None`` returns the remaining inventory from one in-memory
    enumeration. ``total`` and ``truncated`` describe the complete inventory.
    A ``None`` name selects the vault root and indexes only its direct
    files: Commons output is saved directly there, while recursively walking
    the root would incorrectly absorb every real project's files and the rest
    of the vault. Storage enumeration failures are reflected by ``complete``;
    invalid pagination arguments still raise ``ValueError``.
    """
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if max_files is not None and (
        isinstance(max_files, bool)
        or not isinstance(max_files, int)
        or max_files < 1
    ):
        raise ValueError("max_files must be a positive integer")

    projects_base = Path(vault_projects_dir or _default_vault_projects_dir())
    is_vault_root = name is None
    base = (
        projects_base.parent
        if is_vault_root
        else project_folder_path(name, projects_base)
    )
    try:
        base_stat = base.stat()
    except OSError:
        base_stat = None
    if base_stat is None or not stat.S_ISDIR(base_stat.st_mode):
        return {
            "exists": False,
            "folder": str(base),
            "files": [],
            "truncated": False,
            "is_vault_root": is_vault_root,
            "complete": False,
            "reason": "project folder is unavailable",
            "total": 0,
            "offset": offset,
            "limit": max_files,
            "next_offset": None,
        }
    collected, complete = _enumerate_project_file_rows(
        base, recursive=not is_vault_root,
    )
    collected.sort(key=lambda f: (-f["_mtime_ns"], f["rel_path"]))
    total = len(collected)
    page = (
        collected[offset:]
        if max_files is None
        else collected[offset:offset + max_files]
    )
    for item in page:
        item.pop("_mtime_ns", None)
    next_offset = None
    if max_files is not None:
        next_offset = offset + len(page)
        if next_offset >= total:
            next_offset = None
    return {
        "exists": True,
        "folder": str(base),
        "files": page,
        "truncated": next_offset is not None,
        "is_vault_root": is_vault_root,
        "complete": complete,
        "reason": (
            None if complete else
            "one or more project files or folders could not be read"
        ),
        "total": total,
        "offset": offset,
        "limit": max_files,
        "next_offset": next_offset,
    }


# ---------------------------------------------------------------------------
# Explicit Windows storage migration.  Planning is pure and execution requires
# an affirmative confirmation; this is never called from import/read/startup.
# ---------------------------------------------------------------------------

def _pointer_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _migration_source_path(folder_name: Any, projects_dir: Path) -> Path:
    """Join a legacy Mac component without applying Windows transformations."""
    if (
        not isinstance(folder_name, str)
        or not folder_name
        or folder_name in (".", "..")
        or "/" in folder_name
        or "\\" in folder_name
        or Path(folder_name).is_absolute()
    ):
        raise ProjectStorageError("legacy folder identity is not path-confined")
    return projects_dir / folder_name


def _matrix_path_error(path: Path, *, vault_root: Path) -> str | None:
    """Return why an existing Matrix path cannot survive Windows sync."""
    matrix_dir = (vault_root / "Matrix").resolve(strict=False)
    resolved = path.resolve(strict=False)
    if resolved.parent != matrix_dir:
        return "Matrix file is outside the vault Matrix directory"
    name = path.name
    if unicodedata.normalize("NFC", name) != name:
        return "Matrix filename is not Unicode NFC-normalized"
    if _WINDOWS_INVALID_COMPONENT_RE.search(name):
        return "Matrix filename contains a character Windows does not allow"
    if name in (".", "..") or name.endswith((" ", ".")):
        return "Matrix filename is not a portable path component"
    if _windows_device_component(name):
        return "Matrix filename uses a reserved Windows device name"
    if _utf16_units(str(resolved)) > WINDOWS_PORTABLE_PATH_LIMIT:
        return "Matrix path exceeds the portable Windows path budget"
    return None


def _resolve_matrix_for_migration(nexus: str, vault_root: Path) -> Path | None:
    """Resolve by frontmatter through operation_matrix's public API."""
    try:
        from orchestrator import operation_matrix
    except ImportError:  # pragma: no cover - direct orchestrator PYTHONPATH
        import operation_matrix  # type: ignore
    # Passing no folder identity deliberately bypasses convention-name guessing
    # and resolves solely from canonical frontmatter nexus.
    return operation_matrix.resolve_matrix_path(nexus, None, vault=vault_root)


def _same_existing_path(left: Path, right: Path) -> bool:
    if left == right:
        return True
    if not left.exists() or not right.exists():
        return False
    try:
        return left.samefile(right)
    except OSError:
        return False


def plan_windows_project_storage_migration(
    *,
    pointer_dir: Path | None = None,
    vault_projects_dir: Path | None = None,
) -> dict[str, Any]:
    """Report physical project folders that require a Windows-safe rename.

    This function performs no writes.  Malformed pointers, invalid source
    nexuses, missing folders, and ambiguous case-insensitive identities are
    reported rather than guessed at.
    """
    pdir = Path(pointer_dir or POINTER_DIR)
    projects = Path(vault_projects_dir or _default_vault_projects_dir())
    records: list[tuple[str, Path, dict[str, Any], Any]] = []
    scan_blocked: list[dict[str, Any]] = []
    if pdir.is_dir():
        for pf in sorted(pdir.glob("*.json")):
            nexus = pf.stem
            if nexus in {DEFAULT_NEXUS, LEGACY_DEFAULT_NEXUS}:
                continue
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                scan_blocked.append({
                    "nexus": nexus,
                    "folder_name": None,
                    "reasons": [f"could not read project pointer: {exc}"],
                })
                continue
            if not isinstance(data, dict):
                scan_blocked.append({
                    "nexus": nexus,
                    "folder_name": None,
                    "reasons": ["project pointer is not a JSON object"],
                })
                continue
            if not pointer_has_container_metadata(data):
                continue
            records.append((nexus, pf, data, _pointer_folder_identity(nexus, data)))

    identities: dict[str, list[str]] = {}
    for nexus, _, _, folder in records:
        if isinstance(folder, str):
            identities.setdefault(_portable_collision_key(folder), []).append(nexus)

    changes: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = list(scan_blocked)
    for nexus, pf, data, folder in records:
        reasons: list[str] = []
        try:
            validate_nexus(nexus)
        except NexusValidationError as exc:
            reasons.append(f"nexus requires rename first: {exc}")

        folder_error = _folder_identity_error(folder, vault_root=projects.parent)
        colliders = (
            identities.get(_portable_collision_key(folder), [])
            if isinstance(folder, str)
            else []
        )
        duplicate = len(colliders) > 1
        if duplicate:
            # A same-spelling identity points multiple projects at one folder;
            # ownership cannot be inferred.  Distinct case-only spellings on a
            # case-sensitive source filesystem are safe to plan after the first.
            spellings = {
                str(other_folder)
                for nx, _, _, other_folder in records
                if nx in colliders
            }
            if len(spellings) == 1:
                reasons.append(
                    "multiple projects share this exact folder identity: "
                    + ", ".join(colliders)
                )
            elif nexus != sorted(colliders)[0]:
                folder_error = folder_error or "case-insensitive folder collision"

        matrix_path: Path | None = None
        matrix_error: str | None = None
        try:
            matrix_path = _resolve_matrix_for_migration(nexus, projects.parent)
            if matrix_path is not None:
                matrix_error = _matrix_path_error(
                    matrix_path, vault_root=projects.parent,
                )
        except Exception as exc:
            reasons.append(f"Matrix resolution is ambiguous or unreadable: {exc}")

        if reasons:
            blocked.append({
                "nexus": nexus,
                "folder_name": folder,
                "reasons": [
                    *([folder_error] if folder_error else []),
                    *([matrix_error] if matrix_error else []),
                    *reasons,
                ],
            })
            continue

        if not folder_error and not matrix_error:
            continue

        folder_move = bool(folder_error)
        matrix_move = bool(matrix_error and matrix_path is not None)
        try:
            if folder_move:
                source = _migration_source_path(folder, projects)
                target_name = allocate_folder_name(
                    str(data.get("display_name") or data.get("name") or nexus),
                    nexus,
                    pointer_dir=pdir,
                    vault_projects_dir=projects,
                    exclude_nexus=nexus,
                )
                target = projects / target_name
            else:
                source = target = _migration_source_path(folder, projects)
                target_name = str(folder)
        except ProjectStorageError as exc:
            blocked.append({
                "nexus": nexus,
                "folder_name": folder,
                "reasons": [
                    *([folder_error] if folder_error else []),
                    *([matrix_error] if matrix_error else []),
                    str(exc),
                ],
            })
            continue

        matrix_target: Path | None = None
        if matrix_move:
            matrix_target = projects.parent / "Matrix" / f"Project Matrix {target_name}.md"
            target_error = _matrix_path_error(
                matrix_target, vault_root=projects.parent,
            )
            if target_error:
                blocked.append({
                    "nexus": nexus,
                    "folder_name": folder,
                    "reasons": [matrix_error, f"proposed Matrix target: {target_error}"],
                })
                continue
            if matrix_target.exists() and not _same_existing_path(matrix_path, matrix_target):
                blocked.append({
                    "nexus": nexus,
                    "folder_name": folder,
                    "reasons": [
                        matrix_error,
                        f"proposed Matrix target already exists: {matrix_target}",
                    ],
                })
                continue

        entry = {
            "nexus": nexus,
            "reasons": [
                *([folder_error] if folder_error else []),
                *([matrix_error] if matrix_error else []),
            ],
            "old_folder_name": folder,
            "new_folder_name": target_name,
            "pointer_path": str(pf),
            "pointer_sha256": _pointer_digest(pf),
            "folder_move": folder_move,
            "source_path": str(source) if folder_move else None,
            "target_path": str(target) if folder_move else None,
            "matrix_move": matrix_move,
            "matrix_source_path": str(matrix_path) if matrix_move else None,
            "matrix_target_path": str(matrix_target) if matrix_move else None,
            "matrix_sha256": _pointer_digest(matrix_path) if matrix_move else None,
        }
        entry_blockers: list[str] = []
        if folder_move and not source.is_dir():
            entry_blockers.append("source project folder does not exist")
        if matrix_move and (matrix_path is None or not matrix_path.is_file()):
            entry_blockers.append("source Matrix file does not exist")
        if entry_blockers:
            blocked.append({
                "nexus": nexus,
                "folder_name": folder,
                "reasons": [*entry["reasons"], *entry_blockers],
            })
        else:
            changes.append(entry)

    body = {
        "version": 2,
        "pointer_dir": str(pdir),
        "vault_projects_dir": str(projects),
        "changes": changes,
        "blocked": blocked,
    }
    fingerprint = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        **body,
        "fingerprint": fingerprint,
        "has_changes": bool(changes),
        "can_apply": bool(changes) and not blocked,
    }


def _move_migration_path(source: Path, target: Path, nexus: str) -> None:
    if source == target:
        return
    if _portable_collision_key(source.name) != _portable_collision_key(target.name):
        os.replace(source, target)
        return
    intermediate = source.with_name(
        f".{source.name}.{nexus}.{os.getpid()}.ora-migration"
    )
    if intermediate.exists():
        raise ProjectStorageError(f"migration staging path already exists: {intermediate}")
    os.replace(source, intermediate)
    try:
        os.replace(intermediate, target)
    except Exception:
        os.replace(intermediate, source)
        raise


def apply_windows_project_storage_migration(
    plan: dict[str, Any], *, confirmed: bool = False,
) -> dict[str, Any]:
    """Apply a reviewed migration plan, rolling back a failed pointer write."""
    if not confirmed:
        raise ProjectStorageError("migration requires explicit confirmation")
    if not isinstance(plan, dict) or plan.get("version") != 2:
        raise ProjectStorageError("unsupported or malformed migration plan")
    if plan.get("blocked"):
        raise ProjectStorageError("migration plan has blockers and cannot be applied")
    changes = plan.get("changes")
    if not isinstance(changes, list) or not changes:
        return {"ok": True, "applied": [], "errors": []}

    # Validate the plan fingerprint and every source before the first move.
    signed_body = {
        key: plan.get(key)
        for key in ("version", "pointer_dir", "vault_projects_dir", "changes", "blocked")
    }
    expected_fingerprint = hashlib.sha256(
        json.dumps(signed_body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if plan.get("fingerprint") != expected_fingerprint:
        raise ProjectStorageError("migration plan fingerprint does not match its contents")
    for entry in changes:
        pf = Path(entry["pointer_path"])
        if not pf.is_file() or _pointer_digest(pf) != entry.get("pointer_sha256"):
            raise ProjectStorageError(f"project pointer changed since planning: {pf}")
        if entry.get("folder_move"):
            source = Path(entry["source_path"])
            target = Path(entry["target_path"])
            if not source.is_dir():
                raise ProjectStorageError(f"source project folder is missing: {source}")
            if target.exists() and not _same_existing_path(source, target):
                raise ProjectStorageError(f"migration target now exists: {target}")
        if entry.get("matrix_move"):
            matrix_source = Path(entry["matrix_source_path"])
            matrix_target = Path(entry["matrix_target_path"])
            if (
                not matrix_source.is_file()
                or _pointer_digest(matrix_source) != entry.get("matrix_sha256")
            ):
                raise ProjectStorageError(
                    f"Matrix file changed or disappeared since planning: {matrix_source}"
                )
            if matrix_target.exists() and not _same_existing_path(
                matrix_source, matrix_target,
            ):
                raise ProjectStorageError(
                    f"Matrix migration target now exists: {matrix_target}"
                )

    applied: list[str] = []
    errors: list[str] = []
    pdir = Path(plan["pointer_dir"])
    for entry in changes:
        nexus = entry["nexus"]
        pf = Path(entry["pointer_path"])
        source = Path(entry["source_path"]) if entry.get("folder_move") else None
        target = Path(entry["target_path"]) if entry.get("folder_move") else None
        matrix_source = (
            Path(entry["matrix_source_path"]) if entry.get("matrix_move") else None
        )
        matrix_target = (
            Path(entry["matrix_target_path"]) if entry.get("matrix_move") else None
        )
        folder_moved = False
        matrix_moved = False
        try:
            with _lock:
                with _rp.locked_file(pf):
                    if _pointer_digest(pf) != entry["pointer_sha256"]:
                        raise ProjectStorageError(
                            f"project pointer changed during migration: {pf}"
                        )
                    data = json.loads(pf.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        raise ProjectStorageError(f"project pointer is not an object: {pf}")
                    if matrix_source is not None:
                        if _pointer_digest(matrix_source) != entry["matrix_sha256"]:
                            raise ProjectStorageError(
                                f"Matrix file changed during migration: {matrix_source}"
                            )
                    if source is not None and target is not None:
                        _move_migration_path(source, target, nexus)
                        folder_moved = source != target
                    if matrix_source is not None and matrix_target is not None:
                        _move_migration_path(matrix_source, matrix_target, nexus)
                        matrix_moved = matrix_source != matrix_target
                    if entry.get("folder_move"):
                        data["folder_name"] = entry["new_folder_name"]
                        # Rollback readers derive Projects/<name>; keep it pinned
                        # to the same migrated physical identity.
                        data["name"] = entry["new_folder_name"]
                        _write_pointer(nexus, data, pdir)
            applied.append(nexus)
        except Exception as exc:
            rollback_errors: list[str] = []
            if (
                matrix_moved
                and matrix_target is not None
                and matrix_source is not None
                and matrix_target.exists()
                and not matrix_source.exists()
            ):
                try:
                    _move_migration_path(matrix_target, matrix_source, nexus)
                except Exception as rb_exc:  # preserve both failures for repair
                    rollback_errors.append(f"Matrix rollback failed: {rb_exc}")
            if (
                folder_moved
                and target is not None
                and source is not None
                and target.exists()
                and not source.exists()
            ):
                try:
                    _move_migration_path(target, source, nexus)
                except Exception as rb_exc:
                    rollback_errors.append(f"folder rollback failed: {rb_exc}")
            message = f"{nexus}: {exc}"
            if rollback_errors:
                message += "; " + "; ".join(rollback_errors)
            errors.append(message)
            break
    return {"ok": not errors, "applied": applied, "errors": errors}


def _migration_cli(argv: list[str] | None = None) -> int:
    """Expose report-first Windows storage remediation as an explicit CLI.

    ``report`` only scans and prints JSON.  ``apply`` either consumes that
    saved JSON verbatim or regenerates the current report for an exact
    fingerprint, and requires the operator to repeat the reviewed fingerprint
    through an intentionally explicit confirmation flag.
    """
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.project_meta",
        description="Inspect or explicitly apply Windows project-storage migration.",
    )
    commands = parser.add_subparsers(dest="command")
    migration = commands.add_parser("windows-storage-migration")
    actions = migration.add_subparsers(dest="action")

    report = actions.add_parser(
        "report", help="print a write-free migration report as JSON"
    )
    report.add_argument("--pointer-dir", type=Path)
    report.add_argument("--vault-projects-dir", type=Path)

    apply_cmd = actions.add_parser(
        "apply", help="apply a saved or exact-fingerprint migration report"
    )
    source = apply_cmd.add_mutually_exclusive_group()
    source.add_argument(
        "--plan", type=Path, help="saved JSON emitted by the report command"
    )
    source.add_argument(
        "--fingerprint",
        help="exact fingerprint of the current report (which is regenerated)",
    )
    apply_cmd.add_argument("--pointer-dir", type=Path)
    apply_cmd.add_argument("--vault-projects-dir", type=Path)
    apply_cmd.add_argument(
        "--confirm-apply-fingerprint",
        help="repeat the reviewed report fingerprint to authorize filesystem writes",
    )

    args = parser.parse_args(argv)
    try:
        if args.command != "windows-storage-migration" or args.action not in {
            "report", "apply",
        }:
            raise ProjectStorageError(
                "choose 'windows-storage-migration report' or "
                "'windows-storage-migration apply'"
            )

        if args.action == "report":
            result = plan_windows_project_storage_migration(
                pointer_dir=args.pointer_dir,
                vault_projects_dir=args.vault_projects_dir,
            )
            print(json.dumps(result, sort_keys=True, ensure_ascii=False))
            return 0

        if bool(args.plan) == bool(args.fingerprint):
            raise ProjectStorageError(
                "apply requires exactly one of --plan or --fingerprint"
            )
        if args.plan:
            try:
                loaded = json.loads(args.plan.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProjectStorageError(
                    f"could not read migration plan {args.plan}: {exc}"
                ) from exc
            if not isinstance(loaded, dict):
                raise ProjectStorageError("saved migration plan is not a JSON object")
            plan = loaded
        else:
            plan = plan_windows_project_storage_migration(
                pointer_dir=args.pointer_dir,
                vault_projects_dir=args.vault_projects_dir,
            )
            if args.fingerprint != plan.get("fingerprint"):
                raise ProjectStorageError(
                    "current migration report does not match --fingerprint; "
                    "generate and review a fresh report"
                )

        reviewed_fingerprint = plan.get("fingerprint")
        if (
            not isinstance(reviewed_fingerprint, str)
            or args.confirm_apply_fingerprint != reviewed_fingerprint
        ):
            raise ProjectStorageError(
                "--confirm-apply-fingerprint must exactly match the reviewed "
                "migration report fingerprint"
            )
        result = apply_windows_project_storage_migration(plan, confirmed=True)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    except (ProjectMetaError, NexusValidationError, ValueError) as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


__all__ = [
    "POINTER_DIR",
    "DEFAULT_NEXUS",
    "LEGACY_DEFAULT_NEXUS",
    "GENERAL_NEXUS",
    "MAX_NEXUS_LENGTH",
    "NEXUS_RE",
    "WINDOWS_DEVICE_NEXUSES",
    "RESERVED_NEXUS",
    "PROJECT_STATUSES",
    "DEFAULT_VAULT_PROJECTS_DIR",
    "ProjectMetaError",
    "NexusValidationError",
    "ProjectStorageError",
    "validate_nexus",
    "validate_existing_nexus_source",
    "is_valid_nexus",
    "slugify_nexus",
    "allocate_folder_name",
    "validate_folder_identity",
    "default_project_meta",
    "general_meta",
    "pointer_has_container_metadata",
    "migrate_project_folder_names",
    "read_project_meta",
    "list_project_meta",
    "create_project",
    "register_existing_container_project",
    "set_project_status",
    "touch_project",
    "update_project_meta",
    "set_project_model_binding",
    "ensure_project_folder",
    "project_folder_path",
    "list_project_files",
    "plan_windows_project_storage_migration",
    "apply_windows_project_storage_migration",
]


if __name__ == "__main__":
    raise SystemExit(_migration_cli())
