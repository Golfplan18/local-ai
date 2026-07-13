"""Type-specific read-only payload readers for Matrix files.

Each reader resolves a project's Matrix file, classifies it via the shared
``matrix_classifier.classify_matrix``, and extracts the H2 sections
appropriate to the classified type.  Returns a dict with:

  - ``exists``: whether a Matrix file was found
  - ``state``: "ok", "missing", "ambiguous", or "invalid" (from diagnose_matrix)
  - ``classification``: the resolved type (when state is "ok")
  - ``warnings``: list of classifier warnings
  - ``payload``: dict of section-name → raw-text (type-specific keys)
  - ``matrix_path``: path to the Matrix file (when found)

The readers are read-only — they never write to the Matrix file.

Canonical section shapes (from the approved proposal):

Project:       Mission, Objectives, Milestones
Passion legacy: Mission, Objectives, Milestones, Projects, Files,
                Problem Solving, Spawned Activity Registry
Passion newer:  Mission, Practices, Directions of Travel, Operations,
                Open Items
Operation:      Mission, Excluded Outcomes, Objectives, Constraints,
                Cadence and Deliverables, Coordinated Corpora,
                Coordinated Outputs, Active Milestones,
                Aspirational Milestones, Performance Log, Incident Log,
                Open Questions / Strategic Topics,
                Spawned Activity Registry, Iteration History, Decision Log
Incubator:      Critical Unknown, Candidate Classifications,
                Exploration Plan (required); Source Intersection,
                Founding Iteration Entry (optional)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---- Section sets per classification ----

_PROJECT_SECTIONS = [
    "Mission", "Objectives", "Milestones",
]

_PASSION_LEGACY_SECTIONS = [
    "Mission", "Objectives", "Milestones",
    "Projects", "Files", "Problem Solving", "Spawned Activity Registry",
]

_PASSION_NEWER_SECTIONS = [
    "Mission", "Practices", "Directions of Travel", "Operations", "Open Items",
]

_OPERATION_SECTIONS = [
    "Mission", "Excluded Outcomes", "Objectives", "Constraints",
    "Cadence and Deliverables", "Coordinated Corpora", "Coordinated Outputs",
    "Active Milestones", "Aspirational Milestones",
    "Performance Log", "Incident Log",
    "Open Questions / Strategic Topics",
    "Spawned Activity Registry", "Iteration History", "Decision Log",
]

_INCUBATOR_REQUIRED = [
    "Critical Unknown", "Candidate Classifications", "Exploration Plan",
]

_INCUBATOR_OPTIONAL = [
    "Source Intersection", "Founding Iteration Entry",
]

_INCUBATOR_SECTIONS = _INCUBATOR_REQUIRED + _INCUBATOR_OPTIONAL

# Sections that contain `- [ ]` / `- [x]` task lists.
_TASK_LIST_SECTIONS = {"Milestones", "Active Milestones", "Aspirational Milestones"}


# ---- Helpers ----

def _extract_section(text: str, heading: str) -> str:
    """Extract the body of ``## heading`` from *text*.  Returns "" if absent."""
    target = heading.strip().lower()
    h2_re = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
    matches = list(h2_re.finditer(text))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == target:
            body_start = m.end()
            if body_start < len(text) and text[body_start] == "\n":
                body_start += 1
            section_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[body_start:section_end].strip()
    return ""


_TASK_RE = re.compile(r"^([ \t]*)-[ \t]+\[([ xX])\][ \t]?(.*)$")


def _parse_tasks(raw: str) -> list[dict[str, Any]]:
    """Parse ``- [ ]`` / ``- [x]`` task lines into structured records."""
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


def _read_sections(text: str, section_names: list[str]) -> dict[str, str]:
    """Extract named sections from *text*.  Only present sections are included."""
    result: dict[str, str] = {}
    for name in section_names:
        body = _extract_section(text, name)
        if body:
            result[name] = body
    return result


def _read_sections_with_tasks(
    text: str,
    section_names: list[str],
    task_sections: set[str] | None = None,
) -> dict[str, Any]:
    """Extract sections, adding parsed task lists for designated sections.

    Task-list sections return ``{"raw": text, "tasks": [...]}``.
    Non-task sections return the raw text as a plain string.
    """
    task_sections = task_sections or set()
    result: dict[str, Any] = {}
    for name in section_names:
        body = _extract_section(text, name)
        if not body:
            continue
        if name in task_sections:
            result[name] = {"raw": body, "tasks": _parse_tasks(body)}
        else:
            result[name] = body
    return result


# ---- Main entry point ----

def read_payload(
    nexus: str,
    folder_name: str | None = None,
    *,
    vault: Path | None = None,
) -> dict[str, Any]:
    """Read a Matrix file's type-specific payload.

    Returns a dict with ``exists``, ``state``, ``classification``,
    ``warnings``, ``payload``, and ``matrix_path``.  Never raises.
    """
    # Lazy imports to avoid circular dependency.
    try:
        from matrix_classifier import classify_matrix, schema_valid, InvalidProjectTypeError
        from operation_matrix import resolve_matrix_path, _split_frontmatter, MatrixAmbiguityError
    except ImportError:
        from orchestrator.matrix_classifier import classify_matrix, schema_valid, InvalidProjectTypeError
        from orchestrator.operation_matrix import resolve_matrix_path, _split_frontmatter, MatrixAmbiguityError

    nexus_l = (nexus or "").strip().lower()
    if not nexus_l or nexus_l in ("commons", "general"):
        return _empty_payload()

    # Resolve Matrix file.
    try:
        path = resolve_matrix_path(nexus, folder_name, vault=vault)
    except MatrixAmbiguityError as exc:
        return {
            "exists": False, "state": "ambiguous", "classification": None,
            "warnings": [str(exc)], "payload": {}, "matrix_path": None,
        }
    except Exception as exc:
        return {
            "exists": False, "state": "invalid", "classification": None,
            "warnings": [str(exc)], "payload": {}, "matrix_path": None,
        }

    if path is None:
        return _empty_payload()

    # Read file.
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "exists": True, "state": "invalid", "classification": None,
            "warnings": [f"Could not read Matrix file: {exc}"],
            "payload": {}, "matrix_path": str(path),
        }

    frontmatter, _ = _split_frontmatter(text)

    # Classify.
    try:
        classification, warnings = classify_matrix(frontmatter, str(path))
    except InvalidProjectTypeError as exc:
        return {
            "exists": True, "state": "invalid", "classification": None,
            "warnings": [str(exc)], "payload": {}, "matrix_path": str(path),
        }
    except Exception as exc:
        return {
            "exists": True, "state": "invalid", "classification": None,
            "warnings": [f"Classification failed: {exc}"],
            "payload": {}, "matrix_path": str(path),
        }

    # Dispatch to type-specific reader.
    payload = _read_by_type(text, classification)

    return {
        "exists": True,
        "state": "ok",
        "classification": classification,
        "warnings": warnings,
        "payload": payload,
        "matrix_path": str(path),
    }


def _empty_payload() -> dict[str, Any]:
    return {
        "exists": False, "state": "missing", "classification": None,
        "warnings": [], "payload": {}, "matrix_path": None,
    }


def _read_by_type(text: str, classification: str) -> dict[str, Any]:
    """Dispatch to the type-specific section reader."""
    if classification == "project":
        return _read_project(text)
    if classification == "operation":
        return _read_operation(text)
    if classification == "passion":
        return _read_passion(text)
    if classification == "incubator":
        return _read_incubator(text)
    return {}


def _read_project(text: str) -> dict[str, Any]:
    """Project payload: Mission, Objectives, Milestones (with task parsing)."""
    return _read_sections_with_tasks(text, _PROJECT_SECTIONS, _TASK_LIST_SECTIONS)


def _read_passion(text: str) -> dict[str, Any]:
    """Passion payload: tries the newer shape first, falls back to legacy.

    The newer shape has Practices/Directions of Travel.  If those sections
    are absent, the legacy shape (Objectives/Milestones) is used.
    """
    # Try newer shape.
    newer = _read_sections_with_tasks(text, _PASSION_NEWER_SECTIONS, _TASK_LIST_SECTIONS)
    if "Practices" in newer or "Directions of Travel" in newer:
        return newer
    # Fall back to legacy shape.
    return _read_sections_with_tasks(text, _PASSION_LEGACY_SECTIONS, _TASK_LIST_SECTIONS)


def _read_operation(text: str) -> dict[str, Any]:
    """Operation payload: all Operation-shape sections."""
    return _read_sections_with_tasks(text, _OPERATION_SECTIONS, _TASK_LIST_SECTIONS)


def _read_incubator(text: str) -> dict[str, Any]:
    """Incubator payload: Critical Unknown, Candidate Classifications,
    Exploration Plan (required); Source Intersection, Founding Iteration
    Entry (optional)."""
    return _read_sections(text, _INCUBATOR_SECTIONS)


__all__ = ["read_payload"]
