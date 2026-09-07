"""Explicit, shallow folder orientation from existing local authorities.

Preview with ``python -m orchestrator.project_orientation --ora-root ROOT
--vault ROOT``. Only ``--write`` replaces the marked ``Directory Map.md``.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

from orchestrator import operation_matrix, project_meta, runtime_paths
from orchestrator.project_documents import DocumentIdentity, inspect_document, require_valid_document


MAP_NAME = "Directory Map.md"
MARKER = "<!-- ora-generated-directory-map -->"
NO_DESCRIPTION = "No recorded description"


@dataclass
class DirectoryMap:
    text: str
    issues: list[str]

    @property
    def complete(self) -> bool:
        return not self.issues


def _root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise ValueError("selected root must not be a symlink")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("selected root must be an existing directory")
    return path


def _safe_path(path: Path, root: Path, *, directory: bool = False) -> os.stat_result:
    """Check each component before inspecting or opening the selected object."""
    relative = path.relative_to(root)
    if ".." in relative.parts:
        raise ValueError("path escapes the selected root")
    current = root
    result = root.lstat()
    for index, part in enumerate(relative.parts):
        current = current / part
        result = current.lstat()
        if stat.S_ISLNK(result.st_mode):
            raise ValueError("symlinks are not followed")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(result.st_mode):
            raise ValueError("parent is not a regular directory")
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(result.st_mode):
        raise ValueError("not a regular directory" if directory else "not a regular file")
    return result


def _read(path: Path, root: Path) -> bytes:
    before = _safe_path(path, root)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("source changed while reading")
        return stream.read()


def _literal(value: str) -> str:
    # Names/descriptions are source text, never executable Markdown or HTML.
    value = html.escape(value, quote=False)
    value = re.sub(r"([\\`*{}\[\]()#+.!_|>~-])", r"\\\1", value)
    return value.replace("\r", " ").replace("\n", " ")


def _link(label: str, relative: Path) -> str:
    return f"[{_literal(label)}]({quote(relative.as_posix(), safe='/')})"


def _root_descriptions(vault: Path, issues: list[str]) -> dict[str, str]:
    try:
        text = _read(vault / "AGENTS.md", vault).decode("utf-8")
    except (OSError, UnicodeError, ValueError):
        issues.append("Root descriptions unavailable: AGENTS.md is missing, unsafe or unreadable.")
        return {}
    section = re.search(r"^## Key Directory Structure[ \t]*\r?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not section:
        issues.append("Root descriptions unavailable: AGENTS.md has no Key Directory Structure section.")
        return {}
    descriptions: dict[str, str] = {}
    seen: set[str] = set()
    for block in re.finditer(r"^### ([^/\r\n]+)/[ \t]*\r?\n(.*?)(?=^### |\Z)", section[1], re.M | re.S):
        name = block[1]
        if name in seen:
            descriptions.pop(name, None)
            issues.append(f"Root description unavailable for {_literal(name)}: repeated directory heading.")
            continue
        seen.add(name)
        # A child-directory bullet describes that child, not its parent.
        for line in block[2].splitlines():
            if line.startswith("- ") and not re.match(r"- (?:\*\*|`)?[^\n]+/(?:\*\*|`)?[: ]", line):
                description = line[2:].strip()
                if description:
                    descriptions[name] = description
                    break
    return descriptions


def _projects(ora_root: Path, issues: list[str]) -> list[dict]:
    pointer_dir = ora_root / "data" / "projects"
    try:
        _safe_path(pointer_dir, ora_root, directory=True)
        paths = sorted(pointer_dir.iterdir(), key=lambda path: (path.name.casefold(), path.name))
    except (OSError, ValueError):
        issues.append("Project records unavailable: selected Ora root has no safe readable data/projects directory.")
        return []
    records = []
    for path in paths:
        if path.suffix != ".json" or path.stem in {"commons", "general"}:
            continue
        try:
            nexus = project_meta.validate_existing_nexus_source(path.stem)
            data = json.loads(_read(path, ora_root))
            if not isinstance(data, dict):
                raise ValueError("project record is not a mapping")
            records.append(project_meta._normalize_meta(nexus, data))
        except (OSError, UnicodeError, ValueError):
            issues.append(f"Project record {_literal(path.name)} unavailable: invalid, unsafe or unreadable authority.")
    return sorted(records, key=lambda row: (str(row["folder_name"]).casefold(), str(row["folder_name"]), row["nexus"]))


def _project_rows(vault: Path, records: list[dict], issues: list[str]) -> list[str]:
    requests = {row["nexus"]: row["folder_name"] for row in records}
    # P3 owns Matrix authentication and duplicate detection; one shared scan.
    try:
        _safe_path(vault / "Matrix", vault, directory=True)
        snapshots = operation_matrix.resolve_matrix_snapshots(requests, vault=vault)
    except FileNotFoundError:
        snapshots = {nexus: None for nexus in requests}
    except (OSError, ValueError):
        snapshots = {nexus: operation_matrix.MatrixError("Matrix storage unreadable") for nexus in requests}
    rows = []
    for record in records:
        nexus, folder = record["nexus"], record["folder_name"]
        label = f"{folder}/ ({nexus})" if isinstance(folder, str) else f"Project ({nexus})"
        problems = []
        try:
            folder_path = project_meta.project_folder_path(folder, vault / "Projects")
            _safe_path(folder_path, vault, directory=True)
            location = _link(label, folder_path.relative_to(vault))
        except FileNotFoundError:
            location = _literal(label)
            problems.append("registered folder unavailable: missing")
        except (OSError, ValueError, project_meta.ProjectStorageError):
            location = _literal(label)
            problems.append("registered folder unavailable: unsafe or unreadable")
        snapshot = snapshots.get(nexus)
        description = NO_DESCRIPTION
        matrix = "Matrix unavailable: missing"
        if isinstance(snapshot, operation_matrix.MatrixAmbiguityError):
            matrix = "Matrix unavailable: ambiguous nexus claims"
        elif isinstance(snapshot, Exception):
            matrix = "Matrix unavailable: unsafe or unreadable authority"
        elif snapshot:
            path, raw = snapshot
            try:
                _safe_path(path, vault)
                report = inspect_document(raw.decode("utf-8"), DocumentIdentity(nexuses=(nexus,)), owner="matrix")
                if any(issue.field == "frontmatter" for issue in report.errors):
                    raise ValueError("Matrix frontmatter is malformed or ambiguous")
                value = report.metadata.get("description")
                if isinstance(value, str) and value.strip() and not any(c in value.strip() for c in "\r\n"):
                    description = value.strip()
                matrix = _link("Matrix", path.relative_to(vault))
            except (OSError, UnicodeError, ValueError):
                matrix = "Matrix unavailable: unsafe or unreadable authority"
        if matrix.startswith("Matrix unavailable"):
            problems.append(matrix)
        if problems:
            issues.append(f"Project {_literal(nexus)}: {'; '.join(problems)}.")
        suffix = f"; {'; '.join(problems[:1])}" if problems and problems[0].startswith("registered folder") else ""
        rows.append(f"  - {location} — {_literal(description)}; {matrix}{suffix}")
    return rows


def generate_directory_map(*, ora_root: Path | str, vault: Path | str) -> DirectoryMap:
    """Read the selected sources and compose validated Markdown without writes."""
    ora_root, vault = _root(ora_root), _root(vault)
    issues: list[str] = []
    descriptions = _root_descriptions(vault, issues)
    records = _projects(ora_root, issues)
    project_rows = _project_rows(vault, records, issues)
    folders: list[str] = []
    try:
        with os.scandir(vault) as entries:
            for entry in entries:
                if entry.name in project_meta._FILE_INDEX_SKIP:
                    continue
                if entry.is_symlink():
                    issues.append(f"Root entry {_literal(entry.name)} excluded: symlinks are not followed.")
                elif entry.is_dir(follow_symlinks=False):
                    folders.append(entry.name)
    except OSError:
        issues.append("Root folder inventory is incomplete: vault directory is unreadable.")
    lines: list[str] = []
    for name in sorted(folders, key=lambda value: (value.casefold(), value)):
        lines.append(f"- {_link(name + '/', Path(name))} — {_literal(descriptions.get(name, NO_DESCRIPTION))}")
        if name == "Projects":
            lines.extend(project_rows)
    if project_rows and "Projects" not in folders:
        lines.append("- Projects/ — Unavailable: no safe existing Projects directory")
        lines.extend(project_rows)
    now = datetime.now(timezone.utc)
    metadata = {
        "nexus": [], "type": "directory_map", "tags": [],
        "date created": now.date(), "date modified": now.date(),
        "description": "Generated shallow folder orientation from existing local authorities.",
    }
    body = [
        "# Directory Map", "", MARKER, "",
        f"Generated on: {now.isoformat(timespec='seconds')}",
        f"Covered root: {_literal(str(vault))}", "",
        "Coverage: immediate vault folders and registered project folders under Projects/. "
        "Files and deeper folders are not inventoried. Configuration, trash and dependency folders are excluded.",
        "This is a replaceable snapshot, not continuous freshness or another source of authority. "
        "Names, descriptions and links retain their source privacy; this map does not authorize uploading them.", "",
        "Status: Complete for stated coverage." if not issues else "Status: INCOMPLETE — some source information is unavailable.",
        "", "## Folders", "", *(lines or ["No eligible folders found."]),
    ]
    if issues:
        body.extend(["", "## Unavailable information", "", *(f"- {issue}" for issue in issues)])
    text = "---\n" + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + "---\n\n" + "\n".join(body) + "\n"
    require_valid_document(text, DocumentIdentity(nexuses=(), filename=MAP_NAME, heading="Directory Map"), owner="directory_map")
    return DirectoryMap(text, issues)


def write_directory_map(vault: Path | str, result: DirectoryMap) -> Path:
    """Replace only our generated file, preserving any previous output on failure."""
    vault = _root(vault)
    path = vault / MAP_NAME
    mode = 0o600
    try:
        existing = _read(path, vault).decode("utf-8")
        if not re.search(r"\n# Directory Map\r?\n\r?\n" + re.escape(MARKER) + r"(?:\r?\n|$)", existing):
            raise ValueError("Directory Map.md is an unrecognized existing user file")
        mode = stat.S_IMODE(_safe_path(path, vault).st_mode)
    except FileNotFoundError:
        pass
    require_valid_document(result.text, DocumentIdentity(nexuses=(), filename=MAP_NAME, heading="Directory Map"), owner="directory_map")
    runtime_paths.atomic_write_bytes(path, result.text.encode("utf-8"), mode=mode)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ora-root", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--write", action="store_true", help="Replace this vault's marked Directory Map.md")
    args = parser.parse_args(argv)
    try:
        result = generate_directory_map(ora_root=args.ora_root, vault=args.vault)
        if args.write:
            write_directory_map(args.vault, result)
            print(f"Saved {MAP_NAME}" + (" (incomplete; see unavailable information)." if not result.complete else "."))
        else:
            print(result.text, end="")
        return 0 if result.complete else 2
    except (OSError, UnicodeError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "selected storage is unavailable or unreadable"
        print(f"Directory map refused: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
