"""Operation-Matrix MOM read/write (G1.33 sub-step 5).

A project's **Mission / Objectives / Milestones** (MOM) live canonically in the
vault's Operation-Matrix markdown — ``<vault>/Matrix/Project Matrix <Name>.md`` —
under the ``## Mission``, ``## Objectives``, and ``## Milestones`` headings. The
project management modal reads and writes ONLY those three sections; everything
else in the file (Obsidian Bases queries, ``## Problem Solving``, the
``## Spawned Activity Registry`` table, …) is preserved byte-for-byte.

Design choices
--------------
* **The matrix is canonical.** The project JSON record (``project_meta.py``)
  stores no copy of the MOM text — the modal reads live from the file, so there
  is no drift to reconcile.
* **Section-targeted edit.** Writing splices the body between a target ``## H``
  heading and the next ``## `` heading (or EOF), leaving every other byte
  untouched. A missing MOM section is inserted in MOM order.
* **Best-effort + vault-sandboxed.** Never raises on a missing vault (cloud-ora
  has none) — returns ``exists: False`` / ``None``. Resolution and writes are
  confined to the vault's ``Matrix/`` directory.

Milestones round-trip both ways: ``read_mom`` returns a parsed ``milestones``
list (``{text, done, indent}`` for ``- [ ]`` / ``- [x]`` task lines) *and* the
raw ``milestones_raw`` markdown, so the modal can offer checkbox editing while
falling back to raw-text editing when a section has non-task content.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

try:
    import yaml  # PyYAML 6.x is available in the runtime
except ImportError:  # pragma: no cover - yaml ships with the runtime
    yaml = None

MOM_HEADINGS = ("Mission", "Objectives", "Milestones")


class MatrixError(Exception):
    """Base class for Matrix identity/resolution failures."""


class MatrixAmbiguityError(MatrixError):
    """More than one Matrix file claims the same project nexus."""


class MatrixMigrationRequiredError(MatrixError):
    """Persisted Matrix/folder identity cannot be used portably as-is."""


def vault_root() -> Path:
    """Resolve the canonical vault root.

    Delegates to the call-time runtime resolver so canonical/legacy override
    conflicts fail loudly and Windows Known Folder redirection is honored.
    """
    accessor = getattr(_rp, "vault_dir", None)
    if callable(accessor):
        return Path(accessor())
    # D-01 remains independently usable on an older runtime_paths module;
    # D-03 replaces this compatibility fallback with the shared accessor.
    raw = os.environ.get("ORA_VAULT_PATH") or os.environ.get("ORA_VAULT")
    return Path(os.path.expanduser(raw or "~/Documents/vault")).resolve()


def _matrix_dir(vault: Path | None = None) -> Path:
    return (vault or vault_root()) / "Matrix"


def _folder_component(folder_name: str, *, vault: Path) -> str:
    """Validate, but never rewrite, a persisted physical folder identity.

    ``folder_name`` is allocated and frozen by :mod:`project_meta`. Re-running
    a sanitizer here would allow separate consumers to derive separate paths.
    Legacy values that are not portable require the explicit folder migration
    rather than being silently mapped to a new Matrix filename on read.
    """
    try:
        try:
            from project_meta import validate_folder_identity, ProjectStorageError
        except ImportError:  # pragma: no cover - package import context
            from orchestrator.project_meta import (
                validate_folder_identity,
                ProjectStorageError,
            )
        return validate_folder_identity(folder_name, vault_root=vault)
    except ProjectStorageError as exc:
        raise MatrixMigrationRequiredError(str(exc)) from exc


def _matrix_filename(folder_name: str, *, vault: Path) -> str:
    return f"Project Matrix {_folder_component(folder_name, vault=vault)}.md"


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[dict[str, Any], int]:
    """Return (parsed frontmatter dict, body_start_index).

    body_start_index is the offset just past the closing ``---`` line; 0 when
    there is no frontmatter. Parse failures degrade to ``({}, 0)``.
    """
    if not text.startswith("---"):
        return {}, 0
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return {}, 0
    raw = m.group(1)
    data: dict[str, Any] = {}
    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw)
            if isinstance(loaded, dict):
                data = loaded
        except yaml.YAMLError:
            data = {}
    return data, m.end()


def _frontmatter_nexus(text: str) -> list[str]:
    fm, _ = _split_frontmatter(text)
    nx = fm.get("nexus")
    if isinstance(nx, list):
        vals = nx
    elif nx:
        vals = [nx]
    else:
        vals = []
    return [str(v).strip().lower() for v in vals if v is not None and str(v).strip()]


# ---------------------------------------------------------------------------
# Matrix file resolution
# ---------------------------------------------------------------------------

def resolve_matrix_path(
    nexus: str, folder_name: str | None = None, *, vault: Path | None = None
) -> Path | None:
    """Find a project's Operation-Matrix file, or None.

    A convention-name candidate is accepted only when its frontmatter claims
    ``nexus``. The full directory is always scanned so duplicate Matrix files
    cannot be hidden by a preferred filename. Duplicate claims raise a typed
    ambiguity error; callers must not guess which canonical file to edit.
    """
    mdir = _matrix_dir(vault)
    if not mdir.is_dir():
        return None
    nexus_l = (nexus or "").strip().lower()
    if not nexus_l or nexus_l in ("commons", "general"):
        return None
    if folder_name:
        # Load-bearing validation: even though resolution is nexus-based, reject
        # a stored physical identity that cannot form a portable Matrix path.
        _ = _matrix_filename(folder_name, vault=mdir.parent)
    matches: list[Path] = []
    for pf in sorted(mdir.glob("*.md")):
        try:
            text = pf.read_text(encoding="utf-8")
        except OSError:
            continue
        if nexus_l in _frontmatter_nexus(text):
            matches.append(pf)
    if len(matches) > 1:
        raise MatrixAmbiguityError(
            f"multiple Matrix files claim nexus {nexus_l!r}: "
            + ", ".join(str(path) for path in matches)
        )
    if matches:
        return matches[0]
    # A convention-name collision belonging to another nexus must not be
    # overwritten during creation. Resolution still returns None so reads
    # correctly report "not created"; _create_matrix raises on the collision.
    return None


# ---------------------------------------------------------------------------
# Section splice
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _section_bounds(text: str, heading: str) -> tuple[int, int, int] | None:
    """Return (heading_line_start, body_start, section_end) for ``## heading``.

    body_start is the offset just past the heading line; section_end is the
    start of the next ``## `` heading, or len(text). None if absent.
    """
    target = heading.strip().lower()
    matches = list(_H2_RE.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == target:
            body_start = m.end()
            if body_start < len(text) and text[body_start] == "\n":
                body_start += 1
            section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return m.start(), body_start, section_end
    return None


def _extract_section(text: str, heading: str) -> str:
    bounds = _section_bounds(text, heading)
    if bounds is None:
        return ""
    _, body_start, section_end = bounds
    return text[body_start:section_end]


def _format_section(heading: str, body: str) -> str:
    """``## Heading`` + a blank line + the (stripped) body + a trailing blank."""
    body = (body or "").strip("\n")
    if body:
        return f"## {heading}\n\n{body}\n\n"
    return f"## {heading}\n\n"


def _insert_index(text: str, heading: str) -> int:
    """Where to splice in a missing MOM section, keeping Mission→Objectives→
    Milestones order and placing the block ahead of any non-MOM section."""
    order = list(MOM_HEADINGS)
    try:
        pos = order.index(heading)
    except ValueError:
        pos = len(order)
    later = {h.lower() for h in order[pos + 1:]}
    for m in _H2_RE.finditer(text):
        name = m.group(1).strip().lower()
        # First section that should come after us (a later MOM heading or any
        # non-MOM heading) is our insertion point.
        if name in later or name not in {h.lower() for h in order}:
            return m.start()
    return len(text)


def _replace_section(text: str, heading: str, body: str) -> str:
    block = _format_section(heading, body)
    bounds = _section_bounds(text, heading)
    if bounds is not None:
        head_start, _, section_end = bounds
        return text[:head_start] + block + text[section_end:]
    idx = _insert_index(text, heading)
    prefix = text[:idx]
    # Guarantee a blank line before the inserted heading.
    if prefix and not prefix.endswith("\n\n"):
        prefix = prefix.rstrip("\n") + "\n\n"
    return prefix + block + text[idx:]


# ---------------------------------------------------------------------------
# Milestone task lists
# ---------------------------------------------------------------------------

_TASK_RE = re.compile(r"^([ \t]*)-[ \t]+\[([ xX])\][ \t]?(.*)$")


def _parse_tasks(raw: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        m = _TASK_RE.match(line)
        if not m:
            continue
        lead = m.group(1).replace("\t", "  ")
        tasks.append({
            "text": m.group(3).strip(),
            "done": m.group(2).lower() == "x",
            "indent": len(lead) // 2,
        })
    return tasks


def parse_milestones(raw: str) -> list[dict[str, Any]]:
    """Public: parse markdown task lines into ``[{text, done, indent}]``."""
    return _parse_tasks(raw)


def render_milestones(milestones: list[dict[str, Any]]) -> str:
    """Public: render ``[{text, done, indent}]`` back to markdown task lines."""
    return _render_tasks(milestones)


def _render_tasks(milestones: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in milestones or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        indent = item.get("indent", 0)
        try:
            indent = max(0, int(indent))
        except (TypeError, ValueError):
            indent = 0
        mark = "x" if item.get("done") else " "
        lines.append(f"{'  ' * indent}- [{mark}] {text}")
    return ("\n".join(lines) + "\n") if lines else ""


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def _empty_mom() -> dict[str, Any]:
    return {
        "exists": False,
        "matrix_path": None,
        "mission": "",
        "objectives": "",
        "milestones": [],
        "milestones_raw": "",
    }


def read_mom(
    nexus: str, folder_name: str | None = None, *, vault: Path | None = None
) -> dict[str, Any]:
    """Read a project's MOM from its Operation-Matrix file.

    Returns ``exists: False`` (with empty fields) when no matrix file is found —
    never raises, so a missing vault degrades gracefully.
    """
    path = resolve_matrix_path(nexus, folder_name, vault=vault)
    if path is None:
        return _empty_mom()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return _empty_mom()
    milestones_raw = _extract_section(text, "Milestones").strip("\n")
    if not milestones_raw:
        # Operations Manifest Appendix A uses the qualified canonical headings,
        # while the older project-management modal reads a single Milestones
        # field.  Keep the physical Matrix canonical and present both Operation
        # milestone classes read-only through the legacy surface.  Server-side
        # writes remain classification-gated to Projects.
        active = (
            _extract_section(text, "Active Milestones (Recurring)")
            or _extract_section(text, "Active Milestones")
        ).strip("\n")
        aspirational = (
            _extract_section(text, "Aspirational Milestones (Maturity Gates)")
            or _extract_section(text, "Aspirational Milestones")
        ).strip("\n")
        blocks: list[str] = []
        if active:
            blocks.append(f"### Active Milestones (Recurring)\n\n{active}")
        if aspirational:
            blocks.append(
                "### Aspirational Milestones (Maturity Gates)\n\n"
                f"{aspirational}"
            )
        milestones_raw = "\n\n".join(blocks)
    return {
        "exists": True,
        "matrix_path": str(path),
        "mission": _extract_section(text, "Mission").strip(),
        "objectives": _extract_section(text, "Objectives").strip(),
        "milestones": _parse_tasks(milestones_raw),
        "milestones_raw": milestones_raw,
    }


def _new_matrix_text(nexus: str, display_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    fm = (
        "---\n"
        "nexus:\n"
        f"  - {nexus}\n"
        "type: matrix\n"
        f"date created: {today}\n"
        f"date modified: {today}\n"
        "---\n\n"
    )
    # The filename is a frozen portable storage identity; the H1 remains the
    # current human-facing label, including punctuation that is not filename-
    # safe. Display-only renames therefore never move the canonical file.
    title = f"# Project Matrix {display_name}\n\n"
    sections = "".join(_format_section(h, "") for h in MOM_HEADINGS)
    return fm + title + sections


def _create_matrix(
    nexus: str,
    folder_name: str,
    display_name: str,
    *,
    vault: Path | None = None,
) -> Path | None:
    mdir = _matrix_dir(vault)
    # A cloud/headless process with no configured vault must not manufacture a
    # parallel Documents/vault tree merely because a user saved MOM fields.
    vroot = mdir.parent
    if not vroot.is_dir():
        return None
    try:
        mdir.mkdir(exist_ok=True)
    except OSError:
        return None
    path = mdir / _matrix_filename(folder_name, vault=vroot)
    created = False
    try:
        # Exclusive creation prevents two projects or concurrent requests from
        # replacing a Matrix file between resolution and creation.
        with path.open("x", encoding="utf-8") as stream:
            created = True
            stream.write(_new_matrix_text(nexus, display_name))
    except FileExistsError:
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MatrixMigrationRequiredError(
                f"Matrix path already exists and could not be verified: {path}"
            ) from exc
        if (nexus or "").strip().lower() in _frontmatter_nexus(existing):
            return path
        raise MatrixMigrationRequiredError(
            f"Matrix path {path} already belongs to another project"
        )
    except OSError:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return None
    return path


def _bump_modified(text: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    fm, body_start = _split_frontmatter(text)
    if not fm or body_start == 0:
        return text
    head = text[:body_start]
    if re.search(r"^date modified:.*$", head, re.MULTILINE):
        head = re.sub(
            r"^date modified:.*$", f"date modified: {today}", head, count=1,
            flags=re.MULTILINE,
        )
    else:
        # Insert before the closing fence.
        head = re.sub(r"\n---\n?$", f"\ndate modified: {today}\n---\n", head, count=1)
    return head + text[body_start:]


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_mom(
    nexus: str,
    folder_name: str | None = None,
    *,
    display_name: str | None = None,
    mission: str | None = None,
    objectives: str | None = None,
    milestones: list[dict[str, Any]] | None = None,
    milestones_raw: str | None = None,
    create_if_missing: bool = True,
    vault: Path | None = None,
) -> dict[str, Any] | None:
    """Patch a project's MOM in its Operation-Matrix file.

    Only the provided sections are touched; ``None`` leaves a section as-is.
    Milestones accept either a structured ``milestones`` list (rendered to
    ``- [ ]`` task lines) or ``milestones_raw`` markdown (``milestones_raw``
    wins if both are given). Creates the matrix file from a template when
    missing and ``create_if_missing`` is True. Returns the re-read MOM, or
    None if no file exists / could be created.
    """
    if (nexus or "").strip().lower() in ("", "commons", "general"):
        return None  # Commons is synthetic — no matrix file
    path = resolve_matrix_path(nexus, folder_name, vault=vault)
    if path is None:
        if not create_if_missing or not folder_name:
            return None
        path = _create_matrix(
            nexus,
            folder_name,
            display_name or folder_name,
            vault=vault,
        )
        if path is None:
            return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if mission is not None:
        text = _replace_section(text, "Mission", mission)
    if objectives is not None:
        text = _replace_section(text, "Objectives", objectives)
    if milestones_raw is not None:
        text = _replace_section(text, "Milestones", milestones_raw)
    elif milestones is not None:
        text = _replace_section(text, "Milestones", _render_tasks(milestones))

    text = _bump_modified(text)
    try:
        _atomic_write(path, text)
    except OSError:
        return None
    return read_mom(nexus, folder_name, vault=vault)


__all__ = [
    "MOM_HEADINGS",
    "MatrixError",
    "MatrixAmbiguityError",
    "MatrixMigrationRequiredError",
    "vault_root",
    "resolve_matrix_path",
    "read_mom",
    "write_mom",
    "parse_milestones",
    "render_milestones",
]
