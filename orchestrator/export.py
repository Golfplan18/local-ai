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
    folder (``<vault>/Projects/<name>/``, the G1.33 binding); otherwise in a
    shared ``<vault>/Outputs/`` folder. (Full-conversation export already lives
    in ``vault_export.export_session_to_vault``; this is the per-output scope.)

  * **Render targets (docx / pdf).** When Pandoc is on the machine, a rendered
    output is converted from its canonical markdown and written to
    ``~/Documents/Ora Exports/``. PDF uses Typst as the engine (the plan's
    bundleable choice). Both are *detected at runtime* — absent Pandoc / engine,
    the format is reported unavailable and nothing breaks. The installer bundles
    Pandoc + Typst so this works out of the box for shipped users; here it works
    once ``brew install pandoc typst`` has run.

Everything is best-effort and path-sandboxed; it never raises on a missing
vault or a permissions error (cloud-ora has neither vault nor ~/Documents).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.operation_matrix import vault_root

# §2.8 LOCKED locations — siblings of ~/Documents/vault, outside the vault.
EXPORTS_DIR = Path.home() / "Documents" / "Ora Exports"
RESOURCES_DIR = Path.home() / "Documents" / "Ora Resources"

# Where non-project ("General") output notes land inside the vault.
DEFAULT_OUTPUTS_SUBDIR = "Outputs"


def ensure_export_dirs(
    exports_dir: Path | None = None, resources_dir: Path | None = None
) -> dict[str, Any]:
    """Best-effort create the Exports/ + Resources/ boundary folders.

    Returns their paths and whether each exists, for the UI's quick-access
    links. Never raises (a sandboxed server may lack ~/Documents access)."""
    ex = exports_dir or EXPORTS_DIR
    res = resources_dir or RESOURCES_DIR
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
    words = re.sub(r"[^\w\s-]", "", (text or "").lower()).split()[:max_words]
    slug = "-".join(words).strip("-")
    return slug or "output"


def _derive_title(content: str) -> str:
    """A short title from the first non-empty / heading line of the content."""
    for line in (content or "").splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:80]
    return "output"


def _unique_path(folder: Path, base: str, suffix: str = ".md") -> Path:
    """A non-colliding path ``folder/base.md`` → ``base-2.md`` …"""
    candidate = folder / f"{base}{suffix}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{base}-{n}{suffix}"
        n += 1
    return candidate


def _format_nexus(nexus: str | None) -> str:
    """Canonical frontmatter nexus: empty (Commons) → bare ``nexus:``; else a
    one-item block list (Schema §10)."""
    slug = (nexus or "").strip().lower()
    if not slug or slug in ("commons", "general"):
        return "nexus:\n"
    return f"nexus:\n  - {slug}\n"


def save_output_to_vault(
    content: str,
    *,
    title: str | None = None,
    project_nexus: str | None = None,
    project_name: str | None = None,
    vault: Path | None = None,
    outputs_subdir: str = DEFAULT_OUTPUTS_SUBDIR,
) -> Path | None:
    """Save one rendered output as a canonical vault markdown note.

    Lands in ``<vault>/Projects/<project_name>/`` when a project is given,
    else ``<vault>/<outputs_subdir>/``. Returns the written path, or None if the
    vault is unavailable (never raises)."""
    if content is None:
        return None
    root = vault or vault_root()
    folder = (
        root / "Projects" / _safe_folder(project_name)
        if project_name
        else root / outputs_subdir
    )
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    display = (title or "").strip() or _derive_title(content)
    today = datetime.now().strftime("%Y-%m-%d")
    path = _unique_path(folder, f"{today} {_slugify(display)}")
    frontmatter = (
        "---\n"
        + _format_nexus(project_nexus)
        + "type: output\n"
        + f"title: {display}\n"
        + "tags:\n  - output\n"
        + f"date created: {today}\n"
        + f"date modified: {today}\n"
        + "---\n\n"
    )
    body = content if content.endswith("\n") else content + "\n"
    try:
        tmp = path.with_suffix(".md.tmp")
        tmp.write_text(frontmatter + body, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return None
    return path


def _safe_folder(name: str | None) -> str:
    cleaned = re.sub(r"[\\/]+", " ", (name or "").strip()).strip()
    return cleaned or "Untitled"


# ---------------------------------------------------------------------------
# Render targets — docx / pdf via Pandoc (detected at runtime)
# ---------------------------------------------------------------------------

# Formats this module can always produce (no external binary).
NATIVE_FORMATS = ("markdown",)
# Formats that need Pandoc (+ a PDF engine for pdf). Available when the binaries
# are present; the installer bundles them.
PANDOC_FORMATS = ("docx", "pdf")

# Homebrew/user installs aren't always on a service's minimal PATH — resolve
# against the common bin dirs too.
_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin")
# PDF engines Pandoc can drive, preferred order (Typst is the plan's choice).
_PDF_ENGINES = ("typst", "weasyprint", "wkhtmltopdf", "tectonic", "xelatex", "pdflatex")


def _which(name: str) -> str | None:
    """Absolute path to ``name``, checking PATH then the common bin dirs."""
    found = shutil.which(name)
    if found:
        return found
    for d in _BIN_DIRS:
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
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
    base = exports_dir or EXPORTS_DIR
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
    "NATIVE_FORMATS",
    "PANDOC_FORMATS",
    "ensure_export_dirs",
    "save_output_to_vault",
    "export_capabilities",
    "export_to_file",
    "pandoc_path",
    "pdf_engine_path",
]
