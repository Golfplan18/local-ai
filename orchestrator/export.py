"""Output export (G1.34).

Markdown + YAML frontmatter is **canonical**; every other format is a render
target (Export §1.9). This module owns:

  * **The workspace boundary (§2.8, LOCKED).** Ora-generated non-markdown lands
    in ``~/Documents/Ora Exports/``; externally-brought files live in
    ``~/Documents/Ora Resources/`` — both siblings of the vault, OUTSIDE it so
    Obsidian never indexes binaries, but inside ``~/Documents/`` where users
    look. The vault itself stays markdown-only.
  * **Save-to-Vault (markdown).** A single rendered output is saved as a vault
    markdown note. When a project is active the note lands in that project's
    folder (``<vault>/Projects/<name>/``, the G1.33 binding); Commons output
    lands at the vault root. (Full-Dialogue export already lives in
    ``vault_export.export_session_to_vault``; this is the per-output scope.)

  * **Render targets (docx / pdf).** When Pandoc is on the machine, a rendered
    output is converted from its canonical markdown and written to
    ``~/Documents/Ora Exports/``. PDF uses Typst as the engine. Both are
    *detected at runtime* — absent Pandoc / engine, the format is reported
    unavailable and nothing breaks.

    Neither program ships inside this repository (Pandoc is GPL-2.0-or-later;
    vendoring it here would be redistribution). ``scripts/converters.py``,
    which the installer runs, downloads the publishers' own pinned releases
    into ``<ORA_HOME>/data/converters/bin`` — ``converters_dir()`` below —
    unless the machine already has them. Detection looks at ``PATH`` first, so
    a Homebrew / WinGet / hand-rolled install always wins over Ora's copy. If
    provisioning was skipped or failed, ``python3 scripts/install.py
    converters`` re-runs it.

Everything is best-effort and path-sandboxed; it never raises on a missing
vault or a permissions error (cloud-ora has neither vault nor ~/Documents).
"""

from __future__ import annotations

import yaml
from orchestrator.project_documents import DocumentIdentity, require_valid_document

import os
import ntpath
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator import runtime_paths as _rp
from orchestrator.operation_matrix import vault_root

# §2.8 LOCKED locations — siblings of ~/Documents/vault, outside the vault.
_INITIAL_EXPORTS_DIR = _rp.DOCUMENTS / "Ora Exports"
_INITIAL_RESOURCES_DIR = _rp.DOCUMENTS / "Ora Resources"
EXPORTS_DIR = _INITIAL_EXPORTS_DIR  # compatibility patch hook
RESOURCES_DIR = _INITIAL_RESOURCES_DIR  # compatibility patch hook

PROJECT_OUTPUT_CHILD_BUDGET_UNITS = 120
WINDOWS_PORTABLE_PATH_LIMIT = 240


class ExportError(Exception):
    """Base class for explicit export failures."""


class ProjectExportIdentityError(ExportError):
    """A requested project does not have one usable persisted identity."""


class ProjectExportNotFoundError(ProjectExportIdentityError):
    """The requested non-Common project record does not exist."""


class ProjectExportMigrationRequiredError(ProjectExportIdentityError):
    """The requested project's physical identity requires migration."""


class ExportPathError(ExportError):
    """The destination leaves no safe Windows filename budget."""


def current_exports_dir() -> Path:
    """Configured generated-export root, resolved at call time."""
    if Path(EXPORTS_DIR) != _INITIAL_EXPORTS_DIR:
        return Path(EXPORTS_DIR)
    return _rp.documents_dir() / "Ora Exports"


def current_resources_dir() -> Path:
    """Configured imported-resource root, resolved at call time."""
    if Path(RESOURCES_DIR) != _INITIAL_RESOURCES_DIR:
        return Path(RESOURCES_DIR)
    return _rp.documents_dir() / "Ora Resources"


def ensure_export_dirs(
    exports_dir: Path | None = None, resources_dir: Path | None = None
) -> dict[str, Any]:
    """Best-effort create the Exports/ + Resources/ boundary folders.

    Returns their paths and whether each exists, for the UI's quick-access
    links. Never raises (a sandboxed server may lack ~/Documents access)."""
    ex = Path(exports_dir) if exports_dir is not None else current_exports_dir()
    res = Path(resources_dir) if resources_dir is not None else current_resources_dir()
    out: dict[str, Any] = {}
    for key, path in (("exports", ex), ("resources", res)):
        try:
            path.mkdir(parents=True, exist_ok=True)
            exists = path.is_dir()
        except OSError:
            exists = path.is_dir()
        out[key] = {"path": str(path), "exists": exists}
    return out


def _slugify(text: str, max_words: int = 8) -> str:
    normalized = unicodedata.normalize("NFC", text or "")
    words = re.sub(r"[^\w\s-]", "", normalized.lower()).split()[:max_words]
    slug = "-".join(words).strip("-")
    return slug or "output"


def _derive_title(content: str) -> str:
    """A short title from the first non-empty / heading line of the content."""
    for line in (content or "").splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:80]
    return "output"


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _truncate_utf16(value: str, limit: int) -> str:
    out: list[str] = []
    used = 0
    for char in value:
        width = _utf16_units(char)
        if used + width > limit:
            break
        out.append(char)
        used += width
    return "".join(out)


def _filename_budget(folder: Path, *, project_output: bool) -> int:
    remaining = (
        WINDOWS_PORTABLE_PATH_LIMIT
        - _utf16_units(str(folder.resolve(strict=False)).rstrip("/\\"))
        - 1
    )
    if project_output:
        remaining = min(remaining, PROJECT_OUTPUT_CHILD_BUDGET_UNITS)
    if remaining < _utf16_units("x.md.tmp"):
        raise ExportPathError(
            "destination path is too deep for a portable output filename"
        )
    return remaining


def _unique_path(
    folder: Path,
    base: str,
    suffix: str = ".md",
    *,
    project_output: bool = False,
) -> Path:
    """Return a non-colliding path within the full Windows path budget.

    The base is re-truncated for every numeric collision marker. ``.tmp`` is
    reserved because the write path appends it to the final extension.
    """
    budget = _filename_budget(folder, project_output=project_output)
    n = 1
    while True:
        marker = "" if n == 1 else f"-{n}"
        fixed = marker + suffix + ".tmp"
        base_budget = budget - _utf16_units(fixed)
        if base_budget < 1:
            raise ExportPathError(
                "destination path leaves no room for a portable output basename"
            )
        bounded = _truncate_utf16(base, base_budget).rstrip(" .-") or "output"
        bounded = _truncate_utf16(bounded, base_budget).rstrip(" .-") or "x"
        candidate = folder / f"{bounded}{marker}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _format_nexus(nexus: str | None) -> str:
    """Canonical frontmatter nexus: empty (Commons) → bare ``nexus:``; else a
    one-item block list (Schema §10)."""
    slug = (nexus or "").strip().lower()
    if not slug or slug in ("commons", "general"):
        return "nexus:\n"
    return yaml.safe_dump({"nexus": [slug]}, allow_unicode=True).replace("\n-", "\n  -")


def save_output_to_vault(
    content: str,
    *,
    title: str | None = None,
    project_nexus: str | None = None,
    project_name: str | None = None,
    project_folder_name: str | None = None,
    vault: Path | None = None,
    outputs_subdir: str | None = None,
    turn_privacy: str = "standard",
    warnings: list[str] | None = None,
) -> Path | None:
    """Save one rendered output as a canonical vault markdown note.

    A real project is resolved from its pointer and its exact persisted
    ``folder_name`` is the only accepted physical identity. ``project_name`` is
    retained only to fail old project callers loudly; it is never a storage
    fallback. Non-project callers retain the explicit ``outputs_subdir``
    compatibility path. A Private source stays visibly and mechanically
    Private. A Stealth source is the deliberate destination-owned exception:
    it carries neither a privacy label nor a source-mode marker. Returns None
    when the vault itself is unavailable.
    """
    if content is None:
        return None
    if turn_privacy not in {"standard", "private", "stealth"}:
        raise ValueError("turn_privacy must be standard, private, or stealth")
    root = Path(vault or vault_root())
    if not root.is_dir():
        return None

    canonical_nexus = (project_nexus or "").strip().lower()
    is_project = canonical_nexus not in ("", "commons", "general")
    if project_name is not None:
        raise ProjectExportIdentityError(
            "project_name is not a storage identity; pass only project_nexus"
        )
    if is_project:
        if outputs_subdir:
            raise ProjectExportIdentityError(
                "outputs_subdir cannot override a project's persisted folder"
            )
        try:
            from orchestrator import project_meta as _pm
            _pm.validate_existing_nexus_source(canonical_nexus)
            record = _pm.read_project_meta(canonical_nexus)
        except Exception as exc:
            raise ProjectExportIdentityError(
                f"could not resolve project {canonical_nexus!r}: {exc}"
            ) from exc
        if record is None or record.get("is_default"):
            raise ProjectExportNotFoundError(
                f"no project record for {canonical_nexus!r}"
            )
        persisted = record.get("folder_name")
        if project_folder_name is not None and project_folder_name != persisted:
            raise ProjectExportIdentityError(
                "supplied project_folder_name does not match the persisted identity"
            )
        try:
            folder = _pm.project_folder_path(
                persisted,
                vault_projects_dir=root / "Projects",
            )
        except _pm.ProjectStorageError as exc:
            raise ProjectExportMigrationRequiredError(str(exc)) from exc
    elif project_folder_name is not None:
        raise ProjectExportIdentityError(
            "project_folder_name requires a real persisted project nexus"
        )
    elif outputs_subdir:
        folder = root / _safe_folder(outputs_subdir)
    else:
        folder = root
    display = (title or "").strip() or _derive_title(content)
    today = datetime.now().strftime("%Y-%m-%d")
    path = _unique_path(
        folder,
        f"{today} {_slugify(display)}",
        project_output=is_project,
    )
    tags = ["output"]
    if turn_privacy == "private":
        tags.append("private")
    frontmatter = (
        "---\n"
        + _format_nexus(project_nexus)
        + "type: output\n"
        + yaml.safe_dump({"title": display}, allow_unicode=True, sort_keys=False)
        + "tags:\n"
        + "".join(f"  - {tag}\n" for tag in tags)
        + f"date created: {today}\n"
        + f"date modified: {today}\n"
        + "---\n\n"
    )
    body = output_content_for_privacy(content, turn_privacy)
    body = body if body.endswith("\n") else body + "\n"
    report = require_valid_document(
        frontmatter + body,
        DocumentIdentity((canonical_nexus,) if is_project else (), path.name,
                         created=today, modified=today),
        owner="output",
    )
    if warnings is not None:
        warnings.extend(report.warning_messages)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(frontmatter + body, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return None
    return path


def output_content_for_privacy(content: str, turn_privacy: str) -> str:
    """Apply the explicit-export privacy presentation to canonical content.

    Standard output needs no extra label. Private output retains a visible
    disclosure even when rendered outside the vault as DOCX/PDF. Stealth
    export is intentionally marker-free under the Dialogue plan.
    """
    if turn_privacy not in {"standard", "private", "stealth"}:
        raise ValueError("turn_privacy must be standard, private, or stealth")
    if turn_privacy == "private":
        return "**Privacy:** Private\n\n" + content
    return content


def _safe_folder(name: str | None) -> str:
    cleaned = re.sub(r"[\\/]+", " ", (name or "").strip()).strip()
    return cleaned if cleaned and cleaned not in (".", "..") else "Untitled"


# ---------------------------------------------------------------------------
# Render targets — docx / pdf via Pandoc (detected at runtime)
# ---------------------------------------------------------------------------

# Formats this module can always produce (no external binary).
NATIVE_FORMATS = ("markdown",)
# Formats that need Pandoc (+ a PDF engine for pdf). Available when the binaries
# are present; the installer provisions them into ``converters_dir()`` when the
# machine does not already have them (``python3 scripts/install.py converters``).
PANDOC_FORMATS = ("docx", "pdf")

# Package-manager/user installs aren't always on a service's minimal PATH.
_POSIX_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
# PDF engines Pandoc can drive, preferred order (Typst is the plan's choice).
_PDF_ENGINES = ("typst", "weasyprint", "wkhtmltopdf", "tectonic", "xelatex", "pdflatex")


def converters_dir() -> Path:
    """Where Ora keeps the converters it provisioned itself.

    ``scripts/converters.py`` downloads Pandoc and Typst here when the machine
    has neither, and ``_binary_search_dirs`` looks here — after ``PATH`` — so a
    converter the user installed some other way is always preferred. Resolved
    at call time so a relocated ``ORA_HOME`` is honored.
    """
    return Path(_rp.DATA_DIR_STR) / "converters" / "bin"


def _binary_search_dirs(
    platform_name: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """Extra service-PATH locations for the current operating system.

    Ora's own converter directory comes first: it is the one location this
    project provisions, so it is the one location it can vouch for. ``PATH``
    still wins over the whole list — see ``_which``.
    """
    platform_name = platform_name or os.name
    ora_owned = str(converters_dir())
    if platform_name != "nt":
        return (ora_owned, *_POSIX_BIN_DIRS)
    env = os.environ if env is None else env
    out: list[str] = [ora_owned]

    def add(root: str | None, *parts: str) -> None:
        if root:
            out.append(ntpath.join(root, *parts))

    add(env.get("LOCALAPPDATA"), "Pandoc")
    add(env.get("ProgramFiles"), "Pandoc")
    add(env.get("ProgramFiles(x86)"), "Pandoc")
    add(env.get("ProgramData"), "chocolatey", "bin")
    add(env.get("USERPROFILE"), "scoop", "shims")
    add(env.get("USERPROFILE"), ".cargo", "bin")
    add(env.get("LOCALAPPDATA"), "Microsoft", "WinGet", "Links")
    return tuple(dict.fromkeys(out))


def _which(name: str) -> str | None:
    """Absolute path to ``name``, honoring PATHEXT and common install dirs."""
    found = shutil.which(name)
    if found:
        return found
    for directory in _binary_search_dirs():
        found = shutil.which(name, path=directory)
        if found:
            return found
    return None


def pandoc_path() -> str | None:
    return _which("pandoc")


def pdf_engine_path() -> tuple[str, str] | None:
    """Return (engine_name, engine_abs_path) for the first available PDF engine."""
    for eng in _PDF_ENGINES:
        p = _which(eng)
        if p:
            return eng, p
    return None


def export_capabilities() -> dict[str, Any]:
    """What non-markdown formats this machine can currently produce."""
    pandoc = pandoc_path() is not None
    engine = pdf_engine_path()
    return {
        "pandoc": pandoc,
        "docx": pandoc,
        "pdf": pandoc and engine is not None,
        "pdf_engine": engine[0] if engine else None,
    }


def export_to_file(
    content: str,
    *,
    title: str | None = None,
    fmt: str = "docx",
    exports_dir: Path | None = None,
) -> Path | None:
    """Render one output's canonical markdown to ``fmt`` (docx/pdf) via Pandoc,
    landing in ``~/Documents/Ora Exports/`` (the §2.8 boundary). Returns the
    written path, or None if the content is empty, the format is unsupported, or
    Pandoc / the PDF engine isn't available. Never raises."""
    if not content or not content.strip() or fmt not in PANDOC_FORMATS:
        return None
    pandoc = pandoc_path()
    if pandoc is None:
        return None
    base = Path(exports_dir) if exports_dir is not None else current_exports_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    display = (title or "").strip() or _derive_title(content)
    today = datetime.now().strftime("%Y-%m-%d")
    out = _unique_path(base, f"{today} {_slugify(display)}", "." + fmt)

    tmp_md = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(content)
            tmp_md = tf.name
        cmd = [pandoc, tmp_md, "-o", str(out)]
        if fmt == "pdf":
            engine = pdf_engine_path()
            if engine is None:
                return None
            cmd += ["--pdf-engine", engine[1]]
        subprocess.run(cmd, check=True, capture_output=True, timeout=90)
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if tmp_md:
            try:
                os.unlink(tmp_md)
            except OSError:
                pass
    return out if out.exists() else None


__all__ = [
    "EXPORTS_DIR",
    "RESOURCES_DIR",
    "current_exports_dir",
    "current_resources_dir",
    "NATIVE_FORMATS",
    "PANDOC_FORMATS",
    "converters_dir",
    "ensure_export_dirs",
    "save_output_to_vault",
    "output_content_for_privacy",
    "export_capabilities",
    "export_to_file",
    "pandoc_path",
    "pdf_engine_path",
]
