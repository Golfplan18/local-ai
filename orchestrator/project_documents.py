"""Strict, report-only metadata inspection for document owners and explicit checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DocumentIdentity:
    """Authority supplied by the producer; None is unavailable, () is Commons."""

    nexuses: tuple[str, ...] | None
    filename: str | None = None
    heading: str | None = None
    created: str | date | None = None
    modified: str | date | None = None


@dataclass(frozen=True)
class DocumentIssue:
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass
class DocumentReport:
    errors: list[DocumentIssue] = field(default_factory=list)
    warnings: list[DocumentIssue] = field(default_factory=list)
    complete: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def warning_messages(self) -> list[str]:
        return [str(issue) for issue in self.warnings]


class InvalidProjectDocumentError(ValueError):
    """Safe refusal: field names and reasons, never document prose or paths."""

    def __init__(self, report: DocumentReport):
        self.report = report
        reasons = report.errors or [DocumentIssue("identity", "authority is incomplete")]
        super().__init__("Document metadata refused: " + "; ".join(map(str, reasons)))


class _StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _value in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in seen:
                raise yaml.YAMLError("mapping keys must be unique text")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _calendar_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def inspect_document(text: str, identity: DocumentIdentity, *, owner: str) -> DocumentReport:
    """Inspect without changing input or performing any filesystem operations."""
    report = DocumentReport(complete=identity.nexuses is not None and owner in {"ordinary", "matrix", "output", "chat", "directory_map"})
    error = lambda field, reason: report.errors.append(DocumentIssue(field, reason))
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        error("frontmatter", "leading YAML is missing or unterminated")
        return report
    try:
        metadata = yaml.load(match.group(1), Loader=_StrictLoader)
    except (yaml.YAMLError, ValueError, TypeError, RecursionError):
        error("frontmatter", "YAML must be a valid mapping with unique text keys")
        return report
    if not isinstance(metadata, dict):
        error("frontmatter", "YAML must be a mapping")
        return report
    report.metadata = metadata
    for key in ("nexus", "type", "tags", "date created", "date modified"):
        if key not in metadata:
            error(key, "required field is missing")
    from orchestrator.project_meta import validate_existing_nexus_source, NexusValidationError
    for key in ("nexus", "tags"):
        if key not in metadata:
            continue
        values = metadata[key]
        if values is None:  # The schema's bare empty-list representation.
            values = []
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            error(key, "must be a list of nonempty text values or empty")
            continue
        if key == "nexus":
            for value in values:
                try:
                    validate_existing_nexus_source(value)
                except NexusValidationError:
                    error("nexus", "contains an invalid existing nexus")
                    break
            if identity.nexuses is not None and set(values) != set(identity.nexuses):
                error("nexus", "does not match authenticated destination identity")
    type_value = metadata.get("type")
    if "type" in metadata and (not isinstance(type_value, str) or not type_value.strip()):
        error("type", "must be a nonempty text scalar")
    for key, expected in (("date created", identity.created), ("date modified", identity.modified)):
        if key not in metadata:
            continue
        actual = _calendar_date(metadata[key])
        if actual is None:
            error(key, "must be a real calendar date in YYYY-MM-DD form")
        elif expected is not None and actual != _calendar_date(expected):
            error(key, "does not match the owner's source date")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        report.warnings.append(DocumentIssue("description", "No recorded description"))
    if identity.nexuses is None:
        report.complete = False
        error("identity", "authenticated nexus authority is unavailable")
    expected_types = {"matrix": "matrix", "output": "output", "chat": "chat", "directory_map": "directory_map"}
    if owner == "ordinary" and isinstance(type_value, str) and type_value in expected_types:
        report.complete = False
        report.warnings.append(DocumentIssue("owner", "specialized contract not checked: select its authenticated owner"))
    if owner in expected_types and type_value != expected_types[owner]:
        error("type", f"must be {expected_types[owner]} for this owner")
    if owner == "matrix":
        from orchestrator.matrix_classifier import schema_valid
        if not schema_valid(metadata):
            error("project_type", "must be a schema-valid Matrix classification list")
        if identity.nexuses is not None and len(identity.nexuses) != 1:
            error("nexus", "a project Matrix requires one authenticated project")
    if owner not in {*expected_types, "ordinary"}:
        report.complete = False
        report.warnings.append(DocumentIssue("owner", "specialized contract not checked"))
    if owner == "output" and identity.filename is not None:
        # The exporter preserves Unicode word characters and underscores. A
        # tight portable path budget can shorten even the date prefix; numeric
        # collision suffixes are added after that truncation.
        output_date = _calendar_date(identity.created) or _calendar_date(metadata.get("date created"))
        truncated_date = output_date is not None and any(
            re.fullmatch(re.escape(output_date.isoformat()[:end].rstrip("-")) + r"(?:-\d+)?\.md", identity.filename)
            for end in range(1, 11)
        )
        if not (re.fullmatch(r"\d{4}-\d{2}-\d{2} [\w-]+\.md", identity.filename) or truncated_date):
            error("filename", "must use the owner's dated output slug")
    expected_heading = identity.heading
    if owner == "ordinary" and identity.filename:
        expected_heading = Path(identity.filename).stem
    if expected_heading is not None:
        heading = re.search(r"^# +([^\r\n]+)\r?$", text[match.end():], re.M)
        if not heading or heading.group(1).rstrip() != expected_heading:
            error("heading", "does not match the owner's document label")
    return report


def require_valid_document(text: str, identity: DocumentIdentity, *, owner: str) -> DocumentReport:
    report = inspect_document(text, identity, owner=owner)
    if report.errors or not report.complete:
        raise InvalidProjectDocumentError(report)
    return report


def _safe_path(root: Path, relative: str, *, directory: bool = False) -> Path:
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise OSError("path must stay inside the selected root")
    path = root
    for component in part.parts:
        path = path / component
        if path.is_symlink():
            raise OSError("symlinks are not selected")
    mode = path.stat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise OSError("not a regular directory" if directory else "not a regular file")
    return path


def _read_text(root: Path, relative: str) -> str:
    path = _safe_path(root, relative)
    before = path.stat()
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise OSError("file changed while reading")
        return stream.read().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report metadata findings without repairs")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--ora-root", required=True, type=Path)
    check.add_argument("--vault", required=True, type=Path)
    targets = check.add_mutually_exclusive_group(required=True)
    targets.add_argument("--project")
    targets.add_argument("--file")
    check.add_argument("--owner", choices=("ordinary", "matrix", "output", "chat"))
    args = parser.parse_args(argv)
    if bool(args.file) != bool(args.owner):
        parser.error("--owner is required only with --file")
    from orchestrator import project_meta as pm, operation_matrix as om
    errors = warnings = 0
    complete = True

    def emit(relative: str, report: DocumentReport):
        nonlocal errors, warnings, complete
        errors += len(report.errors)
        warnings += len(report.warnings)
        complete = complete and report.complete
        for level, issues in (("error", report.errors), ("warning", report.warnings)):
            for issue in issues:
                print(f"{relative}: {level}: {issue}")
        if not report.errors and not report.warnings:
            print(f"{relative}: valid")

    def unavailable(relative: str, reason: str):
        emit(relative, DocumentReport(errors=[DocumentIssue("selection", reason)], complete=False))

    try:
        for root in (args.ora_root, args.vault):
            if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() != root:
                raise OSError("explicit roots must be existing absolute nonsymlink directories")
        pdir = args.ora_root / "data" / "projects"
        if pdir.exists():
            _safe_path(args.ora_root, "data/projects", directory=True)
        # The existing reader supplies project normalization, but only after
        # every selected pointer has passed the nonsymlink boundary.
        records = []
        if pdir.exists():
            for pointer in sorted(pdir.glob("*.json")):
                try:
                    pm.validate_existing_nexus_source(pointer.stem)
                    data = json.loads(_read_text(args.ora_root, str(pointer.relative_to(args.ora_root))))
                    if not isinstance(data, dict):
                        raise OSError("unreadable project authority")
                    record = pm._normalize_meta(pointer.stem, data)
                    records.append(record)
                except (OSError, ValueError, UnicodeError):
                    continue  # Only a selected document's authority affects its result.
        known = {r["nexus"]: r for r in records}
        requests = {r["nexus"]: r.get("folder_name") for r in records
                    if args.owner == "matrix" or r["nexus"] == args.project}
        snapshots = om.resolve_matrix_snapshots(requests, vault=args.vault) if requests else {}
        matrix_by_path = {value[0]: known[nexus] for nexus, value in snapshots.items() if isinstance(value, tuple)}

        def inspect_file(relative: str, owner: str, project=None):
            try:
                if Path(relative).suffix.lower() != ".md":
                    raise OSError("selection must be Markdown")
                text = _read_text(args.vault, relative)
                path = args.vault / relative
                record = matrix_by_path.get(path)
                if project is None and path.parts[len(args.vault.parts):len(args.vault.parts) + 1] == ("Projects",):
                    matches = []
                    for candidate in records:
                        try:
                            folder = pm.project_folder_path(candidate["folder_name"], vault_projects_dir=args.vault / "Projects")
                            if path.is_relative_to(folder):
                                matches.append(candidate)
                        except pm.ProjectStorageError:
                            continue
                    if len(matches) != 1:
                        unavailable(relative, "project-folder authority is unavailable or ambiguous")
                        return
                    project = matches[0]
                # First inspect universal shapes; authority is established below.
                preliminary = inspect_document(text, DocumentIdentity(()), owner="ordinary")
                values = preliminary.metadata.get("nexus") or []
                authority = tuple(values) if isinstance(values, list) and all(isinstance(v, str) and v in known for v in values) else None
                heading = None
                if project is not None and authority is not None and project["nexus"] not in values:
                    authority = (project["nexus"],)
                if owner == "matrix":
                    if record is None:
                        authority = None
                    else:
                        authority = (record["nexus"],)
                        # Existing Project/Operation/Passion Matrices retain
                        # their authenticated historical names and labels.
                        # Only the new Project template owns a current-label H1.
                report = inspect_document(text, DocumentIdentity(authority, path.name, heading), owner=owner)
                if owner in {"output", "chat"}:
                    report.complete = False
                    report.warnings.append(DocumentIssue("owner", "specialized contract not checked: authenticated producer source is unavailable"))
                emit(relative, report)
            except (OSError, UnicodeError):
                unavailable(relative, "unsafe or unreadable document")

        if args.file:
            inspect_file(args.file, args.owner)
        else:
            pm.validate_existing_nexus_source(args.project)
            project = known.get(args.project)
            if project is None:
                raise OSError("selected project authority is unavailable")
            folder = pm.project_folder_path(project["folder_name"], vault_projects_dir=args.vault / "Projects")
            try:
                _safe_path(args.vault, str(folder.relative_to(args.vault)), directory=True)
                def walk(directory):
                    try:
                        for child in sorted(directory.iterdir()):
                            relative = str(child.relative_to(args.vault))
                            if child.is_symlink():
                                unavailable(relative, "symlink is not selected")
                            elif child.is_dir():
                                walk(child)
                            elif child.suffix.lower() == ".md":
                                inspect_file(relative, "unfamiliar", project)
                    except OSError:
                        unavailable(str(directory.relative_to(args.vault)), "directory is unreadable")
                walk(folder)
            except OSError:
                unavailable(str(folder.relative_to(args.vault)), "project folder is unavailable or unsafe")
            snapshot = snapshots.get(args.project)
            if isinstance(snapshot, tuple):
                inspect_file(str(snapshot[0].relative_to(args.vault)), "matrix", project)
            else:
                unavailable("Matrix", "authenticated Matrix is missing or ambiguous/unreadable")
    except (OSError, ValueError, pm.ProjectStorageError):
        unavailable("selection", "explicit root or project authority is unavailable or unsafe")
    print(f"{errors} error(s), {warnings} warning(s); {'complete' if complete else 'incomplete'}")
    return 2 if not complete else 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
