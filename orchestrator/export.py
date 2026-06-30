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

Pandoc-backed formats (docx/pdf) are intentionally **not** implemented here —
they require the bundled Pandoc from the installer step (G1.34 build note). The
server reports them as unavailable until then; this module stays markdown-only
so it never depends on an external binary.

Everything is best-effort and path-sandboxed; it never raises on a missing
vault or a permissions error (cloud-ora has neither vault nor ~/Documents).
"""

from __future__ import annotations

import re
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
    """Canonical frontmatter nexus: empty (General) → bare ``nexus:``; else a
    one-item block list (Schema §10)."""
    slug = (nexus or "").strip().lower()
    if not slug or slug == "general":
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


# Formats this module can produce on its own (no external binary).
NATIVE_FORMATS = ("markdown",)
# Formats that need the bundled Pandoc (installer step) — reported, not built.
PANDOC_FORMATS = ("docx", "pdf")


__all__ = [
    "EXPORTS_DIR",
    "RESOURCES_DIR",
    "NATIVE_FORMATS",
    "PANDOC_FORMATS",
    "ensure_export_dirs",
    "save_output_to_vault",
]
