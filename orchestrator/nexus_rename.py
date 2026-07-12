"""Nexus rename — the bulk-YAML cascade (G1.33 sub-step 5, 3b carry-over).

A project's ``nexus`` is the vault-facing metadata slug stamped into YAML
frontmatter and stored in conversation ``project_ids``. Renaming it therefore
cascades across four surfaces:

  1. **Vault frontmatter** — every ``.md`` whose ``nexus:`` (scalar or block
     list) contains the old slug is rewritten, replacing ONLY that slug and
     preserving everything else in the file byte-for-byte.
  2. **Conversation memberships** — every conversation whose ``project_ids``
     contains the old slug is rewritten to the new one.
  3. **The project pointer** — ``data/projects/<old>.json`` → ``<new>.json``
     (with the internal ``nexus`` field updated).
  4. **The active-project pointer** — bumped if it pointed at the old slug.

Safety
------
* **Dry-run by default.** ``rename_nexus(..., dry_run=True)`` computes and
  returns the full impact report (which files / conversations would change)
  WITHOUT writing anything, so the UI can preview + confirm before executing.
* **Atomic per-file writes** on execute; the vault's 15-minute git auto-commit
  is the recovery net for the bulk frontmatter rewrite.
* **Validated + collision-guarded**: the new slug must be a valid, non-reserved
  nexus that isn't already taken; the old must exist.
* Never raises on an unreadable file — it is skipped and reported.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from orchestrator.project_meta import (
    RESERVED_NEXUS,
    _NEXUS_RE,
    POINTER_DIR,
    _pointer_path,
)
from orchestrator.operation_matrix import vault_root

# Directories never touched by the cascade.
_SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".smart-env"}


class NexusRenameError(Exception):
    pass


# ---------------------------------------------------------------------------
# Frontmatter rewrite (line-based, surgical — preserves the rest of the file)
# ---------------------------------------------------------------------------

def rewrite_frontmatter_nexus(text: str, old: str, new: str) -> str | None:
    """Replace the ``old`` nexus value with ``new`` inside the YAML frontmatter
    ONLY. Handles the scalar (``nexus: old``) and block-list (``nexus:\\n  - old``)
    forms. Returns the rewritten text, or None when nothing changed (so callers
    skip the write)."""
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        return None

    changed = False
    in_nexus = False
    i = 1
    while i < close:
        line = lines[i]
        # `nexus:` (block-list header) — start of the nexus block.
        if re.match(r"^nexus:\s*$", line):
            in_nexus = True
            i += 1
            continue
        # `nexus: <scalar>` — single inline value (comment preserved).
        m_scalar = re.match(r"^nexus:\s+(.*)$", line)
        if m_scalar:
            val, comment = _split_value_comment(m_scalar.group(1))
            if val == old:
                lines[i] = f"nexus: {new}{comment}"
                changed = True
            in_nexus = False
            i += 1
            continue
        if in_nexus:
            m_item = re.match(r"^(\s*-\s+)(.*)$", line)
            if m_item:
                val, comment = _split_value_comment(m_item.group(2))
                if val == old:
                    lines[i] = f"{m_item.group(1)}{new}{comment}"
                    changed = True
                i += 1
                continue
            # A non-indented, non-list line ends the nexus block.
            if line and not line[0].isspace():
                in_nexus = False
        i += 1

    return "\n".join(lines) if changed else None


def _split_value_comment(raw: str) -> tuple[str, str]:
    """Split a YAML scalar into (value, trailing-comment).

    The value is unquoted; ``comment`` keeps its leading whitespace + ``#`` so
    it can be re-appended verbatim. A ``#`` without preceding whitespace (or one
    inside a quoted string) is treated as part of the value, matching YAML."""
    s = raw.rstrip()
    comment = ""
    if s[:1] not in ("\"", "'"):
        m = re.search(r"(\s+#.*)$", s)
        if m:
            comment = m.group(1)
            s = s[: m.start()]
    val = s.strip().strip("\"'")
    return val, comment


def _frontmatter_has_nexus(text: str, slug: str) -> bool:
    """Cheap check: does the frontmatter's nexus contain ``slug``?"""
    if not text.startswith("---"):
        return False
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return False
    fm = m.group(1)
    # Scalar form.
    ms = re.search(r"^nexus:\s+(.*)$", fm, re.MULTILINE)
    if ms and _split_value_comment(ms.group(1))[0] == slug:
        return True
    # Block-list form: `nexus:` then indented `- slug` items until the next key.
    block = re.search(r"^nexus:\s*$\n((?:[ \t].*\n?)*)", fm, re.MULTILINE)
    if block:
        for line in block.group(1).splitlines():
            m_item = re.match(r"^\s*-\s+(.*)$", line)
            if m_item and _split_value_comment(m_item.group(1))[0] == slug:
                return True
    return False


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _find_vault_files(old: str, vault: Path) -> list[Path]:
    hits: list[Path] = []
    if not vault.is_dir():
        return hits
    for p in vault.rglob("*.md"):
        if any(part in _SKIP_DIRS for part in p.relative_to(vault).parts):
            continue
        try:
            head = p.read_text(encoding="utf-8")[:4096]
        except OSError:
            continue
        if _frontmatter_has_nexus(head, old):
            hits.append(p)
    return hits


def _find_member_conversations(old: str, sessions_root: Path) -> list[tuple[str, list[str]]]:
    """Return [(conversation_id, project_ids)] for threads carrying ``old``."""
    out: list[tuple[str, list[str]]] = []
    if not sessions_root.is_dir():
        return out
    for entry in sessions_root.iterdir():
        if not entry.is_dir():
            continue
        cp = entry / "conversation.json"
        if not cp.exists():
            continue
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pids = data.get("project_ids")
        if isinstance(pids, list) and old in pids:
            out.append((entry.name, [p for p in pids if isinstance(p, str)]))
    return out


def rename_nexus(
    old: str,
    new: str,
    *,
    vault: Path | None = None,
    pointer_dir: Path | None = None,
    sessions_root: Path | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Rename a project's nexus across the vault, conversations, and pointers.

    With ``dry_run=True`` (default) nothing is written — the returned report's
    ``vault_files`` / ``conversations`` lists are the preview. With
    ``dry_run=False`` the cascade is performed atomically per file.
    """
    old = (old or "").strip().lower()
    new = (new or "").strip().lower()
    if old in RESERVED_NEXUS:
        raise NexusRenameError(f"{old!r} is reserved and cannot be renamed")
    if new in RESERVED_NEXUS:
        raise NexusRenameError(f"{new!r} is reserved")
    # Validate BOTH slugs' shape before any path is built from them — guards the
    # pointer-file path against traversal (defense-in-depth; the HTTP route
    # already can't carry a slash, but this module is reusable).
    if not _NEXUS_RE.match(old):
        raise NexusRenameError(f"{old!r} is not a valid nexus")
    if not _NEXUS_RE.match(new):
        raise NexusRenameError(
            f"{new!r} is not a valid nexus (lowercase letters, digits, - and _)")
    if old == new:
        raise NexusRenameError("old and new nexus are the same")

    pdir = pointer_dir or POINTER_DIR
    old_pointer = _pointer_path(old, pdir)
    new_pointer = _pointer_path(new, pdir)
    if not old_pointer.is_file():
        raise NexusRenameError(f"no project pointer for {old!r}")
    if new_pointer.exists():
        raise NexusRenameError(f"a project named {new!r} already exists")

    vroot = vault or vault_root()
    sroot = Path(sessions_root) if sessions_root else _default_sessions_root()

    vault_files = _find_vault_files(old, vroot)
    conversations = _find_member_conversations(old, sroot)

    report: dict[str, Any] = {
        "old": old,
        "new": new,
        "dry_run": dry_run,
        "vault_files": [str(p) for p in vault_files],
        "vault_file_count": len(vault_files),
        "conversations": [cid for cid, _ in conversations],
        "conversation_count": len(conversations),
        "pointer_renamed": False,
        "active_updated": False,
        "errors": [],
    }
    if dry_run:
        return report

    # 1) Vault frontmatter.
    for p in vault_files:
        try:
            text = p.read_text(encoding="utf-8")
            rewritten = rewrite_frontmatter_nexus(text, old, new)
            if rewritten is not None:
                _atomic_write(p, rewritten)
        except OSError as exc:
            report["errors"].append(f"{p}: {exc}")

    # 2) Conversation memberships.
    from conversation_memory import set_conversation_projects
    for cid, pids in conversations:
        new_pids = [new if p == old else p for p in pids]
        try:
            set_conversation_projects(cid, new_pids, sessions_root=sroot)
        except Exception as exc:  # best-effort; report and continue
            report["errors"].append(f"conversation {cid}: {exc}")

    # 3) Project pointer rename (old.json → new.json, internal nexus updated).
    try:
        data = json.loads(old_pointer.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["nexus"] = new
        _atomic_write(new_pointer, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        old_pointer.unlink()
        report["pointer_renamed"] = True
    except (OSError, json.JSONDecodeError) as exc:
        report["errors"].append(f"pointer: {exc}")

    # 4) Active-project pointer.
    try:
        from orchestrator.active_project import get_active_project, set_active_project
        if get_active_project() == old:
            set_active_project(new)
            report["active_updated"] = True
    except Exception as exc:
        report["errors"].append(f"active-project: {exc}")

    return report


def _default_sessions_root() -> Path:
    try:
        from conversation_memory import _DEFAULT_SESSIONS_ROOT
        return _DEFAULT_SESSIONS_ROOT
    except Exception:
        return Path(os.path.expanduser("~/ora/sessions"))


__all__ = ["rename_nexus", "rewrite_frontmatter_nexus", "NexusRenameError"]
