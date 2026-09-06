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
list (``{text, done, indent}``) *and* the raw ``milestones_raw`` markdown, so
the modal can offer checkbox editing while falling back to raw-text editing
when a section has non-task content.

Two milestone forms exist, reported as ``milestone_form``:

* ``checkbox`` — a Project's ``## Milestones`` section of ``- [ ]`` task lines.
  Structured edits round-trip through the ``milestones`` list.
* ``operation`` — an Operation's Appendix A prose milestones
  (``- **Milestone A1 — …**`` plus verification / status sub-bullets) living
  under ``## Active Milestones (Recurring)`` and ``## Aspirational Milestones
  (Maturity Gates)``. These parse for display but edit as raw markdown, and
  ``write_mom`` splits the composed blob back to its source headings — writing
  them as checkboxes would destroy the form.

A Passion Matrix has no milestones at all by design (``## Practices`` and
``## Directions of Travel`` replace them); saving one must not grow a section.

The ``<!-- MASTER_MATRIX_PROJECTION_START/END -->`` markers that 35 vault
matrices carry are invisible to readers and preserved across writes: reads stop
at the closing marker, writes re-attach it with the file's own separator.
"""

from __future__ import annotations

import os
import re
import stat
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
    m = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
    if not m:
        return {}, 0
    raw = m.group(1)
    data: dict[str, Any] = {}
    if yaml is not None:
        try:
            loaded = yaml.safe_load(raw)
            if isinstance(loaded, dict):
                data = loaded
        except (yaml.YAMLError, ValueError, RecursionError):
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
    result = resolve_matrix_snapshots({nexus: folder_name}, vault=vault)[nexus]
    if isinstance(result, Exception):
        raise result
    return result[0] if result else None


def resolve_matrix_snapshots(
    requests: dict[str, str | None], *, vault: Path | None = None,
) -> dict[str, tuple[Path, bytes] | Exception | None]:
    """Resolve many nexuses in one directory pass, with per-project failures.

    This is the same authority used by single-target resolution, not a cache.
    The byte snapshots let a read-only caller avoid reopening every Matrix.
    """
    mdir = _matrix_dir(vault)
    results: dict[str, Any] = {key: None for key in requests}
    if not mdir.exists():
        return results
    if mdir.is_symlink() or not mdir.is_dir():
        return {key: MatrixError("Matrix storage is not a regular directory") for key in requests}
    wanted: dict[str, list[str]] = {}
    candidates: dict[str, str] = {}
    for key, folder in requests.items():
        normalized = (key or "").strip().lower()
        if not normalized or normalized in ("commons", "general"):
            continue
        try:
            if folder:
                candidates[_matrix_filename(folder, vault=mdir.parent)] = key
            wanted.setdefault(normalized, []).append(key)
        except MatrixError as exc:
            results[key] = exc
    matches: dict[str, list[tuple[Path, bytes]]] = {key: [] for key in wanted}
    for path in sorted(mdir.glob("*.md")):
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise OSError("Matrix is not a regular nonsymlink file")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise OSError("Matrix changed while reading")
                raw = stream.read()
            for claim in set(_frontmatter_nexus(raw.decode("utf-8"))) & wanted.keys():
                matches[claim].append((path, raw))
        except (OSError, UnicodeError) as exc:
            if path.name in candidates:
                results[candidates[path.name]] = MatrixError(str(exc))
    for claim, keys in wanted.items():
        found = matches[claim]
        for key in keys:
            if len(found) > 1:
                results[key] = MatrixAmbiguityError(f"Multiple Matrix files claim nexus {claim!r}")
            elif found and not isinstance(results[key], Exception):
                results[key] = found[0]
    return results


# ---------------------------------------------------------------------------
# Project order
# ---------------------------------------------------------------------------

def list_active_project_meta(
    pointer_dir: Path | None = None,
    *,
    skipped_authority: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return active real projects in the canonical project-metadata order.

    ``project_meta.list_project_meta`` owns both explicit priority ranks and
    immutable-nexus tie-breaking for tied and unranked projects.  Filtering
    that list in place keeps both guarantees; this consumer must not sort it a
    second time or maintain a competing order.
    """
    # Lazy import avoids the existing reverse dependency used only by
    # project_meta's explicit Matrix-identity migration path.
    try:
        import project_meta as _project_meta
    except ImportError:  # pragma: no cover - package-qualified import context
        from orchestrator import project_meta as _project_meta

    return [
        meta
        for meta in _project_meta.list_project_meta(
            pointer_dir, skipped_authority=skipped_authority,
        )
        if not meta.get("is_default") and meta.get("status") == "active"
    ]


# ---------------------------------------------------------------------------
# Section splice
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_PROJECTION_END_RE = re.compile(
    r"^[ \t]*<!--[ \t]*MASTER_MATRIX_PROJECTION_END[ \t]*-->[ \t]*\r?$", re.MULTILINE
)


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
    # Stop at the projection END marker so it never leaks into the editable
    # body. Read and write are symmetric about this line: the marker is
    # invisible to the reader and re-attached by ``_replace_section``, so a
    # round-trip neither drops nor duplicates it.
    return text[body_start:_protected_tail_start(text, body_start, section_end)]


def _format_section(heading: str, body: str, newline: str = "\n") -> str:
    """``## Heading`` + a blank line + the (stripped) body + a trailing blank."""
    body = (body or "").strip("\r\n")
    if body:
        return f"## {heading}{newline}{newline}{body}{newline}{newline}"
    return f"## {heading}{newline}{newline}"


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


def _protected_tail_start(text: str, body_start: int, section_end: int) -> int:
    """Offset where trailing content that must survive a section rewrite begins.

    35 of the vault's Matrix files wrap their strategic block in
    ``<!-- MASTER_MATRIX_PROJECTION_START … -->`` / ``<!-- …_END -->`` markers
    projected from ``Administration/Reference — Master Matrix.md``. ``Milestones``
    is the last section inside that block, so its span runs past the closing
    marker to the next ``## `` heading — and a naive splice deletes the marker,
    breaking the projection's authentication for every governed matrix.

    Returns ``section_end`` when there is nothing to protect.
    """
    m = _PROJECTION_END_RE.search(text, body_start, section_end)
    return m.start() if m else section_end


def _replace_section(text: str, heading: str, body: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    block = _format_section(heading, body, newline)
    bounds = _section_bounds(text, heading)
    if bounds is not None:
        head_start, body_start, section_end = bounds
        tail_start = _protected_tail_start(text, body_start, section_end)
        if tail_start < section_end:
            # Protected content (the projection END marker) trails the body.
            # Rebuild around it using the file's own separator so an unchanged
            # save is byte-identical rather than drifting a blank line each time.
            original = text[body_start:tail_start]
            sep = original[len(original.rstrip("\r\n")):] or newline
            core = (body or "").strip("\r\n")
            block = f"## {heading}{newline}{newline}{core}{sep}" if core else f"## {heading}{newline}{newline}"
        return text[:head_start] + block + text[tail_start:]
    # Never conjure a section that does not exist just to hold nothing — a
    # Passion Matrix has no ``## Milestones`` by design (Practices and
    # Directions of Travel replace it), and saving must not grow one.
    if not (body or "").strip():
        return text
    idx = _insert_index(text, heading)
    prefix = text[:idx]
    # Guarantee a blank line before the inserted heading.
    if prefix and not prefix.endswith(newline * 2):
        prefix = prefix.rstrip("\r\n") + newline * 2
    return prefix + block + text[idx:]


# ---------------------------------------------------------------------------
# Milestone task lists
# ---------------------------------------------------------------------------

_TASK_RE = re.compile(r"^([ \t]*)-[ \t]+\[([ xX])\][ \t]?(.*)$")
_BULLET_RE = re.compile(r"^([ \t]*)-[ \t]+(.*)$")


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


#: An Operation Matrix records milestones as prose bullets, not checkboxes —
#: ``- **Milestone A1 — Statement.** …`` or ``- **Milestone B1:** …`` — per the
#: Operations Manifest Appendix A template, each followed by indented
#: Delivering-framework / Verification-criterion / Status sub-bullets.
_OPERATION_MILESTONE_RE = re.compile(
    r"^([ \t]*)-[ \t]+\*\*(Milestone[^*]*)\*\*[ \t]*(.*)$"
)


#: ``read_mom`` composes an Operation's milestones from these two ``## ``
#: sections into one ``### ``-delimited blob; ``write_mom`` splits on the same
#: delimiters to put each body back where it came from. Without the split, a
#: write would append a synthetic ``## Milestones`` section duplicating content
#: that already lives under the Appendix A headings.
_OPERATION_MILESTONE_SECTIONS = (
    "Active Milestones (Recurring)",
    "Aspirational Milestones (Maturity Gates)",
)
_H3_RE = re.compile(r"^###[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _split_operation_milestones(raw: str) -> dict[str, str] | None:
    """Split a composed Operation milestones blob back into {heading: body}.

    Returns None when ``raw`` is not in the composed shape, so the caller falls
    back to writing a single ``## Milestones`` section.
    """
    heads = list(_H3_RE.finditer(raw or ""))
    if not heads:
        return None
    known = {h.lower(): h for h in _OPERATION_MILESTONE_SECTIONS}
    out: dict[str, str] = {}
    for i, m in enumerate(heads):
        name = known.get(m.group(1).strip().lower())
        if name is None:
            return None  # unrecognized shape — do not guess
        end = heads[i + 1].start() if i + 1 < len(heads) else len(raw)
        out[name] = raw[m.end():end].strip("\n")
    return out or None


def has_operation_milestones(raw: str) -> bool:
    """True when the section uses the Operation prose form rather than tasks."""
    return any(
        _OPERATION_MILESTONE_RE.match(line) for line in (raw or "").splitlines()
    )


def _parse_operation_milestones(raw: str) -> list[dict[str, Any]]:
    """Parse Operation prose milestones for DISPLAY.

    ``done`` is always False: a recurring per-cycle milestone has no binary
    completed state — its disposition lives in the ``Status:`` sub-bullet, which
    is preserved as an indented child row. These rows are display-only; edits
    round-trip through ``milestones_raw`` so the Appendix A form is never
    rewritten into checkboxes.
    """
    items: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        m = _OPERATION_MILESTONE_RE.match(line)
        if m:
            label = m.group(2).strip().rstrip(":").strip()
            trailing = m.group(3).strip()
            items.append({
                "text": f"{label} {trailing}".strip() if trailing else label,
                "done": False,
                "indent": len(m.group(1).replace("\t", "  ")) // 2,
            })
            continue
        b = _BULLET_RE.match(line)
        if b and items:
            # Sub-bullet of the milestone above it (verification criterion,
            # status, P-Feasibility verdict).
            items.append({
                "text": b.group(2).strip(),
                "done": False,
                "indent": max(1, len(b.group(1).replace("\t", "  ")) // 2),
            })
    return items


def parse_milestones(raw: str) -> list[dict[str, Any]]:
    """Public: parse a Milestones section into ``[{text, done, indent}]``.

    Handles both the Project checkbox form and the Operation prose form.
    """
    if has_operation_milestones(raw):
        return _parse_operation_milestones(raw)
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
        text = path.read_bytes().decode("utf-8")
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
    operation_form = has_operation_milestones(milestones_raw)
    return {
        "exists": True,
        "matrix_path": str(path),
        "mission": _extract_section(text, "Mission").strip(),
        "objectives": _extract_section(text, "Objectives").strip(),
        "milestones": parse_milestones(milestones_raw),
        "milestones_raw": milestones_raw,
        # "operation" milestones are prose (Operations Manifest Appendix A) and
        # must be edited as raw markdown — rendering them as checkboxes would
        # rewrite the form and drop the verification / status sub-bullets.
        "milestone_form": "operation" if operation_form else "checkbox",
    }


def _new_matrix_text(nexus: str, display_name: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    fm = (
        "---\n"
        "nexus:\n"
        f"  - {nexus}\n"
        "type: matrix\n"
        # Required in list form: the MOM write gate rejects a matrix whose
        # project_type is absent or scalar, so omitting it here would make every
        # matrix Ora creates unwritable on its very next save.
        "project_type:\n"
        "  - project\n"
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
    newline = "\r\n" if "\r\n" in head else "\n"
    if re.search(r"^date modified:[^\r\n]*", head, re.MULTILINE):
        head = re.sub(
            r"^date modified:[^\r\n]*", f"date modified: {today}", head, count=1,
            flags=re.MULTILINE,
        )
    else:
        # Insert before the closing fence.
        closing = head.rfind("---")
        head = head[:closing] + f"date modified: {today}" + newline + head[closing:]
    return head + text[body_start:]


def _atomic_write(path: Path, text: str) -> None:
    _rp.atomic_write_bytes(path, text.encode("utf-8"), mode=stat.S_IMODE(path.stat().st_mode))


def _write_mom_locked(
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
    if (
        mission is None and objectives is None
        and milestones is None and milestones_raw is None
    ):
        # Nothing to patch. Returning early keeps a no-op save from re-stamping
        # `date modified`, which the vault's auto-sync would otherwise commit as
        # a spurious change to every matrix the user merely opened.
        return read_mom(nexus, folder_name, vault=vault)
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
        text = path.read_bytes().decode("utf-8")
    except OSError:
        return None

    if mission is not None:
        text = _replace_section(text, "Mission", mission)
    if objectives is not None:
        text = _replace_section(text, "Objectives", objectives)
    if milestones_raw is not None:
        # An Operation Matrix has no ``## Milestones`` section — its milestones
        # live under the Appendix A headings. Write each body back to the
        # section it was read from rather than appending a duplicate.
        split = (
            _split_operation_milestones(milestones_raw)
            if _section_bounds(text, "Milestones") is None
            else None
        )
        if split:
            for heading, body in split.items():
                if _section_bounds(text, heading) is not None:
                    text = _replace_section(text, heading, body)
        else:
            text = _replace_section(text, "Milestones", milestones_raw)
    elif milestones is not None:
        text = _replace_section(text, "Milestones", _render_tasks(milestones))

    text = _bump_modified(text)
    try:
        _atomic_write(path, text)
    except OSError:
        return None
    return read_mom(nexus, folder_name, vault=vault)


def write_mom(nexus: str, folder_name: str | None = None, **kwargs) -> dict[str, Any] | None:
    """Hold the shared Matrix lock through MOM's complete read/splice/write."""
    try:
        from runtime_hygiene import mutation_path_locks
    except ImportError:  # pragma: no cover
        from orchestrator.runtime_hygiene import mutation_path_locks
    vault = kwargs.get("vault")
    path = resolve_matrix_path(nexus, folder_name, vault=vault)
    if path is None:
        if (nexus or "").strip().lower() in ("", "commons", "general") or not folder_name:
            return _write_mom_locked(nexus, folder_name, **kwargs)
        path = _matrix_dir(vault) / _matrix_filename(folder_name, vault=_matrix_dir(vault).parent)
    with mutation_path_locks([path]):
        current = resolve_matrix_path(nexus, folder_name, vault=vault)
        if current is not None and current != path:
            raise MatrixError("Matrix identity changed while waiting to save")
        return _write_mom_locked(nexus, folder_name, **kwargs)


def read_tasks(nexus: str, folder_name: str | None = None, *, vault: Path | None = None):
    try:
        from . import matrix_tasks
    except ImportError:
        import matrix_tasks
    return matrix_tasks.read_group(nexus, folder_name, vault=vault)


def write_tasks(nexus: str, folder_name: str, body: dict, *, vault: Path | None = None,
                identity_check=None):
    try:
        from . import matrix_tasks
    except ImportError:
        import matrix_tasks
    return matrix_tasks.write_group(nexus, folder_name, body, vault=vault, identity_check=identity_check)


__all__ = [
    "MOM_HEADINGS",
    "MatrixError",
    "MatrixAmbiguityError",
    "MatrixMigrationRequiredError",
    "vault_root",
    "resolve_matrix_path",
    "resolve_matrix_snapshots",
    "read_tasks",
    "write_tasks",
    "list_active_project_meta",
    "read_mom",
    "write_mom",
    "parse_milestones",
    "render_milestones",
    "has_operation_milestones",
]
