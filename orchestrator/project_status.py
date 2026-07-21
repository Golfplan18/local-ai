"""Deterministic Operation-Matrix status context for G1.5.

Ordinary vault RAG deliberately excludes or down-weights some matrix material,
and Gear 1 does not run the heavy retrieval path at all.  A direct question
about a registered project's current status therefore needs a small,
identity-bound source resolver rather than a hope that semantic retrieval
happens to find the right note.

This module is read-only.  It recognizes an explicit status request for one of
the two G1.5 Operations, resolves exactly one Matrix by frontmatter nexus,
requires the Matrix to classify as an Operation, and follows only wikilinks in
its Spawned Activity Registry.  Registered child excerpts are accepted only
when the child carries the same nexus.  Ambiguous/missing/invalid sources fail
closed into an explicit gap record; they never invite a model to infer status
from unrelated vault text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

try:
    from matrix_classifier import classify_matrix
    from operation_matrix import (
        MatrixAmbiguityError,
        _frontmatter_nexus,
        _split_frontmatter,
        resolve_matrix_path,
    )
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator.matrix_classifier import classify_matrix
    from orchestrator.operation_matrix import (
        MatrixAmbiguityError,
        _frontmatter_nexus,
        _split_frontmatter,
        resolve_matrix_path,
    )


_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "nexus": "ora",
        "label": "Ora",
        "aliases": (r"\bora\b",),
    },
    {
        "nexus": "main-street-independent",
        "label": "Main Street Independent (MSI)",
        "aliases": (r"\bmsi\b", r"\bmain\s+street\s+independent\b"),
    },
)

_PROJECT_ALIAS_SOURCE = r"(?:ora|msi|main\s+street\s+independent)"
_PROJECT_STATUS_RELATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in (
        # "What's the status of Ora?", "Give me an update on MSI."
        r"\b(?:the\s+)?(?:project\s+)?(?:status|progress|current\s+state|update)"
        r"\s+(?:of|for|on)\s+(?P<target>[^.!?\n]+)",
        # "What's happening with Ora and MSI?"
        r"\bwhat(?:'s|\s+is)\s+happening\s+(?:with|on)\s+"
        r"(?P<target>[^.!?\n]+)",
        # "How is MSI doing?"
        r"\bhow(?:'s|\s+(?:is|are))\s+(?P<target>.+?)\s+"
        r"(?:doing|going|progressing)\b",
        # "Where does Ora stand?"
        r"\bwhere\s+(?:does|do|is|are)\s+(?P<target>.+?)\s+stand\b",
        # "Where do we stand on Ora?"
        r"\bwhere\s+(?:do|are)\s+we\s+stand\s+(?:on|with)\s+"
        r"(?P<target>[^.!?\n]+)",
        # "Ora's project status" / "MSI progress". The relationship word
        # must immediately qualify the named project; technical compounds such
        # as status-code and progress-event therefore do not match.
        rf"\b(?P<target>{_PROJECT_ALIAS_SOURCE})(?:['’]s)?\s+"
        r"(?:project\s+)?(?:status|progress|current\s+state|update)\b"
        r"(?!\s+(?:code|codes|event|events|machine|machines|model|models|"
        r"handler|handlers|handling|transition|transitions))",
    )
)
_ALLOWED_TARGET_WORDS = frozenset({
    "and", "the", "both", "project", "projects", "operation", "operations",
    "please", "right", "now", "today", "currently", "overall", "s",
})
_WIKILINK_RE = re.compile(
    r"\[\[(?P<path>[^\]|#]+?)(?:#(?P<fragment>[^\]|]+))?"
    r"(?:\|[^\]]+)?\]\]"
)
_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)

_MATRIX_SECTIONS = (
    "Mission",
    "Objectives",
    "Active Milestones (Recurring)",
    "Aspirational Milestones (Maturity Gates)",
    "Performance Log",
    "Open Questions / Strategic Topics",
    "Spawned Activity Registry",
)
_MATRIX_CHAR_LIMIT = 10_500
_CHILD_CHAR_LIMIT = 8_000
_CHILD_EXCERPT_LIMIT = 2_400
_MAX_CHILDREN = 8


def _vault_root(vault: Path | None = None) -> Path:
    if vault is not None:
        return Path(vault).expanduser().resolve()
    accessor = getattr(_rp, "vault_dir", None)
    if callable(accessor):
        return Path(accessor()).expanduser().resolve()
    return (Path.home() / "Documents" / "vault").resolve()


def _projects_in_relationship_target(target_text: str) -> list[dict[str, Any]]:
    """Accept a target composed of project identities and connective words.

    This is the key subject/object boundary.  A target such as ``Ora and MSI``
    is project-shaped.  ``Ora's state machine`` or ``MSI progress events`` is
    not: after removing project aliases, material technical nouns remain.
    """
    remaining = str(target_text or "").casefold()
    matched: list[dict[str, Any]] = []
    for project in _PROJECTS:
        found = False
        for alias in project["aliases"]:
            if re.search(alias, remaining, re.IGNORECASE):
                found = True
                remaining = re.sub(alias, " ", remaining, flags=re.IGNORECASE)
        if found:
            matched.append(project)
    if not matched:
        return []
    words = re.findall(r"[a-z0-9]+", remaining.replace("’", "'"))
    if any(word not in _ALLOWED_TARGET_WORDS for word in words):
        return []
    return matched


def requested_projects(prompt: str) -> list[dict[str, Any]]:
    """Return exact G1.5 project targets for an explicit status request.

    A status-like word is insufficient.  A recognized grammatical relationship
    must make the named project the subject of status/progress/update, and the
    target may contain only registered project names plus connective words.
    Thus ``Ask Ora for the status of MSI`` selects MSI, while ``HTTP status 500
    in Ora`` and ``MSI progress events`` select nothing.
    """
    text = str(prompt or "").strip().replace("’", "'")
    if not text:
        return []
    for pattern in _PROJECT_STATUS_RELATION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        projects = _projects_in_relationship_target(match.group("target"))
        if projects:
            return projects
    return []


def _extract_heading(text: str, heading: str) -> str:
    target = heading.strip().casefold()
    matches = list(_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        if match.group("title").strip().casefold() != target:
            continue
        level = len(match.group("marks"))
        body_start = match.end()
        if body_start < len(text) and text[body_start] == "\n":
            body_start += 1
        section_end = len(text)
        for later in matches[index + 1 :]:
            if len(later.group("marks")) <= level:
                section_end = later.start()
                break
        return text[body_start:section_end].strip()
    return ""


def _relative(path: Path, vault: Path) -> str:
    try:
        return path.resolve().relative_to(vault).as_posix()
    except (OSError, ValueError):
        return path.name


def _resolve_child_path(target: str, *, vault: Path) -> Path | None:
    raw = str(target or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        return None
    direct = vault / raw
    if direct.suffix.lower() != ".md":
        direct = direct.with_suffix(".md")
    try:
        resolved = direct.resolve()
        resolved.relative_to(vault)
    except (OSError, ValueError):
        return None
    if resolved.is_file():
        return resolved

    # Obsidian permits basename-only wikilinks.  Accept one exact match, but
    # fail closed when multiple notes share the same name.
    name = Path(raw).name
    if not name.lower().endswith(".md"):
        name += ".md"
    matches: list[Path] = []
    for path in vault.rglob(name):
        if not path.is_file():
            continue
        try:
            candidate = path.resolve()
            candidate.relative_to(vault)
        except (OSError, ValueError):
            continue
        matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _child_excerpt(text: str, fragment: str | None) -> str:
    if fragment:
        return _extract_heading(text, fragment)[:_CHILD_EXCERPT_LIMIT].strip()
    _, body_start = _split_frontmatter(text)
    body = text[body_start:].lstrip()
    headings = list(_HEADING_RE.finditer(body))
    if headings and len(headings[0].group("marks")) == 1:
        start = headings[0].end()
        if start < len(body) and body[start] == "\n":
            start += 1
        end = len(body)
        for later in headings[1:]:
            if len(later.group("marks")) <= 2:
                end = later.start()
                break
        body = body[start:end]
    return body.strip()[:_CHILD_EXCERPT_LIMIT].strip()


def _format_matrix_source(
    project: dict[str, Any], *, vault: Path
) -> tuple[str, list[str], str | None]:
    nexus = project["nexus"]
    warnings: list[str] = []
    try:
        matrix_path = resolve_matrix_path(nexus, vault=vault)
    except MatrixAmbiguityError as exc:
        return "", [str(exc)], None
    except Exception as exc:
        return "", [f"matrix resolution failed for {nexus}: {exc}"], None
    if matrix_path is None:
        return "", [f"no Matrix file claims nexus {nexus!r}"], None
    try:
        text = matrix_path.read_text(encoding="utf-8")
    except OSError as exc:
        return "", [f"could not read {_relative(matrix_path, vault)}: {exc}"], None

    frontmatter, _ = _split_frontmatter(text)
    try:
        classification, classifier_warnings = classify_matrix(
            frontmatter, str(matrix_path)
        )
    except Exception as exc:
        return "", [f"invalid Matrix {_relative(matrix_path, vault)}: {exc}"], None
    warnings.extend(str(item) for item in classifier_warnings)
    if classification != "operation":
        return "", [
            f"Matrix {_relative(matrix_path, vault)} classifies as "
            f"{classification!r}, not 'operation'"
        ], None

    pieces = [
        f"# PROJECT STATUS SOURCE — {project['label']}",
        f"Matrix: `{_relative(matrix_path, vault)}`",
        f"Nexus: `{nexus}`",
        "Classification: `operation`",
    ]
    used = sum(len(piece) for piece in pieces)
    registry = ""
    for heading in _MATRIX_SECTIONS:
        section = _extract_heading(text, heading)
        if heading == "Spawned Activity Registry":
            registry = section
        if not section:
            warnings.append(f"Matrix section missing: {heading}")
            continue
        remaining = _MATRIX_CHAR_LIMIT - used
        if remaining <= 0:
            break
        rendered = f"## {heading}\n\n{section}"
        rendered = rendered[:remaining].rstrip()
        pieces.append(rendered)
        used += len(rendered)

    child_blocks: list[str] = []
    child_used = 0
    seen: set[str] = set()
    for match in _WIKILINK_RE.finditer(registry):
        if len(seen) >= _MAX_CHILDREN or child_used >= _CHILD_CHAR_LIMIT:
            break
        target = match.group("path").strip()
        fragment = (match.group("fragment") or "").strip() or None
        key = f"{target}#{fragment or ''}"
        if key in seen:
            continue
        seen.add(key)
        child_path = _resolve_child_path(target, vault=vault)
        if child_path is None:
            warnings.append(f"registered child cannot be resolved uniquely: {key}")
            continue
        try:
            child_text = child_path.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"registered child unreadable: {key}: {exc}")
            continue
        child_nexus = _frontmatter_nexus(child_text)
        if nexus not in child_nexus:
            warnings.append(
                f"registered child nexus mismatch: {_relative(child_path, vault)} "
                f"does not claim {nexus!r}"
            )
            continue
        excerpt = _child_excerpt(child_text, fragment)
        if not excerpt:
            warnings.append(f"registered child section is empty or missing: {key}")
            continue
        identity = _relative(child_path, vault)
        if fragment:
            identity += f"#{fragment}"
        block = f"### REGISTERED ACTIVITY — `{identity}`\n\n{excerpt}"
        remaining = _CHILD_CHAR_LIMIT - child_used
        block = block[:remaining].rstrip()
        child_blocks.append(block)
        child_used += len(block)

    if child_blocks:
        pieces.append("## Registered activity evidence\n\n" + "\n\n".join(child_blocks))
    return "\n\n".join(pieces).strip(), warnings, _relative(matrix_path, vault)


def resolve_status_request(prompt: str, *, vault: Path | None = None) -> dict[str, Any]:
    """Resolve status context and provenance for an explicit G1.5 request."""
    targets = requested_projects(prompt)
    if not targets:
        return {
            "matched": False,
            "projects": [],
            "context": "",
            "warnings": [],
        }

    root = _vault_root(vault)
    blocks: list[str] = []
    warnings: list[str] = []
    projects: list[dict[str, Any]] = []
    for target in targets:
        block, project_warnings, matrix_path = _format_matrix_source(
            target, vault=root
        )
        warnings.extend(project_warnings)
        projects.append({
            "nexus": target["nexus"],
            "label": target["label"],
            "matrix_path": matrix_path,
            "ready": bool(block),
        })
        if block:
            blocks.append(block)

    if warnings:
        warning_block = "## SOURCE WARNINGS\n\n" + "\n".join(
            f"- {warning}" for warning in warnings
        )
        blocks.append(warning_block)
    if not any(project["ready"] for project in projects):
        blocks.append(
            "## FAIL-CLOSED STATUS\n\nNo authenticated Operation Matrix was "
            "available for the requested project. Do not infer current status "
            "from unrelated conversation memory or general vault retrieval."
        )
    return {
        "matched": True,
        "projects": projects,
        "context": "\n\n---\n\n".join(blocks).strip(),
        "warnings": warnings,
    }


def build_project_status_context(prompt: str, *, vault: Path | None = None) -> str:
    """Return model-facing authenticated status context, or ``""``."""
    return resolve_status_request(prompt, vault=vault)["context"]


__all__ = [
    "build_project_status_context",
    "requested_projects",
    "resolve_status_request",
]
